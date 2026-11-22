import io,json,unittest
from unittest.mock import Mock,patch
from test_v97r22_production import make_bridge
from inference_backend import HTTPInferenceBackend,InferenceRequest,InvalidResponse,InferenceCancelled

def wire(frames): return ('\n'.join(json.dumps(f) for f in frames)+'\n').encode()
class StreamTests(unittest.TestCase):
 def backend(self,frames,kind='ollama'):
  return HTTPInferenceBackend('http://localhost:12345','fake',kind,opener=lambda req,timeout:io.BytesIO(wire(frames)))
 def test_ollama_interleaved_channels(self):
  b=self.backend([{'message':{'thinking':'A'},'done':False},{'message':{'content':'B'},'done':False},{'message':{'thinking':'C','content':'D'},'done':True}])
  events=list(b.stream_events(InferenceRequest(messages=[{'role':'user','content':'x'}]),chat=True))
  self.assertEqual([(e['channel'],e.get('text')) for e in events],[('THINKING','A'),('CONTENT','B'),('THINKING','C'),('CONTENT','D'),('OPERATIONAL','')])
 def test_llama_reasoning_content(self):
  b=self.backend([{'choices':[{'delta':{'reasoning_content':'x'},'finish_reason':None}]},{'choices':[{'delta':{'content':'y'},'finish_reason':'stop'}]}],kind='llamacpp')
  self.assertEqual([e['channel'] for e in b.stream_events(InferenceRequest(messages=[{'role':'user','content':'x'}]),chat=True)],['THINKING','CONTENT','OPERATIONAL'])
 def test_missing_thinking_not_fabricated(self):
  b=self.backend([{'response':'ok','done':True}]);self.assertEqual([e['channel'] for e in b.stream_events(InferenceRequest(prompt='x'))],['CONTENT','OPERATIONAL'])
 def test_broken_stream_is_error(self):
  b=self.backend([{'response':'incompleto','done':False}])
  with self.assertRaises(InvalidResponse):list(b.stream_events(InferenceRequest(prompt='x')))
 def test_cancel_during_each_channel(self):
  for frame in ({'thinking':'x','done':False},{'response':'x','done':False}):
   b=self.backend([frame,{'response':'nunca','done':True}]); it=b.stream_events(InferenceRequest(prompt='x',request_id='cancel'))
   next(it); self.assertTrue(b.cancel('cancel'))
   with self.assertRaises(InferenceCancelled):next(it)
 def test_real_chat_emits_ordered_stream(self):
  b=make_bridge();b._push_event=Mock();b.get_effort_mode=Mock(return_value={'mode':'DEEP'})
  frames=[{'thinking':'pensamento','done':False},{'response':'res','done':False},{'response':'posta','done':True}]
  def factory(endpoint,model,kind):return HTTPInferenceBackend(endpoint,model,kind,opener=lambda req,timeout:io.BytesIO(wire(frames)))
  with patch('inference_backend.HTTPInferenceBackend',side_effect=factory):result=b.send_command('O que é uma estrela?')
  events=[c.args[1] for c in b._push_event.call_args_list if c.args[0]=='aios:stream']
  self.assertEqual([e['sequence'] for e in events],list(range(len(events))))
  self.assertEqual([e['channel'] for e in events],['THINKING','CONTENT','CONTENT','OPERATIONAL'])
  self.assertTrue(all(e['task_id']==result['task_budget']['task_id'] and e['message_id']==events[0]['message_id'] for e in events))
  self.assertEqual(result['reply'],'resposta');self.assertNotIn('pensamento',result['reply'])
if __name__=='__main__':unittest.main()
