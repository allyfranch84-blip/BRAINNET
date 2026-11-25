"""All tests are pure or mocked; no real cursor, click, scroll or model invocation."""
import pytest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from motor_intent import parse_response, resolve_move, validate_plan


def test_geometry_covers_all_directions_and_preserves_monitor():
    start, rect = (200,200), (0,0,500,500)
    for direction, point in [('left',(50,200)),('right',(350,200)),('up',(200,50)),('down',(200,350))]:
        assert resolve_move(start,rect,direction,150)[0] == point
    assert resolve_move(start,rect,'any',150,previous='right',choose=lambda choices:choices[0])[1] != 'right'
    with pytest.raises(ValueError):
        resolve_move((20,20),rect,'left',150)


def test_invalid_actions_and_nonexecution_are_rejected():
    for step in [
        {'action':'move','direction':'left','distance':True},
        {'action':'move','direction':'right','distance':151},
        {'action':'move','direction':'right','distance':150,'x':123},
        {'action':'click','button':'invalid','count':1},
        {'action':'scroll','direction':'up','count':11},
        {'action':'shell','command':'example'},
    ]:
        with pytest.raises(ValueError):
            validate_plan({'status':'execute','steps':[step]})
    with pytest.raises(ValueError):
        validate_plan({'status':'none','steps':[{'action':'click','button':'left','count':1}]})
    with pytest.raises(ValueError):
        parse_response('not json')


def test_semantic_plan_executes_multiple_observed_movements_and_reuses_verified_plan():
    from test_p44_direct_move import _bridge
    state = {'status':'OBSERVED','coordinate_space':'PHYSICAL','cursor':(200,200),'monitor':'DISPLAY','monitor_rect':(0,0,800,800)}
    bridge,kernel,patches = _bridge(state)
    def perform(proposal, approval, budget):
        assert approval.consume(proposal,state)
        state['cursor'] = proposal.target
        return {'status':'EFFECT_VERIFIED','after':proposal.target}
    response = SimpleNamespace(text='{"intent_type":"composite","steps":[{"action":"move","direction":"up","distance":50},{"action":"move","direction":"left","distance":30}]}',finish_reason='stop',output_tokens=60)
    try:
        with patch.dict('os.environ',{'BRAINNET_MOTOR_SEMANTIC':'1'}), \
             patch('capability_lab.observe_physical_monitor',side_effect=lambda: dict(state)), \
             patch('inference_backend.HTTPInferenceBackend.chat',return_value=response) as model, \
             patch.object(bridge,'_dispatch_direct_p4_move',side_effect=perform):
            first=bridge.send_command('suba um pouco e vá para a esquerda')
            second=bridge.send_command('suba um pouco e vá para a esquerda')
        assert first['status']==second['status']=='EFFECT_VERIFIED'
        assert state['cursor']==(140,100)
        assert model.call_count==1
        assert second['motor_source']=='VERIFIED_SESSION_CACHE'
    finally:
        for p in reversed(patches):p.stop()


def test_semantic_question_does_not_execute():
    from test_p44_direct_move import _bridge
    bridge,kernel,patches = _bridge({})
    response = SimpleNamespace(text='{"intent_type":"none"}',finish_reason='stop',output_tokens=12)
    try:
        with patch.dict('os.environ',{'BRAINNET_MOTOR_SEMANTIC':'1'}), \
             patch('inference_backend.HTTPInferenceBackend.chat',return_value=response), \
             patch.object(bridge,'_dispatch_direct_p4_move') as dispatch:
            result=bridge.send_command('como mover o mouse?')
        assert result['dispatched'] is False
        dispatch.assert_not_called()
    finally:
        for p in reversed(patches):p.stop()


