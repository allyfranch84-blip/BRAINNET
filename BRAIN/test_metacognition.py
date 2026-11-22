"""Calibracao por intencao e integracao com o retorno factual da ponte."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from BRAINNET import BrainnetBridge
from metacognition import MetacognitionEngine
from theory_of_mind import MotorGateState


AVISO = "(Aviso: estou sobreconfiante nesta rota, posso falhar)"


def test_erro_assinado_acumula_media_de_hits_menos_confianca():
    engine = MetacognitionEngine()
    assert engine.registrar_resultado("rota", 0.9, False) == pytest.approx(-0.9)
    assert engine.registrar_resultado("rota", 0.7, True) == pytest.approx(-0.3)
    assert engine.obter_calibracao("rota") == pytest.approx({
        "tentativas": 2, "taxa_acerto": 0.5,
        "confianca_media": 0.8, "erro_calibracao": -0.3,
    })


def test_intencoes_independentes_normalizadas_sem_truncamento():
    engine = MetacognitionEngine()
    engine.registrar_resultado("  EXECUTE   ROTA  ", 0.9, False)
    engine.registrar_resultado("execute outra rota", 0.7, True)
    assert engine.obter_calibracao("execute rota")["erro_calibracao"] == pytest.approx(-0.9)
    assert engine.obter_calibracao("execute outra rota")["erro_calibracao"] == pytest.approx(0.3)


@pytest.mark.parametrize("confianca", [-0.1, 1.1, float("nan"), float("inf")])
def test_rejeita_confianca_invalida_sem_registrar(confianca):
    engine = MetacognitionEngine()
    with pytest.raises(ValueError):
        engine.registrar_resultado("rota", confianca, True)
    assert engine.obter_calibracao("rota")["tentativas"] == 0


def _bridge(resultado):
    bridge = object.__new__(BrainnetBridge)
    bridge._kernel = MagicMock()
    bridge._kernel.loop = None
    bridge._kernel.metacognition = MetacognitionEngine()
    bridge._kernel.trajectory_engine.executar_trajetoria_completa = AsyncMock(return_value=resultado)
    bridge._kernel.blackbox.registrar_falha_e_punir.return_value = {"snapshot_id": "test"}
    bridge._tom = MagicMock()
    bridge._tom.evaluate_intent.return_value = SimpleNamespace(gate=MotorGateState.GO)
    bridge._modo_coder_ativo = False
    bridge._falar_seguro = MagicMock()
    return bridge


def _executar(bridge):
    return bridge._executar_comando_interno("execute tarefa alfa", "execute tarefa alfa", "execute tarefa alfa")


@pytest.mark.parametrize("mielinizada, sucesso", [(False, False), (False, True), (True, False), (True, True)])
def test_ponte_registra_confianca_origem_e_sucesso_factual(mielinizada, sucesso):
    bridge = _bridge({"status": "CONCLUIDO" if sucesso else "FALHA_REALIDADE",
                      "rota_mielinizada": mielinizada, "sucesso_real": sucesso})
    response = _executar(bridge)
    report = bridge._kernel.metacognition.obter_calibracao("execute tarefa alfa")
    assert report["tentativas"] == 1
    assert report["confianca_media"] == pytest.approx(0.9 if mielinizada else 0.7)
    assert report["taxa_acerto"] == float(sucesso)
    assert (AVISO in response["reply"]) == (not sucesso)
    assert ("✅" in response["reply"]) == sucesso


def test_acerto_ainda_avisa_se_historico_da_intencao_indica_sobreconfianca():
    bridge = _bridge({"status": "CONCLUIDO", "rota_mielinizada": True, "sucesso_real": True})
    for _ in range(3):
        bridge._kernel.metacognition.registrar_resultado("execute tarefa alfa", 0.9, False)
    response = _executar(bridge)
    assert "✅" in response["reply"] and AVISO in response["reply"]
    assert bridge._kernel.metacognition.obter_calibracao("execute tarefa alfa")["tentativas"] == 4


def test_excecao_registra_uma_falha_sem_afirmar_sucesso(tmp_path, monkeypatch):
    monkeypatch.setattr("BRAINNET.__file__", str(tmp_path / "BRAINNET.py"))
    bridge = _bridge({})
    bridge._kernel.trajectory_engine.executar_trajetoria_completa.side_effect = RuntimeError("sensor indisponivel")
    response = _executar(bridge)
    report = bridge._kernel.metacognition.obter_calibracao("execute tarefa alfa")
    assert report["tentativas"] == 1 and report["taxa_acerto"] == 0
    assert AVISO in response["reply"] and "✅" not in response["reply"]


def test_status_textual_sem_confirmacao_factual_nao_e_acerto():
    bridge = _bridge({"status": "CONCLUIDO"})
    response = _executar(bridge)
    assert bridge._kernel.metacognition.obter_calibracao("execute tarefa alfa")["taxa_acerto"] == 0
    assert AVISO in response["reply"] and "✅" not in response["reply"]
