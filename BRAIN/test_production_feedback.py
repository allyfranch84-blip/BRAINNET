"""Production regressions tested without MasterShell, LLM or Windows actions."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import BRAINNET
from BRAINNET import BrainnetBridge
from causal_trajectory import CausalTrajectoryEngine
from metacognition import MetacognitionEngine
from theory_of_mind import MotorGateState


@pytest.fixture
def bridge():
    obj = object.__new__(BrainnetBridge)
    obj._kernel = MagicMock()
    obj._kernel.esta_dormindo = False
    obj._kernel.loop = None
    obj._kernel.metacognition = MetacognitionEngine()
    obj._tom = MagicMock()
    obj._tom.evaluate_intent.return_value = SimpleNamespace(gate=MotorGateState.GO, is_physical_world=False)
    obj._last_executed_task = "abra o Brave"
    obj._window = None
    obj._modo_coder_ativo = False
    obj._chat_history = []
    obj._falar_seguro = MagicMock()
    return obj


@pytest.mark.parametrize("text", ["não abriu", "nao funcionou", "errou", "falhou", "deu errado", "quebrou", "não é isso"])
def test_negative_feedback_precedes_tom_and_keeps_original_task(bridge, text):
    bridge._kernel.pdag.apply_user_report_penalty.return_value = {"status": "PENALTY_APPLIED"}
    result = bridge.send_command(text)
    bridge._kernel.pdag.apply_user_report_penalty.assert_called_once_with("abra o Brave", text)
    bridge._tom.evaluate_intent.assert_not_called()
    bridge._kernel.trajectory_engine.executar_trajetoria_completa.assert_not_called()
    assert bridge._last_executed_task == ""
    assert bridge._last_completed_task == "abra o Brave"
    assert "penalizada" in result["reply"]


def test_missing_route_does_not_claim_penalty(bridge):
    bridge._kernel.pdag.apply_user_report_penalty.return_value = {"status": "NOT_FOUND"}
    assert "nenhuma rota" in bridge.send_command("não abriu")["reply"]


@pytest.mark.parametrize("text", ["você abriu?", "voce executou?", "o brave está aberto?", "o bloco de notas abriu?"])
def test_state_query_is_read_only_and_reports_observed_focus(bridge, text):
    bridge._kernel.context_engine.escanear_estado_janelas.return_value = [
        {"titulo": "Editor real", "em_foco": True}, {"titulo": "Outra janela", "em_foco": False}]
    result = bridge.send_command(text)
    assert "Editor real" in result["reply"] and "Outra janela" not in result["reply"]
    assert bridge._last_executed_task == ""
    assert bridge._last_completed_task == "abra o Brave"
    bridge._tom.evaluate_intent.assert_not_called()
    bridge._kernel.pdag.apply_user_report_penalty.assert_not_called()
    bridge._kernel.trajectory_engine.executar_trajetoria_completa.assert_not_called()


def test_exception_preserves_type_traceback_and_empty_message(bridge, tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(BRAINNET, "__file__", str(tmp_path / "BRAINNET.py"))
    bridge._kernel.trajectory_engine.executar_trajetoria_completa = AsyncMock(side_effect=AssertionError())
    result = bridge.send_command("execute tarefa alfa")
    assert "AssertionError: sem mensagem" in result["reply"]
    assert "Snapshot gravado" in result["reply"]
    snapshot = json.loads(next((tmp_path / "error_snapshots").glob("*.json")).read_text(encoding="utf-8"))
    assert snapshot["exception_type"] == "AssertionError"
    assert "Traceback" in snapshot["traceback"]
    assert any(record.exc_info for record in caplog.records)


def test_snapshot_write_failure_does_not_hide_original_error(bridge, tmp_path, monkeypatch):
    monkeypatch.setattr(BRAINNET, "__file__", str(tmp_path / "BRAINNET.py"))
    bridge._kernel.trajectory_engine.executar_trajetoria_completa = AsyncMock(side_effect=ValueError("sensor"))
    with patch("BRAINNET.Path.write_text", side_effect=PermissionError("read only")):
        result = bridge.send_command("execute tarefa alfa")
    assert "ValueError: sensor" in result["reply"]
    assert "Não foi possível gravar" in result["reply"]


@pytest.mark.parametrize("original,normalized", [
    ("abra thoruym", "abra thorium"), ("abra thoruim", "abra thorium"),
    ("abra navageaor", "abra navegador"), ("abra nabegador", "abra navegador"),
    ("abra whatsappp", "abra whatsapp"), ("abra whatsap", "abra whatsapp"),
])
def test_phonetics_precedes_fhrr_projection(original, normalized):
    engine = object.__new__(CausalTrajectoryEngine)
    with patch.object(CausalTrajectoryEngine, "_projetar_onda_de_probabilidade", side_effect=RuntimeError("stop before actions")) as projection:
        with pytest.raises(RuntimeError, match="stop before actions"):
            engine.decompor_trajetoria_cognitiva(original)
    projection.assert_called_once_with(normalized)


def test_compound_typo_normalizes_command_but_preserves_quoted_content():
    engine = object.__new__(CausalTrajectoryEngine)
    result = engine.decompor_trajetoria_cognitiva("abra o bloco de nootas e digiti 'whatsap thoruym'")
    assert result["passos"][0]["app"] == "notepad"
    assert result["passos"][1]["text"] == "whatsap thoruym"


def test_creative_generation_has_bounded_token_budget_and_timeout():
    engine = object.__new__(CausalTrajectoryEngine)
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps({"response": "Verso completo", "done": True}).encode()
    with patch("causal_trajectory.urllib.request.urlopen", return_value=response) as request:
        assert engine._generate_creative_text("um poema curto") == "Verso completo"
    assert request.call_args.kwargs["timeout"] == 45
    assert json.loads(request.call_args.args[0].data)["options"]["num_predict"] == 2048
