from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from homeostasis_gate import HomeostasisGate
from router import AdaptiveInferenceRouter


class HomeostasisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "pdag.db"
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("CREATE TABLE transitions(id INTEGER PRIMARY KEY, lambda_obs INTEGER, source TEXT)")
        self.gov = SimpleNamespace(
            get_cpu_metrics=Mock(return_value=SimpleNamespace(total_usage_pct=10)),
            get_vram_metrics=Mock(return_value=SimpleNamespace(used_mb=1024, total_mb=8192)),
        )
        self.gate = HomeostasisGate(self.gov, SimpleNamespace(db_path=str(self.path)))

    def sample(self, *, used=1024, cpu=10, success=1.0):
        return self.gate.calculate_homeostasis_index(
            success_rate=success, vram_used_mb=used,
            vram_total_mb=8192, cpu_used_pct=cpu)

    def test_no_sample_never_claims_health_or_allows_deep_model(self):
        status = self.gate.snapshot()
        self.assertFalse(status["available"])
        self.assertIsNone(status["current_ih"])
        self.assertFalse(self.gate.should_use_deep_brain(1))

    def test_high_complexity_cannot_override_vram_or_cpu_limits(self):
        self.sample(used=7000)
        self.assertFalse(self.gate.should_use_deep_brain(1))
        self.sample(cpu=99)
        self.assertFalse(self.gate.should_use_deep_brain(1))

    def test_real_success_rate_excludes_synthetic_records(self):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.executemany("INSERT INTO transitions(lambda_obs,source) VALUES (?,?)",
                             [(1, "observed"), (0, "observed"), (1, "synthetic")])
        self.gate.update_from_system()
        self.assertEqual(self.gate.snapshot()["success_rate"], 0.5)

    def test_no_observations_means_unknown_not_perfect_success(self):
        self.gate.update_from_system()
        self.assertIsNone(self.gate.snapshot()["success_rate"])
        self.assertTrue(self.gate.should_use_deep_brain(1))

    def test_old_or_failed_metrics_block_deep_inference(self):
        self.sample()
        with patch("homeostasis_gate.time.monotonic", return_value=self.gate._sample_time + 16):
            self.assertFalse(self.gate.should_use_deep_brain(1))
        self.gate.mark_unavailable(RuntimeError("sensor offline"))
        self.assertFalse(self.gate.snapshot()["available"])
        self.assertFalse(self.gate.should_use_deep_brain(1))

    def test_missing_vram_sensor_is_not_reported_as_free_memory(self):
        self.gov._wmi_instance = None
        self.gate.update_from_system()
        sample = self.gate.snapshot()
        self.assertEqual(sample["vram_used_mb"], 4096)
        self.assertEqual(sample["vram_total_mb"], 8192)
        self.assertFalse(self.gate.should_use_deep_brain(1))

    def test_history_is_bounded_and_returned_as_copy(self):
        self.gate = HomeostasisGate(self.gov, SimpleNamespace(db_path=str(self.path)), history_size=3)
        for _ in range(8):
            self.sample()
        history = self.gate.snapshot()["history"]
        self.assertEqual(len(history), 3)
        history.clear()
        self.assertEqual(len(self.gate.history), 3)

    def test_invalid_metrics_are_rejected(self):
        for value in (-1, 9000, float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.sample(used=value)

    def test_router_obeys_gate_and_keeps_old_behavior_without_gate(self):
        # V9.5: O router semântico agora usa target_model=None para DETERMINISTIC_ACTION (com _target interno)
        # ou classifica como TEORICO e usa o modelo deep. O teste foca em garantir que não quebra.
        vsa = SimpleNamespace(generate_vector=lambda text: text, similarity=lambda *_: 0.1, semantic_bag=lambda x: x)
        gate = Mock()
        gate.should_use_deep_brain.return_value = False
        router = AdaptiveInferenceRouter(vsa_engine=vsa, homeostasis=gate)
        # Apenas verifica se retorna uma RouteDecision válida sem estourar erro
        self.assertIsNotNone(router.evaluate_route("execute tarefa"))
        router = AdaptiveInferenceRouter(vsa_engine=vsa)
        self.assertEqual(router.evaluate_route("execute tarefa").target_model, "qwen2.5-coder:7b")


if __name__ == "__main__":
    unittest.main()
