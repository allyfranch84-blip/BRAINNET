import shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from kiwix_knowledge import KiwixKnowledge,record_reference
from situation_memory import SituationMemory
from development_logs.mission_log import read_events
from test_v97r22_production import make_bridge

FIXTURE=Path(__file__).parent/'testdata'/'kiwix'/'small.zim'
class KiwixTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);shutil.copyfile(FIXTURE,self.root/'small.zim');self.k=KiwixKnowledge(self.root,cache_size=2)
 def tearDown(self):self.tmp.cleanup()
 def test_catalog_search_read_offline(self):
  with patch('urllib.request.urlopen',side_effect=AssertionError('rede proibida')):
   cat=self.k.catalog();self.assertEqual(cat[0]['status'],'AVAILABLE'); self.assertTrue(cat[0]['fulltext'])
   for mode in ('title','fulltext'):
    result=self.k.answer('small.zim','Test',mode=mode)
    self.assertEqual(result['status'],'SOURCE_RETRIEVED');self.assertEqual(result['sources'][0]['article_path'],'A/main.html')
    self.assertIn('Fonte: small.zim',result['reply']);self.assertEqual(result['sources'][0]['evidence'],'UNVERIFIED_SOURCE_TEXT')
 def test_persist_reference_not_verified_fact(self):
  memory=SituationMemory(enabled=True);doc=self.k.answer('small.zim','Test')['sources'][0]
  record_reference(doc,journal_directory=self.root/'events',memory=memory,task_id='demo')
  record=read_events(self.root/'events','mission')[0];self.assertEqual(record['reference']['archive_uuid'],doc['archive_uuid'])
  self.assertEqual(memory.export_eligible(),[]);self.assertFalse(memory.snapshot('demo').observations[0].verified)
 def test_missing_corrupt_and_article_limit(self):
  with self.assertRaises(FileNotFoundError):self.k.search('missing.zim','Test')
  (self.root/'bad.zim').write_bytes(b'bad');self.assertEqual([x for x in self.k.catalog() if x['file']=='bad.zim'][0]['status'],'ERROR')
  with self.assertRaises(ValueError):KiwixKnowledge(self.root,max_article_bytes=10).read('small.zim','A/main.html')
 def test_cache_is_bounded(self):
  for term in ('Test','ZIM','file'):self.k.search('small.zim',term)
  self.assertLessEqual(len(self.k._cache),2)
 def test_real_chat_handler_with_fixture(self):
  brain=self.root/'BRAIN';brain.mkdir();directory=self.root/'knowledge'/'zim';directory.mkdir(parents=True);shutil.copyfile(FIXTURE,directory/'small.zim')
  b=make_bridge();b._kernel.situation_memory=None
  with patch('BRAINNET.__file__',str(brain/'BRAINNET.py')), patch('urllib.request.urlopen',side_effect=AssertionError('network')):
   result=b.send_command('/offline Test')
  self.assertEqual(result['status'],'SOURCE_RETRIEVED');self.assertIn('Fonte: small.zim',result['reply'])
  self.assertEqual(result['sources'][0]['evidence'],'UNVERIFIED_SOURCE_TEXT')
if __name__=='__main__':unittest.main()
