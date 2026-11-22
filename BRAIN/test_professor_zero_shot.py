"""Generic opening survives persistence and does not mutate taught examples."""
import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

from causal_trajectory import CausalTrajectoryEngine
from hyperdimensional import FHRRHyperdimensionalEngine
from pdag_engine import MyelinatedPDAGEngine
from test_professor_mode import bridge, send
from test_professor_complete import mock_batch


def test_finish_asks_target_rejects_wrong_answer_then_saves_generic(bridge):
    mock_batch(bridge)
    bridge._kernel.pdag.record_user_confirmed_route.return_value = True
    send(bridge, "/professor abrir_brave | abrir_app | tecla win; digite brave; enter")
    original = deepcopy(bridge._professor_mode["passos_executados"])
    assert "variáveis" in send(bridge, "/fim")["reply"]
    bridge._kernel.pdag.record_user_confirmed_route.assert_not_called()
    assert "Não foi possível salvar" in send(bridge, "notepad")["reply"]
    with patch("qualia_algebra.save_qualia"):
        assert "salvo" in send(bridge, "brave")["reply"]
    args = bridge._kernel.pdag.record_user_confirmed_route.call_args.args
    assert args[0] == "trajectory:abrir_app_generico"
    assert args[2]["passos"][1]["text"] == "{APP_ALVO}"
    assert original[1]["text"] == "brave"
    assert bridge._professor_mode is None
    bridge._tom.evaluate_intent.assert_not_called()


def test_generic_opening_reloads_and_instantiates_without_llm(tmp_path):
    from role_binding import abstract_app_demonstration
    vsa = FHRRHyperdimensionalEngine(dim=64)
    steps = [{"acao": "HOTKEY", "keys": ["win"]}, {"acao": "WAIT", "seconds": .8},
             {"acao": "TYPE", "text": "brave"}, {"acao": "HOTKEY", "keys": ["enter"]}]
    template = abstract_app_demonstration(steps, "brave")
    path = str(tmp_path / "generic.db")
    pdag = MyelinatedPDAGEngine(path, dim=64, max_nodes=4)
    assert pdag.record_user_confirmed_route("trajectory:abrir_app_generico", "abrir_app_generico", template, vsa.generate_vector("generic"), vsa)
    pdag.close()
    pdag = MyelinatedPDAGEngine(path, dim=64, max_nodes=4)
    try:
        engine = object.__new__(CausalTrajectoryEngine)
        engine.pdag, engine.vsa = pdag, vsa
        with patch.object(CausalTrajectoryEngine, "_generate_creative_text", side_effect=AssertionError("No LLM")):
            for command, app in [("abra o notepad", "notepad"), ("inicie o gridcraft", "gridcraft")]:
                result = engine.decompor_trajetoria_cognitiva(command)
                assert result["passos"][2]["text"] == app
                assert result["pipeline"][1] == {"p": "WAIT", "seconds": .8}
        assert pdag.find_myelinated_path("trajectory:abrir_app_generico", exact_only=True)["passos"][2]["text"] == "{APP_ALVO}"
    finally:
        pdag.close()


def test_wait_uses_async_sleep_and_win_uses_bridge():
    engine = object.__new__(CausalTrajectoryEngine)
    engine.bridge = MagicMock()
    engine.bridge.dispatch = AsyncMock(return_value=MagicMock(status="completed", result=True))
    with patch("causal_trajectory.asyncio.sleep", new_callable=AsyncMock) as sleep:
        assert asyncio.run(engine._executar_passo_individual({"acao": "WAIT", "seconds": .8}))
        sleep.assert_awaited_once_with(.8)
    assert asyncio.run(engine._executar_passo_individual({"acao": "HOTKEY", "keys": ["win"]}))
    assert engine.bridge.dispatch.call_args.args[:2] == ("hotkey", {"keys": ["win"]})
