# ==============================================================================
# BRAINNET v7 - SISTEMA OPERACIONAL COGNITIVO
# MODULO: audio_ear.py
# FUNCAO: Captura de Voz Estavel com Tolerancia Natural de Fala (Sem Cortes).
# ==============================================================================

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("BRAINNET_Audio")


class AudioEar:
    """Ouvido com temporizador estendido para capturar frases completas."""

    def __init__(self, on_speech_detected: Optional[Callable[[str], None]] = None) -> None:
        self.on_speech_detected = on_speech_detected
        self.is_listening = False
        self._thread: Optional[threading.Thread] = None

    def start_listening(self) -> bool:
        if self.is_listening:
            return True
        self.is_listening = True
        self._thread = threading.Thread(target=self._listen_worker, daemon=True)
        self._thread.start()
        logger.info("Escuta do microfone ativada.")
        return True

    def stop_listening(self) -> bool:
        self.is_listening = False
        logger.info("Escuta do microfone desligada.")
        return True

    def _listen_worker(self) -> None:
        try:
            import speech_recognition as sr
            recognizer = sr.Recognizer()
            
            # Parametros de tolerancia para nao cortar frases longas
            recognizer.energy_threshold = 200
            recognizer.dynamic_energy_threshold = False  # Limiar fixo estavel
            recognizer.pause_threshold = 1.4             # Espera 1.4s de silencio antes de cortar a frase
            recognizer.non_speaking_duration = 0.6

            # Conecta no microfone padrao do Windows (o '2- High Definition' do seu print)
            with sr.Microphone() as source:
                logger.info("Microfone pronto para gravacao continua.")

                while self.is_listening:
                    try:
                        # Ouve frases de ate 15 segundos sem interrupcao
                        audio = recognizer.listen(source, timeout=3.0, phrase_time_limit=15.0)
                        texto = recognizer.recognize_google(audio, language="pt-BR")
                        if texto and self.on_speech_detected:
                            logger.info(f"Frase completa capturada: '{texto}'")
                            self.on_speech_detected(texto)
                    except sr.WaitTimeoutError:
                        continue
                    except sr.UnknownValueError:
                        continue
                    except Exception as e:
                        logger.debug(f"Ciclo de audio: {e}")

        except ImportError:
            while self.is_listening:
                time.sleep(1.0)