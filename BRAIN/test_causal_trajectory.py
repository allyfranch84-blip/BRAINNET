# ==============================================================================
# BRAINNET v7 - SISTEMA OPERACIONAL COGNITIVO
# MODULO: test_causal_trajectory.py
# FUNCAO: Testes bloqueantes T1-T6 com CyberneticVerifier REAL e P-DAG REAL.
# Tag: [BN_TEST_CAUSAL_TRAJECTORY]
# ==============================================================================

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time

import pytest

from causal_trajectory import CausalTrajectoryEngine
from cybernetic_verifier import CyberneticVerifier
from context_capture import ContextCapture
from perception_eye import PerceptionEye
from effector import Effector
from actuator_bridge import ActuatorBridge
from hyperdimensional import FHRRHyperdimensionalEngine
from pdag_engine import MyelinatedPDAGEngine
from shadow_simulator import ShadowSimulator

class StatefulCapture:
    """Mock apenas do framebuffer visual, simulando a mudança de pixels."""
    def __init__(self, states):
        self.states = states
        self.idx = 0

    def __call__(self):
        val = self.states[min(self.idx, len(self.states) - 1)]
        self.idx += 1
        return val

class _TestableEngine(CausalTrajectoryEngine):
    """
    Subclasse de teste para contornar o __slots__ da classe original.
    Permite sobrescrever métodos (mock) sem usar patch.object na instância.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mock_action = None
        self._mock_decomp = None

    def decompor_trajetoria_cognitiva(self, obj):
        if self._mock_decomp is not None:
            return self._mock_decomp
        return super().decompor_trajetoria_cognitiva(obj)

    async def _executar_passo_individual(self, passo):
        if self._mock_action is not None:
            return await self._mock_action(passo)
        return await super()._executar_passo_individual(passo)

def get_real_engine(capture_states):
    """Instancia o organismo real, alterando apenas o capture_fn."""
    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_db.close()

    ctx = ContextCapture()
    eye = PerceptionEye()
    eff = Effector()
    bridge = ActuatorBridge(eff, eye)
    
    # CORREÇÃO: Forçando o P-DAG e o VSA a usarem a mesma dimensão (1000) para o teste
    vsa = FHRRHyperdimensionalEngine(dim=1000) 
    pdag = MyelinatedPDAGEngine(db_path=tmp_db.name, dim=1000)
    
    shadow = ShadowSimulator(ctx, eye, vsa, pdag)
    
    verifier = CyberneticVerifier(
        capture_fn=StatefulCapture(capture_states), 
        poll_interval=0.1
    )
    
    engine = _TestableEngine(ctx, eye, eff, bridge, vsa, pdag, shadow, verifier)
    return engine, pdag, tmp_db.name

def cleanup(pdag, db_path):
    pdag.close()
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError:
            pass

# ------------------------------------------------------------------------------
# TESTES
# ------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_t1_sucesso_fisico_completo():
    """T1 - Processo real com janela, verificado pelo M_SO."""
    cap_states = [b"A"*1000, b"B"*1000]
    engine, pdag, db_path = get_real_engine(cap_states)
    
    async def mock_action(p):
        subprocess.Popen([sys.executable, "-c", "import tkinter; root=tkinter.Tk(); root.title('Test'); root.after(1500, root.destroy); root.mainloop()"])
        return True

    engine._mock_decomp = {"monologo_socratico": ["ok"], "passos": [{"acao": "ENSURE_APP"}]}
    engine._mock_action = mock_action

    try:
        res = await engine.executar_trajetoria_completa("abrir janela")
        assert res["status"] == "CONCLUIDO"
        assert res["passos_concluidos"] == "1/1"
        assert res["detalhes"] == []
    finally:
        cleanup(pdag, db_path)

@pytest.mark.asyncio
async def test_t2_falha_timeout(monkeypatch):
    """T2 - Nenhuma ação física, verifier detecta ausência de PID e NCD."""
    monkeypatch.setattr(CyberneticVerifier, "snapshot_pids", lambda self: {101})
    cap_states = [b"A"*1000, b"A"*1000]
    engine, pdag, db_path = get_real_engine(cap_states)
    
    async def mock_action(p):
        await asyncio.sleep(0.1)
        return True

    engine._mock_decomp = {"monologo_socratico": ["ok"], "passos": [{"acao": "ENSURE_APP"}]}
    engine._mock_action = mock_action

    try:
        res = await engine.executar_trajetoria_completa("abrir nada")
        assert res["status"] == "FALHA_REALIDADE"
        assert res["detalhes"]["lambda_obs"] == 0
        assert "pid=False" in res["detalhes"]["failure_reason"]
    finally:
        cleanup(pdag, db_path)

@pytest.mark.asyncio
async def test_t3_falha_ausencia_processo(monkeypatch):
    """T3 - Tela muda, mas nenhum processo novo nasce."""
    monkeypatch.setattr(CyberneticVerifier, "snapshot_pids", lambda self: {101})
    cap_states = [b"A"*1000, b"B"*1000]
    engine, pdag, db_path = get_real_engine(cap_states)
    
    async def mock_action(p):
        await asyncio.sleep(0.1)
        return True

    engine._mock_decomp = {"monologo_socratico": ["ok"], "passos": [{"acao": "ENSURE_APP"}]}
    engine._mock_action = mock_action

    try:
        res = await engine.executar_trajetoria_completa("abrir nada")
        assert res["status"] == "FALHA_REALIDADE"
        assert "pid=False" in res["detalhes"]["failure_reason"]
    finally:
        cleanup(pdag, db_path)

@pytest.mark.asyncio
async def test_t4_aborto_em_falha_intermediaria():
    """T4 - Passo 1 funciona, Passo 2 falha fisicamente, Passo 3 nunca roda."""
    cap_states = [b"A"*1000, b"B"*1000, b"B"*1000, b"B"*1000]
    engine, pdag, db_path = get_real_engine(cap_states)
    
    step_count = 0
    async def mock_action(p):
        nonlocal step_count
        step_count += 1
        if step_count == 1:
            subprocess.Popen([sys.executable, "-c", "import tkinter; root=tkinter.Tk(); root.title('Test'); root.after(1000, root.destroy); root.mainloop()"])
        await asyncio.sleep(0.1)
        return True

    engine._mock_decomp = {
        "monologo_socratico": ["ok"], 
        "passos": [{"acao": "A"}, {"acao": "B"}, {"acao": "C"}]
    }
    engine._mock_action = mock_action

    try:
        res = await engine.executar_trajetoria_completa("passo a passo")
        assert res["status"] == "FALHA_REALIDADE"
        assert res["passos_concluidos"] == "1/3"
        assert step_count == 2
    finally:
        cleanup(pdag, db_path)

@pytest.mark.asyncio
async def test_t5_excecao_em_action_fn():
    """T5 - Exceção em action_fn."""
    engine, pdag, db_path = get_real_engine([b"A"*1000, b"A"*1000])
    
    async def mock_action(p):
        raise RuntimeError("Erro simulado")
        
    engine._mock_decomp = {"monologo_socratico": ["ok"], "passos": [{"acao": "A"}]}
    engine._mock_action = mock_action

    try:
        res = await engine.executar_trajetoria_completa("abrir dummy")
        assert res["status"] == "FALHA_REALIDADE"
        assert "ACTION_EXCEPTION: RuntimeError: Erro simulado" in res["detalhes"]["failure_reason"]
    finally:
        cleanup(pdag, db_path)

@pytest.mark.asyncio
async def test_t6_fast_path_exige_verificacao_factual():
    """T6 - Uma rota mielinizada sem efeito fisico deve falhar."""
    engine, pdag, db_path = get_real_engine([b"A"*1000, b"A"*1000])
    
    pdag.record_execution(
        context_key="trajectory:rota mielinizada",
        intent="rota mielinizada",
        pipeline={"passos": [{"acao": "FOCUS_WINDOW", "app": "notepad"}]},
        reinforcement=0.85,
        vsa_engine=engine.vsa
    )
    # Mielinização forçada
    pdag.is_myelinated[pdag.id_to_index["trajectory:rota mielinizada"]] = True
    pdag.flush_pending_writes()

    step_count = 0
    async def mock_action(p):
        nonlocal step_count
        step_count += 1
        return True

    engine._mock_action = mock_action

    try:
        res = await engine.executar_trajetoria_completa("rota mielinizada")
        assert res["status"] == "FALHA_REALIDADE"
        assert "SENSOR_FALHOU" in res["detalhes"]["failure_reason"]
        assert not pdag.is_myelinated[pdag.id_to_index["trajectory:rota mielinizada"]]
        assert step_count == 1
    finally:
        cleanup(pdag, db_path)
