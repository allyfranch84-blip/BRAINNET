from types import SimpleNamespace
from unittest.mock import Mock
from BRAINNET import BrainnetBridge
from parser_contract import analyze_literal_intent
from system_intent import system_launch_target


def bridge():
    b = object.__new__(BrainnetBridge)
    b._kernel = SimpleNamespace(esta_dormindo=False, ultimo_toque_ai=0, blackbox=SimpleNamespace(buffer_circular=[]))
    b._window = None
    b._chat_history = []
    b._last_executed_task = ''
    b._executar_comando_interno = Mock(return_value={'reply': 'resposta simulada', 'logs': []})
    return b


def test_history_sequence_includes_history_questions_and_roles():
    b = bridge()
    first = 'como fazer macarrão óleo e alho?'
    b.send_command(first)
    question = 'qual foi a primeira mensagem que mandei?'
    assert b.send_command(question)['reply'] == first
    assert b.send_command('qual foi a última mensagem que mandei antes dessa?')['reply'] == question
    assert [x['role'] for x in b._chat_history] == ['user', 'ai'] * 3
    assert all(x.get('id') and x.get('timestamp') for x in b._chat_history)


def test_failure_report_is_not_an_action_and_does_not_replace_task():
    b = bridge()
    b._last_executed_task = 'abra o notepad'
    result = b.send_command('Não conseguiu abrir Notepad porque escrevi note pad.')
    assert 'Nenhuma ação' in result['reply']
    assert b._last_executed_task == 'abra o notepad'
    b._executar_comando_interno.assert_not_called()


def test_search_natural_and_slash_use_same_discovery_and_no_claims():
    b = bridge()
    b.web_search_autonomous = Mock(return_value={'results': [{'title': 'Fonte', 'url': 'https://example.org', 'snippet': 'texto'}]})
    for q in ('pesquise quem foi Dom Pedro I', '/pesquise quem foi Dom Pedro I'):
        result = BrainnetBridge._executar_comando_interno(b, q, q.lower(), q.lower())
        assert result['search_state'] == 'SOURCES_FOUND'
        assert 'não foram verificados' in result['reply']
    assert b.web_search_autonomous.call_args_list[0] == b.web_search_autonomous.call_args_list[1]


def test_no_search_results_do_not_create_factual_success():
    b = bridge()
    b.web_search_autonomous = Mock(return_value={'results': []})
    result = BrainnetBridge._executar_comando_interno(b, '/pesquise algo', '/pesquise algo', '/pesquise algo')
    assert result['search_state'] == 'SEARCH_STARTED'
    assert 'Não encontrei' in result['reply']


def test_spaced_app_name_is_contextually_normalized_only_for_launch():
    assert system_launch_target('abra o note pad') == system_launch_target('abra o notepad')
    assert system_launch_target('Não conseguiu abrir note pad') is None
    assert not analyze_literal_intent('abra o note pad')['execution_authorized']


def test_search_and_help_via_send_command():
    b = bridge()
    b._executar_comando_interno = BrainnetBridge._executar_comando_interno.__get__(b)
    b._falar_seguro = Mock()
    b.web_search_autonomous = Mock(return_value={'results': [{'title': 'Fonte', 'url': 'https://example.org'}]})
    natural = b.send_command('pesquise quem foi Dom Pedro I')
    slash = b.send_command('/pesquise quem foi Dom Pedro I')
    assert natural['search_state'] == slash['search_state'] == 'SOURCES_FOUND'
    assert b.web_search_autonomous.call_args_list[0] == b.web_search_autonomous.call_args_list[1]
    assert b.send_command('mostre seus comandos')['reply'] == b.send_command('/help')['reply']
