"""Preview the official update channel. Apply only an explicitly selected commit."""
import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
REMOTE = "https://github.com/allyfranch84-blip/BRAINNET.git"
BRANCH = "refs/heads/updates/local"
REF = "refs/remotes/brainnet-updates/local"
PATCH = "updates/current.py"
MANIFEST = "updates/release.json"
PROJECT = Path("INTERFACE DE USUARIO/BRAINDET IU/project")
# Installed client policy. New destinations require a reviewed client change.
TARGETS = frozenset((
    "BRAIN/inference_supervisor.py", "BRAIN/test_inference_supervisor.py",
    "iniciar/iniciar_aios.bat",
))


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], timeout=90)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def source_hash(data):
    return sha(data.replace(b"\r\n", b"\n"))


def safe_path(root, name):
    path = root
    for part in (".", *Path(name).parts):
        path = path / part
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError("Caminho redirecionado: " + str(part))
    return path


def git_blob(commit, name):
    spec = f"{commit}:{name}"
    if int(git("cat-file", "-s", spec)) > 4 * 1024 * 1024:
        raise ValueError("Arquivo excede o limite por atualização")
    return git("cat-file", "blob", spec)


def plan(root, release, read_blob):
    if not isinstance(release, dict) or release.get("format") != 1:
        raise ValueError("Formato de pacote incompatível")
    entries = release.get("files")
    if not isinstance(entries, list) or not entries or len(entries) > len(TARGETS):
        raise ValueError("Lista de arquivos inválida")
    result = {}
    for item in entries:
        name = item["path"]
        if name not in TARGETS or name in result or set(item) != {"path", "before", "after"}:
            raise ValueError("Destino inválido ou duplicado")
        if any(not isinstance(h, str) or not re.fullmatch("[0-9a-f]{64}", h) for h in (item["before"], item["after"])):
            raise ValueError("Hash inválido")
        new = read_blob(name)
        if source_hash(new) != item["after"]:
            raise ValueError("Hash do conteúdo remoto divergente: " + name)
        path = safe_path(root, name)
        old = path.read_bytes() if path.is_file() else None
        current = source_hash(old) if old is not None else None
        status = "PRESENT" if current == item["after"] else "UPDATE" if current == item["before"] else "CONFLICT"
        # Preserve the checked-out file's CRLF convention.
        if old and b"\r\n" in old and b"\n" not in old.replace(b"\r\n", b""):
            new = new.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        result[name] = (status, old, new)
    return result


def replace_if_unchanged(root, name, expected, replacement):
    path = safe_path(root, name)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, prefix=".bn-update-") as f:
        tmp = Path(f.name)
        try:
            f.write(replacement)
            f.flush()
            os.fsync(f.fileno())
        except BaseException:
            f.close()
            tmp.unlink()
            raise
    try:
        if safe_path(root, name).read_bytes() != expected:
            raise RuntimeError("Arquivo mudou durante a atualização: " + name)
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def validate(root):
    python = root / "VENV/Scripts/python.exe"
    subprocess.run([str(python), "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                    "test_inference_supervisor.py"], cwd=root / "BRAIN", check=True, timeout=180)
    with tempfile.TemporaryDirectory(prefix="brainnet-build-") as out:
        subprocess.run(["npm.cmd", "run", "build", "--", "--outDir", out],
                       cwd=root / PROJECT, check=True, timeout=300)


def install(root, commit, prepare, check=validate):
    state = safe_path(root, ".git/brainnet-updates")
    state.mkdir(exist_ok=True)
    lock = safe_path(root, ".git/brainnet-updates/apply.lock")
    with lock.open("x", encoding="utf-8") as stream:
        stream.write(commit)
    try:
        changes = prepare()
        if any(row[0] == "CONFLICT" for row in changes.values()):
            raise RuntimeError("CONFLICT: nenhuma alteração aplicada")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        run = state / (stamp + "-" + uuid4().hex)
        run.mkdir()
        journal = {"utc": stamp, "commit": commit, "status": "PREPARED", "files": {}}
        manifest = run / "result.json"
        def record():
            draft = run / "result.tmp"
            draft.write_text(json.dumps(journal, ensure_ascii=True, indent=2), encoding="utf-8")
            os.replace(draft, manifest)
        for name, (status, old, new) in changes.items():
            journal["files"][name] = {"status": status, "before_sha256": sha(old), "after_sha256": sha(new)}
            if status == "UPDATE":
                backup = run / name
                backup.parent.mkdir(parents=True, exist_ok=True)
                backup.write_bytes(old)
                if sha(backup.read_bytes()) != sha(old):
                    raise RuntimeError("Backup divergente")
        record()
        written = []
        try:
            for name, (status, old, new) in changes.items():
                if status == "UPDATE":
                    replace_if_unchanged(root, name, old, new)
                    written.append(name)
            check(root)
            for name, (status, old, new) in changes.items():
                expected = new if status == "UPDATE" else old
                if safe_path(root, name).read_bytes() != expected:
                    raise RuntimeError("Verificação pós-teste divergente: " + name)
            journal["status"] = "VERIFIED"
            record()
        except BaseException:
            conflicts = []
            for name in reversed(written):
                _, old, new = changes[name]
                try:
                    replace_if_unchanged(root, name, new, old)
                    if safe_path(root, name).read_bytes() != old:
                        raise RuntimeError("Restauração divergente")
                except (OSError, RuntimeError, ValueError):
                    conflicts.append(name)
            journal.update(status="ROLLBACK_CONFLICT" if conflicts else "ROLLED_BACK", conflicts=conflicts)
            record()
            raise
        return journal
    finally:
        lock.unlink()


def sync(*, cached=False, apply=None):
    if Path(os.fsdecode(git("rev-parse", "--show-toplevel").strip())).resolve() != ROOT:
        raise ValueError("Raiz Git incompatível")
    if cached and apply:
        raise ValueError("Cache permitido apenas para prévia")
    if not cached:
        git("fetch", "--no-tags", REMOTE, f"{BRANCH}:{REF}")
    commit = git("rev-parse", "--verify", REF + "^{commit}").decode().strip()
    if apply is not None and apply != commit:
        raise ValueError("Commit autorizado diverge da ponta atual; refaça a prévia")
    legacy_hash = sha(git_blob(commit, PATCH))
    print(f"updates/local {commit} | SHA-256 de {PATCH}: {legacy_hash}")
    if not git("ls-tree", "--name-only", commit, "--", MANIFEST).strip():
        if apply:
            raise ValueError("Instalador legado sem manifesto revisável; aplicação bloqueada")
        print("LEGACY_PREVIEW: instalador somente identificado, sem execução")
        return
    release = json.loads(git_blob(commit, MANIFEST))
    if release.get("current_py_sha256") != legacy_hash:
        raise ValueError("Manifesto incompatível com updates/current.py")
    def prepare():
        return plan(ROOT, release, lambda name: git_blob(commit, name))
    if apply:
        print(install(ROOT, commit, prepare)["status"])
    else:
        preview = prepare()
        for name, (status, _, _) in preview.items():
            print(status, name)
        if any(row[0] == "CONFLICT" for row in preview.values()):
            raise ValueError("CONFLICT: preserve as diferenças locais")
        print("Prévia concluída. Para aplicar o commit revisado: --apply", commit)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cached", action="store_true", help="Prévia da última versão obtida")
    parser.add_argument("--apply", metavar="COMMIT", help="Validar e aplicar somente este SHA completo")
    args = parser.parse_args()
    try:
        sync(cached=args.cached, apply=args.apply)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print("[SYNC ERROR]", exc, file=sys.stderr)
        sys.exit(1)
