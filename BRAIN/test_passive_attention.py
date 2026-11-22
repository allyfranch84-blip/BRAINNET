import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from PIL import Image
from visual_attention import VisualAttentionManager
from adaptive_resource_controller import AdaptiveResourceController, ResourceSample, PerceptualSignals

class PassiveTests(unittest.TestCase):
 def setUp(self):
  self.now=100.;self.ctx={'hwnd':1,'pid':2,'process_name':'paint','title':'secret'}
  self.context=SimpleNamespace(capture_foreground_context=lambda:dict(self.ctx))
  self.vision=SimpleNamespace(capture_ui_observation=Mock(return_value=(Image.new('RGB',(40,40)),None,None)),extrair_texto_e_coordenadas=Mock(side_effect=RuntimeError()),descrever_elemento_visual=Mock())
  self.items=[SimpleNamespace(name='save',class_name='button',affordance='invoke')]
  self.eye=SimpleNamespace(scan_window_controls=lambda hwnd:list(self.items))
  self.a=VisualAttentionManager(SimpleNamespace(context_engine=self.context,vision=self.vision,eye=self.eye),enable_ocr=True,min_capture_interval=2,clock=lambda:self.now)
 def test_no_inference_ocr_fails(self):
  o=self.a.observe(roi=(0,0,20,20));self.assertEqual(o['ocr_status'],'unavailable');self.vision.descrever_elemento_visual.assert_not_called();self.assertEqual(o['focused_window'],'')
 def test_no_models_or_vision(self):
  self.a.kernel.vision=None;o=self.a.observe();self.assertIn('visual_capture_unavailable',o['degraded']);self.assertTrue(o['uia_available'])
 def test_cursor_pixel_change_never_vlm(self):
  self.a.observe(roi=(0,0,20,20));self.now+=3
  self.vision.capture_ui_observation.return_value=(Image.new('RGB',(40,40),'white'),None,None)
  o=self.a.observe(roi=(0,0,20,20));self.assertTrue(o['visual_changed']);self.vision.descrever_elemento_visual.assert_not_called()
  c=AdaptiveResourceController(clock=lambda:100);s=ResourceSample(cpu_pct=10,gpu_pct=10,ram_available_mb=3000,user_active=True,active_tasks=1,timestamp=100)
  self.assertFalse(c.update_observation(s,o,roi_identified=True)['invoke_vlm'])
 def test_window_and_uia(self):
  self.a.observe();self.now+=2;self.items.append(SimpleNamespace(name='open',class_name='button',affordance='invoke'))
  self.assertTrue(self.a.observe()['uia_changed']);self.now+=2;self.ctx['hwnd']=4;self.assertTrue(self.a.observe()['window_changed'])
 def test_rate_limit(self):
  self.a.observe(roi=(0,0,20,20));self.assertTrue(self.a.observe(roi=(0,0,20,20))['rate_limited']);self.assertEqual(self.vision.capture_ui_observation.call_count,1)
 def test_escalation_requires_approval(self):
  with self.assertRaises(PermissionError):self.a.escalate_visual(Image.new('RGB',(1,1)))
  self.vision.descrever_elemento_visual.assert_not_called()
 def test_residency_advice_no_side_effect(self):
  c=AdaptiveResourceController(clock=lambda:100);s=ResourceSample(cpu_pct=90,gpu_pct=90,ram_available_mb=3000,user_active=True,active_tasks=1,timestamp=100)
  d=c.update(s,PerceptualSignals(explicit_request=True,roi_identified=True));a=c.residency_advice(d,{'models':[{'name':'vision_small','state':'HOT','active':1}]})
  self.assertEqual(a['action'],'DEFER');self.assertTrue(a['protect_active_requests']);self.assertEqual(d['confidence'],'OBSERVED');self.assertGreater(d['reassess_at'],100)
 def test_unknown_memory_defers(self):
  c=AdaptiveResourceController(clock=lambda:100);s=ResourceSample(cpu_pct=10,gpu_pct=None,ram_available_mb=None,user_active=True,active_tasks=1,timestamp=100)
  d=c.update(s,PerceptualSignals(explicit_request=True,roi_identified=True));self.assertEqual(c.residency_advice(d,{})['action'],'DEFER');self.assertEqual(d['confidence'],'LOW')
 def test_import_no_side_effect(self):
  import subprocess,sys
  result=subprocess.run([sys.executable,'-c','import threading; n=len(threading.enumerate()); import visual_attention, adaptive_resource_controller; assert len(threading.enumerate()) == n'],capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stderr)
  self.vision.capture_ui_observation.assert_not_called();self.vision.descrever_elemento_visual.assert_not_called()
if __name__=='__main__':unittest.main()
