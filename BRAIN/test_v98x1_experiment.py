import unittest
from experiments.v98_x1_hdc_benchmark import step, capacity
from ghrr_core import GHRRHyperdimensionalEngine
import numpy as np
class SyntheticWorldTests(unittest.TestCase):
 def test_bounded_and_contextual(self):
  self.assertEqual(step((0,1,0),'left'),(0,1,0))
  self.assertEqual(step((2,1,0),'toggle'),(2,1,1))
  self.assertEqual(step((2,0,0),'toggle'),(2,0,0))
 def test_ghrr_left_recovery(self):
  result=capacity(GHRRHyperdimensionalEngine(dim=128,seed=2),4,0,np.random.default_rng(2))
  self.assertEqual(result['recall_top1'],1)
 def test_invalid_action(self):
  with self.assertRaises(ValueError): step((1,0,0),'click')
if __name__=='__main__': unittest.main()
