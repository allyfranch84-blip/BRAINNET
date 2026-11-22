import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import regression_runner as runner

class RunnerTests(unittest.TestCase):
 def test_new_failure_is_reported_against_passed_baseline(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); base=root/'baseline.json'; logs=root/'logs'
   base.write_text(json.dumps({'cases':{'test_demo::test_one':{'status':'passed','failure_signature':None}},'selection':['fake.py']}))
   def fake_run(args,cwd,log,env=None):
    path=next(x.split('=',1)[1] for x in args if x.startswith('--junitxml='))
    Path(path).write_text('<testsuites><testsuite><testcase classname="test_demo" name="test_one"><failure message="boom"/></testcase></testsuite></testsuites>')
    return 1
   with patch.object(runner,'BASELINE',base),patch.object(runner,'LOGS',logs),patch.object(runner,'GROUPS',{'fast':['fake.py'],'integration':[],'visual_history':[]}),patch.object(runner,'run',side_effect=fake_run),patch('sys.argv',['regression_runner.py','--suite','fast']):
    self.assertEqual(runner.main(),1)
    summary=json.loads(next(logs.glob('*_summary.json')).read_text(encoding='utf-8'))
    self.assertEqual(summary['new_failures'],['test_demo::test_one'])
 def test_e2e_does_not_run_tests(self):
  with patch('sys.argv',['regression_runner.py','--suite','e2e-supervised']),patch.object(runner,'run') as call:
   self.assertEqual(runner.main(),2); call.assert_not_called()
if __name__=='__main__': unittest.main()
