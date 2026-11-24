"""No live UI, network, or persistent database access."""
import numpy as np
from cognitive_context import CognitiveContext
from hyperdimensional import FHRRHyperdimensionalEngine

def window(app,hwnd,pid,birth=1.):
    return {'app':app+'.exe','hwnd':hwnd,'pid':pid,'started':birth,'owned':False,'minimized':False}

def snapshot(*windows,status='OBSERVED'):
    return {'windows':list(windows),'channels':{'windows':{'status':status}}}

def record(memory,w,step,status='EFFECT_VERIFIED'):
    return memory.record('task',[step],{'status':status},w)

def test_multicontext_survives_opening_another_app_and_resolves_purpose():
    memory=CognitiveContext(FHRRHyperdimensionalEngine(dimension=256))
    whatsapp=window('WhatsApp',1,10)
    thorium=window('thorium',2,20)
    paint=window('mspaint',3,30)
    record(memory,paint,{'action':'move_to','target':'Ampliar'})
    record(memory,thorium,{'action':'move_to','target':'Nova guia'})
    state=snapshot(whatsapp,thorium,paint)
    context=memory.prompt_context(state)
    assert {r['app'] for r in context['recent_operations']}=={'thorium','mspaint'}
    result=memory.resolve_purpose(state,'communication')
    assert result['status']=='CANDIDATE' and result['candidates'][0]['app']=='whatsapp'
    assert result['action_authorized'] is False and result['candidates'][0]['ui_verified'] is False

def test_ambiguity_and_stale_inventory_do_not_resolve():
    memory=CognitiveContext(FHRRHyperdimensionalEngine(dimension=256))
    state=snapshot(window('WhatsApp',1,10),window('Telegram',2,20))
    assert memory.resolve_purpose(state,'communication')['status']=='AMBIGUOUS'
    assert memory.resolve_purpose(snapshot(*state['windows'],status='STALE'),'communication')['status']=='UNKNOWN'

def test_recycled_window_identity_never_revives_old_target():
    memory=CognitiveContext(FHRRHyperdimensionalEngine(dimension=256))
    w=window('mspaint',1,10)
    record(memory,w,{'action':'move_to','target':'Ampliar'})
    assert memory.prompt_context(snapshot(w))['recent_operations']
    assert not memory.prompt_context(snapshot(window('mspaint',1,10,birth=2.)))['recent_operations']

def test_tree_is_bounded_and_receipts_keep_effect_distinction():
    memory=CognitiveContext(FHRRHyperdimensionalEngine(dimension=10_000))
    w=window('mspaint',1,10)
    other=window('notepad',2,20)
    for i in range(51):
        record(memory,w if i%2 else other,{'action':'click_target','target':'Salvar','button':'left','count':1},'INPUT_SENT')
    stats=memory.stats()
    assert stats['events']==50 and stats['leaf_bytes']==4_000_000
    tree=memory.tree()
    assert tree['root'].shape==(10_000,) and np.isfinite(tree['root']).all()
    assert sum(n['count'] for n in tree['nodes'])==50
    assert all(not r['effect_verified'] for r in memory.prompt_context(snapshot(w,other))['recent_operations'])

def test_context_query_does_not_accept_action_fields():
    import pytest
    from motor_intent import validate_plan
    assert validate_plan({'status':'execute','steps':[{'action':'inspect_context','purpose':'communication'}]})
    with pytest.raises(ValueError):
        validate_plan({'status':'execute','steps':[{'action':'inspect_context','purpose':'communication','target':'Andre'}]})


def test_planner_never_receives_old_executable_operations():
    memory=CognitiveContext(FHRRHyperdimensionalEngine(dimension=256))
    paint=window('mspaint',1,10)
    notepad=window('notepad',2,20)
    record(memory,paint,{'action':'move_to','target':'Ampliar'})
    record(memory,notepad,{'action':'open_app','target':'notepad'})
    state=snapshot(paint,notepad)
    facts,ref=memory.planner_context(state,'Abra o Bloco de Notas',paint)
    assert 'recent_operations' not in facts and 'reference_candidate' not in facts and ref is None
    facts,ref=memory.planner_context(state,'Clique nesse botão no Paint',notepad)
    assert ref=={'app':'mspaint','target':'Ampliar','source':'verified_cursor_location'}
    assert 'recent_operations' not in facts
    facts,ref=memory.planner_context(state,'Clique nesse botão',notepad)
    assert ref is None
