import concurrent.futures
import unittest
from situation_memory import Observation, SituationMemory, TaskContext, InferenceRequest
from adaptive_resource_controller import TaskContinuity
from inference_backend import InferenceRequest as ExistingRequest
from portable_planner import simulate

class FoundationTests(unittest.TestCase):
 def test_existing_contracts_reused(self):
  self.assertIs(TaskContext,TaskContinuity);self.assertIs(InferenceRequest,ExistingRequest)
 def test_snapshot_expiry_and_isolation(self):
  now=[10.0];m=SituationMemory(enabled=True,clock=lambda:now[0])
  m.update(Observation('g',1,'test',9,11));m.update(Observation('t',2,'test',9,11,task_id='a'))
  self.assertEqual({x.key for x in m.snapshot('b').observations},{'g'})
  self.assertEqual({x.key for x in m.snapshot('a').observations},{'g','t'})
  now[0]=11;self.assertEqual(m.snapshot('a').observations,())
 def test_window_and_restart(self):
  m=SituationMemory(enabled=True,clock=lambda:10)
  m.change_window('one');m.update(Observation('x',1,'uia',9,11,window_id='one',verified=True,persist_eligible=True))
  records=m.export_eligible();m.change_window('two');self.assertEqual(m.snapshot().observations,())
  restarted=SituationMemory(enabled=True,clock=lambda:10)
  self.assertEqual(restarted.restore_historical(records)[0]['state'],'REVALIDATION_REQUIRED')
  self.assertEqual(restarted.snapshot().observations,())
 def test_capacity_and_concurrency(self):
  m=SituationMemory(enabled=True,max_bytes=1100,clock=lambda:10)
  def insert(i):m.update(Observation(str(i),'x'*30,'test',9,11,priority=i))
  with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(insert,range(20)))
  snap=m.snapshot();self.assertLess(len(snap.observations),20)
  self.assertEqual(snap.observations[0].key,'19')
 def test_failed_inference_not_automatically_verified(self):
  m=SituationMemory(enabled=True,clock=lambda:10)
  m.update(Observation('inference','failed','test',9,11,persist_eligible=True))
  self.assertEqual(m.export_eligible(),[])
 def test_router_read_only_and_disabled(self):
  from router import AdaptiveInferenceRouter
  router=object.__new__(AdaptiveInferenceRouter)
  self.assertIsNone(router.read_situation(SituationMemory(), 'a'))
  m=SituationMemory(enabled=True,clock=lambda:10);m.update(Observation('x',1,'test',9,11,task_id='a'))
  self.assertEqual(router.read_situation(m,'a',keys={'x'}).observations[0].key,'x')
 def test_planner_conservative(self):
  for profile in ('Core','Edge CPU','Desktop GPU','Servidor opcional'):
   plan=simulate(profile,{'vulkan_verified':False})
   self.assertEqual(plan['execution'],'SIMULATION_ONLY')
   self.assertTrue(all(c['decision']=='PENDING_EVIDENCE' for c in plan['components']))
