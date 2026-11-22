import time
from types import SimpleNamespace
from unittest.mock import Mock
from BRAINNET import BrainnetBridge

D = {'name':'Pincéis','hwnd':1,'pid':2,'process_started':123.0,'runtime_id':(3,4)}

def observed(name='Pincéis', hwnd=1, recommendation='REVALIDATE_BEFORE_ACTION'):
    return {'status':'OBSERVED','target_assessment':{'recommendation':recommendation},
            'scene':{'observation_id':'obs','observed_at':time.monotonic(),
                     'app':{'hwnd':hwnd,'pid':2,'process_started':123.0},
                     'frame':{'window_rect':(0,0,100,100)},
                     'elements':[{'name':name,'evidence':[{'source':'UIA','reference':str((3,4))}]}]}}

def make_bridge(observations):
    b=object.__new__(BrainnetBridge)
    b._kernel=SimpleNamespace(observe_ui_scene=Mock(side_effect=observations))
    return b

def test_missing_then_reobserved_and_validated():
    b=make_bridge([observed(name='outro'),observed()])
    result=b._prepare_contextual_scene(D)
    assert result['status']=='READY' and result['attempts']==2
    assert b._kernel.observe_ui_scene.call_count==2

def test_ambiguous_and_changed_window_block():
    for first in (observed(recommendation='REOBSERVE_OR_ALTERNATIVE'), observed(hwnd=99)):
        b=make_bridge([first,first])
        assert b._prepare_contextual_scene(D)['status']=='ACTION_BLOCKED'
        assert b._kernel.observe_ui_scene.call_count==2

def test_absent_target_never_dispatches():
    b=make_bridge([observed(name='outro')]*2)
    b._contextual_grounder=SimpleNamespace(resolve=Mock(return_value={'status':'READY_FOR_UIA','target_descriptor':D}))
    out=b._executar_comando_interno('clique pincéis','clique pincéis','clique pincéis')
    assert out['contextual_result']['status']=='ACTION_BLOCKED'
    assert not hasattr(b._kernel,'bridge')
