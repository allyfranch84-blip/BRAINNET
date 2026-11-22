"""OCR geometry and primitive composition; all actuators mocked."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image, ImageDraw, ImageFont

from causal_trajectory import CausalTrajectoryEngine, _located_element
from execution_authority import background_only
from htn_planner import compile_primitives, parse_objectives
from vision_eye import RealVisionEngine


def test_ocr_boxes_are_clipped_and_native_types():
    eye = RealVisionEngine()
    eye._ocr = MagicMock(return_value=([
        ([[-3, 2], [30, 2], [30, 20], [-3, 20]], "Salvar", 0.99),
        ([[1, 2]] * 4, "invalid", float("nan")),
    ], []))
    assert eye.extrair_texto_e_coordenadas(Image.new("RGB", (40, 30))) == [
        {"texto": "Salvar", "x": 0, "y": 2, "w": 30, "h": 18, "confianca": 0.99}]
    assert eye.last_ocr_ms >= 0
    eye._ocr.assert_called_once()


@pytest.mark.parametrize("rows,hwnd,expected", [
    ([{"texto": "Configurações", "x": 20, "y": 10, "w": 40, "h": 20, "confianca": .98}], 7, (-160, 120)),
    ([{"texto": "Configurações", "x": 20, "y": 10, "w": 40, "h": 20, "confianca": .2}], 7, None),
    ([{"texto": "Configurações", "x": 20, "y": 10, "w": 40, "h": 20, "confianca": .98}], 9, None),
    ([{"texto": "Outro", "x": 20, "y": 10, "w": 40, "h": 20, "confianca": .98}], 7, None),
])
def test_locate_normalization_offsets_and_rejection(rows, hwnd, expected):
    with patch.object(RealVisionEngine, "capture_ui_observation", return_value=(Image.new("RGB", (100, 60)), (-200, 100, -100, 160), {"hwnd": 7})), \
         patch.object(RealVisionEngine, "extrair_texto_e_coordenadas", return_value=rows), \
         patch("vision_eye.user32.GetForegroundWindow", return_value=hwnd):
        assert RealVisionEngine().encontrar_elemento_por_texto("configuracoes") == expected


def test_duplicate_labels_do_not_choose_arbitrary_button():
    row = {"texto": "Salvar", "x": 1, "y": 1, "w": 20, "h": 10, "confianca": .98}
    with patch.object(RealVisionEngine, "capture_ui_observation", return_value=(Image.new("RGB", (100, 60)), (0, 0, 100, 60), {"hwnd": 7})), \
         patch.object(RealVisionEngine, "extrair_texto_e_coordenadas", return_value=[row, dict(row, x=40)]):
        assert RealVisionEngine().encontrar_elemento_por_texto("Salvar") is None


@pytest.mark.parametrize("text,expected", [
    ("Abra o gridcraft e digite teste", [{"p": "OPEN_APP", "app": "gridcraft"}, {"p": "TYPE", "text": "teste"}]),
    ("Pesquise no brave sobre python", [{"p": "OPEN_APP", "app": "brave"}, {"p": "HOTKEY", "keys": ["ctrl", "l"]}, {"p": "TYPE", "text": "https://www.google.com/search?q=python"}, {"p": "HOTKEY", "keys": ["enter"]}]),
    ("No WhatsApp mande oi para o Davi", [{"p": "OPEN_APP", "app": "whatsapp"}, {"p": "HOTKEY", "keys": ["ctrl", "f"]}, {"p": "TYPE", "text": "Davi"}, {"p": "HOTKEY", "keys": ["enter"]}, {"p": "TYPE", "text": "oi", "target_contact": "Davi"}, {"p": "HOTKEY", "keys": ["enter"], "target_contact": "Davi"}]),
    ("Clique no botão Salvar", [{"p": "LOCATE_VISUAL", "target": "Salvar"}, {"p": "CLICK", "target": "Salvar"}]),
])
def test_primitive_compilation(text, expected):
    assert compile_primitives(parse_objectives(text), web_search="brave" in text)["pipeline"] == expected


@pytest.mark.parametrize("text", ["abra gridcraft e digite teste", "pesquise no brave sobre python",
                                 "No WhatsApp mande oi para o Davi", "Clique no botão Salvar"])
def test_htn_explicit_primitives_never_use_domain_competition(text):
    engine = CausalTrajectoryEngine.__new__(CausalTrajectoryEngine)
    with patch.object(CausalTrajectoryEngine, "_projetar_onda_de_probabilidade", side_effect=AssertionError("fallback inesperado")):
        assert engine.decompor_trajetoria_cognitiva(text)["pipeline"]


def test_open_primitive_uses_native_launcher_without_professor():
    engine = CausalTrajectoryEngine.__new__(CausalTrajectoryEngine)
    with patch.object(CausalTrajectoryEngine, "_start_menu_search", new=AsyncMock(return_value={"target_hwnd": 7})) as launch:
        assert asyncio.run(engine._executar_primitiva("OPEN_APP", {"app": "gridcraft"})) == {"target_hwnd": 7}
    launch.assert_awaited_once_with("gridcraft")


def engine_fixture():
    engine = CausalTrajectoryEngine.__new__(CausalTrajectoryEngine)
    engine.ctx_engine = SimpleNamespace(capture_foreground_context=MagicMock(return_value={"hwnd": 7}))
    engine.vision_eye = SimpleNamespace(encontrar_elemento_por_texto=MagicMock(return_value=(40, 50)))
    engine.bridge = SimpleNamespace(dispatch=AsyncMock(return_value=SimpleNamespace(status="completed", result=True)))
    return engine


def test_locate_click_consumes_observation_once():
    engine = engine_fixture()
    async def run():
        await engine._executar_primitiva("LOCATE", {"target": "Salvar"})
        assert await engine._executar_primitiva("CLICK", {"target": "Salvar"}) is True
        with pytest.raises(RuntimeError):
            await engine._executar_primitiva("CLICK", {"target": "Salvar"})
    asyncio.run(run())
    assert engine.bridge.dispatch.await_count == 1
    assert engine.bridge.dispatch.call_args.args[:2] == ("mouse_click_at", {"x": 40, "y": 50, "button": "left", "count": 1})


@pytest.mark.parametrize("change", ["focus", "expired", "target"])
def test_stale_locate_cannot_click(change):
    engine = engine_fixture()
    async def run():
        await engine._executar_primitiva("LOCATE", {"target": "Salvar"})
        if change == "focus":
            engine.ctx_engine.capture_foreground_context.return_value = {"hwnd": 9}
        elif change == "expired":
            observed = _located_element.get()
            _located_element.set((*observed[:3], observed[3] - 3))
        with pytest.raises(RuntimeError):
            await engine._executar_primitiva("CLICK", {"target": "Outro" if change == "target" else "Salvar"})
    asyncio.run(run())
    engine.bridge.dispatch.assert_not_called()


def test_background_primitive_write_blocked():
    engine = engine_fixture()
    @background_only
    async def run():
        await engine._executar_passo_individual({"p": "TYPE", "text": "never"})
    with pytest.raises(PermissionError):
        asyncio.run(run())
    engine.bridge.dispatch.assert_not_called()


def test_locate_is_observation_without_fake_ncd():
    engine = engine_fixture()
    engine.verifier = MagicMock()
    result = asyncio.run(engine.execute_subgoal("locate", AsyncMock(return_value=(1, 2)), contract={"action": "LOCATE"}))
    assert result["status"] == "OBSERVED" and result["ncd_real"] is None
    engine.verifier.measure_collapse.assert_not_called()


def test_real_ocr_cpu_smoke():
    image = Image.new("RGB", (480, 180), "white")
    ImageDraw.Draw(image).text((40, 55), "Salvar arquivo", font=ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 32), fill="black")
    rows = RealVisionEngine().extrair_texto_e_coordenadas(image)
    assert any("salvar" in row["texto"].casefold() for row in rows)
