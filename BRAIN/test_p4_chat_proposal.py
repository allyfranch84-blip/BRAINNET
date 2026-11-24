from types import SimpleNamespace
from unittest.mock import Mock,patch
from BRAINNET import BrainnetKernel,BrainnetBridge

def test_p4_chat_proposal_and_invalid_approval_does_not_dispatch():
 obs={'status':'OBSERVED','cursor':(200,200),'monitor':'DISPLAY1','monitor_rect':(0,0,1000,1000),'coordinate_space':'PHYSICAL'}
 with patch.dict('os.environ',{'BRAINNET_MINIMAL':'1','BRAINNET_P4_PHYSICAL_PROPOSALS':'1'}), \
      patch('BRAINNET.FHRRHyperdimensionalEngine'),patch('BRAINNET.ContextCapture'),patch('BRAINNET.PerceptionEye'), \
      patch('BRAINNET.Effector'),patch('BRAINNET.ActuatorBridge'),patch('BRAINNET.DigitalProprioceptionGate'), \
      patch('BRAINNET.TheoryOfMindEngine'),patch('capability_lab.observe_physical_monitor',return_value=obs), \
      patch('capability_lab.observe_cursor_monitors',return_value={'interactive_desktop_verified':True}):
  k=BrainnetKernel();b=BrainnetBridge(k)
  with patch.object(b,'get_effort_mode',return_value={'mode':'FAST'}),patch.object(b,'get_conversation_status',return_value={}):
   r=b.send_command('mova o mouse em qualquer direção')
  assert r['status']=='PENDING_APPROVAL' and not r['dispatched']
  assert r['task_id']==r['task_budget']['task_id']
  assert b.approve_p4_physical('/aprovar algo')['status']=='ACTION_BLOCKED'
  k.bridge.dispatch.assert_not_called()

def test_p4_observation_failure_blocks():
 with patch.dict('os.environ',{'BRAINNET_MINIMAL':'1','BRAINNET_P4_PHYSICAL_PROPOSALS':'1'}), \
      patch('BRAINNET.FHRRHyperdimensionalEngine'),patch('BRAINNET.ContextCapture'),patch('BRAINNET.PerceptionEye'), \
      patch('BRAINNET.Effector'),patch('BRAINNET.ActuatorBridge'),patch('BRAINNET.DigitalProprioceptionGate'), \
      patch('BRAINNET.TheoryOfMindEngine'),patch('capability_lab.observe_physical_monitor',return_value={'status':'ERROR'}), \
      patch('capability_lab.observe_cursor_monitors',return_value={'interactive_desktop_verified':True}):
  k=BrainnetKernel();b=BrainnetBridge(k)
  with patch.object(b,'get_effort_mode',return_value={'mode':'FAST'}),patch.object(b,'get_conversation_status',return_value={}):
   r=b.send_command('mova o mouse em qualquer direção')
  assert r['status']=='ACTION_BLOCKED' and not r['dispatched']

def test_p4_confirmation_exact_and_replay_blocked_without_real_motor():
 from concurrent.futures import Future
 obs={'status':'OBSERVED','cursor':(200,200),'monitor':'DISPLAY1','monitor_rect':(0,0,1000,1000),'coordinate_space':'PHYSICAL'}
 with patch.dict('os.environ',{'BRAINNET_MINIMAL':'1','BRAINNET_P4_PHYSICAL_PROPOSALS':'1'}), \
      patch('BRAINNET.FHRRHyperdimensionalEngine'),patch('BRAINNET.ContextCapture'),patch('BRAINNET.PerceptionEye'), \
      patch('BRAINNET.Effector'),patch('BRAINNET.ActuatorBridge'),patch('BRAINNET.DigitalProprioceptionGate'), \
      patch('BRAINNET.TheoryOfMindEngine'),patch('capability_lab.observe_physical_monitor',return_value=obs), \
      patch('capability_lab.observe_cursor_monitors',return_value={'interactive_desktop_verified':True}):
  k=BrainnetKernel();k.loop=Mock();k.loop.is_running.return_value=True;b=BrainnetBridge(k)
  with patch.object(b,'get_effort_mode',return_value={'mode':'FAST'}),patch.object(b,'get_conversation_status',return_value={}):
   r=b.send_command('mova o mouse em qualquer direção')
  task,op=r['task_id'],r['pending_operation_id']
  assert b.approve_p4_physical(f'/aprovar {task} {op} 200 200 211 200 DISPLAY1 0')['status']=='ACTION_BLOCKED'
  future=Future();future.set_result(SimpleNamespace(result={'status':'EFFECT_UNVERIFIED'},status='completed'))
  def fake_submit(coro,loop): coro.close();return future
  with patch('BRAINNET.asyncio.run_coroutine_threadsafe',side_effect=fake_submit):
   text=f'/aprovar {task} {op} 200 200 210 200 DISPLAY1 0'
   assert b.approve_p4_physical(text)['status']=='EFFECT_UNVERIFIED'
   assert b.approve_p4_physical(text)['status']=='ACTION_BLOCKED'
  k.bridge.dispatch.assert_not_called()
