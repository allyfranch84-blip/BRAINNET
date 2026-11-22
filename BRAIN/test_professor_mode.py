"""Explicit teaching sessions only; all physical inputs and speech are mocked."""
import asyncio
import json
import sqlite3
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from BRAINNET import BrainnetBridge
from causal_trajectory import CausalTrajectoryEngine
from pdag_engine import MyelinatedPDAGEngine
from professor_mode import parse_professor_step
from hyperdimensional import FHRRHyperdimensionalEngine


@pytest.mark.parametrize("text,step", [
    ("tecla Win", {"acao": "HOTKEY", "keys": ["win"]}),
    ("aperte Enter", {"acao": "HOTKEY", "keys": ["enter"]}),
    ("tecla ctrl+s", {"acao": "HOTKEY", "keys": ["ctrl", "s"]}),
    ("digite Gridcraft", {"acao": "TYPE", "text": "Gridcraft"}),
    ('digite "Texto literal e completo"', {"acao": "TYPE", "text": "Texto literal e completo"}),
    ("clique em 120 340", {"acao": "CLICK", "x": 120, "y": 340}),
    ("clique em -10, 250", {"acao": "CLICK", "x": -10, "y": 250}),
])
def test_literal_grammar_preserves_user_step(text, step):
    assert parse_professor_step(text) == step


@pytest.mark.parametrize("text", ["abra whatsapp", "pesquise X", "tecla Win Enter", "tecla F32", "digite   ", "clique em x y", "clique em 2147483648 0"])
def test_unrecognized_or_unsafe_step_never_becomes_an_action(text):
    with pytest.raises(ValueError):
        parse_professor_step(text)


@pytest.fixture
def bridge():
    obj = object.__new__(BrainnetBridge)
    obj._kernel, obj._tom = MagicMock(), MagicMock()
    obj._kernel.vsa = FHRRHyperdimensionalEngine(dim=64)
    obj._kernel.pdag.id_to_index = {}
    obj._kernel.pdag._lock = threading.Lock()
    obj._kernel.pdag.record_human_demonstration.return_value = True
    obj._kernel.loop = None
    obj._professor_mode = None
    obj._professor_lock = threading.RLock()
    obj._kernel.trajectory_engine.execute_professor_step = AsyncMock(return_value={
        "lambda_obs": 1, "ncd_real": 0.1, "observed_hwnd": 77, "expected_delta": 0.02, "discovered_pid": 10})
    obj._kernel.trajectory_engine.save_professor_session = AsyncMock(return_value=True)
    return obj


def send(bridge, text):
    return bridge._executar_comando_interno(text, text.lower(), text.lower())


def test_full_teacher_session_records_then_saves_without_llm_or_tom(bridge):
    with patch("BRAINNET.urllib.request.urlopen", side_effect=AssertionError("No LLM")):
        assert "PROPÓSITO" in send(bridge, "/professor abrir_gridcraft")["reply"]
        send(bridge, "abrir_qualquer_app")
        for text in ("tecla Win", "digite gridcraft", "aperte Enter"):
            assert "Próximo passo?" in send(bridge, text)["reply"]
        steps = bridge._professor_mode["passos"]
        assert [step["acao"] for step in steps] == ["HOTKEY", "TYPE", "HOTKEY"]
        assert [step["passo"] for step in steps] == [1, 2, 3]
        assert all(step["feedback"]["lambda_obs"] == 1 for step in steps)
        assert "Verificação factual pendente" in send(bridge, "/fim")["reply"]
    bridge._tom.evaluate_intent.assert_not_called()
    bridge._kernel.trajectory_engine.executar_trajetoria_completa.assert_not_called()
    bridge._kernel.trajectory_engine.save_professor_session.assert_awaited_once()
    assert bridge._professor_mode is None


@pytest.mark.parametrize("ncd,observed,hwnd", [(0.0, 1, 77), (0.4, 0, 77), (None, 0, 77), (0.1, 1, 0)])
def test_unconfirmed_step_is_captured_and_finish_saves_honest_feedback(bridge, ncd, observed, hwnd):
    send(bridge, "/professor teste")
    send(bridge, "teste")
    bridge._kernel.trajectory_engine.execute_professor_step.return_value = {"lambda_obs": observed, "ncd_real": ncd, "observed_hwnd": hwnd}
    assert "capturado" in send(bridge, "tecla Win")["reply"]
    evidence = bridge._professor_mode["passos"][0]["feedback"]
    assert evidence["lambda_obs"] == observed and evidence["ncd_real"] == ncd
    assert "salvo" in send(bridge, "/fim")["reply"]
    bridge._kernel.trajectory_engine.save_professor_session.assert_awaited_once()
    assert bridge._kernel.trajectory_engine.save_professor_session.call_args.kwargs["capture_only"] is True


