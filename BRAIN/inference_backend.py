"""Backend de inferencia local opt-in. Importar nao inicia processos nem modelos."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
import ipaddress
import json
import logging
import math
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
from typing import Iterator, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import uuid

logger = logging.getLogger("BRAINNET_Inference")


class InferenceError(Exception):
    code = "INFERENCE_ERROR"

    def __init__(self, message: str, request_id: str = ""):
        super().__init__(message)
        self.request_id = request_id


class ConfigurationError(InferenceError): code = "CONFIGURATION_ERROR"
class BackendUnavailable(InferenceError): code = "BACKEND_UNAVAILABLE"
class ModelUnavailable(InferenceError): code = "MODEL_UNAVAILABLE"
class InferenceTimeout(InferenceError): code = "TIMEOUT"
class InferenceCancelled(InferenceError): code = "CANCELLED"
class ProcessFailed(InferenceError): code = "PROCESS_FAILED"
class InvalidResponse(InferenceError): code = "INVALID_RESPONSE"
class UnsupportedOperation(InferenceError): code = "UNSUPPORTED_OPERATION"


@dataclass(frozen=True)
class InferenceRequest:
    prompt: str = ""
    model: Optional[str] = None
    messages: Optional[list] = None
    timeout: float = 60.0
    request_id: Optional[str] = None
    max_tokens: int = 256
    context_tokens: Optional[int] = None
    json_output: bool = False


@dataclass(frozen=True)
class InferenceResult:
    request_id: str
    model: str
    text: str
    backend: str
    output_tokens: Optional[int] = None
    input_tokens: Optional[int] = None
    finish_reason: Optional[str] = None


def validate_model_artifacts(model_path: str, projector_path: Optional[str] = None,
                             chat_template_path: Optional[str] = None, *,
                             require_vision: bool = False, require_template: bool = False,
                             expected_model_sha256: Optional[str] = None):
    """Confere arquivos separadamente; nao afirma compatibilidade de arquitetura."""
    def check_gguf(value, label, required):
        if not value:
            if required: raise ConfigurationError(f"{label} nao configurado")
            return None
        path = Path(value)
        if not path.is_file(): raise ModelUnavailable(f"{label} nao encontrado")
        try:
            with path.open("rb") as source:
                if source.read(4) != b"GGUF": raise ConfigurationError(f"{label} nao possui assinatura GGUF")
        except OSError as exc:
            raise ConfigurationError(f"Nao foi possivel ler {label}") from exc
        return str(path)
    model = check_gguf(model_path, "modelo", True)
    if expected_model_sha256 is not None:
        import hashlib
        import hmac
        import re
        if not isinstance(expected_model_sha256, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', expected_model_sha256):
            raise ConfigurationError('SHA-256 do modelo invalido')
        digest = hashlib.sha256()
        try:
            with open(model, 'rb') as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    digest.update(chunk)
        except OSError as exc:
            raise ConfigurationError('Nao foi possivel verificar SHA-256 do modelo') from exc
        if not hmac.compare_digest(digest.hexdigest(), expected_model_sha256.lower()):
            raise ConfigurationError('SHA-256 do modelo nao confere')
    projector = check_gguf(projector_path, "projetor", require_vision)
    template = None
    if chat_template_path:
        try:
            template = Path(chat_template_path).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ConfigurationError("Template de chat indisponivel") from exc
        if not template.strip(): raise ConfigurationError("Template de chat vazio")
    elif require_template:
        raise ConfigurationError("Template de chat nao configurado")
    return {"model": model, "projector": projector, "template_present": template is not None,
            "compatibility_verified": False}


class InferenceBackend(ABC):
    @abstractmethod
    def generate(self, request: InferenceRequest) -> InferenceResult: ...
    @abstractmethod
    def chat(self, request: InferenceRequest) -> InferenceResult: ...
    @abstractmethod
    def stream(self, request: InferenceRequest, *, chat: bool = False) -> Iterator[str]: ...
    @abstractmethod
    def health_check(self) -> bool: ...
    @abstractmethod
    def cancel(self, request_id: str) -> bool: ...
    def embed(self, request: InferenceRequest):
        raise UnsupportedOperation("Embeddings nao implementados neste adaptador", request.request_id or "")
    def vision(self, request: InferenceRequest):
        raise UnsupportedOperation("Visao multimodal nao implementada neste adaptador", request.request_id or "")


def _local_endpoint(endpoint: str) -> str:
    try:
        u = urlsplit(endpoint)
        host = u.hostname
        port = u.port
    except ValueError as exc:
        raise ConfigurationError("Endpoint invalido") from exc
    if u.scheme != "http" or not host or u.username or u.password or u.query or u.fragment or u.path not in ("", "/"):
        raise ConfigurationError("Endpoint deve ser URL HTTP local, sem caminho ou credenciais")
    if host.lower() != "localhost":
        try:
            if not ipaddress.ip_address(host).is_loopback:
                raise ConfigurationError("Endpoint deve usar loopback")
        except ValueError as exc:
            raise ConfigurationError("Endpoint deve usar localhost ou IP loopback") from exc
    if port is not None and not 1 <= port <= 65535:
        raise ConfigurationError("Porta invalida")
    return endpoint.rstrip("/")


class HTTPInferenceBackend(InferenceBackend):
    def __init__(self, endpoint: str, model: Optional[str], kind: str, *, opener=urlopen, supervisor=None):
        self.endpoint = _local_endpoint(endpoint)
        self.model = model
        self.kind = kind
        self._opener = opener
        self.supervisor = supervisor
        self._lock = threading.Lock()
        self._requests = {}

    def _check(self, rid, cancel, deadline):
        if cancel.is_set():
            logger.info("inference request_id=%s outcome=cancelled", rid)
            raise InferenceCancelled("Inferencia cancelada", rid)
        if self.supervisor is not None:
            self.supervisor.raise_if_failed(rid)
        if time.monotonic() >= deadline:
            logger.warning("inference request_id=%s outcome=timeout", rid)
            raise InferenceTimeout("Prazo de inferencia excedido", rid)

    def _http_error(self, exc, rid):
        if self.supervisor is not None:
            self.supervisor.raise_if_failed(rid)
        if isinstance(exc, HTTPError):
            try:
                detail = exc.read(4096).decode("utf-8", errors="replace").casefold()
            except (OSError, AttributeError, TypeError):
                detail = ""
            if exc.code in (400, 404) and "model" in detail and any(word in detail for word in ("not found", "unknown", "not available", "does not exist")):
                raise ModelUnavailable("Modelo solicitado indisponivel", rid) from exc
            raise BackendUnavailable(f"Backend retornou HTTP {exc.code}", rid) from exc
        cause = getattr(exc, "reason", exc)
        if isinstance(cause, (TimeoutError, socket.timeout)):
            logger.warning("inference request_id=%s outcome=http_timeout", rid)
            raise InferenceTimeout("Tempo limite de conexao ou leitura excedido", rid) from exc
        logger.warning("inference request_id=%s outcome=backend_unavailable", rid)
        raise BackendUnavailable(f"Falha de conexao com backend: {cause}", rid) from exc

    def health_check(self) -> bool:
        if self.supervisor is not None:
            self.supervisor.raise_if_failed("")
        path = "/api/version" if self.kind == "ollama" else "/health"
        try:
            with self._opener(Request(self.endpoint + path), timeout=2) as response:
                return response.status == 200
        except (OSError, HTTPError, URLError) as exc:
            self._http_error(exc, "")

    def cancel(self, request_id: str) -> bool:
        with self._lock:
            state = self._requests.get(request_id)
            if state is None:
                return False
            state.set()
            return True

    def _payload(self, request, chat, stream):
        model = request.model or self.model
        if not model:
            raise ConfigurationError("Configure o modelo antes da inferencia", request.request_id or "")
        if self.kind == "llamacpp" and self.model and request.model and request.model != self.model:
            raise ModelUnavailable("Este adaptador esta vinculado a outro modelo", request.request_id or "")
        if self.kind == "ollama":
            path = "/api/chat" if chat else "/api/generate"
            body = {"model": model, "stream": stream, "options": {"num_predict": request.max_tokens}}
            if request.context_tokens is not None:
                if isinstance(request.context_tokens, bool) or not isinstance(request.context_tokens, int) or request.context_tokens <= 0:
                    raise ConfigurationError("Contexto invalido")
                body['options']['num_ctx'] = request.context_tokens
            if request.json_output:
                body["format"] = "json"
                body["options"]["temperature"] = 0
            body.update({"messages": request.messages} if chat else {"prompt": request.prompt})
        else:
            path = "/v1/chat/completions" if chat else "/completion"
            body = {"stream": stream, "n_predict": request.max_tokens}
            if chat:
                body = {"model": model, "messages": request.messages, "stream": stream, "max_tokens": request.max_tokens}
                if request.json_output:
                    body["response_format"] = {"type": "json_object"}
                    body["temperature"] = 0
            else:
                body["prompt"] = request.prompt
        if chat and (not isinstance(request.messages, list) or not request.messages):
            raise ConfigurationError("Chat exige lista nao vazia de mensagens", request.request_id or "")
        return path, body, model

    def _run(self, request, chat, streaming, structured=False):
        if (not isinstance(request, InferenceRequest) or isinstance(request.timeout, bool)
            or not isinstance(request.timeout, (int, float)) or not math.isfinite(request.timeout) or request.timeout <= 0
            or isinstance(request.max_tokens, bool) or not isinstance(request.max_tokens, int) or request.max_tokens < 1):
            raise ConfigurationError("Solicitacao ou timeout invalido")
        rid = request.request_id or uuid.uuid4().hex
        path, body, model = self._payload(request, chat, streaming)
        event = threading.Event()
        with self._lock:
            if rid in self._requests:
                raise ConfigurationError("request_id ja esta em uso", rid)
            self._requests[rid] = event
        deadline = time.monotonic() + request.timeout
        try:
            self._check(rid, event, deadline)
            req = Request(self.endpoint + path, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
            try:
                with self._opener(req, timeout=request.timeout) as response:
                    if streaming:
                        done = False
                        terminal = {}
                        while True:
                            self._check(rid, event, deadline)
                            line = response.readline()
                            self._check(rid, event, deadline)
                            if not line:
                                break
                            line = line.decode("utf-8").strip()
                            if not line or line.startswith(":"):
                                continue
                            if line.startswith("data:"):
                                line = line[5:].strip()
                            if line == "[DONE]":
                                done = True
                                break
                            try:
                                data = json.loads(line)
                            except (ValueError, UnicodeError) as exc:
                                raise InvalidResponse("Fragmento de streaming invalido", rid) from exc
                            thinking = ''
                            if self.kind == "ollama":
                                text = data.get("message", {}).get("content", "") if chat else data.get("response", "")
                                thinking = data.get("message", {}).get("thinking", "") if chat else data.get('thinking', '')
                                done = data.get("done") is True
                            elif chat:
                                delta = data.get("choices", [{}])[0].get("delta", {})
                                text = delta.get("content") or ""
                                thinking = delta.get("reasoning_content") or ""
                                done = bool(data.get("choices", [{}])[0].get("finish_reason"))
                            else:
                                text = data.get("content", "")
                                done = data.get("stop") is True
                            if thinking and structured:
                                if not isinstance(thinking, str): raise InvalidResponse("Fragmento de pensamento invalido", rid)
                                yield {'channel':'THINKING','text':thinking}
                            if text:
                                if not isinstance(text, str): raise InvalidResponse("Fragmento nao textual", rid)
                                yield {'channel':'CONTENT','text':text} if structured else text
                            if done:
                                terminal = {'finish_reason': data.get('done_reason') if self.kind == 'ollama' else
                                            (data.get('choices', [{}])[0].get('finish_reason') if chat else data.get('stop_type')),
                                            'output_tokens': data.get('eval_count') if self.kind == 'ollama' else None}
                                break
                        if not done:
                            raise InvalidResponse("Streaming terminou sem marcador de conclusao", rid)
                        if structured: yield {'channel':'OPERATIONAL','state':'COMPLETED','text':'',**terminal}
                    else:
                        self._check(rid, event, deadline)
                        try:
                            data = json.loads(response.read().decode("utf-8"))
                        except (ValueError, UnicodeError) as exc:
                            raise InvalidResponse("Resposta JSON invalida", rid) from exc
                        self._check(rid, event, deadline)
                        if self.kind == "ollama":
                            if data.get("done") is not True: raise InvalidResponse("Resposta incompleta", rid)
                            text = data.get("message", {}).get("content") if chat else data.get("response")
                        elif chat:
                            try: text = data["choices"][0]["message"]["content"]
                            except (KeyError, IndexError, TypeError) as exc: raise InvalidResponse("Resposta de chat invalida", rid) from exc
                        else: text = data.get("content")
                        if not isinstance(text, str): raise InvalidResponse("Resposta textual ausente", rid)
                        def count(value):
                            return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
                        usage = data.get('usage') if isinstance(data.get('usage'), dict) else {}
                        output_tokens = count(data.get('eval_count') if self.kind == 'ollama' else usage.get('completion_tokens'))
                        input_tokens = count(data.get('prompt_eval_count') if self.kind == 'ollama' else usage.get('prompt_tokens'))
                        reason = data.get('done_reason') if self.kind == 'ollama' else (data.get('choices', [{}])[0].get('finish_reason') if chat else data.get('stop_type'))
                        yield InferenceResult(rid, model, text, self.kind, output_tokens, input_tokens, reason if isinstance(reason, str) else None)
            except (HTTPError, URLError, OSError) as exc:
                self._check(rid, event, deadline)
                self._http_error(exc, rid)
        finally:
            with self._lock:
                self._requests.pop(rid, None)

    def generate(self, request): return next(self._run(request, False, False))
    def chat(self, request): return next(self._run(request, True, False))
    def stream(self, request, *, chat=False): return self._run(request, chat, True)
    def stream_events(self, request, *, chat=False): return self._run(request, chat, True, True)


class LlamaProcessManager:
    """Supervisao opt-in; reinicio e sempre solicitado explicitamente."""
    def __init__(self, executable: Optional[str], gguf: Optional[str], endpoint="http://127.0.0.1:8080",
                 device="cpu", max_starts=2, recovery_interval=2.0, version=None, context_size=2048,
                 gpu_layers=None, concurrency=None, load_mode=None, device_name="Vulkan0", *, expected_model_sha256=None,
                 popen=subprocess.Popen, probe=None, port_probe=None, clock=time.monotonic):
        self.endpoint = _local_endpoint(endpoint)
        port = urlsplit(self.endpoint).port
        if port is None or port in (11434, 11435):
            raise ConfigurationError("llama-server exige porta propria, diferente de 11434 e 11435")
        if (isinstance(max_starts, bool) or not isinstance(max_starts, int) or max_starts < 1
            or isinstance(recovery_interval, bool) or not isinstance(recovery_interval, (int, float))
            or not math.isfinite(recovery_interval) or recovery_interval < 0):
            raise ConfigurationError("Politica de recuperacao invalida")
        if isinstance(context_size, bool) or not isinstance(context_size, int) or context_size < 1:
            raise ConfigurationError("context_size deve ser inteiro positivo")
        if gpu_layers is not None and (isinstance(gpu_layers, bool) or not isinstance(gpu_layers, int) or gpu_layers < 0):
            raise ConfigurationError("gpu_layers deve ser inteiro nao negativo")
        if device == 'cpu' and gpu_layers not in (None, 0):
            raise ConfigurationError("CPU nao aceita camadas GPU")
        if concurrency is not None and (isinstance(concurrency, bool) or not isinstance(concurrency, int) or concurrency < 1):
            raise ConfigurationError("concurrency deve ser inteiro positivo")
        if load_mode not in (None, 'auto', 'none', 'mmap', 'mlock', 'mmap+mlock', 'dio'):
            raise ConfigurationError("load_mode invalido")
        if not isinstance(device_name, str) or not __import__('re').fullmatch(r'Vulkan[0-9]+', device_name):
            raise ConfigurationError("dispositivo Vulkan invalido")
        self.executable, self.gguf, self.device, self.version = executable, gguf, device, version
        self.expected_model_sha256 = expected_model_sha256
        self.context_size = context_size
        self.gpu_layers, self.concurrency, self.load_mode, self.device_name = gpu_layers, concurrency, load_mode, device_name
        self.max_starts, self.recovery_interval = max_starts, float(recovery_interval)
        self._starts, self._process = 0, None
        self._popen, self._probe, self._port_probe, self._clock = popen, probe, port_probe, clock
        self._recent, self._events = deque(maxlen=100), deque(maxlen=100)
        self._lock = threading.Lock()
        self._last_failure_at = None
        self._last_seen_process = None
        self._state = "stopped"
        self._start_time = None
        self._last_exit = None
        self._reason = None
        self._pid = None

    def _record(self, event, reason=None):
        self._events.append({"event": event, "backend": "llamacpp", "pid": self._pid,
            "model": self.gguf, "version": self.version, "device": self.device,
            "start_time": self._start_time, "timestamp": time.time(),
            "exit_code": self._last_exit, "reason": reason})
        logger.info("backend=llamacpp event=%s pid=%s model=%s version=%s device=%s start_time=%s exit_code=%s reason=%s",
                    event, self._pid, self.gguf, self.version, self.device, self._start_time, self._last_exit, reason)

    def _observe_exit(self):
        p = self._process
        if p is None:
            return
        code = p.poll()
        if code is not None and p is not self._last_seen_process:
            self._last_seen_process = p
            self._last_exit = code
            self._last_failure_at = self._clock()
            self._state = "degraded" if self._starts >= self.max_starts else "crashed"
            evidence = "\n".join(self._recent).casefold()
            self._reason = ("vulkan_error_reported" if self.device == "vulkan"
                            and "vulkan" in evidence and ("error" in evidence or "failed" in evidence)
                            else "unexpected_exit")
            self._record("process_exit", self._reason)
            self._record("PROCESS_FAILED", self._reason)

    def _drain(self, pipe):
        if pipe:
            for line in pipe:
                self._recent.append(line.rstrip()[:2000])

    def _occupied(self, host, port):
        if self._port_probe is not None:
            return bool(self._port_probe(host, port))
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except (OSError, TimeoutError):
            return False

    def status(self):
        with self._lock:
            self._observe_exit()
            return {"state": self._state, "pid": self._pid, "model": self.gguf,
                    "backend": "llamacpp", "version": self.version, "device": self.device,
                    "start_time": self._start_time, "exit_code": self._last_exit,
                    "reason": self._reason, "starts": self._starts, "events": list(self._events)}

    def start(self):
        with self._lock:
            self._observe_exit()
            if self._process is not None and self._process.poll() is None:
                return "owned"
            if self._probe is not None:
                available = self._probe()
            else:
                try:
                    with urlopen(Request(self.endpoint + "/health"), timeout=2) as response:
                        available = response.status == 200
                except (HTTPError, URLError, OSError):
                    available = False
            if available:
                self._process = None
                self._state, self._reason = "external", "external_server"
                self._record("external_server", self._reason)
                return "external"
            u = urlsplit(self.endpoint)
            if self._occupied(u.hostname, u.port):
                self._state, self._reason = "blocked", "port_occupied"
                self._record("start_blocked", self._reason)
                raise BackendUnavailable("Porta ocupada por processo externo; nenhum processo foi encerrado")
            if self._starts >= self.max_starts:
                self._state, self._reason = "degraded", "restart_limit"
                self._record("degraded", self._reason)
                raise ProcessFailed("Limite de inicializacoes do llama-server atingido")
            if self._last_failure_at is not None and self._clock() - self._last_failure_at < self.recovery_interval:
                self._state, self._reason = "recovery_wait", "recovery_interval"
                self._record("start_deferred", self._reason)
                raise ProcessFailed("Intervalo de recuperacao ainda nao terminou")
            if not self.executable or not Path(self.executable).is_file():
                raise ConfigurationError("Executavel llama-server nao configurado ou nao encontrado")
            install_root = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama"
            if Path(self.executable).resolve().is_relative_to(install_root.resolve()):
                raise ConfigurationError("Use um llama-server independente da instalacao do Ollama")
            if not self.gguf or not Path(self.gguf).is_file():
                raise ModelUnavailable("Modelo GGUF nao configurado ou nao encontrado")
            if self.expected_model_sha256 is None:
                validate_model_artifacts(self.gguf)
            else:
                validate_model_artifacts(self.gguf, expected_model_sha256=self.expected_model_sha256)
            if self.device not in ("cpu", "vulkan"):
                raise ConfigurationError("device deve ser cpu ou vulkan")
            args = [self.executable, "--model", self.gguf, "--host", u.hostname, "--port", str(u.port),
                    "--ctx-size", str(self.context_size)]
            args += ["--device", "none", "--n-gpu-layers", "0"] if self.device == "cpu" else ["--device", self.device_name]
            if self.device == 'vulkan' and self.gpu_layers is not None:
                args += ['--n-gpu-layers', str(self.gpu_layers)]
            if self.concurrency is not None:
                args += ['--parallel', str(self.concurrency)]
            if self.load_mode is not None:
                try:
                    check = subprocess.run([self.executable, '--help'], capture_output=True, text=True,
                        errors='replace', timeout=10, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                except (OSError, subprocess.TimeoutExpired) as exc:
                    raise ConfigurationError('Nao foi possivel verificar --load-mode') from exc
                if check.returncode or '--load-mode' not in check.stdout or self.load_mode not in check.stdout:
                    raise ConfigurationError('Build nao confirma suporte ao load_mode solicitado')
                args += ['--load-mode', self.load_mode]
            try:
                self._process = self._popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                            errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except OSError as exc:
                self._state, self._reason = "start_failed", "spawn_failed"
                self._record("start_failed", self._reason)
                raise ConfigurationError(f"Nao foi possivel iniciar llama-server: {exc}") from exc
            self._starts += 1
            self._pid = getattr(self._process, "pid", None)
            self._start_time = time.time()
            self._last_exit, self._reason, self._state = None, None, "starting"
            self._record("started")
            threading.Thread(target=self._drain, args=(self._process.stdout,), daemon=True).start()
            return "started"

    def raise_if_failed(self, request_id=""):
        with self._lock:
            self._observe_exit()
            if self._process is not None and self._process.poll() is not None:
                raise ProcessFailed(f"llama-server encerrou com codigo {self._last_exit}", request_id)

    def recent_logs(self): return list(self._recent)

    def stop(self, timeout=5.0):
        with self._lock:
            p = self._process
            if p is None: return False
            if p.poll() is None:
                self._record("STOP_REQUESTED", "requested_shutdown")
                p.terminate()
                try: p.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait(timeout=timeout)
                self._last_exit = p.returncode
                self._state, self._reason = "stopped", "requested_shutdown"
                # terminate() on Windows uses TerminateProcess, never a cooperative exit.
                self._record("FORCED_TERMINATION", "terminate_api")
                self._record("stopped", self._reason)
            else:
                self._observe_exit()
            self._process = None
            return True


def create_backend(config=None):
    """Selecao explicita; padrao ollama mantem clientes existentes intactos."""
    config = dict(config or {})
    kind = config.get("backend", "ollama")
    if kind == "ollama":
        endpoint = config.get("endpoint") or os.getenv("OLLAMA_HOST", "127.0.0.1:11435")
        if not endpoint.startswith(("http://", "https://")): endpoint = "http://" + endpoint
        return HTTPInferenceBackend(endpoint, config.get("model"), "ollama")
    if kind == "llamacpp":
        endpoint = _local_endpoint(config.get("endpoint", "http://127.0.0.1:8080"))
        if urlsplit(endpoint).port in (None, 11434, 11435):
            raise ConfigurationError("llama-server exige porta propria, diferente de 11434 e 11435")
        return HTTPInferenceBackend(endpoint, config.get("model"), "llamacpp", supervisor=config.get("supervisor"))
    raise ConfigurationError("backend deve ser ollama ou llamacpp")
