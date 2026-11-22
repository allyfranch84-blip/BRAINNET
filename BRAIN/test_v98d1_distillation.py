import json,threading,unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from distillation_preparation import OfflineTeacherBudget,estimate_cost,validate_dataset,summarize_evaluations

class DistillationTests(unittest.TestCase):
 def setUp(self):
  self.row={'input':'teste sintético','local_response':None,'verified_outcome':'simulado','category':'intent','criterion':'resposta válida','evidence_id':'synthetic','teacher_model':'test-only','group_id':'sample'}
  self.ok=lambda req:{'choices':[{'message':{'content':'resposta simulada'}}],'usage':{'prompt_tokens':100,'completion_tokens':10}}
 def request(self,b,transport=None,**kw):
  args={'input_tokens':100,'max_output_tokens':20,'input_rate':'1','output_rate':'2','transport':transport or self.ok,'simulation':True,'license_reviewed':True};args.update(kw)
  return b.request(self.row,**args)
 def test_no_network_default(self):
  with self.assertRaises(RuntimeError):OfflineTeacherBudget().request(self.row,input_tokens=1,max_output_tokens=1,input_rate=1,output_rate=1)
 def test_deduplicate_and_cost(self):
  b=OfflineTeacherBudget();calls=[]
  def fake(req):calls.append(req);return self.ok(req)
  a=self.request(b,fake);c=self.request(b,fake)
  self.assertEqual(a,c);self.assertEqual(len(calls),1);self.assertEqual(a['cost_usd'],'0.00012')
 def test_reject_over_budget_and_invalid_rates(self):
  with self.assertRaises(RuntimeError):self.request(OfflineTeacherBudget('0.00001'))
  with self.assertRaises(ValueError):estimate_cost(1,1,'NaN','0')
 def test_unknown_cost_blocks_retry(self):
  b=OfflineTeacherBudget()
  def fail(req):raise TimeoutError()
  with self.assertRaises(TimeoutError):self.request(b,fail)
  with self.assertRaises(RuntimeError):self.request(b)
  self.assertGreater(b.reserved,0)
 def test_concurrent_never_double_dispatch(self):
  b=OfflineTeacherBudget();entered=threading.Event();release=threading.Event();calls=[]
  def slow(req):calls.append(1);entered.set();release.wait(2);return self.ok(req)
  with ThreadPoolExecutor(max_workers=2) as ex:
   future=ex.submit(self.request,b,slow);self.assertTrue(entered.wait(2))
   with self.assertRaises(RuntimeError):self.request(b,slow)
   release.set();future.result()
  self.assertEqual(len(calls),1)
 def test_same_input_cannot_cross_groups(self):
  with self.assertRaises(ValueError):validate_dataset([self.row,{**self.row,'group_id':'other'}])
 def test_unknown_evaluation_not_success(self):
  out=summarize_evaluations([{'verified':False,'correct':True}]);self.assertIsNone(out['error_rate']);self.assertEqual(out['promotion'],'DISABLED')
if __name__=='__main__':unittest.main()
