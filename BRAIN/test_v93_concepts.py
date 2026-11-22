"""Deterministic advisory interpretation; no real actions or services."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from natural_comprehension import conceptual_hypotheses
from execution_authority import require_action_allowed

@pytest.mark.parametrize('text',[
 'Crie uma aula divertida para ensinar astronomia',
 'Para aprender astronomia, faça algo divertido',
 'Ensine astronomia de forma divertida',
])
def test_paraphrases_propose_same_educational_goal(text):
    result=conceptual_hypotheses(text)
    assert any(h['goal']=='ensinar_astronomia' for h in result['hypotheses'])
    assert result['execution_authorized'] is False and result['verified_facts']==[]

def test_preference_and_missing_topic():
    result=conceptual_hypotheses('Faça um livro para iniciantes, mas não muito infantil')
    assert result['hypotheses'][0]['goal']=='criar_livro'
    assert 'assunto do livro' in result['missing_information']
    assert result['constraints'] and result['preferences']

def test_quote_and_url_not_treated_as_instructions():
    text='Analise este recurso https://example.org/ensinar/astronomia e `ensine astronomia`'
    result=conceptual_hypotheses(text)
    assert result['original']==text and not result['hypotheses']

def test_kernel_observation_opt_in_never_grants_authority(monkeypatch):
    from BRAINNET import BrainnetBridge
    def bridge():
        obj=object.__new__(BrainnetBridge);obj._kernel=SimpleNamespace(esta_dormindo=False,ultimo_toque_ai=0)
        obj._window=None;obj._chat_history=[]
        def dispatch(*args):
            require_action_allowed('EXECUTE')
            return {'reply':'simulated','logs':[]}
        obj._executar_comando_interno=Mock(side_effect=dispatch)
        return obj
    monkeypatch.delenv('BRAINNET_CONCEPTUAL_OBSERVE',raising=False)
    assert 'conceptual_analysis' not in bridge().send_command('Ensine astronomia')
    monkeypatch.setenv('BRAINNET_CONCEPTUAL_OBSERVE','1')
    obj=bridge();result=obj.send_command('Ensine astronomia de forma divertida')
    assert result['conceptual_analysis']['execution_authorized'] is False
    assert result['conceptual_analysis']['hypotheses'][0]['status']=='HYPOTHESIS'
    obj._executar_comando_interno.assert_called_once()
