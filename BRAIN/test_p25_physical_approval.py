import time,uuid,threading
from unittest.mock import Mock,patch
import pytest
import effector
from execution_authority import PhysicalMoveProposal,PhysicalMoveApproval,authorization_scope
from actuator_bridge import ActuatorBridge
class Fake:
 def __init__(self,fail=False):self.pos=(20,30);self.fail=fail;self.sets=0
 def GetPhysicalCursorPos(self,p):p._obj.x,p._obj.y=self.pos;return 1
 def SetPhysicalCursorPos(self,x,y):
  self.sets+=1
  if self.fail:return 0
  self.pos=(x,y);return 1

def make(deadline=None):
 p=PhysicalMoveProposal('task',uuid.uuid4().hex,(20,30),(30,30),'DISPLAY',(0,0,100,100),0,deadline or time.monotonic()+30)
 return p,PhysicalMoveApproval(p)

def invoke(p,a,*,pos=(20,30),fail=False):
 f=Fake(fail); bridge=ActuatorBridge(effector_instance=effector.Effector())
 async def call_direct(fn,*args,**kwargs):return fn(*args,**kwargs)
 obs={'status':'OBSERVED','coordinate_space':'PHYSICAL','cursor':pos,'monitor':'DISPLAY','monitor_rect':(0,0,100,100)}
 with authorization_scope(threading.Event()),patch.object(effector,'user32',f),patch('capability_lab.observe_physical_monitor',side_effect=lambda: {**obs, 'cursor':f.pos} if f.sets else obs),patch.object(ActuatorBridge,'_complete_physical',side_effect=call_direct):
  coro=bridge._route_execution('mouse_move_physical',{'approval':a,'proposal':p})
  try:coro.send(None)
  except StopIteration as done:return done.value,f
  raise AssertionError('not completed')

def test_unapproved_then_approved_once():
 p,a=make();r,f=invoke(p,a);assert r['status']=='ACTION_BLOCKED' and f.sets==0
 assert a.approve_explicitly(p.proposal_id)
 r,f=invoke(p,a);assert r['status']=='EFFECT_VERIFIED' and f.sets==1
 r,f=invoke(p,a);assert r['status']=='ACTION_BLOCKED' and f.sets==0

def test_context_change_consumes_and_blocks():
 p,a=make();assert a.approve_explicitly(p.proposal_id)
 r,f=invoke(p,a,pos=(21,30));assert r['status']=='ACTION_BLOCKED' and f.sets==0
 r,f=invoke(p,a);assert r['status']=='ACTION_BLOCKED' and f.sets==0

def test_set_failure_is_unverified():
 p,a=make();assert a.approve_explicitly(p.proposal_id)
 r,f=invoke(p,a,fail=True);assert r['status']=='EFFECT_UNVERIFIED' and f.sets==1

def test_expired_and_wrong_task():
 from dataclasses import replace
 p,a=make(time.monotonic()-1);assert not a.approve_explicitly(p.proposal_id)
 p,a=make();assert a.approve_explicitly(p.proposal_id)
 r,f=invoke(replace(p,task_id='other'),a);assert r['status']=='ACTION_BLOCKED' and f.sets==0

def test_generic_token_cannot_use_physical_profile():
 f=Fake()
 with authorization_scope(threading.Event()),patch.object(effector,'user32',f),pytest.raises(PermissionError):
  effector.Effector().mouse_move(30,30,profile='physical_diagnostic')
 assert f.sets==0

def test_concurrent_approval_consumed_once():
 from concurrent.futures import ThreadPoolExecutor
 p,a=make();assert a.approve_explicitly(p.proposal_id)
 obs={'status':'OBSERVED','coordinate_space':'PHYSICAL','cursor':p.start,'monitor':p.monitor,'monitor_rect':p.monitor_rect}
 with ThreadPoolExecutor(max_workers=2) as pool: values=list(pool.map(lambda _:a.consume(p,obs),range(2)))
 assert sorted(values)==[False,True]

def test_duplicate_authority_cannot_reuse_proposal_id():
 p,a=make();b=PhysicalMoveApproval(p);assert a.approve_explicitly(p.proposal_id);assert b.approve_explicitly(p.proposal_id)
 obs={'status':'OBSERVED','coordinate_space':'PHYSICAL','cursor':p.start,'monitor':p.monitor,'monitor_rect':p.monitor_rect}
 assert a.consume(p,obs) and not b.consume(p,obs)
