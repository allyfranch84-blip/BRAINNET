import json
import logging
from pathlib import Path
import sqlite3
import subprocess
import shutil
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from BRAINNET import BrainnetBridge
from test_semantic_concepts import semantic_bridge


@pytest.mark.parametrize("method,target", [
    ("get_world_model_status", "BRAINNET.world_model_status"),
    ("get_diagnostics", "operations_status.diagnostics"),
    ("get_usage_report", "operations_status.usage_report"),
])
@pytest.mark.parametrize("broken", [None, sqlite3.OperationalError("schema temporarily unavailable")])
def test_bridge_always_returns_and_logs_serializable_empty_snapshot(semantic_bridge, caplog, method, target, broken):
    kwargs = {"side_effect": broken} if isinstance(broken, Exception) else {"return_value": broken}
    with patch(target, **kwargs), caplog.at_level(logging.DEBUG):
        result = getattr(semantic_bridge, method)()
    assert result["available"] is False and result["errors"]
    json.dumps(result, allow_nan=False)
    messages = [r.getMessage() for r in caplog.records if r.getMessage().startswith(f"[TELEMETRY:{method}] ")]
    assert json.loads(messages[-1].split("] ", 1)[1]) == result


def test_legacy_transition_schema_remains_readable_without_latency_or_source(tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE transitions (id INTEGER PRIMARY KEY, lambda_obs INTEGER)")
        conn.executemany("INSERT INTO transitions (lambda_obs) VALUES (?)", [(1,), (0,), (-1,)])
    bridge = object.__new__(BrainnetBridge)
    bridge._kernel = SimpleNamespace(pdag=SimpleNamespace(db_path=str(path)))
    result = bridge.get_usage_report()
    assert result["available"] is True
    assert result["total_executions"] == 2 and result["success_rate"] == 50
    assert result["average_latency_ms"] is None and result["latency_samples"] == 0


def test_missing_database_is_not_created_and_not_reported_as_zero(tmp_path):
    path = tmp_path / "does-not-exist.db"
    bridge = object.__new__(BrainnetBridge)
    bridge._kernel = SimpleNamespace(pdag=SimpleNamespace(db_path=str(path)))
    result = bridge.get_usage_report()
    assert not path.exists()
    assert result["available"] is False and result["total_executions"] is None


def test_frontend_polling_recovers_from_null_and_rejects_stale_responses():
    root = Path(__file__).resolve().parents[1]
    ui = root / "INTERFACE DE USUARIO" / "BRAINDET IU" / "project"
    node_exe = shutil.which("node") or str(root / "node.exe")
    result = subprocess.run([node_exe, str(Path(__file__).parent / "test_data" / "telemetry_recovery_test.cjs"), str(ui)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Telemetry recovery OK" in result.stdout
