"""Bottom-up RoIs, bounded VLM crops and factually gated shape memory."""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageEnhance

from causal_trajectory import CausalTrajectoryEngine
from concept_cortex import ConceptCortex
from hyperdimensional import FHRRHyperdimensionalEngine
from vision_eye import RealVisionEngine


def button_image():
    image = Image.new("RGB", (600, 400), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 30, 110, 90), outline="black", width=2)
    draw.rectangle((200, 40, 204, 44), fill="black")  # Too small.
    draw.line((200, 100, 400, 100), fill="black", width=2)  # Too thin.
    return image


def test_real_canny_filters_duplicates_and_preserves_pixels():
    image = button_image()
    before = image.tobytes()
    eye = RealVisionEngine()
    regions = eye.encontrar_regioes_de_interesse(image)
    assert len(regions) == 1
    box = regions[0]
    assert box["x"] <= 31 and box["y"] <= 31
    assert 200 <= box["w"] * box["h"] <= 50000
    assert 1 <= box["w"] / box["h"] <= 4
    assert box["crop"].size == (box["w"], box["h"])
    assert image.tobytes() == before
    assert eye.last_roi_ms >= 0


def test_blank_has_no_roi_or_vlm_call():
    eye = RealVisionEngine()
    with patch.object(RealVisionEngine, "_consultar_visual_json") as vlm:
        assert eye.propor_candidatos_visuais(Image.new("RGB", (600, 400), "white"), "pesquisa", "app") == []
    vlm.assert_not_called()


def test_roi_locator_ocr_short_circuit():
    with patch.object(RealVisionEngine, "encontrar_elemento_por_texto", return_value=(11,22)), \
         patch.object(RealVisionEngine, "propor_candidatos_visuais") as vlm:
        assert RealVisionEngine().localizar_alvo_com_roi("Salvar") == (11,22)
    vlm.assert_not_called()


@pytest.mark.parametrize("changed", [False, True])
def test_roi_locator_maps_offsets_and_rejects_changed_window(changed):
    frame = Image.new("RGB", (100,100))
    ctx = {"hwnd":7, "process_name":"app"}
    samples = [(frame,(-100,10,0,110),ctx), (frame,(-100,10,0,110),dict(ctx, hwnd=8 if changed else 7))]
    candidate = {"x":30, "y":40, "box":(20,30,40,50)}
    with patch.object(RealVisionEngine,"encontrar_elemento_por_texto",return_value=None), \
         patch.object(RealVisionEngine,"capture_ui_observation",side_effect=samples), \
         patch.object(RealVisionEngine,"propor_candidatos_visuais",return_value=[candidate]):
        assert RealVisionEngine().localizar_alvo_com_roi("Salvar") == (None if changed else (-70,50))


def regions(count=8):
    return [{"x": index*40, "y": 30, "w": 30, "h": 30, "crop": Image.new("RGB", (30, 30), "white")}
            for index in range(count)]


def test_only_five_crops_never_full_frame_reach_vlm():
    response = {"eh_botao": True, "corresponde_alvo": False, "descricao": "outro icone"}
    with patch.object(RealVisionEngine, "encontrar_regioes_de_interesse", return_value=regions()), \
         patch.object(RealVisionEngine, "_consultar_visual_json", return_value=response) as vlm:
        assert RealVisionEngine().propor_candidatos_visuais(Image.new("RGB", (1920, 1080)), "pesquisa", "app") == []
    assert vlm.call_count == 5
    assert all(call.args[0].size == (30, 30) for call in vlm.call_args_list)


def test_matching_roi_returns_native_box_and_stops_at_first_match():
    responses = [{"eh_botao": False, "corresponde_alvo": False, "descricao": "texto"},
                 {"eh_botao": True, "corresponde_alvo": True, "descricao": "lupa cinza de pesquisa"}]
    with patch.object(RealVisionEngine, "encontrar_regioes_de_interesse", return_value=regions()), \
         patch.object(RealVisionEngine, "_consultar_visual_json", side_effect=responses) as vlm:
        candidates = RealVisionEngine().propor_candidatos_visuais(Image.new("RGB", (600, 400)), "pesquisa", "app")
    assert candidates == [{"x": 55, "y": 45, "rotulo": "lupa cinza de pesquisa",
                           "descricao": "lupa cinza de pesquisa", "box": (40, 30, 70, 60)}]
    assert vlm.call_count == 2


def test_shape_fhrr_is_unit_complex_10000_and_brightness_stable():
    cortex = ConceptCortex.__new__(ConceptCortex)
    cortex.hdc = FHRRHyperdimensionalEngine(dim=10000)
    image = button_image().crop((20, 20, 120, 100))
    shape = cortex.hash_visual_para_fhrr(image)
    dimmer = cortex.hash_visual_para_fhrr(ImageEnhance.Brightness(image).enhance(.75))
    assert shape.shape == (10000,) and shape.dtype == np.complex64
    np.testing.assert_allclose(np.abs(shape), 1, atol=1e-6)
    assert cortex.hdc.similarity(shape, dimmer) > .9
    cortex.hdc.register_cleanup("FORMA_BOTAO", shape)
    assert cortex.hdc.cleanup_query(dimmer)[0] == "FORMA_BOTAO"


@pytest.mark.parametrize("success,ncd,expected", [(False,.2,0), (True,.01,0), (True,.2,1)])
def test_only_verified_click_registers_shape(success,ncd,expected):
    engine = CausalTrajectoryEngine.__new__(CausalTrajectoryEngine)
    engine.vsa, engine.pdag = MagicMock(), MagicMock()
    engine.concept_cortex = SimpleNamespace(hash_visual_para_fhrr=MagicMock(return_value=np.ones(10000, dtype=np.complex64)))
    meta = {"target": "enviar", "description": "seta", "context": "whatsapp", "roi": Image.new("RGB", (30,30))}
    feedback = {"lambda_obs": int(success), "ncd_real": ncd, "expected_delta": .05, "reward": -.01}
    engine._record_visual_success(meta,feedback)
    assert engine.vsa.register_cleanup.call_count == expected
    assert engine.concept_cortex.hash_visual_para_fhrr.call_count == expected
    assert engine.pdag.record_execution.call_count == expected
