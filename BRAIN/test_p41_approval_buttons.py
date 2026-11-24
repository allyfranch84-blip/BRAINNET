from types import SimpleNamespace
from unittest.mock import AsyncMock,Mock,patch
import time
from BRAINNET import BrainnetKernel,BrainnetBridge

def setup():
 env=patch.dict('os.environ',{'BRAINNET_MINIMAL':'1','BRAINNET_P4_PHYSICAL_PROPOSALS':'1'})
 patches=[env]+[patch('BRAINNET.'+name) for name in ['FHRRHyperdimensionalEngine','ContextCapture','PerceptionEye','Effector','ActuatorBridge','DigitalProprioceptionGate','TheoryOfMindEngine']]
 for p in patches:p.start()
 k=BrainnetKernel();k.loop=Mock();k.loop.is_running.return_value=True;b=BrainnetBridge(k)
 b.get_effort_mode=Mock(return_value={'mode':'FAST'});b.get_conversation_status=Mock(return_value={})
 return k,b,patches

def proposal(b):
 obs={'status':'OBSERVED','cursor':(200,200),'monitor':'DISPLAY1','monitor_rect':(0,0,1000,1000),'coordinate_space':'PHYSICAL'}
 region={'status':'VERIFIED','coordinate_space':'PHYSICAL','safe_rect':(100,100,900,900),'lab_hwnd':10,'lab_pid':20}
 with patch('capability_lab.observe_physical_monitor',return_value=obs),patch('capability_lab.observe_cursor_monitors',return_value={'interactive_desktop_verified':True}),patch('capability_lab.find_verified_safe_region',return_value=region):
  return b.send_command('mova o mouse em qualquer direção')

def test_button_uses_backend_proposal_once():
 k,b,patches=setup()
 try:
  r=proposal(b);p=r['physical_proposal'];assert r['status']=='PENDING_APPROVAL' and not r['dispatched']
  k.bridge.dispatch=AsyncMock(return_value=SimpleNamespace(result={'status':'EFFECT_UNVERIFIED'},status='completed'))
  def submit(coro,loop):
   from concurrent.futures import Future
   f=Future()
   try:coro.send(None)
   except StopIteration as v:f.set_result(v.value)
   return f
  with patch('BRAINNET.asyncio.run_coroutine_threadsafe',side_effect=submit):
   assert b.approve_p4_proposal('wrong',p['proposal_id'])['status']=='ACTION_BLOCKED'
   assert b.approve_p4_proposal(p['task_id'],p['proposal_id'])['status']=='EFFECT_UNVERIFIED'
   assert b.approve_p4_proposal(p['task_id'],p['proposal_id'])['status']=='ACTION_BLOCKED'
  payload=k.bridge.dispatch.call_args.args[1];assert (payload['proposal'].dx,payload['proposal'].dy)==(10,0) and payload['proposal'].safe_rect==(100,100,900,900)
  assert k.bridge.dispatch.call_args.args[0]=='mouse_move_relative'
  assert k.bridge.dispatch.await_count==1
 finally:
  for q in reversed(patches):q.stop()

def test_cancel_and_expiry_block():
 k,b,patches=setup()
 try:
  r=proposal(b);p=r['physical_proposal']
  assert b.cancel_p4_proposal('wrong',p['proposal_id'])['status']=='ACTION_BLOCKED'
  assert b.cancel_p4_proposal(p['task_id'],p['proposal_id'])['status']=='CANCELLED'
  assert b.approve_p4_proposal(p['task_id'],p['proposal_id'])['status']=='ACTION_BLOCKED'
  r=proposal(b);p=r['physical_proposal'];obj=b._p4_pending[p['proposal_id']][0]
  with patch('BRAINNET.time.monotonic',return_value=obj.deadline_monotonic+1):
   assert b.approve_p4_proposal(p['task_id'],p['proposal_id'])['status']=='EXPIRED'
  k.bridge.dispatch.assert_not_called()
 finally:
  for q in reversed(patches):q.stop()

def test_ordinary_chat_text_cannot_approve():
 k,b,patches=setup()
 try:
  r=proposal(b);p=r['physical_proposal']
  text=f"/aprovar {p['task_id']} {p['proposal_id']}"
  blocked=b.send_command(text)
  assert blocked['status']=='UNAVAILABLE'
  k.bridge.dispatch.assert_not_called()
 finally:
  for q in reversed(patches):q.stop()
