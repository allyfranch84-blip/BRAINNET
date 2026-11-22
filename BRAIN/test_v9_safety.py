"""V9 deterministic contracts; no desktop or remote services."""
import asyncio
import json
import threading
import unittest
from unittest.mock import Mock
from types import SimpleNamespace
from execution_authority import authorized_trajectory, authorization_scope, require_action_allowed, command_authority
from system_intent import system_launch_target
from ui_tars_protocol import parse_ui_action

class SecurityTests(unittest.IsolatedAsyncioTestCase):
 async def test_trajectory_requires_token(self):
  called=[]
  @authorized_trajectory
  async def fn():called.append(True)
  with self.assertRaises(PermissionError):await fn()
  self.assertEqual(called,[])
 async def test_revoked_or_invalid_token_denied(self):
  @authorized_trajectory
  async def fn():return True
  token=threading.Event();token.set()
  with self.assertRaises(PermissionError):await fn(authorization_token=token)
  with authorization_scope(object()):
   with self.assertRaises(PermissionError):require_action_allowed('CLICK')
 async def test_inherited_authority(self):
  @authorized_trajectory
  async def fn():require_action_allowed('CLICK');return True
  token=threading.Event()
  with authorization_scope(token):self.assertTrue(await fn())
  self.assertFalse(token.is_set())
 async def test_background_denied(self):
  @authorized_trajectory
  async def fn(**kwargs):return True
  with authorization_scope(threading.Event()):
   with self.assertRaises(PermissionError):await fn(is_background=True)
 async def test_revoked_parent_cannot_mint_new_command(self):
  @command_authority
  def cmd(): return True
  token=threading.Event();token.set()
  with authorization_scope(token):
   with self.assertRaises(PermissionError):cmd()

 async def test_cancelled_native_call_keeps_lock_until_worker_finishes(self):
  from actuator_bridge import ActuatorBridge
  bridge=ActuatorBridge();entered=threading.Event();release=threading.Event();acquired=asyncio.Event()
  def worker():entered.set();release.wait(2)
  async def first():
   async with bridge._input_lock: await bridge._complete_physical(worker)
  async def second():
   async with bridge._input_lock: acquired.set()
  task=asyncio.create_task(first())
  self.assertTrue(await asyncio.to_thread(entered.wait,1));task.cancel()
  other=asyncio.create_task(second());await asyncio.sleep(.03);self.assertFalse(acquired.is_set())
  task.cancel();await asyncio.sleep(.03);self.assertFalse(acquired.is_set())
  release.set()
  with self.assertRaises(asyncio.CancelledError):await task
  await asyncio.wait_for(other,1);self.assertTrue(acquired.is_set())

 async def test_cancelled_trajectory_revokes_inherited_token(self):
  token=threading.Event();started=asyncio.Event()
  @authorized_trajectory
  async def trajectory():
   started.set();await asyncio.Event().wait()
  with authorization_scope(token):
   task=asyncio.create_task(trajectory());await started.wait();task.cancel()
   with self.assertRaises(asyncio.CancelledError):await task
   self.assertTrue(token.is_set())
   with self.assertRaises(PermissionError):require_action_allowed('CLICK')

 async def test_cancelled_dispatch_revokes_pending_actions(self):
  from actuator_bridge import ActuatorBridge
  entered=threading.Event();release=threading.Event();calls=[]
  def click(*args):
   calls.append(args);entered.set();release.wait(2);return True
  bridge=ActuatorBridge(effector_instance=Mock(mouse_click=click),max_workers=2)
  await bridge.start();token=threading.Event()
  try:
   with authorization_scope(token):
    first=asyncio.create_task(bridge.dispatch('mouse_click',{}))
    self.assertTrue(await asyncio.to_thread(entered.wait,1))
    second=asyncio.create_task(bridge.dispatch('mouse_click',{}))
    await asyncio.sleep(.03);first.cancel()
    with self.assertRaises(asyncio.CancelledError):await first
    self.assertTrue(token.is_set());release.set()
    result=await asyncio.wait_for(second,2)
    self.assertEqual(result.status,'failed');self.assertEqual(len(calls),1)
  finally:
   release.set();await bridge.stop()

 async def test_deadline_revokes_before_native_worker_finishes(self):
  from actuator_bridge import ActuatorBridge
  entered=threading.Event();release=threading.Event();calls=[]
  def click(*args):
   calls.append(args);entered.set();release.wait(2);return True
  bridge=ActuatorBridge(effector_instance=Mock(mouse_click=click),max_workers=2)
  await bridge.start();token=threading.Event()
  try:
   with authorization_scope(token):
    first=asyncio.create_task(bridge.dispatch('mouse_click',{},timeout_sec=.05))
    self.assertTrue(await asyncio.to_thread(entered.wait,1))
    second=asyncio.create_task(bridge.dispatch('mouse_click',{},timeout_sec=1))
    await asyncio.sleep(.12);self.assertTrue(token.is_set());self.assertFalse(first.done())
    release.set();self.assertEqual((await asyncio.wait_for(first,2)).status,'timed_out')
    self.assertEqual((await asyncio.wait_for(second,2)).status,'failed');self.assertEqual(len(calls),1)
  finally:
   release.set();await bridge.stop()

