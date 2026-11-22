import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from contextual_grounder import ContextualGrounder,parse_click
from paint_app_context import paint_context,plan_draw_circle,ExecutionEvidence,visual_fallback_advice

class PaintCapabilitiesTests(unittest.TestCase):
 def setUp(self):
  ctx={'hwnd':3,'pid':4,'process_name':'mspaint.exe'}
  self.eye=SimpleNamespace(scan_window_controls=Mock(return_value=[SimpleNamespace(name='Pincéis')]),scan_uia_properties=Mock(return_value=[{'name':'Pincéis','process_id':4,'runtime_id':(1,2),'is_enabled':True,'is_offscreen':False,'invoke_supported':True}]))
  self.g=ContextualGrounder(SimpleNamespace(capture_foreground_context=lambda:dict(ctx)),self.eye,lambda pid:123.)
  self.g.remember('paint','abra paint','CONCLUIDO')
 def test_host_context_and_grounded_without_execution(self):
  r=self.g.resolve(parse_click('clique em pincéis'))
  self.assertEqual(r['status'],'READY_FOR_UIA');self.assertEqual(r['app_context']['app'],'paint');self.assertFalse(r['learning_candidate']['eligible_for_consolidation']);self.assertEqual(r['learning_candidate']['executed_actions'],[])
 def test_paint_circle_canvas_untrusted(self):
  app=paint_context(self.g.context);r=plan_draw_circle(app,verified_canvas_rect=(0,0,200,200));self.assertEqual(r['status'],'GOAL_UNVERIFIED');self.assertIsNone(r['verified_canvas_rect']);self.assertEqual(len(r['steps']),5)
 def test_learning_requires_explicit_evidence(self):
  e=ExecutionEvidence('draw','paint',goal_state='GOAL_VERIFIED');self.assertFalse(e.as_learning_candidate()['eligible_for_consolidation'])
  e.executed_actions.append({'action':'drag'});e.verified_effects.append({'effect':'circle'});self.assertTrue(e.as_learning_candidate()['eligible_for_consolidation'])
 def test_fallback_explicit_and_limited(self):
  for auth,resources in [(False,False),(True,False),(False,True)]:self.assertEqual(visual_fallback_advice(uia_status='TARGET_NOT_FOUND',explicit_authorization=auth,resource_approved=resources)['decision'],'DENIED')
  self.assertEqual(visual_fallback_advice(uia_status='ACTION_BLOCKED',explicit_authorization=True,resource_approved=True)['decision'],'DENIED')
  self.assertEqual(visual_fallback_advice(uia_status='TARGET_NOT_FOUND',explicit_authorization=True,resource_approved=True)['decision'],'ELIGIBLE')
 def test_ambiguous_controls_block(self):
  self.eye.scan_window_controls.return_value=[SimpleNamespace(name='Pincéis'),SimpleNamespace(name='Pincéis')]
  self.assertEqual(self.g.resolve(parse_click('clique em pincéis'))['status'],'TARGET_AMBIGUOUS')
if __name__=='__main__':unittest.main()
