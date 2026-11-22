"""Explicit /autoteste: pytest, one guarded repair attempt, then revalidation."""
import itertools
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
from owned_processes import run_owned

logger = logging.getLogger("BRAINNET_Autotest")
BRAIN_DIR = Path(__file__).resolve().parent


def _local_evidence(output):
    excerpts, seen = [], set()
    for filename, number in re.findall(r"(?m)^\s*(.+?\.py):(\d+)(?::\d+)?:", output):
        path = (BRAIN_DIR / filename.strip()).resolve()
        if (not path.is_relative_to(BRAIN_DIR) or path in seen or not path.is_file()
                or path.name.startswith("test_") or path.name == "conftest.py"):
            continue
        seen.add(path)
        line = int(number)
        start = max(0, line - 9)
        with path.open(encoding="utf-8-sig", errors="replace") as source:
            content = "".join(itertools.islice(source, start, line + 8))[:2400]
        excerpts.append({"file": str(path.relative_to(BRAIN_DIR)), "line_start": start+1, "content": content})
        if len(excerpts) == 4:
            break
    return excerpts


def run_autotest(blackbox):
    if os.environ.get("BRAINNET_AUTOTEST_RUNNING") == "1" or os.environ.get("BRAINNET_AUTOCURA_VALIDATING") == "1":
        return {"reply": "Autoteste já está em validação; execução recursiva bloqueada.", "logs": []}
    env = os.environ.copy()
    env.update(BRAINNET_AUTOTEST_RUNNING="1", PYTHONIOENCODING="utf-8")
    command = [sys.executable, "-m", "pytest", "-q", "--tb=short"]
    logs = []

    def run_tests():
        result = run_owned(command, cwd=str(BRAIN_DIR), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180, check=False, env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        logs.append({"level": "INFO" if result.returncode == 0 else "ERROR", "core": "Autoteste",
                     "msg": (result.stdout + "\n" + result.stderr).strip()[-2000:]})
        logger.info("[PYTEST returncode=%s]\n%s\n%s", result.returncode, result.stdout, result.stderr)
        return result

    try:
        first = run_tests()
        if first.returncode == 0:
            return {"reply": "✅ Todos os testes passaram. O sistema está saudável.", "logs": logs}
        if first.returncode < 0:
            return {"reply": f"❌ Pytest interrompido (código {first.returncode}); nenhum reparo foi iniciado.", "logs": logs}
        output = first.stdout + "\n" + first.stderr
        snapshot = {"snapshot_id": f"AUTOTEST_{uuid.uuid4().hex}", "timestamp": time.time(),
            "intencao_original": "/autoteste", "acao_executada": {"tipo": "PYTEST", "command": command},
            "estado_esperado": {"returncode": 0}, "estado_observado": {"returncode": first.returncode,
                "stdout": first.stdout[-2000:], "stderr": first.stderr[-2000:]},
            "traceback": output[-2000:], "motivo_punicao": "PYTEST_FAILED",
            "trechos_locais": _local_evidence(output)}
        blackbox.buffer_circular.append(snapshot)
        try:
            repair = blackbox.disparar_auto_cura(snapshot)
            if not isinstance(repair, dict):
                raise ValueError("Resposta da auto-cura inválida")
        except Exception as ex:
            logger.exception("Auto-cura falhou")
            repair = {"status": "ERRO_AUTO_CURA", "detalhe": str(ex)}
        status = repair.get("status", "SEM_STATUS")
        logs.append({"level": "INFO" if status == "PATCH_APLICADO_TESTES_OK" else "WARN",
                     "core": "AutoCura", "msg": f"{status}: {repair.get('causa_raiz', repair.get('detalhe', ''))}"})
        second = run_tests()
        if second.returncode == 0:
            if status == "PATCH_APLICADO_TESTES_OK":
                return {"reply": "🛠️ Código corrigido autonomamente pelo Qwen-Coder 7B. Testes verdes.", "logs": logs}
            return {"reply": f"✅ Testes verdes na revalidação. A auto-cura retornou {status}; nenhum reparo foi confirmado.", "logs": logs}
        return {"reply": f"❌ Os testes continuam falhando após uma tentativa de auto-cura ({status}). Consulte os logs.", "logs": logs}
    except subprocess.TimeoutExpired:
        logger.exception("Pytest excedeu o limite de tempo")
        return {"reply": "❌ Pytest excedeu o limite de 180 segundos. O autoteste foi interrompido.", "logs": logs}
    except Exception as ex:
        logger.exception("Autoteste não concluído")
        return {"reply": f"❌ Autoteste não concluído: {type(ex).__name__}: {ex}", "logs": logs}
