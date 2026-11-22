import unittest
from model_residency_manager import ModelResidencyManager, ModelSpec, Residency, ResidencyError, profiler_admission

class Driver:
 def __init__(self,fail=False):self.loaded=False;self.fail=fail
 def load(self):
  if self.fail:raise RuntimeError('backend unavailable')
  self.loaded=True;return True
 def healthy(self):return self.loaded
 def unload(self):self.loaded=False;return True
 def residency(self):return {'weights_resident':self.loaded,'kv_cache':'UNKNOWN','measured':{'ram':100}}

class ResidencyTests(unittest.TestCase):
 def setUp(self):
  self.time=0;self.available=1000;self.policy='APPROVED'
  self.manager=ModelResidencyManager(lambda:{'available':self.available},self.admit,clock=lambda:self.time,max_wait=10)
  for name,role,prio in [('fast','fast',10),('mid','general',5),('vision','vision',4),('big','heavy',1)]:
   self.manager.register(ModelSpec(name,role,Driver(),None,{},100,priority=prio,idle_seconds=2,projector='p' if role=='vision' else None,projector_compatible=role=='vision'))
 def admit(self,inv,spec):
  resident=sum(x.spec.ram_budget for x in self.manager.models.values() if x.state in (Residency.HOT,Residency.WARM))
  if self.policy!='APPROVED':return {'decision':'INSUFFICIENT_EVIDENCE'}
  if resident+spec.ram_budget>inv['available']:return {'decision':'INSUFFICIENT_EVIDENCE','eviction_may_help':True}
  return {'decision':'APPROVED'}
 def test_fast_hot_mid_warm(self):
  self.manager.promote('fast');self.manager.promote('mid');self.time=3;self.manager.idle()
  self.assertEqual(self.manager.models['fast'].state,Residency.HOT);self.assertEqual(self.manager.models['mid'].state,Residency.WARM)
 def test_vision_while_fast_busy(self):
  self.manager.promote('fast');self.manager.acquire('fast');self.assertEqual(self.manager.promote('vision')['decision'],'READY');self.assertEqual(self.manager.models['fast'].active,1)
 def test_three_do_not_fit(self):
  self.available=200;self.manager.promote('fast');self.manager.promote('mid');self.assertEqual(self.manager.promote('vision')['decision'],'INSUFFICIENT_EVIDENCE')
 def test_heavy_evicts_secondary(self):
  self.available=200;self.manager.promote('fast');self.manager.promote('mid');self.assertEqual(self.manager.promote('big',explicit_heavy=True)['decision'],'READY');self.assertEqual(self.manager.models['mid'].state,Residency.COLD)
 def test_heavy_rejected_and_explicit(self):
  self.assertEqual(self.manager.promote('big')['decision'],'DENIED');self.policy='DENIED';self.assertEqual(self.manager.promote('big',explicit_heavy=True)['decision'],'INSUFFICIENT_EVIDENCE')
 def test_busy_protected(self):
  self.manager.promote('mid');self.manager.acquire('mid')
  with self.assertRaises(ResidencyError):self.manager.evict('mid')
 def test_load_failure_reserves_budget(self):
  self.manager.models['mid'].spec.driver.fail=True;self.assertEqual(self.manager.promote('mid')['decision'],'FAILED');self.assertEqual(self.manager.models['mid'].record()['reserved_ram'],100)
 def test_vulkan_failure(self):
  self.manager.models['vision'].spec.driver.fail=True;self.assertEqual(self.manager.promote('vision')['decision'],'FAILED')
 def test_recover_fast(self):
  self.manager.promote('fast');self.manager.evict('fast');self.manager.promote('big',explicit_heavy=True);self.manager.evict('big');self.assertEqual(self.manager.promote('fast')['decision'],'READY')
 def test_cpu_no_gpu(self):
  self.assertEqual(self.manager.promote('fast')['decision'],'READY')
 def test_telemetry_unknown(self):
  self.policy='UNKNOWN';self.assertNotEqual(self.manager.promote('mid')['decision'],'READY')
 def test_profiler_fails_closed_without_memory_evidence(self):
  self.assertEqual(profiler_admission({},self.manager.models['big'].spec)['decision'],'INSUFFICIENT_EVIDENCE')
 def test_priority_aging_and_cancel(self):
  self.manager.enqueue('slow','mid',1,100);self.time=11;self.manager.enqueue('fast','fast',100,100);self.assertEqual(self.manager.dequeue().task_id,'slow');self.assertTrue(self.manager.cancel('fast'));self.assertIsNone(self.manager.dequeue())
 def test_projector_required(self):
  with self.assertRaises(ValueError):ModelSpec('v','vision',Driver(),None,{},100)
 def test_unknown_driver_residency_never_warm(self):
  self.manager.promote('mid');self.manager.models['mid'].spec.driver.residency=lambda:{};self.time=3;self.manager.idle();self.assertEqual(self.manager.models['mid'].state,Residency.COLD)
if __name__=='__main__':unittest.main()
