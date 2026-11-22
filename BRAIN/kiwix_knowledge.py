"""Read-only, opt-in access to local ZIM; source text is untrusted data."""
from collections import OrderedDict
from html.parser import HTMLParser
from pathlib import Path
import hashlib,time,sys

VENDOR=Path(__file__).resolve().parent.parent/'vendor'/'kiwix'
if str(VENDOR) not in sys.path: sys.path.insert(0,str(VENDOR))

class _Text(HTMLParser):
 def __init__(self): super().__init__(convert_charrefs=True);self.parts=[];self.hidden=0
 def handle_starttag(self,tag,attrs):
  if tag.lower() in ('script','style','noscript'):self.hidden+=1
  elif tag.lower() in ('p','br','div','h1','h2','li'):self.parts.append(' ')
 def handle_endtag(self,tag):
  if tag.lower() in ('script','style','noscript') and self.hidden:self.hidden-=1
 def handle_data(self,data):
  if not self.hidden:self.parts.append(data)

def _archive(path):
 from libzim.reader import Archive
 return Archive(str(path))

class KiwixKnowledge:
 def __init__(self,directory,*,cache_size=16,max_article_bytes=1048576,max_excerpt=4000):
  self.directory=Path(directory).resolve();self.cache_size=max(0,min(int(cache_size),32));self.max_article_bytes=max_article_bytes;self.max_excerpt=max_excerpt;self._cache=OrderedDict()
 def catalog(self):
  out=[]
  if not self.directory.is_dir():return out
  for path in sorted(self.directory.glob('*.zim')):
   try:
    if path.resolve().parent != self.directory:continue
    z=_archive(path)
    def meta(key):
     try:return z.get_metadata(key).decode('utf-8','replace')[:256]
     except (KeyError,RuntimeError):return None
    out.append({'file':path.name,'uuid':str(z.uuid),'date':meta('Date'),'title':meta('Title'),'fulltext':bool(z.has_fulltext_index),'status':'AVAILABLE'})
   except Exception as exc:out.append({'file':path.name,'status':'ERROR','error_type':type(exc).__name__})
  return out
 def search(self,filename,query,*,mode='title',limit=5):
  if not isinstance(filename,str) or Path(filename).name!=filename or not filename.lower().endswith('.zim'):raise ValueError('invalid archive name')
  if not isinstance(query,str) or not query.strip() or len(query)>256 or mode not in ('title','fulltext') or type(limit) is not int or not 1<=limit<=10:raise ValueError('invalid query')
  path=(self.directory/filename).resolve()
  if path.parent!=self.directory or not path.is_file():raise FileNotFoundError(filename)
  key=(filename,path.stat().st_size,path.stat().st_mtime_ns,query,mode,limit)
  if key in self._cache:self._cache.move_to_end(key);return [dict(x) for x in self._cache[key]]
  z=_archive(path)
  if mode=='title':
   from libzim.suggestion import SuggestionSearcher
   matches=SuggestionSearcher(z).suggest(query).getResults(0,limit)
  else:
   if not z.has_fulltext_index:raise LookupError('fulltext index unavailable')
   from libzim.search import Searcher,Query
   matches=Searcher(z).search(Query().set_query(query)).getResults(0,limit)
  result=[]
  for entry_path in matches:
   e=z.get_entry_by_path(entry_path);result.append({'path':e.path,'title':e.title})
  if self.cache_size:
   self._cache[key]=result
   while len(self._cache)>self.cache_size:self._cache.popitem(last=False)
  return [dict(x) for x in result]
 def read(self,filename,article_path):
  if not isinstance(filename,str) or Path(filename).name!=filename or not filename.lower().endswith('.zim'):raise ValueError('invalid archive name')
  if not isinstance(article_path,str) or not article_path or len(article_path)>1024:raise ValueError('invalid article path')
  path=(self.directory/filename).resolve()
  if path.parent!=self.directory or not path.is_file():raise FileNotFoundError(filename)
  before=path.stat();z=_archive(path);entry=z.get_entry_by_path(article_path);item=entry.get_item()
  if item.mimetype not in ('text/html','text/plain'):raise ValueError('article is not textual')
  if item.size>self.max_article_bytes:raise ValueError('article exceeds size limit')
  text=bytes(item.content).decode('utf-8','replace')
  if item.mimetype=='text/html':
   parser=_Text();parser.feed(text);text=' '.join(' '.join(parser.parts).split())
  date=None
  try:date=z.get_metadata('Date').decode('utf-8','replace')[:128]
  except (KeyError,RuntimeError):pass
  after=path.stat()
  if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise RuntimeError('archive changed during read')
  return {'archive':filename,'archive_uuid':str(z.uuid),'archive_date':date,'article_path':entry.path,'title':entry.title,
          'archive_size':after.st_size,'archive_mtime_ns':after.st_mtime_ns,
          'excerpt':text[:self.max_excerpt],'truncated':len(text)>self.max_excerpt,'observed_at':time.time(),
          'evidence':'UNVERIFIED_SOURCE_TEXT','instruction_trust':'UNTRUSTED'}
 def answer(self,filename,query,*,mode='title'):
  hits=self.search(filename,query,mode=mode)
  if not hits:return {'status':'NOT_FOUND','sources':[],'reply':'Nenhum artigo local encontrado.'}
  doc=self.read(filename,hits[0]['path'])
  return {'status':'SOURCE_RETRIEVED','sources':[doc],'reply':doc['excerpt']+'\n\nFonte: '+filename+' | '+doc['article_path']+' | '+str(doc['archive_date'] or 'data desconhecida')}