def test_ncd_failure_does_not_require_repeating_a_teaching_step(bridge):
    send(bridge, "/professor teste")
    send(bridge, "teste")
    engine = bridge._kernel.trajectory_engine.execute_professor_step
    engine.return_value = {"lambda_obs": 0, "ncd_real": 0.0, "observed_hwnd": 77}
    send(bridge, "tecla Win")
    assert "capturado" in send(bridge, "digite gridcraft")["reply"]
    assert engine.await_count == 2
    engine.return_value = {"lambda_obs": 1, "ncd_real": 0.1, "observed_hwnd": 77}
    send(bridge, "enter")
    assert len(bridge._professor_mode["passos"]) == 3
    assert "failed_step" not in bridge._professor_mode


def test_empty_finish_and_cancel_never_save(bridge):
    send(bridge, "/professor teste")
    send(bridge, "teste")
    assert "Nenhum passo gravado" in send(bridge, "/fim")["reply"]
    bridge._kernel.trajectory_engine.save_professor_session.assert_not_awaited()
    send(bridge, "/professor teste")
    assert "descartada" in send(bridge, "/cancelar_professor")["reply"]
    assert bridge._professor_mode is None
    assert "Não há demonstração" in send(bridge, "/fim")["reply"]
    bridge._kernel.trajectory_engine.save_professor_session.assert_not_awaited()


def test_unknown_teacher_phrase_does_not_fall_through_to_planner(bridge):
    send(bridge, "/professor teste")
    send(bridge, "teste")
    send(bridge, "abra whatsapp")
    bridge._tom.evaluate_intent.assert_not_called()
    bridge._kernel.trajectory_engine.execute_professor_step.assert_not_awaited()
    bridge._kernel.trajectory_engine.executar_trajetoria_completa.assert_not_called()


def evidence_step(ncd=0.1):
    return {"passo": 1, "acao": "HOTKEY", "keys": ["win"],
            "feedback": {"lambda_obs": 1, "ncd_real": ncd, "observed_hwnd": 77}}


def test_teacher_promotion_persists_without_inventing_bayesian_successes(tmp_path):
    path = str(tmp_path / "teacher.db")
    engine = MyelinatedPDAGEngine(path, dim=8, max_nodes=4)
    try:
        assert engine.record_demonstration("trajectory:abrir_gridcraft", "abrir_gridcraft", {"passos": [evidence_step()]})
        idx = engine.id_to_index["trajectory:abrir_gridcraft"]
        assert (engine.alpha[idx], engine.beta[idx]) == (1.5, 0.5)
        assert engine.weights[idx] == 1.0 and engine.is_myelinated[idx]
        assert engine.is_verified_demonstration("abrir_gridcraft")
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT weight,is_myelinated,teacher_verified,consecutive_successes FROM pdag_nodes").fetchone() == (1.0, 1, 1, 1)
    finally:
        engine.close()
    loaded = MyelinatedPDAGEngine(path, dim=8, max_nodes=4)
    try:
        route = loaded.find_myelinated_path("trajectory:abrir_gridcraft")
        assert route["__meta__"]["teacher_verified"] is True
        loaded.record_execution("trajectory:abrir_gridcraft", "abrir_gridcraft", {"passos": [evidence_step()]}, reinforcement=0.0)
        assert not loaded.is_verified_demonstration("abrir_gridcraft")
        assert loaded.flush_pending_writes()
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT is_myelinated,teacher_verified FROM pdag_nodes").fetchone() == (0, 0)
    finally:
        loaded.close()


def test_teacher_user_report_demotes_manual_override(tmp_path):
    engine = MyelinatedPDAGEngine(str(tmp_path / "penalty.db"), dim=8, max_nodes=4)
    try:
        engine.record_demonstration("trajectory:teste", "teste", {"passos": [evidence_step()]})
        engine.apply_user_report_penalty("teste", "falhou")
        assert not engine.is_verified_demonstration("teste")
    finally:
        engine.close()


@pytest.mark.parametrize("steps", [[], [evidence_step(0.0)], [{"acao": "TYPE", "text": "x"}]])
def test_pdag_rejects_unverified_demonstrations(tmp_path, steps):
    engine = MyelinatedPDAGEngine(str(tmp_path / "rejected.db"), dim=8, max_nodes=4)
    try:
        with pytest.raises(ValueError):
            engine.record_demonstration("trajectory:teste", "teste", {"passos": steps})
        assert engine.active_count == 0
    finally:
        engine.close()


def test_demonstrated_route_is_not_selected_by_fuzzy_similarity(tmp_path):
    engine = MyelinatedPDAGEngine(str(tmp_path / "exact.db"), dim=8, max_nodes=4)
    try:
        engine.record_demonstration("trajectory:teste", "teste", {"passos": [evidence_step()]})
        vsa = MagicMock()
        vsa.text_to_hypervector.return_value = engine.phase_matrix[0].copy()
        assert engine.find_myelinated_path("trajectory:other", vsa) is None
    finally:
        engine.close()


