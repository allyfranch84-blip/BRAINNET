import io
import json
from unittest.mock import patch
from test_v97r22_production import make_bridge
from inference_backend import HTTPInferenceBackend
from adaptive_resource_controller import current_task_budget


def test_background_search_is_a_tool_without_tokens_or_gui():
    b=make_bridge()
    html=b'<a class="result__a" href="https://example.org">Fonte</a>'
    with patch('BRAINNET.urllib.request.urlopen',return_value=io.BytesIO(html)) as transport:
        result=b.send_command('pesquise estrelas')
    assert result['search_state']=='SOURCES_FOUND'
    snap=result['task_budget']
    assert snap['inference_calls_used']==0 and snap['token_usage']['estimated']==0
    assert list(snap['operations'].values())[0]['kind']=='tool'
    assert transport.call_count==1


def test_reported_tokens_are_reconciled_once():
    b=make_bridge()
    def opener(req,timeout):
        return io.BytesIO(json.dumps({'done':True,'response':'ok','eval_count':12,'prompt_eval_count':8}).encode())
    def factory(endpoint,model,kind):return HTTPInferenceBackend(endpoint,model,kind,opener=opener)
    with patch('inference_backend.HTTPInferenceBackend', side_effect=factory):
        result=b.send_command('O que é uma estrela?')
    assert result['task_budget']['token_usage']=={'estimated':200,'reported':12}
    assert result['task_budget']['inflight']==0


def test_late_search_result_is_discarded_after_cancellation():
    b=make_bridge()
    def opener(*args,**kwargs):
        current_task_budget.get().cancellation_event.set()
        return io.BytesIO(b'<a class="result__a" href="https://example.org">Fonte</a>')
    with patch('BRAINNET.urllib.request.urlopen',side_effect=opener):
        result=b.send_command('pesquise estrelas')
    assert result['status']=='BUDGET_EXHAUSTED' and 'Fonte' not in result['reply']
