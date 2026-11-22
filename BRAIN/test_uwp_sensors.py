import asyncio
from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import psutil
import pytest

from cybernetic_verifier import CyberneticVerifier
from field_tests import _app_evidence, run_field_tests
from system_intent import find_app_process
from test_field_tests import simulation, saved


@contextmanager
def hosted(child_name):
    host = MagicMock(info={"pid": 100, "name": "ApplicationFrameHost.exe"})
    host.status.return_value = psutil.STATUS_RUNNING
    def process(pid):
        item = MagicMock()
        item.name.return_value = "ApplicationFrameHost.exe" if pid == 100 else child_name
        return item
    with ExitStack() as stack:
        stack.enter_context(patch("psutil.process_iter", return_value=[host]))
        stack.enter_context(patch("psutil.pid_exists", return_value=True))
        stack.enter_context(patch("psutil.Process", side_effect=process))
        stack.enter_context(patch("win32process.GetWindowThreadProcessId", side_effect=lambda hwnd: (1, 100 if hwnd == 50 else 200)))
        stack.enter_context(patch("win32gui.IsWindow", return_value=True))
        stack.enter_context(patch("win32gui.IsWindowVisible", return_value=True))
        stack.enter_context(patch("win32gui.IsIconic", return_value=False))
        stack.enter_context(patch("win32gui.GetForegroundWindow", return_value=50))
        stack.enter_context(patch("win32gui.GetWindowText", return_value="Título sem nome do aplicativo"))
        stack.enter_context(patch("win32gui.EnumWindows", side_effect=lambda callback, data: callback(50, data)))
        stack.enter_context(patch("win32gui.EnumChildWindows", side_effect=lambda hwnd, callback, data: callback(51, data)))
        yield


@pytest.mark.parametrize("app,child_name", [("calc", "CalculatorApp.exe"), ("calc", "calc.exe"), ("notepad", "Notepad.exe")])
def test_uwp_host_binds_child_process_without_requiring_window_title(app, child_name):
    with hosted(child_name):
        process = find_app_process(app)
        assert process["pid"] == 100 and process["app_pid"] == 200
        assert _app_evidence(app)["detected"] is True


def test_unrelated_frame_host_is_not_notepad_or_calculator():
    with hosted("Photos.exe"):
        assert find_app_process("notepad") is None
        assert find_app_process("calc") is None
        assert _app_evidence("notepad")["detected"] is False


@pytest.mark.parametrize("ncd,alive,success", [(0., True, 0), (.05, True, 0), (.0501, True, 1), (1.0, True, 1), (.9, False, 0)])
def test_type_requires_ncd_above_point_zero_five_and_live_target(ncd, alive, success):
    verifier = CyberneticVerifier(capture_fn=lambda: b"after", poll_interval=.001)
    with patch.object(CyberneticVerifier, "snapshot_pids", return_value={100}), \
         patch.object(CyberneticVerifier, "calculate_ncd_lz4", return_value=ncd), \
         patch.object(CyberneticVerifier, "_check_hwnd_liveness", return_value=(False, "")), \
         patch("cybernetic_verifier.user32"), \
         patch("system_intent.find_app_process", return_value={"pid": 100} if alive else None):
        result = verifier.measure_collapse({100}, b"before", b"", timeout_sec=.002,
            contract={"action": "TYPE", "app": "notepad", "expects_new_pid": False, "target_hwnd": 50})
    assert result[0] == success and result[4] == ncd


@pytest.mark.parametrize("title,visible,found", [("Calculadora", True, True), ("Calculator", True, True), ("Fotos", True, False), ("Calculator", False, False)])
def test_calculator_title_fallback(title, visible, found):
    from system_intent import find_app_window_by_title
    with patch("win32gui.EnumWindows", side_effect=lambda callback, data: callback(50, data)), \
         patch("win32gui.IsWindowVisible", return_value=visible), \
         patch("win32gui.GetWindowText", return_value=title), \
         patch("win32process.GetWindowThreadProcessId", return_value=(1, 200)):
        assert bool(find_app_window_by_title("calc")) is found
        assert find_app_window_by_title("notepad") is None


@pytest.mark.parametrize("ncd,passed", [(.9998, True), (.90, False)])
def test_field_calculator_visual_fallback_without_process_or_window(simulation, ncd, passed):
    kernel, engine, _, _, _ = simulation
    async def execute(intent_hash, action_fn, **kwargs):
        await action_fn()
        return {"lambda_obs": 0, "ncd_real": ncd, "failure_reason": "process missing"}
    engine.execute_subgoal = AsyncMock(side_effect=execute)
    with patch("field_tests._window_evidence", return_value={"detected": False, "hwnd": 0}), \
         patch("field_tests._process_evidence", return_value={"detected": False}):
        asyncio.run(run_field_tests(kernel))
    rows, _ = saved(kernel)
    assert (rows[2]["status"] == "✅ PASSOU") is passed


def test_field_calculator_passes_with_process_and_ncd_one_without_title(simulation):
    kernel, engine, _, reader, _ = simulation
    async def execute(intent_hash, action_fn, **kwargs):
        await action_fn()
        return {"lambda_obs": 1, "ncd_real": 1.0, "expected_delta": .05, "failure_reason": ""}
    engine.execute_subgoal = AsyncMock(side_effect=execute)
    with patch("field_tests._window_evidence", return_value={"detected": False, "hwnd": 0}):
        asyncio.run(run_field_tests(kernel))
    rows, _ = saved(kernel)
    assert rows[2]["status"] == "✅ PASSOU" and rows[2]["ncd"] == 1.0
    assert rows[1]["status"] == "✅ PASSOU"
    reader.assert_not_called()
    engine.resolver.find_and_focus_window.assert_called_once_with("notepad")
