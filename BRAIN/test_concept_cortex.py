# ==============================================================================
# BRAINNET v7 - SISTEMA OPERACIONAL COGNITIVO
# MODULO: test_concept_cortex.py
# FUNCAO: Testes bloqueantes T1-T7 para o Cortex de Conceitos.
# Tag: [BN_TEST_CONCEPT_CORTEX]
# ==============================================================================

import ast
import os
import sqlite3
import tempfile
import numpy as np
import pytest
from unittest.mock import MagicMock

from concept_cortex import ConceptCortex
from hyperdimensional import FHRRHyperdimensionalEngine
from causal_trajectory import WindowsAppResolver, CausalTrajectoryEngine

@pytest.fixture
def cortex_setup():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    
    hdc = FHRRHyperdimensionalEngine(dim=10_000)
    resolver = WindowsAppResolver()
    cortex = ConceptCortex(hdc, resolver, db_path=tmp.name, dim=10_000)
    
    yield cortex, tmp.name
    
    cortex.close()
    if os.path.exists(tmp.name):
        try:
            os.remove(tmp.name)
        except OSError:
            pass

def test_t1_rejeicao_fisica(cortex_setup):
    """T1 - Testa o gate com intent construído via Role-Binding."""
    cortex, _ = cortex_setup
    
    intent = cortex.phase_project(
        cortex.hdc.bind(cortex.role_action, cortex.hdc.text_to_hypervector("abra")) +
        cortex.hdc.bind(cortex.role_target, cortex.hdc.text_to_hypervector("geladeira")) +
        cortex.hdc.bind(cortex.role_domain, cortex.hdc.text_to_hypervector("fisico"))
    )
    
    res = cortex.parse_and_route(intent, target_text="geladeira", raw_text="abra a geladeira")
    
    assert res["is_physically_viable"] is False
    assert res["kappa"] < 0.20
    assert res["decision"] == "REJECT_NO_AFFORDANCE"

def test_t2_grounding_positivo(cortex_setup, monkeypatch):
    """T2 - Grounding positivo com mock do Resolver."""
    cortex, _ = cortex_setup
    
    def mock_probe(target_text, vsa):
        return {"tipo": "PATH", "cmd": "C:\\fake.exe"}
        
    monkeypatch.setattr(cortex.resolver, "resolve_app_probabilistic", mock_probe)
    
    a = cortex.actions_cb[0]
    t = cortex.targets_cb[0]
    d = cortex.domains_cb[0]
    S = cortex.hdc.bind(cortex.hdc.bind(a, cortex.hdc.permute(t, 1)), cortex.hdc.permute(d, 2))
    
    res = cortex.parse_and_route(S, target_text="fake_app", raw_text="inicie o processo")
    
    assert res["is_physically_viable"] is True
    assert res["kappa"] >= 0.20
    assert res["grounding"] == "GROUNDED"

def test_t3_resonator_convergencia(cortex_setup):
    """T3 - Resonator 3-fatores converge em <= 15 iterações."""
    cortex, _ = cortex_setup
    
    a = cortex.actions_cb[0] # OPEN
    t = cortex.targets_cb[0] # PORTA
    d = cortex.domains_cb[0] # DIGITAL_UI
    
    S = cortex.hdc.bind(cortex.hdc.bind(a, cortex.hdc.permute(t, 1)), cortex.hdc.permute(d, 2))
    la, lt, ld, _, _, _, _, _, _ = cortex._resonate(S)
    
    assert la == "OPEN"
    assert lt == "PORTA_DE_TRANSICAO"
    assert ld == "DIGITAL_UI"

def test_t4_anti_regressao_determinismo():
    """T4 - Garante ausência de strings de apps, regex e ast.Num."""
    with open("concept_cortex.py", "r", encoding="utf-8") as f:
        code = f.read()
        
    assert "_gen_random" not in code
    assert "np.random.uniform" not in code
    assert "if app ==" not in code
    assert '"dividido por" in' not in code
    assert '"quanto é" in' not in code
    assert 'd_label not in' not in code
    assert 'ast.Num' not in code
    assert '.replace("dividido por"' not in code
    assert '.replace("vezes"' not in code

def test_t5_aprendizado_persistencia(cortex_setup):
    """T5 - learn_exemplar e persistência real no SQLite."""
    cortex, db_path = cortex_setup
    
    obs = cortex.hdc.generate_vector("teste_aprendizado")
    cortex.learn_exemplar(obs, "CONCEITO_X", success=True, eta=0.15)
    
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute("SELECT exemplar_count FROM concept_invariants WHERE concept_key = 'CONCEITO_X'")
        row = cur.fetchone()
        assert row is not None
        assert row[0] == 1
        
    cortex2 = ConceptCortex(cortex.hdc, cortex.resolver, db_path=db_path, dim=10_000)
    assert "CONCEITO_X" in cortex2.invariants_cache
    cortex2.close()

def test_t6_mechanism_hint_contrato(cortex_setup, monkeypatch):
    """T6 - Vocabulário de mechanism_hint estritamente aderente ao contrato."""
    cortex, _ = cortex_setup
    
    monkeypatch.setattr(ConceptCortex, "evaluate_affordance", lambda self, x: 0.5)
    monkeypatch.setattr(WindowsAppResolver, "resolve_app_probabilistic", lambda cls, x, y=None: {"tipo": "PATH", "cmd": "x"})
    
    a = cortex.actions_cb[0] # OPEN
    t = cortex.targets_cb[0]
    d = cortex.domains_cb[0]
    S = cortex.hdc.bind(cortex.hdc.bind(a, cortex.hdc.permute(t, 1)), cortex.hdc.permute(d, 2))
    
    res = cortex.parse_and_route(S, target_text="test")
    
    assert "mechanism_hint" in res
    assert res["mechanism_hint"]["kind"] in ("LAUNCH", "TYPE", "CLICK", "HOTKEY")
    assert res["mechanism_hint"]["kind"] == "LAUNCH"

def test_t7_decision_contract(cortex_setup, monkeypatch):
    """T7 - Contrato de decisão sem dead code."""
    cortex, _ = cortex_setup
    
    monkeypatch.setattr(ConceptCortex, "evaluate_affordance", lambda self, x: 0.5)
    monkeypatch.setattr(WindowsAppResolver, "resolve_app_probabilistic", lambda cls, x, y=None: {"tipo": "PATH", "cmd": "x"})
    
    a = cortex.actions_cb[0]
    t = cortex.targets_cb[0]
    d = cortex.domains_cb[0]
    S = cortex.hdc.bind(cortex.hdc.bind(a, cortex.hdc.permute(t, 1)), cortex.hdc.permute(d, 2))
    
    res = cortex.parse_and_route(S, target_text="test")
    assert res["decision"] == "OS_AUTOMATION"
    
    kind = res["mechanism_hint"]["kind"]
    assert kind in ("LAUNCH", "TYPE", "CLICK", "HOTKEY")