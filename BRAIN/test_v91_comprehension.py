import unittest
from pathlib import Path
from code_mapper import index_symbols
from natural_comprehension import interpret, CAPABILITIES
from long_workflows import BookDraft, inspect_video

class ComprehensionTests(unittest.TestCase):
 def test_large_file_symbol_index(self):
  for name in ('BRAINNET.py','causal_trajectory.py'):
   index=index_symbols(Path(__file__).with_name(name))
   self.assertGreater(index['line_count'],1000)
   self.assertTrue(index['symbols'])
   self.assertTrue(all(item['line']>0 for item in index['symbols']))
   self.assertEqual(len({x['name'] for x in index['symbols']}),len(index['symbols']))
 def test_natural_and_shortcut_capabilities(self):
  for text,cap in [('mostre seus comandos','help'),('/help','help'),('pesquise sobre física','research'),('/pesquisa física','research'),('analize seu codigo','code_audit'),('faça um livo sobre astronomia','book'),('escreva um livro sobre astronomia','book'),('veja esse vidio do youtube','video')]:
   with self.subTest(text=text):
    result=interpret(text);self.assertEqual(result['capability'],cap);self.assertFalse(result['execution_authorized']);self.assertIn(cap,CAPABILITIES)
 def test_sensitive_commands_are_not_approved(self):
  for text in ('não abra o Paint','nao apague meus arquivos','abra o peint','apague arquivo','abra o paint e desenhe um quadrado','isso é ironia'):
   with self.subTest(text=text):
    result=interpret(text);self.assertIsNone(result['capability']);self.assertTrue(result['needs_clarification']);self.assertFalse(result['execution_authorized'])
 def test_original_and_paths_preserved(self):
  text=r'analize seu codigo em A:\Documentos\João.txt 2026'
  r=interpret(text);self.assertEqual(r['original'],text);self.assertIn(r'A:\Documentos\João.txt',r['protected']);self.assertIn('2026',r['protected'])
 def test_book_interruption_resume(self):
  b=BookDraft('synthetic',[str(i) for i in range(30)]);b.record(0,status='REVIEWED',text='one');b.record(1,status='FAILED')
  r=BookDraft.restore(b.serialize());self.assertEqual(r.status,'IN_PROGRESS');self.assertEqual(r.chapters[1]['status'],'FAILED')
  r.record(1,status='CANCELLED');self.assertNotEqual(r.status,'COMPLETE')
 def test_video_states_without_network(self):
  url='https://www.youtube.com/watch?v=synthetic'
  ok=inspect_video(url,lambda u:{'title':'fake'},lambda u:[{'start':0,'text':'caption'}])
  self.assertEqual(ok['status'],'CAPTIONS_AVAILABLE');self.assertFalse(ok['visual_analyzed'])
  self.assertEqual(inspect_video(url,lambda u:{},lambda u:[])['status'],'CAPTIONS_UNAVAILABLE')
  def fail(u):raise OSError('offline')
  self.assertEqual(inspect_video(url,fail,lambda u:[])['status'],'UNAVAILABLE')
  self.assertEqual(inspect_video('https://youtube.com.evil.test/a',lambda u:{},lambda u:[])['status'],'INVALID_URL')
