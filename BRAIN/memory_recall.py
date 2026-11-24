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
    ('experience_journal.db','verified_experiences','id','label','timestamp',None),
    ('hmem_memory.db','hmem_nodes','node_id','concept_label','timestamp',None),
    ('hmem_memory.db','hmem_schemas','schema_id','concept_label','last_updated','sample_count'),
    ('core1_pdag.db','pdag_nodes','context_key','intent','last_active','consecutive_successes'),
    ('core1_pdag.db','pdag_syntactic_routes','context_key','intent','last_active',None),
    ('core1_pdag.db','transitions','id',"app_name || ' | ' || COALESCE(intent,'')",'timestamp',None),
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

def _grams(tokens):
    return {word[i:i+3] for word in tokens for i in range(len(word)-2)}

def _label_vector(engine,grams):
    # A deliberately small associative lexical representation, not an embedding
    # of meaning. No shared token cache or retained matrix is allocated.
    import numpy as np
    total=np.zeros(engine.dim,dtype=np.complex64)
    for gram in sorted(grams):
        total+=engine.generate_vector('recall:trigram:v1:'+gram)
    return np.exp(1j*np.angle(total)).astype(np.complex64)

def recall(directory,query,*,limit=12,seconds=3.0,engine=None):
    if not isinstance(query,str) or not query.strip() or len(query)>200 or type(limit) is not int or not 1<=limit<=30:
        raise ValueError('Consulta inválida')
    tokens=_words(query)
    if not tokens:
        raise ValueError('Consulta sem termos')
    deadline=time.monotonic()+seconds
    results=[]; sources=[]
    qgrams=_grams(tokens)
    qvector=_label_vector(engine,qgrams) if engine is not None and qgrams else None
    scores={}
    approximate_truncated=False
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
                score=overlap/len(tokens)
                similarity=None
                match='LEXICAL'
                if not overlap:
                    if qvector is None:
                        continue
                    grams=_grams(candidate)
                    if not grams & qgrams:
                        continue
                    if time.monotonic()>=deadline:
                        approximate_truncated=True
                        continue
                    cache_key=tuple(sorted(grams))
                    if cache_key not in scores:
                        import numpy as np
                        vec=_label_vector(engine,grams)
                        scores[cache_key]=float(np.real(np.vdot(qvector,vec))/engine.dim)
                    similarity=scores[cache_key]
                    if similarity<0.10:
                        continue
                    match='FHRR_LEXICAL_CANDIDATE'
                results.append({'database':name,'table':table,'id':str(ref),'label':str(text),
                                'timestamp':ts,'count':n,'lexical_score':score,'fhrr_similarity':similarity,'match':match,
                                'historical_verification':'EFFECT_RECORDED' if table=='verified_experiences' else 'UNKNOWN','execution_authorized':False})
            sources.append({'table':table,'status':'READ','scanned':len(rows),'possibly_truncated':len(rows)==5000})
        except (sqlite3.Error,OSError) as exc:
            sources.append({'table':table,'status':'UNAVAILABLE','error':type(exc).__name__})
    results.sort(key=lambda r:(r['lexical_score'],r['fhrr_similarity'] or 0,r['timestamp'] or 0),reverse=True)
    # In hybrid mode, leave room for different concepts and sources rather
    # than returning twelve identical process labels.
    if engine is not None:
        selected=[]; groups={}
        for item in results:
            group=(item['table'],tuple(sorted(_words(item['label']))))
            if groups.get(group,0)>=3:
                continue
            groups[group]=groups.get(group,0)+1
            selected.append(item)
            if len(selected)>=limit:
                break
    else:
        selected=results[:limit]
    return {'status':'OBSERVED' if any(s['status']=='READ' for s in sources) else 'UNAVAILABLE',
            'matches':selected,'sources':sources,'candidate_count':len(results),
            'approximate_truncated':approximate_truncated,'execution_authorized':False}

def read_record(directory,table,record_id,*,seconds=2.0):
    """Read a single explicitly named record, with a bounded raw payload.
    Do not automatically add the returned payload to a motor/LLM prompt.
    """
    payloads={'verified_experiences':'payload_json','hmem_nodes':'payload_json','hmem_schemas':'payload_json',
              'pdag_nodes':'pipeline_spec','pdag_syntactic_routes':'pipeline_steps',
              'long_context_state':'cumulative_summary','transitions':'steps_json'}
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
            'historical_verification':'EFFECT_RECORDED' if table=='verified_experiences' else 'UNKNOWN','execution_authorized':False}
