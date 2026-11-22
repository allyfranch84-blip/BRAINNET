# ==============================================================================
# BRAINNET v7 - SISTEMA OPERACIONAL COGNITIVO
# MODULO: test_pdag_engine.py
# FUNCAO: Testes bloqueantes T1-T8 para a Plasticidade Hebbiana e P-DAG.
# Tag: [BN_TEST_PDAG]
# ==============================================================================

import os
from contextlib import closing
import tempfile
import time
import pytest

from pdag_engine import MyelinatedPDAGEngine

@pytest.fixture
def pdag():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = MyelinatedPDAGEngine(db_path=tmp.name, max_nodes=100, dim=1000)
    try:
        yield engine
    finally:
        engine.close()
        if os.path.exists(tmp.name):
            os.remove(tmp.name)

def test_t1_hebbian_pure(pdag):
    """T1: Reforço estável com latência de 1s."""
    w, s, m = pdag.update_hebbian("ctx1", lambda_obs=1, delta_t=1.0, sigma_lat=0.0)
    assert w == pytest.approx(0.75)
    assert s == 1
    assert not m

def test_t2_reg_dt_zero(pdag):
    """T2: Regularização Δt→0 (amortecedor impede explosão)."""
    w, s, m = pdag.update_hebbian("ctx2", lambda_obs=1, delta_t=0.001, sigma_lat=0.0)
    assert w == pytest.approx(0.75)
    assert s == 1

def test_t3_asymmetric_punish(pdag):
    """T3: Punição assimétrica (λ=0) gera queda drástica."""
    pdag.update_hebbian("ctx3", lambda_obs=1, delta_t=0.001, sigma_lat=0.0)
    pdag.weights[pdag.id_to_index["ctx3"]] = 2.0
    
    w, s, m = pdag.update_hebbian("ctx3", lambda_obs=0, delta_t=1.0, sigma_lat=0.0)
    assert w < 0.80
    assert s == 0
    assert not m

def test_t4_myelination_n4(pdag):
    """T4: Quatro sucessos atingem media >= 0.85 e variancia <= 0.02."""
    for _ in range(4):
        w, s, m = pdag.update_hebbian("ctx4", lambda_obs=1, delta_t=0.001, sigma_lat=0.0)
    
    assert s == 4
    assert m is True
    assert pdag.is_myelinated[pdag.id_to_index["ctx4"]] is True or pdag.is_myelinated[pdag.id_to_index["ctx4"]] == True

def test_t5_demyelination(pdag):
    """T5: Desmielinização imediata na primeira falha."""
    for _ in range(4):
        pdag.update_hebbian("ctx5", lambda_obs=1, delta_t=0.001, sigma_lat=0.0)
    
    assert pdag.is_myelinated[pdag.id_to_index["ctx5"]] == True
    
    pdag.update_hebbian("ctx5", lambda_obs=0, delta_t=1.0, sigma_lat=0.0)
    assert pdag.is_myelinated[pdag.id_to_index["ctx5"]] == False

def test_t6_ebbinghaus(pdag):
    """T6: Poda de Ebbinghaus após 90 dias sem acesso."""
    pdag.update_hebbian("ctx6", lambda_obs=1, delta_t=1.0, sigma_lat=0.0)
    
    idx = pdag.id_to_index["ctx6"]
    pdag.last_active[idx] = time.time() - (95 * 86400)
    pdag.weights[idx] = 0.04
    
    pruned = pdag.apply_ebbinghaus_decay(90.0)
    assert pruned == 1
    assert pdag.weights[idx] == 0.0

def test_t7_async_persist(pdag):
    """T7: Persistência assíncrona no SQLite (Write-Behind)."""
    import sqlite3
    pdag.update_hebbian("ctx7", lambda_obs=1, delta_t=1.0, sigma_lat=0.0)
    pdag.flush_pending_writes(2.0)
    
    with closing(sqlite3.connect(pdag.db_path)) as conn:
        cursor = conn.execute("SELECT weight FROM pdag_nodes WHERE context_key = 'ctx7'")
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == pytest.approx(0.75)

def test_t8_compat_find_path(pdag):
    """T8: Compatibilidade com causal_trajectory.py (chave 'passos')."""
    # Quatro observacoes factuais satisfazem os cortes do posterior Beta.
    pipeline = {"passos": [{"acao": "WAIT"}], "tempo_total_ms": 1.0}
    
    pdag.record_execution(
        context_key="trajectory:ctx8",
        intent="ctx8",
        pipeline=pipeline,
        reinforcement=0.85,
        vsa_engine=None
    )
    for _ in range(3):
        pdag.record_execution("trajectory:ctx8", "ctx8", pipeline, 0.85)
    
    pdag.flush_pending_writes(2.0)
    
    res = pdag.find_myelinated_path("trajectory:ctx8")
    assert res is not None
    assert "passos" in res
    assert res["passos"][0]["acao"] == "WAIT"
