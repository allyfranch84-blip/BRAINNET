import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from causal_trajectory import CausalTrajectoryEngine
from pdag_engine import MyelinatedPDAGEngine
from professor_mode import parse_professor_step
from teacher_slots import abstract_message, parse_variables
from test_professor_mode import bridge, send
from test_professor_complete import mock_batch


def steps():
    return [{"acao": "HOTKEY", "keys": ["win"]}, {"acao": "TYPE", "text": "whatsapp"},
            {"acao": "HOTKEY", "keys": ["enter"]}, {"acao": "WAIT", "seconds": 3.0},
            {"acao": "HOTKEY", "keys": ["ctrl", "f"]}, {"acao": "TYPE", "text": "Davi"},
            {"acao": "HOTKEY", "keys": ["enter"]}, {"acao": "TYPE", "text": "Olá"},
            {"acao": "HOTKEY", "keys": ["enter"]}]


def test_multi_slot_finish_records_generic_with_human_confirmation(bridge):
    mock_batch(bridge)
    bridge._kernel.pdag.record_user_confirmed_route.return_value = True
    send(bridge, "/professor mensagem | enviar_mensagem | tecla win; digite whatsapp; enter; aguarde 3 segundos; tecla ctrl+f; digite Davi; enter; digite Olá; enter")
    assert "variáveis" in send(bridge, "/fim")["reply"]
    bridge._kernel.pdag.record_user_confirmed_route.assert_not_called()
    with patch("qualia_algebra.save_qualia"):
        assert "salvo" in send(bridge, "app=whatsapp, contato=Davi, msg=Olá")["reply"]
    args = bridge._kernel.pdag.record_user_confirmed_route.call_args.args
    assert args[0] == "trajectory:enviar_mensagem_generico"
    assert [step["text"] for step in args[2]["passos"] if step["acao"] == "TYPE"] == ["{APP_ALVO}", "{CONTATO}", "{MENSAGEM}"]
    assert bridge._professor_mode is None
    bridge._tom.evaluate_intent.assert_not_called()


def test_generic_message_reloads_and_preserves_payload_without_llm(bridge, tmp_path):
    vsa = bridge._kernel.vsa
    template = abstract_message(steps(), {"app": "whatsapp", "contato": "Davi", "msg": "Olá"})
    path = str(tmp_path / "message.db")
    pdag = MyelinatedPDAGEngine(path, dim=64, max_nodes=4)
    assert pdag.record_user_confirmed_route("trajectory:enviar_mensagem_generico", "enviar_mensagem_generico", template, vsa.generate_vector("message"), vsa)
    pdag.close()
    pdag = MyelinatedPDAGEngine(path, dim=64, max_nodes=4)
    try:
        engine = object.__new__(CausalTrajectoryEngine)
        engine.pdag = pdag
        with patch("urllib.request.urlopen", side_effect=AssertionError("No LLM")):
            plan = engine.decompor_trajetoria_cognitiva("enviar mensagem para Ana dizendo não abra o brave, diga Olá")
        assert [s["text"] for s in plan["passos"] if s["acao"] == "TYPE"] == ["whatsapp", "Ana", "não abra o brave, diga Olá"]
        assert plan["passos"][3] == {"acao": "WAIT", "seconds": 3.0}
        assert template["passos"][5]["text"] == "{CONTATO}"
    finally:
        pdag.close()


def test_quoted_variables_preserve_commas():
    assert parse_variables('app=whatsapp, contato="Davi Silva", msg="Olá, tudo bem?"')["msg"] == "Olá, tudo bem?"


@pytest.mark.parametrize("raw", ["app=whatsapp, contato=Davi", "app=x, app=y", "msg=", "contato={CONTATO}"])
def test_invalid_variables_cannot_form_generic_message(raw):
    with pytest.raises(ValueError):
        abstract_message(steps(), parse_variables(raw))


def test_wait_parsing_and_executor_are_async():
    step = parse_professor_step("aguarde 3 segundos")
    assert step == {"acao": "WAIT", "seconds": 3.0}
    with patch("causal_trajectory.asyncio.sleep", new_callable=AsyncMock) as sleep:
        assert asyncio.run(object.__new__(CausalTrajectoryEngine)._executar_passo_individual(step))
        sleep.assert_awaited_once_with(3.0)
