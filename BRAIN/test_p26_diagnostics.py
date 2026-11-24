from dataclasses import replace
from unittest.mock import patch
from test_p25_physical_approval import make

def obs(p):
 return {'status':'OBSERVED','coordinate_space':'PHYSICAL','cursor':p.start,'monitor':p.monitor,'monitor_rect':p.monitor_rect}

def test_diagnostic_codes_and_atomic_consumption():
 cases=[('CURSOR_POSITION_CHANGED',{'cursor':(21,30)}),('MONITOR_CHANGED',{'monitor':'other'}),('MONITOR_GEOMETRY_CHANGED',{'monitor_rect':(0,0,99,100)}),('COORDINATE_SPACE_MISMATCH',{'coordinate_space':'UNKNOWN'}),('OBSERVATION_UNAVAILABLE',{'status':'ERROR'})]
 for code,delta in cases:
  p,a=make();assert a.approve_explicitly(p.proposal_id)
  r=a.consume_diagnostic(p,{**obs(p),**delta});assert r['code']==code
  assert a.consume_diagnostic(p,obs(p))['code']=='APPROVAL_ALREADY_CONSUMED'

def test_wrong_identity_and_missing_and_expired():
 p,a=make();assert a.consume_diagnostic(p,obs(p))['code']=='APPROVAL_MISSING'
 assert a.approve_explicitly(p.proposal_id)
 assert a.consume_diagnostic(replace(p,task_id='different'),obs(p))['code']=='PROPOSAL_MISMATCH'
 p,a=make();assert a.approve_explicitly(p.proposal_id)
 with patch('execution_authority.time.monotonic',return_value=p.deadline_monotonic+1):
  assert a.consume_diagnostic(p,obs(p))['code']=='APPROVAL_EXPIRED'
