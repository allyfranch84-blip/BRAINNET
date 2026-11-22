"""Regressoes do teste de estresse; nenhum teste acessa LLM ou navegador reais."""
import ast
import inspect
import json
import textwrap
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from assistant_prompts import BRAINNET_SYSTEM_PROMPT, MODELO_DEEP, MODELO_PARSER
from BRAINNET import BrainnetBridge
from browser_bridge import BrowserDeepBridge
from causal_trajectory import CausalTrajectoryEngine
from cybernetic_verifier import CyberneticVerifier
from theory_of_mind import MotorGateState, TheoryOfMindEngine


def http_response(data):
    result = MagicMock()
    result.__enter__.return_value.read.return_value = json.dumps(data).encode("utf-8")
    return result


@pytest.mark.parametrize("prompt, gate", [
    ("quem foi Dom Pedro II?", MotorGateState.GO),
    ("quem foi Dom Pedro II?", MotorGateState.NO_GO),
    ("o que é urânio?", MotorGateState.GO),
    ("o que é urânio?", MotorGateState.NO_GO),
    ("escreva um poema sobre a lua", MotorGateState.GO),
])
@pytest.mark.parametrize("deep_allowed,expected_model", [(True, MODELO_DEEP), (False, MODELO_PARSER)])
def test_general_knowledge_uses_7b_and_requested_personality(prompt, gate, deep_allowed, expected_model):
    bridge = object.__new__(BrainnetBridge)
    bridge._kernel = MagicMock()
    bridge._kernel.router._qwen_fast = "brainnet-parser-v2"
    bridge._homeostasis = MagicMock()
    bridge._homeostasis.should_use_deep_brain.return_value = deep_allowed
    bridge._tom = MagicMock()
    bridge._tom.evaluate_intent.return_value = SimpleNamespace(gate=gate, is_physical_world=False)
    bridge._modo_coder_ativo = False
    bridge._falar_seguro = MagicMock()
    with patch("BRAINNET.urllib.request.urlopen", return_value=http_response({"response": "resposta de teste"})) as request:
        result = bridge._executar_comando_interno(prompt, prompt.lower(), prompt.lower())
    payload = json.loads(request.call_args.args[0].data)
    assert payload["model"] == expected_model and payload["keep_alive"] == "5m"
    bridge._homeostasis.should_use_deep_brain.assert_called_once()
    assert BRAINNET_SYSTEM_PROMPT in payload["prompt"]
    assert result["reply"] == "resposta de teste"
    bridge._kernel.trajectory_engine.executar_trajetoria_completa.assert_not_called()


def test_parser_keeps_schema_and_personality_without_general_answer():
    bridge = object.__new__(BrainnetBridge)
    with patch("BRAINNET.urllib.request.urlopen", return_value=http_response({"response": '{"action":"OPEN","target":"editor","domain":"DIGITAL_UI"}'})) as request:
        result = bridge._extract_roles_via_schema("abra editor")
    payload = json.loads(request.call_args.args[0].data)
    assert payload["model"] == MODELO_PARSER
    assert payload["format"]["additionalProperties"] is False
    assert BRAINNET_SYSTEM_PROMPT in payload["prompt"]
    assert set(result) == {"action", "target", "domain"}


@pytest.mark.parametrize("command, expected", [
    ("abra o bloco de notas e escreva 'rosas e violetas'", "rosas e violetas"),
    ('abra notepad e digite "um poema sobre a noite"', "um poema sobre a noite"),
    ("abra o bloco de notas e escreva Olá, mundo!", "Olá, mundo!"),
])
def test_compound_literal_keeps_both_steps_and_whole_text(command, expected):
    engine = object.__new__(CausalTrajectoryEngine)
    with patch("causal_trajectory.urllib.request.urlopen", side_effect=AssertionError("Literal nao chama LLM")):
        result = engine.decompor_trajetoria_cognitiva(command)
    assert result["passos"] == [{"passo": 1, "acao": "ENSURE_APP", "app": "notepad"},
                                 {"passo": 2, "acao": "TYPE", "text": expected}]


