"""Opt-in model residency coordination. No model starts at import.

Drivers and the resource/admission providers are injected. A driver must own
its process and expose load(), healthy(), unload(), and residency().
"""
from dataclasses import dataclass, field
from enum import Enum
import itertools
import math
import threading
import time

class Residency(str, Enum):
    HOT='HOT'; WARM='WARM'; COLD='COLD'; LOADING='LOADING'; EVICTING='EVICTING'; FAILED='FAILED'

class ResidencyError(RuntimeError): pass

@dataclass
class ModelSpec:
    name: str
    role: str
    driver: object
    profile: object
    model: dict
    ram_budget: int
    vram_budget: int = 0
    priority: int | None = None
    max_gpu_layers: int = 0
    idle_seconds: float = 300.0
    projector: str | None = None
    projector_compatible: bool = False
    ram_margin: int = 0
    vram_margin: int = 0
    def __post_init__(self):
        if self.role not in ('fast','general','vision','heavy'): raise ValueError('invalid role')
        if self.priority is None: self.priority={'fast':100,'general':50,'vision':40,'heavy':10}[self.role]
        if isinstance(self.priority,bool) or not isinstance(self.priority,int): raise ValueError('invalid priority')
        if any(isinstance(x,bool) or not isinstance(x,int) or x<0 for x in (self.ram_margin,self.vram_margin)): raise ValueError('invalid margins')
        if not self.name or isinstance(self.ram_budget,bool) or not isinstance(self.ram_budget,int) or self.ram_budget <= 0: raise ValueError('invalid model or RAM budget')
        if isinstance(self.vram_budget,bool) or not isinstance(self.vram_budget,int) or self.vram_budget < 0: raise ValueError('invalid VRAM budget')
        if self.role=='vision' and (not self.projector or not self.projector_compatible): raise ValueError('vision requires verified model/projector compatibility')
        if not isinstance(self.idle_seconds,(int,float)) or not math.isfinite(self.idle_seconds) or self.idle_seconds<0: raise ValueError('invalid idle time')

@dataclass
class ModelRuntime:
    spec: ModelSpec
    state: Residency = Residency.COLD
    active: int = 0
    last_used: float = 0.0
    residency: dict = field(default_factory=dict)
    measured: dict = field(default_factory=dict)
    error: str | None = None
    def record(self):
        return {'name':self.spec.name,'role':self.spec.role,'priority':self.spec.priority,
                'state':self.state.value,'active':self.active,'residency':dict(self.residency),
                # Failed loading/unloading may leave an owned process alive.
                'reserved_ram': self.spec.ram_budget if self.state != Residency.COLD else 0,
                'reserved_vram': self.spec.vram_budget if self.state != Residency.COLD else 0,
                'measured':dict(self.measured),'error':self.error}

@dataclass
class Task:
    task_id: str
    model: str
    priority: int
    deadline: float
    created: float
    requirements: dict = field(default_factory=dict)
    cancelled: bool = False

