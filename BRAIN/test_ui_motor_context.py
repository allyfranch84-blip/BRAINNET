"""UI motor grounding contract tests. No real input or window activation."""
import math
from unittest.mock import Mock, patch
import threading
import time
import pytest

from motor_intent import validate_plan
from ui_motor_context import eligible_controls, resolve_target, center, waypoints, execute_target


def row(name='Salvar',runtime=(1,2),**extra):
    return {'name':name,'control_type':'ButtonControl','process_id':10,
            'runtime_id':runtime,'rect':(300,100,340,140),'is_enabled':True,'is_offscreen':False,
            'automation_id':'save',**extra}


def test_only_visible_named_controls_and_unique_target():
    controls=eligible_controls([row(),row('Excluir',is_enabled=False),row('Oculto',is_offscreen=True),
                                row('Outro processo',process_id=11)],10)
    assert len(controls)==1
    assert resolve_target(controls,'salvar')['status']=='RESOLVED'
    assert resolve_target(controls,'save')['status']=='RESOLVED'
    assert resolve_target(controls,'missing')['status']=='TARGET_NOT_FOUND'
    duplicates=eligible_controls([row(),row(runtime=(1,3))],10)
    assert resolve_target(duplicates,'Salvar')['status']=='TARGET_AMBIGUOUS'


def test_long_move_is_bounded_and_ends_at_target():
    start,target=(10,20),(1500,400)
    points=waypoints(start,target)
    assert points[-1]==target and len(points)>1
    assert all(0<math.dist(a,b)<=150 for a,b in zip([start]+points,points))
    assert waypoints(target,target)==[]


def test_named_target_has_no_model_supplied_coordinates():
    assert validate_plan({'status':'execute','steps':[{'action':'move_to','target':'Salvar'}]})
    assert validate_plan({'status':'execute','steps':[{'action':'click_target','target':'Salvar','button':'left','count':1}]})
    with pytest.raises(ValueError):
        validate_plan({'status':'execute','steps':[{'action':'move_to','target':'Salvar','x':123}]})
    with pytest.raises(ValueError):
        validate_plan({'status':'execute','steps':[{'action':'move_to','target':'Salvar'},{'action':'click','button':'left','count':1}]})


@pytest.mark.parametrize('action', ['move_to','click_target'])
@pytest.mark.parametrize('initial_focus', [1, 99])
def test_target_motor_reobserves_and_uses_existing_effector(action, initial_focus):
    from execution_authority import authorization_scope, _physical_move_scope
    window={'hwnd':1,'pid':10,'started':100,'app':'test.exe'}
    state={'status':'OBSERVED','coordinate_space':'PHYSICAL','cursor':(10,20),'monitor':'DISPLAY','monitor_rect':(0,0,800,600)}
    controls=eligible_controls([row()],10)
    eye=Mock()
    motor=Mock()
    def move(x,y,**kwargs):
        proposal=_physical_move_scope.get()
        assert proposal.start==state['cursor'] and proposal.target==(x,y)
        state['cursor']=(x,y)
        return True
    motor.mouse_move.side_effect=move
    motor.mouse_click.return_value=True
    step={'action':action,'target':'Salvar'}
    if action=='click_target':
        step.update(button='left',count=1)
    with authorization_scope(threading.Event()),patch('ui_motor_context.same_window',return_value=True), \
         patch('ui_motor_context.observe',return_value={'status':'OBSERVED','controls':controls}), \
         patch('ui_motor_context.hit_target',return_value=True), \
         patch('capability_lab.observe_cursor_monitors',return_value={'interactive_desktop_verified':True}), \
         patch('capability_lab.observe_physical_monitor',side_effect=lambda:dict(state)), \
         patch('win32gui.GetForegroundWindow',return_value=1),patch('effector.user32') as native:
        native.GetAsyncKeyState.return_value=0
        result=execute_target(window,step,eye,motor,task_id='test',deadline=time.monotonic()+30,
                              expected_cursor=dict(state),expected_foreground=initial_focus)
    assert result['target']==center(controls[0]['rect'])==state['cursor']
    assert motor.mouse_move.call_count>=2
    if action=='click_target':
        assert result['status']=='INPUT_SENT'
        motor.mouse_click.assert_called_once_with('left',1)
    else:
        assert result['status']=='EFFECT_VERIFIED'
        motor.mouse_click.assert_not_called()


def test_unrelated_focus_change_blocks_before_motor():
    from execution_authority import authorization_scope
    window={'hwnd':1,'pid':10,'started':100,'app':'test.exe'}
    state={'status':'OBSERVED','coordinate_space':'PHYSICAL','cursor':(10,20),'monitor':'DISPLAY','monitor_rect':(0,0,800,600)}
    motor=Mock()
    with authorization_scope(threading.Event()),patch('ui_motor_context.same_window',return_value=True), \
         patch('capability_lab.observe_cursor_monitors',return_value={'interactive_desktop_verified':True}), \
         patch('capability_lab.observe_physical_monitor',return_value=state), \
         patch('win32gui.GetForegroundWindow',return_value=555),patch('effector.user32') as native:
        native.GetAsyncKeyState.return_value=0
        result=execute_target(window,{'action':'move_to','target':'Salvar'},Mock(),motor,
                              task_id='test',deadline=time.monotonic()+30,expected_cursor=state,expected_foreground=99)
    assert result['code']=='FOCUS_CHANGED' and result['observed_focus']==555
    motor.mouse_move.assert_not_called()


def test_app_launch_schema_accepts_only_supported_application():
    assert validate_plan({'status':'execute','steps':[{'action':'open_app','target':'paint'}]})
    with pytest.raises(ValueError):
        validate_plan({'status':'execute','steps':[{'action':'open_app','target':'cmd.exe'}]})


def test_focus_handoff_from_own_chat_to_selected_window():
    import os
    from ui_motor_context import activate_selected_window
    from execution_authority import authorization_scope
    window={'hwnd':1,'pid':10,'started':100,'app':'test.exe'}
    with authorization_scope(threading.Event()),patch('ui_motor_context.same_window',return_value=True), \
         patch('win32gui.GetForegroundWindow',side_effect=[99,1]), \
         patch('win32process.GetWindowThreadProcessId',return_value=(1,os.getpid())), \
         patch('win32gui.SetForegroundWindow') as focus:
        result=activate_selected_window(window,99,deadline=time.monotonic()+5)
    assert result['status']=='READY' and result['observed_focus']==1
    focus.assert_called_once_with(1)


def test_scan_reports_filtered_controls_without_allowing_them_as_targets():
    from ui_motor_context import observe
    window={'hwnd':1,'pid':10,'started':100,'app':'test.exe'}
    eye=Mock()
    eye.scan_uia_properties.return_value=[row(),row('Pincéis',runtime=(3,4),is_offscreen=True)]
    with patch('ui_motor_context.same_window',return_value=True):
        scene=observe(window,eye,foreground=True)
    assert scene['raw_count']==2 and len(scene['controls'])==1
    assert scene['rejection_counts']['fora da vista']==1
    assert scene['rejected'][0]['name']=='Pincéis'
    assert resolve_target(scene['controls'],'Pincéis')['status']=='TARGET_NOT_FOUND'
