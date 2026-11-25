"""Explicit, bounded smoke test of FAST and DEEP on a test-owned local Ollama."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import psutil
from inference_supervisor import InferenceSupervisor


def probe(work):
    exe = shutil.which("ollama.exe")
    store = Path("A:/OLLAMA_MODELS")
    model = "qwen2.5:1.5b"
    s = InferenceSupervisor()
    if s.kind != "ollama" or not exe or not (store / "manifests/registry.ollama.ai/library/qwen2.5/1.5b").is_file():
        return {"status": "BLOCKED", "reason": "Pré-requisitos locais ausentes"}
    if not s._port_free():
        return {"status": "BLOCKED", "reason": "Porta 11435 ocupada antes do ensaio"}
    child_env = dict(os.environ, USERPROFILE=str(work), HOME=str(work), OLLAMA_HOST="127.0.0.1:11435",
                     OLLAMA_MODELS=str(store), OLLAMA_NOPRUNE="1", OLLAMA_NO_CLOUD="1",
                     OLLAMA_VULKAN="1", OLLAMA_NUM_PARALLEL="1", OLLAMA_MAX_LOADED_MODELS="1")
    result = {"model": model, "modes": {}, "status": "FAIL"}
    log = work / "server.log"
    with log.open("wb") as output:
        s.proc = subprocess.Popen([exe, "serve"], env=child_env, cwd=work, stdout=output,
                                  stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    proc = s.proc
    try:
        deadline = time.monotonic() + 30
        while proc.poll() is None and time.monotonic() < deadline:
            if any(c.pid == proc.pid and c.status == "LISTEN" and c.laddr == ("127.0.0.1", 11435)
                   for c in psutil.net_connections(kind="tcp")):
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("PID proprietário da porta não confirmado")
        # A listening socket can precede API readiness during Vulkan discovery.
        while True:
            try:
                version, names = s._ollama_catalog()
                break
            except OSError:
                if time.monotonic() >= deadline or proc.poll() is not None:
                    raise
                time.sleep(0.5)
        result.update(version=version, catalog_count=len(names))
        if model not in names:
            raise RuntimeError("Modelo ausente no catálogo oficial")
        os.environ.update(LOCALAPPDATA=str(work), BRAINNET_MINIMAL="1", BRAINNET_MOTOR_SEMANTIC="1",
                          BRAINNET_MANAGE_INFERENCE="0", OLLAMA_HOST="127.0.0.1:11435",
                          BRAINNET_P4_DIRECT_MOVE="0", BRAINNET_PERSIST_EXPERIENCES="0")
        import BRAINNET as app
        app.CONFIG_FILE = work / "settings.json"
        bridge = app.BrainnetBridge(app.BrainnetKernel())
        for mode in ("FAST", "DEEP"):
            if not bridge.set_effort_mode(mode)["ok"]:
                raise RuntimeError("Falha ao configurar o modo no perfil descartável")
            start = time.perf_counter()
            reply = bridge.send_command("Quanto é dois mais dois? Responda somente com o algarismo.")
            budget = reply["task_budget"]
            result["modes"][mode] = {
                "status": reply["status"], "answer_to_fixture": reply["reply"][:160],
                "correct": reply["reply"].strip() == "4",
                "task_id": budget["task_id"], "token_usage": budget.get("token_usage"),
                "elapsed_ms": round((time.perf_counter() - start) * 1000, 2)}
        result["resident"] = [{k: row.get(k) for k in ("name", "size", "size_vram")}
                              for row in s._json("/api/ps")["models"]]
        if all(r["correct"] and r["status"] == "CONVERSATION" for r in result["modes"].values()):
            result["status"] = "PASS_REAL"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        children = psutil.Process(proc.pid).children(recursive=True) if proc.poll() is None else []
        s.stop()
        _, alive = psutil.wait_procs(children, timeout=5)
        result["shutdown"] = proc.poll() is not None and not alive
        if not result["shutdown"]:
            result["status"] = "INCONCLUSIVE"
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    result["vulkan_reported_by_runtime"] = any("library=vulkan" in line.casefold() for line in lines)
    return result


if __name__ == "__main__":
    if os.name != "nt" or sys.argv[1:] != ["--run"]:
        raise SystemExit("Uso explícito em Windows: probe_ollama_workspace.py --run")
    sys.argv[0] = str(Path(__file__).resolve())
    scratch = Path(__file__).resolve().parents[1] / ".pytest_runs"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch, prefix="ollama-") as folder:
        original = Path.cwd()
        try:
            os.chdir(folder)
            result = probe(Path(folder))
        finally:
            os.chdir(original)
    print(json.dumps(result), flush=True)
    raise SystemExit(0 if result["status"] == "PASS_REAL" else 1)
