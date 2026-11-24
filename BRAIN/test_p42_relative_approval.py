import threading,time,uuid
from unittest.mock import patch,Mock
from execution_authority import RelativePhysicalMoveProposal,PhysicalMoveApproval,authorization_scope
from actuator_bridge import ActuatorBridge
import effector

class Fake:
 def __init__(self,pos):self.pos=pos;self.sets=0
 def GetPhysicalCursorPos(self,p):p._obj.x,p._obj.y=self.pos;return 1
 def SetPhysicalCursorPos(self,x,y):self.sets+=1;self.pos=(x,y);return 1

def setup():
 p=RelativePhysicalMoveProposal('task',uuid.uuid4().hex,10,0,'DISPLAY',(0,0,100,100),(10,10,90,90),123,456,0,time.monotonic()+30)
 a=PhysicalMoveApproval(p);assert a.approve_explicitly(p.proposal_id)
 return p,a

def execute(p,a,point=(40,40),controls=None,verified=True):
 fake=Fake(point);bridge=ActuatorBridge(effector_instance=effector.Effector())
 def observation():return {'status':'OBSERVED','coordinate_space':'PHYSICAL','cursor':fake.pos,'monitor':'DISPLAY','monitor_rect':(0,0,100,100)}
 region={'status':'VERIFIED' if verified else 'SAFE_REGION_UNVERIFIED','coordinate_space':'PHYSICAL','lab_hwnd':123,'lab_pid':456,'safe_rect':(10,10,90,90),'controls_rects':[] if controls is None else controls,'observed_monotonic':time.monotonic()}
 async def invoke(fn,*args,**kwargs):return fn(*args,**kwargs)
 with authorization_scope(threading.Event()),patch.object(effector,'user32',fake),patch('capability_lab.observe_physical_monitor',side_effect=observation),patch('capability_lab.observe_verified_safe_region',return_value=region),patch.object(ActuatorBridge,'_complete_physical',side_effect=invoke):
  coro=bridge._route_execution('mouse_move_relative',{'proposal':p,'approval':a})
  try:coro.send(None)
  except StopIteration as v:return v.value,fake
  raise AssertionError('unexpected suspension')

def test_relative_uses_post_click_position_once():
 p,a=setup();r,f=execute(p,a,point=(40,40))
 assert r['status']=='EFFECT_VERIFIED' and r['before']==(40,40) and r['target']==(50,40) and f.sets==1
 r,f=execute(p,a);assert r['code']=='APPROVAL_ALREADY_CONSUMED' and f.sets==0

def test_missing_region_and_controls_block():
 p,a=setup();r,f=execute(p,a,verified=False);assert r['code']=='SAFE_REGION_UNVERIFIED' and f.sets==0
 p,a=setup();r,f=execute(p,a,controls=[(39,39,42,42)]);assert r['code']=='CONTROL_INTERSECTS_PATH' and f.sets==0

def test_position_outside_safe_region_blocks():
 p,a=setup();r,f=execute(p,a,point=(91,40));assert r['code']=='CURSOR_OUTSIDE_SAFE_REGION' and f.sets==0

def test_no_specific_approval_blocks():
 p,a=setup();a.cancel();r,f=execute(p,a);assert r['code']=='APPROVAL_MISSING' and f.sets==0

def test_default_safe_region_is_never_assumed():
 from capability_lab import find_verified_safe_region,observe_verified_safe_region
 assert find_verified_safe_region({'status':'OBSERVED'})['status']=='SAFE_REGION_UNVERIFIED'
 assert observe_verified_safe_region(1,2,(0,0,100,100))['status']=='SAFE_REGION_UNVERIFIED'

def test_wrong_monitor_geometry_and_expiry_fail_closed():
 from dataclasses import replace
 from unittest.mock import patch
 p,a=setup();obs={'status':'OBSERVED','coordinate_space':'PHYSICAL','cursor':(40,40),'monitor':'other','monitor_rect':p.monitor_rect}
 region={'status':'VERIFIED','coordinate_space':'PHYSICAL','lab_hwnd':p.lab_hwnd,'lab_pid':p.lab_pid,'safe_rect':p.safe_rect,'controls_rects':[],'observed_monotonic':time.monotonic()}
 assert a.consume_relative(p,obs,region)['code']=='MONITOR_CHANGED'
 p,a=setup();obs['monitor']=p.monitor;obs['monitor_rect']=(0,0,99,100)
 assert a.consume_relative(p,obs,region)['code']=='MONITOR_GEOMETRY_CHANGED'
 p,a=setup();obs['monitor_rect']=p.monitor_rect
 with patch('execution_authority.time.monotonic',return_value=p.deadline_monotonic+1):
  assert a.consume_relative(p,obs,region)['code']=='APPROVAL_EXPIRED'

def test_chat_blocks_when_no_independently_verified_region():
 from test_p41_approval_buttons import setup
 k,b,patches=setup()
 obs={'status':'OBSERVED','cursor':(200,200),'monitor':'DISPLAY1','monitor_rect':(0,0,1000,1000),'coordinate_space':'PHYSICAL'}
 try:
  with patch('capability_lab.observe_physical_monitor',return_value=obs),patch('capability_lab.observe_cursor_monitors',return_value={'interactive_desktop_verified':True}):
   result=b.send_command('mova o mouse em qualquer direção')
  assert result['status']=='ACTION_BLOCKED' and result['code']=='SAFE_REGION_UNVERIFIED'
  assert result['dispatched'] is False
  k.bridge.dispatch.assert_not_called()
 finally:
  for q in reversed(patches):q.stop()
