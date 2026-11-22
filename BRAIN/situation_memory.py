"""Experimental situational snapshots; no actuator or implicit persistence."""
from dataclasses import dataclass
from threading import RLock
from typing import Optional
import copy
import json
import math
import time

@dataclass(frozen=True)
class Observation:
    key: str
    value: object
    source: str
    observed_at: float
    valid_until: float
    task_id: Optional[str] = None
    window_id: Optional[str] = None
    priority: int = 0
    verified: bool = False
    persist_eligible: bool = False
    schema_version: int = 1

@dataclass(frozen=True)
class SituationSnapshot:
    task_id: Optional[str]
    timestamp: float
    observations: tuple[Observation, ...]
    schema_version: int = 1

@dataclass(frozen=True)
class VerifiedOutcome:
    task_id: str
    source: str
    timestamp: float
    status: str
    evidence: tuple[str, ...] = ()
    schema_version: int = 1

@dataclass(frozen=True)
class ResourceBudget:
    ram_bytes: Optional[int] = None
    vram_bytes: Optional[int] = None
    schema_version: int = 1

# Existing contracts remain authoritative; no parallel inference/task models.
from adaptive_resource_controller import TaskContinuity as TaskContext
from inference_backend import InferenceRequest, InferenceResult
from inference_capability import ExecutionProfile as CapabilityProfile

class SituationMemory:
    def __init__(self, *, enabled=False, max_bytes=65536, clock=time.time):
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes <= 0:
            raise ValueError('invalid memory limit')
        self.enabled=enabled; self.max_bytes=max_bytes; self.clock=clock
        self._items={}; self._lock=RLock(); self._window=None

    def update(self, observation):
        if not self.enabled: raise RuntimeError('experimental memory disabled')
        if not isinstance(observation, Observation) or not observation.key or not observation.source:
            raise ValueError('invalid observation')
        if not all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in (observation.observed_at,observation.valid_until)) or observation.valid_until <= observation.observed_at:
            raise ValueError('invalid validity')
        # Restrict to JSON values; prevents unsafe serialization and detached copies.
        value=json.loads(json.dumps(observation.value, allow_nan=False))
        from dataclasses import replace
        item=replace(observation, value=value)
        if len(json.dumps(item.__dict__, ensure_ascii=False).encode('utf-8')) > self.max_bytes:
            raise ValueError('observation exceeds memory limit')
        with self._lock:
            key=(item.task_id,item.key)
            staged=dict(self._items);staged[key]=item
            while sum(len(json.dumps(x.__dict__,ensure_ascii=False).encode('utf-8')) for x in staged.values()) > self.max_bytes:
                victim=min(staged,key=lambda k:(staged[k].priority,staged[k].observed_at))
                del staged[victim]
            self._items=staged

    def change_window(self, window_id):
        with self._lock:
            if window_id != self._window:
                self._items={k:v for k,v in self._items.items() if v.window_id is None}
                self._window=window_id

    def snapshot(self, task_id=None, *, keys=None):
        with self._lock:
            now=self.clock()
            selected=[copy.deepcopy(v) for v in self._items.values() if v.observed_at <= now < v.valid_until
                      and (v.task_id is None or v.task_id == task_id) and (keys is None or v.key in keys)]
            selected.sort(key=lambda x:(-x.priority,-x.observed_at))
            return SituationSnapshot(task_id,now,tuple(selected))

    def export_eligible(self):
        with self._lock:
            return [copy.deepcopy(v.__dict__) for v in self._items.values() if v.verified and v.persist_eligible]

    def restore_historical(self, records):
        # Returned separately and never inserted into the current situation.
        return tuple({'observation': copy.deepcopy(r), 'state':'REVALIDATION_REQUIRED'} for r in records)