def record_reference(doc,*,journal_directory,memory=None,task_id=None,hmem=None):
 from development_logs.mission_log import append_event
 # Persist provenance only; retrieved statements are not verified facts.
 fields={k:doc.get(k) for k in ('archive','archive_uuid','archive_date','archive_size','archive_mtime_ns','article_path','title','observed_at','evidence')}
 fields.update({'verification_state':'SOURCE_UNVERIFIED','concept_relations':[{'concept':doc.get('title'),'relation':'ARTICLE_TITLE','verified':False}]})
 node_id=None
 if hmem is not None:
  import uuid
  node_id=hmem.record_episodic_node(concept='kiwix_reference',payload=fields,context_tuple='kiwix_source',
                                    session_id=task_id or 'unassigned',step_idx=int(uuid.uuid4().hex[:8],16))
 event_id=append_event(journal_directory,'mission',{'mission_id':'KIWIX_REFERENCE','reference':fields,'concepts':[doc.get('title')], 'task_id':task_id})
 if memory is not None:
  from situation_memory import Observation
  now=time.time(); memory.update(Observation('kiwix:'+hashlib.sha256((str(doc['archive_uuid'])+doc['article_path']).encode()).hexdigest()[:16],fields,'kiwix',now,now+300,task_id=task_id,verified=False,persist_eligible=False))
 return node_id or event_id

def recall_reference(knowledge,hmem,node_id):
 episode=hmem.get_episodic_node(node_id)
 if not episode or episode.get('context')!='kiwix_source' or episode.get('concept')!='kiwix_reference':
  return {'status':'REFERENCE_NOT_FOUND'}
 ref=episode['payload']
 filename=ref.get('archive')
 if not isinstance(filename,str) or Path(filename).name!=filename:return {'status':'SOURCE_UNAVAILABLE','reference_id':node_id}
 path=(knowledge.directory/filename).resolve()
 if path.parent!=knowledge.directory:return {'status':'SOURCE_UNAVAILABLE','reference_id':node_id}
 try: stat=path.stat()
 except FileNotFoundError:return {'status':'SOURCE_MISSING','reference_id':node_id}
 if (stat.st_size,stat.st_mtime_ns)!=(ref.get('archive_size'),ref.get('archive_mtime_ns')):
  return {'status':'SOURCE_CHANGED','reference_id':node_id}
 try:
  doc=knowledge.read(ref['archive'],ref['article_path'])
 except FileNotFoundError:return {'status':'SOURCE_MISSING','reference_id':node_id}
 except Exception:return {'status':'SOURCE_UNAVAILABLE','reference_id':node_id}
 for key in ('archive_uuid','archive_size','archive_mtime_ns','article_path'):
  if ref.get(key) is None or doc.get(key)!=ref.get(key):return {'status':'SOURCE_CHANGED','reference_id':node_id}
 if doc.get('archive_date')!=ref.get('archive_date'):return {'status':'SOURCE_CHANGED','reference_id':node_id}
 return {'status':'SOURCE_RETRIEVED','reference_id':node_id,'source':doc,
         'reply':doc['excerpt']+'\n\nFonte: '+doc['archive']+' | '+doc['article_path']+' | '+str(doc['archive_date'] or 'data desconhecida')}
