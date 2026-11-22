import ast
import json
import os
import tempfile
from unittest.mock import MagicMock, AsyncMock
import pytest
import numpy as np

from BRAINNET import BrainnetBridge, BrainnetKernel
from concept_cortex import ConceptCortex
from causal_trajectory import CausalTrajectoryEngine

@pytest.fixture
def kernel_bridge(monkeypatch):
    kernel = MagicMock()
    kernel.vsa = MagicMock()
    kernel.vsa.dim = 10_000
    
    kernel.vsa.text_to_hypervector.side_effect = lambda x: np.ones(10_000, dtype=np.complex64)
    kernel.vsa.bind.side_effect = lambda a, b: a * b
    kernel.vsa.permute.side_effect = lambda v, shift: np.roll(v, shift)
    
    kernel.concept_cortex = MagicMock()
    
    kernel.pdag = MagicMock()
    kernel.pdag.db_path = ":memory:"  # Banco em memória para testes

    kernel.trajectory_engine = MagicMock()
    kernel.trajectory_engine.executar_trajetoria_completa = AsyncMock(return_value={"status": "CONCLUIDO", "tempo_total_ms": 12})

    bridge = BrainnetBridge(kernel)
    return bridge, kernel

def test_t1_extract_roles_via_schema(monkeypatch, kernel_bridge):
    bridge, _ = kernel_bridge
    
    def mock_urlopen(req, timeout):
        class MockResponse:
            def read(self):
                return json.dumps({"response": '{"action": "OPEN", "target": "brave", "domain": "DIGITAL_UI"}'}).encode("utf-8")
            def __enter__(self): return self
            def __exit__(self, *args): pass
        return MockResponse()

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
    
    roles = bridge._extract_roles_via_schema("abra o brave")
    
    assert roles["action"] == "OPEN"
    assert roles["target"] == "brave"
    assert roles["domain"] == "DIGITAL_UI"
    assert "error" not in roles

def test_t2_extract_theoretical(monkeypatch, kernel_bridge):
    bridge, _ = kernel_bridge
    
    def mock_urlopen(req, timeout):
        class MockResponse:
            def read(self):
                return json.dumps({"response": '{"action": null, "target": null, "domain": "LOGICAL_MATH"}'}).encode("utf-8")
            def __enter__(self): return self
            def __exit__(self, *args): pass
        return MockResponse()

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
    
    roles = bridge._extract_roles_via_schema("o que é física de partículas?")
    
    assert roles["action"] is None
    assert roles["target"] is None
    assert roles["domain"] == "LOGICAL_MATH"

def test_t3_invalid_json(monkeypatch, kernel_bridge):
    bridge, _ = kernel_bridge
    
    def mock_urlopen(req, timeout):
        class MockResponse:
            def read(self):
                return json.dumps({"response": 'Isso não é um JSON válido'}).encode("utf-8")
            def __enter__(self): return self
            def __exit__(self, *args): pass
        return MockResponse()

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)
    
    roles = bridge._extract_roles_via_schema("comando aleatorio")
    
    assert roles["target"] is None
    assert "error" in roles




def test_t7_ast_integrity():
    """T7 - Garante ausência de regex e strings de app APENAS nos novos métodos."""
    with open("BRAINNET.py", "r", encoding="utf-8") as f:
        code = f.read()
        
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in ("_extract_roles_via_schema", "_build_intent_phasor", "_dispatch_via_concept_cortex"):
            func_code = ast.unparse(node)
            assert "re.match" not in func_code
            assert "re.search" not in func_code
            assert "brave" not in func_code
            assert "chrome" not in func_code
            assert ".exe" not in func_code

            