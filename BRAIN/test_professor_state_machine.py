"""Interactive teacher states never leak user answers into LLM or ToM."""
from unittest.mock import AsyncMock, patch

import pytest

from test_professor_mode import bridge, send


def test_interactive_concept_purpose_batch_undo_and_save(bridge):
    async def execute(steps, concept, **kwargs):
        for step in steps:
            kwargs["on_step"](step, {"lambda_obs": 0, "ncd_real": .01})
    bridge._kernel.trajectory_engine.execute_professor_batch = AsyncMock(side_effect=execute)
    bridge._kernel.pdag.record_user_confirmed_route.return_value = True
    with patch("BRAINNET.urllib.request.urlopen", side_effect=AssertionError("No LLM")):
        assert "CONCEITO" in send(bridge, "/professor")["reply"]
        session = bridge._professor_mode
        assert session["etapa"] == "conceito"
        assert "1 a 40" in send(bridge, "nome inválido!")["reply"]
        assert session["etapa"] == "conceito"
        assert "PROPÓSITO" in send(bridge, "abrir_obsidian")["reply"]
        assert session["etapa"] == "proposito"
        send(bridge, "abrir_app")
        assert session["etapa"] == "passos"
        send(bridge, "tecla win; digite obsidian; enter")
        assert [step["acao"] for step in session["passos_executados"]] == ["HOTKEY", "TYPE", "HOTKEY"]
        send(bridge, "/voltar")
        assert len(session["passos_executados"]) == len(session["passos_raw"]) == 2
        send(bridge, "enter")
        with patch("BRAINNET.save_qualia", create=True), patch("qualia_algebra.save_qualia"):
            assert "variáveis" in send(bridge, "/fim")["reply"]
            assert "salvo" in send(bridge, "obsidian")["reply"]
        assert bridge._professor_mode is None
    bridge._tom.evaluate_intent.assert_not_called()
    bridge._kernel.pdag.record_user_confirmed_route.assert_called_once()


@pytest.mark.parametrize("stage", ["conceito", "proposito", "passos"])
def test_cancel_and_unknown_slash_are_isolated_in_every_stage(bridge, stage):
    send(bridge, "/professor")
    bridge._professor_mode["etapa"] = stage
    assert "Ensino ativo" in send(bridge, "/importar_dataset")["reply"]
    assert "Nenhum passo" in send(bridge, "/fim")["reply"]
    assert "cancelado" in send(bridge, "/cancelar")["reply"]
    assert bridge._professor_mode is None
    bridge._tom.evaluate_intent.assert_not_called()


@pytest.mark.parametrize("command", ["/fim", "/voltar", "/cancelar"])
def test_controls_without_session_do_not_save(bridge, command):
    result = send(bridge, command)
    assert "Não há" in result["reply"]
    bridge._kernel.pdag.record_user_confirmed_route.assert_not_called()
    bridge._tom.evaluate_intent.assert_not_called()
