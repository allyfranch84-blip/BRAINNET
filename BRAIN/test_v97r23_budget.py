import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from adaptive_resource_controller import SharedTaskBudget, ExecutionLimits, BudgetExhausted


def budget():
    return SharedTaskBudget('task', 'FAST', time.monotonic()+10, threading.Event(), ExecutionLimits(2,2,2,500))


def test_reservation_and_unknown_remote_state():
    b=budget(); op=b.begin_inference(estimated_tokens=100)
    b.mark_unconfirmed(op)
    snap=b.snapshot()
    assert snap['inflight']==1 and snap['operations'][op]['status']=='CANCEL_REQUESTED_UNCONFIRMED'
    b.finish_inference(op, confirmed=False)
    assert b.snapshot()['operations'][op]['status']=='REMOTE_UNCONFIRMED'
    b.finish_inference(op, reported_tokens=30)
    assert b.snapshot()['inflight']==0 and b.snapshot()['token_usage']=={'estimated':100,'reported':30}
    b.finish_inference(op, reported_tokens=30)
    assert b.snapshot()['token_usage']['reported']==30


def test_cancel_blocks_next_reservation_without_claiming_finished():
    b=budget(); op=b.begin_inference(estimated_tokens=20); b.cancellation_event.set();b.mark_unconfirmed(op)
    try: b.begin_inference()
    except BudgetExhausted: pass
    else: assert False
    assert b.snapshot()['inflight']==1
