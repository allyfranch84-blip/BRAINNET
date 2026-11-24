"""Independent sensor fusion contract. No Windows input or live sensors."""
from perceptual_present import PerceptualPresent


def make():
    time=[10.]
    present=PerceptualPresent(None,clock=lambda:time[0])
    window={'hwnd':41,'pid':2,'started':1.,'owned':False,'minimized':False,'app':'paint.exe','rect':(0,0,100,100)}
    present.publish('windows',{'windows':[window]},9.8,9.9)
    present.publish('spatial',{'foreground':41,'cursor':{}},9.95,10.)
    return present,time,window


def test_zero_focus_is_transition_not_disappearance():
    present,time,window=make()
    time[0]=10.1
    present.publish('spatial',{'foreground':0,'cursor':{}},10.,10.1)
    state=present.snapshot()
    assert state['focus_state']=='TRANSITION'
    assert state['external_foreground'] is None
    assert state['last_external']==window
    assert state['action_authorized'] is False


def test_old_sensor_result_cannot_replace_newer_evidence():
    present,time,window=make()
    assert present.publish('spatial',{'foreground':0},9.8,9.9) is False
    assert present.snapshot()['foreground']==41


def test_window_reuse_or_closure_invalidates_recent_external_context():
    present,time,window=make()
    time[0]=10.1
    present.publish('spatial',{'foreground':0},10.,10.1)
    present.publish('windows',{'windows':[{**window,'started':2.}]},10.,10.1)
    assert present.snapshot()['last_external'] is None


def test_stale_inventory_does_not_authorize_context_or_preserve_fresh_claim():
    present,time,window=make()
    time[0]=13.
    state=present.snapshot()
    assert state['windows']==[] and state['last_external'] is None
    assert state['channels']['windows']['status']=='STALE'
    assert state['channels']['spatial']['status']=='STALE'


def test_uia_evidence_is_not_current_after_switch():
    present,time,window=make()
    present.publish('uia',{'status':'OBSERVED','window':window,'count':2},9.9,10.)
    assert present.snapshot()['channels']['uia']['status']=='OBSERVED'
    time[0]=10.1
    present.publish('spatial',{'foreground':0},10.,10.1)
    assert present.snapshot()['channels']['uia']['status']=='CONTEXT_CHANGED'


def test_monitor_query_excludes_minimized_and_outside_windows():
    from perceptual_present import describe_monitor
    present,time,window=make()
    present.publish('spatial',{'foreground':41,'cursor':{},'monitors':[{'device':'DISPLAY2','rect':(100,0,200,100)}]},9.95,10.)
    present.publish('windows',{'windows':[dict(window,z_index=0),dict(window,hwnd=42,app='visible.exe',rect=(100,0,200,100),z_index=1),dict(window,hwnd=43,app='hidden.exe',rect=(100,0,200,100),minimized=True,z_index=2)]},9.9,10.)
    reply=describe_monitor(present.snapshot(),2)['reply']
    assert 'visible.exe' in reply and 'hidden.exe' not in reply and 'paint.exe' not in reply
