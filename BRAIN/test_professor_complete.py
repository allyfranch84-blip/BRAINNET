"""Immediate batch state machine; no test sends real Windows input."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
import numpy as np

from causal_trajectory import CausalTrajectoryEngine
from hyperdimensional import FHRRHyperdimensionalEngine
from pdag_engine import MyelinatedPDAGEngine
from professor_mode import parse_complete_lesson
from test_professor_mode import bridge, send


def mock_batch(bridge):
    async def execute(steps, concept, authorization_token=None, on_step=None):
        for step in steps:
            on_step(step,{"lambda_obs":0,"ncd_real":0.,"observed_hwnd":77})
        return []
    bridge._kernel.trajectory_engine.execute_professor_batch = AsyncMock(side_effect=execute)


def test_complete_syntax_executes_now_then_waits_for_human(bridge):
    mock_batch(bridge)
    with patch("BRAINNET.urllib.request.urlopen",side_effect=AssertionError("No LLM")):
        reply = send(bridge,"/professor abrir_calc | abrir_app | tecla win; digite calc; tecla enter")
    assert "Ações executadas" in reply["reply"]
    session = bridge._professor_mode
    assert session["conceito"] == "abrir_calc" and session["proposito"] == "abrir_app"
    assert session["aguardando_validacao"] and not session["executing"]
    assert [s["acao"] for s in session["passos_executados"]] == ["HOTKEY","TYPE","HOTKEY"]
    bridge._kernel.trajectory_engine.execute_professor_batch.assert_awaited_once()
    bridge._kernel.pdag.record_execution.assert_not_called()


def test_undo_replace_finish_and_original_feedback_retained(bridge):
    mock_batch(bridge)
    send(bridge,"/professor abrir_calc | abrir_app | tecla win; digite calc; tecla enter")
    assert "Último passo removido" in send(bridge,"/voltar")["reply"]
    assert len(bridge._professor_mode["passos_executados"]) == 2
    send(bridge,"tecla esc")
    assert bridge._professor_mode["passos_executados"][-1]["keys"] == ["esc"]
    bridge._kernel.pdag.record_user_confirmed_route.return_value = True
    with patch("qualia_algebra.save_qualia",return_value=True):
        assert send(bridge,"/fim")["reply"] == "🎓 Conceito salvo com sucesso e mielinizado."
    saved = bridge._kernel.pdag.record_user_confirmed_route.call_args
    assert saved.args[0] == "trajectory:abrir_calc"
    assert saved.args[2]["passos"][0]["feedback"]["lambda_obs"] == 0
    assert bridge._professor_mode is None


def test_cancel_does_not_persist(bridge):
    mock_batch(bridge)
    send(bridge,"/professor teste | abrir_app | tecla win")
    assert "Nenhum conceito foi salvo" in send(bridge,"/cancelar")["reply"]
    assert bridge._professor_mode is None
    bridge._kernel.pdag.record_user_confirmed_route.assert_not_called()


def test_empty_after_undo_cannot_save(bridge):
    mock_batch(bridge)
    send(bridge,"/professor teste | abrir_app | tecla win")
    send(bridge,"/voltar")
    assert send(bridge,"/fim")["reply"] == "⚠️ Nenhum passo gravado. Digite os passos primeiro."


def test_quoted_commas_are_literal_text():
    lesson = parse_complete_lesson('/professor texto | escrever | digite "oi, mundo"; tecla enter')
    assert len(lesson[3]) == 2 and lesson[3][0]["text"] == "oi, mundo"


def test_invalid_batch_cannot_execute_any_prefix(bridge):
    bridge._kernel.trajectory_engine.execute_professor_batch = AsyncMock()
    send(bridge,"/professor teste | abrir_app | tecla win; invente comando")
    bridge._kernel.trajectory_engine.execute_professor_batch.assert_not_awaited()


def test_human_confirmation_promotes_once_and_survives_reload(tmp_path):
    path = str(tmp_path/"confirm.db")
    vsa = FHRRHyperdimensionalEngine(dim=64)
    pdag = MyelinatedPDAGEngine(path,dim=64,max_nodes=4)
    evidence = {"passos":[{"acao":"HOTKEY","keys":["enter"],"feedback":{"lambda_obs":0,"ncd_real":0.}}]}
    vector = vsa.generate_vector("qualia")
    try:
        assert pdag.record_user_confirmed_route("trajectory:aula","aula",evidence,vector,vsa)
        assert pdag.alpha[0] == 1.5 and pdag.beta[0] == .5
        assert pdag.is_myelinated[0]
    finally:
        pdag.close()
    reloaded = MyelinatedPDAGEngine(path,dim=64,max_nodes=4)
    try:
        assert reloaded.is_verified_demonstration("aula")
        saved = reloaded.find_myelinated_path("trajectory:aula",exact_only=True)
        assert saved["passos"][0]["feedback"]["lambda_obs"] == 0
        np.testing.assert_array_equal(reloaded.phase_matrix[0],vector)
    finally:
        reloaded.close()
