import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import psutil
import pytest

from causal_trajectory import CausalTrajectoryEngine, WindowsAppResolver
from cybernetic_verifier import CyberneticVerifier
from field_tests import run_field_tests
from system_intent import find_app_process
from test_field_tests import simulation, saved


@pytest.mark.parametrize("action", ["OPEN_APP", "ENSURE_APP", "START_MENU_SEARCH"])
def test_opening_succeeds_for_matching_process_without_focus(action):
    verifier = CyberneticVerifier(capture_fn=lambda: b"after")
    with patch.object(CyberneticVerifier, "snapshot_pids", return_value={10}), \
         patch.object(CyberneticVerifier, "calculate_ncd_lz4", return_value=1.0001), \
         patch.object(CyberneticVerifier, "_check_hwnd_liveness", return_value=(False, "SEM_FOCO")), \
         patch("cybernetic_verifier.user32") as native, \
         patch("system_intent.find_app_process", return_value={"pid": 10, "process_name": "notepad.exe"}):
        native.GetForegroundWindow.return_value = 999
        result = verifier.measure_collapse({10}, b"before", b"", timeout_sec=.01,
            contract={"action": action, "app": "notepad", "expects_new_pid": False})
    assert result[0] == 1 and result[3] == 10 and result[4] == 1.0001


def test_wrong_foreground_process_is_not_opening_evidence():
    verifier = CyberneticVerifier(capture_fn=lambda: b"after")
    with patch.object(CyberneticVerifier, "snapshot_pids", return_value={99}), \
         patch.object(CyberneticVerifier, "calculate_ncd_lz4", return_value=1.0001), \
         patch.object(CyberneticVerifier, "_check_hwnd_liveness", return_value=(True, "")), \
         patch("cybernetic_verifier.user32"), patch("system_intent.find_app_process", return_value=None):
        result = verifier.measure_collapse({99}, b"before", b"", timeout_sec=.001,
            contract={"action": "ENSURE_APP", "app": "notepad", "expects_new_pid": False})
    assert result[0] == 0


def test_valid_target_window_is_accepted_only_with_matching_owner():
    verifier = CyberneticVerifier(capture_fn=lambda: b"after")
    def owner(hwnd, pointer):
        pointer._obj.value = 42
        return 1
    with patch.object(CyberneticVerifier, "snapshot_pids", return_value=set()), \
         patch.object(CyberneticVerifier, "calculate_ncd_lz4", return_value=0.0), \
         patch.object(CyberneticVerifier, "_check_hwnd_liveness", return_value=(False, "SEM_FOCO")), \
         patch("cybernetic_verifier.user32") as native, patch("system_intent.find_app_process", return_value=None), \
         patch("psutil.Process") as process:
        native.IsWindow.return_value = True
        native.GetWindowThreadProcessId.side_effect = owner
        process.return_value.name.return_value = "notepad.exe"
        result = verifier.measure_collapse(set(), b"before", b"", timeout_sec=.01,
            contract={"action": "ENSURE_APP", "app": "notepad", "target_hwnd": 77, "expects_new_pid": False})
    assert result[0] == 1 and result[3] == 42


@pytest.mark.parametrize("name,expected", [("notepad.exe", True), ("notepad++.exe", False), ("whatsapp.exe", False)])
def test_pid_existence_is_bound_to_exact_app_identity(name, expected):
    process = MagicMock(info={"pid": 10, "name": name})
    process.status.return_value = psutil.STATUS_RUNNING
    with patch("psutil.process_iter", return_value=[process]), patch("psutil.pid_exists", return_value=True):
        assert bool(find_app_process("notepad")) is expected


def test_focus_helper_uses_topmost_toggle_and_detaches_threads():
    with patch("causal_trajectory.user32") as native, patch("causal_trajectory.kernel32"):
        native.GetForegroundWindow.return_value = 77
        assert WindowsAppResolver.focus_window_handle(77)
        operations = [c for c in native.mock_calls if c[0] in ("ShowWindow", "SetWindowPos", "SetForegroundWindow")]
        assert operations == [call.ShowWindow(77, 9), call.SetWindowPos(77, -1, 0, 0, 0, 0, 3),
                              call.SetWindowPos(77, -2, 0, 0, 0, 0, 3), call.SetForegroundWindow(77)]
        assert native.AttachThreadInput.call_args.args[-1] is False


def test_find_and_focus_uses_requested_sequence_for_matching_window():
    process = MagicMock(info={"pid": 42, "name": "notepad.exe"})
    def owner(hwnd, pointer):
        if pointer is not None:
            pointer._obj.value = 42
        return 2
    def rectangle(hwnd, pointer):
        pointer._obj.left, pointer._obj.top = 0, 0
        pointer._obj.right, pointer._obj.bottom = 500, 400
        return True
    with patch("causal_trajectory.user32") as native, patch("causal_trajectory.kernel32"), \
         patch("causal_trajectory.dwmapi"), patch("psutil.process_iter", return_value=[process]), \
         patch("causal_trajectory.time.sleep"):
        native.IsIconic.return_value = False
        native.GetWindow.return_value = 0
        native.GetWindowTextLengthW.return_value = 7
        native.GetWindowTextW.side_effect = lambda hwnd, buffer, size: setattr(buffer, "value", "Notepad")
        native.GetWindowThreadProcessId.side_effect = owner
        native.GetWindowRect.side_effect = rectangle
        native.EnumWindows.side_effect = lambda callback, data: callback(77, data)
        native.GetForegroundWindow.return_value = 77
        assert WindowsAppResolver.find_and_focus_window("notepad") == 77
        operations = [c for c in native.mock_calls if c[0] in ("ShowWindow", "SetWindowPos", "SetForegroundWindow")]
        assert operations == [call.ShowWindow(77, 9), call.SetWindowPos(77, -1, 0, 0, 0, 0, 3),
                              call.SetWindowPos(77, -2, 0, 0, 0, 0, 3), call.SetForegroundWindow(77)]


def test_unfocused_open_app_never_authorizes_typing():
    engine = object.__new__(CausalTrajectoryEngine)
    engine.ctx_engine, engine.pdag, engine.verifier, engine.resolver = MagicMock(), MagicMock(), MagicMock(), MagicMock()
    engine.ctx_engine.capture_foreground_context.return_value = {"hwnd": 999, "process_name": "other.exe"}
    engine.verifier.capture_state_bytes.return_value = b"screen"
    engine.verifier.snapshot_pids.return_value = {10}
    engine.resolver.foreground_app_hwnd.return_value = None
    action = AsyncMock()
    result = asyncio.run(engine.execute_subgoal("typing", action,
        contract={"action": "TYPE", "expects_new_pid": False, "min_ncd": .02, "expected_app": "notepad"}))
    assert result["lambda_obs"] == 0 and "sem foco" in result["failure_reason"]
    action.assert_not_awaited()


def test_field_open_passes_without_focus_but_typing_waits_and_blocks(simulation):
    kernel, engine, window, _, _ = simulation
    window.return_value = {"detected": False, "hwnd": 999}
    original_sleep, waits = asyncio.sleep, []
    async def sleep(seconds):
        waits.append(seconds)
        await original_sleep(0 if seconds == 1.5 else seconds)
    with patch("field_tests.asyncio.sleep", side_effect=sleep):
        asyncio.run(run_field_tests(kernel))
    rows, _ = saved(kernel)
    assert rows[0]["status"] == "✅ PASSOU"
    assert "ativo na memória" in rows[0]["observed"]
    assert rows[1]["status"] == "❌ FALHOU" and 1.5 in waits
    engine.bridge.dispatch.assert_not_awaited()
