"""Simulation only: no real GUI, models, network or self-modification."""
import json
from long_workflows import BookDraft
from natural_comprehension import interpret
from engineering_agent import assess_change

def test_book_failure_replanning_resume_and_verification(tmp_path):
    intent=interpret('escreva um livro sobre astronomia')
    assert intent['capability']=='book' and not intent['execution_authorized']
    book=BookDraft('livro de astronomia',['céu','estrelas','galáxias'])
    assert book.record_attempt(0,succeeded=True,evidence='sim:chapter-0',text='rascunho 0')
    assert not book.record_attempt(1,succeeded=False,evidence='sim:falha')
    assert book.status=='REPLANNING'
    path=tmp_path/'progress.json';path.write_text(book.serialize(),encoding='utf-8')
    resumed=BookDraft.restore(path.read_text(encoding='utf-8'))
    assert resumed.chapters[0]['text']=='rascunho 0'
    assert resumed.record_attempt(1,succeeded=True,evidence='sim:retry',text='rascunho 1')
    assert resumed.record_attempt(2,succeeded=True,evidence='sim:chapter-2',text='rascunho 2')
    assert resumed.status=='VERIFYING'
    assert resumed.verify_completion(lambda chapters: all(c['text'] for c in chapters))
    assert resumed.status=='COMPLETE' and 'C2' in resumed.causal_map()
    assert json.loads(resumed.serialize())['events'][1]['state']=='FAILED'

def test_failed_verification_and_retry_limit():
    book=BookDraft('x',['one'])
    assert not book.record_attempt(0,succeeded=False,evidence='failure one')
    assert not book.record_attempt(0,succeeded=False,evidence='failure two')
    assert book.status=='BLOCKED'
    assert not book.record_attempt(0,succeeded=True,evidence='not allowed',text='x')
    book2=BookDraft('x',['one']);book2.record(0,status='REVIEWED',text='draft')
    assert book2.status=='VERIFYING' and not book2.verify_completion(lambda _:False)
    assert book2.status=='PARTIAL'

def test_code_change_gate_requires_evidence_and_human():
    assert assess_change({})=='PROPOSED'
    evidence={'static_valid':True,'safe_tests_passed':True,'integration_validated':True,'stability_validated':True}
    assert assess_change(evidence)=='STABILITY_VALIDATED'
    assert assess_change({**evidence,'human_approved':True})=='APPROVED'
    assert assess_change({**evidence,'rejected':True})=='REJECTED'