class ParsingTests(unittest.TestCase):
 def test_action_formats(self):
  for action in ('click(340,210)','click(start_box=(340,210))','left_double(340,210)','right_single(340,210)','drag((340,210),(560,460))','drag(start_box=(340,210),end_box=(560,460))'):
   with self.subTest(action=action):self.assertIn('action_type',parse_ui_action(json.dumps({'thought':'','action':action})))
 def test_no_text_fallback(self):
  eye=Mock();eye.encontrar_elemento_por_texto.return_value=(10,10)
  with self.assertRaises(ValueError):parse_ui_action(json.dumps({'thought':'','action':'left_double click on the triangle shape tool in the toolbar'}),eye)
  eye.encontrar_elemento_por_texto.assert_not_called()
 def test_untrusted_expression_rejected(self):
  for action in ('click(__import__("os"),2)','unknown(1,2)','click(True,2)','click(-3,5)'):
   with self.subTest(action=action),self.assertRaises(ValueError):parse_ui_action(json.dumps({'thought':'','action':action}))
 def test_literal_app_negation(self):
  self.assertEqual(system_launch_target('abre paint'),'paint');self.assertEqual(system_launch_target('abra o paint'),'paint')
  self.assertIsNone(system_launch_target('não abra o paint'));self.assertIsNone(system_launch_target('o que é o Paint?'))

 def test_structured_intent_does_not_authorize(self):
  from parser_contract import analyze_literal_intent
  examples=[('abra o paint','OPEN','DIGITAL_UI'),('clique nesse botão','CLICK','DIGITAL_UI'),
            ('abra a geladeira','OPEN','PHYSICAL_WORLD'),('abra seu coração',None,'SOCIAL_AFFECT')]
  for text,action,domain in examples:
   with self.subTest(text=text):
    result=analyze_literal_intent(text);self.assertEqual((result['action'],result['domain']),(action,domain));self.assertFalse(result['execution_authorized'])
  self.assertTrue(analyze_literal_intent('não abra o paint')['negated'])

 def test_engineer_classifier_and_no_autofix(self):
  from engineering_agent import classify_error, EngineeringAgent
  self.assertEqual(classify_error('Traceback\nModuleNotFoundError: x'),'ModuleNotFoundError')
  self.assertEqual(classify_error(IndentationError('x')),'IndentationError')
  self.assertEqual(classify_error('unknown'),'UNKNOWN')
  with self.assertRaises(PermissionError):EngineeringAgent.__new__(EngineeringAgent)._apply_auto_fix(None,'bad')

class KernelIntentIntegrationTests(unittest.TestCase):
 def make_bridge(self):
  from BRAINNET import BrainnetBridge
  bridge=object.__new__(BrainnetBridge)
  bridge._kernel=SimpleNamespace(esta_dormindo=False,ultimo_toque_ai=0)
  bridge._window=None;bridge._chat_history=[]
  def dispatch(*args):
   require_action_allowed('EXECUTE')
   return {'reply':'simulado','logs':[]}
  bridge._executar_comando_interno=Mock(side_effect=dispatch)
  return bridge

 def test_requests_preserve_existing_dispatch(self):
  cases=['abre paint','abra o paint','desenhe um quadrado no paint',
         'abra o paint e desenhe um quadrado','o que é o Paint?']
  for text in cases:
   with self.subTest(text=text):
    bridge=self.make_bridge();result=bridge.send_command(text)
    bridge._executar_comando_interno.assert_called_once_with(text,text.lower(),' '.join(text.lower().split()))
    self.assertFalse(result['intent_contract']['execution_authorized'])
    if text in ('abre paint','abra o paint'):
     self.assertEqual(result['intent_contract']['action'],'OPEN')
    if text == 'abra o paint e desenhe um quadrado':
     self.assertTrue(result['intent_contract']['ambiguous'])
     self.assertIsNone(result['intent_contract']['target'])

 def test_negation_does_not_dispatch(self):
  bridge=self.make_bridge();result=bridge.send_command('não abra o paint')
  bridge._executar_comando_interno.assert_not_called()
  self.assertTrue(result['intent_contract']['negated'])
  self.assertFalse(result['intent_contract']['execution_authorized'])
if __name__=='__main__':unittest.main()
