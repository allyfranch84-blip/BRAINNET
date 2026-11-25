"""Regression tests for intent contamination and wrong-application routing."""
import pytest
from intent_grounding import direct_app_request, ground_plan

def plan(*steps):
    return {'status':'execute','steps':list(steps)}

def test_open_notepad_does_not_replay_previous_paint_operations():
    with pytest.raises(ValueError,match='NAMED_ACTION_NOT_GROUNDED'):
        ground_plan('Abra o Bloco de Notas',plan(
            {'action':'open_app','target':'notepad'},
            {'action':'move_to','target':'Ampliar'},
            {'action':'click_target','target':'Ampliar','button':'left','count':1}))
    assert ground_plan('Abra o Bloco de Notas',plan({'action':'open_app','target':'notepad'}))['steps']==[{'action':'open_app','target':'notepad'}]

def test_dynamic_app_name_must_be_explicitly_present_in_current_utterance():
    assert ground_plan('Abra o Visual Studio Code',plan({'action':'open_app','target':'Visual Studio Code'}))['steps']==[{'action':'open_app','target':'Visual Studio Code'}]
    with pytest.raises(ValueError,match='OPEN_APP_NOT_GROUNDED'):
        ground_plan('Abra o Bloco de Notas',plan({'action':'open_app','target':'Visual Studio Code'}))

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


def open_app(app):
    return {'action': 'open_app', 'target': app}


@pytest.mark.parametrize(('text', 'proposal', 'result'), [
    ('Abra o Blco de Notas.', 'notepad', 'notepad'),
    ('Abra o Blco de Notas.', 'Blco de Notas', 'notepad'),
    ('Por favor, abra o Paitn agora.', 'paint', 'paint'),
    ('Abra o aplicativo “Paitn”.', 'paint', 'paint'),
    ('Quero que você abra a calculadroa.', 'calculator', 'calculator'),
    ('Abra o Notepad++.', 'Notepad++', 'Notepad++'),
])
def test_recovers_a_single_typo_in_known_app_name(text, proposal, result):
    assert ground_plan(text, plan(open_app(proposal)))['steps'] == [open_app(result)]


@pytest.mark.parametrize(('text', 'target'), [
    ('Abra o Notepad++.', 'notepad'),
    ('Abra o Paint.NET.', 'paint'),
    ('Abra o Point.', 'paint'),
    ('Abra o Visual Studo Code.', 'Visual Studio Code'),
    ('Não abra o Blco de Notas.', 'notepad'),
    ('Não quero que abra o Blco de Notas.', 'notepad'),
    ('Como eu faço para abrir o Paint?', 'paint'),
    ('Abra o Paint e o Bloco de Notas?', 'paint'),
    ('Use como exemplo "abra o Paint".', 'paint'),
    ('Abra um arquivo no Paint.', 'paint'),
])
def test_weak_or_contradictory_app_evidence_remains_blocked(text, target):
    with pytest.raises(ValueError, match='OPEN_APP_NOT_GROUNDED'):
        ground_plan(text, plan(open_app(target)))


@pytest.mark.parametrize('text', [
    'Abra o Paitn ou o Blco de Notas.',
    'Abra o Paitn, ou abra o Blco de Notas.',
])
def test_user_alternatives_require_clarification(text):
    with pytest.raises(ValueError, match='APPLICATION_AMBIGUOUS'):
        ground_plan(text, plan(open_app('paint')))


def test_letter_edit_candidates_can_be_ambiguous(monkeypatch):
    monkeypatch.setattr('intent_grounding.APP_ALIASES', {'pino': ('pino',), 'pint': ('pint',)})
    with pytest.raises(ValueError, match='APPLICATION_AMBIGUOUS'):
        ground_plan('Abra o Pinto.', plan(open_app('pino')))


@pytest.mark.parametrize('targets', [
    ('notepad', 'paint'), ('paint',), ('notepad',), ('paint', 'notepad', 'notepad'),
])
def test_app_open_sequence_rejects_omitted_reordered_and_duplicate_steps(targets):
    with pytest.raises(ValueError, match='OPEN_APP_NOT_GROUNDED'):
        ground_plan('Abra o Paitn e depois abra o Blco de Notas.', plan(*(open_app(app) for app in targets)))


def test_succeeds_when_the_order_and_scope_match():
    expected = plan(open_app('paint'), open_app('notepad'))
    assert ground_plan('Abra o Paitn e o Blco de Notas.', expected) == expected
    expected = plan(open_app('notepad'))
    assert ground_plan('Não abra o Paint. Abra o Blco de Notas.', expected) == expected


def test_comma_separated_application_list_cannot_be_reduced_to_an_atomic_open():
    text = 'Abra o Paitn, o Blco de Notas e o Discord.'
    expected = plan(open_app('paint'), open_app('notepad'), open_app('Discord'))
    assert ground_plan(text, expected) == expected
    with pytest.raises(ValueError, match='OPEN_APP_NOT_GROUNDED'):
        ground_plan(text, plan(open_app('paint')))


def test_opening_with_typo_does_not_authorize_a_negated_click():
    with pytest.raises(ValueError, match='CLICK_NOT_GROUNDED'):
        ground_plan('Abra o Paitn e não clique.', plan(
            open_app('paint'), {'action': 'click', 'button': 'left', 'count': 1}))


@pytest.mark.parametrize(('text', 'target'), [
    ('Abra o Blco de Notas.', 'notepad'),
    ('Por favor, abra o mspaint.exe!', 'paint'),
    ('Abra a Calculadora, por favor.', 'calculator'),
])
def test_direct_request_fallback_contains_one_complete_known_open(text, target):
    result = direct_app_request(text)
    assert result == plan(open_app(target))
    assert ground_plan(text, result) == result


@pytest.mark.parametrize('text', [
    'Abra o Blco de Notas e escreva olá.',
    'Abra o Blco de Notas. Salve na área de trabalho.',
    'Abra o Paint e não clique.',
    'Abra o Paint, o Blco de Notas.',
    'Abra o Paint e',
    'Abra o Notepad++.',
    'Abra o Discord.',
    'Não abra o Paint!',
    'Abra o Paint?',
    'Faço como para abrir o Paint?',
])
def test_direct_request_fallback_cannot_drop_context_or_open_dynamic_names(text):
    assert direct_app_request(text) is None


def test_direct_request_fallback_reports_ambiguous_alternatives():
    with pytest.raises(ValueError, match='APPLICATION_AMBIGUOUS'):
        direct_app_request('Abra o Paitn ou o Blco de Notas.')
