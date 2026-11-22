import unittest
from adaptive_resource_controller import AdaptiveResourceController, ControllerConfig, ResourceSample, PerceptualSignals, TaskContinuity

class TestAdaptiveController(unittest.TestCase):
 def setUp(self):
  self.now=100.;self.c=AdaptiveResourceController(ControllerConfig(min_transition_seconds=3,recovery_samples=2),clock=lambda:self.now)
 def sample(self,**kw):
  args=dict(cpu_pct=10,gpu_pct=10,ram_available_mb=4096,user_active=True,user_idle_seconds=0,active_tasks=1,timestamp=self.now);args.update(kw);return ResourceSample(**args)
 def update(self,signals=None,**kw):return self.c.update(self.sample(**kw),signals)
 def advance(self,n=4):self.now+=n
 def test_idle(self):
  self.advance();r=self.update(user_active=False,user_idle_seconds=60,active_tasks=0);self.assertEqual(r['state'],'IDLE')
 def test_browsing(self):self.assertEqual(self.update()['attention'],'PERIPHERAL')
 def test_fullscreen_game_load_based(self):
  r=self.update(cpu_pct=90,gpu_pct=95);self.assertEqual(r['state'],'HIGH_LOAD');self.assertFalse(r['budgets']['allow_new_loads'])
 def test_gpu_load_without_game(self):self.assertEqual(self.update(gpu_pct=90)['state'],'HIGH_LOAD')
 def test_ram_critical(self):
  r=self.update(ram_available_mb=500);self.assertEqual(r['state'],'CRITICAL');self.assertEqual(r['attention'],'SUSPENDED')
 def test_hysteresis(self):
  self.update(cpu_pct=90);self.advance();self.assertEqual(self.update(cpu_pct=68)['state'],'HIGH_LOAD');self.assertEqual(self.update(cpu_pct=80)['state'],'HIGH_LOAD');self.assertEqual(self.update(cpu_pct=60)['state'],'HIGH_LOAD');self.assertEqual(self.update(cpu_pct=60)['state'],'NORMAL')
 def test_focal(self):
  r=self.update(PerceptualSignals(explicit_request=True,roi_identified=True));self.assertEqual(r['attention'],'FOCAL');self.assertFalse(r['invoke_vlm'])
 def test_deep(self):
  r=self.update(PerceptualSignals(uncertainty_high=True,roi_identified=True));self.assertEqual(r['attention'],'DEEP');self.assertTrue(r['invoke_vlm'])
 def test_suspend_and_resume_context(self):
  t=TaskContinuity('t','draw',plan=['x'],next_action='click',last_validated_observation={'hwnd':1,'pid':5});self.c.register_task(t);self.update(ram_available_mb=100)
  self.assertEqual(t.status,'PAUSED');self.assertEqual(t.next_action,'click');self.advance();self.update();self.update();self.c.resume('t');self.assertFalse(self.c.can_act('t'));self.assertFalse(self.c.confirm_context('t',None,verified=True));self.assertFalse(self.c.confirm_context('t',{'hwnd':2,'pid':5,'controls_validated':True,'objective':'draw'},verified=True));self.assertTrue(self.c.confirm_context('t',{'hwnd':1,'pid':5,'controls_validated':True,'objective':'draw'},verified=True));self.assertIsNone(t.next_action);self.assertTrue(self.c.can_act('t'))
 def test_metric_loss_fail_closed(self):
  r=self.update(PerceptualSignals(uncertainty_high=True,roi_identified=True),gpu_pct=None);self.assertIn('gpu',r['unknown_metrics']);self.assertFalse(r['invoke_vlm']);self.assertFalse(r['budgets']['allow_new_loads'])
 def test_no_14b(self):self.assertFalse(self.update()['budgets']['allow_14b'])
 def test_action_in_progress(self):
  t=TaskContinuity('t','draw',action_in_progress=True);self.c.register_task(t);self.update(ram_available_mb=1);self.assertTrue(t.pause_pending);self.assertEqual(t.status,'RUNNING');self.c.action_finished('t');self.assertEqual(t.status,'PAUSED')
 def test_irrelevant_pixels(self):self.assertFalse(self.update(PerceptualSignals(pixel_change_only=True))['invoke_vlm'])
 def test_stale(self):
  r=self.update(timestamp=1);self.assertTrue(r['sample_stale']);self.assertFalse(r['budgets']['allow_new_loads'])
 def test_essential(self):
  t=TaskContinuity('t','essential',essential=True);self.c.register_task(t);self.update(ram_available_mb=1);self.assertEqual(t.status,'RUNNING')
if __name__=='__main__':unittest.main()
