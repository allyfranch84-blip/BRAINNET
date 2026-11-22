"""Four-role algebra, honest cleanup scores, durable phases and guarded plans."""
from copy import deepcopy
from unittest.mock import patch

import numpy as np
import pytest

from causal_trajectory import CausalTrajectoryEngine
from hyperdimensional import FHRRHyperdimensionalEngine
from pdag_engine import MyelinatedPDAGEngine
from qualia_algebra import compose_qualia, save_qualia, retrieve_opening
from test_professor_mode import bridge, send


def opening():
    return [{"acao":"HOTKEY","keys":["win"]}, {"acao":"TYPE","text":"{APP_ALVO}"},
            {"acao":"HOTKEY","keys":["enter"]}]


def test_four_anchors_are_deterministic_unit_complex_vectors():
    vsa = FHRRHyperdimensionalEngine()
    other = FHRRHyperdimensionalEngine()
    for role in ("formal","constitutive","telic","agentive"):
        vector = getattr(vsa,"role_"+role)
        assert vector.shape == (10000,) and vector.dtype == np.complex64
        np.testing.assert_allclose(np.abs(vector),1,atol=1e-6)
        np.testing.assert_array_equal(vector,getattr(other,"role_"+role))


def test_extraction_is_exactly_existing_unbind_and_does_not_claim_perfect_decode():
    engine = CausalTrajectoryEngine.__new__(CausalTrajectoryEngine)
    engine.vsa = FHRRHyperdimensionalEngine()
    vector = compose_qualia(engine.vsa,"ABRIR_APP",opening())
    extracted = engine.extrair_proposito(vector)
    np.testing.assert_array_equal(extracted,engine.vsa.unbind(vector,engine.vsa.role_telic))
    raw = engine.vsa.similarity(extracted,engine.vsa.text_to_hypervector("ABRIR_APP"))
    assert .30 < raw < .70


def test_phase_tuple_roundtrip_and_zero_llm_transfer(tmp_path):
    path = str(tmp_path/"algebra.db")
    engine = CausalTrajectoryEngine.__new__(CausalTrajectoryEngine)
    engine.vsa = FHRRHyperdimensionalEngine(dim=10000)
    engine.pdag = MyelinatedPDAGEngine(path,dim=10000,max_nodes=4)
    vector = compose_qualia(engine.vsa,"ABRIR_APP",opening())
    try:
        assert save_qualia(engine.pdag,engine.vsa,"ABRIR_APP",opening(),vector)
        np.testing.assert_array_equal(engine.pdag.get_node_phases("qualia:ABRIR_APP"),vector)
        with patch("urllib.request.urlopen",side_effect=AssertionError("No Qwen")):
            plan = engine.decompor_trajetoria_cognitiva("abra o gridcraft")
        assert plan["pipeline"] == [{"p":"OPEN_APP","app":"gridcraft"}]
        transfer = plan["qualia_transfer"]
        assert transfer["source"] == "qualia:ABRIR_APP"
        assert .30 < transfer["raw_similarity"] < .70 < transfer["similarity"]
        assert transfer["agentive"][1]["text"] == "gridcraft"
        assert engine.pdag.alpha[0] == engine.pdag.beta[0] == .5
    finally:
        engine.pdag.close()
    engine.vsa = FHRRHyperdimensionalEngine(dim=10000)  # Empty cleanup on restart.
    engine.pdag = MyelinatedPDAGEngine(path,dim=10000,max_nodes=4)
    try:
        np.testing.assert_array_equal(engine.pdag.get_node_phases("qualia:ABRIR_APP"),vector)
        assert retrieve_opening(engine,"notepad")["pipeline"][0]["app"] == "notepad"
    finally:
        engine.pdag.close()


def test_reteaching_updates_same_phase_row_and_persists(tmp_path):
    path = str(tmp_path/"reteach.db")
    pdag = MyelinatedPDAGEngine(path,dim=256,max_nodes=4)
    vsa = FHRRHyperdimensionalEngine(dim=256)
    try:
        save_qualia(pdag,vsa,"ABRIR_APP",opening(),compose_qualia(vsa,"ABRIR_APP",opening()))
        updated = deepcopy(opening())
        updated[0]["feedback"] = {"lambda_obs":None}
        vector = compose_qualia(vsa,"ABRIR_APP",updated)
        save_qualia(pdag,vsa,"ABRIR_APP",updated,vector)
        assert pdag.active_count == 1
    finally:
        pdag.close()
    reloaded = MyelinatedPDAGEngine(path,dim=256,max_nodes=4)
    try:
        np.testing.assert_array_equal(reloaded.get_node_phases("qualia:ABRIR_APP"),vector)
    finally:
        reloaded.close()


def test_corrupted_tuple_cannot_select_a_route(tmp_path):
    engine = CausalTrajectoryEngine.__new__(CausalTrajectoryEngine)
    engine.vsa = FHRRHyperdimensionalEngine(dim=256)
    engine.pdag = MyelinatedPDAGEngine(str(tmp_path/"corrupt.db"),dim=256,max_nodes=4)
    try:
        save_qualia(engine.pdag,engine.vsa,"ABRIR_APP",opening(),compose_qualia(engine.vsa,"ABRIR_APP",opening()))
        engine.pdag.phase_matrix[0] = engine.vsa.generate_vector("unrelated")
        assert retrieve_opening(engine,"gridcraft") is None
    finally:
        engine.pdag.close()


@pytest.mark.parametrize("target", ["{APP_ALVO}", "gridcraft"])
def test_finish_composes_and_saves_separate_qualia_key(bridge,target):
    bridge._kernel.trajectory_engine.execute_professor_batch = __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(
        return_value=[{"lambda_obs":0,"ncd_real":0.}] * 3)
    send(bridge,f"/professor abrir_app | win | digite {target} | enter")
    send(bridge,"abrir_qualquer_app")
    with patch("qualia_algebra.save_qualia",return_value=True) as save:
        assert "salvo" in send(bridge,"/fim")["reply"]
    assert save.call_args.args[2] == "ABRIR_APP"
    assert save.call_args.args[3][1]["text"] == "{APP_ALVO}"
    np.testing.assert_allclose(save.call_args.args[4],compose_qualia(
        bridge._kernel.vsa,"ABRIR_APP",save.call_args.args[3]))
