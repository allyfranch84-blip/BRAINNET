"""Semanas 1/2: instrumentacao e exemplares; sem reconhecimento ou cliques reais."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from concept_cortex import ConceptCortex
from cybernetic_verifier import CyberneticVerifier
from causal_trajectory import CausalTrajectoryEngine
from error_blackbox import ErrorBlackBoxEngine
from hyperdimensional import FHRRHyperdimensionalEngine
from ui_tars_protocol import UIProtocolController, parse_ui_action


@pytest.fixture
def learning(tmp_path):
    vsa = FHRRHyperdimensionalEngine(dim=64)
    cortex = ConceptCortex(vsa, MagicMock(), db_path=str(tmp_path / "concepts.db"), dim=64)
    blackbox = ErrorBlackBoxEngine(MagicMock(), vsa, MagicMock(), sandbox=MagicMock(), concept_cortex=cortex)
    try:
        yield vsa, cortex, blackbox
    finally:
        cortex.close()


@pytest.mark.parametrize("pid_after, ncd, hwnd, expected", [
    (20, 0.4, 8, "ABRIU_JANELA_NOVA"), (10, 0.4, 7, "MUDOU_ESTADO_INTERNO"),
    (10, 0.2, 7, "NADA"), (10, 0.0, 7, "NADA"),
    (10, None, 7, "NADA"), (20, 0.4, 0, "NADA"), (10, float("nan"), 7, "NADA"),
])
def test_classification_uses_observed_pid_hwnd_ncd(pid_after, ncd, hwnd, expected):
    verifier = CyberneticVerifier(capture_fn=lambda: b"state")
    assert verifier.classificar_tipo_mudanca({"pid": 10, "hwnd": 7},
        {"pid": pid_after, "hwnd": hwnd, "ncd_real": ncd}) == expected


def test_negative_exemplar_preserves_positive_and_stays_complex(learning):
    vsa, cortex, _ = learning
    positive, negative = vsa.generate_vector("positive"), vsa.generate_vector("negative")
    cortex.learn_exemplar(positive.astype(np.complex128), "BOTAO_TESTE", True)
    before = cortex.invariants_cache["BOTAO_TESTE"].copy()
    cortex.learn_exemplar(negative, "BOTAO_TESTE", False)
    np.testing.assert_array_equal(cortex.invariants_cache["BOTAO_TESTE"], before)
    assert cortex.negative_cache["BOTAO_TESTE"].dtype == np.complex64
    np.testing.assert_allclose(cortex.negative_cache["BOTAO_TESTE"], negative, atol=1e-6)
    assert cortex._conn.execute("SELECT exemplar_count, failure_count FROM concept_invariants WHERE concept_key = 'BOTAO_TESTE'").fetchone() == (1, 1)


@pytest.mark.parametrize("vector", [np.ones(64), np.ones(2, dtype=complex),
                                     np.zeros(64, dtype=complex), np.full(64, complex(float("nan"), 0))])
def test_invalid_exemplars_are_not_persisted(learning, vector):
    _, cortex, _ = learning
    with pytest.raises(ValueError):
        cortex.learn_exemplar(vector, "INVALID", True)
    assert cortex._conn.execute("SELECT 1 FROM concept_invariants WHERE concept_key = 'INVALID'").fetchone() is None


def test_negative_only_prototype_rehydrates_as_negative(learning):
    vsa, cortex, _ = learning
    vector = vsa.generate_vector("non_button")
    cortex.learn_exemplar(vector, "BOTAO_NADA", False)
    assert "BOTAO_NADA" not in cortex.invariants_cache
    assert cortex._conn.execute("SELECT exemplar_count, failure_count FROM concept_invariants WHERE concept_key='BOTAO_NADA'").fetchone() == (0, 1)
    restored = ConceptCortex(vsa, MagicMock(), db_path=cortex.db_path, dim=64)
    try:
        assert "BOTAO_NADA" not in restored.invariants_cache
        np.testing.assert_allclose(restored.negative_cache["BOTAO_NADA"], vector, atol=1e-6)
    finally:
        restored.close()


@pytest.mark.parametrize("verified, ncd, pid_after, change, prototype_success", [
    (1, 0.4, 10, "MUDOU_ESTADO_INTERNO", True),
    (1, 0.4, 20, "ABRIU_JANELA_NOVA", True),
    (0, 0.0, 10, "NADA", False),
    (1, 0.1, 10, "NADA", False),
    (0, 0.4, 10, "MUDOU_ESTADO_INTERNO", None),
])
def test_click_pipeline_learns_from_verifier_and_audits_sqlite(learning, verified, ncd, pid_after, change, prototype_success):
    vsa, cortex, blackbox = learning
    engine = object.__new__(CausalTrajectoryEngine)
    engine.vsa, engine.concept_cortex, engine.blackbox = vsa, cortex, blackbox
    engine.pdag = MagicMock()
    engine.verifier = CyberneticVerifier(capture_fn=lambda: b"state")
    engine.ctx_engine = MagicMock()
    before = {"pid": 10, "hwnd": 7, "process_name": "canvas.exe"}
    after = {"pid": pid_after, "hwnd": 7 if pid_after == 10 else 8, "process_name": "canvas.exe"}
    engine.ctx_engine.capture_foreground_context.side_effect = [before, after]
    engine.bridge = SimpleNamespace(dispatch=AsyncMock(return_value=SimpleNamespace(status="completed", result=True)))
    step = {"acao": "CLICK", "x": 12, "y": 34, "target": "Salvar"}
    async def action():
        await engine._executar_passo_individual(step)
    with patch.object(CyberneticVerifier, "snapshot_pids", return_value={10}), \
         patch.object(CyberneticVerifier, "measure_collapse", return_value=(verified, 1.0, "", pid_after if verified else None, ncd, 0.03)):
        result = asyncio.run(engine.execute_subgoal("click_probe", action,
            contract={"expects_new_pid": False, "min_ncd": 0.03}, click_target=engine._click_target_for_step(step),
            step=step, intent="clique em Salvar"))
    assert result["click_event"]["change_type"] == change
    assert result["click_event"]["prototype_success"] is prototype_success
    import hashlib
    engine.pdag.record_transition.assert_called_once()
    assert engine.pdag.record_transition.call_args.args == (
        hashlib.sha256(b"state").hexdigest()[:16], "click_probe",
        hashlib.sha256(b"state").hexdigest()[:16], verified, ncd, "canvas.exe")
    metadata = engine.pdag.record_transition.call_args.kwargs
    assert metadata["intent"] == "clique em Salvar"
    import json
    assert json.loads(metadata["steps_json"])["executed_step"] == step
    assert metadata["expected_delta"] == 0.03
    row = cortex._conn.execute("SELECT element, app_name, change_type, ncd_real, verified, prototype_success FROM click_audit").fetchone()
    assert row == ("Salvar", "canvas.exe", change, ncd, verified, None if prototype_success is None else int(prototype_success))
    concept = f"ELEMENTO_{change}"
    if prototype_success is True:
        vector = vsa.encode_compositional(action="CLICK", target="Salvar", param=change, context="canvas.exe|")
        np.testing.assert_allclose(cortex.invariants_cache[concept], vector, atol=1e-6)
    elif prototype_success is False:
        assert concept in cortex.negative_cache and concept not in cortex.invariants_cache
    else:
        assert concept not in cortex.invariants_cache and concept not in cortex.negative_cache


def test_blackbox_does_not_invent_negative_evidence(learning):
    vsa, cortex, blackbox = learning
    assert not blackbox.learn_failed_click(vsa.generate_vector("unknown"), "BOTAO_NADA",
                                          {"lambda_obs": 0, "ncd_real": None, "expected_delta": 0.03})
    assert "BOTAO_NADA" not in cortex.negative_cache


def test_ui_protocol_passes_coordinate_identity_to_verified_click():
    vision, context = MagicMock(), MagicMock()
    state = {"pid": 10, "hwnd": 7, "window_rect": (0, 0, 100, 100), "process_name": "canvas.exe"}
    vision.capture_ui_observation.return_value = (None, (0, 0, 100, 100), state)
    vision.describe_ui_with_protocol.side_effect = [
        {**parse_ui_action("Action: click(start_box='(12,34)')"), "image_size": (100, 100)},
        parse_ui_action("Action: finished(content='observed')"),
    ]
    vision.protocol_point_to_screen.return_value = (12, 34)
    context.capture_foreground_context.return_value = state
    trajectory = SimpleNamespace(bridge=SimpleNamespace(dispatch=AsyncMock(return_value=SimpleNamespace(status="completed", result=True))))
    async def measure(**kwargs):
        assert kwargs["click_target"] == {"element": "xy(12,34)", "x": 12, "y": 34}
        await kwargs["action_fn"]()
        return {"lambda_obs": 1, "ncd_real": 0.4}
    trajectory.execute_subgoal = AsyncMock(side_effect=measure)
    controller = UIProtocolController(vision, trajectory, context)
    assert asyncio.run(controller.run_task("click Salvar", goal_check=lambda: True))["status"] == "CONCLUIDO"
