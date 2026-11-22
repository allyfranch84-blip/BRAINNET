"""Bounded derived index for structured snapshots; never grants authority."""
from collections import OrderedDict
from dataclasses import dataclass
import numpy as np
import time

@dataclass(frozen=True)
class IndexedSnapshot:
    task_id: str
    snapshot_id: str
    timestamp: float
    source: str
    valid_until: float
    verification_status: str
    fields: dict
    schema_version: int = 1
    representation_version: int = 1

class SituationFHRRIndex:
    def __init__(self, engine, *, max_bytes=1048576, clock=time.time):
        if max_bytes <= 0: raise ValueError('invalid index budget')
        self.engine=engine;self.max_bytes=max_bytes;self.clock=clock;self._items=OrderedDict()

    @staticmethod
    def _text(fields):
        names=('objective','intent','application','window','target','state','context','verified_result')
        return ' '.join(f'{k} {fields[k]}' for k in names if isinstance(fields.get(k),str) and fields[k])

    def put(self, record):
        if not isinstance(record,IndexedSnapshot) or record.schema_version != 1 or record.representation_version != 1:
            raise ValueError('unsupported representation')
        if not record.task_id or not record.snapshot_id or not record.source or record.valid_until <= record.timestamp:
            raise ValueError('invalid provenance')
        if not record.timestamp <= self.clock() < record.valid_until:
            raise ValueError('snapshot not currently valid')
        text=self._text(record.fields)
        if not text: raise ValueError('empty index text')
        vector=np.asarray(self.engine.text_to_hypervector(text),dtype=np.complex64)
        if vector.shape != (self.engine.dim,) or not np.isfinite(vector).all() or vector.nbytes > self.max_bytes:
            raise ValueError('invalid or oversized vector')
        import copy
        key=(record.task_id,record.snapshot_id)
        self._items.pop(key,None)
        while self._items and sum(v.nbytes for _,v in self._items.values())+vector.nbytes>self.max_bytes:
            self._items.popitem(last=False)
        self._items[key]=(copy.deepcopy(record),vector.copy())

    def search(self, task_id, text, *, exact_snapshot_id=None, limit=5):
        if limit <= 0: return []
        import copy
        now=self.clock(); valid=[(r,v) for r,v in self._items.values() if r.task_id==task_id and r.timestamp<=now<r.valid_until and r.schema_version==1 and r.representation_version==1 and v.shape==(self.engine.dim,) and np.isfinite(v).all()]
        try:
            query=np.asarray(self.engine.text_to_hypervector(text),dtype=np.complex64)
            if query.shape!=(self.engine.dim,) or not np.isfinite(query).all(): raise ValueError('invalid query')
            ranked=sorted(((float(self.engine.similarity(query,v)),r) for r,v in valid),key=lambda x:x[0],reverse=True)
            if not all(np.isfinite(score) for score,_ in ranked): raise ValueError('invalid similarity')
            return [{'snapshot':copy.deepcopy(r),'similarity':score,'match':'associative'} for score,r in ranked[:limit]]
        except Exception:
            return [{'snapshot':copy.deepcopy(r),'similarity':None,'match':'exact'} for r,_ in valid if exact_snapshot_id and r.snapshot_id==exact_snapshot_id][:limit]
