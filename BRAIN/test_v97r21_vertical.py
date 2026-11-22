import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PIL import Image
from BRAINNET import BrainnetBridge
from causal_trajectory import CausalTrajectoryEngine
from ui_tars_protocol import UIProtocolController
from adaptive_resource_controller import ExecutionLimits, SharedTaskBudget, BudgetExhausted, current_task_budget


def make_budget(name, seconds=5):
    return SharedTaskBudget(name, 'DEEP', time.monotonic()+seconds, threading.Event(), ExecutionLimits(2,2,2,100))


def test_vertical_same_identity_across_thread_and_visual():
    bridge=object.__new__(BrainnetBridge); bridge._chat_history=[]
    bridge.get_effort_mode=Mock(return_value={'mode':'DEEP'})
    engine=object.__new__(CausalTrajectoryEngine); engine.syntactic_pdag=None; engine.pdag=None
    seen=[]
    def generated(self, instruction, budget=None):
        seen.append(('inference',budget.task_id,budget.deadline_monotonic))
        budget.reserve('inference', estimated_tokens=5)
        return 'poema simulado'
    vision=Mock(); context=Mock(); snapshot={'hwnd':1,'process_name':'notepad.exe','window_rect':(0,0,100,100)}
    vision.capture_ui_observation.return_value=(Image.new('RGB',(100,100)),(0,0,100,100),snapshot)
    vision.describe_ui_with_protocol.return_value={'action_type':'finished','action_inputs':{'content':'done'}}
    controller=UIProtocolController(vision,SimpleNamespace(),context)
    def impl(text):
        budget=current_task_budget.get(); seen.append(('kernel',budget.task_id,budget.deadline_monotonic))
        async def pipeline():
            loop=asyncio.get_running_loop()
            plan=await loop.run_in_executor(None,engine.decompor_trajetoria_cognitiva,'abra o notepad e escreva um poema',budget)
            assert plan['pipeline']
            return await controller.run_task(text,task_budget=budget)
        result=asyncio.run(pipeline()); seen.append(('visual',result['task_id'],budget.deadline_monotonic))
        return {'reply':'simulado','logs':[],'visual':result}
    bridge._send_command_impl=impl
    with patch.object(CausalTrajectoryEngine,'_generate_creative_text',generated): result=bridge.send_command('desenhe')
    budget=result['task_budget']
    assert len({item[1] for item in seen})==1 and seen[0][1]==budget['task_id']
    assert len({item[2] for item in seen})==1
    assert budget['planning_steps_used']==1 and budget['inference_calls_used']==2 and budget['visual_iterations_used']==1
    assert budget['token_usage']['estimated']==5 and result['visual']['sucesso_real'] is False


def test_atomic_limits_cancellation_and_task_isolation():
    a,b=make_budget('a'),make_budget('b')
    a.reserve('inference');a.reserve('inference')
    try: a.reserve('inference')
    except BudgetExhausted: pass
    else: assert False
    assert a.cancellation_event.is_set() and a.inference_calls_used==2
    b.reserve('inference'); assert b.inference_calls_used==1 and not b.cancellation_event.is_set()
    expired=make_budget('late',-1)
    try: expired.reserve('visual')
    except BudgetExhausted: pass
    else: assert False
    assert expired.visual_iterations_used==0


def test_concurrent_reservations_never_exceed_limit():
    from concurrent.futures import ThreadPoolExecutor
    budget=make_budget('parallel')
    def reserve(_):
        try:
            budget.reserve('inference')
            return True
        except BudgetExhausted:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes=list(pool.map(reserve, range(20)))
    assert sum(outcomes)==2 and budget.inference_calls_used==2
