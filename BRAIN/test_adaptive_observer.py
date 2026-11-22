import asyncio
import os
import threading
import time
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
from adaptive_observer import AdaptiveObserver, configured_interval
from BRAINNET import BrainnetKernel

class Sensor:
 def __init__(self): self.calls=0
 def observe(self):self.calls+=1;return {'uia_available':False,'degraded':['uia_unavailable'],'window_changed':False}

class ObserverTests(unittest.TestCase):
 def test_interval_bounds(self):
  self.assertEqual(configured_interval('0'),5);self.assertEqual(configured_interval('1000'),300);self.assertEqual(configured_interval('nan'),30)
 def test_degraded_no_models_or_motor(self):
  sensor=Sensor();kernel=SimpleNamespace(vision=Mock(),bridge=Mock());o=AdaptiveObserver(kernel,sensor=sensor)
  with patch('adaptive_observer.user_idle_seconds',return_value=None):record=o.tick()
  self.assertIn('gpu',record['unknown_metrics']);self.assertIn('uia_unavailable',record['degraded']);self.assertFalse(record['capture_performed'])
  kernel.vision.assert_not_called();kernel.bridge.assert_not_called();self.assertNotIn('title',str(record))
 def test_privacy_retention_and_sensor_failure(self):
  sensor=Mock();sensor.observe.side_effect=RuntimeError('private content')
  o=AdaptiveObserver(None,sensor=sensor)
  with patch('adaptive_observer.user_idle_seconds',return_value=None):
   for _ in range(110):r=o.tick()
  self.assertEqual(len(o.records),100);self.assertIn('passive_observation_unavailable',r['degraded']);self.assertNotIn('private content',str(r))
 def test_worker_idempotent_and_restart(self):
  o=AdaptiveObserver(None,sensor=Sensor(),interval=5)
  self.assertTrue(o.start());self.assertFalse(o.start());self.assertTrue(o.stop());self.assertTrue(o.start());self.assertTrue(o.stop())
 def test_blocked_sensor_no_duplicate(self):
  entered=threading.Event();unblock=threading.Event()
  class Slow:
   def observe(self):entered.set();unblock.wait(2);return {}
  o=AdaptiveObserver(None,sensor=Slow());o.start();self.assertTrue(entered.wait(2));self.assertFalse(o.stop(timeout=.01));self.assertFalse(o.start());unblock.set();self.assertTrue(o.stop(timeout=3))

class KernelLifecycleTests(unittest.IsolatedAsyncioTestCase):
 def kernel(self):
  k=BrainnetKernel.__new__(BrainnetKernel);k.is_running=False;k.loop=None;k._adaptive_observer=None
  class Bridge:
   async def start(self):pass
  k.bridge=Bridge()
  async def watchdog():await asyncio.Event().wait()
  k._circadian_rem_watchdog=watchdog
  return k
 async def run_kernel(self,k):
  task=asyncio.create_task(k.start());await asyncio.sleep(.05);return task
 async def test_disabled_by_default_and_shutdown(self):
  k=self.kernel()
  with patch.dict(os.environ,{},clear=True):
   task=await self.run_kernel(k);self.assertIsNone(k._adaptive_observer);task.cancel()
   with self.assertRaises(asyncio.CancelledError):await task
   self.assertFalse(k.is_running)
 async def test_enabled_observe_and_shutdown(self):
  k=self.kernel();observer=Mock();observer.stop.return_value=True
  with patch.dict(os.environ,{'BRAINNET_ADAPTIVE_OBSERVE':'1'},clear=True),patch('adaptive_observer.AdaptiveObserver',return_value=observer):
   task=await self.run_kernel(k);self.assertIs(k._adaptive_observer,observer);observer.start.assert_called_once();task.cancel()
   with self.assertRaises(asyncio.CancelledError):await task
   observer.stop.assert_called_once()
 async def test_failed_observer_does_not_stop_kernel(self):
  k=self.kernel()
  with patch.dict(os.environ,{'BRAINNET_ADAPTIVE_OBSERVE':'1'},clear=True),patch('adaptive_observer.AdaptiveObserver',side_effect=RuntimeError('unavailable')):
   task=await self.run_kernel(k);self.assertTrue(k.is_running);task.cancel()
   with self.assertRaises(asyncio.CancelledError):await task
 async def test_worker_does_not_block_event_loop(self):
  k=self.kernel();entered=threading.Event();unblock=threading.Event()
  class Slow:
   def observe(self):entered.set();unblock.wait(2);return {}
  observer=AdaptiveObserver(k,sensor=Slow())
  with patch.dict(os.environ,{'BRAINNET_ADAPTIVE_OBSERVE':'1'},clear=True),patch('adaptive_observer.AdaptiveObserver',return_value=observer):
   task=await self.run_kernel(k);await asyncio.wait_for(asyncio.to_thread(entered.wait,1),2)
   marker=asyncio.Event();asyncio.get_running_loop().call_soon(marker.set);await asyncio.wait_for(marker.wait(),.3)
   unblock.set();task.cancel()
   with self.assertRaises(asyncio.CancelledError):await task

if __name__=='__main__':unittest.main()
