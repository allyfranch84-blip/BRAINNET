"""Decision-only adaptive attention; no capture, inference or motor I/O."""
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
import math
import time
import threading
import uuid
from contextvars import ContextVar

class ResourceState(str, Enum):
    IDLE='IDLE'; NORMAL='NORMAL'; FOCUSED='FOCUSED'; HIGH_LOAD='HIGH_LOAD'; CRITICAL='CRITICAL'
class Attention(str, Enum):
    PERIPHERAL='PERIPHERAL'; FOCAL='FOCAL'; DEEP='DEEP'; SUSPENDED='SUSPENDED'

@dataclass(frozen=True)
class ResourceSample:
    cpu_pct: Optional[float] = None
    gpu_pct: Optional[float] = None
    ram_available_mb: Optional[float] = None
    user_active: Optional[bool] = None
    user_idle_seconds: Optional[float] = None
    active_tasks: Optional[int] = None
    timestamp: Optional[float] = None
    sources: dict = field(default_factory=dict)

@dataclass(frozen=True)
class PerceptualSignals:
    unexpected_element: bool = False
    target_changed: bool = False
    action_failed: bool = False
    effect_diverged: bool = False
    uncertainty_high: bool = False
    explicit_request: bool = False
    pixel_change_only: bool = False
    uia_available: bool = False
    localized_change: bool = False
    roi_identified: bool = False

@dataclass(frozen=True)
class ControllerConfig:
    cpu_high: float = 85.0
    cpu_recover: float = 70.0
    gpu_high: float = 85.0
    gpu_recover: float = 70.0
    ram_critical_mb: float = 1024.0
    ram_recover_mb: float = 1536.0
    idle_cpu_pct: float = 20.0
    idle_gpu_pct: float = 20.0
    min_transition_seconds: float = 5.0
    recovery_samples: int = 2
    max_sample_age_seconds: float = 10.0
    idle_seconds: float = 30.0
    def __post_init__(self):
        vals=(self.cpu_high,self.cpu_recover,self.gpu_high,self.gpu_recover,self.ram_critical_mb,self.ram_recover_mb,self.min_transition_seconds,self.max_sample_age_seconds,self.idle_seconds)
        if any(not isinstance(x,(int,float)) or isinstance(x,bool) or not math.isfinite(x) for x in vals): raise ValueError('invalid thresholds')
        if not (0 <= self.cpu_recover < self.cpu_high <= 100 and 0 <= self.gpu_recover < self.gpu_high <= 100): raise ValueError('invalid load hysteresis')
        if not 0 < self.ram_critical_mb < self.ram_recover_mb or self.min_transition_seconds < 0 or self.max_sample_age_seconds <= 0 or self.idle_seconds < 0: raise ValueError('invalid resource thresholds')
        if isinstance(self.recovery_samples,bool) or not isinstance(self.recovery_samples,int) or self.recovery_samples < 1: raise ValueError('invalid recovery samples')

@dataclass
class TaskContinuity:
    task_id: str
    objective: str
    plan: object = None
    last_validated_observation: object = None
    next_action: object = None
    factual_verification: str = 'UNKNOWN'
    selected_model: Optional[str] = None
    escalation_reason: Optional[str] = None
    allowed_resources: dict = field(default_factory=dict)
    status: str = 'RUNNING'
    action_in_progress: bool = False
    essential: bool = False
    pause_pending: bool = False
    requires_revalidation: bool = False
    pause_reason: Optional[str] = None


@dataclass(frozen=True)
class ExecutionLimits:
    planning_steps: int
    inference_calls: int
    visual_iterations: int
    token_limit: int


class BudgetExhausted(RuntimeError):
    pass


