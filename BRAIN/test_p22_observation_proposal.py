import pytest
from capability_lab import prepare_delegated_observation

def observation():
 return {'cursor':(-40,10),'cursor_status':'OK','monitor_status':'OK','interactive_desktop_verified':True,'coordinates_compatible':True,'cursor_monitor':{'device':'DISPLAY2','monitor_rect':(-100,0,0,100)}}

def test_immutable_proposal_secondary_negative():
 p=prepare_delegated_observation('task',observation(),(-100,0,0,100),deadline_monotonic=20,clock=lambda:10)
 assert p['target']==(-20,10) and p['task_id']=='task' and p['execution_authorized'] is False
 with pytest.raises(TypeError): p['target']=(1,2)

def test_dpi_unavailable_and_expired():
 x=observation();x['coordinates_compatible']=False
 assert prepare_delegated_observation('task',x,(-100,0,0,100),deadline_monotonic=20,clock=lambda:10)['status']=='COORDINATE_MISMATCH'
 assert prepare_delegated_observation('task',observation(),(-100,0,0,100),deadline_monotonic=9,clock=lambda:10)['status']=='ACTION_BLOCKED'
