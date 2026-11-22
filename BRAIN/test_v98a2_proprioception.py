from unittest.mock import Mock, patch
from capability_lab import observe_cursor_monitors, propose_right_30, attach_motor_observation
from adaptive_resource_controller import TaskContinuity
from perception_eye import PerceptionEye


def fake_api():
    api=Mock();api.GetCursorPos.return_value=(-100,20)
    api.EnumDisplayMonitors.return_value=[(1,0,(-500,0,0,500)),(2,0,(0,0,800,600))]
    api.GetMonitorInfo.side_effect=lambda handle: {'Monitor':(-500,0,0,500) if handle==1 else (0,0,800,600), 'Work':(-500,0,0,480) if handle==1 else (0,0,800,580),'Device':f'D{handle}'}
    api.MonitorFromPoint.return_value=1
    return api


def test_negative_coordinates_and_safe_proposal():
    obs=observe_cursor_monitors(fake_api())
    assert obs['cursor']==(-100,20) and len(obs['monitors'])==2
    assert propose_right_30(obs)['target']==(-70,20)
    obs['cursor']=(-20,20)
    assert propose_right_30(obs)['status']=='OUT_OF_BOUNDS'


def test_cursor_api_failure_is_not_zero():
    api=fake_api();api.GetCursorPos.side_effect=OSError('not accessible')
    obs=observe_cursor_monitors(api)
    assert obs['cursor'] is None and obs['cursor_status']=='ERROR'
    assert propose_right_30(obs)['status']=='INCONCLUSIVE'


def test_observation_requires_confirmed_desktop_for_task():
    task=TaskContinuity('id','observe')
    obs=observe_cursor_monitors(fake_api());obs['interactive_desktop_verified']=False
    assert not attach_motor_observation(task,obs) and task.last_validated_observation is None
    obs['interactive_desktop_verified']=True
    assert attach_motor_observation(task,obs)
    assert task.last_validated_observation['execution_authorized'] is False


def test_uia_walk_accepts_three_item_entries():
    root=Mock();root.Exists.return_value=True
    control=Mock();control.Name='TESTE A';control.AutomationId='lab_button_a';control.ControlTypeName='ButtonControl';control.ProcessId=5
    control.BoundingRectangle=type('Rect',(),dict(left=0,top=0,right=10,bottom=10))()
    control.GetRuntimeId.return_value=(1,2);control.IsEnabled=True;control.IsOffscreen=False
    fake=Mock();fake.ControlFromHandle.return_value=root;fake.WalkTree.return_value=[(control,1,0)]
    fake.UIAutomationInitializerInThread.return_value.__enter__=Mock(return_value=None)
    fake.UIAutomationInitializerInThread.return_value.__exit__=Mock(return_value=None)
    with patch('perception_eye.auto',fake),patch('perception_eye.HAS_UIA_NATIVE',True):
        rows=PerceptionEye.__new__(PerceptionEye).scan_uia_properties(1)
    assert rows[0]['name']=='TESTE A' and rows[0]['automation_id']=='lab_button_a'
