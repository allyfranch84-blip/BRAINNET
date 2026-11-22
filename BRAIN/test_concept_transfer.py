"""Role-projected transfer across app names, without LLM or Windows input."""
from unittest.mock import patch

import numpy as np
import pytest

from causal_trajectory import CausalTrajectoryEngine
from concept_cortex import ConceptCortex
from hyperdimensional import FHRRHyperdimensionalEngine
from pdag_engine import MyelinatedPDAGEngine
from role_binding import abstract_app_demonstration, encode_open_concept


def lesson():
    evidence = {"lambda_obs": 1, "ncd_real": .2, "observed_hwnd": 77}
    steps = [{"acao": "HOTKEY", "keys": ["win"], "feedback": dict(evidence)},
             {"acao": "TYPE", "text": "notepad", "feedback": dict(evidence)},
             {"acao": "HOTKEY", "keys": ["enter"], "feedback": dict(evidence)}]
    return abstract_app_demonstration(steps, "notepad")


@pytest.fixture
def taught(tmp_path):
    vsa = FHRRHyperdimensionalEngine(dim=256)
    pdag = MyelinatedPDAGEngine(str(tmp_path / "transfer.db"), max_nodes=4, dim=256)
    pdag.record_demonstration("trajectory:abrir_app_generico", "abrir_app_generico", lesson(), vsa)
    yield pdag, vsa
    pdag.close()


@pytest.mark.parametrize("app", ["gridcraft", "whatsapp", "notepad", "aplicativo_nunca_visto"])
def test_action_transfers_with_new_slot_without_llm(taught, app):
    pdag, vsa = taught
    with patch("urllib.request.urlopen", side_effect=AssertionError("LLM indisponivel")):
        result = pdag.find_abstract_opening(app, vsa)
    assert result["similarity"] > .99
    assert result["similarity_space"] == "ROLE_ACTION"
    assert result["pipeline"] == [{"acao": "OPEN_APP", "app": app}]
    np.testing.assert_allclose(pdag.phase_matrix[0], encode_open_concept(vsa))


def test_learned_template_not_overwritten_by_bound_target(taught):
    pdag, vsa = taught
    pdag.find_abstract_opening("gridcraft", vsa)["pipeline"][0]["app"] = "changed"
    assert pdag.find_abstract_opening("whatsapp", vsa)["pipeline"][0]["app"] == "whatsapp"
    np.testing.assert_allclose(pdag.phase_matrix[0], encode_open_concept(vsa))


def test_transfer_survives_sqlite_reload(taught):
    pdag, vsa = taught
    pdag.close()
    reloaded = MyelinatedPDAGEngine(pdag.db_path, max_nodes=4, dim=256)
    try:
        assert reloaded.find_abstract_opening("gridcraft", vsa)["similarity"] > .99
        np.testing.assert_allclose(reloaded.phase_matrix[0], encode_open_concept(vsa))
    finally:
        reloaded.close()


def test_penalty_revokes_concept_transfer(taught):
    pdag, vsa = taught
    pdag.apply_user_report_penalty("abrir_app_generico", "Nao abriu")
    assert pdag.find_abstract_opening("gridcraft", vsa) is None


@pytest.mark.parametrize("score", [.70, .3, float("nan")])
def test_strict_threshold_no_optimistic_transfer(taught, score):
    pdag, vsa = taught
    with patch.object(FHRRHyperdimensionalEngine, "similarity", return_value=score):
        assert pdag.find_abstract_opening("gridcraft", vsa) is None


def test_htn_transfer_precedes_fuzzy_competition_and_preserves_goals(taught):
    engine = CausalTrajectoryEngine.__new__(CausalTrajectoryEngine)
    engine.pdag, engine.vsa = taught
    with patch.object(CausalTrajectoryEngine, "_projetar_onda_de_probabilidade", side_effect=AssertionError("Nao usar fallback")), \
         patch("urllib.request.urlopen", side_effect=AssertionError("LLM indisponivel")):
        single = engine.decompor_trajetoria_cognitiva("Abra o Gridcraft")
        multiple = engine.decompor_trajetoria_cognitiva("abra o whatsapp e diga oi para davi")
    assert single["pipeline"] == [{"p": "HOTKEY", "keys": ["win"]},
                                  {"p": "TYPE", "text": "gridcraft"},
                                  {"p": "HOTKEY", "keys": ["enter"]}]
    assert multiple["pipeline"][0]["app"] == "whatsapp"
    assert any(step.get("text") == "oi" for step in multiple["pipeline"])


def test_target_role_binding_is_local_and_complex(taught):
    _, vsa = taught
    cortex = ConceptCortex.__new__(ConceptCortex)
    cortex.hdc = vsa
    with patch("urllib.request.urlopen", side_effect=AssertionError("Sem Qwen")):
        target = cortex.vincular_alvo_ao_slot("Gridcraft")
    assert target.dtype == np.complex64
    np.testing.assert_allclose(target, vsa.bind(vsa.role_target, vsa.text_to_hypervector("Gridcraft")))


def test_tampered_meta_pipeline_never_transfers(taught):
    pdag, vsa = taught
    import sqlite3, json
    spec = lesson()
    spec["meta_pipeline"] = [{"acao": "TYPE", "text": "wrong"}]
    with sqlite3.connect(pdag.db_path) as conn:
        conn.execute("UPDATE pdag_nodes SET pipeline_spec = ?", (json.dumps(spec),))
    assert pdag.find_abstract_opening("gridcraft", vsa) is None
