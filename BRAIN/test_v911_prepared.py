"""Prepared V9.1.1 tests; not executed during this mission."""
import unittest
from unittest.mock import Mock
import numpy as np
from qfhrr_core import QFHRRHyperdimensionalEngine
from pdag_ghrr_extension import SyntacticPDAG

class PreparedContracts(unittest.TestCase):
    def test_qfhrr_zero_phase_and_absence_are_distinct(self):
        engine=QFHRRHyperdimensionalEngine(dimension=3)
        phases=np.array([0,0,7],dtype=np.uint8)
        present=np.array([True,False,True],dtype=bool)
        values,mask=engine.unpack_masked_v2(engine.pack_masked_v2(phases,present))
        np.testing.assert_array_equal(values,phases)
        np.testing.assert_array_equal(mask,present)
        with self.assertRaises(ValueError):engine.unpack_masked_v2(b'broken')

    def test_route_key_includes_entire_intent_and_context(self):
        prefix='a'*50
        self.assertNotEqual(SyntacticPDAG.route_key(prefix+'x',{}),SyntacticPDAG.route_key(prefix+'y',{}))
        self.assertNotEqual(SyntacticPDAG.route_key('x',{'window':'one'}),SyntacticPDAG.route_key('x',{'window':'two'}))

    def test_route_is_only_proposed(self):
        p=object.__new__(SyntacticPDAG)
        p.retrieve_route=Mock(return_value={'intent':'x','steps':[{'acao':'CLICK'}]})
        result=p.propose_route('legacy')
        self.assertEqual(result['status'],'REVIEW_REQUIRED')
        self.assertFalse(result['execution_authorized'])
        self.assertEqual(result['historical_verification'],'UNKNOWN')
