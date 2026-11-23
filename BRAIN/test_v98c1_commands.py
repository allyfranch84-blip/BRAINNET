import io,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from BRAINNET import BrainnetBridge
from test_v97r22_production import make_bridge
from inference_backend import HTTPInferenceBackend
from command_catalog import COMMANDS

class CommandsModesTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.patch=patch('BRAINNET.CONFIG_FILE',Path(self.tmp.name)/'config.json');self.patch.start()
  self.b=make_bridge();self.b.get_effort_mode=BrainnetBridge.get_effort_mode.__get__(self.b)
 def tearDown(self):self.patch.stop();self.tmp.cleanup()
 def test_help_includes_catalog_and_missing_module(self):
  r=self.b.send_command('/help'); self.assertTrue(all(syntax in r['reply'] for _,syntax,*_ in COMMANDS))
  self.assertIn('módulo vision ausente',r['reply']);self.assertNotIn('`/ui <instrução>`',r['reply'])
 def test_modes_independent_and_apply_next_inference(self):
  self.assertEqual(self.b.send_command('/modo deep')['status'],'CONFIGURED')
  self.assertEqual(self.b.send_command('/modo livre')['status'],'CONFIGURED')
  self.assertEqual(self.b.get_effort_mode()['mode'],'DEEP');self.assertEqual(self.b.get_conversation_status()['profile'],'LIVRE')
  requests=[]
  def opener(req,timeout):requests.append(json.loads(req.data));return io.BytesIO(json.dumps({'done':True,'response':'ok'}).encode())
  def factory(endpoint,model,kind):return HTTPInferenceBackend(endpoint,model,kind,opener=opener)
  with patch('inference_backend.HTTPInferenceBackend',side_effect=factory): result=self.b.send_command('O que é uma estrela?')
  self.assertEqual(result['reply'],'ok');self.assertEqual(requests[0]['options']['num_predict'],800)
  self.assertIn('Responda de forma direta',requests[0]['prompt'])
  self.b.send_command('/modo padrao');self.assertEqual(self.b.get_effort_mode()['mode'],'DEEP')
 def test_model_selects_only_installed(self):
  def fake(req,timeout):return io.BytesIO(json.dumps({'models':[{'name':'teste:1'}]}).encode())
  with patch('BRAINNET.urllib.request.urlopen',side_effect=fake):
   self.assertEqual(self.b.send_command('/modelo usar teste:1')['status'],'CONFIGURED')
   self.assertEqual(self.b.send_command('/modelo usar ausente')['status'],'NOT_FOUND')
  self.assertEqual(self.b.get_conversation_status()['model'],'teste:1')
  requests=[]
  def opener(req,timeout):requests.append(json.loads(req.data));return io.BytesIO(json.dumps({'done':True,'response':'ok'}).encode())
  def factory(endpoint,model,kind):return HTTPInferenceBackend(endpoint,model,kind,opener=opener)
  with patch('inference_backend.HTTPInferenceBackend',side_effect=factory):self.b.send_command('O que é uma estrela?')
  self.assertEqual(requests[0]['model'],'teste:1')
 def test_model_endpoint_unavailable_is_explicit(self):
  with patch('BRAINNET.urllib.request.urlopen',side_effect=OSError('offline')):
   r=self.b.send_command('/modelo listar')
  self.assertEqual(r['status'],'UNAVAILABLE');self.assertIn('Ollama indisponível',r['reply'])
 def test_manual_uia_and_vision_use_existing_methods(self):
  eye=Mock();eye.scan_uia_properties.return_value=[{'name':'Segredo','control_type':'ButtonControl'}];self.b._kernel.eye=eye
  self.b._kernel.context_engine=SimpleNamespace(capture_foreground_context=Mock())
  self.b._kernel.vision=SimpleNamespace(descrever_tela=Mock(return_value='Descrição simulada'))
  self.assertEqual(self.b.send_command('/uia scan')['status'],'TARGET_REQUIRED')
  with patch('uia_chat_readonly.inspect_window',return_value={'pid':20,'started':123.0,'rect':(0,0,100,100)}),patch('perception_eye.HAS_UIA_NATIVE',True):
   observed=self.b.send_command('/uia scan 42 20')
  self.assertEqual(observed['status'],'OBSERVED');eye.scan_uia_properties.assert_called_once_with(42,max_controls=100)
  self.assertNotIn('Segredo',str(observed))
  self.b._kernel.context_engine.capture_foreground_context.assert_not_called()
  self.assertEqual(self.b.send_command('/visao agora')['status'],'OBSERVATION_UNVERIFIED')
 def test_motor_ambiguous_and_exact_never_dispatch(self):
  self.b._kernel.bridge=Mock()
  r=self.b.send_command('mova o mouse em qualquer direção');self.assertEqual(r['motor_stage'],'INTENT_RECOGNIZED');self.assertFalse(r['dispatched'])
  self.assertIn('direção e distância',r['reply']);self.assertNotIn('aplicativo',r['reply'].lower())
  r=self.b.send_command('mova o mouse 30 pixels para a direita, sem clicar');self.assertEqual(r['motor_stage'],'AUTHORIZATION_REQUIRED');self.assertFalse(r['dispatched'])
  self.b._kernel.bridge.dispatch.assert_not_called()
 def test_unknown_and_legacy_mode(self):
  self.b._modo_operacao='TRAJETORIA'
  self.assertIn('CONSENSO',self.b.send_command('/switch mode')['reply'])
  r=self.b.send_command('/nao-existe');self.assertLess(len(r['reply']),200);self.assertNotIn('Comandos registrados',r['reply'])
if __name__=='__main__':unittest.main()
