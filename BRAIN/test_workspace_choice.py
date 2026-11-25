from unittest.mock import patch

import pytest
import BRAINNET as app
from intent_grounding import explicit_app_choices


@pytest.fixture
def chat(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("BRAINNET_MINIMAL", "1")
    monkeypatch.setenv("BRAINNET_MOTOR_SEMANTIC", "1")
    monkeypatch.setattr(app, "CONFIG_FILE", tmp_path / "config.json")
    bridge = app.BrainnetBridge(app.BrainnetKernel())
    with patch("capability_lab.observe_physical_monitor", return_value={}), \
         patch("inference_backend.HTTPInferenceBackend.generate", side_effect=AssertionError("unexpected generation")), \
         patch("inference_backend.HTTPInferenceBackend.chat", side_effect=AssertionError("unexpected inference")), \
         patch.object(bridge, "_run_remembered_plan", return_value={"status":"ACTION_BLOCKED","dispatched":False}) as dispatch:
        yield bridge, dispatch


def test_real_handler_resumes_only_the_selected_action(chat):
    bridge, dispatch = chat
    first = bridge.send_command("Abra o Paint ou o Bloco de Notas.")
    assert first["choices"] == ["paint", "notepad"] and first["dispatched"] is False
    dispatch.assert_not_called()
    result = bridge.send_command("Bloco de Notas")
    assert result["clarified_task_id"] == first["task_budget"]["task_id"]
    assert result["status"] == "ACTION_BLOCKED" and result["dispatched"] is False
    assert dispatch.call_count == 1 and dispatch.call_args.args[0]["steps"] == [{"action":"open_app","target":"notepad"}]
    assert bridge._pending_app_choice is None


def test_switch_discards_other_chats_choices_and_projects(chat):
    bridge, dispatch = chat
    assert bridge.workspace_chat_activate("a")["ok"]
    assert bridge.send_command("Faça um jogo de corrida")["status"] == "CLARIFICATION_REQUIRED"
    assert bridge.send_command("Abra Paint ou Notepad")["choices"] == ["paint","notepad"]
    assert bridge.workspace_chat_activate("b")["ok"]
    assert bridge._pending_app_choice is None
    assert bridge.send_command("/projeto cancelar")["status"] == "NO_PROJECT"
    dispatch.assert_not_called()


def test_expired_and_negated_choice_cannot_dispatch(chat):
    bridge, dispatch = chat
    bridge.send_command("Abra a Calculadora ou o Paint")
    original, targets, _ = bridge._pending_app_choice
    bridge._pending_app_choice = original, targets, 0
    assert bridge.send_command("Paint")["code"] == "CHOICE_EXPIRED"
    bridge.send_command("Abra a Calculadora ou o Paint")
    assert bridge.send_command("Não abra o Paint")["dispatched"] is False
    assert bridge._pending_app_choice is None
    dispatch.assert_not_called()


@pytest.mark.parametrize("text", ["Não abra Paint ou Notepad", "Abra Paint ou clique em Notepad",
                                 "Abra Paint ou Notepad?", "Abra Paint ou Notepad e clique",
                                 "O que acontece se eu disser abra Paint ou Notepad?", "Paint ou Notepad"])
def test_options_do_not_grant_an_unrequested_operation(text):
    assert explicit_app_choices(text) == ()
