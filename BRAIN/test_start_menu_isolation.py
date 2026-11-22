import ast
import asyncio
import inspect
import textwrap
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from causal_trajectory import WindowsAppResolver
from execution_authority import background_only
from field_tests import run_field_tests
from test_field_tests import simulation, saved


def test_keyboard_sequence_has_exact_waits_and_no_mouse_or_focus_call():
    effector = MagicMock()
    effector.send_text.return_value = True
    resolver = WindowsAppResolver(effector)
    timeline = MagicMock()
    with patch("causal_trajectory.user32") as native, patch("causal_trajectory.time.sleep") as sleep, \
         patch.object(WindowsAppResolver, "_start_menu_has_focus", return_value=True), \
         patch("focus_isolation.suspend_master_shell_focus") as suppress:
        timeline.attach_mock(native.keybd_event, "key")
        timeline.attach_mock(sleep, "sleep")
        timeline.attach_mock(effector.send_text, "type")
        assert resolver._open_via_start_menu("calculadora") is True
        assert timeline.mock_calls == [call.key(0x5B, 0, 0, 0), call.key(0x5B, 0, 2, 0), call.sleep(.8),
                                       call.type("calculadora"), call.sleep(.5), call.key(0x0D, 0, 0, 0), call.key(0x0D, 0, 2, 0)]
        suppress.assert_called_once_with(3.0)
    source = ast.parse(textwrap.dedent(inspect.getsource(WindowsAppResolver._open_via_start_menu)))
    forbidden = {"mouse_move", "mouse_click", "find_and_focus_window", "focus_window_handle"}
    assert not any(isinstance(node, ast.Attribute) and node.attr in forbidden for node in ast.walk(source))


@pytest.mark.parametrize("checks,typed,keys", [([False], False, 2), ([True, False], True, 2)])
def test_lost_menu_focus_blocks_type_or_enter(checks, typed, keys):
    effector = MagicMock()
    effector.send_text.return_value = True
    with patch("causal_trajectory.user32") as native, patch("causal_trajectory.time.sleep"), \
         patch.object(WindowsAppResolver, "_start_menu_has_focus", side_effect=checks), \
         patch("focus_isolation.suspend_master_shell_focus"):
        with pytest.raises(RuntimeError):
            WindowsAppResolver(effector)._open_via_start_menu("calc")
        assert effector.send_text.called is typed
        assert native.keybd_event.call_count == keys


def test_background_cannot_open_menu():
    resolver = WindowsAppResolver(MagicMock())
    @background_only
    def execute():
        resolver._open_via_start_menu("calc")
    with patch("causal_trajectory.user32") as native:
        with pytest.raises(PermissionError):
            execute()
        native.keybd_event.assert_not_called()


def test_master_shell_activation_is_restored_without_global_css_changes():
    import focus_isolation as isolation
    window = SimpleNamespace(native=SimpleNamespace(Handle=SimpleNamespace(ToInt64=lambda: 77)), focus=True, evaluate_js=MagicMock())
    style = {"value": 0x40000}
    with patch.object(isolation, "_native") as native, patch.object(isolation.threading, "Timer"), \
         patch.object(isolation, "_window", None), patch.object(isolation, "_state", None), \
         patch.object(isolation, "_until", 0.0), patch.object(isolation, "_timer", None):
        native.IsWindow.return_value = True
        native.GetWindowLongW.side_effect = lambda *args: style["value"]
        native.SetWindowLongW.side_effect = lambda hwnd, idx, value: style.update(value=value)
        isolation.register_master_shell(window)
        assert isolation.suspend_master_shell_focus(3.0)
        assert window.focus is False and style["value"] & isolation.NO_ACTIVATE
        assert "HTMLElement.prototype.focus" in window.evaluate_js.call_args.args[0]
        isolation._until = 0
        isolation._restore()
        assert window.focus is True and style["value"] == 0x40000


def test_calculator_waits_three_seconds_before_app_window_verification(simulation):
    kernel, engine, _, _, _ = simulation
    timeline = []
    engine.resolver._open_via_start_menu.side_effect = lambda name: timeline.append(("launch", name)) or True
    original_sleep = asyncio.sleep
    async def wait(seconds):
        timeline.append(("wait", seconds))
        await original_sleep(seconds)
    with patch("field_tests.asyncio.sleep", side_effect=wait), \
         patch("field_tests._window_evidence", side_effect=lambda app: timeline.append(("verify", app)) or {"detected": True, "hwnd": 102}):
        asyncio.run(run_field_tests(kernel))
    assert timeline.index(("launch", "calculadora")) < timeline.index(("wait", 3.0)) < timeline.index(("verify", "calc"))
    assert saved(kernel)[0][2]["status"] == "✅ PASSOU"
