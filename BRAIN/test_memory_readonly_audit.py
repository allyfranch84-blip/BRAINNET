"""Temporary databases only. Never open the user's memory."""
import sqlite3
from memory_readonly_audit import audit_memory

def test_readonly_audit_reports_counts_without_changes(tmp_path):
    path=tmp_path/'hmem_memory.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE hmem_nodes (id INTEGER)')
        conn.executemany('INSERT INTO hmem_nodes VALUES (?)',[(1,),(2,)])
    before=path.read_bytes()
    results={r['file']:r for r in audit_memory(tmp_path)}
    assert results['hmem_memory.db']['status']=='CHECK_OK'
    assert results['hmem_memory.db']['counts']=={'hmem_nodes':2,'hmem_schemas':None}
    assert results['core1_pdag.db']['status']=='ABSENT'
    assert path.read_bytes()==before
    assert not (tmp_path/'core1_pdag.db').exists()

def test_invalid_database_is_not_reported_healthy(tmp_path):
    path=tmp_path/'core1_pdag.db'
    path.write_bytes(b'not a database')
    results={r['file']:r for r in audit_memory(tmp_path)}
    assert results['core1_pdag.db']['status']=='UNAVAILABLE'
