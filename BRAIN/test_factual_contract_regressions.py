"""Action-specific facts and raw recipe fallback; no real UI or LLM calls."""
import asyncio
import itertools
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from BRAINNET import BrainnetBridge
from browser_bridge import BrowserDeepBridge
from causal_trajectory import CausalTrajectoryEngine
from cybernetic_verifier import CyberneticVerifier
from error_blackbox import ErrorBlackBoxEngine
from theory_of_mind import MotorGateState


@pytest.mark.parametrize("action,ncd,focused,alive,reuse,expected", [
    ("TYPE", 0.0, True, True, False, 0),
    ("HOTKEY", 0.0, True, True, False, 1),
    ("WAIT", 0.0, True, True, False, 1),
    ("TYPE", 0.03, False, True, False, 0),
    ("TYPE", 0.02, False, True, False, 0),
    ("TYPE", 0.0201, False, True, False, 0),
    ("TYPE", 0.0, False, True, False, 0),
    ("TYPE", 0.5, True, False, False, 0),
    ("CLICK", 0.05, True, True, False, 0),
    ("CLICK", 0.0501, True, True, False, 1),
    ("RIGHT_CLICK", 0.0, True, True, False, 0),
    ("RIGHT_CLICK", 0.0199, True, True, False, 0),
    ("RIGHT_CLICK", 0.02, True, True, False, 1),
    ("RIGHT_CLICK", 0.0201, True, True, False, 1),
    ("RIGHT_CLICK", 0.1, False, True, False, 0),
    ("SCROLL", 0.0, True, True, False, 0),
    ("SCROLL", 0.0199, True, True, False, 0),
    ("SCROLL", 0.02, True, True, False, 1),
    ("SCROLL", 0.0201, True, True, False, 1),
    ("SCROLL", 0.1, False, True, False, 0),
    ("ENSURE_APP", 0.0, True, True, True, 1),
    ("ENSURE_APP", 0.0, False, True, True, 0),
    ("START_MENU_SEARCH", 0.0, True, True, True, 1),
    ("START_MENU_SEARCH", 0.0, False, True, True, 0),
    ("ENSURE_APP", 0.4, True, True, False, 0),
])
def test_action_specific_verification(action, ncd, focused, alive, reuse, expected):
    verifier = CyberneticVerifier(capture_fn=lambda: b"post")
    contract = {"action": action, "target_hwnd": 77}
    if reuse:
        contract.update(expects_new_pid=False, reuse_existing=True)
    def window_pid(hwnd, pointer):
        pointer._obj.value = 10
    user32 = SimpleNamespace(GetForegroundWindow=lambda: 77 if focused else 99,
                             GetWindowThreadProcessId=window_pid)
    with patch("cybernetic_verifier.user32", user32), \
         patch.object(CyberneticVerifier, "snapshot_pids", return_value={10}), \
         patch.object(CyberneticVerifier, "_check_hwnd_liveness", return_value=(alive, "")), \
         patch.object(CyberneticVerifier, "calculate_ncd_lz4", return_value=ncd), \
         patch("cybernetic_verifier.time.perf_counter", side_effect=itertools.chain([0, 0], itertools.repeat(1))), \
         patch("cybernetic_verifier.time.sleep"):
        result = verifier.measure_collapse({10}, b"before", b"", timeout_sec=0.1, contract=contract)
    assert result[0] == expected
    assert result[4] == ncd


@pytest.mark.parametrize("process,pid,reuse", [("notepad.exe", 10, True), ("chrome.exe", 10, False), ("notepad.exe", 20, False)])
def test_ensure_app_reuses_only_matching_preexisting_process(process, pid, reuse):
    engine = object.__new__(CausalTrajectoryEngine)
    engine.verifier = MagicMock(ncd_threshold=0.2)
    engine.verifier.snapshot_pids.return_value = {10}
    engine.verifier.capture_state_bytes.return_value = b"before"
    engine.verifier.measure_collapse.return_value = (1, 1.0, "", pid, 0.0, 0.0)
    engine.ctx_engine = MagicMock()
    engine.ctx_engine.capture_foreground_context.return_value = {"hwnd": 77, "pid": pid, "process_name": process}
    asyncio.run(engine.execute_subgoal("open", AsyncMock(), contract=engine._contract_for_action("ENSURE_APP", "notepad")))
    contract = engine.verifier.measure_collapse.call_args.kwargs["contract"]
    assert contract.get("reuse_existing", False) is reuse
    assert contract["expects_new_pid"] is not reuse


@pytest.mark.parametrize("generated", ["Ingredientes e modo de preparo coletados da página.", "Resumo curto", ""])
def test_recipe_fallback_keeps_entire_real_excerpt(generated):
    raw = "INGREDIENTES: farinha, ovos.\nPREPARO: misture e asse.\n" * 8
    assert CausalTrajectoryEngine._recipe_text_or_excerpt(generated, raw) == raw


