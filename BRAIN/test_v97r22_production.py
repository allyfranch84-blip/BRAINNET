import io, json
from types import SimpleNamespace
from unittest.mock import Mock, patch
from concurrent.futures import ThreadPoolExecutor
from BRAINNET import BrainnetBridge
from theory_of_mind import MotorGateState
from inference_backend import HTTPInferenceBackend


def make_bridge():
    b=object.__new__(BrainnetBridge)
    b._kernel=SimpleNamespace(esta_dormindo=False,ultimo_toque_ai=0,
        context_engine=SimpleNamespace(capture_foreground_context=lambda:{}),
        router=SimpleNamespace(evaluate_route=lambda *a:SimpleNamespace(mode='DEEP_PATH')),
        record_situation_event=Mock(),read_situation_evidence=Mock(return_value=None))
    b._window=None;b._chat_history=[];b._last_executed_task='';b._modo_coder_ativo=False
    b._contextual_grounder=SimpleNamespace(context=None)
    b._tom=SimpleNamespace(evaluate_intent=lambda *a:SimpleNamespace(gate=MotorGateState.NO_GO,is_physical_world=False))
    b._falar_seguro=Mock();b.get_effort_mode=Mock(return_value={'mode':'FAST'})
    return b


def test_real_send_command_to_adapter_with_unique_task_id():
    b=make_bridge(); requests=[]
    def opener(req,timeout):
        requests.append((req,timeout))
        return io.BytesIO(json.dumps({'done':True,'response':'Resposta simulada'}).encode())
    def factory(endpoint,model,kind):return HTTPInferenceBackend(endpoint,model,kind,opener=opener)
    with patch('inference_backend.HTTPInferenceBackend', side_effect=factory):
        result=b.send_command('O que é uma estrela?')
    assert result['reply']=='Resposta simulada'
    task=result['task_budget']; assert task['inference_calls_used']==1 and task['backend']=='ollama'
    assert task['token_usage']['estimated']==200 and task['token_usage']['reported'] is None
    events=b._kernel.record_situation_event.call_args_list
    assert all(call.args[0]==task['task_id'] for call in events)
    assert json.loads(requests[0][0].data)['options']['num_ctx']==2048


def test_backend_failure_is_explicit():
    b=make_bridge()
    def fail(*args,**kwargs):raise OSError('unavailable')
    def factory(endpoint,model,kind):return HTTPInferenceBackend(endpoint,model,kind,opener=fail)
    with patch('inference_backend.HTTPInferenceBackend', side_effect=factory):
        result=b.send_command('O que é uma estrela?')
    assert 'Não foi possível' in result['reply']
    assert result['task_budget']['task_state']=='INFERENCE_FAILED'
    assert result['task_budget']['inference_calls_used']==1


def test_timeout_is_reported_without_fabricated_answer():
    b=make_bridge()
    def fail(*args,**kwargs): raise TimeoutError('timeout')
    def factory(endpoint,model,kind): return HTTPInferenceBackend(endpoint,model,kind,opener=fail)
    with patch('inference_backend.HTTPInferenceBackend', side_effect=factory): result=b.send_command('O que é uma estrela?')
    assert 'InferenceTimeout' in result['reply'] and result['task_budget']['task_state']=='INFERENCE_FAILED'


def test_cancelled_after_transport_discards_result():
    from adaptive_resource_controller import current_task_budget
    b=make_bridge()
    def opener(req,timeout):
        current_task_budget.get().cancellation_event.set()
        return io.BytesIO(json.dumps({'done':True,'response':'não usar'}).encode())
    def factory(endpoint,model,kind): return HTTPInferenceBackend(endpoint,model,kind,opener=opener)
    with patch('inference_backend.HTTPInferenceBackend', side_effect=factory): result=b.send_command('O que é uma estrela?')
    assert result['status']=='BUDGET_EXHAUSTED' and 'não usar' not in result['reply']


def test_parallel_commands_have_separate_ids():
    def opener(req,timeout):return io.BytesIO(json.dumps({'done':True,'response':'ok'}).encode())
    def factory(endpoint,model,kind):return HTTPInferenceBackend(endpoint,model,kind,opener=opener)
    with patch('inference_backend.HTTPInferenceBackend', side_effect=factory):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:make_bridge().send_command('O que é uma estrela?'),range(2)))
    assert results[0]['task_budget']['task_id'] != results[1]['task_budget']['task_id']
    assert all(result['task_budget']['inference_calls_used']==1 for result in results)
