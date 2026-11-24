"""Explicit read-only recall of legacy memory, with source identities.
No schema creation, access-count updates, model calls, or action dispatch.
Historical labels and routes are evidence of stored records, not live facts.
"""
from contextlib import closing
from pathlib import Path
import sqlite3
import time
import unicodedata

# Each tuple: database, table, identity, searchable label, time, optional count.
SOURCES=(
    ('hmem_memory.db','hmem_nodes','node_id','concept_label','timestamp',None),
    ('hmem_memory.db','hmem_schemas','schema_id','concept_label','last_updated','sample_count'),
    ('core1_pdag.db','pdag_nodes','context_key','intent','last_active','consecutive_successes'),
    ('core1_pdag.db','pdag_syntactic_routes','context_key','intent','last_active',None),
    ('long_context.db','long_context_state','doc_id','doc_id','updated_at','current_chunk'),
)

def _words(value):
    folded=''.join(c for c in unicodedata.normalize('NFKD',str(value).casefold()) if not unicodedata.combining(c))
    return set(''.join(c if c.isalnum() else ' ' for c in folded).split())

def _open(path,deadline):
    conn=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=.3)
    conn.execute('PRAGMA query_only=ON')
    conn.set_progress_handler(lambda:int(time.monotonic()>=deadline),1000)
    return conn

def recall(directory,query,*,limit=12,seconds=3.0):
    if not isinstance(query,str) or not query.strip() or len(query)>200 or type(limit) is not int or not 1<=limit<=30:
        raise ValueError('Consulta inválida')
    tokens=_words(query)
    if not tokens:
        raise ValueError('Consulta sem termos')
    deadline=time.monotonic()+seconds
    results=[]; sources=[]
    for name,table,key,label,stamp,count in SOURCES:
        path=Path(directory)/name
        if not path.is_file():
            sources.append({'table':table,'status':'ABSENT'})
            continue
        try:
            with closing(_open(path,deadline)) as conn:
                # Fixed allowlist of identifiers; never run SQL supplied by a user.
                rows=conn.execute(f'SELECT {key}, substr({label},1,240), {stamp}, {count or "NULL"} FROM {table} ORDER BY {stamp} DESC LIMIT 5000').fetchall()
            for ref,text,ts,n in rows:
                candidate=_words(text or '')
                overlap=len(tokens&candidate)
                if not overlap:
                    continue
                score=overlap/len(tokens)
                results.append({'database':name,'table':table,'id':str(ref),'label':str(text),
                                'timestamp':ts,'count':n,'lexical_score':score,
                                'historical_verification':'UNKNOWN','execution_authorized':False})
            sources.append({'table':table,'status':'READ','scanned':len(rows),'possibly_truncated':len(rows)==5000})
        except (sqlite3.Error,OSError) as exc:
            sources.append({'table':table,'status':'UNAVAILABLE','error':type(exc).__name__})
    results.sort(key=lambda r:(r['lexical_score'],r['timestamp'] or 0),reverse=True)
    return {'status':'OBSERVED' if any(s['status']=='READ' for s in sources) else 'UNAVAILABLE',
            'matches':results[:limit],'sources':sources,'execution_authorized':False}

def read_record(directory,table,record_id,*,seconds=2.0):
    """Read a single explicitly named record, with a bounded raw payload.
    Do not automatically add the returned payload to a motor/LLM prompt.
    """
    payloads={'hmem_nodes':'payload_json','hmem_schemas':'payload_json',
              'pdag_nodes':'pipeline_spec','pdag_syntactic_routes':'pipeline_steps',
              'long_context_state':'cumulative_summary'}
    source=next((s for s in SOURCES if s[1]==table),None)
    if source is None or not isinstance(record_id,str) or not record_id or len(record_id)>256:
        raise ValueError('Fonte ou ID inválido')
    name,_,key,label,stamp,_=source
    path=Path(directory)/name
    if not path.is_file():
        return {'status':'UNAVAILABLE','execution_authorized':False}
    try:
        with closing(_open(path,time.monotonic()+seconds)) as conn:
            column=payloads[table]
            row=conn.execute(f'SELECT substr({label},1,240), {stamp}, substr({column},1,4000), length({column}) FROM {table} WHERE {key}=?',(record_id,)).fetchone()
    except (sqlite3.Error,OSError):
        return {'status':'UNAVAILABLE','execution_authorized':False}
    if row is None:
        return {'status':'NOT_FOUND','execution_authorized':False}
    return {'status':'OBSERVED','table':table,'id':record_id,'label':row[0],
            'timestamp':row[1],'payload':row[2],'truncated':(row[3] or 0)>4000,
            'historical_verification':'UNKNOWN','execution_authorized':False}