def test_professor_executor_restores_session_focus_then_verifies_post_hwnd():
    engine = object.__new__(CausalTrajectoryEngine)
    engine.ctx_engine = MagicMock()
    engine.ctx_engine.capture_foreground_context.side_effect = [
        {"hwnd": 99}, {"hwnd": 77, "process_name": "searchhost.exe"}, {"hwnd": 88}]
    engine.resolver = SimpleNamespace(focus_window_handle=MagicMock(return_value=True))
    engine.bridge = SimpleNamespace(dispatch=AsyncMock(return_value=SimpleNamespace(status="completed", result=True)))
    engine.verifier = MagicMock(ncd_threshold=0.2)
    engine.verifier.snapshot_pids.return_value = {10}
    engine.verifier.capture_state_bytes.side_effect = [b"before", b"after"]
    engine.verifier.measure_collapse.return_value = (1, 1.0, "", 10, 0.1, 0.02)
    engine.pdag = MagicMock()
    with patch("causal_trajectory.asyncio.sleep", new_callable=AsyncMock):
        result = asyncio.run(engine.execute_professor_step({"acao": "TYPE", "text": "gridcraft"}, "demo", expected_hwnd=77))
    assert result["observed_hwnd"] == 88 and result["lambda_obs"] == 1
    engine.resolver.focus_window_handle.assert_called_once_with(77)
    contract = engine.verifier.measure_collapse.call_args.kwargs["contract"]
    assert contract["action"] == "PROFESSOR_STEP" and contract["target_hwnd"] == 88
    assert contract["min_ncd"] == 0.02 and contract["expects_new_pid"] is False
    engine.pdag.record_transition.assert_called_once()


def test_failed_focus_restore_never_types():
    engine = object.__new__(CausalTrajectoryEngine)
    engine.ctx_engine = MagicMock()
    engine.ctx_engine.capture_foreground_context.return_value = {"hwnd": 99}
    engine.resolver = SimpleNamespace(focus_window_handle=MagicMock(return_value=False))
    engine.bridge = SimpleNamespace(dispatch=AsyncMock())
    with pytest.raises(RuntimeError, match="nenhuma entrada"):
        asyncio.run(engine.execute_professor_step({"acao": "TYPE", "text": "gridcraft"}, "demo", expected_hwnd=77))
    engine.bridge.dispatch.assert_not_awaited()


def test_save_open_concept_requires_correct_final_application():
    engine = object.__new__(CausalTrajectoryEngine)
    engine.resolver = SimpleNamespace(app_hwnd=MagicMock(return_value=None))
    engine.pdag = MagicMock()
    session = {"conceito": "abrir_app_generico", "app_alvo": "gridcraft", "passos": [
        evidence_step(), {**evidence_step(), "passo": 2, "acao": "TYPE", "text": "gridcraft"},
        {**evidence_step(), "passo": 3, "keys": ["enter"]}]}
    with pytest.raises(ValueError, match="janela"):
        asyncio.run(engine.save_professor_session(session))
    engine.pdag.record_demonstration.assert_not_called()


def test_nested_teacher_step_does_not_revoke_parent_trajectory_token():
    from execution_authority import authorization_scope
    engine = object.__new__(CausalTrajectoryEngine)
    engine.ctx_engine = MagicMock()
    engine.ctx_engine.capture_foreground_context.return_value = {"hwnd": 77}
    token = threading.Event()
    with authorization_scope(token), \
         patch.object(CausalTrajectoryEngine, "execute_subgoal", new_callable=AsyncMock, return_value={"lambda_obs": 1}):
        asyncio.run(engine.execute_professor_step({"acao": "HOTKEY", "keys": ["win"]}, "demo"))
        assert not token.is_set()


def test_exact_concept_replay_skips_decomposition_and_uses_teacher_verification():
    engine = object.__new__(CausalTrajectoryEngine)
    engine.pdag, engine.vsa = MagicMock(), MagicMock()
    engine.pdag.find_myelinated_path.return_value = {"passos": [evidence_step()], "__meta__": {"teacher_verified": True}}
    with patch.object(CausalTrajectoryEngine, "execute_professor_step", new_callable=AsyncMock,
                      return_value={"lambda_obs": 1, "ncd_real": 0.1, "expected_delta": 0.02, "reward": -0.0064}) as step, \
         patch.object(CausalTrajectoryEngine, "decompor_trajetoria_cognitiva", side_effect=AssertionError("No planner")):
        result = asyncio.run(engine.executar_trajetoria_completa("abrir_gridcraft"))
    assert result["sucesso_real"] is True and result["rota_mielinizada"] is True
    step.assert_awaited_once()
