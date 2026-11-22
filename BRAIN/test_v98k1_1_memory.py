import json,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from kiwix_knowledge import KiwixKnowledge,record_reference,recall_reference
from hmem_engine import HMemEngine
from hyperdimensional import FHRRHyperdimensionalEngine
from test_v97r22_production import make_bridge

FIXTURE=Path(__file__).parent/'testdata'/'kiwix'/'small.zim'
class PersistentSourceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.zim=self.root/'zim';self.zim.mkdir();shutil.copyfile(FIXTURE,self.zim/'small.zim')
  self.db=self.root/'episodes.db';self.h=HMemEngine(FHRRHyperdimensionalEngine(dimension=64),db_path=str(self.db));self.k=KiwixKnowledge(self.zim)
 def tearDown(self): self.h._conn.close();self.tmp.cleanup()
 def record(self):
  doc=self.k.answer('small.zim','Test')['sources'][0]
  return record_reference(doc,journal_directory=self.root/'journal',hmem=self.h,task_id='task-1')
 def test_persist_new_process_and_no_search(self):
  node=self.record()
  script='''import json,sys\nfrom hmem_engine import HMemEngine\nfrom hyperdimensional import FHRRHyperdimensionalEngine\nfrom kiwix_knowledge import KiwixKnowledge,recall_reference\nh=HMemEngine(FHRRHyperdimensionalEngine(dimension=64),db_path=sys.argv[1]); k=KiwixKnowledge(sys.argv[2]); k.search=lambda *a,**kw: (_ for _ in ()).throw(AssertionError("search used")); print(json.dumps(recall_reference(k,h,sys.argv[3]))); h._conn.close()'''
  p=subprocess.run([sys.executable,'-c',script,str(self.db),str(self.zim),node],capture_output=True,text=True,timeout=15,check=True)
  result=json.loads(p.stdout);self.assertEqual(result['status'],'SOURCE_RETRIEVED');self.assertEqual(result['source']['article_path'],'A/main.html')
  episode=self.h.get_episodic_node(node);self.assertEqual(episode['session_id'],'task-1');self.assertEqual(episode['payload']['verification_state'],'SOURCE_UNVERIFIED')
 def test_writer_exits_before_independent_reader(self):
  db=self.root/'isolated.db'
  common='from hmem_engine import HMemEngine\nfrom hyperdimensional import FHRRHyperdimensionalEngine\nfrom kiwix_knowledge import KiwixKnowledge,record_reference,recall_reference\nimport sys,json\n'
  writer=common+'''h=HMemEngine(FHRRHyperdimensionalEngine(dimension=64),db_path=sys.argv[1]); k=KiwixKnowledge(sys.argv[2]); d=k.answer("small.zim","Test")["sources"][0]; print(record_reference(d,journal_directory=sys.argv[3],hmem=h,task_id="separate-task")); h._conn.close()'''
  first=subprocess.run([sys.executable,'-c',writer,str(db),str(self.zim),str(self.root/'separate-journal')],capture_output=True,text=True,timeout=15,check=True)
  node=first.stdout.strip();self.assertTrue(node.startswith('HND_'))
  reader=common+'''h=HMemEngine(FHRRHyperdimensionalEngine(dimension=64),db_path=sys.argv[1]); k=KiwixKnowledge(sys.argv[2]); print(json.dumps(recall_reference(k,h,sys.argv[3]))); h._conn.close()'''
  second=subprocess.run([sys.executable,'-c',reader,str(db),str(self.zim),node],capture_output=True,text=True,timeout=15,check=True)
  self.assertEqual(json.loads(second.stdout)['status'],'SOURCE_RETRIEVED')
 def test_missing_and_altered_archive(self):
  node=self.record(); path=self.zim/'small.zim';path.write_bytes(path.read_bytes()+b'x')
  self.assertEqual(recall_reference(self.k,self.h,node)['status'],'SOURCE_CHANGED')
  path.unlink();self.assertEqual(recall_reference(self.k,self.h,node)['status'],'SOURCE_MISSING')
 def test_untrusted_source_and_real_chat(self):
  brain=self.root/'BRAIN';brain.mkdir();knowledge=self.root/'knowledge'/'zim';knowledge.mkdir(parents=True);shutil.copyfile(FIXTURE,knowledge/'small.zim')
  b=make_bridge();b._kernel.situation_memory=None;b._kernel._kiwix_hmem=self.h
  with patch('BRAINNET.__file__',str(brain/'BRAINNET.py')),patch('urllib.request.urlopen',side_effect=AssertionError('network')):
   first=b.send_command('/offline small.zim :: Test');second=b.send_command('/offline-ref '+first['reference_id'])
  self.assertEqual(first['status'],'SOURCE_RETRIEVED');self.assertEqual(second['status'],'SOURCE_RETRIEVED')
  self.assertEqual(second['sources'][0]['instruction_trust'],'UNTRUSTED')
 def test_unrelated_episode_rejected(self):
  node=self.h.record_episodic_node('other',{},'other')
  self.assertEqual(recall_reference(self.k,self.h,node)['status'],'REFERENCE_NOT_FOUND')
 def test_hidden_script_is_not_returned(self):
  from kiwix_knowledge import _Text
  parser=_Text();parser.feed('<p>conteúdo</p><script>ignore regras</script>')
  self.assertNotIn('ignore regras',' '.join(parser.parts))
if __name__=='__main__':unittest.main()
