"""New mouse actions are verified with mocked SendInput; no real cursor input."""
import asyncio
import ctypes
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import effector as mouse
from effector import Effector
from actuator_bridge import ActuatorBridge, CommandPriority
from causal_trajectory import CausalTrajectoryEngine
from execution_authority import background_only


@pytest.mark.parametrize("direction,clicks,delta", [("up", 1, 120), ("down", 1, -120), ("up", 3, 360), ("down", 4, -480)])
def test_scroll_sendinput_flags_signed_delta_and_struct_size(direction, clicks, delta):
    events = []
    def send_input(count, pointer, size):
        event = ctypes.cast(pointer, ctypes.POINTER(mouse.INPUT)).contents
        events.append((count, size, event.type, event.u.mi.dwFlags, ctypes.c_int32(event.u.mi.mouseData).value))
        return 1
    with patch("effector.user32", SimpleNamespace(SendInput=send_input)):
        assert Effector().mouse_scroll(direction, clicks) is True
    assert events == [(1, ctypes.sizeof(mouse.INPUT), mouse.INPUT_MOUSE, mouse.MOUSEEVENTF_WHEEL, delta)]


@pytest.mark.parametrize("direction,clicks", [("left", 1), ("down", 0), ("up", -1), ("up", 1.5), ("up", True), ("down", 2**31)])
def test_invalid_scroll_never_calls_sendinput(direction, clicks):
    send = MagicMock()
    with patch("effector.user32", SimpleNamespace(SendInput=send)):
        with pytest.raises(ValueError):
            Effector().mouse_scroll(direction, clicks)
    send.assert_not_called()


def test_scroll_reports_sendinput_failure():
    with patch("effector.user32", SimpleNamespace(SendInput=MagicMock(return_value=0))):
        assert Effector().mouse_scroll("down") is False


@pytest.mark.parametrize("button,flags", [
    ("right", [mouse.MOUSEEVENTF_RIGHTDOWN, mouse.MOUSEEVENTF_RIGHTUP]),
    ("left", [mouse.MOUSEEVENTF_LEFTDOWN, mouse.MOUSEEVENTF_LEFTUP]),
])
def test_click_sends_matching_down_and_up(button, flags):
    observed = []
    def send_input(count, pointer, size):
        observed.append(ctypes.cast(pointer, ctypes.POINTER(mouse.INPUT)).contents.u.mi.dwFlags)
        return 1
    with patch("effector.user32", SimpleNamespace(SendInput=send_input)), patch("effector.time.sleep"):
        assert Effector().mouse_click(button) is True
    assert observed == flags


@pytest.mark.parametrize("returns", [[0], [1, 0]])
def test_right_click_does_not_report_success_when_injection_fails(returns):
    with patch("effector.user32", SimpleNamespace(SendInput=MagicMock(side_effect=returns))), patch("effector.time.sleep"):
        assert Effector().mouse_click("right") is False


@pytest.mark.parametrize("action,payload,method,args,kwargs", [
    ("right_click", {}, "mouse_click", ("right",), {}),
    ("scroll", {}, "mouse_scroll", (), {"direction": "down", "clicks": 1}),
    ("scroll", {"direction": "up", "clicks": 3}, "mouse_scroll", (), {"direction": "up", "clicks": 3}),
])
def test_bridge_routes_new_actions_without_touching_hardware(action, payload, method, args, kwargs):
    hardware = MagicMock()
    getattr(hardware, method).return_value = True
    bridge = ActuatorBridge(hardware, None)
    assert asyncio.run(bridge._route_execution(action, payload)) is True
    getattr(hardware, method).assert_called_once_with(*args, **kwargs)


@pytest.mark.parametrize("step,command,payload", [
    ({"acao": "RIGHT_CLICK"}, "right_click", {}),
    ({"acao": "SCROLL"}, "scroll", {"direction": "down", "clicks": 1}),
    ({"acao": "SCROLL", "direction": "up", "clicks": 2}, "scroll", {"direction": "up", "clicks": 2}),
])
def test_trajectory_dispatches_new_actions(step, command, payload):
    engine = object.__new__(CausalTrajectoryEngine)
    engine.bridge = SimpleNamespace(dispatch=AsyncMock(return_value=SimpleNamespace(status="completed", result=True)))
    assert asyncio.run(engine._executar_passo_individual(step)) is True
    engine.bridge.dispatch.assert_awaited_once_with(command, payload, priority=CommandPriority.HIGH)


@pytest.mark.parametrize("action", ["RIGHT_CLICK", "SCROLL"])
def test_new_actions_reject_background_without_dispatch(action):
    engine = object.__new__(CausalTrajectoryEngine)
    engine.bridge = SimpleNamespace(dispatch=AsyncMock())
    with pytest.raises(PermissionError, match="background"):
        asyncio.run(engine._executar_passo_individual({"acao": action}, is_background=True))
    engine.bridge.dispatch.assert_not_called()


@pytest.mark.parametrize("action", ["RIGHT_CLICK", "SCROLL"])
def test_low_level_new_actions_preserve_background_guard(action):
    @background_only
    def execute():
        return Effector().mouse_scroll("down") if action == "SCROLL" else Effector().mouse_click("right")
    send = MagicMock()
    with patch("effector.user32", SimpleNamespace(SendInput=send)):
        with pytest.raises(PermissionError, match="background"):
            execute()
    send.assert_not_called()


@pytest.mark.parametrize("action", ["RIGHT_CLICK", "SCROLL"])
def test_new_actions_use_verifier_and_transition_writer(action):
    engine = object.__new__(CausalTrajectoryEngine)
    engine.verifier = MagicMock(ncd_threshold=0.2)
    engine.verifier.snapshot_pids.return_value = {10}
    engine.verifier.capture_state_bytes.return_value = b"screen"
    engine.verifier.measure_collapse.return_value = (1, 1.0, "", 10, 0.1, 0.02)
    engine.ctx_engine = MagicMock()
    engine.ctx_engine.capture_foreground_context.return_value = {"hwnd": 77, "pid": 10, "process_name": "editor.exe"}
    engine.pdag = MagicMock()
    result = asyncio.run(engine.execute_subgoal(action, AsyncMock(), contract=engine._contract_for_action(action)))
    contract = engine.verifier.measure_collapse.call_args.kwargs["contract"]
    assert contract["expects_new_pid"] is False and contract["target_hwnd"] == 77
    assert contract["min_ncd"] == 0.02
    assert result["lambda_obs"] == 1
    engine.pdag.record_transition.assert_called_once()
    assert engine.pdag.record_transition.call_args.args[-1] == "editor.exe"


@pytest.mark.parametrize("action", ["RIGHT_CLICK", "SCROLL"])
def test_failed_injection_is_not_successful_step(action):
    engine = object.__new__(CausalTrajectoryEngine)
    engine.bridge = SimpleNamespace(dispatch=AsyncMock(return_value=SimpleNamespace(status="completed", result=False)))
    with pytest.raises(RuntimeError):
        asyncio.run(engine._executar_passo_individual({"acao": action}))
