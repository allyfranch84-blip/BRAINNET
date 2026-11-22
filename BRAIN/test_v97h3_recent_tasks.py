from collections import deque
import threading
from unittest.mock import Mock
from adaptive_resource_controller import current_task_budget
from test_v97r22_production import make_bridge


def test_recent_tasks_preserve_pending_operation_and_are_bounded():
    bridge=make_bridge()
    bridge._kernel._runtime_task_lock=threading.RLock()
    bridge._kernel._runtime_tasks={}
    bridge._kernel._runtime_recent_tasks=deque(maxlen=32)
    captured=[]
    def run(_):
        budget=current_task_budget.get()
        op=budget.begin_inference(estimated_tokens=5)
        budget.mark_unconfirmed(op)
        captured.append((budget,op))
        return {'reply':'pendente','logs':[]}
    bridge._send_command_impl=run
    result=bridge.send_command('tarefa')
    assert result['task_budget']['inflight']==1
    assert not bridge._kernel._runtime_tasks
    recent=bridge._kernel._runtime_recent_tasks[-1]
    assert recent.task_id==result['task_budget']['task_id'] and recent.snapshot()['inflight']==1
    budget,op=captured[0]
    budget.finish_inference(op,confirmed=True)
    assert recent.snapshot()['inflight']==0
