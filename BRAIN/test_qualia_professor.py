"""Telic teaching, symbolic slots and compact persistent Qualia vectors."""
import asyncio
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from causal_trajectory import CausalTrajectoryEngine
from hyperdimensional import FHRRHyperdimensionalEngine
from pdag_engine import MyelinatedPDAGEngine
from professor_mode import parse_professor_step
from test_professor_mode import bridge, send


def test_purpose_question_never_calls_llm_or_actuator(bridge):
    with patch("BRAINNET.urllib.request.urlopen",side_effect=AssertionError("No LLM")):
        reply = send(bridge,"/professor abrir_app")["reply"]
        assert reply == "🎓 Qual é o PROPÓSITO deste conceito? (ex: abrir_qualquer_app, enviar_mensagem)"
        assert bridge._professor_mode["awaiting_purpose"]
        send(bridge,"abrir_qualquer_app")
    assert bridge._professor_mode["telic"] == "ABRIR_APP"
    bridge._kernel.trajectory_engine.execute_professor_step.assert_not_awaited()


def test_symbolic_batch_is_captured_and_saved_without_window_focus(bridge):
    engine = bridge._kernel.trajectory_engine
    engine.execute_professor_batch = AsyncMock()
    assert "PROPÓSITO" in send(bridge,"/professor abrir_app | win | digite {APP_ALVO} | enter")["reply"]
    assert "sem execução" in send(bridge,"abrir_qualquer_app")["reply"]
    session = bridge._professor_mode
    assert session["passos"][1]["text"] == "{APP_ALVO}"
    assert session["telic"] == "ABRIR_APP"
    assert all(step["feedback"]["lambda_obs"] is None for step in session["passos"])
    assert "salvo" in send(bridge,"/fim")["reply"]
    engine.execute_professor_batch.assert_not_awaited()
    engine.execute_professor_step.assert_not_awaited()
    engine.save_professor_session.assert_awaited_once()


def test_single_slot_switches_remaining_lesson_to_capture_only(bridge):
    send(bridge,"/professor mensagem")
    send(bridge,"enviar_mensagem")
    send(bridge,"digite {MENSAGEM}")
    send(bridge,"enter")
    assert len(bridge._professor_mode["passos"]) == 2
    bridge._kernel.trajectory_engine.execute_professor_step.assert_not_awaited()


def test_engine_batch_cannot_send_a_placeholder_or_even_open_start():
    engine = CausalTrajectoryEngine.__new__(CausalTrajectoryEngine)
    steps = [parse_professor_step(text) for text in ("win","digite {APP_ALVO}","enter")]
    with patch.object(CausalTrajectoryEngine,"execute_professor_step",new=AsyncMock()) as execute:
        result = asyncio.run(engine.execute_professor_batch(steps,"abrir"))
    execute.assert_not_awaited()
    assert all(item["failure_reason"] == "SYMBOLIC_CAPTURE_ONLY" for item in result)


def test_autonomous_type_requires_bound_slot():
    engine = CausalTrajectoryEngine.__new__(CausalTrajectoryEngine)
    engine.bridge = MagicMock()
    with pytest.raises(ValueError,match="slots"):
        asyncio.run(engine._executar_passo_individual({"acao":"TYPE","text":"{APP_ALVO}"}))
    engine.bridge.dispatch.assert_not_called()


def test_record_execution_persists_qualia_and_actual_complex_vector(tmp_path):
    path = str(tmp_path/"qualia.db")
    vsa = FHRRHyperdimensionalEngine(dim=10000)
    pdag = MyelinatedPDAGEngine(path,dim=10000,max_nodes=4)
    steps = [{"acao":"TYPE","text":"{APP_ALVO}"}]
    try:
        pdag.record_execution("trajectory:abrir","abrir",{"telic":"ABRIR_APP","passos":steps},vsa_engine=vsa)
        qualia = pdag.get_qualia("trajectory:abrir")
        assert qualia["formal"] == "MACRO_ACTION" and qualia["telic"] == "ABRIR_APP"
        assert qualia["agentive"] == steps
        assert qualia["v_conceito"].dtype == np.complex64
        np.testing.assert_allclose(qualia["v_conceito"],vsa.encode_compositional(action="ABRIR_APP",target="QUALIA"))
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT length(qualia_vector) FROM pdag_nodes").fetchone()[0] == 80000
    finally:
        pdag.close()
    reloaded = MyelinatedPDAGEngine(path,dim=10000,max_nodes=4)
    try:
        np.testing.assert_allclose(reloaded.get_qualia("trajectory:abrir")["v_conceito"],qualia["v_conceito"])
    finally:
        reloaded.close()


def test_professor_symbolic_save_qualia_does_not_invent_success(tmp_path):
    engine = CausalTrajectoryEngine.__new__(CausalTrajectoryEngine)
    engine.vsa = FHRRHyperdimensionalEngine(dim=128)
    engine.pdag = MyelinatedPDAGEngine(str(tmp_path/"human.db"),dim=128,max_nodes=4)
    session = {"conceito":"abrir_app", "telic":"ABRIR_APP",
               "passos":[parse_professor_step(text) for text in ("win","digite {APP_ALVO}","enter")]}
    try:
        assert asyncio.run(engine.save_professor_session(session,capture_only=True))
        key = f"trajectory:{session['saved_concept']}"
        assert engine.pdag.get_qualia(key)["telic"] == "ABRIR_APP"
        assert engine.pdag.alpha[0] == engine.pdag.beta[0] == .5
        assert engine.pdag.find_taught_path(key)["pending_validation"]
    finally:
        engine.pdag.close()
