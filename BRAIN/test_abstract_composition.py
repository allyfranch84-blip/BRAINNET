"""Abstract role binding and multi-goal composition; no actual app or message."""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from BRAINNET import BrainnetBridge
from causal_trajectory import CausalTrajectoryEngine
from concept_cortex import ConceptCortex
from htn_planner import compile_objectives, parse_objectives
from hyperdimensional import FHRRHyperdimensionalEngine
from pdag_engine import MyelinatedPDAGEngine
from role_binding import abstract_app_demonstration


def demonstration():
    evidence = {"lambda_obs": 1, "ncd_real": 0.1, "observed_hwnd": 77}
    return [{"passo": 1, "acao": "HOTKEY", "keys": ["win"], "feedback": dict(evidence)},
            {"passo": 2, "acao": "TYPE", "text": "gridcraft", "feedback": dict(evidence)},
            {"passo": 3, "acao": "HOTKEY", "keys": ["enter"], "feedback": dict(evidence)}]


def test_abstract_template_contains_slot_and_no_original_app():
    steps = demonstration()
    template = abstract_app_demonstration(steps, "gridcraft")
    assert template["passos"][1]["text"] == "{APP_ALVO}"
    assert "gridcraft" not in json.dumps(template)
    assert steps[1]["text"] == "gridcraft"


def test_slot_instantiation_is_literal_and_does_not_mutate_template():
    template = abstract_app_demonstration(demonstration(), "gridcraft")
    before = deepcopy(template)
    notepad = ConceptCortex.SUBSTITUIR_SLOT(template, {"APP_ALVO": "notepad"})
    whatsapp = ConceptCortex.SUBSTITUIR_SLOT(template, {"APP_ALVO": "whatsapp"})
    assert notepad["passos"][1]["text"] == "notepad"
    assert whatsapp["passos"][1]["text"] == "whatsapp"
    assert template == before


def test_missing_binding_never_leaves_an_executable_placeholder():
    with pytest.raises(ValueError, match="APP_ALVO"):
        ConceptCortex.SUBSTITUIR_SLOT({"passos": [{"acao": "TYPE", "text": "{APP_ALVO}"}]}, {})


def test_values_with_braces_are_not_evaluated_or_recursively_expanded():
    result = ConceptCortex.SUBSTITUIR_SLOT({"text": "{MENSAGEM}"}, {"MENSAGEM": "literal {OUTRO_SLOT}"})
    assert result["text"] == "literal {OUTRO_SLOT}"


@pytest.mark.parametrize("app", ["outro app", ""])
def test_teacher_answer_must_match_actual_demonstration(app):
    with pytest.raises(ValueError):
        abstract_app_demonstration(demonstration(), app)


def test_absolute_click_coordinates_cannot_be_promoted_to_generic_app_concept():
    steps = demonstration()
    steps[0] = {"acao": "CLICK", "x": 1, "y": 2}
    with pytest.raises(ValueError, match="coordenadas"):
        abstract_app_demonstration(steps, "gridcraft")


def test_open_and_message_preserve_both_goals_and_all_roles():
    goals = parse_objectives("abra o whatsapp e diga oi para davi")
    assert [goal["kind"] for goal in goals] == ["OPEN_APP", "SEND_MESSAGE"]
    assert goals[1]["roles"] == {"MENSAGEM": "oi", "DESTINATARIO": "davi"}
    plan = compile_objectives(goals)
    assert plan["passos"][0] == {"passo": 1, "acao": "ENSURE_APP", "app": "whatsapp"}
    values = [step.get("text") for step in plan["passos"] if step["acao"] == "TYPE"]
    assert values == ["davi", "oi"]


def test_quoted_message_does_not_inject_additional_goals():
    goals = parse_objectives('abra o whatsapp e diga "oi e abra outro app" para davi')
    assert len(goals) == 2
    assert goals[1]["roles"]["MENSAGEM"] == "oi e abra outro app"


def test_open_and_search_compile_in_order():
    goals = parse_objectives("abra o brave e pesquise python")
    plan = compile_objectives(goals, web_search=True)
    assert plan["passos"][0]["app"] == "brave"
    assert plan["passos"][1]["keys"] == ["ctrl", "l"]
    assert plan["passos"][2]["text"] == "https://www.google.com/search?q=python"


