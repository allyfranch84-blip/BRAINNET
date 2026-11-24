"""Pure sequence tests: no desktop input, LLM, or Windows dependencies."""
from motor_intent import parse_response
from motor_sequence import execute_sequence, groups


def plan():
    return parse_response('{"status":"execute","steps":[{"action":"open_app","target":"paint"},{"action":"move_to","target":"Ampliar"},{"action":"click_target","target":"Ampliar","button":"left","count":1},{"action":"move","direction":"down","distance":100}]}')


def test_sequence_order_and_input_effect_distinction():
    seen=[]
    def run(group, receipts):
        seen.append(group[0]['action'])
        assert len(receipts)==len(seen)-1
        return {'status':'INPUT_SENT' if group[0]['action']=='click_target' else 'EFFECT_VERIFIED','reply':'ok','dispatched':True}
    result=execute_sequence(plan(),run,check_active=lambda:None)
    assert seen==['open_app','move_to','click_target','move']
    assert result['completed_steps']==result['total_steps']==4
    assert result['status']=='INPUT_SENT'


def test_failure_stops_remaining_steps():
    seen=[]
    def run(group, receipts):
        seen.append(group[0]['action'])
        return {'status':'EFFECT_VERIFIED' if len(seen)==1 else 'ACTION_BLOCKED','reply':'result','dispatched':len(seen)==1}
    result=execute_sequence(plan(),run,check_active=lambda:None)
    assert seen==['open_app','move_to']
    assert result['status']=='PARTIAL' and result['completed_steps']==1


def test_cancellation_prevents_dispatch():
    def cancel():
        raise RuntimeError('cancelled')
    def run(*args):
        raise AssertionError('must not dispatch')
    result=execute_sequence(plan(),run,check_active=cancel)
    assert result['status']=='CANCEL_REQUESTED'
    assert result['completed_steps']==0 and result['dispatched'] is False


def test_consecutive_moves_preflight_together_and_click_is_separate():
    value=parse_response('{"status":"execute","steps":[{"action":"move","direction":"up","distance":300},{"action":"click","button":"left","count":1},{"action":"move","direction":"down","distance":100}]}')
    assert [len(g) for g in groups(value['steps'])]==[2,1,1]