class SharedTaskBudget:
    """In-memory, per-task reservations; deadline is never persisted."""
    def __init__(self, task_id, reasoning_mode, deadline_monotonic, cancellation_event, limits):
        self.task_id = task_id
        self.reasoning_mode = reasoning_mode
        self.deadline_monotonic = deadline_monotonic
        self.cancellation_event = cancellation_event
        self.limits = limits
        self.planning_steps_used = self.inference_calls_used = self.visual_iterations_used = 0
        self.token_usage = {'estimated': 0, 'reported': None}
        self.task_state = 'RUNNING'
        self.selected_model = None
        self.backend = None
        self._lock = threading.RLock()
        self._operations = {}

    def begin_inference(self, *, estimated_tokens=0):
        with self._lock:
            self.reserve('inference', estimated_tokens=estimated_tokens)
            operation_id = uuid.uuid4().hex
            self._operations[operation_id] = {'kind': 'inference', 'status': 'RUNNING', 'started': time.monotonic(), 'estimated_tokens': estimated_tokens}
            return operation_id

    def check_active(self):
        with self._lock:
            if self.cancellation_event.is_set() or time.monotonic() >= self.deadline_monotonic:
                self.cancellation_event.set()
                self.task_state = 'CANCEL_REQUESTED'
                raise BudgetExhausted('cancelamento ou prazo atingido; término em andamento não confirmado')

    def begin_tool(self, name):
        with self._lock:
            self.check_active()
            operation_id = uuid.uuid4().hex
            self._operations[operation_id] = {'kind': 'tool', 'name': name, 'status': 'RUNNING', 'started': time.monotonic()}
            return operation_id

    def begin_pending_motor(self, proposal):
        """Record a proposal, not an authorization, under this task's lock."""
        with self._lock:
            self.check_active()
            operation_id = uuid.uuid4().hex
            self._operations[operation_id] = {
                'kind': 'motor_proposal', 'action': 'MOVE_CURSOR',
                'dx': proposal['dx'], 'dy': proposal['dy'],
                'hwnd': None, 'pid': None, 'safe_rect': None,
                'deadline_monotonic': self.deadline_monotonic,
                'status': 'WAITING_AUTHORIZATION', 'started': time.monotonic(),
            }
            self.task_state = 'WAITING_AUTHORIZATION'
            return operation_id

    def cancel_pending_motor(self, operation_id):
        with self._lock:
            operation = self._operations.get(operation_id)
            if not operation or operation['status'] not in ('WAITING_AUTHORIZATION', 'AUTHORIZED'):
                return False
            self.cancellation_event.set()
            operation['status'] = 'CANCELLED'
            self.task_state = 'CANCELLED'
            return True

    def expire_pending_motor(self, operation_id):
        with self._lock:
            operation = self._operations.get(operation_id)
            if (not operation or operation['status'] not in ('WAITING_AUTHORIZATION', 'AUTHORIZED')
                    or time.monotonic() < operation['deadline_monotonic']):
                return False
            operation['status'] = self.task_state = 'EXPIRED'
            self.cancellation_event.set()
            return True

    def bind_motor_observation(self, operation_id, *, hwnd, pid, safe_rect):
        with self._lock:
            op = self._operations.get(operation_id)
            if (not op or op['status'] != 'WAITING_AUTHORIZATION' or self.cancellation_event.is_set()
                    or self.expire_pending_motor(operation_id)):
                return False
            if (type(hwnd) is not int or hwnd <= 0 or type(pid) is not int or pid <= 0
                    or not isinstance(safe_rect, (tuple, list)) or len(safe_rect) != 4
                    or any(type(v) is not int for v in safe_rect)
                    or safe_rect[0] >= safe_rect[2] or safe_rect[1] >= safe_rect[3]):
                return False
            op.update(hwnd=hwnd, pid=pid, safe_rect=tuple(safe_rect))
            return True

    def transition_motor_simulation(self, operation_id, expected, new_state, *, evidence=None):
        """State machine for isolated simulation only; never grants physical authority."""
        allowed = {('WAITING_AUTHORIZATION', 'AUTHORIZED'), ('AUTHORIZED', 'EXECUTING'),
                   ('EXECUTING', 'VERIFYING'), ('EXECUTING', 'FAILED'),
                   ('EXECUTING', 'INCONCLUSIVE'), ('VERIFYING', 'SUCCEEDED'),
                   ('VERIFYING', 'FAILED'), ('VERIFYING', 'INCONCLUSIVE')}
        with self._lock:
            op = self._operations.get(operation_id)
            if not op or (expected, new_state) not in allowed or op['status'] != expected:
                return False
            if self.expire_pending_motor(operation_id) or self.cancellation_event.is_set():
                return False
            if time.monotonic() >= op['deadline_monotonic']:
                return False
            if expected in ('WAITING_AUTHORIZATION', 'AUTHORIZED'):
                if not isinstance(evidence, dict) or any(evidence.get(k) != op.get(k) for k in ('hwnd', 'pid', 'safe_rect', 'dx', 'dy')):
                    return False
                if not evidence.get('hwnd') or not evidence.get('pid') or not evidence.get('safe_rect'):
                    return False
            op['status'] = self.task_state = new_state
            return True

    def mark_unconfirmed(self, operation_id):
        with self._lock:
            if operation_id in self._operations and self._operations[operation_id]['status'] == 'RUNNING':
                self._operations[operation_id]['status'] = 'CANCEL_REQUESTED_UNCONFIRMED'

    def finish_inference(self, operation_id, *, reported_tokens=None, confirmed=True):
        with self._lock:
            operation = self._operations[operation_id]
            if operation['status'] == 'FINISHED':
                return
            operation['status'] = 'FINISHED' if confirmed else 'REMOTE_UNCONFIRMED'
            operation['elapsed_s'] = time.monotonic() - operation['started']
            if isinstance(reported_tokens, int) and not isinstance(reported_tokens, bool) and reported_tokens >= 0:
                self.token_usage['reported'] = (self.token_usage['reported'] or 0) + reported_tokens

    def reserve(self, operation, *, estimated_tokens=0):
        fields = {'planning': ('planning_steps_used', self.limits.planning_steps),
                  'inference': ('inference_calls_used', self.limits.inference_calls),
                  'visual': ('visual_iterations_used', self.limits.visual_iterations)}
        if operation not in fields or not isinstance(estimated_tokens, int) or estimated_tokens < 0:
            raise ValueError('invalid reservation')
        with self._lock:
            attr, limit = fields[operation]
            if self.cancellation_event.is_set() or time.monotonic() >= self.deadline_monotonic:
                self.cancellation_event.set()
                self.task_state = 'CANCEL_REQUESTED'
                raise BudgetExhausted('cancelamento ou prazo atingido; término em andamento não confirmado')
            if getattr(self, attr) >= limit or self.token_usage['estimated'] + estimated_tokens > self.limits.token_limit:
                self.cancellation_event.set()
                self.task_state = 'BUDGET_EXHAUSTED'
                raise BudgetExhausted('orçamento esgotado; término em andamento não confirmado')
            setattr(self, attr, getattr(self, attr) + 1)
            self.token_usage['estimated'] += estimated_tokens

    def snapshot(self):
        with self._lock:
            return {'task_id': self.task_id, 'reasoning_mode': self.reasoning_mode,
                    'deadline_monotonic': self.deadline_monotonic,
                    'planning_steps_used': self.planning_steps_used,
                    'inference_calls_used': self.inference_calls_used,
                    'visual_iterations_used': self.visual_iterations_used,
                    'token_usage': dict(self.token_usage), 'task_state': self.task_state,
                    'selected_model': self.selected_model, 'backend': self.backend,
                    'inflight': sum(op['status'] != 'FINISHED' for op in self._operations.values()),
                    'operations': {key: dict(value) for key, value in self._operations.items()},
                    'remaining_s': max(0.0, self.deadline_monotonic - time.monotonic())}

    def record_inference(self, backend, model, state):
        with self._lock:
            self.backend = backend
            self.selected_model = model
            self.task_state = state


