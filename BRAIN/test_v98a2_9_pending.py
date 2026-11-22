import threading
from test_v97r22_production import make_bridge


def make_registered_bridge():
    b=make_bridge()
    b._kernel._runtime_tasks={}
    b._kernel._runtime_task_lock=threading.Lock()
    b._kernel._runtime_recent_tasks=[]
    return b


def test_real_chat_retains_pending_task_and_operation():
    b=make_registered_bridge()
    r=b.send_command('mova o mouse 30 pixels para a direita, sem clicar')
    task_id=r['task_budget']['task_id']; operation_id=r['pending_operation_id']
    task=b._kernel._runtime_tasks[task_id]
    assert r['status']=='AUTHORIZATION_REQUIRED'
    assert r['motor_proposal']['task_id']==task_id
    assert task.task_state=='WAITING_AUTHORIZATION'
    assert not task.cancellation_event.is_set()
    op=task.snapshot()['operations'][operation_id]
    assert (op['action'],op['dx'],op['dy'],op['status']) == ('MOVE_CURSOR',30,0,'WAITING_AUTHORIZATION')
    assert op['hwnd'] is None and op['safe_rect'] is None


def test_pending_task_can_be_cancelled_once():
    b=make_registered_bridge()
    r=b.send_command('mova o mouse 30 pixels para a direita, sem clicar')
    task=b._kernel._runtime_tasks[r['task_budget']['task_id']]
    assert task.cancel_pending_motor(r['pending_operation_id'])
    assert task.cancellation_event.is_set() and task.task_state=='CANCELLED'
    assert not task.cancel_pending_motor(r['pending_operation_id'])
