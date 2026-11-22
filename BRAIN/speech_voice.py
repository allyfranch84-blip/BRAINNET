# ==============================================================================
# BRAINNET v7 - SISTEMA OPERACIONAL COGNITIVO
# MODULO: speech_voice.py
# FUNCAO: Sintese de Voz Neural Humana em Portugues (pt-BR-FranciscaNeural)
#         com Tratamento de Buffer, Respeito a Sentencas e Fila Assincrona.
# ==============================================================================

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
from typing import Optional

logger = logging.getLogger("BRAINNET_Voice")

VOZ_NEURAL_PADRAO = "pt-BR-FranciscaNeural"  # Alternativa masculina: "pt-BR-AntonioNeural"

PASTA_LOCAL = Path(__file__).resolve().parent / "temp_media"
try:
    PASTA_LOCAL.mkdir(parents=True, exist_ok=True)
    PASTA_TEMP = PASTA_LOCAL
except PermissionError:
    PASTA_TEMP = Path(tempfile.gettempdir()) / "brainnet_media"
    PASTA_TEMP.mkdir(parents=True, exist_ok=True)


class SpeechVoiceEngine:
    """Motor de Sintese de Voz Neural Humana com reproducao assincrona resiliente."""

    def __init__(self, voice_name: str = VOZ_NEURAL_PADRAO) -> None:
        self.voice_name = voice_name
        self._fila_audio: queue.Queue[tuple[int, Path]] = queue.Queue()
        self._lock_audio = threading.RLock()
        self._audio_generation = 0
        self._ativo = True
        self._pygame_iniciado = False
        self._lock_sintese = threading.Lock()
        self._thread = threading.Thread(target=self._loop_player, daemon=True)
        self._thread.start()

    @staticmethod
    def _limpar_texto(texto: str, max_chars: int = 1600) -> str:
        """
        Higieniza texto para TTS. Se exceder max_chars, corta estritamente
        na ultima fronteira de sentenca (. ! ?), nunca decepando palavras.
        """
        if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars < 1:
            raise ValueError("max_chars deve ser inteiro positivo")
        t = re.sub(r"[\*\_#`]", "", str(texto or ""))
        t = re.sub(r"https?://\S+", "link", t)
        # Preserva caracteres acentuados, numeros, pontuacao basica e simbolos comuns
        t = re.sub(r"[^\w\s\.,;:!\?\-áàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ0-9%]", "", t)
        t = " ".join(t.split()).strip()

        if not t:
            return ""

        if len(t) <= max_chars:
            return t

        corte = t[:max_chars]
        ultimo_ponto = max(corte.rfind("."), corte.rfind("!"), corte.rfind("?"))
        if ultimo_ponto > int(max_chars * 0.4):
            return corte[: ultimo_ponto + 1].strip()

        ultimo_espaco = corte.rfind(" ")
        if ultimo_espaco > 0:
            return corte[:ultimo_espaco].strip() + "."

        return corte[:max_chars - 1].rstrip() + "." if max_chars > 1 else corte

    @staticmethod
    def resumir_para_voz(texto: str, max_chars: int = 320) -> str:
        paragraph = re.split(r"\n\s*\n", str(texto or "").strip(), maxsplit=1)[0]
        paragraph = re.sub(r"[\*\_#`]", "", paragraph)
        sentence = re.split(r"(?<=[.!?])\s+", paragraph, maxsplit=1)[0]
        return SpeechVoiceEngine._limpar_texto(sentence, max_chars=max_chars)

    def _sintetizar_edge_neural(self, texto: str, out_file: Path) -> bool:
        """Gera o audio neural via edge-tts em event loop isolado."""
        try:
            import edge_tts

            async def _coro() -> None:
                comunicador = edge_tts.Communicate(texto, self.voice_name)
                await comunicador.save(str(out_file))

            # Cria e registra loop exclusivo na thread para permitir comunicacao aiohttp
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                new_loop.run_until_complete(_coro())
            finally:
                new_loop.close()

            return out_file.is_file() and out_file.stat().st_size > 100
        except Exception as e:
            logger.error(f"[VOZ NEURAL]: Edge-TTS falhou: {e}")
            return False

    def _sintetizar_powershell_fallback(self, texto: str, out_wav: Path) -> bool:
        """Fallback local sem conexao via SAPI do Windows."""
        texto_escapado = texto.replace('"', '`"').replace("'", "''")
        ps_script = f"""
        Add-Type -AssemblyName System.Speech;
        $synthesizer = New-Object System.Speech.Synthesis.SpeechSynthesizer;
        $synthesizer.SetOutputToWaveFile('{str(out_wav)}');
        $synthesizer.Speak('{texto_escapado}');
        $synthesizer.Dispose();
        """
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                timeout=8,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return out_wav.is_file() and out_wav.stat().st_size > 44
        except Exception:
            return False

    def falar(self, texto: str, max_chars: int = 1600) -> bool:
        """Higieniza, filtra código/markdown, sintetiza e enfileira para reproducao."""
        if isinstance(max_chars, bool) or not isinstance(max_chars, int) or not 1 <= max_chars <= 10000:
            raise ValueError("max_chars deve ser inteiro entre 1 e 10000")
        with self._lock_audio:
            generation = self._audio_generation
        t_raw = str(texto or "").strip()
        
        # BLOQUEIO RESTRITO A CÓDIGO FONTE REAL: Permite descrições de tela longas
        sintaxe_codigo = ["```python", "def ", "class ", "import ", "Traceback (most recent", "File \""]
        if max_chars > 1600:
            t_limpo = self._limpar_texto(t_raw, max_chars=max_chars)
        elif any(marker in t_raw for marker in sintaxe_codigo) or ("{" in t_raw and "}" in t_raw and ":" in t_raw and len(t_raw) > 120):
            t_limpo = self._limpar_texto("A resposta contém código. Consulte o texto na interface.", max_chars=max_chars)
        else:
            t_limpo = self._limpar_texto(self.resumir_para_voz(t_raw), max_chars=max_chars)

        if not t_limpo:
            return False

        with self._lock_sintese:
            with self._lock_audio:
                if generation != self._audio_generation:
                    return False
            out_file = PASTA_TEMP / f"fala_{int(time.time()*1000)}.mp3"

            # 1. Prioridade: Edge-TTS Neural pt-BR
            sucesso = self._sintetizar_edge_neural(t_limpo, out_file)

            # 2. Contingencia offline: SAPI PowerShell
            if not sucesso:
                out_file = PASTA_TEMP / f"fala_{int(time.time()*1000)}.wav"
                sucesso = self._sintetizar_powershell_fallback(t_limpo, out_file)

            if sucesso:
                with self._lock_audio:
                    if generation == self._audio_generation:
                        self._fila_audio.put((generation, out_file))
                        return True
                out_file.unlink(missing_ok=True)

        return False

    def parar(self) -> None:
        """Esvazia a fila pendente e interrompe a reproducao atual."""
        with self._lock_audio:
            self._audio_generation += 1
            while True:
                try:
                    _, path = self._fila_audio.get_nowait()
                except queue.Empty:
                    break
                try:
                    Path(path).unlink(missing_ok=True)
                except OSError:
                    logger.exception("Falha ao remover audio cancelado")
                finally:
                    self._fila_audio.task_done()
            if self._pygame_iniciado:
                try:
                    import pygame
                    if pygame.mixer.get_init():
                        pygame.mixer.music.stop()
                        pygame.mixer.stop()
                        pygame.mixer.music.unload()
                except Exception:
                    logger.exception("Falha ao interromper mixer de voz")

    def _loop_player(self) -> None:
        """Player isolado: 24kHz nativo do Edge-TTS e drenagem de buffer."""
        while self._ativo:
            try:
                generation, audio_path = self._fila_audio.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                import pygame

                with self._lock_audio:
                    if generation != self._audio_generation:
                        continue
                    if not self._pygame_iniciado:
                        try:
                            # Edge-TTS produz MP3 a 24000Hz mono. Evita truncamento e estalos.
                            pygame.mixer.init(frequency=24000, size=-16, channels=2, buffer=2048)
                        except Exception:
                            pygame.mixer.init()
                        self._pygame_iniciado = True
                    pygame.mixer.music.load(str(audio_path))
                    pygame.mixer.music.play()

                while self._ativo:
                    with self._lock_audio:
                        if generation != self._audio_generation or not pygame.mixer.music.get_busy():
                            break
                    time.sleep(0.03)

                # Drenagem essencial: impede corte da ultima silaba no Windows
                time.sleep(0.18)
                with self._lock_audio:
                    if generation == self._audio_generation:
                        pygame.mixer.music.unload()

            except Exception as e:
                logger.error(f"Erro no player de voz: {e}")
            finally:
                try:
                    Path(audio_path).unlink(missing_ok=True)
                except OSError:
                    logger.exception("Falha ao remover audio reproduzido")
                finally:
                    self._fila_audio.task_done()
