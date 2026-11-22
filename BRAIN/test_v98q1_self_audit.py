import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from self_inspector import SelfInspector

class InspectorAuditTests(unittest.TestCase):
 def test_audit_reads_symbols_without_rollback_and_journals(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); source=root/'example.py'; source.write_text('def inspect_me():\n    return 1\n',encoding='utf-8')
   before=source.read_bytes()
   with patch('subprocess.run',side_effect=OSError('git unavailable')):
    result=SelfInspector(root).audit_read_only(['example.py'])
   self.assertEqual(source.read_bytes(),before)
   self.assertEqual(result['inventories']['example.py']['symbols'][0]['name'],'inspect_me')
   self.assertEqual(result['regression']['status'],'NOT_RUN')
   self.assertTrue((root/'development_logs'/'missions.jsonl').exists())
 def test_rejects_outside_scope(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(ValueError): SelfInspector(d).audit_read_only(['../outside.py'])
 def test_timeout_rejects_unlisted_test(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(ValueError): SelfInspector(d).diagnose_audited_timeout('test_physical.py::test_move')
if __name__=='__main__': unittest.main()
