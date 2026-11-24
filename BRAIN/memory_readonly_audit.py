"""Read-only legacy memory audit; no migrations, pruning, or payload retrieval."""
from pathlib import Path
from contextlib import closing
import sqlite3
import time

SCHEMAS={
    'core1_pdag.db':('pdag_nodes','pdag_syntactic_routes','transitions','concept_invariants','concepts'),
    'hmem_memory.db':('hmem_nodes','hmem_schemas'),
    'long_context.db':('long_context_state',),
}

def audit_memory(directory, *, seconds=5.0):
    results=[]
    for name,expected in SCHEMAS.items():
        path=Path(directory)/name
        if not path.is_file():
            results.append({'file':name,'status':'ABSENT'})
            continue
        deadline=time.monotonic()+seconds
        try:
            with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=.5)) as conn:
                conn.execute('PRAGMA query_only=ON')
                conn.set_progress_handler(lambda:int(time.monotonic()>=deadline),1000)
                check=conn.execute('PRAGMA quick_check(1)').fetchone()
                actual={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                counts={}
                for table in expected:
                    if table in actual:
                        counts[table]=conn.execute('SELECT COUNT(*) FROM "'+table+'"').fetchone()[0]
                    else:
                        counts[table]=None
                results.append({'file':name,'status':'CHECK_OK' if check==('ok',) else 'CHECK_FAILED','counts':counts})
        except (sqlite3.Error,OSError) as exc:
            results.append({'file':name,'status':'UNAVAILABLE','error':type(exc).__name__})
    return results
