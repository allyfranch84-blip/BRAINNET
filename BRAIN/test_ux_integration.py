import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from BRAINNET import BrainnetBridge
from browser_bridge import BrowserDeepBridge


def tab_state(ids, active, focused=True):
    return {"ok": True, "window_id": 10, "focused": focused,
            "tabs": [{"id": i, "active": i == active, "window_id": 10} for i in ids]}


def browser_with_states(states, hwnd=77):
    browser = object.__new__(BrowserDeepBridge)
    import time
    browser._last_heartbeat = time.time()
    browser._research_tab_ids = {17, 23}
    browser.send_command = MagicMock(side_effect=states)
    browser.resolver = SimpleNamespace(foreground_app_hwnd=MagicMock(return_value=hwnd))
    browser.effector = SimpleNamespace(send_hotkey=MagicMock(return_value=True))
    return browser


def test_fallback_closes_only_research_tabs_and_preserves_last_tab():
    browser = browser_with_states([
        tab_state([1, 17, 23], 23), tab_state([1, 17], 17),
        tab_state([1, 17], 17), tab_state([1], 1),
    ])
    result = browser._close_research_tabs_keyboard([17, 23])
    assert result == {"ok": True, "closed_count": 2}
    assert browser.effector.send_hotkey.call_count == 2
    assert all(call.args == (["ctrl", "w"],) for call in browser.effector.send_hotkey.call_args_list)
    assert browser._research_tab_ids == set()


@pytest.mark.parametrize("state,hwnd", [
    (tab_state([17], 17), 77),
    (tab_state([1, 17], 1), 77),
    (tab_state([1, 17], 17, focused=False), 77),
    (tab_state([1, 17], 17), 0),
    ({"ok": False}, 77),
])
def test_fallback_never_closes_last_user_or_unfocused_tab(state, hwnd):
    browser = browser_with_states([state], hwnd)
    assert browser._close_research_tabs_keyboard([17])["ok"] is False
    browser.effector.send_hotkey.assert_not_called()
    assert browser._research_tab_ids == {17, 23}


def test_fallback_stops_if_window_changes_during_tab_snapshot():
    browser = browser_with_states([tab_state([1, 17], 17)])
    browser.resolver.foreground_app_hwnd.side_effect = [77, 99]
    assert browser._close_research_tabs_keyboard([17])["ok"] is False
    browser.effector.send_hotkey.assert_not_called()


def test_fallback_does_not_claim_success_without_closure_confirmation():
    browser = browser_with_states([tab_state([1, 17], 17), {"ok": False}])
    assert browser._close_research_tabs_keyboard([17]) == {"ok": False, "closed_count": 0}
    browser.effector.send_hotkey.assert_called_once_with(["ctrl", "w"])
    assert 17 in browser._research_tab_ids


def test_voice_transcription_is_escaped_and_emitted_before_command_processing():
    bridge = object.__new__(BrainnetBridge)
    bridge._professor_mode = None
    events = []
    bridge._window = SimpleNamespace(evaluate_js=lambda js: events.append(("js", js)))
    bridge.send_command = lambda text: events.append(("command", text)) or {}
    spoken = "olá '); window.bad = true; //\ntexto"
    bridge._on_voice_input(spoken)
    assert events[0][0] == "js" and "aios:voice_transcription" in events[0][1]
    assert json.dumps({"text": spoken}, ensure_ascii=True) in events[0][1]
    assert events[1] == ("command", spoken)