def test_compound_poem_types_generated_text_not_instruction():
    engine = object.__new__(CausalTrajectoryEngine)
    poem = "Primeiro verso\nSegundo verso\nTerceiro verso"
    with patch("causal_trajectory.urllib.request.urlopen", return_value=http_response({"response": poem, "done": True, "done_reason": "stop"})) as request:
        result = engine.decompor_trajetoria_cognitiva("abra o bloco de notas e escreva um poema sobre a noite")
    assert result["passos"][1]["text"] == poem
    payload = json.loads(request.call_args.args[0].data)
    assert payload["model"] == "iaos-qwen:latest"
    assert BRAINNET_SYSTEM_PROMPT in payload["prompt"]


def test_incomplete_creative_generation_is_not_turned_into_typing():
    engine = object.__new__(CausalTrajectoryEngine)
    with patch("causal_trajectory.urllib.request.urlopen", return_value=http_response({"response": "verso cortado", "done": True, "done_reason": "length"})):
        with pytest.raises(RuntimeError, match="completo"):
            engine.decompor_trajetoria_cognitiva("abra notepad e escreva um poema")


@pytest.mark.parametrize("word", ["armário", "armario", "papel", "geladeira", "boca"])
def test_physical_words_rejected_before_probabilistic_classification(word):
    engine = object.__new__(TheoryOfMindEngine)
    result = engine.evaluate_intent(f"abra {word}", {})
    assert result.gate == MotorGateState.PRAGMATIC_REJECT and result.is_physical_world


def test_verifier_retries_after_render_instead_of_failing_first_measurement():
    verifier = CyberneticVerifier(capture_fn=lambda: b"after")
    assert verifier.poll_interval == 0.5
    process = MagicMock()
    process.status.return_value = "running"
    with patch.object(CyberneticVerifier, "snapshot_pids", return_value={10, 20}), \
         patch.object(CyberneticVerifier, "_find_top_level_hwnd", return_value=77), \
         patch.object(CyberneticVerifier, "_check_hwnd_liveness", return_value=(True, "")), \
         patch.object(CyberneticVerifier, "calculate_ncd_lz4", side_effect=[0.0, 0.3]), \
         patch("cybernetic_verifier.psutil.Process", return_value=process), \
         patch("cybernetic_verifier.time.sleep") as wait:
        result = verifier.measure_collapse({10}, b"before", b"", timeout_sec=2.0)
    assert result[0] == 1 and result[4] == 0.3
    wait.assert_called_once_with(0.5)


@pytest.mark.parametrize("connected, acknowledgement, confirmed", [
    (False, {}, False), (True, {"ok": False}, False),
    (True, {"ok": True}, False), (True, {"ok": True, "closed_count": 1}, False),
    (True, {"ok": True, "closed_count": 2}, True),
])
def test_tab_cleanup_never_uses_blind_keyboard_fallback(connected, acknowledgement, confirmed):
    source = textwrap.dedent(inspect.getsource(BrowserDeepBridge.deep_multi_tab_research))
    function = next(node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.FunctionDef) and node.name == "_fechar_abas_async")
    assert "keybd_event" not in ast.unparse(function)
    browser = SimpleNamespace(extension_connected=connected,
                              send_command=MagicMock(return_value=acknowledgement), resolver=MagicMock())
    log = MagicMock()
    namespace = {"self": browser, "abas_para_fechar": [17, 23, 17],
                 "time": SimpleNamespace(sleep=MagicMock()), "logger": log}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "<trusted tab cleanup>", "exec"), namespace)
    namespace["_fechar_abas_async"]()
    browser.resolver.find_and_focus_window.assert_not_called()
    if connected:
        browser.send_command.assert_called_once_with("CLOSE_TABS", tab_ids=[17, 23], timeout=2.0)
    else:
        browser.send_command.assert_not_called()
    if confirmed:
        log.info.assert_called_once()
        log.warning.assert_not_called()
    else:
        log.warning.assert_called()
