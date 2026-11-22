import json
from unittest.mock import Mock
from test_v97r22_production import make_bridge


def test_task_events_share_identity_and_real_mode():
    bridge=make_bridge()
    bridge._window=Mock()
    bridge._send_command_impl=Mock(return_value={'reply':'ok','logs':[]})
    result=bridge.send_command('teste')
    scripts=[call.args[0] for call in bridge._window.evaluate_js.call_args_list if 'aios:task' in call.args[0]]
    assert len(scripts)==2
    details=[json.JSONDecoder().raw_decode(script.split('{ detail: ',1)[1])[0] for script in scripts]
    assert [event['phase'] for event in details]==['PROCESSING','FINISHED']
    assert all(event['budget']['task_id']==result['task_budget']['task_id'] for event in details)
    assert all(event['configured']=='FAST' and event['effective']=='FAST' for event in details)


def test_modes_are_accepted_and_cancel_is_not_finished():
    from adaptive_resource_controller import current_task_budget
    for mode in ('FAST','BALANCED','DEEP','AUTO'):
        bridge=make_bridge(); bridge._window=Mock();bridge.get_effort_mode=Mock(return_value={'mode':mode})
        def impl(text):
            current_task_budget.get().cancellation_event.set()
            return {'reply':'cancelamento solicitado','logs':[]}
        bridge._send_command_impl=impl
        bridge.send_command('teste')
        scripts=[c.args[0] for c in bridge._window.evaluate_js.call_args_list if 'aios:task' in c.args[0]]
        event=json.JSONDecoder().raw_decode(scripts[-1].split('{ detail: ',1)[1])[0]
        assert event['configured']==mode and event['phase']=='CANCEL_REQUESTED'
