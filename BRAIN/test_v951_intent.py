"""Intent, gate and planning simulation; no actual desktop or model."""
import threading
from unittest.mock import Mock, patch
import pytest
from parser_contract import analyze_literal_intent
from system_intent import system_launch_target
from theory_of_mind import TheoryOfMindEngine, MotorGateState
from execution_authority import authorization_scope, require_action_allowed
from htn_planner import parse_objectives, compile_primitives
from router import AdaptiveInferenceRouter

@pytest.mark.parametrize('text,target',[
    ('abra o paint','Paint'),('abre o paint','Paint'),('inicie o Paint','Paint'),
    ('abra o bloco de notas','Notepad'),
])
def test_open_contract_and_tom(text,target):
    result=analyze_literal_intent(text)
    assert result['intent_kind']=='OPEN_APP' and result['canonical_target']==target
    assert result['domain']=='DIGITAL_UI' and result['execution_authorized'] is False
    assert TheoryOfMindEngine().evaluate_intent(text,{}).gate != MotorGateState.CLARIFICATION

def test_negation_question_compound_and_door():
    for text,kind in [('não abra o paint','NEGATED'),('como abrir o paint?','QUESTION'),
                      ('abra o paint e desenhe um círculo','COMPOUND')]:
        result=analyze_literal_intent(text)
        assert result['intent_kind']==kind and result['intent_kind']!='OPEN_APP'
        assert result['execution_authorized'] is False
    door=analyze_literal_intent('abra a porta')
    assert door['domain']=='PHYSICAL_WORLD' and system_launch_target('abra a porta') is None
    assert TheoryOfMindEngine().evaluate_intent('abra a porta',{}).gate == MotorGateState.PRAGMATIC_REJECT

def test_uniform_distribution_still_uses_structured_evidence():
    tom=TheoryOfMindEngine()
    with patch.object(TheoryOfMindEngine,'_calcular_distribuicao_intencao',return_value={x:.2 for x in ('AFETO','FISICO','SOCIAL','TEORICO','OPERACIONAL')}):
        assert tom.evaluate_intent('abra o paint',{}).gate != MotorGateState.CLARIFICATION

def test_simulated_end_to_end_intent_plan_authorization_verification():
    text='abra o paint'
    intent=analyze_literal_intent(text)
    tom=TheoryOfMindEngine(); judgement=tom.evaluate_intent(text,{})
    route=AdaptiveInferenceRouter(vsa_engine=tom.vsa).evaluate_route(text,{})
    goals=parse_objectives(text); proposal=compile_primitives(goals)
    assert intent['intent_kind']=='OPEN_APP' and judgement.gate == MotorGateState.GO
    assert route.mode in ('DEEP_PATH','INSPECT_SCREEN','COMPOUND_PIPELINE','DETERMINISTIC_ACTION')
    assert goals[0]['roles']['APP_ALVO']=='paint' and proposal['pipeline']
    executor=Mock(return_value={'executed':True});verifier=Mock(return_value=True)
    with pytest.raises(PermissionError):require_action_allowed('OPEN_APP')
    with authorization_scope(threading.Event()):
        require_action_allowed('OPEN_APP');observed=executor(proposal)
    assert observed['executed'] and verifier(observed) is True
    executor.assert_called_once();verifier.assert_called_once()
