import sqlite3
import tempfile
import unittest
from pathlib import Path
import numpy as np
import hyperdimensional
from ghrr_core import GHRRHyperdimensionalEngine
from qfhrr_core import QFHRRHyperdimensionalEngine
from pdag_ghrr_extension import SyntacticPDAG
from situation_fhrr_index import IndexedSnapshot, SituationFHRRIndex

class AlgebraTests(unittest.TestCase):
 def test_sides_order_and_legacy(self):
  e=GHRRHyperdimensionalEngine(dim=128);a,b,c=[e.generate_vector(x) for x in ('a','b','c')]
  seq=e.bind(e.bind(a,b),c)
  np.testing.assert_allclose(e.unbind_left(e.unbind_right(seq,c),a),b,atol=2e-6)
  np.testing.assert_allclose(e.unbind(e.bind(a,b),b),a,atol=2e-6)
  self.assertLess(e.similarity(e.bind(a,b),e.bind(b,a)),.95)
  self.assertTrue(np.isfinite(seq).all())
  eye=np.eye(2,dtype=np.complex64)[None,:,:]
  np.testing.assert_allclose(np.matmul(np.conj(a.swapaxes(1,2)),a),np.broadcast_to(eye,a.shape),atol=1e-6)
  np.testing.assert_array_equal(e.generate_vector('a'),a)
  self.assertFalse(np.array_equal(e.generate_vector(),e.generate_vector()))
  e2=GHRRHyperdimensionalEngine(dim=128);e3=GHRRHyperdimensionalEngine(dim=128)
  np.testing.assert_array_equal(e2.generate_vector(),e3.generate_vector())
 def test_legacy_blob_and_corruption(self):
  with tempfile.TemporaryDirectory() as folder:
   path=str(Path(folder)/'test.db');engine=GHRRHyperdimensionalEngine(dim=128)
   p=SyntacticPDAG(path,engine);steps=[{'acao':'A'},{'acao':'B'}]
   p.store_route('test','intent',steps);self.assertEqual(p.retrieve_route('test')['steps'],steps)
   c=sqlite3.connect(path)
   try:
    with c:c.execute('UPDATE pdag_syntactic_routes SET ghrr_blob=?',(b'bad',))
   finally:c.close()
   with self.assertRaises(ValueError):p.retrieve_route('test')
 def test_quantization_legacy(self):
  q=QFHRRHyperdimensionalEngine(dimension=17,sparsity=1)
  v=np.arange(17,dtype=np.uint8)%8
  np.testing.assert_array_equal(q.unpack_from_bits(q.pack_to_bits(v),17),v)
  self.assertEqual(q.similarity(v,q.unpack_from_bits(q.pack_to_bits(v),17)),1.0)
  # Legacy encoding has no way to distinguish an inactive zero from phase zero.
  self.assertEqual(q.similarity(np.zeros(17,dtype=np.uint8),np.zeros(17,dtype=np.uint8)),1.0)

class IndexTests(unittest.TestCase):
 def test_filter_exact_fallback_and_budget(self):
  from unittest.mock import patch
  change=patch.object(hyperdimensional,'HAS_NUMBA',False);change.start();self.addCleanup(change.stop)
  e=hyperdimensional.FHRRHyperdimensionalEngine(dimension=256);i=SituationFHRRIndex(e,max_bytes=2048,clock=lambda:10)
  a=IndexedSnapshot('t','one',9,'test',11,'UNVERIFIED',{'objective':'abrir paint'})
  i.put(a)
  with self.assertRaises(ValueError):i.put(IndexedSnapshot('t','expired',1,'test',2,'UNVERIFIED',{'objective':'abrir paint'}))
  result=i.search('t','objective abrir paint');self.assertEqual([r['snapshot'].snapshot_id for r in result],['one'])
  self.assertGreater(result[0]['similarity'],.99)
  # A separate stub simulates an unavailable embedding operation.
  class Broken:
   dim=256
   def text_to_hypervector(self,text):raise RuntimeError('unavailable')
  i.engine=Broken();self.assertEqual(i.search('t','x',exact_snapshot_id='one')[0]['match'],'exact')
  self.assertEqual(i.search('other','x',exact_snapshot_id='one'),[])
  with self.assertRaises(ValueError):i.put(IndexedSnapshot('t','bad',9,'test',11,'UNVERIFIED',{'objective':'x'},representation_version=99))
