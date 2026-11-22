"""Regressoes da Fase 1: posterior Beta, migracao e reward factual."""
import asyncio
import sqlite3
from unittest.mock import MagicMock

import numpy as np
import pytest

from pdag_engine import MyelinatedPDAGEngine
from cybernetic_verifier import CyberneticVerifier
from causal_trajectory import CausalTrajectoryEngine


def test_alpha_beta_myelination_and_reload(tmp_path):
    path = str(tmp_path / "posterior.db")
    engine = MyelinatedPDAGEngine(path, max_nodes=4, dim=8)
    try:
        for n in range(1, 5):
            _, _, myelin = engine.update_hebbian("ctx", 1, 10.0, 0.0)
            idx = engine.id_to_index["ctx"]
            assert engine.alpha[idx] == n + 0.5
            assert engine.beta[idx] == 0.5
            assert myelin == (n == 4)
            print(f"sucesso={n} alpha={engine.alpha[idx]:g} beta={engine.beta[idx]:g} "
                  f"posterior={engine.alpha[idx] / (engine.alpha[idx] + engine.beta[idx]):.2f} mielina={myelin}")
        assert engine.flush_pending_writes()
    finally:
        engine.close()
    engine = MyelinatedPDAGEngine(path, max_nodes=4, dim=8)
    try:
        idx = engine.id_to_index["ctx"]
        assert (engine.alpha[idx], engine.beta[idx]) == (4.5, 0.5)
        assert engine.is_myelinated[idx]
        _, _, myelin = engine.update_hebbian("ctx", 0, 1.0, 0.0)
        assert (engine.alpha[idx], engine.beta[idx]) == (4.5, 1.5)
        assert not myelin
        assert engine.flush_pending_writes()
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT alpha, beta FROM pdag_nodes").fetchone() == (4.5, 1.5)
    finally:
        engine.close()


def test_alpha_beta_legacy_migration(tmp_path):
    path = str(tmp_path / "legacy.db")
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE pdag_nodes (
            context_key TEXT PRIMARY KEY, intent TEXT NOT NULL, pipeline_spec TEXT NOT NULL,
            phase_blob BLOB NOT NULL, weight REAL NOT NULL DEFAULT 1.0,
            consecutive_successes INTEGER NOT NULL DEFAULT 0,
            is_myelinated INTEGER NOT NULL DEFAULT 0, last_active REAL NOT NULL,
            created_at REAL NOT NULL)""")
        conn.execute("INSERT INTO pdag_nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     ("legacy", "", '{}', np.ones(8, dtype=np.complex64).tobytes(), 2.0, 3, 1, 1.0, 1.0))
    for _ in range(2):
        engine = MyelinatedPDAGEngine(path, max_nodes=4, dim=8)
        try:
            idx = engine.id_to_index["legacy"]
            assert (engine.alpha[idx], engine.beta[idx]) == (3.5, 0.5)
            assert not engine.is_myelinated[idx]
        finally:
            engine.close()


def test_verifier_returns_real_ncd_on_timeout(monkeypatch):
    verifier = CyberneticVerifier(capture_fn=lambda: b"same")
    monkeypatch.setattr(CyberneticVerifier, "snapshot_pids", lambda self: set())
    result = verifier.measure_collapse(set(), b"same", b"same", timeout_sec=-1, expected_delta=0.4)
    assert result[0] == 0
    assert result[4:] == (0.0, 0.4)


@pytest.mark.parametrize("factual", [0, 1])
def test_reward_is_independent_of_factual_success(factual):
    engine = object.__new__(CausalTrajectoryEngine)
    engine.ctx_engine, engine.pdag = MagicMock(), MagicMock()
    engine.ctx_engine.capture_foreground_context.return_value = {"process_name": "test.exe"}
    engine.verifier = MagicMock(ncd_threshold=0.2)
    engine.verifier.capture_state_bytes.return_value = b"screen"
    engine.verifier.measure_collapse.return_value = (factual, 1.0, "", None, 0.3, 0.5)

    async def action():
        pass

    result = asyncio.run(engine.execute_subgoal("ctx", action, expected_ncd=0.5))
    assert result["reward"] == pytest.approx(-0.04)
    assert result["lambda_obs"] == factual
    assert result["ncd_real"] == 0.3
    assert result["expected_delta"] == 0.5
    assert engine.verifier.measure_collapse.call_args.kwargs["expected_delta"] == 0.5


def test_thompson_explores_compatible_routes(tmp_path):
    engine = MyelinatedPDAGEngine(str(tmp_path / "sampling.db"), max_nodes=4, dim=8)
    try:
        for key in ("route_a", "route_b", "incompatible"):
            for _ in range(4):
                engine.update_hebbian(key, 1, 10.0, 0.0, pipeline={"passos": [{"route": key}]})
        engine.phase_matrix[0] = np.ones(8, dtype=np.complex64)
        engine.phase_matrix[1] = np.exp(1j * np.arccos(0.8))
        engine.phase_matrix[2] = np.exp(1j * np.arccos(0.6))
        assert engine.flush_pending_writes()
        vsa = MagicMock()
        vsa.text_to_hypervector.return_value = np.ones(8, dtype=np.complex64)
        engine._rng = MagicMock()
        engine._rng.beta.side_effect = [np.array([0.1, 0.9]), np.array([0.9, 0.1])]
        first = engine.find_myelinated_path("new_context", vsa)
        second = engine.find_myelinated_path("new_context", vsa)
        assert first["passos"][0]["route"] == "route_b"
        assert second["passos"][0]["route"] == "route_a"
        assert first["__meta__"]["source"] == "ram_cache_thompson"
        assert engine.phase_matrix.dtype == np.complex64
    finally:
        engine.close()


def test_verifier_runs_outside_event_loop_thread():
    import threading
    main_thread = threading.get_ident()
    threads = []
    engine = object.__new__(CausalTrajectoryEngine)
    engine.ctx_engine, engine.pdag = MagicMock(), MagicMock()
    engine.ctx_engine.capture_foreground_context.return_value = {"process_name": "test.exe"}
    engine.verifier = MagicMock(ncd_threshold=0.2)
    engine.verifier.capture_state_bytes.return_value = b"screen"

    def measure(**kwargs):
        threads.append(threading.get_ident())
        return (0, 1.0, "SENSOR_FALHOU", None, 0.0, 0.2)

    engine.verifier.measure_collapse.side_effect = measure

    async def action():
        pass

    asyncio.run(engine.execute_subgoal("ctx", action))
    assert threads and threads[0] != main_thread


def test_kernel_boot_wires_one_cortex_and_real_trajectory(monkeypatch):
    import ast
    import inspect
    import textwrap
    import BRAINNET as module

    tree = ast.parse(textwrap.dedent(inspect.getsource(module.BrainnetKernel.__init__)))
    keep = {"FHRRHyperdimensionalEngine", "CausalTrajectoryEngine", "CyberneticVerifier", "MetacognitionEngine"}
    constructors = {node.func.id for node in ast.walk(tree)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id[0].isupper()}
    for name in constructors - keep:
        monkeypatch.setattr(module, name, MagicMock())
    kernel = module.BrainnetKernel()
    assert isinstance(kernel.trajectory_engine, CausalTrajectoryEngine)
    assert kernel.trajectory_engine.verifier is kernel.verifier
    assert isinstance(kernel.metacognition, module.MetacognitionEngine)
    module.ConceptCortex.assert_called_once()
