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


# Experimental, in-memory approval; no model or chat endpoint can approve it.
from dataclasses import dataclass
import math
import time

@dataclass(frozen=True, slots=True)
class PhysicalMoveProposal:
    task_id: str
    proposal_id: str
    start: tuple
    target: tuple
    monitor: str
    monitor_rect: tuple
    tolerance: int
    deadline_monotonic: float
    max_distance: int = 10
    duration_ms: int = 0

@dataclass(frozen=True, slots=True)
class RelativePhysicalMoveProposal:
    task_id: str
    proposal_id: str
    dx: int
    dy: int
    monitor: str
    monitor_rect: tuple
    safe_rect: tuple
    lab_hwnd: int
    lab_pid: int
    tolerance: int
    deadline_monotonic: float

_physical_approvals_lock = threading.Lock()
_physical_consumed = set()

class PhysicalMoveApproval:
    """One explicitly approved proposal; each attempted use consumes it."""
    def __init__(self, proposal):
        if type(proposal) not in (PhysicalMoveProposal, RelativePhysicalMoveProposal):
            raise ValueError('Proposta específica obrigatória')
        self.proposal = proposal
        self._lock = threading.Lock()
        self._state = 'PENDING_APPROVAL'
    def approve_explicitly(self, proposal_id):
        with self._lock:
            if self._state != 'PENDING_APPROVAL' or proposal_id != self.proposal.proposal_id or time.monotonic() >= self.proposal.deadline_monotonic:
                return False
            self._state = 'APPROVED'
            return True
    def cancel(self):
        with self._lock:
            if self._state not in ('PENDING_APPROVAL', 'APPROVED'):
                return False
            self._state = 'CANCELLED'
            return True
    def consume_relative(self, proposal, observation, region):
        """Consume once, then validate only backend-observed geometry and region evidence."""
        def blocked(code): return {'ok':False, 'code':code}
        with self._lock:
            if self._state == 'CONSUMED': return blocked('APPROVAL_ALREADY_CONSUMED')
            if self._state != 'APPROVED': return blocked('APPROVAL_MISSING')
            self._state = 'CONSUMED'
            with _physical_approvals_lock:
                if self.proposal.proposal_id in _physical_consumed: return blocked('APPROVAL_ALREADY_CONSUMED')
                _physical_consumed.add(self.proposal.proposal_id)
            p = self.proposal
            if type(p) is not RelativePhysicalMoveProposal or proposal != p: return blocked('PROPOSAL_MISMATCH')
            if type(p.deadline_monotonic) not in (int,float) or not math.isfinite(p.deadline_monotonic) or time.monotonic() >= p.deadline_monotonic: return blocked('APPROVAL_EXPIRED')
            if not p.task_id or not p.proposal_id or not p.monitor or type(p.lab_hwnd) is not int or p.lab_hwnd <= 0 or type(p.lab_pid) is not int or p.lab_pid <= 0:
                return blocked('PROPOSAL_MISMATCH')
            if type(p.dx) is not int or type(p.dy) is not int or not 0 < abs(p.dx)+abs(p.dy) <= 10 or type(p.tolerance) is not int or p.tolerance != 0:
                return blocked('PROPOSAL_MISMATCH')
            if not isinstance(p.safe_rect, tuple) or not isinstance(p.monitor_rect, tuple) or len(p.safe_rect)!=4 or len(p.monitor_rect)!=4 or any(type(v) is not int for v in (*p.safe_rect,*p.monitor_rect)):
                return blocked('PROPOSAL_MISMATCH')
            if not isinstance(observation,dict) or observation.get('status') != 'OBSERVED': return blocked('OBSERVATION_UNAVAILABLE')
            if observation.get('coordinate_space') != 'PHYSICAL': return blocked('COORDINATE_SPACE_MISMATCH')
            if observation.get('monitor') != p.monitor: return blocked('MONITOR_CHANGED')
            if tuple(observation.get('monitor_rect', ())) != p.monitor_rect: return blocked('MONITOR_GEOMETRY_CHANGED')
            if not isinstance(region,dict) or region.get('status') != 'VERIFIED' or region.get('coordinate_space') != 'PHYSICAL': return blocked('SAFE_REGION_UNVERIFIED')
            if (region.get('lab_hwnd'),region.get('lab_pid'),tuple(region.get('safe_rect', ()))) != (p.lab_hwnd,p.lab_pid,p.safe_rect): return blocked('SAFE_REGION_CHANGED')
            observed_at=region.get('observed_monotonic')
            if type(observed_at) not in (int,float) or not math.isfinite(observed_at) or not 0 <= time.monotonic()-observed_at <= 1.0: return blocked('SAFE_REGION_STALE')
            sl,st,sr,sb=p.safe_rect; ml,mt,mr,mb=p.monitor_rect
            if not (ml <= sl < sr <= mr and mt <= st < sb <= mb): return blocked('SAFE_REGION_UNVERIFIED')
            point = observation.get('cursor')
            controls = region.get('controls_rects')
            if not isinstance(point,(tuple,list)) or len(point)!=2 or any(type(v) is not int for v in point) or not isinstance(controls,list): return blocked('SAFE_REGION_UNVERIFIED')
            if any(not isinstance(c,(tuple,list)) or len(c)!=4 or any(type(v) is not int for v in c) or c[0]>=c[2] or c[1]>=c[3] for c in controls): return blocked('SAFE_REGION_UNVERIFIED')
            from capability_lab import bounded_linear_points
            try: points=bounded_linear_points(point,p.dx,p.dy,p.safe_rect)
            except ValueError: return blocked('CURSOR_OUTSIDE_SAFE_REGION')
            l,t,r,b=p.monitor_rect
            if any(not(l<=x<r and t<=y<b) for x,y in points): return blocked('MONITOR_BOUNDARY')
            if any(c[0]<=x<c[2] and c[1]<=y<c[3] for x,y in points for c in controls): return blocked('CONTROL_INTERSECTS_PATH')
            return {'ok':True,'code':'APPROVAL_CONSUMED','start':tuple(point),'target':points[-1]}

    def consume(self, proposal, observation):
        return self.consume_diagnostic(proposal, observation)['ok']

    def consume_diagnostic(self, proposal, observation):
        """Consume an approved proposal atomically; return only bounded diagnostics."""
        def blocked(code, category):
            return {'ok': False, 'code': code, 'category': category}
        with self._lock:
            if self._state == 'CONSUMED':
                return blocked('APPROVAL_ALREADY_CONSUMED', 'approval')
            if self._state != 'APPROVED':
                return blocked('APPROVAL_MISSING', 'approval')
            self._state = 'CONSUMED'
            with _physical_approvals_lock:
                if self.proposal.proposal_id in _physical_consumed:
                    return blocked('APPROVAL_ALREADY_CONSUMED', 'approval')
                _physical_consumed.add(self.proposal.proposal_id)
            p = self.proposal
            if time.monotonic() >= p.deadline_monotonic:
                return blocked('APPROVAL_EXPIRED', 'approval')
            if type(proposal) is not PhysicalMoveProposal or proposal != p:
                return blocked('PROPOSAL_MISMATCH', 'approval')
            if not p.task_id or not p.proposal_id or not p.monitor or type(p.tolerance) is not int or p.tolerance not in range(4):
                return blocked('PROPOSAL_MISMATCH', 'approval')
            if (not isinstance(p.start, tuple) or not isinstance(p.target, tuple) or not isinstance(p.monitor_rect, tuple)
                or len(p.start)!=2 or len(p.target)!=2 or len(p.monitor_rect)!=4
                or not all(type(v) is int for v in (*p.start, *p.target, *p.monitor_rect))):
                return blocked('PROPOSAL_MISMATCH', 'approval')
            if type(p.duration_ms) is not int or p.duration_ms not in (0, 300):
                return blocked('PROPOSAL_MISMATCH', 'approval')
            if type(p.max_distance) is not int or p.max_distance not in (10, 150) or not 0 < math.dist(p.start,p.target) <= p.max_distance:
                return blocked('PROPOSAL_MISMATCH', 'approval')
            l,t,r,b=p.monitor_rect
            if not all(l <= point[0] < r and t <= point[1] < b for point in (p.start,p.target)):
                return blocked('PROPOSAL_MISMATCH', 'geometry')
            if not isinstance(observation, dict) or observation.get('status') != 'OBSERVED':
                return blocked('OBSERVATION_UNAVAILABLE', 'observation')
            if observation.get('coordinate_space') != 'PHYSICAL':
                return blocked('COORDINATE_SPACE_MISMATCH', 'geometry')
            if tuple(observation.get('cursor', ())) != p.start:
                return blocked('CURSOR_POSITION_CHANGED', 'observation')
            if observation.get('monitor') != p.monitor:
                return blocked('MONITOR_CHANGED', 'observation')
            if tuple(observation.get('monitor_rect', ())) != p.monitor_rect:
                return blocked('MONITOR_GEOMETRY_CHANGED', 'geometry')
            return {'ok': True, 'code': 'APPROVAL_CONSUMED', 'category': 'approval'}

_physical_move_scope = ContextVar('brainnet_physical_move_scope', default=None)
@contextmanager
def approved_physical_move_scope(proposal):
    marker = _physical_move_scope.set(proposal)
    try: yield
    finally: _physical_move_scope.reset(marker)

def require_specific_physical_move(x, y):
    require_action_allowed('MOVE_CURSOR')
    p = _physical_move_scope.get()
    if type(p) is not PhysicalMoveProposal or p.target != (x, y) or time.monotonic() >= p.deadline_monotonic:
        raise PermissionError('Aprovação física específica ausente ou expirada')
