import pytest
from workspace_intent import local_motion, voice_route, note_command
from workspace_notes import Notes

@pytest.mark.parametrize('text,expected', [('mova o mouse para cima',100),('mova o mouse para cima 300 pixels',300)])
def test_move(text,expected):
    p=local_motion(text);assert sum(s['distance'] for s in p['steps'])==expected
    assert all(s['direction']=='up' for s in p['steps'])

def test_square():
    p=local_motion('faça um movimento em formato de quadrado de qualquer tamanho com o mouse sem pressionar')
    assert [x['direction'] for x in p['steps']]==['right','down','left','up']
    assert all(x['distance']==100 for x in p['steps'])

@pytest.mark.parametrize('text',['faça um quadrado com o mouse','não mova o mouse para cima','mova o mouse para cima?','mova o mouse para cima e clique','faça um quadrado de 100 pixels com o mouse sem clicar e clique'])
def test_not_authorized(text):assert local_motion(text) is None

def test_voice():
    assert voice_route('O que é gravidade?')=='CHAT'
    assert voice_route('mova o mouse para cima')=='REVIEW'
    assert voice_route('O que é gravidade? abra Paint')=='REVIEW'

def test_note_command():
    assert note_command('/nota criar Teste | texto')==('criar','Teste | texto')
    assert note_command('crie uma nota') is None

def test_note_links(tmp_path):
    db=Notes(tmp_path/'notes.db');a=db.save(None,'A','texto',0);b=db.save(None,'B','outro',0)
    db.link('A','B');assert db.get(a['id'])['links'][0]['id']==b['id'];assert db.get(b['id'])['backlinks'][0]['id']==a['id']
    assert db.by_title('a')['title']=='A'
    with pytest.raises(ValueError):db.link('A','inexistente')

def test_note_chat_roundtrip(tmp_path, monkeypatch):
    import workspace_note_chat as c
    from types import SimpleNamespace
    db=Notes(tmp_path/'notes.db');monkeypatch.setattr(c,'Notes',lambda:db)
    bridge=SimpleNamespace(_push_event=lambda *args:None,_budgeted_conversation=lambda prompt,return_result:SimpleNamespace(finish_reason='stop',text='Resumo de teste'))
    assert c.handle(bridge,'/nota criar Motor | movimento')['status']=='NOTE_SAVED'
    assert c.handle(bridge,'/nota gerar Cognição | assunto')['status']=='NOTE_SAVED'
    assert c.handle(bridge,'/nota ligar Motor | Cognição')['status']=='NOTE_SAVED'
    assert c.handle(bridge,'resuma a nota Motor')['status']=='CONVERSATION'
    assert c.handle(bridge,'use a nota Motor')['status']=='CONVERSATION'
    assert c.note_context(bridge)[0]['title']=='Motor'
    c.handle(bridge,'/nota limpar contexto');assert c.note_context(bridge)==[]
