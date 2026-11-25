import math
from types import SimpleNamespace
import pytest
from workspace_geometry import polygon_plan, compile_polyline, DIRECTION
from workspace_intent import local_motion
from workspace_notes import Notes
import workspace_note_chat as chat

@pytest.mark.parametrize('shape,count', [('quadrado',4),('triangulo',3)])
@pytest.mark.parametrize('size',[1,75,100,106,107,150,151,300])
def test_closed_polygon(shape,count,size):
    p=polygon_plan(shape,size);x=y=0;points=[]
    reverse={v:k for k,v in DIRECTION.items()}
    for s in p['steps']:
        dx,dy=reverse[s['direction']];scale=s['distance']/math.hypot(dx,dy)
        x+=math.trunc(dx*scale);y+=math.trunc(dy*scale);points.append((x,y))
        assert 1<=s['distance']<=150
    assert (x,y)==(0,0) and len(points)<=8
    assert (size,0) in points
    assert (0,size) in points
    if shape=='quadrado':assert (size,size) in points

@pytest.mark.parametrize('text',['não faça um triângulo de qualquer tamanho com o mouse sem clicar','faça um triângulo de qualquer tamanho com o mouse sem clicar e clique','faça um triângulo com o mouse','faça um triângulo de 301 pixels com o mouse sem clicar'])
def test_invalid_geometry(text):assert local_motion(text) is None

def test_triangle_phrase():
    p=local_motion('Faça um movimento em formato de triangulo de qualquer tamanho com o mouse sem pressionar.')
    assert p==polygon_plan('triangulo',100)

def test_reject_invalid_edge():
    with pytest.raises(ValueError):compile_polyline([(0,0),(2,1),(0,0)])

def test_real_note_chat(tmp_path,monkeypatch):
    db=Notes(tmp_path/'test.db');monkeypatch.setattr(chat,'Notes',lambda:db)
    calls=[];events=[]
    def ask(prompt,return_result):
        calls.append(prompt);return SimpleNamespace(text='Resposta',finish_reason='stop')
    bridge=SimpleNamespace(_push_event=lambda *a:events.append(a),_budgeted_conversation=ask)
    result=chat.handle(bridge,'crie uma nota com titulo olá que esteja escrito olá 1 dentro dela')
    assert result['status']=='NOTE_SAVED' and db.by_title('olá')['body']=='olá 1'
    assert not calls and not result['dispatched']
    assert chat.handle(bridge,'crie uma nota com titulo olá que esteja escrito diferente dentro dela')['status']=='CLARIFICATION_REQUIRED'
    assert db.by_title('olá')['body']=='olá 1'
    assert chat.handle(bridge,'o que está escrito na nota [[olá]]')['reply']=='# olá\n\nolá 1'
    assert 'não encontrada' in chat.handle(bridge,'o que está escrito na nota [[teste 1]]')['reply']
    assert not calls
    chat.handle(bridge,'/nota criar teste 1 | Conteúdo real')
    assert chat.handle(bridge,'ligue a nota [[olá]] à nota [[teste 1]]')['status']=='NOTE_SAVED'
    assert db.by_title('teste 1')['backlinks'][0]['title']=='olá'
    assert chat.handle(bridge,'Compare [[olá]] e [[teste 1]]')['status']=='CONVERSATION'
    assert 'Conteúdo real' in calls[-1] and 'olá 1' in calls[-1]
    assert chat.handle(bridge,'crie uma nota')['status']=='CLARIFICATION_REQUIRED'
    assert len(db.list())==2
