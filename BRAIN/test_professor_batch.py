"""Human teaching may be unverified; autonomous writes remain verified."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from causal_trajectory import CausalTrajectoryEngine
from hyperdimensional import FHRRHyperdimensionalEngine
from pdag_engine import MyelinatedPDAGEngine
from professor_mode import parse_professor_step
from effector import Effector
from test_professor_mode import bridge, send


def steps():
    return [{"passo": index, **parse_professor_step(text)} for index, text in enumerate(
        ["tecla win", "digite gridcraft", "enter"], 1)]


def test_batch_is_one_authorized_operation_and_captures_low_ncd(bridge):
    engine = bridge._kernel.trajectory_engine
    engine.execute_professor_batch = AsyncMock(return_value=[{"lambda_obs": 0, "ncd_real": 0.0}] * 3)
    with patch("BRAINNET.urllib.request.urlopen", side_effect=AssertionError("No LLM")):
        response = send(bridge, "/professor abrir_app | tecla win | digite gridcraft | enter")
        assert "PROPÓSITO" in response["reply"]
        engine.execute_professor_batch.assert_not_awaited()
        response = send(bridge, "abrir_qualquer_app")
        assert "3 passos" in response["reply"]
        assert [s["acao"] for s in bridge._professor_mode["passos"]] == ["HOTKEY", "TYPE", "HOTKEY"]
        assert all(s["feedback"]["lambda_obs"] == 0 for s in bridge._professor_mode["passos"])
        assert "salvo" in send(bridge, "/fim")["reply"]
    engine.execute_professor_batch.assert_awaited_once()
    engine.execute_professor_step.assert_not_awaited()
    engine.save_professor_session.assert_awaited_once()
    bridge._tom.evaluate_intent.assert_not_called()


def test_bad_batch_prevalidated_before_any_input(bridge):
    bridge._kernel.trajectory_engine.execute_professor_batch = AsyncMock()
    send(bridge, "/professor teste | tecla win | abra whatsapp")
    bridge._kernel.trajectory_engine.execute_professor_batch.assert_not_awaited()
    assert bridge._professor_mode is None


def test_timeout_keeps_all_human_steps_as_not_executed(bridge):
    bridge._kernel.trajectory_engine.execute_professor_batch = AsyncMock(side_effect=TimeoutError("limite"))
    send(bridge, "/professor teste | tecla win | digite gridcraft | enter")
    send(bridge, "teste")
    assert len(bridge._professor_mode["passos"]) == 3
    assert all(s["feedback"]["failure_reason"] == "NOT_EXECUTED_YET" for s in bridge._professor_mode["passos"])
    assert "salvo" in send(bridge,"/fim")["reply"]


@pytest.mark.parametrize("voice,key", [("enter","enter"), ("tecla enter","enter"),
                                      ("apertar enter","enter"), ("espaço","space"),
                                      ("seta para baixo","down")])
def test_voice_teaching_uses_literal_keyboard_route(bridge,voice,key):
    bridge._professor_mode = {"conceito":"teste", "passos":[]}
    bridge._window = None
    bridge.send_command = MagicMock(return_value={"reply":"capturado"})
    bridge._on_voice_input(voice)
    bridge.send_command.assert_called_once_with(f"tecla {key}")
    assert parse_professor_step(voice) == {"acao":"HOTKEY","keys":[key]}


def test_batch_ignores_ncd_failure_but_halts_after_actuator_failure():
    engine = CausalTrajectoryEngine.__new__(CausalTrajectoryEngine)
    outcomes = [{"lambda_obs":0,"failure_reason":"NCD baixo"},
                {"lambda_obs":0,"failure_reason":"ACTION_EXCEPTION: RuntimeError: Win32"}]
    with patch.object(CausalTrajectoryEngine,"execute_professor_step",new=AsyncMock(side_effect=outcomes)) as execute:
        result = asyncio.run(engine.execute_professor_batch(steps(),"teste"))
    assert execute.await_count == 2
    assert all(call.kwargs["teaching"] is True for call in execute.call_args_list)
    assert result[2]["failure_reason"] == "NOT_EXECUTED_PRIOR_ACTUATOR_ERROR"


@pytest.mark.parametrize("key,vk", [("space",0x20),("left",0x25),("up",0x26),("right",0x27),("down",0x28)])
def test_professor_voice_keys_reach_win32_correctly(key,vk):
    events = []
    def capture(count,pointer,size):
        events.append((pointer._obj.u.ki.wVk,pointer._obj.u.ki.dwFlags))
        return count
    with patch("effector.user32.SendInput",side_effect=capture), patch("effector.time.sleep"):
        assert Effector().send_hotkey([key]) is True
    assert events == [(vk,0),(vk,2)]


def test_human_capture_persists_without_inventing_beta_success(tmp_path):
    path = str(tmp_path/"human.db")
    pdag = MyelinatedPDAGEngine(path,dim=64,max_nodes=4)
    vsa = FHRRHyperdimensionalEngine(dim=64)
    pipeline = {"passos":[{"acao":"HOTKEY","keys":["enter"],"feedback":{"lambda_obs":0,"ncd_real":0.0}}]}
    try:
        assert pdag.record_human_demonstration("trajectory:aula","aula",pipeline,vsa)
        assert pdag.alpha[0] == pdag.beta[0] == .5
        assert not pdag.teacher_verified[0] and not pdag.is_myelinated[0]
        assert pdag.find_myelinated_path("trajectory:aula",exact_only=True) is None
    finally:
        pdag.close()
    reloaded = MyelinatedPDAGEngine(path,dim=64,max_nodes=4)
    try:
        saved = reloaded.find_taught_path("trajectory:aula")
        assert saved["passos"] == pipeline["passos"] and saved["pending_validation"]
        assert reloaded.alpha[0] == reloaded.beta[0] == .5
    finally:
        reloaded.close()


def test_forced_save_infers_app_even_without_ncd_or_hwnd(tmp_path):
    engine = CausalTrajectoryEngine.__new__(CausalTrajectoryEngine)
    engine.pdag = MyelinatedPDAGEngine(str(tmp_path/"forced.db"),dim=64,max_nodes=4)
    engine.vsa = FHRRHyperdimensionalEngine(dim=64)
    engine.resolver = MagicMock()
    session = {"conceito":"abrir_app", "passos":steps()}
    try:
        assert asyncio.run(engine.save_professor_session(session,capture_only=True))
        assert session["saved_concept"] == "abrir_app_generico"
        transfer = engine.pdag.find_abstract_opening("notepad",engine.vsa)
        assert transfer["pipeline"] == [{"acao":"OPEN_APP","app":"notepad"}]
        assert transfer["pending_validation"]
        engine.resolver.app_hwnd.assert_not_called()
    finally:
        engine.pdag.close()


def test_autonomous_replay_of_capture_still_stops_on_verifier_failure(tmp_path):
    engine = CausalTrajectoryEngine.__new__(CausalTrajectoryEngine)
    engine.pdag = MyelinatedPDAGEngine(str(tmp_path/"replay.db"),dim=64,max_nodes=4)
    engine.vsa = FHRRHyperdimensionalEngine(dim=64)
    try:
        engine.pdag.record_human_demonstration("trajectory:aula","aula",{"passos":steps()},engine.vsa)
        failed = {"lambda_obs":0,"ncd_real":0.,"expected_delta":.02,"reward":-.0004,"failure_reason":"NCD baixo"}
        with patch.object(CausalTrajectoryEngine,"execute_subgoal",new=AsyncMock(return_value=failed)) as verify:
            result = asyncio.run(engine.executar_trajetoria_completa("aula"))
        assert result["sucesso_real"] is False
        assert verify.await_count == 1
    finally:
        engine.pdag.close()
