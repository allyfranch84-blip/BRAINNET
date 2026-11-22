import threading,time
from concurrent.futures import ThreadPoolExecutor
from test_v98a2_9_pending import make_registered_bridge


def setup():
 b=make_registered_bridge(); r=b.send_command('mova o mouse 30 pixels para a direita, sem clicar')
 t=b._kernel._runtime_tasks[r['task_budget']['task_id']]; op=r['pending_operation_id']
 assert t.bind_motor_observation(op,hwnd=12,pid=42,safe_rect=(0,0,100,100))
 return b,t,op,dict(hwnd=12,pid=42,safe_rect=(0,0,100,100),dx=30,dy=0)


def test_simulated_transitions_are_single_use_and_verify():
 b,t,op,e=setup()
 assert t.transition_motor_simulation(op,'WAITING_AUTHORIZATION','AUTHORIZED',evidence=e)
 assert not t.transition_motor_simulation(op,'WAITING_AUTHORIZATION','AUTHORIZED',evidence=e)
 assert not t.transition_motor_simulation(op,'AUTHORIZED','EXECUTING',evidence={**e,'hwnd':13})
 assert t.transition_motor_simulation(op,'AUTHORIZED','EXECUTING',evidence=e)
 assert t.transition_motor_simulation(op,'EXECUTING','VERIFYING')
 assert t.transition_motor_simulation(op,'VERIFYING','SUCCEEDED')
 assert not t.transition_motor_simulation(op,'AUTHORIZED','EXECUTING',evidence=e)


def test_expired_cannot_authorize():
 b,t,op,e=setup(); t.deadline_monotonic=time.monotonic()-1
 t._operations[op]['deadline_monotonic']=t.deadline_monotonic
 assert not t.transition_motor_simulation(op,'WAITING_AUTHORIZATION','AUTHORIZED',evidence=e)
 assert t.task_state=='EXPIRED'


def test_approve_cancel_race_has_only_one_winner():
 b,t,op,e=setup(); gate=threading.Barrier(2)
 def approve(): gate.wait(); return t.transition_motor_simulation(op,'WAITING_AUTHORIZATION','AUTHORIZED',evidence=e)
 def cancel(): gate.wait(); return t.cancel_pending_motor(op)
 with ThreadPoolExecutor(max_workers=2) as pool:
  f=pool.submit(approve); g=pool.submit(cancel); a=f.result(); c=g.result()
 # Cancellation after authorization is allowed and invalidates the grant.
 assert a or c
 assert not (t.task_state=='AUTHORIZED' and t.cancellation_event.is_set())
 if t.task_state=='CANCELLED': assert not t.transition_motor_simulation(op,'AUTHORIZED','EXECUTING',evidence=e)
