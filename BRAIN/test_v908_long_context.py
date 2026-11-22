import unittest
from unittest.mock import patch
from long_context_engine import LongContextEngine, ProvenanceContext

class LongContextFailureTests(unittest.TestCase):
    def test_failed_chunk_does_not_advance_or_claim_done(self):
        engine = LongContextEngine(':memory:')
        with patch.object(LongContextEngine, '_call_llm_summary', side_effect=['resumo inicial', RuntimeError('offline')]):
            result = engine.process_long_text('a' * 3000, 'synthetic')
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(result['processed_chunks'], 1)
        self.assertEqual(result['failed_chunk'], 2)
        self.assertEqual(result['final_summary'], 'resumo inicial')
        row = engine._conn.execute('SELECT current_chunk,status FROM long_context_state').fetchone()
        self.assertEqual(row, (1, 'FAILED'))
        self.assertIsNone(engine.get_summary('synthetic'))
        engine._conn.close()

    def test_selective_provenance_and_unverified_claims(self):
        ledger = ProvenanceContext('synthetic-task')
        for i in range(3):
            ledger.add_block(str(i), 'synthetic', (i * 100, (i + 1) * 100), dependencies=['0'] if i == 2 else [])
        ledger.record('0', status='PROCESSED', extracted_claims=['A'], evidence=['synthetic:0-100'])
        ledger.record('1', status='FAILED', pending=['retry'])
        ledger.record('2', status='PARTIAL', contradictions=['B conflicts with A'], pending=['check block 0'])
        blocks = ledger.select(['0', '2'])
        self.assertEqual([b['block_id'] for b in blocks], ['0', '2'])
        self.assertEqual(blocks[0]['facts'], [])
        self.assertEqual(blocks[0]['hypotheses'], ['A'])
        self.assertEqual(blocks[1]['dependencies'], ['0'])
        self.assertEqual(ledger.select(['1'])[0]['status'], 'FAILED')
        with self.assertRaises(ValueError):
            ledger.record('0', status='VERIFIED')