current_task_budget = ContextVar('brainnet_shared_task_budget', default=None)

class AdaptiveResourceController:
    """Consumes snapshots and returns advice only. The caller performs all I/O.

    Times use an injected monotonic clock. Unknown/stale metrics never imply idle
    or permission for deep inference. CRITICAL enters immediately; other changes
    obey dwell time, and recovery from pressure requires consecutive safe samples.
    """
    def __init__(self, config=None, *, clock=time.monotonic):
        self.config=config or ControllerConfig(); self.clock=clock
        self.state=ResourceState.NORMAL; self._last_transition=clock(); self._safe_samples=0
        self.tasks={};self.events=[]
    def _event(self, kind, **data): self.events.append({'event':kind,'at':self.clock(),**data})
    def register_task(self, task):
        if not isinstance(task,TaskContinuity) or not task.task_id or task.task_id in self.tasks: raise ValueError('invalid or duplicate task')
        self.tasks[task.task_id]=task
    def pause(self, task_id, reason):
        task=self.tasks[task_id];task.pause_reason=reason;task.requires_revalidation=True
        if task.action_in_progress:
            task.pause_pending=True;self._event('pause_pending',task=task_id,reason=reason);return 'PAUSE_PENDING'
        task.status='PAUSED';task.pause_pending=False;self._event('paused',task=task_id,reason=reason);return 'PAUSED'
    def action_finished(self, task_id):
        task=self.tasks[task_id];task.action_in_progress=False
        if task.pause_pending:task.status='PAUSED';task.pause_pending=False;self._event('paused',task=task_id,reason=task.pause_reason)
    def resume(self, task_id):
        task=self.tasks[task_id]
        if task.status!='PAUSED': raise ValueError('task is not paused')
        if self.state==ResourceState.CRITICAL: raise ValueError('resources remain critical')
        task.status='REVALIDATING';task.requires_revalidation=True;self._event('revalidation_required',task=task_id)
    def confirm_context(self, task_id, observation, *, verified):
        task=self.tasks[task_id]
        prior=task.last_validated_observation
        if (task.status!='REVALIDATING' or verified is not True or not isinstance(observation,dict)
            or not isinstance(prior,dict) or not prior.get('hwnd') or not prior.get('pid')
            or observation.get('hwnd')!=prior['hwnd'] or observation.get('pid')!=prior['pid']
            or observation.get('controls_validated') is not True
            or observation.get('objective')!=task.objective): return False
        # Coordinates belong to an old observation and may not be reused.
        task.next_action=None
        task.last_validated_observation=observation;task.requires_revalidation=False;task.status='RUNNING';task.pause_reason=None;self._event('context_revalidated',task=task_id);return True
    def can_act(self, task_id):
        t=self.tasks[task_id];return t.status=='RUNNING' and not t.requires_revalidation and self.state!=ResourceState.CRITICAL
    @staticmethod
    def _valid_number(x, lo, hi): return not isinstance(x,bool) and isinstance(x,(int,float)) and math.isfinite(x) and lo<=x<=hi
    def update(self, sample, signals=None):
        if not isinstance(sample,ResourceSample): raise TypeError('expected ResourceSample')
        s=signals or PerceptualSignals(); now=self.clock();c=self.config
        age=now-sample.timestamp if self._valid_number(sample.timestamp,0,float('inf')) else None
        stale=age is None or age<0 or age>c.max_sample_age_seconds
        cpu=sample.cpu_pct if not stale and self._valid_number(sample.cpu_pct,0,100) else None
        gpu=sample.gpu_pct if not stale and self._valid_number(sample.gpu_pct,0,100) else None
        ram=sample.ram_available_mb if not stale and self._valid_number(sample.ram_available_mb,0,float('inf')) else None
        user=sample.user_active if not stale and isinstance(sample.user_active,bool) else None
        idle=sample.user_idle_seconds if not stale and self._valid_number(sample.user_idle_seconds,0,float('inf')) else None
        tasks=sample.active_tasks if not stale and isinstance(sample.active_tasks,int) and not isinstance(sample.active_tasks,bool) and sample.active_tasks>=0 else None
        missing=[name for name,val in (('cpu',cpu),('gpu',gpu),('ram',ram),('user_activity',user),('tasks',tasks)) if val is None]
        critical=ram is not None and ram<c.ram_critical_mb
        high=(cpu is not None and cpu>=c.cpu_high) or (gpu is not None and gpu>=c.gpu_high)
        relevant=any((s.unexpected_element,s.target_changed,s.action_failed,s.effect_diverged,s.uncertainty_high,s.explicit_request))
        if critical: desired=ResourceState.CRITICAL
        elif high: desired=ResourceState.HIGH_LOAD
        elif self.state==ResourceState.CRITICAL and (ram is None or ram<c.ram_recover_mb): desired=ResourceState.CRITICAL
        elif self.state in (ResourceState.HIGH_LOAD,ResourceState.CRITICAL) and (missing or cpu>c.cpu_recover or gpu>c.gpu_recover or ram<c.ram_recover_mb): desired=self.state
        elif relevant: desired=ResourceState.FOCUSED
        elif not missing and not user and idle is not None and idle>=c.idle_seconds and tasks==0 and cpu<c.idle_cpu_pct and gpu<c.idle_gpu_pct: desired=ResourceState.IDLE
        else: desired=ResourceState.NORMAL
        recovering=self.state in (ResourceState.HIGH_LOAD,ResourceState.CRITICAL) and desired not in (ResourceState.HIGH_LOAD,ResourceState.CRITICAL)
        self._safe_samples=self._safe_samples+1 if recovering else 0
        can_change=(desired==ResourceState.CRITICAL or (desired==ResourceState.HIGH_LOAD and self.state not in (ResourceState.HIGH_LOAD,ResourceState.CRITICAL)) or (now-self._last_transition>=c.min_transition_seconds and (not recovering or self._safe_samples>=c.recovery_samples)))
        if desired!=self.state and can_change:
            old=self.state;self.state=desired;self._last_transition=now;self._safe_samples=0;self._event('state_changed',previous=old.value,current=desired.value)
        if self.state==ResourceState.CRITICAL:
            for task in self.tasks.values():
                if task.status=='RUNNING' and not task.essential and not task.pause_pending:self.pause(task.task_id,'critical resource pressure')
            attention=Attention.SUSPENDED
        elif self.state==ResourceState.HIGH_LOAD: attention=Attention.FOCAL if s.explicit_request and s.roi_identified else Attention.PERIPHERAL
        elif missing: attention=Attention.FOCAL if s.explicit_request and s.roi_identified else Attention.PERIPHERAL
        elif s.uncertainty_high and relevant and s.roi_identified: attention=Attention.DEEP
        elif relevant and (s.roi_identified or s.uia_available): attention=Attention.FOCAL
        else: attention=Attention.PERIPHERAL
        deep_allowed=attention==Attention.DEEP and not missing and self.state not in (ResourceState.HIGH_LOAD,ResourceState.CRITICAL)
        reason=None
        if deep_allowed:reason='high uncertainty with relevant identified region'
        priorities=['1.5B','7B','vision_small','vision_large','14B_on_demand']
        reasons={'SUSPENDED':'critical resource pressure','PERIPHERAL':'limited resources or no relevant change',
                 'FOCAL':'relevant target or explicit request','DEEP':'high uncertainty with identified region'}
        return {'state':self.state.value,'attention':attention.value,'unknown_metrics':missing,'sample_stale':stale,
                'reason':reasons[attention.value], 'confidence':'LOW' if missing else 'OBSERVED',
                'reassess_at':now+(5 if self.state in (ResourceState.HIGH_LOAD,ResourceState.CRITICAL) else 30),
                'metrics':{'cpu_pct':cpu,'gpu_pct':gpu,'ram_available_mb':ram,'user_active':user,'active_tasks':tasks},
                'sources':dict(sample.sources),'invoke_vlm':deep_allowed,'escalation_reason':reason,
                'budgets':{'capture_interval_s':None if self.state==ResourceState.CRITICAL else (60 if self.state==ResourceState.HIGH_LOAD else 30),
                           'allow_new_loads':not missing and self.state not in (ResourceState.HIGH_LOAD,ResourceState.CRITICAL),
                           'allow_14b':False,'allow_deep':deep_allowed,'resident_policy':'reduce' if self.state in (ResourceState.HIGH_LOAD,ResourceState.CRITICAL) else 'normal',
                           'model_priority':priorities},
                'task_states':{k:asdict(v) for k,v in self.tasks.items()}}

    def residency_advice(self, decision, residency_snapshot, *, visual_model='vision_small'):
        """Return a proposal only; never load, evict, or alter a request."""
        models=residency_snapshot.get('models',[]) if isinstance(residency_snapshot,dict) else []
        model=next((x for x in models if x.get('name')==visual_model),None)
        if decision.get('state') in ('HIGH_LOAD','CRITICAL'):
            return {'action':'DEFER','fallback':'UIA','reason':'resource pressure',
                    'recommend_secondary_eviction':True,'protect_active_requests':True}
        if decision.get('attention') not in ('FOCAL','DEEP'):
            return {'action':'NO_CHANGE','reason':'no focal demand'}
        if model and model.get('state')=='HOT': return {'action':'USE_IF_NEEDED','model':visual_model}
        if not decision.get('budgets',{}).get('allow_new_loads'):
            return {'action':'DEFER','fallback':'UIA','reason':'resources unverified or insufficient'}
        return {'action':'REQUEST_ADMISSION','model':visual_model,'reason':'profiler approval required'}

    def update_observation(self, sample, observation, *, explicit_request=False,
                           target_relevant=False, roi_identified=False, uncertainty_high=False):
        """Translate passive signals to advice; a pixel change alone never escalates."""
        if not isinstance(observation,dict): raise TypeError('expected passive observation')
        # Relevance must be established by the caller's task/UIA logic.
        target_changed=bool(target_relevant and (observation.get('uia_changed') or
                            observation.get('uia_focus_changed') or observation.get('window_changed')))
        signals=PerceptualSignals(target_changed=target_changed,explicit_request=explicit_request,
            uncertainty_high=bool(uncertainty_high and (target_relevant or explicit_request)),
            pixel_change_only=bool(observation.get('visual_changed')),
            uia_available=bool(observation.get('uia_available')),roi_identified=roi_identified,
            localized_change=bool(observation.get('region_persistent') and roi_identified))
        return self.update(sample,signals)
