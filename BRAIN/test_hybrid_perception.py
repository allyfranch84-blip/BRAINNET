"""Hybrid hypotheses are bounded, grounded and never execute during tests."""
import asyncio
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from causal_trajectory import CausalTrajectoryEngine, _located_element, _visual_click
from concept_cortex import ConceptCortex
from execution_authority import background_only
from hyperdimensional import FHRRHyperdimensionalEngine
from vision_eye import RealVisionEngine


def engine_fixture(ocr=None, score=.8):
    engine = CausalTrajectoryEngine.__new__(CausalTrajectoryEngine)
    frame = Image.new("RGB", (200, 100), "white")
    ctx = {"hwnd": 7, "process_name": "notepad.exe", "title": "Editor"}
    engine.ctx_engine = SimpleNamespace(capture_foreground_context=MagicMock(return_value=ctx))
    engine.vision_eye = SimpleNamespace(
        encontrar_elemento_por_texto=MagicMock(return_value=ocr),
        capture_ui_observation=MagicMock(return_value=(frame, (-200, 0, 0, 100), ctx)),
        propor_candidatos_visuais=MagicMock(return_value=[{"x": 100, "y": 50, "rotulo": "lupa"}]),
        descrever_elemento_visual=MagicMock(return_value="Lupa cinza para pesquisa"),
        protocol_point_to_screen=RealVisionEngine.protocol_point_to_screen)
    engine.concept_cortex = SimpleNamespace(deduzir_funcao_visual=MagicMock(return_value={"encontrado": score > .4, "similaridade": score}))
    engine.bridge = SimpleNamespace(dispatch=AsyncMock(return_value=SimpleNamespace(status="completed", result=True)))
    engine.pdag = MagicMock()
    engine.vsa = MagicMock()
    return engine


def test_ocr_success_never_calls_vlm():
    engine = engine_fixture(ocr=(20, 30))
    assert asyncio.run(engine._executar_primitiva("LOCATE_VISUAL", {"target": "pesquisa"})) == (20, 30)
    engine.vision_eye.propor_candidatos_visuais.assert_not_called()
    engine.bridge.dispatch.assert_not_called()


def test_visual_fallback_describes_roi_and_scores_context():
    engine = engine_fixture()
    async def run():
        point = await engine._executar_primitiva("LOCATE_VISUAL", {"target": "pesquisa"})
        assert point == (-100, 50)
        observed = _located_element.get()
        assert observed[4]["description"] == "Lupa cinza para pesquisa"
        await engine._executar_primitiva("CLICK", {"target": "pesquisa"})
    asyncio.run(run())
    assert engine.vision_eye.descrever_elemento_visual.call_args.args[0].size == (96, 96)
    engine.concept_cortex.deduzir_funcao_visual.assert_called_once_with("Lupa cinza para pesquisa", "pesquisa", "notepad.exe|Editor")
    assert engine.bridge.dispatch.await_count == 1
    engine.pdag.record_execution.assert_not_called()  # No verifier, no learned route.


@pytest.mark.parametrize("score", [.4, .1])
def test_weak_association_does_not_click(score):
    engine = engine_fixture(score=score)
    with pytest.raises(RuntimeError, match="limiar"):
        asyncio.run(engine._executar_primitiva("LOCATE_VISUAL", {"target": "pesquisa"}))
    engine.bridge.dispatch.assert_not_called()


def test_no_candidate_has_no_default_coordinates():
    engine = engine_fixture()
    engine.vision_eye.propor_candidatos_visuais.return_value = []
    with pytest.raises(RuntimeError, match="candidato"):
        asyncio.run(engine._executar_primitiva("LOCATE_VISUAL", {"target": "pesquisa"}))
    engine.vision_eye.descrever_elemento_visual.assert_not_called()


def test_first_candidate_is_only_hypothesis_and_same_failed_point_is_excluded():
    engine = engine_fixture()
    with pytest.raises(RuntimeError, match="repete"):
        asyncio.run(engine._executar_primitiva("LOCATE_VISUAL", {"target": "pesquisa", "force_vlm": True, "exclude_point": (-100, 50)}))
    engine.vision_eye.encontrar_elemento_por_texto.assert_not_called()
    engine.bridge.dispatch.assert_not_called()


@pytest.mark.parametrize("change", ["frame", "focus", "rect"])
def test_visual_observation_rechecked_before_click(change):
    engine = engine_fixture()
    async def run():
        await engine._executar_primitiva("LOCATE_VISUAL", {"target": "pesquisa"})
        frame, rect, ctx = engine.vision_eye.capture_ui_observation.return_value
        frame = Image.new("RGB", frame.size, "black") if change == "frame" else frame
        rect = (0, 0, 200, 100) if change == "rect" else rect
        ctx = dict(ctx, hwnd=8) if change == "focus" else ctx
        engine.vision_eye.capture_ui_observation.return_value = (frame, rect, ctx)
        with pytest.raises(RuntimeError, match="expirou"):
            await engine._executar_primitiva("CLICK", {"target": "pesquisa"})
    asyncio.run(run())
    engine.bridge.dispatch.assert_not_called()


def test_background_visual_click_blocked():
    engine = engine_fixture()
    @background_only
    async def run():
        await engine._executar_passo_individual({"p": "CLICK", "target": "pesquisa"})
    with pytest.raises(PermissionError):
        asyncio.run(run())
    engine.bridge.dispatch.assert_not_called()


