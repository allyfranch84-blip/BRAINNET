import tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from long_workflows import BookDraft
from test_v97r22_production import make_bridge

class LongDraftTests(unittest.TestCase):
 def test_multiple_sections_and_context(self):
  d=BookDraft('tema',['a','b','c']); calls=[]; events=[]; saves=[]
  def generate(prompt):
   calls.append(prompt); return SimpleNamespace(text='seção '+str(len(calls)),finish_reason='stop')
  self.assertEqual(d.generate_sections(generate,lambda x:saves.append(x.serialize()),emit=lambda i,t:events.append((i,t))),'DRAFT_COMPLETE')
  self.assertIn('seção 1',calls[1]); self.assertEqual(len(events),3);self.assertEqual(len(saves),4)
 def test_incomplete_is_preserved_and_not_overwritten(self):
  d=BookDraft('tema',['a']);saved=[]
  self.assertEqual(d.generate_sections(lambda p:SimpleNamespace(text='parcial',finish_reason='length'),lambda x:saved.append(x.serialize())),'PARTIAL_UNCONFIRMED')
  restored=BookDraft.restore(saved[-1]); calls=[]
  self.assertEqual(restored.generate_sections(lambda p:calls.append(p),lambda x:None),'PARTIAL_UNCONFIRMED')
  self.assertEqual(restored.chapters[0]['text'],'parcial');self.assertEqual(calls,[])
 def test_duplicate_stops(self):
  d=BookDraft('tema',['a','b']); status=d.generate_sections(lambda p:SimpleNamespace(text='igual',finish_reason='stop'),lambda x:None)
  self.assertEqual(status,'PARTIAL_DUPLICATE')
 def test_adapter_reports_output_limit(self):
  import io,json
  from inference_backend import HTTPInferenceBackend,InferenceRequest
  envelope={'done':True,'done_reason':'length','response':'trecho','eval_count':10}
  backend=HTTPInferenceBackend('http://localhost:12345','fake','ollama',opener=lambda req,timeout:io.BytesIO(json.dumps(envelope).encode()))
  result=backend.generate(InferenceRequest(prompt='x',max_tokens=10))
  self.assertEqual(result.finish_reason,'length')
 def test_cancelled_preserves_previous(self):
  d=BookDraft('tema',['a','b']); d.chapters[0].update(status='DRAFT',text='anterior');save=[]
  self.assertEqual(d.generate_sections(lambda p:None,lambda x:save.append(x.serialize()),cancelled=lambda:True),'CANCELLED')
  self.assertEqual(d.chapters[0]['text'],'anterior')
 def test_real_chat_uses_sections_without_model(self):
  b=make_bridge(); n=[]
  def fake(prompt,*,return_result=False):
   n.append(prompt);return SimpleNamespace(text='texto '+str(len(n)),finish_reason='stop')
  with tempfile.TemporaryDirectory() as folder, patch('BRAINNET.__file__',str(Path(folder)/'BRAINNET.py')), patch.object(b,'_budgeted_conversation',side_effect=fake):
   result=b.send_command('/escreva tema de teste')
   self.assertEqual(result['status'],'DRAFT_COMPLETE')
   self.assertEqual(result['long_task_id'],result['task_budget']['task_id'])
   self.assertTrue((Path(folder)/'long_drafts'/(result['long_task_id']+'.json')).exists())
   self.assertIn('texto 3',result['reply'])
 def test_resume_keeps_document_and_uses_new_request_budget(self):
  b=make_bridge(); calls=[]
  def first(prompt,*,return_result=False):
   calls.append(prompt)
   if len(calls)==2: raise RuntimeError('offline')
   return SimpleNamespace(text='seção inicial',finish_reason='stop')
  def later(prompt,*,return_result=False):
   return SimpleNamespace(text='seção '+str(len(prompt)),finish_reason='stop')
  with tempfile.TemporaryDirectory() as folder, patch('BRAINNET.__file__',str(Path(folder)/'BRAINNET.py')):
   with patch.object(b,'_budgeted_conversation',side_effect=first): first_result=b.send_command('/escreva tema')
   with patch.object(b,'_budgeted_conversation',side_effect=later): resumed=b.send_command('/continue '+first_result['long_task_id'])
   self.assertEqual(first_result['status'],'PARTIAL_ERROR')
   self.assertEqual(resumed['long_task_id'],first_result['long_task_id'])
   self.assertNotEqual(resumed['task_budget']['task_id'],first_result['task_budget']['task_id'])
   self.assertIn('seção inicial',resumed['reply'])
if __name__=='__main__': unittest.main()
