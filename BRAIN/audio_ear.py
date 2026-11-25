"""Microphone lifecycle with revocable capture and explicit state."""
import logging
import threading

logger = logging.getLogger('BRAINNET_Audio')

class AudioEar:
    def __init__(self, on_speech_detected=None, on_state=None):
        self.on_speech_detected = on_speech_detected
        self.on_state = on_state
        self._lock = threading.RLock()
        self._thread = None
        self._stop = threading.Event()
        self._state = 'STOPPED'
        self._error = None
        self._revision = 0
        self.is_listening = False

    def status(self):
        with self._lock:
            return {'ok':True,'state':self._state,'active':self.is_listening,'error':self._error,'revision':self._revision}

    def _publish(self, state, error=None):
        with self._lock:
            self._state, self._error = state, error
            self.is_listening = state in ('STARTING','LISTENING')
            self._revision += 1
            result = self.status()
        if self.on_state:
            try: self.on_state(result)
            except Exception: logger.debug('Voice state notification failed', exc_info=True)
        return result

    def start_listening(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return self.is_listening
            self._stop = threading.Event()
            self._publish('STARTING')
            self._thread = threading.Thread(target=self._listen_worker, args=(self._stop,),daemon=True)
            self._thread.start()
            return True

    def stop_listening(self):
        with self._lock:
            self._stop.set()
            if self._thread and self._thread.is_alive():
                self._publish('STOPPING')
            else:
                self._publish('STOPPED')
            return True

    def _listen_worker(self, stop):
        failure = None
        try:
            import speech_recognition as sr
            recognizer = sr.Recognizer()
            recognizer.operation_timeout = 5
            recognizer.pause_threshold = 1.4
            recognizer.non_speaking_duration = .6
            with sr.Microphone() as source:
                with self._lock:
                    if stop.is_set(): return
                    self._publish('LISTENING')
                while not stop.is_set():
                    try:
                        audio = recognizer.listen(source, timeout=2, phrase_time_limit=12)
                        if stop.is_set(): break
                        text = recognizer.recognize_google(audio, language='pt-BR')
                        if text and not stop.is_set() and self.on_speech_detected:
                            if self.status()["error"]:
                                self._publish("LISTENING")
                            self.on_speech_detected(text)
                    except sr.WaitTimeoutError:
                        continue
                    except sr.UnknownValueError:
                        if not stop.is_set():
                            self._publish('LISTENING','Não compreendi o áudio. Repita ou digite.')
                    except sr.RequestError as exc:
                        failure = 'Serviço de reconhecimento indisponível'
                        logger.warning('%s: %s',failure,type(exc).__name__)
                        break
        except Exception as exc:
            failure = 'Microfone indisponível: ' + type(exc).__name__
            logger.warning('%s',failure)
        finally:
            with self._lock:
                self._publish('STOPPED' if stop.is_set() or not failure else 'ERROR', None if stop.is_set() else failure)