def test_three_objectives_are_composed_without_cutting_literal_text():
    goals = parse_objectives('abra notepad e digite "texto e palavras" e pesquise exemplo')
    assert [goal["kind"] for goal in goals] == ["OPEN_APP", "TYPE_TEXT", "SEARCH"]
    plan = compile_objectives(goals)
    assert plan["passos"][1]["text"] == "texto e palavras"
    assert [step["passo"] for step in plan["passos"]] == list(range(1, len(plan["passos"]) + 1))


def test_causal_planner_uses_htn_before_competing_intention_scores():
    engine = object.__new__(CausalTrajectoryEngine)
    with patch.object(CausalTrajectoryEngine, "_projetar_onda_de_probabilidade", side_effect=AssertionError("No argmax routing")):
        plan = engine.decompor_trajetoria_cognitiva("abra o whatsapp e diga oi para davi")
    assert plan["passos"][0]["app"] == "whatsapp"
    assert any(step.get("text") == "oi" for step in plan["passos"])


def test_generic_opening_reuses_template_for_multiple_targets_without_specializing_it():
    template = abstract_app_demonstration(demonstration(), "gridcraft")
    engine = object.__new__(CausalTrajectoryEngine)
    engine.pdag, engine.vsa = MagicMock(), MagicMock()
    engine.pdag.is_verified_demonstration.return_value = True
    engine.pdag.find_myelinated_path.return_value = {**deepcopy(template), "__meta__": {"teacher_verified": True}}
    engine.resolver = SimpleNamespace(foreground_app_hwnd=MagicMock(return_value=88))
    with patch.object(CausalTrajectoryEngine, "execute_professor_step", new_callable=AsyncMock,
                      return_value={"lambda_obs": 1}) as execute:
        asyncio.run(engine._execute_generic_opening("notepad"))
        asyncio.run(engine._execute_generic_opening("whatsapp"))
    assert execute.call_args_list[1].args[0]["text"] == "notepad"
    assert execute.call_args_list[4].args[0]["text"] == "whatsapp"
    for saved in engine.pdag.record_execution.call_args_list:
        assert saved.args[0] == "trajectory:abrir_app_generico"
        assert saved.args[2]["passos"][1]["text"] == "{APP_ALVO}"
    assert engine.pdag.find_myelinated_path.return_value["passos"][1]["text"] == "{APP_ALVO}"


def test_generic_demonstration_persists_role_bound_phase_not_original_app(tmp_path):
    pdag = MyelinatedPDAGEngine(str(tmp_path / "generic.db"), dim=64, max_nodes=4)
    vsa = FHRRHyperdimensionalEngine(dim=64)
    try:
        template = abstract_app_demonstration(demonstration(), "gridcraft")
        pdag.record_demonstration("trajectory:abrir_app_generico", "abrir_app_generico", template, vsa)
        route = pdag.find_myelinated_path("trajectory:abrir_app_generico", exact_only=True)
        assert route["passos"][1]["text"] == "{APP_ALVO}"
        expected = vsa.bind(vsa.role_action, vsa.text_to_hypervector("ABRIR_APP"))
        np.testing.assert_allclose(pdag.phase_matrix[0], expected)
        bound = ConceptCortex.instantiate_generic_opening(pdag, "notepad")
        assert bound["pipeline"]["passos"][1]["text"] == "notepad"
    finally:
        pdag.close()


def test_unbound_generic_concept_never_executes_placeholder():
    engine = object.__new__(CausalTrajectoryEngine)
    engine.pdag, engine.vsa = MagicMock(), MagicMock()
    engine.pdag.find_myelinated_path.return_value = {"meta_primitive": "OPEN_APP", "passos": []}
    with patch.object(CausalTrajectoryEngine, "execute_subgoal", new_callable=AsyncMock) as execute:
        result = asyncio.run(engine.executar_trajetoria_completa("abrir_app_generico"))
    assert result["status"] == "NEED_BINDING"
    execute.assert_not_awaited()