def test_fhrr_context_does_not_inflate_unrelated_similarity():
    cortex = ConceptCortex.__new__(ConceptCortex)
    cortex.hdc = FHRRHyperdimensionalEngine(dim=1000)
    same = cortex.deduzir_funcao_visual("pesquisa", "pesquisa", "notepad")
    assert same["encontrado"] and same["similaridade"] > .99 and same["verificado"] is False
    unrelated = cortex.deduzir_funcao_visual("geladeira", "pesquisa", "notepad")
    assert not unrelated["encontrado"]


def test_roi_description_strict_json_and_small_image():
    with patch("context_capture.ContextCapture.capture_foreground_context", return_value={"process_name": "notepad.exe"}), \
         patch.object(RealVisionEngine, "_consultar_visual_json", return_value={"descricao": "Lupa azul para pesquisa"}) as call:
        assert RealVisionEngine().descrever_elemento_visual(Image.new("RGB", (400, 400))) == "Lupa azul para pesquisa"
    assert call.call_args.args[0].size == (256, 256)
    assert "notepad.exe" in call.call_args.args[1]


@pytest.mark.parametrize("candidate", [{"eh_botao": "true", "corresponde_alvo": True, "descricao": "lupa"},
                                      {"eh_botao": True, "corresponde_alvo": True, "descricao": ""},
                                      {"eh_botao": True, "corresponde_alvo": True, "descricao": "lupa", "exec": "anything"}])
def test_bad_vlm_candidate_rejected(candidate):
    region = {"x": 10, "y": 10, "w": 30, "h": 30, "crop": Image.new("RGB", (30, 30))}
    with patch.object(RealVisionEngine, "_consultar_visual_json", return_value=candidate), \
         patch.object(RealVisionEngine, "encontrar_regioes_de_interesse", return_value=[region]):
        with pytest.raises(ValueError):
            RealVisionEngine().propor_candidatos_visuais(Image.new("RGB", (200, 100)), "pesquisa", "notepad")


def test_visual_variant_relocates_and_contains_no_persistent_coordinates():
    engine = engine_fixture()
    evidence = {"lambda_obs": 1, "ncd_real": .2, "expected_delta": .05, "reward": -.0225}
    engine._record_visual_success({"target": "pesquisa", "context": "notepad|Editor", "description": "lupa"}, evidence)
    call = engine.pdag.record_execution.call_args.kwargs
    assert "via_icone" in call["context_key"]
    assert call["pipeline"]["passos"][0] == {"p": "LOCATE_VISUAL", "target": "pesquisa"}
    assert call["pipeline"]["passos"][1]["feedback"] == evidence
    assert all("x" not in step and "y" not in step for step in call["pipeline"]["passos"])


@pytest.mark.parametrize("observed,ncd", [(0, .8), (1, .01), (1, float("nan"))])
def test_unverified_visual_never_learns(observed, ncd):
    engine = engine_fixture()
    assert engine._record_visual_success({}, {"lambda_obs": observed, "ncd_real": ncd}) is False
    engine.pdag.record_execution.assert_not_called()


@pytest.mark.parametrize("observed,ncd,saves", [(0, .8, 0), (1, .01, 0), (1, .2, 1)])
def test_visual_learning_gated_by_actual_verifier(observed, ncd, saves):
    engine = engine_fixture()
    engine.blackbox = MagicMock()
    engine.verifier = SimpleNamespace(snapshot_pids=lambda: {3}, capture_state_bytes=lambda bbox=None: b"frame",
        measure_collapse=lambda **kwargs: (observed, 1., "failure" if not observed else "", 3, ncd, .05))
    async def action():
        _visual_click.set({"target": "pesquisa", "context": "notepad", "description": "lupa"})
        return True
    with patch.object(CausalTrajectoryEngine, "_learn_click_feedback"), \
         patch.object(CausalTrajectoryEngine, "_record_visual_success", return_value=True) as save:
        result = asyncio.run(engine.execute_subgoal("test", action, contract={"action": "CLICK", "expects_new_pid": False},
                                                   click_target={"element": "pesquisa"}))
    assert result["lambda_obs"] == observed
    assert save.call_count == saves


@pytest.mark.parametrize("retry_success", [False, True])
def test_low_ncd_retry_is_bounded_and_reverified(retry_success):
    engine = engine_fixture()
    engine.pdag.find_myelinated_path.return_value = None
    failed = {"lambda_obs": 0, "ncd_real": .01, "expected_delta": .05, "reward": -.0016, "failure_reason": "NCD baixo"}
    retry = dict(failed, lambda_obs=int(retry_success), ncd_real=.2 if retry_success else .01)
    with patch.object(CausalTrajectoryEngine, "decompor_trajetoria_cognitiva", return_value={"pipeline": [{"p": "CLICK", "target": "pesquisa"}]}), \
         patch.object(CausalTrajectoryEngine, "execute_subgoal", new=AsyncMock(side_effect=[failed, retry])) as verify, \
         patch.object(CausalTrajectoryEngine, "_executar_primitiva", new=AsyncMock()) as primitive:
        result = asyncio.run(engine.executar_trajetoria_completa("clique no botão pesquisa"))
    assert verify.await_count == 2
    primitive.assert_awaited_once_with("LOCATE_VISUAL", {"target": "pesquisa", "force_vlm": True, "exclude_point": None})
    assert result["sucesso_real"] is retry_success
