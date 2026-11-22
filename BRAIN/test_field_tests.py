"""Only simulated dependencies. Never open apps, type, or call Windows UIA."""
import asyncio
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from BRAINNET import BrainnetBridge
from execution_authority import background_only
from field_tests import TEXT, run_field_tests
from pdag_engine import MyelinatedPDAGEngine


@pytest.fixture
def simulation(tmp_path):
    pdag = MyelinatedPDAGEngine(str(tmp_path / "field.db"), dim=16, max_nodes=4)
    engine = SimpleNamespace(pdag=pdag)
    feedback = {"lambda_obs": 1, "ncd_real": .15, "expected_delta": .02, "failure_reason": ""}
    async def subgoal(intent_hash, action_fn, **kwargs):
        try:
            await action_fn()
        except Exception as ex:
            return {**feedback, "lambda_obs": 0, "failure_reason": str(ex)}
        return dict(feedback)
    engine.execute_subgoal = AsyncMock(side_effect=subgoal)
    engine._contract_for_action = MagicMock(return_value={"action": "START_MENU_SEARCH", "expects_new_pid": False})
    engine._start_menu_search = AsyncMock(return_value={"target_hwnd": 101})
    engine.resolver = SimpleNamespace(find_and_focus_window=MagicMock(return_value=101), _open_via_start_menu=MagicMock(return_value=True))
    engine.bridge = SimpleNamespace(_input_lock=asyncio.Lock(), dispatch=AsyncMock(return_value=SimpleNamespace(status="completed", result=True)))
    engine.execute_professor_step = AsyncMock(return_value=dict(feedback))
    async def wait_step(step):
        await asyncio.sleep(step["seconds"])
        return True
    engine._executar_passo_individual = AsyncMock(side_effect=wait_step)
    engine.verifier = MagicMock()
    engine.verifier.capture_state_bytes.return_value = b"screen"
    engine.verifier.snapshot_pids.return_value = {1}
    engine.verifier.measure_collapse.return_value = (1, .2, "", 1, .0, .0)
    engine.ctx_engine = MagicMock()
    engine.ctx_engine.capture_foreground_context.return_value = {"hwnd": 101, "pid": 1, "process_name": "calc.exe"}
    kernel = SimpleNamespace(pdag=pdag, trajectory_engine=engine, loop=None)
    original_sleep = asyncio.sleep
    async def simulated_sleep(seconds):
        await original_sleep(0 if seconds in (0.8, 1.0, 1.5, 3.0) else seconds)
    generic = {"pipeline": {"passos": [{"acao": "HOTKEY", "keys": ["win"]}, {"acao": "TYPE", "text": "calc"}, {"acao": "HOTKEY", "keys": ["enter"]}]}, "bindings": {"APP_ALVO": "calc"}}
    with patch("field_tests._app_evidence", return_value={"detected": True, "hwnd": 101, "pid": 1, "process_name": "notepad.exe"}) as window, \
         patch("field_tests._window_evidence", return_value={"detected": True, "hwnd": 102, "pid": 2, "process_name": "calculatorapp.exe"}), \
         patch("field_tests.asyncio.sleep", side_effect=simulated_sleep), \
         patch("field_tests._process_evidence", return_value={"detected": True, "pid": 1, "process_name": "notepad.exe"}), \
         patch("field_tests._read_notepad_text", side_effect=lambda hwnd, expected=TEXT: "" if expected is None else TEXT) as reader, \
         patch("concept_cortex.ConceptCortex.instantiate_generic_opening", return_value=generic) as route:
        yield kernel, engine, window, reader, route
    pdag.close()


def saved(kernel):
    with sqlite3.connect(kernel.pdag.db_path) as conn:
        row = conn.execute("SELECT results_json,report_markdown FROM field_tests").fetchone()
    return json.loads(row[0]), row[1]


def test_four_scenarios_report_real_observed_values_and_persist(simulation):
    kernel, engine, _, _, _ = simulation
    result = asyncio.run(run_field_tests(kernel))
    rows, markdown = saved(kernel)
    assert len(rows) == 4 and all(row["status"] == "✅ PASSOU" for row in rows)
    assert [row["ncd"] for row in rows] == [.15, .15, .15, .0]
    assert all(row["elapsed_ms"] >= 0 for row in rows)
    assert "| Cenário | Esperado | Observado | NCD |" in markdown
    assert markdown in result["reply"] and result["field_test_id"] in result["reply"]
    assert rows[-1]["evidence"]["cancelled"] is True
    assert rows[-1]["evidence"]["revoked_write_blocked"] is True
    assert rows[-1]["evidence"]["completed"] is False
    payloads = [call.args for call in engine.bridge.dispatch.call_args_list]
    assert payloads == [("hotkey", {"keys": ["ctrl", "n"]}), ("send_text", {"text": TEXT})]


def test_calculator_uses_dedicated_sequence_without_generic_route(simulation):
    kernel, engine, _, _, route = simulation
    route.return_value = None
    asyncio.run(run_field_tests(kernel))
    rows, _ = saved(kernel)
    assert rows[2]["status"] == "✅ PASSOU"
    engine.resolver._open_via_start_menu.assert_called_once_with("calculadora")
    route.assert_not_called()
    engine.execute_professor_step.assert_not_awaited()


def test_ncd_does_not_prove_process_or_text(simulation):
    kernel, engine, window, _, _ = simulation
    window.return_value = {"detected": False, "hwnd": 0}
    with patch("field_tests._process_evidence", return_value={"detected": False}), \
         patch("field_tests._window_evidence", return_value={"detected": False, "hwnd": 0}):
        asyncio.run(run_field_tests(kernel))
    rows, _ = saved(kernel)
    assert rows[0]["status"] == "❌ FALHOU"
    assert rows[1]["status"] == "⚠️ INCONCLUSIVO"
    assert rows[2]["status"] == "❌ FALHOU"
    engine.bridge.dispatch.assert_not_awaited()


def test_delayed_uia_never_blocks_visual_process_verification(simulation):
    kernel, engine, _, reader, _ = simulation
    reader.side_effect = RuntimeError("Texto exato não pôde ser confirmado pela UIA")
    asyncio.run(run_field_tests(kernel))
    rows, _ = saved(kernel)
    assert rows[1]["status"] == "✅ PASSOU"
    reader.assert_not_called()
    assert any(call.args[0] == "send_text" for call in engine.bridge.dispatch.call_args_list)


def test_command_is_explicit_and_never_uses_llm(simulation):
    kernel, _, _, _, _ = simulation
    bridge = object.__new__(BrainnetBridge)
    bridge._kernel, bridge._professor_mode = kernel, None
    bridge._clear_pending_actions = MagicMock()
    bridge._tom = MagicMock()
    with patch("BRAINNET.urllib.request.urlopen", side_effect=AssertionError("LLM proibido")), \
         patch("field_tests.run_field_tests", new=AsyncMock(return_value={"reply": "relatório simulado", "logs": []})) as runner:
        result = bridge._executar_comando_interno("/teste_campo", "/teste_campo", "/teste_campo")
    assert result["reply"] == "relatório simulado"
    runner.assert_awaited_once()
    bridge._tom.evaluate_intent.assert_not_called()


def test_background_cannot_start_battery(simulation):
    kernel, engine, _, _, _ = simulation
    @background_only
    async def background():
        return await run_field_tests(kernel)
    with pytest.raises(PermissionError, match="background"):
        asyncio.run(background())
    engine.execute_subgoal.assert_not_awaited()
