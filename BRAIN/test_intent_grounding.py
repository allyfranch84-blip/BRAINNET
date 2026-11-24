"""Regression tests for intent contamination and wrong-application routing."""
import pytest
from intent_grounding import ground_plan

def plan(*steps):
    return {'status':'execute','steps':list(steps)}

def test_open_notepad_does_not_replay_previous_paint_operations():
    with pytest.raises(ValueError,match='NAMED_ACTION_NOT_GROUNDED'):
        ground_plan('Abra o Bloco de Notas',plan(
            {'action':'open_app','target':'notepad'},
            {'action':'move_to','target':'Ampliar'},
            {'action':'click_target','target':'Ampliar','button':'left','count':1}))
    assert ground_plan('Abra o Bloco de Notas',plan({'action':'open_app','target':'notepad'}))['steps']==[{'action':'open_app','target':'notepad'}]

def test_move_in_paint_is_bound_to_paint_even_when_model_omits_app():
    result=ground_plan('Mova o mouse até Ampliar no Paint',plan({'action':'move_to','target':'Ampliar'}))
    assert result['steps']==[{'action':'move_to','target':'Ampliar','app':'paint'}]

def test_wrong_app_or_unrequested_open_is_rejected():
    with pytest.raises(ValueError,match='APPLICATION_NOT_GROUNDED'):
        ground_plan('Mova o mouse até Ampliar no Paint',plan({'action':'move_to','target':'Ampliar','app':'notepad'}))
    with pytest.raises(ValueError,match='OPEN_APP_NOT_GROUNDED'):
        ground_plan('Mova o mouse até Ampliar no Paint',plan({'action':'open_app','target':'notepad'}))
    with pytest.raises(ValueError,match='OPEN_APP_NOT_GROUNDED'):
        ground_plan('Mova o mouse até Ampliar no Paint',plan({'action':'open_app','target':'paint'}))

def test_explicit_sequence_remains_valid_and_deictic_click_is_bound():
    result=ground_plan('Abra o Paint, mova o mouse até Ampliar e clique nesse botão.',plan(
        {'action':'open_app','target':'paint'},
        {'action':'move_to','target':'Ampliar'},
        {'action':'click','button':'left','count':1}))
    assert [s['action'] for s in result['steps']]==['open_app','move_to','click_target']
    assert result['steps'][2]['target']=='Ampliar' and result['steps'][2]['app']=='paint'

def test_historical_reference_requires_current_user_reference():
    reference={'app':'mspaint','target':'Ampliar'}
    result=ground_plan('Clique nesse botão',plan({'action':'click','button':'left','count':1}),reference=reference)
    assert result['steps'][0]['app']=='paint' and result['steps'][0]['target']=='Ampliar'
    with pytest.raises(ValueError,match='TARGET_NOT_GROUNDED'):
        ground_plan('Mova o mouse para cima',plan({'action':'move_to','target':'Ampliar'}),reference=reference)

def test_ai_chat_query_is_not_ordinary_messaging():
    result=ground_plan('Qual aplicativo aberto serve para conversar com uma inteligência artificial?',plan({'action':'inspect_context','purpose':'communication'}))
    assert result['steps']==[{'action':'inspect_context','purpose':'ai_chat'}]
