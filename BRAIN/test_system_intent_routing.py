"""Literal OS routing and native search, with every physical boundary mocked."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import numpy as np
import pytest

from BRAINNET import BrainnetBridge
from causal_trajectory import CausalTrajectoryEngine, DynamicAppInventory
from concept_cortex import ConceptCortex
from system_intent import application_matches, system_launch_target
from theory_of_mind import MentalizingJudgment, MotorGateState


@pytest.mark.parametrize("text,target", [
    ("abra o menu iniciar, digite gridcraft e aperte enter", "gridcraft"),
    ("abra o menu iniciar e digite gridcraft e aperte enter", "gridcraft"),
    ('abra o Menu Iniciar... digite "GridCraft" e pressione Enter', "gridcraft"),
    ("abra o gridcraft", "gridcraft"), ("pesquise no pc por gridcraft", "gridcraft"),
    ("abra o Visual Studio Code", "visual studio code"),
    ("abra a geladeira", None), ("inicie o processo", None),
    ("o gridcraft não abriu", None),
])
def test_extracts_literal_system_target_without_message_payload(text, target):
    assert system_launch_target(text) == target


@pytest.mark.parametrize("text", ["abra o gridcraft", "abra o menu iniciar e digite gridcraft e aperte enter", "pesquise no pc gridcraft"])
def test_projection_cannot_choose_communication_for_os_requests(text):
    engine = object.__new__(CausalTrajectoryEngine)
    probabilities = engine._projetar_onda_de_probabilidade(text)
    assert probabilities["COMUNICACAO"] == 0 and probabilities["ESTADO_SISTEMA"] == 1


@pytest.mark.parametrize("text", ["abra o gridcraft", "abra o menu iniciar e digite gridcraft e aperte enter"])
def test_literal_launch_overrides_even_a_hijacked_probability_vector(text):
    engine = object.__new__(CausalTrajectoryEngine)
    with patch.object(CausalTrajectoryEngine, "_projetar_onda_de_probabilidade", return_value={"COMUNICACAO": 1, "ESTADO_SISTEMA": 0}):
        plan = engine.decompor_trajetoria_cognitiva(text)
    assert plan["passos"] == [{"passo": 1, "acao": "START_MENU_SEARCH", "app": "gridcraft"}]
    assert "whatsapp" not in str(plan).casefold()


def test_cortex_uses_raw_literal_instead_of_wrong_model_target():
    cortex = object.__new__(ConceptCortex)
    result = cortex.parse_and_route(np.ones(8, dtype=np.complex64), target_text="whatsapp", raw_text="abra o gridcraft")
    assert result["target"] == "gridcraft" and result["action"] == "OPEN"
    assert result["mechanism_hint"]["kind"] == "START_MENU_SEARCH"
    assert result["is_verified"] is False and result["kappa"] is None


def test_unknown_app_is_not_substituted_by_fhrr_similarity():
    inventory = DynamicAppInventory()
    vsa = MagicMock()
    vsa.similarity.return_value = 1.0
    with patch.object(DynamicAppInventory, "refresh_inventory", return_value={"whatsapp": {"cmd": "whatsapp:"}}):
        assert inventory.resolve_app_probabilistic("gridcraft", vsa) is None
    vsa.similarity.assert_not_called()


@pytest.fixture
def search_engine(monkeypatch):
    monkeypatch.setattr("causal_trajectory.find_app_process", lambda target: None)
    engine = object.__new__(CausalTrajectoryEngine)
    engine.ctx_engine = MagicMock()
    engine.ctx_engine.capture_foreground_context.side_effect = [
        {"start_menu_open": False, "process_name": "whatsapp.exe"},
        {"start_menu_open": True, "process_name": "startmenuexperiencehost.exe"},
        {"start_menu_open": False, "process_name": "searchhost.exe"},
    ]
    engine.resolver = SimpleNamespace(foreground_app_hwnd=MagicMock(return_value=77),
                                     _open_via_start_menu=MagicMock(return_value=True),
                                     _inventory_engine=MagicMock(), launch_app=MagicMock())
    engine.bridge = SimpleNamespace(_input_lock=asyncio.Lock(), dispatch=AsyncMock(return_value=SimpleNamespace(status="completed", result=True)))
    return engine


def test_native_search_is_win_type_enter_then_readonly_target_check(search_engine):
    from actuator_bridge import CommandPriority
    with patch("causal_trajectory.asyncio.sleep", new_callable=AsyncMock):
        result = asyncio.run(search_engine._executar_passo_individual({"acao": "START_MENU_SEARCH", "app": "gridcraft"}))
    assert result == {"target_hwnd": 77, "app": "gridcraft"}
    search_engine.resolver._open_via_start_menu.assert_called_once_with("gridcraft")
    search_engine.bridge.dispatch.assert_not_awaited()
    search_engine.resolver.foreground_app_hwnd.assert_called_once_with("gridcraft")


def test_failed_start_menu_never_types_into_whatsapp(search_engine):
    search_engine.resolver._open_via_start_menu.side_effect = RuntimeError("Menu Iniciar sem foco; nenhuma digitacao foi enviada")
    search_engine.ctx_engine.capture_foreground_context.side_effect = None
    search_engine.ctx_engine.capture_foreground_context.return_value = {"start_menu_open": False, "process_name": "whatsapp.exe"}
    with patch("causal_trajectory.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(RuntimeError, match="nenhuma digitacao"):
            asyncio.run(search_engine._executar_passo_individual({"acao": "START_MENU_SEARCH", "app": "gridcraft"}))
    search_engine.bridge.dispatch.assert_not_awaited()


def test_focus_theft_blocks_enter(search_engine):
    search_engine.resolver._open_via_start_menu.side_effect = RuntimeError("Foco saiu da busca; Enter bloqueado")
    search_engine.ctx_engine.capture_foreground_context.side_effect = [
        {"start_menu_open": False}, {"start_menu_open": True, "process_name": "startmenuexperiencehost.exe"},
        {"start_menu_open": False, "process_name": "whatsapp.exe"}]
    with patch("causal_trajectory.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(RuntimeError, match="Enter bloqueado"):
            asyncio.run(search_engine._executar_passo_individual({"acao": "START_MENU_SEARCH", "app": "gridcraft"}))
    search_engine.bridge.dispatch.assert_not_awaited()


def test_absent_target_window_is_not_reported_as_open(search_engine):
    search_engine.resolver.foreground_app_hwnd.return_value = None
    with patch("causal_trajectory.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(RuntimeError, match="Janela alvo"):
            asyncio.run(search_engine._executar_passo_individual({"acao": "START_MENU_SEARCH", "app": "gridcraft"}))


@pytest.mark.parametrize("process,title,expected", [
    ("gridcraft.exe", "Documento", True), ("electron.exe", "Gridcraft - Projeto", True),
    ("whatsapp.exe", "Gridcraft", False), ("searchhost.exe", "Gridcraft", False),
    ("electron.exe", "Outro app", False),
])
def test_hwnd_identity_does_not_accept_chat_or_search_results(process, title, expected):
    assert application_matches("gridcraft", process, title) is expected


def test_unknown_ensure_app_uses_native_search_not_fuzzy_launcher(search_engine):
    search_engine.resolver._inventory_engine.refresh_inventory.return_value = {}
    with patch.object(CausalTrajectoryEngine, "_start_menu_search", new_callable=AsyncMock, return_value={"target_hwnd": 77}) as search:
        asyncio.run(search_engine._executar_passo_individual({"acao": "ENSURE_APP", "app": "gridcraft"}))
    search.assert_awaited_once_with("gridcraft")
    search_engine.resolver.launch_app.assert_not_called()


def test_unknown_literal_app_bypasses_clarification_without_bypassing_rejection():
    bridge = object.__new__(BrainnetBridge)
    bridge._kernel, bridge._tom = MagicMock(), MagicMock()
    bridge._kernel.loop = None
    bridge._kernel.metacognition.registrar_resultado.return_value = 0.0
    bridge._kernel.trajectory_engine.executar_trajetoria_completa = AsyncMock(return_value={"status": "CONCLUIDO", "sucesso_real": True})
    bridge._modo_coder_ativo = False
    bridge._falar_seguro = MagicMock()
    bridge._tom.evaluate_intent.return_value = MentalizingJudgment(MotorGateState.CLARIFICATION,
        "abra o gridcraft", "unknown app", False, True, 0.1, "Esclarecimento")
    result = bridge._executar_comando_interno("abra o gridcraft", "abra o gridcraft", "abra o gridcraft")
    assert "Esclarecimento Necessário" not in result["reply"]
    bridge._kernel.trajectory_engine.executar_trajetoria_completa.assert_awaited_once()
    bridge._tom.evaluate_intent.return_value = MentalizingJudgment(MotorGateState.PRAGMATIC_REJECT,
        "abra a geladeira", "physical", True, False, 1.0, "Rejeitado")
    bridge._kernel.trajectory_engine.executar_trajetoria_completa.reset_mock()
    bridge._executar_comando_interno("abra a geladeira", "abra a geladeira", "abra a geladeira")
    bridge._kernel.trajectory_engine.executar_trajetoria_completa.assert_not_called()


@pytest.mark.parametrize("cached", [
    [{"acao": "ENSURE_APP", "app": "whatsapp"}],
    [{"acao": "TYPE", "text": "old feedback"}],
    [{"acao": "ENSURE_APP", "app": "gridcraft"}, {"acao": "TYPE", "text": "old feedback"}],
])
def test_poisoned_cached_route_is_not_replayed(cached):
    engine = object.__new__(CausalTrajectoryEngine)
    engine.pdag, engine.vsa = MagicMock(), MagicMock()
    engine.pdag.find_myelinated_path.return_value = {"passos": cached}
    with patch.object(CausalTrajectoryEngine, "execute_subgoal", new_callable=AsyncMock) as execute, \
         patch.object(CausalTrajectoryEngine, "decompor_trajetoria_cognitiva", return_value={"passos": []}) as plan:
        asyncio.run(engine.executar_trajetoria_completa("abra o gridcraft"))
    execute.assert_not_awaited()
    plan.assert_called_once_with("abra o gridcraft")
