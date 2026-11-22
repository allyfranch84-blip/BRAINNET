"""DOM and speech regressions without a browser, sound device or TTS network."""
import json
from pathlib import Path
import queue
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from BRAINNET import BrainnetBridge
from browser_bridge import BrowserDeepBridge
from speech_voice import SpeechVoiceEngine
from theory_of_mind import MotorGateState


@pytest.fixture
def voice(tmp_path, monkeypatch):
    engine = object.__new__(SpeechVoiceEngine)
    engine.voice_name = "fake"
    engine._fila_audio = queue.Queue()
    engine._lock_audio = threading.RLock()
    engine._audio_generation = 0
    engine._lock_sintese = threading.Lock()
    engine._pygame_iniciado = True
    engine._ativo = False
    pygame = SimpleNamespace(mixer=SimpleNamespace(get_init=lambda: True, music=MagicMock(), stop=MagicMock()))
    monkeypatch.setitem(sys.modules, "pygame", pygame)
    monkeypatch.setattr("speech_voice.PASTA_TEMP", tmp_path)
    return engine, pygame


@pytest.mark.parametrize("text,expected", [
    ("Primeira frase. Segunda frase muito longa.", "Primeira frase."),
    ("Primeiro parágrafo\n\nSegundo parágrafo.", "Primeiro parágrafo"),
    ("**Olá!** Mais detalhes aqui.", "Olá!"),
])
def test_voice_summary_keeps_first_sentence_or_paragraph(text, expected):
    assert SpeechVoiceEngine.resumir_para_voz(text) == expected


def test_long_voice_summary_is_bounded():
    assert len(SpeechVoiceEngine.resumir_para_voz("palavra " * 1000)) <= 320


def test_stop_clears_pending_audio_and_all_mixer_playback(voice, tmp_path):
    engine, pygame = voice
    files = [tmp_path / "one.mp3", tmp_path / "two.mp3"]
    for path in files:
        path.write_bytes(b"fake")
        engine._fila_audio.put((0, path))
    engine.parar()
    assert engine._audio_generation == 1
    assert engine._fila_audio.empty() and engine._fila_audio.unfinished_tasks == 0
    assert not any(path.exists() for path in files)
    pygame.mixer.music.stop.assert_called_once()
    pygame.mixer.stop.assert_called_once()
    pygame.mixer.music.unload.assert_called_once()


def test_inflight_synthesis_cannot_requeue_after_stop(voice):
    engine, _ = voice
    entered, release, stopped = threading.Event(), threading.Event(), threading.Event()
    result = []
    def synthesize(text, path):
        path.write_bytes(b"fake audio")
        entered.set()
        release.wait(3)
        return True
    engine._sintetizar_edge_neural = synthesize
    worker = threading.Thread(target=lambda: result.append(engine.falar("Primeira frase. Outra frase.")), daemon=True)
    stopper = threading.Thread(target=lambda: (engine.parar(), stopped.set()), daemon=True)
    worker.start()
    try:
        assert entered.wait(2)
        stopper.start()
        assert stopped.wait(1), "Stop must not wait for the synthesis lock"
    finally:
        release.set()
        worker.join(3)
        if stopper.ident:
            stopper.join(2)
    assert result == [False]
    assert engine._fila_audio.empty()


def test_dequeued_old_audio_cannot_start_after_stop(voice, tmp_path):
    engine, pygame = voice
    class StopOnDequeue(queue.Queue):
        def get(self, *args, **kwargs):
            item = super().get(*args, **kwargs)
            engine.parar()
            engine._ativo = False
            return item
    engine._fila_audio = StopOnDequeue()
    path = tmp_path / "dequeued.mp3"
    path.write_bytes(b"fake")
    engine._fila_audio.put((0, path))
    engine._ativo = True
    engine._loop_player()
    pygame.mixer.music.play.assert_not_called()
    pygame.mixer.music.load.assert_not_called()
    assert not path.exists() and engine._fila_audio.unfinished_tasks == 0


@pytest.mark.parametrize("command", ["/pare", "/silencio", "/silêncio", "/stop"])
def test_stop_route_precedes_tom_llm_and_wakeup_voice(command):
    bridge = object.__new__(BrainnetBridge)
    bridge._kernel, bridge._tom = MagicMock(), MagicMock()
    bridge._kernel.esta_dormindo = True
    bridge._falar_seguro = MagicMock()
    with patch("BRAINNET.urllib.request.urlopen", side_effect=AssertionError("No LLM")):
        result = bridge.send_command(command)
    assert result["reply"] == "Áudio interrompido."
    bridge._kernel.voice.parar.assert_called_once()
    bridge._tom.evaluate_intent.assert_not_called()
    bridge._kernel.trajectory_engine.executar_trajetoria_completa.assert_not_called()
    bridge._falar_seguro.assert_not_called()


