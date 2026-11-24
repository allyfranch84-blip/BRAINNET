from types import SimpleNamespace
from unittest.mock import Mock, patch
import BRAINNET
from test_v97r22_production import make_bridge

def test_visual_receives_budget_and_never_calls_conversation():
    b=make_bridge(); loop=Mock();loop.is_running.return_value=True
    run=Mock(return_value=object()); b._kernel.loop=loop;b._kernel.ui_protocol=SimpleNamespace(run_task=run)
    b._falar_seguro=Mock();b._push_event=Mock();b._budgeted_conversation=Mock()
    future=Mock();future.result.return_value={'status':'ACTION_BLOCKED','sucesso_real':False,'failure_reason':'sem permissao'}
    with patch('BRAINNET.asyncio.run_coroutine_threadsafe',return_value=future):
        result=b.send_command('desenhe uma linha')
    assert run.call_count==1
    assert run.call_args.kwargs['task_budget'].task_id==result['task_budget']['task_id']
    assert result['visual_result']['status']=='ACTION_BLOCKED'
    assert 'Falha visual' not in result['reply']
    b._budgeted_conversation.assert_not_called()

def test_visual_failure_stops_without_conversation():
    b=make_bridge();loop=Mock();loop.is_running.return_value=True;b._kernel.loop=loop
    b._kernel.ui_protocol=SimpleNamespace(run_task=Mock(side_effect=RuntimeError('simulado')))
    b._falar_seguro=Mock();b._push_event=Mock();b._budgeted_conversation=Mock()
    result=b.send_command('desenhe uma linha')
    assert 'Falha visual (RuntimeError)' in result['reply']
    b._budgeted_conversation.assert_not_called()

def test_incomplete_conversation_marked_by_real_handler():
    b=make_bridge(); b._push_event=Mock()
    def fake(text):
        BRAINNET._conversation_finish_reason.set('length')
        return {'reply':'parcial','logs':[]}
    b._send_command_impl=fake
    result=b.send_command('consulta')
    assert result['status']=='INCOMPLETE'
    assert any(call.args[1].get('phase')=='INCOMPLETE' for call in b._push_event.call_args_list if call.args[0]=='aios:task')

def test_truncated_backend_response_is_incomplete():
    import io,json
    from inference_backend import HTTPInferenceBackend
    b=make_bridge(); b._push_event=Mock(); b._falar_seguro=Mock()
    def opener(request,timeout):
        return io.BytesIO(json.dumps({'done':True,'response':'parcial','done_reason':'length'}).encode())
    def factory(endpoint,model,kind): return HTTPInferenceBackend(endpoint,model,kind,opener=opener)
    with patch('inference_backend.HTTPInferenceBackend',side_effect=factory):
        result=b.send_command('O que é uma estrela?')
    assert result['status']=='INCOMPLETE'
    assert 'limite de geração' in result['reply']
