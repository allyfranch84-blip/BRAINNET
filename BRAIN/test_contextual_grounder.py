import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from contextual_grounder import ContextualGrounder, parse_click, suggest_apps
from BRAINNET import BrainnetBridge

class GrounderTests(unittest.TestCase):
 def setUp(self):
  self.now=100.;self.ctx={'hwnd':11,'pid':22,'process_name':'mspaint.exe'}
  self.sensor=SimpleNamespace(capture_foreground_context=lambda:dict(self.ctx));self.controls=[]
  self.eye=SimpleNamespace(scan_window_controls=lambda hwnd:list(self.controls))
  self.g=ContextualGrounder(self.sensor,self.eye,lambda pid:123.,clock=lambda:self.now)
 def control(self,name):return SimpleNamespace(name=name,rect=(0,0,30,30))
 def remember(self):self.assertTrue(self.g.remember('paint','abra paint','CONCLUIDO'))
 def test_variants(self):
  for t in ['Clique em pincéis','Click pincéis','Selecione a ferramenta pincel','Abra o menu Pincéis']:
   with self.subTest(t=t):self.assertIsNotNone(parse_click(t))
  self.assertIsNone(parse_click('explique e pincéis'));self.assertIsNone(parse_click('abra paint'))
 def test_uia_found_blocks_unproven_action(self):
  self.remember();self.controls=[self.control('Pincéis')];r=self.g.resolve(parse_click('click em pincéis'))
  self.assertEqual(r['status'],'ACTION_BLOCKED');self.assertNotIn('x',r);self.assertIsNone(self.g.context.pending_target)
 def test_not_found(self):
  self.remember();self.assertEqual(self.g.resolve(parse_click('click pincéis'))['status'],'TARGET_NOT_FOUND')
 def test_ambiguous(self):
  self.remember();self.controls=[self.control('Pincéis'),self.control('Pincéis')];self.assertEqual(self.g.resolve(parse_click('click pincéis'))['status'],'TARGET_AMBIGUOUS')
 def test_focus_and_pid(self):
  self.remember();self.ctx['hwnd']=55;self.assertEqual(self.g.resolve(parse_click('click pincéis'))['status'],'CONTEXT_UNAVAILABLE')
  self.ctx['hwnd']=11;self.ctx['pid']=88;self.assertEqual(self.g.resolve(parse_click('click pincéis'))['status'],'CONTEXT_UNAVAILABLE')
 def test_pid_reused(self):
  self.remember();self.g.process_started=lambda pid:124.;self.assertEqual(self.g.resolve(parse_click('click pincéis'))['status'],'CONTEXT_UNAVAILABLE')
 def test_expired(self):
  self.remember();self.now+=301;self.assertEqual(self.g.resolve(parse_click('click pincéis'))['status'],'CONTEXT_UNAVAILABLE')
 def test_pronoun_needs_validated_target(self):
  self.remember();self.assertEqual(self.g.resolve(parse_click('clique nesse botão'))['status'],'CONTEXT_UNAVAILABLE')
 def test_incorrect_open_does_not_save(self):
  self.assertFalse(self.g.remember('point','abra point','CONCLUIDO'));self.assertIsNone(self.g.context)
 def test_possible_names_require_confirmation(self):
  self.assertGreaterEqual(len(suggest_apps('point',{'paint':{},'powerpoint':{},'pointing':{}})),1)
  self.assertEqual(suggest_apps('point',{}),[])
 def test_send_command_real_route_read_only(self):
  self.remember();self.controls=[self.control('Pincéis')]
  bridge=BrainnetBridge.__new__(BrainnetBridge);bridge._contextual_grounder=self.g;bridge._kernel=SimpleNamespace(esta_dormindo=False,ultimo_toque_ai=0);bridge._window=None;bridge._chat_history=[]
  out=bridge.send_command('click em pincéis');self.assertEqual(out['contextual_result']['status'],'ACTION_BLOCKED')
if __name__=='__main__':unittest.main()
