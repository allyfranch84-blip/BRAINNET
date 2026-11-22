"""Explicit full narration without real speech synthesis, playback or LLM."""
import inspect
import queue
import threading
from unittest.mock import MagicMock, patch

import pytest

from BRAINNET import BrainnetBridge
from speech_voice import SpeechVoiceEngine


@pytest.fixture
def bridge():
    obj = object.__new__(BrainnetBridge)
    obj._kernel, obj._tom = MagicMock(), MagicMock()
    obj._kernel.voice.falar.return_value = True
    obj._kernel.esta_dormindo = True
    obj._chat_history = []
    obj._falar_seguro = MagicMock()
    return obj


@pytest.mark.parametrize("command", ["/leia **Primeira frase.** Segunda frase.", "/LEIA Primeira frase. Segunda frase.", "/leia\nPrimeira frase. Segunda frase."])
def test_explicit_read_keeps_all_sentences_and_bypasses_llm(bridge, command):
    with patch("BRAINNET.urllib.request.urlopen", side_effect=AssertionError("No LLM")):
        result = bridge.send_command(command)
    bridge._kernel.voice.falar.assert_called_once_with("Primeira frase. Segunda frase.", max_chars=10000)
    bridge._tom.evaluate_intent.assert_not_called()
    bridge._kernel.trajectory_engine.executar_trajetoria_completa.assert_not_called()
    bridge._falar_seguro.assert_not_called()
    assert "Narrando texto integral" in result["reply"]


def test_read_uses_latest_ai_answer_and_ignores_user_text(bridge):
    text = "Primeira frase.\n\n" + "Detalhes da pesquisa. " * 100
    bridge._chat_history = [{"role": "ai", "text": "Resposta antiga"},
                            {"role": "ai", "text": text}, {"role": "user", "text": "não leia isto"}]
    bridge.send_command("/leia")
    expected = SpeechVoiceEngine._limpar_texto(text, max_chars=10000)
    assert len(expected) > 1600
    bridge._kernel.voice.falar.assert_called_once_with(expected, max_chars=10000)


@pytest.mark.parametrize("history", [[], [{"role": "user", "text": "Somente usuário"}]])
def test_read_without_ai_history_reports_no_recent_text(bridge, history):
    bridge._chat_history = history
    assert "Não há texto recente" in bridge.send_command("/leia")["reply"]
    bridge._kernel.voice.falar.assert_not_called()


def test_repeated_read_does_not_replace_answer_with_narration_ack(bridge):
    history = [{"role": "ai", "text": "Resposta completa. Segundo parágrafo."}]
    bridge._chat_history = history.copy()
    bridge.send_command("/leia")
    bridge.send_command("/leia")
    assert bridge._chat_history == history
    assert bridge._kernel.voice.falar.call_count == 2
    for call in bridge._kernel.voice.falar.call_args_list:
        assert call.args[0] == history[0]["text"]


def test_failed_synthesis_does_not_claim_narration_started(bridge):
    bridge._kernel.voice.falar.return_value = False
    result = bridge.send_command("/leia Olá.")
    assert "Não foi possível iniciar" in result["reply"]
    assert "Narrando" not in result["reply"]


def test_read_of_markup_without_readable_content_does_not_synthesize(bridge):
    result = bridge.send_command("/leia *** ### ```")
    assert "Não há texto narrável" in result["reply"]
    bridge._kernel.voice.falar.assert_not_called()


def test_read_reports_limit_when_source_is_longer_than_10000(bridge):
    result = bridge.send_command("/leia " + "palavra " * 2000)
    text = bridge._kernel.voice.falar.call_args.args[0]
    assert len(text) <= 10000
    assert "limitado a 10.000" in result["reply"]


@pytest.fixture
def voice(tmp_path, monkeypatch):
    engine = object.__new__(SpeechVoiceEngine)
    engine._fila_audio = queue.Queue()
    engine._lock_audio = threading.RLock()
    engine._audio_generation = 0
    engine._lock_sintese = threading.Lock()
    engine._pygame_iniciado = False
    captured = []
    def synthesize(text, path):
        captured.append(text)
        path.write_bytes(b"fake speech")
        return True
    engine._sintetizar_edge_neural = synthesize
    monkeypatch.setattr("speech_voice.PASTA_TEMP", tmp_path)
    yield engine, captured
    engine.parar()


def test_speech_default_remains_summary_but_explicit_limit_reads_full(voice):
    engine, captured = voice
    text = "Primeira frase. " + "Detalhes adicionais da pesquisa. " * 100
    assert engine.falar(text)
    assert captured[-1] == "Primeira frase."
    assert engine.falar(text, max_chars=10000)
    assert captured[-1] == SpeechVoiceEngine._limpar_texto(text, max_chars=10000)
    assert len(captured[-1]) > 1600


def test_explicit_read_can_narrate_cleaned_code_without_generic_substitution(voice):
    engine, captured = voice
    assert engine.falar("class Exemplo: Primeira explicação. Segunda explicação.", max_chars=10000)
    assert "Segunda explicação" in captured[-1]
    assert "Consulte o texto" not in captured[-1]


def test_stop_still_clears_full_narration_queue(voice):
    engine, _ = voice
    assert engine.falar("Primeira frase. Segunda frase.", max_chars=10000)
    assert not engine._fila_audio.empty()
    engine.parar()
    assert engine._fila_audio.empty() and engine._fila_audio.unfinished_tasks == 0


def test_cleaner_defaults_to_1600_and_accepts_10000_without_overflow():
    assert inspect.signature(SpeechVoiceEngine._limpar_texto).parameters["max_chars"].default == 1600
    assert inspect.signature(SpeechVoiceEngine.falar).parameters["max_chars"].default == 1600
    assert len(SpeechVoiceEngine._limpar_texto("x" * 10001, max_chars=10000)) == 10000
