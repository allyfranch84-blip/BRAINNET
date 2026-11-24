"""Recall contracts against temporary SQLite databases only."""
import sqlite3
from contextlib import closing
from memory_recall import recall,read_record

def setup_hmem(tmp_path):
    path=tmp_path/'hmem_memory.db'
    with closing(sqlite3.connect(path)) as conn,conn:
        conn.execute('CREATE TABLE hmem_nodes (node_id TEXT PRIMARY KEY, concept_label TEXT, timestamp REAL, payload_json TEXT)')
        conn.execute('CREATE TABLE hmem_schemas (schema_id TEXT PRIMARY KEY, concept_label TEXT, last_updated REAL, sample_count INTEGER, payload_json TEXT)')
        conn.executemany('INSERT INTO hmem_nodes VALUES (?,?,?,?)',[('a','Edição gráfica',1,'{"test":true}'),('b','Música',2,'secret')])
        conn.execute('INSERT INTO hmem_schemas VALUES (?,?,?,?,?)',('s','Edição gráfica',3,4,'x'*5000))
    return path

def test_accent_insensitive_search_preserves_identity_and_omits_payload(tmp_path):
    path=setup_hmem(tmp_path); before=path.read_bytes()
    outcome=recall(tmp_path,'edicao grafica')
    assert outcome['status']=='OBSERVED'
    assert [r['id'] for r in outcome['matches']]==['s','a']
    assert all('payload' not in r and not r['execution_authorized'] for r in outcome['matches'])
    assert path.read_bytes()==before
    assert not (tmp_path/'core1_pdag.db').exists()

def test_exact_record_and_bounded_payload(tmp_path):
    path=setup_hmem(tmp_path); before=path.read_bytes()
    r=read_record(tmp_path,'hmem_schemas','s')
    assert r['status']=='OBSERVED' and r['truncated'] and len(r['payload'])==4000
    assert r['execution_authorized'] is False
    assert read_record(tmp_path,'hmem_nodes',"a' OR 1=1")['status']=='NOT_FOUND'
    assert path.read_bytes()==before

def test_empty_and_unavailable_are_distinct(tmp_path):
    assert recall(tmp_path,'paint')['status']=='UNAVAILABLE'
    setup_hmem(tmp_path)
    r=recall(tmp_path,'paint')
    assert r['status']=='OBSERVED' and not r['matches']