def test_existing_app_preserves_explicit_expected_ncd():
    engine = object.__new__(CausalTrajectoryEngine)
    engine.verifier = MagicMock(ncd_threshold=0.2)
    engine.verifier.snapshot_pids.return_value = {10}
    engine.verifier.measure_collapse.return_value = (1, 1.0, "", 10, 0.0, 0.2)
    engine.ctx_engine = MagicMock()
    engine.ctx_engine.capture_foreground_context.return_value = {"hwnd": 77, "pid": 10, "process_name": "notepad.exe"}
    result = asyncio.run(engine.execute_subgoal("open", AsyncMock(), expected_ncd=0.2,
                        contract=engine._contract_for_action("ENSURE_APP", "notepad")))
    assert engine.verifier.measure_collapse.call_args.kwargs["expected_delta"] == 0.2
    assert result["reward"] == pytest.approx(-0.04)


def test_recipe_without_evidence_is_not_replaced_by_generic_text():
    with pytest.raises(ValueError, match="sem texto"):
        CausalTrajectoryEngine._recipe_text_or_excerpt("coletados da página", "")


def test_recipe_pipeline_saves_raw_page_when_llm_returns_generic_text(tmp_path, monkeypatch):
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    bridge = object.__new__(BrainnetBridge)
    bridge._kernel, bridge._tom = MagicMock(), MagicMock()
    bridge._modo_coder_ativo = False
    bridge._falar_seguro = MagicMock()
    bridge._tom.evaluate_intent.return_value = SimpleNamespace(gate=MotorGateState.GO)
    bridge._kernel.trajectory_engine._recipe_text_or_excerpt = CausalTrajectoryEngine._recipe_text_or_excerpt
    raw = "Receita REAL\nIngredientes: farinha, ovos e leite.\nModo de preparo: misture e asse.\n" * 5
    bridge._kernel.browser_bridge.deep_search_and_optionally_open_link.return_value = {
        "ok": True, "active_page": {"title": "Receita real", "text_excerpt": raw}}
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps({"response": "Ingredientes coletados da página"}).encode()
    command = "abra o brave e pesquise bolo e no bloco de notas escreva e salve na area de trabalho"
    with patch("BRAINNET.urllib.request.urlopen", return_value=response), \
         patch("BRAINNET.subprocess.Popen"), patch("BRAINNET.time.sleep"):
        bridge._executar_comando_interno(command, command, command)
    saved = next(desktop.glob("*.txt")).read_text(encoding="utf-8")
    assert raw in saved
    assert "coletados da página" not in saved


def test_deep_search_preserves_excerpt_without_llm():
    browser = object.__new__(BrowserDeepBridge)
    # Use the method with a stub to avoid starting its HTTP server.
    stub = SimpleNamespace(extension_connected=True, ensure_preferred_browser=lambda: "brave",
                           send_command=MagicMock(return_value={"ok": True, "text_excerpt": "real page", "links": []}))
    result = BrowserDeepBridge.deep_search_and_optionally_open_link(stub, "recipe")
    assert result["text_excerpt"] == result["active_page"]["text_excerpt"] == "real page"


@patch.dict("os.environ", {"BRAINNET_AUTOCURA_VALIDATING": "0"})
def test_no_safe_patch_with_live_target_does_not_penalize_or_auto_apply():
    context = MagicMock()
    context.escanear_estado_janelas.return_value = [{"hwnd": 77, "titulo": "Sem titulo - Bloco de Notas"}]
    pdag = MagicMock()
    blackbox = ErrorBlackBoxEngine(context, MagicMock(), pdag, sandbox=MagicMock())
    snapshot = blackbox.registrar_falha_e_punir("abra notepad", {"tipo": "TRAJECTORY_FAILED"}, {}, {}, "evidencia ausente")
    assert snapshot["penalty_deferred"] is True
    diagnosis = {"decision": "NO_SAFE_PATCH", "failure_class": "UNKNOWN", "diagnosis": "Missing evidence",
                 "evidence_ids": [], "required_evidence": ["NCD"], "patches": [], "validation_cases": []}
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps({"response": json.dumps(diagnosis)}).encode()
    with patch("error_blackbox.urllib.request.urlopen", return_value=response):
        result = blackbox.disparar_auto_cura(snapshot)
    assert result["status"] == "NO_SAFE_PATCH"
    pdag.apply_user_report_penalty.assert_not_called()


def test_explicit_user_report_still_uses_feedback_channel():
    context = MagicMock()
    context.escanear_estado_janelas.return_value = [{"hwnd": 77, "titulo": "Bloco de Notas"}]
    pdag = MagicMock()
    blackbox = ErrorBlackBoxEngine(context, MagicMock(), pdag, sandbox=MagicMock())
    blackbox.registrar_falha_e_punir("abra notepad", {"tipo": "USER_REPORT"}, {}, {}, "nao funcionou")
    pdag.apply_user_report_penalty.assert_called_once()


def test_toryum_normalizes_before_projection():
    engine = object.__new__(CausalTrajectoryEngine)
    with patch.object(CausalTrajectoryEngine, "_projetar_onda_de_probabilidade", side_effect=RuntimeError("stop")) as projection:
        with pytest.raises(RuntimeError, match="stop"):
            engine.decompor_trajetoria_cognitiva("abra toryum")
    projection.assert_called_once_with("abra thorium")
