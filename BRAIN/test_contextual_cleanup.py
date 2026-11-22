"""Context-scoped observation lookup; never dispatches Windows actions."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from hyperdimensional import FHRRHyperdimensionalEngine
from perception_eye import PerceptionEye
import perception_eye


@pytest.fixture
def eye():
    return PerceptionEye(FHRRHyperdimensionalEngine(dim=256))


def observe(eye, change, context="canvas.exe|Documento", target="Salvar", timestamp=1):
    vector = eye.vsa.encode_compositional(action="CLICK", target=target, param=change, context=context)
    eye.vsa.register_cleanup(f"ELEMENTO_{change}|ELEM_{timestamp}|{context}|{target}", vector)
    return vector


@pytest.mark.parametrize("change,expected", [
    ("ABRIU_JANELA_NOVA", "INVOKE"), ("MUDOU_ESTADO_INTERNO", "INVOKE"), ("NADA", "UNKNOWN"),
])
def test_cleanup_recovers_observed_effect(eye, change, expected):
    observe(eye, change)
    assert eye._observed_affordance("Salvar", "canvas.exe|Documento") == expected


def test_cleanup_requires_same_context_and_element(eye):
    observe(eye, "ABRIU_JANELA_NOVA")
    assert eye._observed_affordance("Salvar", "outro.exe|Documento") == "UNKNOWN"
    assert eye._observed_affordance("Excluir", "canvas.exe|Documento") == "UNKNOWN"


def test_recent_negative_observation_overrides_old_positive(eye):
    observe(eye, "ABRIU_JANELA_NOVA")
    observe(eye, "NADA", timestamp=2)
    assert eye._observed_affordance("Salvar", "canvas.exe|Documento") == "UNKNOWN"


def test_document_control_uses_cleanup_without_dispatch(eye, monkeypatch):
    observe(eye, "ABRIU_JANELA_NOVA")
    child = SimpleNamespace(Name="Salvar", ControlTypeName="DocumentControl",
        BoundingRectangle=SimpleNamespace(left=0, top=0, right=50, bottom=50),
        GetValuePattern=lambda: None, GetInvokePattern=lambda: None,
        GetTextPattern=lambda: None, GetSelectionItemPattern=lambda: None)
    auto = SimpleNamespace(ControlFromHandle=lambda hwnd: SimpleNamespace(Exists=lambda *a: True),
                           WalkTree=lambda *a, **kw: [(child, 1)])
    monkeypatch.setattr(perception_eye, "auto", auto, raising=False)
    monkeypatch.setattr(perception_eye, "HAS_UIA_NATIVE", True)
    monkeypatch.setattr(PerceptionEye, "_window_context", lambda *a: "canvas.exe|Documento")
    monkeypatch.setattr(PerceptionEye, "get_window_bounds", lambda *a: (0, 0, 100, 100))
    assert eye.scan_window_controls(7)[0].affordance == "INVOKE"
    monkeypatch.setattr(PerceptionEye, "_window_context", lambda *a: "canvas.exe|Outro")
    assert eye.scan_window_controls(7)[0].affordance == "UNKNOWN"


def test_cortex_context_encoder_preserves_complex_phases():
    from concept_cortex import ConceptCortex
    vsa = FHRRHyperdimensionalEngine(dim=256)
    cortex = object.__new__(ConceptCortex)
    cortex.hdc = vsa
    roles = {"action": "OPEN", "target": "editor", "domain": "OS"}
    first = cortex._build_intent_phasor(roles, "editor|foco|A")
    second = cortex._build_intent_phasor(roles, "editor|minimizada|B")
    assert first.dtype == np.complex64
    assert not np.allclose(first, second)
