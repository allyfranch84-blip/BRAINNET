import io,json,unittest
from unittest.mock import patch,Mock
from test_v97r22_production import make_bridge
from inference_backend import HTTPInferenceBackend

class DeepOperationalTests(unittest.TestCase):
 def test_real_chat_emits_task_and_inference_with_provenance(self):
  b=make_bridge();b._push_event=Mock();b.get_effort_mode=Mock(return_value={'mode':'DEEP'})
  def opener(req,timeout): return io.BytesIO(json.dumps({'done':True,'done_reason':'stop','response':'resposta','eval_count':5}).encode())
  def factory(endpoint,model,kind):return HTTPInferenceBackend(endpoint,model,kind,opener=opener)
  with patch('inference_backend.HTTPInferenceBackend',side_effect=factory): result=b.send_command('O que é uma estrela?')
  events=[c.args[1] for c in b._push_event.call_args_list if c.args[0]=='aios:reasoning']
  self.assertEqual([e['kind'] for e in events],['task_started','model_selected','inference_completed','task_finished'])
  self.assertTrue(all(e['task_id']==result['task_budget']['task_id'] and e['source'] and e['timestamp'] for e in events))
  self.assertEqual(events[1]['native_thinking'],'UNKNOWN');self.assertEqual(result['reply'],'resposta')
  self.assertNotIn('thinking',result)
 def test_backend_failure_is_event_not_success(self):
  b=make_bridge();b._push_event=Mock()
  def factory(endpoint,model,kind):return HTTPInferenceBackend(endpoint,model,kind,opener=Mock(side_effect=OSError('offline')))
  with patch('inference_backend.HTTPInferenceBackend',side_effect=factory): result=b.send_command('O que é uma estrela?')
  events=[c.args[1] for c in b._push_event.call_args_list if c.args[0]=='aios:reasoning']
  self.assertIn('inference_error',[e['kind'] for e in events]);self.assertIn('Não foi possível',result['reply'])
if __name__=='__main__': unittest.main()
