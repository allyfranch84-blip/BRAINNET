import io
import json
import time
from types import SimpleNamespace
from unittest.mock import Mock
from operations_status import RuntimeTelemetrySampler
from BRAINNET import BrainnetBridge


def test_real_read_only_cpu_ram_and_simulated_ollama():
    payload={'models':[{'name':'modelo','size':123,'size_vram':45,'expires_at':'2026-01-01'}]}
    sampler=RuntimeTelemetrySampler(opener=lambda *a,**kw:io.BytesIO(json.dumps(payload).encode()))
    first=sampler.collect(); second=sampler.collect()
    assert first['hardware']['cpu_total_pct'] is None
    assert second['hardware']['ram_total_bytes']>0 and second['hardware']['process_rss_bytes']>0
    assert second['hardware']['gpu_pct'] is None
    assert second['inference']['ollama']['models'][0]['vram_bytes']==45
    assert not sampler.snapshot()['stale']


def test_offline_and_old_sample_are_explicit():
    def offline(*a,**kw): raise OSError('offline')
    sampler=RuntimeTelemetrySampler(opener=offline)
    sample=sampler.collect()
    assert not sample['inference']['ollama']['available']
    sampler._snapshot['timestamp']=time.time()-100
    assert sampler.snapshot()['stale']


def test_bridge_reads_two_tasks_without_inference():
    import threading
    bridge=object.__new__(BrainnetBridge)
    sampler=SimpleNamespace(snapshot=lambda:{'available':True})
    tasks={'a':SimpleNamespace(snapshot=lambda:{'task_id':'a'}),'b':SimpleNamespace(snapshot=lambda:{'task_id':'b'})}
    bridge._kernel=SimpleNamespace(_runtime_telemetry=sampler,_runtime_task_lock=threading.RLock(),_runtime_tasks=tasks,is_running=True)
    result=bridge.get_runtime_telemetry()
    assert {task['task_id'] for task in result['kernel']['active_tasks']}=={'a','b'}
    assert result['kernel']['queue'] is None
