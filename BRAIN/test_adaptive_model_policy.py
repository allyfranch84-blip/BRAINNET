import json
import pytest
from adaptive_model_policy import select_model, catalog, benchmark, PROBES


def test_priority_and_fallback():
    models = {'qwen2.5:1.5b', 'qwen3:4b-instruct', 'qwen3:4b-thinking'}
    assert [select_model(m, models)['model'] for m in ('FAST','BALANCED','DEEP')] == ['qwen2.5:1.5b','qwen3:4b-instruct','qwen3:4b-thinking']
    assert select_model('DEEP', {'qwen3:4b-instruct'})['fallback']
    assert select_model('DEEP', {'qwen3-vl:8b'})['model'] is None
    assert select_model('DEEP', models, 'missing')['status'] == 'UNAVAILABLE'


@pytest.mark.parametrize('rows', [None, [{}], [{'name': 1}], [{'name': ''}]])
def test_invalid_catalog(rows):
    with pytest.raises(ValueError):
        catalog(lambda p: {'version':'test'} if p.endswith('version') else {'models':rows})


def test_no_generation_without_installed_model():
    calls = []
    def api(path, *a, **kw):
        calls.append(path)
        return {'version':'test'} if path.endswith('version') else {'models':[]}
    assert benchmark('DEEP', api)[0]['status'] == 'BLOCKED'
    assert '/api/generate' not in calls


def test_benchmark_checks_results_and_metrics():
    replies = iter([p[2] for p in PROBES])
    def api(path, payload=None, timeout=None):
        if path.endswith('version'): return {'version':'test'}
        if path.endswith('tags'): return {'models':[{'name':'qwen3:4b-instruct'}]}
        assert path == '/api/generate' and payload['model'] == 'qwen3:4b-instruct'
        return {'done':True,'done_reason':'stop','response':json.dumps(next(replies)), 'eval_count':10,'eval_duration':500000000}
    result = benchmark('DEEP', api)
    assert len(result) == 3 and all(r['status']=='PASS_REAL' for r in result)
    assert result[0]['tokens_per_second'] == 20


def test_truncated_or_wrong_answer_is_failure():
    def api(path, *a, **kw):
        if path.endswith('version'): return {'version':'test'}
        if path.endswith('tags'): return {'models':[{'name':'qwen2.5:1.5b'}]}
        return {'done':True,'done_reason':'length','response':'{"acao":"nenhuma"}'}
    assert all(r['status']=='FAIL' for r in benchmark('FAST', api))