def test_full_conversational_reply_stays_in_chat_but_voice_is_short():
    bridge = object.__new__(BrainnetBridge)
    bridge._kernel, bridge._tom = MagicMock(), MagicMock()
    bridge._tom.evaluate_intent.return_value = SimpleNamespace(gate=MotorGateState.GO)
    bridge._modo_coder_ativo = False
    bridge._falar_seguro = MagicMock()
    text = "Primeira sentença factual. " + "Detalhes completos para a interface. " * 20
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps({"response": text}).encode()
    with patch("BRAINNET.urllib.request.urlopen", return_value=response):
        result = bridge._executar_comando_interno("quem foi Dom Pedro II?", "quem foi dom pedro ii?", "quem foi dom pedro ii?")
    assert result["reply"] == text.strip()
    bridge._falar_seguro.assert_called_once_with("Primeira sentença factual.")


def test_central_voice_path_also_limits_screen_descriptions():
    bridge = object.__new__(BrainnetBridge)
    bridge._kernel = MagicMock()
    bridge._falar_seguro("Descrição inicial. " + "Detalhe de tela. " * 100)
    bridge._kernel.voice.falar.assert_called_once_with("Descrição inicial.")


def test_dom_html_and_scripts_are_removed_before_context_limit():
    text = "<html><nav>MENU LIXO</nav><script>codigo secreto</script><main><h1>Titulo</h1><p>" + "Conteudo " * 1000 + "</p></main></html>"
    clean = BrowserDeepBridge._clean_excerpt(text)
    assert len(clean) <= 6000
    assert "MENU LIXO" not in clean and "codigo secreto" not in clean
    assert "<main>" not in clean and "Titulo" in clean


def test_oversized_excerpt_requests_semantic_extraction_on_same_tab():
    browser = SimpleNamespace(extension_connected=True,
        send_command=MagicMock(return_value={"ok": True, "text_excerpt": "Artigo limpo"}))
    result = BrowserDeepBridge._prepare_page_data(browser, {"tab_id": 27, "text_excerpt": "x" * 7000, "html": "huge raw html"})
    assert result["text_excerpt"] == "Artigo limpo" and "html" not in result
    browser.send_command.assert_called_once_with("DOM_ACTION", tab_id=27,
        payload={"mode": "EXTRACT", "preferred_tags": ["main", "article", "p", "h1"], "max_chars": 6000}, timeout=6.0)


def test_excerpt_without_tab_identity_is_cut_without_reading_other_tab():
    browser = SimpleNamespace(send_command=MagicMock())
    result = BrowserDeepBridge._prepare_page_data(browser, {"text_excerpt": "x" * 8000})
    assert len(result["text_excerpt"]) == 6000
    browser.send_command.assert_not_called()


def test_memory_summary_is_clean_and_bounded(tmp_path):
    browser = object.__new__(BrowserDeepBridge)
    browser.db_path = str(tmp_path / "web.db")
    browser.vsa = MagicMock()
    browser.vsa.encode_compositional.return_value = np.ones(8, dtype=np.complex64)
    browser._init_db()
    browser.memorize_in_hyperdimension("query", {"text_excerpt": "texto " * 1000}, "<p>" + "resumo " * 1000 + "</p>")
    with sqlite3.connect(browser.db_path) as conn:
        summary = conn.execute("SELECT summary_text FROM hd_web_memory").fetchone()[0]
    assert len(summary) <= 6000 and "<p>" not in summary


def test_extension_syntax_and_semantic_extraction_in_node():
    node = shutil.which("node") or str(Path(__file__).resolve().parents[1] / "node.exe")
    source = Path(__file__).resolve().parents[1] / "EXTENSAO_NAVEGADOR" / "background.js"
    syntax = subprocess.run([node, "--check", str(source)], capture_output=True, text=True, timeout=10)
    assert syntax.returncode == 0, syntax.stderr
    script = r'''
const fs = require('fs');
const code = fs.readFileSync(process.argv[1], 'utf8');
const fn = code.match(/function domInspectorAndActuator[\s\S]*?\n\}/)[0];
global.window = {devicePixelRatio:1, outerWidth:800, innerWidth:800, outerHeight:600, innerHeight:600};
global.location = {href:'https://example.test/article', hostname:'example.test'};
function textNode(text, hidden=false) {
 return {innerText:text, querySelectorAll:()=>[], closest:()=>hidden ? true : null,
         cloneNode:()=>textNode(text, hidden)};
}
global.document = {title:'Artigo', body:{innerText:'MENU LIXO'},
 querySelector:()=>textNode('Conteudo principal '.repeat(1000)), querySelectorAll:()=>[]};
const result = (new Function('return '+fn))()({mode:'EXTRACT',max_chars:9000});
if(result.text_excerpt.length > 6000 || !result.text_excerpt.startsWith('Conteudo principal')) process.exit(2);
document.querySelector=()=>null;
document.querySelectorAll=(selector)=>selector==='h1, p' ? [
 textNode('Paragrafo limpo'), textNode('MENU LIXO', true)] : [];
const fallback = (new Function('return '+fn))()({mode:'EXTRACT'});
if(fallback.text_excerpt !== 'Paragrafo limpo') process.exit(3);
'''
    result = subprocess.run([node, "-e", script, str(source)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
