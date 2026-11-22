import subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import regression_runner as r

class DiagnosticTests(unittest.TestCase):
 def test_timeout_is_not_pass_and_preserves_stack_log(self):
  with tempfile.TemporaryDirectory() as d:
   def expired(*args,**kwargs):
    kwargs['stdout'].write('stack snapshot\n')
    raise subprocess.TimeoutExpired(args[0],kwargs['timeout'])
   with patch.object(r,'LOGS',Path(d)),patch.object(r.subprocess,'run',side_effect=expired):
    result=r.run_visual_diagnostic(timeout=5)
   self.assertEqual(result['status'],'TIMEOUT'); self.assertIsNone(result['exit_code'])
   self.assertIn('stack snapshot',Path(result['log']).read_text(encoding='utf-8'))
 def test_pass_and_failure_classified(self):
  with tempfile.TemporaryDirectory() as d, patch.object(r,'LOGS',Path(d)):
   for code,status in [(0,'PASS'),(1,'FAIL'),(2,'ERROR')]:
    with patch.object(r.subprocess,'run',return_value=subprocess.CompletedProcess([],code)):
     self.assertEqual(r.run_visual_diagnostic(timeout=5)['status'],status)
 def test_no_unlisted_test(self):
  with self.assertRaises(ValueError): r.run_visual_diagnostic(test_id='test_motor_fisico.py')
if __name__=='__main__': unittest.main()
