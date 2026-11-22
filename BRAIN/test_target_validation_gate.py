import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from causal_trajectory import CausalTrajectoryEngine, TargetMismatchError
from teacher_slots import abstract_message, instantiate_message
from test_professor_multi_slots import steps


def engine_with_ocr(rows, hwnd_after=42):
    engine = object.__new__(CausalTrajectoryEngine)
    engine.vision_eye = MagicMock()
    engine.vision_eye.capture_ui_observation.return_value = (Image.new("RGB", (1000, 800)), (0, 0, 1000, 800), {"hwnd": 42})
    engine.vision_eye.extrair_texto_e_coordenadas.return_value = rows
    engine.ctx_engine = MagicMock()
    engine.ctx_engine.capture_foreground_context.return_value = {"hwnd": hwnd_after}
    engine.bridge = SimpleNamespace(dispatch=AsyncMock(return_value=SimpleNamespace(status="completed", result=True)))
    return engine


@pytest.mark.parametrize("rows", [None, [], [{"texto": "Outra pessoa", "confianca": .99}], [{"texto": "Davi", "confianca": .89}], [{"texto": "Davi Silva", "confianca": .99}]])
def test_missing_or_uncertain_header_blocks_message_before_any_input(rows):
    engine = engine_with_ocr(rows)
    with pytest.raises(TargetMismatchError, match="mensagem não foi enviada"):
        asyncio.run(engine._executar_passo_individual({"acao": "TYPE", "text": "Olá", "target_contact": "Davi"}))
    engine.bridge.dispatch.assert_not_awaited()


def test_gate_uses_only_conversation_header_not_search_results():
    engine = engine_with_ocr([{"texto": "Davi", "confianca": .99}])
    asyncio.run(engine._executar_passo_individual({"acao": "TYPE", "text": "Olá", "target_contact": "Davi"}))
    crop = engine.vision_eye.extrair_texto_e_coordenadas.call_args.args[0]
    assert crop.size == (650, 144)
    assert engine.bridge.dispatch.await_args.args[0] == "send_text"


def test_contact_is_rechecked_before_enter_even_after_successful_typing():
    engine = engine_with_ocr([{"texto": "Davi", "confianca": .99}])
    async def run():
        await engine._executar_passo_individual({"p": "TYPE", "text": "Olá", "target_contact": "Davi"})
        engine.vision_eye.extrair_texto_e_coordenadas.return_value = None
        with pytest.raises(TargetMismatchError):
            await engine._executar_passo_individual({"p": "HOTKEY", "keys": ["enter"], "target_contact": "Davi"})
    asyncio.run(run())
    assert engine.bridge.dispatch.await_count == 1
    assert engine.bridge.dispatch.await_args.args[0] == "send_text"


def test_focus_change_during_ocr_blocks_input():
    engine = engine_with_ocr([{"texto": "Davi", "confianca": .99}], hwnd_after=99)
    with pytest.raises(TargetMismatchError):
        asyncio.run(engine._executar_passo_individual({"acao": "TYPE", "text": "Olá", "target_contact": "Davi"}))
    engine.bridge.dispatch.assert_not_awaited()


def test_generic_message_binds_gate_only_to_payload_and_send():
    template = abstract_message(steps(), {"app": "whatsapp", "contato": "Davi", "msg": "Olá"})
    pdag = MagicMock()
    pdag.is_verified_demonstration.return_value = True
    pdag.find_myelinated_path.return_value = template
    plan = instantiate_message(pdag, "enviar mensagem para Ana dizendo Olá")
    marked = [step for step in plan["passos"] if "target_contact" in step]
    assert len(marked) == 2
    assert all(step["target_contact"] == "Ana" for step in marked)
    assert marked[0]["text"] == "Olá" and marked[1]["keys"] == ["enter"]
    assert all("target_contact" not in step for step in template["passos"])
