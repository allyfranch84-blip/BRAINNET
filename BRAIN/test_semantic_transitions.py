import asyncio
import json
import sqlite3
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from causal_trajectory import CausalTrajectoryEngine
from extract_heuristics import compilar_tudo
from pdag_engine import MyelinatedPDAGEngine


PIPELINE = [{"acao": "HOTKEY", "keys": ["win"]}, {"acao": "TYPE", "text": "calc"},
            {"acao": "HOTKEY", "keys": ["enter"]}]


@pytest.fixture
def pdag(tmp_path):
    engine = MyelinatedPDAGEngine(str(tmp_path / "semantic.db"), dim=16, max_nodes=4)
    yield engine
    engine.close()


def test_legacy_schema_migration_is_idempotent_and_preserves_rows(tmp_path):
    path = str(tmp_path / "legacy.db")
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE transitions(id INTEGER PRIMARY KEY, state_before_hash TEXT NOT NULL, action_hash TEXT NOT NULL, state_after_hash TEXT NOT NULL, lambda_obs INTEGER NOT NULL, ncd REAL NOT NULL, app_name TEXT NOT NULL, timestamp REAL NOT NULL)")
        conn.execute("INSERT INTO transitions VALUES (1,'before','action','after',1,.3,'old.exe',1)")
    for _ in range(2):
        engine = MyelinatedPDAGEngine(path, dim=16, max_nodes=4)
        engine.close()
    with sqlite3.connect(path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(transitions)")}
        assert {"execution_id", "intent", "steps_json", "expected_delta", "actual_delta", "trajectory_id", "step_index", "step_count"} <= columns
        assert conn.execute("SELECT action_hash,ncd,actual_delta,source FROM transitions").fetchall() == [("action", .3, None, "observed")]


@pytest.mark.parametrize("action,step", [("TYPE", PIPELINE[1]), ("HOTKEY", PIPELINE[0]),
                                        ("WAIT", {"acao": "WAIT", "seconds": .1}),
                                        ("SCROLL", {"acao": "SCROLL", "direction": "down", "clicks": 1})])
def test_execute_subgoal_persists_exact_step_and_verifier_result(pdag, action, step):
    engine = object.__new__(CausalTrajectoryEngine)
    engine.ctx_engine = MagicMock()
    engine.ctx_engine.capture_foreground_context.return_value = {"process_name": "calc.exe", "title": "Calculadora", "hwnd": 77, "pid": 20}
    engine.verifier = MagicMock(ncd_threshold=.2)
    engine.verifier.snapshot_pids.return_value = {20}
    engine.verifier.capture_state_bytes.return_value = b"screen"
    engine.verifier.measure_collapse.return_value = (1, 1., "", 20, .37, .12)
    engine.pdag = pdag
    result = asyncio.run(engine.execute_subgoal("hashed", AsyncMock(return_value=True),
        contract=engine._contract_for_action(action), intent="abrir a calculadora", step=step, expected_ncd=.12))
    assert pdag.flush_pending_writes(5)
    with sqlite3.connect(pdag.db_path) as conn:
        row = conn.execute("SELECT execution_id,intent,app_name,steps_json,expected_delta,actual_delta,lambda_obs,window_title FROM transitions").fetchone()
    uuid.UUID(row[0])
    assert row[0] == result["execution_id"]
    assert row[1:3] == ("abrir a calculadora", "calc.exe")
    assert json.loads(row[3]) == {"passos": [step], "executed_step": step}
    assert row[4:] == (.12, .37, 1, "Calculadora")


def test_action_exception_is_failure_without_fabricating_ncd(pdag):
    engine = object.__new__(CausalTrajectoryEngine)
    engine.ctx_engine = MagicMock()
    engine.ctx_engine.capture_foreground_context.return_value = {"process_name": "calc.exe", "hwnd": 77}
    engine.verifier = MagicMock(ncd_threshold=.2)
    engine.verifier.snapshot_pids.return_value = {20}
    engine.verifier.capture_state_bytes.return_value = b"screen"
    engine.pdag = pdag
    result = asyncio.run(engine.execute_subgoal("hash", AsyncMock(side_effect=RuntimeError("atuador falhou")),
        contract=engine._contract_for_action("TYPE"), step=PIPELINE[1]))
    assert result["lambda_obs"] == 0
    assert pdag.flush_pending_writes(5)
    with sqlite3.connect(pdag.db_path) as conn:
        assert conn.execute("SELECT lambda_obs,actual_delta,ncd FROM transitions").fetchone() == (0, None, -1.)
    engine.verifier.measure_collapse.assert_not_called()


@pytest.mark.parametrize("failed,partial,expected", [(0, False, 1), (1, False, 0), (0, True, 0)])
def test_compiler_uses_complete_correlated_semantic_executions(pdag, tmp_path, failed, partial, expected):
    for attempt in range(10):
        trace = str(uuid.uuid4())
        for index, step in enumerate(PIPELINE[:2] if partial else PIPELINE):
            hit = int(not (attempt < failed and index == 2))
            pdag.record_transition("before", "action", "after", hit, .3, "calc.exe",
                execution_id=str(uuid.uuid4()), intent="abrir calculadora",
                steps_json=json.dumps({"passos": PIPELINE, "executed_step": step}), expected_delta=.2,
                trajectory_id=trace, step_index=index, step_count=3)
    assert pdag.flush_pending_writes(5)
    result = compilar_tudo(pdag.db_path, tmp_path / "HABILIDADES")
    assert result["sucessos"] == expected
    if expected:
        from pathlib import Path
        source = Path(result["arquivos"][0]).read_text(encoding="utf-8")
        assert "effector.send_hotkey, ['win']" in source and "effector.send_text, 'calc'" in source
