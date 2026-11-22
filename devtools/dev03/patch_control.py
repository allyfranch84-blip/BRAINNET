"""DEV-03: reviewed Git patch deployment; no implicit apply or service control."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tempfile
import uuid

PROTECTED_NAMES = {'.git', '.gitattributes', '.gitignore', '.env', 'brainnet_config.json',
                   'distill_data_generator_72b.py', 'node_modules', 'development_logs',
                   'long_drafts', 'models', 'model', 'tools', 'vendor', '__pycache__',
                   '.venv', 'venv', 'env', '.vscode', 'knowledge', 'ollama_models',
                   'escrita', '01share', 'projetos', 'error_snapshots', 'temp_media',
                   'code_vault', 'dataset_seed.json', 'config.json', 'settings.json',
                   'credentials.json', 'secrets.json'}
PROTECTED_EXTENSIONS = {'.db', '.sqlite', '.sqlite3', '.gguf', '.ggml', '.safetensors',
                        '.bin', '.pkl', '.pickle', '.pt', '.pth', '.onnx', '.zim', '.exe',
                        '.dll', '.so', '.dylib', '.log', '.jsonl', '.pem', '.key', '.pfx',
                        '.p12', '.zip', '.7z', '.rar', '.npy', '.npz'}
ALLOWED_EXTENSIONS = {'.py', '.pyi', '.js', '.jsx', '.ts', '.tsx', '.css', '.html',
                      '.json', '.toml', '.yaml', '.yml', '.ini', '.cfg', '.md', '.txt',
                      '.bat', '.cmd', '.ps1', '.sh'}


class Refused(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(repo, *args):
    env = os.environ.copy()
    env['GIT_OPTIONAL_LOCKS'] = '0'
    p = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, env=env)
    if p.returncode:
        raise Refused('Git recusou operação de leitura: ' + ' '.join(args[:2]))
    return p.stdout


def safe_rel(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise Refused('Caminho inválido: use caminho relativo com barras /')
    raw = value.split('/')
    if any(not p or p in ('.', '..') or p.endswith((' ', '.')) for p in raw):
        raise Refused('Travessia ou caminho ambíguo recusado')
    p = PurePosixPath(value)
    if p.is_absolute() or any(part.casefold() in PROTECTED_NAMES or
                              part.casefold().startswith(('.env', '.pytest_', 'secret', 'credential', 'token', 'password'))
                              for part in p.parts):
        raise Refused('Conteúdo protegido: ' + value)
    if p.suffix.casefold() in PROTECTED_EXTENSIONS or p.suffix.casefold() not in ALLOWED_EXTENSIONS:
        raise Refused('Extensão não permitida: ' + value)
    return p


def no_links(root, relative):
    root = Path(root).absolute()
    ancestors = list(reversed(root.parents)) + [root]
    for current in ancestors + [root.joinpath(*relative.parts[:i]) for i in range(1, len(relative.parts) + 1)]:
        try:
            st = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(st.st_mode) or getattr(st, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400):
            raise Refused('Link ou junction recusado: ' + str(current))


def checked_path(root, rel, *, excluded=None):
    no_links(root, rel)
    root = Path(root).resolve(strict=True)
    if os.name == 'nt':
        parent = root
        for part in rel.parts:
            if parent.is_dir():
                matches = [child.name for child in parent.iterdir() if child.name.casefold() == part.casefold()]
                if len(matches) > 1 or (matches and matches[0] != part):
                    raise Refused('Diferença de caixa ou colisão no caminho: ' + rel.as_posix())
            parent = parent / part
    out = root.joinpath(*rel.parts)
    resolved = out.resolve(strict=False)
    if not resolved.is_relative_to(root) or (excluded and resolved.is_relative_to(Path(excluded).resolve())):
        raise Refused('Caminho fora da árvore permitida')
    return out


def blob(repo, commit, path):
    return git(repo, 'show', f'{commit}:{path}')


def plan(source, destination, manifest):
    no_links(source, PurePosixPath())
    no_links(destination, PurePosixPath())
    source = Path(source).resolve(strict=True)
    destination = Path(destination).resolve(strict=True)
    if source != (destination / 'BRAINNET').resolve():
        raise Refused('Fonte deve ser a cópia BRAINNET dentro do destino')
    git_root = Path(git(source, 'rev-parse', '--show-toplevel').decode('utf-8').strip()).resolve()
    if git_root != source:
        raise Refused('A fonte não é a raiz do repositório Git esperado')
    data = json.loads(Path(manifest).read_text(encoding='utf-8'))
    base, target = data['base_commit'], data['target_commit']
    if any(not isinstance(x, str) or len(x) != 40 or any(c not in '0123456789abcdef' for c in x) for x in (base, target)):
        raise Refused('Commits devem ser SHA-1 completos e minúsculos')
    if git(source, 'rev-parse', 'HEAD').decode().strip() != target:
        raise Refused('HEAD não corresponde ao commit aprovado')
    if git(source, 'status', '--porcelain=v1', '--untracked-files=all'):
        raise Refused('Cópia Git contém alterações ou arquivos não rastreados')
    git(source, 'merge-base', '--is-ancestor', base, target)
    changes = git(source, 'diff', '--name-status', '--no-renames', '-z', base, target).split(b'\0')
    change_map = {}
    for i in range(0, len(changes) - 1, 2):
        kind = changes[i].decode('ascii'); path = changes[i + 1].decode('utf-8')
        if kind not in ('A', 'M'):
            raise Refused('Exclusões e outros tipos de alteração não são suportados')
        change_map[path] = kind
    entries = data.get('files')
    if not isinstance(entries, list) or not entries:
        raise Refused('Manifesto vazio')
    seen = set(); result = []
    for entry in entries:
        rel = safe_rel(entry['path']); name = rel.as_posix(); key = name.casefold()
        if key in seen:
            raise Refused('Caminho duplicado ou colisão de caixa: ' + name)
        seen.add(key)
        if name not in change_map:
            raise Refused('Caminho não pertence à revisão aprovada: ' + name)
        src = checked_path(source, rel)
        dst = checked_path(destination, rel, excluded=source)
        if not src.is_file():
            raise Refused('Fonte ausente: ' + name)
        new_hash = sha(blob(source, target, name))
        old_hash = sha(blob(source, base, name)) if change_map[name] == 'M' else None
        if entry.get('after_sha256') != new_hash or entry.get('before_sha256') != old_hash:
            raise Refused('Manifesto não corresponde aos blobs Git: ' + name)
        if sha(src.read_bytes()) != new_hash:
            raise Refused('Fonte de trabalho não corresponde ao commit: ' + name)
        current = sha(dst.read_bytes()) if dst.is_file() else None
        if dst.exists() and not dst.is_file():
            raise Refused('Destino não é arquivo: ' + name)
        result.append({'path': name, 'change': change_map[name], 'current_sha256': current,
                       'before_sha256': old_hash, 'after_sha256': new_hash,
                       'conflict': current != old_hash})
    if set(change_map) != {e['path'] for e in result}:
        raise Refused('Manifesto deve listar exatamente os caminhos alterados pela revisão')
    result.sort(key=lambda x: x['path'])
    out = {'schema': 1, 'source': str(source), 'destination': str(destination), 'base_commit': base,
           'target_commit': target, 'file_count': len(result), 'files': result,
           'risks': ['Arquivos operacionais podem estar em uso; processos relevantes bloqueiam a aplicação.',
                     'A confirmação da prévia não substitui teste funcional supervisionado.']}
    out['plan_sha256'] = sha(json.dumps(out, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode())
    return out


def active_processes():
    if os.name != 'nt':
        raise Refused('Inspeção de processos só é suportada em Windows')
    query = ("Get-CimInstance Win32_Process -ErrorAction Stop | "
             "Where-Object { $_.ProcessId -ne " + str(os.getpid()) + " -and "
             "(($_.Name -match '^(ollama|ollama app|llama-server)\\.exe$') -or "
             "($_.Name -match '^(pythonw?|node)(\\.exe)?$' -and "
             "([string]::IsNullOrWhiteSpace($_.CommandLine) -or "
             "$_.CommandLine -match 'BRAINNET|self_inspector|vite|hotbar'))) } | "
             "Select-Object ProcessId,Name | ConvertTo-Json -Compress")
    p = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', query], capture_output=True, timeout=20)
    if p.returncode:
        raise Refused('Não foi possível confirmar ausência de processos relevantes')
    return p.stdout.decode('utf-8', errors='replace').strip()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.dev03-journal-', delete=False) as f:
        temp = Path(f.name)
        try:
            f.write(encoded); f.flush(); os.fsync(f.fileno())
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.dev03-', delete=False) as f:
        temp = Path(f.name)
        try:
            f.write(data); f.flush(); os.fsync(f.fileno())
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def apply_plan(p, approved_hash, backup_root, *, process_check=active_processes):
    if approved_hash != p['plan_sha256']:
        raise Refused('Hash da prévia aprovada não corresponde')
    if any(x['conflict'] for x in p['files']):
        raise Refused('Conflito detectado; nenhuma instalação iniciada')
    processes = process_check()
    if processes and processes not in ('[]', 'null'):
        raise Refused('Processos relevantes ativos: ' + processes)
    src, dest = Path(p['source']), Path(p['destination'])
    no_links(backup_root, PurePosixPath())
    backup_root = Path(backup_root).resolve(strict=False)
    if backup_root.is_relative_to(src):
        raise Refused('Backups não podem ficar na cópia versionada')
    dep = datetime.datetime.now().strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:12]
    folder = backup_root / dep; folder.mkdir(parents=True, exist_ok=False)
    journal = {'deployment_id': dep, 'plan': p, 'status': 'PREPARING', 'files': []}
    journal_path = folder / 'manifest.json'
    for e in p['files']:
        rel = safe_rel(e['path']); dst = checked_path(dest, rel, excluded=src)
        current = sha(dst.read_bytes()) if dst.is_file() else None
        if current != e['before_sha256']:
            raise Refused('Destino mudou antes do backup: ' + e['path'])
        if current is not None:
            backup = folder / 'backup' / Path(*rel.parts); backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(dst.read_bytes())
            if sha(backup.read_bytes()) != current:
                raise Refused('Falha de verificação do backup')
        journal['files'].append({**e, 'state': 'BACKED_UP'})
    journal['status'] = 'READY'; write_json(journal_path, journal)
    try:
        for e in journal['files']:
            rel = safe_rel(e['path']); dst = checked_path(dest, rel, excluded=src); source_file = checked_path(src, rel)
            current = sha(dst.read_bytes()) if dst.is_file() else None
            if current != e['before_sha256'] or sha(source_file.read_bytes()) != e['after_sha256']:
                raise Refused('Arquivo mudou após a prévia: ' + e['path'])
            e['state'] = 'INSTALLING'; write_json(journal_path, journal)
            atomic_write(dst, source_file.read_bytes())
            if sha(dst.read_bytes()) != e['after_sha256']:
                raise Refused('Hash após instalação não confere: ' + e['path'])
            e['state'] = 'INSTALLED'; write_json(journal_path, journal)
        journal['status'] = 'APPLIED'; write_json(journal_path, journal)
    except BaseException as exc:
        journal['status'] = 'PARTIAL_FAILURE'; journal['error'] = type(exc).__name__; write_json(journal_path, journal)
        raise Refused('Falha parcial; não houve rollback automático. Consulte ' + str(journal_path)) from exc
    return journal


def rollback(backup_root, deployment_id, *, expected_source=None, expected_destination=None, process_check=active_processes):
    if not deployment_id or any(c not in '0123456789abcdefT-' for c in deployment_id):
        raise Refused('Identificador inválido')
    no_links(backup_root, PurePosixPath())
    folder = Path(backup_root).resolve(strict=True) / deployment_id
    no_links(folder.parent, PurePosixPath(deployment_id))
    no_links(folder, PurePosixPath('manifest.json'))
    path = folder / 'manifest.json'; journal = json.loads(path.read_text(encoding='utf-8'))
    if journal['deployment_id'] != deployment_id or journal['status'] not in ('APPLIED', 'PARTIAL_FAILURE'):
        raise Refused('Estado não permite rollback')
    processes = process_check()
    if processes and processes not in ('[]', 'null'):
        raise Refused('Processos relevantes ativos: ' + processes)
    src, dest = Path(journal['plan']['source']), Path(journal['plan']['destination'])
    if ((expected_source is not None and src.resolve() != Path(expected_source).resolve()) or
            (expected_destination is not None and dest.resolve() != Path(expected_destination).resolve())):
        raise Refused('As raízes do manifesto de rollback não correspondem ao destino solicitado')
    no_links(src, PurePosixPath()); no_links(dest, PurePosixPath())
    affected = []
    for e in journal['files']:
        if e['state'] not in ('INSTALLING', 'INSTALLED'):
            continue
        rel = safe_rel(e['path']); dst = checked_path(dest, rel, excluded=src)
        current = sha(dst.read_bytes()) if dst.is_file() else None
        if current == e['before_sha256'] and e['state'] == 'INSTALLING':
            continue
        if current != e['after_sha256']:
            raise Refused('Rollback recusado: arquivo foi alterado depois: ' + e['path'])
        if e['before_sha256'] is not None:
            backup = folder / 'backup' / Path(*rel.parts)
            no_links(folder, PurePosixPath('backup') / rel)
            if not backup.is_file() or sha(backup.read_bytes()) != e['before_sha256']:
                raise Refused('Backup ausente ou alterado: ' + e['path'])
        affected.append((e, rel, dst))
    try:
        for e, rel, dst in reversed(affected):
            if (sha(dst.read_bytes()) if dst.is_file() else None) != e['after_sha256']:
                raise Refused('Destino mudou durante rollback: ' + e['path'])
            if e['before_sha256'] is None:
                dst.unlink()
            else:
                atomic_write(dst, (folder / 'backup' / Path(*rel.parts)).read_bytes())
                if sha(dst.read_bytes()) != e['before_sha256']:
                    raise Refused('Hash após rollback não confere')
            e['state'] = 'ROLLED_BACK'; write_json(path, journal)
        journal['status'] = 'ROLLED_BACK'; write_json(path, journal)
    except BaseException as exc:
        journal['status'] = 'ROLLBACK_PARTIAL_FAILURE'; write_json(path, journal)
        raise Refused('Rollback parcial: ' + str(path)) from exc
    return journal


def main():
    p = argparse.ArgumentParser(); p.add_argument('--source', required=True); p.add_argument('--destination', required=True)
    p.add_argument('--manifest'); p.add_argument('--backup-root', required=True); p.add_argument('--apply', action='store_true')
    p.add_argument('--plan-hash'); p.add_argument('--rollback'); args = p.parse_args()
    try:
        source = Path(args.source).resolve(strict=True)
        destination = Path(args.destination).resolve(strict=True)
        backup = Path(args.backup_root).resolve(strict=False)
        if source != (destination / 'BRAINNET').resolve():
            raise Refused('Fonte deve ser a cópia BRAINNET dentro do destino')
        real_destination = Path(r'A:\BRAINNET').resolve()
        temp_root = Path(tempfile.gettempdir()).resolve()
        if destination == real_destination:
            if backup != (destination / 'BRAIN' / 'development_logs' / 'deployments').resolve():
                raise Refused('Backups reais devem usar development_logs/deployments')
        elif not destination.is_relative_to(temp_root) or not backup.is_relative_to(temp_root):
            raise Refused('Somente destino operacional configurado ou árvores temporárias são permitidos')
        if args.rollback:
            print('ATENÇÃO: rollback altera arquivos operacionais; processos ativos impedem a operação.')
            if input('Digite ROLLBACK ' + args.rollback + ': ').strip() != 'ROLLBACK ' + args.rollback:
                raise Refused('Confirmação não fornecida')
            print(json.dumps(rollback(args.backup_root, args.rollback, expected_source=args.source,
                                      expected_destination=args.destination), ensure_ascii=False, indent=2)); return 0
        if not args.manifest:
            raise Refused('Informe manifesto explícito da revisão')
        result = plan(args.source, args.destination, args.manifest)
        result['planned_backup_root'] = str(Path(args.backup_root).absolute())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print('ATENÇÃO: o .bat principal pode encerrar processos Ollama e iniciar serviços; não será executado.')
        if args.apply:
            if args.plan_hash != result['plan_sha256']:
                raise Refused('Informe o hash exato da prévia aprovada')
            if input('Digite APLICAR ' + args.plan_hash + ': ').strip() != 'APLICAR ' + args.plan_hash:
                raise Refused('Confirmação não fornecida')
            print(json.dumps(apply_plan(result, args.plan_hash, args.backup_root), ensure_ascii=False, indent=2))
        return 0
    except (Refused, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print('BLOQUEADO:', str(exc), file=sys.stderr); return 2


if __name__ == '__main__':
    sys.exit(main())
