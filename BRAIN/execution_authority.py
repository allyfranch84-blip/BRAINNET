"""Execution provenance and revocable authorization shared across async actions."""
from contextlib import contextmanager
import asyncio
from contextvars import ContextVar
from functools import wraps
import inspect
import logging
import threading

_background = ContextVar("brainnet_background", default=False)
_authorization = ContextVar("brainnet_authorization", default=None)
_command_token = ContextVar("brainnet_command_token", default=None)
_commands = set()
_commands_lock = threading.Lock()
logger = logging.getLogger("BRAINNET_Authority")


def current_authorization():
    return _authorization.get()


def revoke_all_commands():
    with _commands_lock:
        tokens = list(_commands)
        for token in tokens:
            token.set()
        return tokens


def current_command_token():
    return _command_token.get()


def command_authority(function):
    @wraps(function)
    def execute(*args, **kwargs):
        if _background.get():
            raise PermissionError("BLOQUEIO_DE_SEGURANCA: comando em background")
        if current_authorization() is not None:
            require_action_allowed("EXECUTE")
            return function(*args, **kwargs)
        token = threading.Event()
        with _commands_lock:
            _commands.add(token)
        marker = _command_token.set(token)
        try:
            with authorization_scope(token):
                return function(*args, **kwargs)
        finally:
            was_revoked = token.is_set()
            token.set()
            from owned_processes import release_processes
            if not was_revoked:
                release_processes(token)
            _command_token.reset(marker)
            with _commands_lock:
                _commands.discard(token)
    return execute


def require_action_allowed(action, is_background=False):
    if str(action).upper() in ("READ", "INSPECT", "CAPTURE_SCREEN", "EMERGENCY_STOP"):
        return
    if is_background or _background.get():
        message = "BLOQUEIO_DE_SEGURANCA: Ação de escrita em background"
        logger.error("%s: %s", message, action)
        raise PermissionError(message)
    token = _authorization.get()
    if not isinstance(token, threading.Event):
        logger.error("BLOQUEIO_DE_SEGURANCA: Nenhuma autorização ativa para: %s", action)
        raise PermissionError("BLOQUEIO_DE_SEGURANCA: Nenhuma autorização ativa")
    if token.is_set():
        logger.error("BLOQUEIO_DE_SEGURANCA: Autorizacao revogada: %s", action)
        raise PermissionError("BLOQUEIO_DE_SEGURANCA: Autorizacao revogada")


@contextmanager
def authorization_scope(token):
    marker = _authorization.set(token)
    try:
        yield
    finally:
        _authorization.reset(marker)


def background_only(function):
    if inspect.iscoroutinefunction(function):
        @wraps(function)
        async def asynchronous(*args, **kwargs):
            marker = _background.set(True)
            try:
                return await function(*args, **kwargs)
            finally:
                _background.reset(marker)
        return asynchronous
    @wraps(function)
    def synchronous(*args, **kwargs):
        marker = _background.set(True)
        try:
            return function(*args, **kwargs)
        finally:
            _background.reset(marker)
    return synchronous


def authorized_trajectory(function):
    @wraps(function)
    async def execute(*args, **kwargs):
        inherited = current_authorization()
        supplied = kwargs.get("authorization_token")
        token = supplied if supplied is not None else inherited
        if not isinstance(token, threading.Event):
            raise PermissionError("BLOQUEIO_DE_SEGURANCA: Nenhuma autorização ativa valida")
        owns_token = supplied is not None and supplied is not inherited
        with authorization_scope(token):
            try:
                require_action_allowed("EXECUTE", kwargs.get("is_background", False))
                return await function(*args, **kwargs)
            except asyncio.CancelledError:
                # Cancellation invalidates the entire command, including queued work.
                token.set()
                raise
            finally:
                if owns_token:
                    token.set()
    return execute


def clear_after_command(function):
    @wraps(function)
    def execute(self, *args, **kwargs):
        require_action_allowed("EXECUTE")
        try:
            return function(self, *args, **kwargs)
        finally:
            self._clear_pending_actions()
    return execute

@contextmanager
def sovereign_idle_scope(idle_threshold_sec: float = 300.0):
    """Autoriza escrita em background APENAS se o usuário estiver ausente.
    Garante a Lâmina 4: a IA só toma a tela se o humano não estiver nela."""
    import ctypes
    from ctypes import wintypes
    
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
        raise PermissionError("Falha ao checar ociosidade do Windows.")
        
    idle_ms = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
    if idle_ms < idle_threshold_sec * 1000:
        raise PermissionError(
            f"BLOQUEIO_DE_SEGURANCA: Ação de escrita em background bloqueada. "
            f"O usuário está ativo (idle: {idle_ms/1000:.1f}s)."
        )
        
    token = threading.Event()
    bg_marker = _background.set(False)  # Desativa o bloqueio de background temporariamente
    try:
        with authorization_scope(token):
            yield token
    finally:
        token.set()
        _background.reset(bg_marker)
