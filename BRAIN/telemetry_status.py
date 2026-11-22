"""Read-only UI telemetry; never instantiates or runs a policy/world model."""
import json
import math
from numbers import Real
import os
from pathlib import Path
import sqlite3
import tempfile
import time


def _finite_number(value, minimum=0.0, maximum=None):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        return None
    value = float(value)
    return value if value >= minimum and (maximum is None or value <= maximum) else None


def metacognition_status(engine, intent=""):
    report = engine.obter_calibracao(intent) if intent else engine.obter_status()
    scope = "intent" if intent else "global"
    if intent and report["tentativas"] == 0:
        report, scope = engine.obter_status(), "global"
    samples = int(report["tentativas"])
    error = float(report["erro_calibracao"]) if samples else None
    state = "UNCERTAIN" if error is None or error > 0.15 else "OVERCONFIDENT" if error < -0.15 else "ALIGNED"
    return {"available": True, "state": state, "calibration_error": error,
            "samples": samples, "hit_rate": report["taxa_acerto"] if samples else None,
            "claimed_confidence": report["confianca_media"] if samples else None,
            "scope": scope, "intent": intent if scope == "intent" else None,
            "updated_at": time.time()}


def world_model_status(kernel):
    result = {"available": True, "mse": None, "policy_confidence": None, "transitions": None,
              "world_model_state": "standby", "policy_state": "standby", "trained_steps": None,
              "trained_at": None, "updated_at": time.time(), "errors": []}
    try:
        path = Path(kernel.pdag.db_path).resolve()
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.2) as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(transitions)")}
            observed = " WHERE source = 'observed'" if "source" in columns else ""
            result["transitions"] = conn.execute("SELECT COUNT(*) FROM transitions"+observed).fetchone()[0]
    except (sqlite3.Error, OSError, TypeError, AttributeError):
        result["errors"].append("Contagem de transicoes indisponivel")
    raw_path = getattr(kernel, "world_model_status_path", None)
    status_path = Path(raw_path) if isinstance(raw_path, (str, os.PathLike)) else Path(__file__).with_name("world_model_status.json")
    try:
        if status_path.exists():
            if status_path.stat().st_size > 65536:
                raise ValueError("Arquivo de telemetria excede 64 KiB")
            saved = json.loads(status_path.read_text(encoding="utf-8"))
            if not isinstance(saved, dict):
                raise ValueError("Telemetria deve ser um objeto")
            result["mse"] = _finite_number(saved.get("mse"))
            steps = saved.get("trained_steps")
            result["trained_steps"] = steps if isinstance(steps, int) and not isinstance(steps, bool) and steps > 0 else None
            result["trained_at"] = _finite_number(saved.get("updated_at"))
            if result["mse"] is None:
                raise ValueError("MSE invalido")
    except (OSError, ValueError):
        result["errors"].append("Metrica persistida do World Model indisponivel")
    model = getattr(kernel, "world_model", None)
    live_mse = _finite_number(getattr(model, "last_mse", None))
    if live_mse is not None:
        result["mse"] = live_mse
        steps = getattr(model, "steps", None)
        if isinstance(steps, int) and steps > 0:
            result["trained_steps"] = steps
    policy_result = getattr(kernel, "last_policy_result", None)
    if isinstance(policy_result, dict):
        result["policy_confidence"] = _finite_number(policy_result.get("confidence"), maximum=1.0)
    if result["mse"] is not None:
        result["world_model_state"] = "trained"
    if result["policy_confidence"] is not None:
        result["policy_state"] = "observed"
    return result


def write_training_status(path, mse, steps):
    """Optional training telemetry sink; isolated from network weights/gradients."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump({"mse": float(mse), "trained_steps": int(steps), "updated_at": time.time(),
                       "metric_kind": "training_mse_before_update"}, handle, allow_nan=False)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
