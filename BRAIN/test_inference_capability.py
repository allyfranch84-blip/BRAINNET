import struct, tempfile, unittest
from pathlib import Path
from unittest.mock import Mock, patch
from inference_capability import UNKNOWN, ExecutionProfile, discover_hardware, inspect_gguf, measurement, plan_execution
from inference_backend import LlamaProcessManager, ConfigurationError

def string(s):
 b=s.encode(); return struct.pack('<Q',len(b))+b
class CapabilityTests(unittest.TestCase):
 def setUp(self):
  self.inv={'ram_available':measurement(8_000_000_000,'test'),'vram_usable':measurement(UNKNOWN,'test'),'llama':measurement({'version':'test','flags':['--device','--n-gpu-layers','--ctx-size','--parallel']},'test')}
  self.model={'architecture':'qwen2','quantization_code':15,'sha256':'a'*64,'metadata':{'qwen2.block_count':24,'qwen2.context_length':32768}}
 def profile(self): return ExecutionProfile('CPU_ONLY',{'device':'cpu','gpu_layers':0,'context_size':2048})
 def test_no_gpu(self):
  with patch('inference_capability._run',return_value=''):
   self.assertEqual(discover_hardware()['vram_usable']['value'],UNKNOWN)
 def test_gpu_unknown_and_divergence(self):
  p=ExecutionProfile('HYBRID_CONSERVATIVE',{'device':'vulkan','gpu_layers':2,'context_size':2048},status='TESTED')
  self.assertIn('VRAM utilizavel desconhecida',plan_execution(self.inv,self.model,p,ram_budget=1,vram_budget=1,max_gpu_layers=4)['reasons'])
  with patch('inference_capability._run',side_effect=['[{"Name":"GPU","AdapterRAM":4294967295}]','b12255','--device --n-gpu-layers --ctx-size','Vulkan0 GPU 8192 MiB']):
   inv=discover_hardware('llama-server.exe');self.assertEqual(inv['vram_usable']['value'],UNKNOWN)
 def test_insufficient_ram_and_untested(self):
  r=plan_execution(self.inv,self.model,self.profile(),ram_budget=9_000_000_000)
  self.assertIn('RAM insuficiente',r['reasons']); self.assertIn('perfil sem teste de estabilidade',r['reasons'])
 def test_bad_gguf(self):
  with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as d:
   p=Path(d)/'bad';p.write_bytes(b'NOPE')
   with self.assertRaises(ValueError):inspect_gguf(p)
 def test_incomplete_metadata(self):
  with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as d:
   p=Path(d)/'m';p.write_bytes(b'GGUF'+struct.pack('<IQQ',3,0,1)+string('general.architecture')+struct.pack('<I',8)+string('qwen2'))
   m=inspect_gguf(p,sha256=True);self.assertEqual(m['quantization_code'],UNKNOWN);self.assertEqual(len(m['sha256']),64)
   self.assertIn('metadados do modelo incompletos',plan_execution(self.inv,m,self.profile(),ram_budget=1)['reasons'])
 def test_excess_layers(self):
  p=ExecutionProfile('HYBRID_BALANCED',{'device':'vulkan','gpu_layers':10,'context_size':2048},status='TESTED')
  self.assertIn('offload excede limite comprovado ou desconhecido',plan_execution(self.inv,self.model,p,ram_budget=1,vram_budget=1,max_gpu_layers=4)['reasons'])
 def test_14b_without_budget(self):
  r=plan_execution(self.inv,self.model,self.profile());self.assertEqual(r['decision'],'INSUFFICIENT_EVIDENCE');self.assertIn('orcamento de RAM nao comprovado',r['reasons'])
 def test_positive_evidence(self):
  p=self.profile();p.status='TESTED';p.observed={'model_sha256':'a'*64,'requested':dict(p.requested),'llama_version':'test'};p.metrics={'ram_peak_bytes':1};self.assertEqual(plan_execution(self.inv,self.model,p,ram_budget=1)['decision'],'APPROVED')
 def test_supervisor_cpu_and_vulkan(self):
  for device,layers in [('cpu',0),('vulkan',4)]:
   p=Mock();p.pid=123;p.stdout=None;p.poll.return_value=None;spawn=Mock(return_value=p)
   with patch.object(Path,'is_file',return_value=True),patch('inference_backend.validate_model_artifacts'):
    m=LlamaProcessManager('llama-server.exe','model.gguf',device=device,gpu_layers=layers,concurrency=1,probe=lambda:False,port_probe=lambda *a:False,popen=spawn);m.start();args=spawn.call_args.args[0]
    self.assertEqual(args[args.index('--n-gpu-layers')+1],str(layers));self.assertEqual(args[args.index('--device')+1],'none' if device=='cpu' else 'Vulkan0')
  with self.assertRaises(ConfigurationError):LlamaProcessManager(None,None,gpu_layers=2)
 def test_unsupported_load_mode(self):
  with patch.object(Path,'is_file',return_value=True),patch('inference_backend.validate_model_artifacts'),patch('inference_backend.subprocess.run',return_value=Mock(returncode=0,stdout='no support')):
   m=LlamaProcessManager('llama-server.exe','model.gguf',load_mode='mmap',probe=lambda:False,port_probe=lambda *a:False,popen=Mock())
   with self.assertRaises(ConfigurationError):m.start()
if __name__=='__main__':unittest.main()

