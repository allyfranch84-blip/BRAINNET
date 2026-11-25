"""Semantic-intent envelope tests; no model, desktop, or native input."""
import pytest

from intent_grounding import ground_plan
from motor_intent import parse_semantic_response


@pytest.mark.parametrize('utterance,raw,target', [
    ('Abra o Paint', '{"intent_type":"atomic","step":{"action":"open_app","target":"paint"}}', 'paint'),
    ('Abra o Bloco de Notas', '{"intent_type":"atomic","step":{"action":"open_app","target":"notepad"}}', 'notepad'),
    ('Abra o notepad', '{"intent_type":"atomic","step":{"action":"open_app","target":"notepad"}}', 'notepad'),
    ('Inicie o Paint', '{"intent_type":"atomic","step":{"action":"open_app","target":"paint"}}', 'paint'),
])
def test_atomic_open_paraphrases_are_single_step(utterance, raw, target):
    plan = parse_semantic_response(raw)
    assert plan == {'status':'execute','steps':[{'action':'open_app','target':target}]}
    assert ground_plan(utterance, plan) == plan


def test_atomic_schema_rejects_contaminated_extra_steps_before_grounding():
    contaminated = ('{"intent_type":"atomic","step":{"action":"open_app","target":"notepad"},'
                    '"steps":[{"action":"move_to","target":"Ampliar"}]}')
    with pytest.raises(ValueError, match='invalid atomic semantic intent'):
        parse_semantic_response(contaminated)


def test_composite_preserves_requested_order_without_implicit_steps():
    raw = ('{"intent_type":"composite","steps":['
           '{"action":"open_app","target":"paint"},'
           '{"action":"move_to","target":"Ampliar"},'
           '{"action":"click_target","target":"Ampliar","button":"left","count":1}]}')
    plan = parse_semantic_response(raw)
    assert [step['action'] for step in plan['steps']] == ['open_app','move_to','click_target']
    grounded = ground_plan('Abra o Paint, mova até Ampliar e clique em Ampliar.', plan)
    assert [step['action'] for step in grounded['steps']] == ['open_app','move_to','click_target']
    assert all(step.get('app') == 'paint' for step in grounded['steps'][1:])


def test_explicit_application_sequence_preserves_both_requested_opens():
    raw = ('{"intent_type":"composite","steps":['
           '{"action":"open_app","target":"paint"},'
           '{"action":"open_app","target":"notepad"}]}')
    plan = parse_semantic_response(raw)
    assert plan['steps'] == [
        {'action':'open_app','target':'paint'},
        {'action':'open_app','target':'notepad'},
    ]
    assert ground_plan('Abra o Paint e depois abra o Bloco de Notas.', plan) == plan


@pytest.mark.parametrize('utterance,target', [
    ('Abra o Discord.', 'Discord'),
    ('Abra o Gridcraft.', 'Gridcraft'),
    ('Abra o Thorium.', 'Thorium'),
])
def test_dynamic_application_names_are_grounded_exactly_as_stated(utterance, target):
    raw = '{"intent_type":"atomic","step":{"action":"open_app","target":"%s"}}' % target
    plan = parse_semantic_response(raw)
    assert ground_plan(utterance, plan) == plan


def test_named_paint_control_is_atomic_and_has_no_implicit_click():
    raw = ('{"intent_type":"atomic","step":'
           '{"action":"move_to","target":"Ampliar","app":"paint"}}')
    plan = parse_semantic_response(raw)
    assert plan == {'status':'execute','steps':[{'action':'move_to','target':'Ampliar','app':'paint'}]}


@pytest.mark.parametrize('raw,reason', [
    ('{"intent_type":"composite","steps":[{"action":"open_app","target":"notepad"}]}', 'invalid composite'),
    ('{"status":"execute","steps":[{"action":"open_app","target":"notepad"}]}', 'missing semantic intent discriminator'),
    ('{"intent_type":"none","extra":true}', 'invalid non-executable'),
])
def test_live_semantic_path_rejects_ambiguous_or_legacy_shapes(raw, reason):
    with pytest.raises(ValueError, match=reason):
        parse_semantic_response(raw)


def test_negation_question_and_context_reference_do_not_implicitly_open_an_app():
    assert parse_semantic_response('{"intent_type":"none"}') == {'status':'none','steps':[]}
    assert parse_semantic_response('{"intent_type":"unsupported"}') == {'status':'unsupported','steps':[]}
    # A historical Paint control is not accepted as an extra step on a new open request.
    contaminated = {'status':'execute','steps':[{'action':'open_app','target':'notepad'}, {'action':'move_to','target':'Ampliar'}]}
    with pytest.raises(ValueError, match='NAMED_ACTION_NOT_GROUNDED'):
        ground_plan('Não abra o Paint; o Bloco de Notas abriu?', contaminated)
