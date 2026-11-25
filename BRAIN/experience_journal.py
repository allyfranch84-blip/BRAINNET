"""Append-only journal of verified motor effects, separate from legacy databases.

An effect receipt is not proof of the user's final goal. No replay or authority
is derived from a stored sequence. GHRR is a derived, versioned representation.
"""
from contextlib import closing
from pathlib import Path
import hashlib
import json
import sqlite3
import time
import uuid

SCHEMA="""CREATE TABLE IF NOT EXISTS verified_experiences (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    label TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    ghrr_blob BLOB NOT NULL,
    ghrr_dim INTEGER NOT NULL,
    encoding TEXT NOT NULL,
    checksum TEXT NOT NULL
)"""
ENCODING='ghrr-ordered-effect-v1'
DIM=256
ALLOWED=frozenset(('open_app','move_to','move'))

def _json(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)

def verified_receipt(plan,result):
    """Only complete effect-verified plans; reject partial or input-only plans."""
    from motor_intent import validate_plan
    validate_plan(plan)
    steps=plan['steps']
    if plan['status']!='execute' or result.get('status')!='EFFECT_VERIFIED':
        return None
    if any(s['action'] not in ALLOWED for s in steps):
        return None
    groups=result.get('sequence_results')
    if groups is not None:
        if (not isinstance(groups,list) or result.get('completed_steps')!=len(steps)
                or result.get('total_steps')!=len(steps)):
            return None
        actual=[]
        for group in groups:
            if group.get('status')!='EFFECT_VERIFIED' or group.get('start_step')!=len(actual)+1:
                return None
            actual.extend(group.get('steps',[]))
        if actual!=steps:
            return None
    window=result.get('context_window') or {}
    app=str(window.get('app',''))[:120]
    # Do not persist HWND, coordinates, titles, chat text or free-form replies.
    # For sequences, only explicit target/qualifier identities are known here.
    label=' '.join(filter(None,[app]+[
        ' '.join(str(s[k]) for k in ('action','app','target','direction') if k in s)
        for s in steps]))
    payload={'steps':steps,'app':app or None,'effect_verified':True,
             'goal_verified':False,'execution_authorized':False,
             'scope':'complete_effect_receipt',
             'source':'motor_executor','context_revalidation_required':True}
    return label,payload

def encode_steps(steps):
    from ghrr_core import GHRRHyperdimensionalEngine
    import numpy as np
    engine=GHRRHyperdimensionalEngine(dim=DIM,matrix_size=2)
    if not steps:
        raise ValueError('empty experience')
    vectors=[engine.generate_vector(ENCODING+':'+_json(step)) for step in steps]
    vector=vectors[0]
    for item in vectors[1:]:
        vector=engine.bind(vector,item)
    if not np.isfinite(vector).all():
        raise ValueError('invalid GHRR')
    return vector.astype('<c8',copy=False).tobytes()

class ExperienceJournal:
    def __init__(self,directory):
        self.path=Path(directory)/'experience_journal.db'

    def append(self,task_id,plan,result):
        receipt=verified_receipt(plan,result)
        if receipt is None:
            return None
        label,payload=receipt
        data=_json(payload)
        blob=encode_steps(payload['steps'])
        checksum=hashlib.sha256(data.encode('utf-8')+blob).hexdigest()
        record_id=uuid.uuid4().hex
        # Separate database, short busy timeout, no migration of legacy memory.
        with closing(sqlite3.connect(self.path,timeout=.15)) as conn,conn:
            conn.execute(SCHEMA)
            conn.execute('INSERT INTO verified_experiences VALUES (?,?,?,?,?,?,?,?,?)',
                (record_id,str(task_id)[:128],time.time(),label,data,blob,DIM,ENCODING,checksum))
        return record_id


def describe_experience(directory, record_id):
    """Translate a historical receipt into a non-executable concept card."""
    from memory_recall import read_record

    record = read_record(directory, 'verified_experiences', record_id)
    if record['status'] != 'OBSERVED':
        return {'status': record['status'], 'execution_authorized': False}
    from motor_intent import validate_plan

    try:
        receipt = json.loads(record['payload'])
        if receipt.get('effect_verified') is not True:
            raise ValueError('unverified effect')
        plan = validate_plan({'status': 'execute', 'steps': receipt['steps']})
        names = {'open_app': 'Disponibilizar janela', 'move_to': 'Localizar controle e posicionar cursor',
                 'move': 'Deslocar cursor'}
        stages = [names[step['action']] for step in plan['steps']]
    except (ValueError, KeyError, TypeError, AttributeError):
        return {'status': 'INCONCLUSIVE', 'execution_authorized': False}
    return {'status': 'OBSERVED', 'record_id': record_id, 'app': receipt.get('app'),
            'stages': stages, 'execution_authorized': False, 'goal_verified': False,
            'requirements': ['Revalidar aplicativo, janela e alvo no contexto atual.',
                             'Obter autorização atual antes de uma nova execução.']}