def test_contaminated_atomic_model_response_is_rejected_before_dispatch():
    """A prior task cannot turn a new atomic open into a sequence."""
    from test_p44_direct_move import _bridge
    state = {'status':'OBSERVED','coordinate_space':'PHYSICAL','cursor':(200,200),'monitor':'DISPLAY','monitor_rect':(0,0,800,800)}
    bridge,kernel,patches = _bridge(state)
    # This is deliberately malformed for the new discriminator: it claims an
    # atomic intent but carries a second historical UI action.
    response = SimpleNamespace(
        text=('{"intent_type":"atomic","step":{"action":"open_app","target":"notepad"},'
              '"steps":[{"action":"move_to","target":"Ampliar"}]}'),
        finish_reason='stop', output_tokens=20)
    try:
        with patch.dict('os.environ',{'BRAINNET_MOTOR_SEMANTIC':'1'}), \
             patch('capability_lab.observe_physical_monitor',return_value=state), \
             patch('inference_backend.HTTPInferenceBackend.chat',return_value=response), \
             patch.object(bridge,'_dispatch_direct_p4_move') as dispatch:
            result=bridge.send_command('Abra o Bloco de Notas')
        assert result['status']=='UNAVAILABLE'
        assert result['dispatched'] is False
        dispatch.assert_not_called()
    finally:
        for p in reversed(patches):p.stop()


def test_backend_unavailable_preserves_delegated_move_without_model():
    from test_p44_direct_move import _bridge
    from inference_backend import BackendUnavailable
    state = {'status':'OBSERVED','coordinate_space':'PHYSICAL','cursor':(200,200),'monitor':'DISPLAY','monitor_rect':(0,0,800,800)}
    bridge,kernel,patches = _bridge(state)
    def perform(proposal, approval, budget):
        assert approval.consume(proposal,state)
        state['cursor'] = proposal.target
        return {'status':'EFFECT_VERIFIED','after':proposal.target}
    try:
        with patch.dict('os.environ',{'BRAINNET_MOTOR_SEMANTIC':'1'}), \
             patch('capability_lab.observe_physical_monitor',side_effect=lambda: dict(state)), \
             patch('inference_backend.HTTPInferenceBackend.chat',side_effect=BackendUnavailable('offline')), \
             patch.object(bridge,'_dispatch_direct_p4_move',side_effect=perform) as dispatch:
            result=bridge.send_command('mova o mouse em qualquer direção')
            assert result['status']=='EFFECT_VERIFIED'
            assert result['motor_source']=='BUILTIN_VERIFIED_CAPABILITY'
            assert state['cursor']!=(200,200)
            assert bridge.send_command('como mover o mouse?')['dispatched'] is False
            assert dispatch.call_count==1
    finally:
        for p in reversed(patches):p.stop()


def test_copy_history_available_in_minimal_and_failure_not_reported_as_success():
    from test_p44_direct_move import _bridge
    bridge,kernel,patches = _bridge({})
    bridge._chat_history=[{'role':'user','text':'teste'}, {'role':'ai','text':'resposta'}]
    try:
        with patch.object(bridge,'copy_text',return_value={'ok':True}) as copy:
            assert bridge.send_command('/copy all')['status']=='COPIED'
            assert 'teste' in copy.call_args.args[0]
        with patch.object(bridge,'copy_text',return_value={'ok':False}):
            assert bridge.send_command('/copy all')['status']=='ACTION_FAILED'
    finally:
        for p in reversed(patches):p.stop()


def test_long_relative_move_is_split_at_executor_boundary():
    plan=parse_response('{"status":"execute","steps":[{"action":"move","direction":"up","distance":300}]}')
    assert [s['distance'] for s in plan['steps']]==[150,150]
    assert all(s['direction']=='up' for s in plan['steps'])
    with pytest.raises(ValueError):
        parse_response('{"status":"execute","steps":[{"action":"move","direction":"up","distance":1201}]}')


def test_monitor_query_can_be_composed_but_never_carries_native_input():
    assert parse_response('{"status":"execute","steps":[{"action":"inspect_monitor","monitor":2}]}')
    assert validate_plan({'status':'execute','steps':[{'action':'inspect_monitor','monitor':2},{'action':'open_app','target':'paint'}]})
    with pytest.raises(ValueError):
        validate_plan({'status':'execute','steps':[{'action':'inspect_monitor','monitor':2,'button':'left'}]})