class ModelResidencyManager:
    """Explicit single-process coordinator; no autonomous Kernel integration.

    Resource provider returns fresh inventory. Admission receives (inventory,
    spec) and must return {'decision': 'APPROVED'} to authorize a load.
    Priority is larger-is-more-important. Aging guarantees waiting tasks reach
    FIFO order after max_wait, provided dequeue continues and tasks do not expire.
    """
    def __init__(self, resource_provider, admission, *, clock=time.monotonic, max_wait=30.0):
        if not callable(resource_provider) or not callable(admission): raise ValueError('providers required')
        if not isinstance(max_wait,(int,float)) or not math.isfinite(max_wait) or max_wait<=0: raise ValueError('invalid max_wait')
        self.resource_provider=resource_provider; self.admission=admission; self.clock=clock; self.max_wait=max_wait
        self.models={}; self.tasks={}; self._order=itertools.count(); self._sequence={}; self._lock=threading.RLock(); self.events=[]
    def _event(self, kind, name, **data): self.events.append({'event':kind,'model':name,'at':self.clock(),**data})
    def register(self, spec):
        with self._lock:
            if spec.name in self.models: raise ValueError('duplicate model')
            self.models[spec.name]=ModelRuntime(spec)
    def inventory(self):
        with self._lock: return {'resources':self.resource_provider(),'models':[r.record() for r in self.models.values()]}
    def recommend_resident(self, *, roles, context_tokens, max_latency_ms):
        """Recommend an already resident model using measured evidence; never load one."""
        if (not isinstance(roles, (list, tuple)) or not roles or isinstance(context_tokens, bool)
                or not isinstance(context_tokens, int) or context_tokens < 0
                or isinstance(max_latency_ms, bool) or not isinstance(max_latency_ms, (int, float))
                or not math.isfinite(max_latency_ms) or max_latency_ms <= 0):
            raise ValueError('invalid selection constraints')
        with self._lock:
            candidates = []
            for runtime in self.models.values():
                spec = runtime.spec
                if runtime.state != Residency.HOT or spec.role not in roles:
                    continue
                context = runtime.measured.get('context_tokens')
                latency = runtime.measured.get('latency_ms')
                if (isinstance(context, bool) or not isinstance(context, int) or context < context_tokens
                        or isinstance(latency, bool) or not isinstance(latency, (int, float))
                        or not math.isfinite(latency) or latency < 0 or latency > max_latency_ms):
                    continue
                if self._decision(spec).get('decision') != 'APPROVED':
                    continue
                candidates.append((roles.index(spec.role), latency, spec.name))
            if not candidates:
                return {'decision': 'INSUFFICIENT_EVIDENCE', 'model': None}
            _, latency, name = min(candidates)
            return {'decision': 'RECOMMENDED', 'model': name, 'latency_ms': latency,
                    'starts_model': False, 'execution_authorized': False}

    def enqueue(self, task_id, model, priority, deadline, requirements=None):
        with self._lock:
            if task_id in self.tasks or model not in self.models: raise ValueError('duplicate task or unknown model')
            if not isinstance(deadline,(int,float)) or not math.isfinite(deadline): raise ValueError('invalid deadline')
            if isinstance(priority,bool) or not isinstance(priority,int): raise ValueError('invalid priority')
            self.tasks[task_id]=Task(task_id,model,priority,deadline,self.clock(),dict(requirements or {})); self._sequence[task_id]=next(self._order)
    def cancel(self, task_id):
        with self._lock:
            task=self.tasks.get(task_id)
            if not task: return False
            task.cancelled=True; return True
    def dequeue(self):
        with self._lock:
            now=self.clock()
            for key in list(self.tasks):
                if self.tasks[key].cancelled or self.tasks[key].deadline<=now:
                    self._event('task_cancelled' if self.tasks[key].cancelled else 'task_expired',self.tasks[key].model,task=key)
                    del self.tasks[key]; self._sequence.pop(key,None)
            if not self.tasks:return None
            # Aged tasks are FIFO ahead of non-aged tasks, even under continuous arrivals.
            def key(t):
                aged=now-t.created>=self.max_wait
                return (0 if aged else 1, self._sequence[t.task_id] if aged else -t.priority, self._sequence[t.task_id])
            task=min(self.tasks.values(),key=key); del self.tasks[task.task_id];self._sequence.pop(task.task_id,None);return task
    def _decision(self, spec):
        try:
            inventory=self.resource_provider()
            decision=self.admission(inventory,spec)
            if not isinstance(decision,dict): return {'decision':'INSUFFICIENT_EVIDENCE','reasons':['invalid admission result']}
            return decision
        except Exception as exc: return {'decision':'INSUFFICIENT_EVIDENCE','reasons':[f'provider error: {exc}']}
    def _evict(self, r):
        if r.active: raise ResidencyError('model busy')
        if r.state not in (Residency.HOT,Residency.WARM): return False
        r.state=Residency.EVICTING; started=self.clock();self._event('evict_started',r.spec.name)
        try:
            if r.spec.driver.unload() is not True: raise ResidencyError('unload not confirmed')
            r.state=Residency.COLD;r.residency={};r.measured={};r.error=None
            self._event('evicted',r.spec.name,duration=self.clock()-started);return True
        except Exception as e:
            r.state=Residency.FAILED;r.error=str(e);self._event('evict_failed',r.spec.name,error=str(e));return False
    def evict(self, name):
        with self._lock:return self._evict(self.models[name])
    def promote(self, name, *, explicit_heavy=False, allow_evict=True):
        with self._lock:
            r=self.models[name]; spec=r.spec
            if spec.role=='heavy' and not explicit_heavy: return {'decision':'DENIED','reasons':['heavy model requires explicit demand']}
            if r.state in (Residency.HOT,Residency.WARM):
                try: healthy=spec.driver.healthy() is True
                except Exception: healthy=False
                if healthy: r.state=Residency.HOT;r.last_used=self.clock();return {'decision':'READY'}
                r.state=Residency.FAILED;r.error='health check failed';self._event('health_failed',name)
                return {'decision':'FAILED','reasons':[r.error]}
            if r.state!=Residency.COLD: return {'decision':'DENIED','reasons':['model not cold']}
            if any(x.state == Residency.FAILED for x in self.models.values() if x is not r):
                return {'decision':'INSUFFICIENT_EVIDENCE','reasons':['failed model ownership or resources unresolved']}
            decision=self._decision(spec)
            # Only evict for explicit heavy requests; never destructively chase ambiguous evidence.
            if decision.get('decision')!='APPROVED' and spec.role=='heavy' and explicit_heavy and allow_evict and decision.get('eviction_may_help') is True:
                candidates=sorted((x for x in self.models.values() if x is not r and x.state in (Residency.HOT,Residency.WARM) and not x.active and x.spec.role!='fast'),key=lambda x:x.spec.priority)
                for candidate in candidates:
                    if not self._evict(candidate): break
                    decision=self._decision(spec)
                    if decision.get('decision')=='APPROVED': break
            if decision.get('decision')!='APPROVED': return decision
            r.state=Residency.LOADING;started=self.clock();self._event('load_started',name)
            try:
                if spec.driver.load() is not True or spec.driver.healthy() is not True: raise ResidencyError('load or health not confirmed')
                resident=spec.driver.residency()
                if not isinstance(resident,dict) or not resident.get('weights_resident'): raise ResidencyError('resident weights not confirmed')
                r.residency=dict(resident);r.measured=dict(resident.get('measured',{}));r.state=Residency.HOT;r.error=None;r.last_used=self.clock()
                self._event('loaded',name,duration=self.clock()-started,measured=dict(r.measured));return {'decision':'READY'}
            except Exception as e:
                r.state=Residency.FAILED;r.error=str(e);self._event('load_failed',name,error=str(e));return {'decision':'FAILED','reasons':[str(e)]}
    def acquire(self, name):
        with self._lock:
            r=self.models[name]
            if r.state!=Residency.HOT: raise ResidencyError('model not ready')
            r.active+=1;r.last_used=self.clock()
    def release(self, name):
        with self._lock:
            r=self.models[name]
            if r.active<=0: raise ResidencyError('unbalanced release')
            r.active-=1;r.last_used=self.clock()
    def idle(self):
        with self._lock:
            now=self.clock()
            for r in self.models.values():
                if r.active or r.state not in (Residency.HOT,Residency.WARM): continue
                if r.spec.role=='fast': continue
                if now-r.last_used<r.spec.idle_seconds: continue
                # WARM only if the driver explicitly verifies persistent weights.
                try: resident=r.spec.driver.residency()
                except Exception: resident={}
                if r.spec.role in ('general','vision') and isinstance(resident,dict) and resident.get('weights_resident') is True:
                    r.state=Residency.WARM;r.residency=dict(resident)
                else:self._evict(r)


def profiler_admission(inventory, spec):
    """Adapter for inference_capability; caller supplies fresh measured evidence."""
    from inference_capability import plan_execution
    if spec.profile is None:
        return {'decision':'INSUFFICIENT_EVIDENCE','reasons':['missing execution profile']}
    decision = plan_execution(inventory,spec.model,spec.profile,ram_budget=spec.ram_budget,
        vram_budget=spec.vram_budget or None,max_gpu_layers=spec.max_gpu_layers,
        ram_margin=spec.ram_margin,vram_margin=spec.vram_margin)
    reasons=decision.get('reasons',[])
    if reasons and all(reason in ('RAM insuficiente','VRAM insuficiente') for reason in reasons):
        decision['eviction_may_help']=True
    return decision

class ProcessDriver:
    """Adapter for an owned LlamaProcessManager plus explicit health/residency probes."""
    def __init__(self, manager, backend, residency_probe):
        self.manager=manager;self.backend=backend;self.residency_probe=residency_probe
    def load(self): return self.manager.start() in ('started','owned')
    def healthy(self): return self.backend.health_check() is True
    def unload(self): return self.manager.stop() is True
    def residency(self): return self.residency_probe()
