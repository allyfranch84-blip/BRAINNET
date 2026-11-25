"""Temporary-database tests; no native actions, models or legacy writes."""
import json
import sqlite3
from contextlib import closing
from experience_journal import ExperienceJournal,encode_steps,verified_receipt,DIM
from memory_recall import recall,read_record
from ghrr_core import GHRRHyperdimensionalEngine
import numpy as np

def plan(*steps):
    return {'status':'execute','steps':list(steps)}

OPEN={'action':'open_app','target':'paint'}
MOVE={'action':'move_to','target':'Ampliar','app':'paint'}
CLICK={'action':'click_target','target':'Ampliar','button':'left','count':1}

def test_persistence_and_recall_after_reopen(tmp_path):
    result={'status':'EFFECT_VERIFIED','context_window':{'app':'mspaint.exe','hwnd':123,'pid':55,'started':1.}}
    record_id=ExperienceJournal(tmp_path).append('task',plan(OPEN),result)
    assert record_id
    found=recall(tmp_path,'paint')['matches'][0]
    assert found['id']==record_id and found['historical_verification']=='EFFECT_RECORDED'
    row=read_record(tmp_path,'verified_experiences',record_id)
    data=json.loads(row['payload'])
    assert data['effect_verified'] is True and data['goal_verified'] is False
    assert not data['execution_authorized'] and 'hwnd' not in data
    with closing(sqlite3.connect(tmp_path/'experience_journal.db')) as conn:
        blob,dim=conn.execute('SELECT ghrr_blob,ghrr_dim FROM verified_experiences').fetchone()
        assert dim==DIM and len(blob)==DIM*16
    assert sorted(p.name for p in tmp_path.iterdir())==['experience_journal.db']

def test_input_only_partial_and_unsupported_are_never_persisted(tmp_path):
    journal=ExperienceJournal(tmp_path)
    assert journal.append('a',plan(CLICK),{'status':'INPUT_SENT'}) is None
    assert journal.append('a',plan(CLICK),{'status':'EFFECT_VERIFIED'}) is None
    assert journal.append('a',plan(OPEN,MOVE),{'status':'PARTIAL'}) is None
    assert journal.append('a',plan(OPEN,MOVE),{'status':'EFFECT_VERIFIED','completed_steps':1,
        'total_steps':2,'sequence_results':[{'status':'EFFECT_VERIFIED','start_step':1,'steps':[OPEN]}]}) is None
    assert not journal.path.exists()

def test_complete_sequence_and_noncommutative_encoding(tmp_path):
    p=plan(OPEN,MOVE)
    result={'status':'EFFECT_VERIFIED','completed_steps':2,'total_steps':2,
        'sequence_results':[{'status':'EFFECT_VERIFIED','start_step':1,'steps':[OPEN]},
                            {'status':'EFFECT_VERIFIED','start_step':2,'steps':[MOVE]}]}
    assert ExperienceJournal(tmp_path).append('sequence',p,result)
    engine=GHRRHyperdimensionalEngine(dim=DIM,matrix_size=2)
    shape=(engine.num_blocks,2,2)
    a=np.frombuffer(encode_steps([OPEN,MOVE]),dtype='<c8').reshape(shape)
    b=np.frombuffer(encode_steps([MOVE,OPEN]),dtype='<c8').reshape(shape)
    assert engine.similarity(a,a)>.99
    assert engine.similarity(a,b)<.95
    assert verified_receipt(p,{**result,'sequence_results':list(reversed(result['sequence_results']))}) is None


def test_concept_card_reopens_real_sqlite_and_has_no_replay_parameters(tmp_path):
    from experience_journal import describe_experience

    record_id = ExperienceJournal(tmp_path).append(
        'open', plan(OPEN), {'status': 'EFFECT_VERIFIED', 'context_window': {'app': 'mspaint.exe'}})
    card = describe_experience(tmp_path, record_id)
    assert card['status'] == 'OBSERVED'
    assert card['stages'] == ['Disponibilizar janela']
    assert card['execution_authorized'] is False and card['goal_verified'] is False
    assert 'steps' not in card and 'hwnd' not in card
