"""Bounded, thread-safe resource budget for local inference; no actuators."""

from collections import deque
from contextlib import closing
import math
import logging
from pathlib import Path
import sqlite3
import threading
import time


logger = logging.getLogger("BRAINNET_Homeostasis")


class HomeostasisGate:
    def __init__(self, governance, pdag, *, history_size=120,
                 deep_vram_budget_mb=5120.0, max_age_seconds=15.0):
        if history_size < 1 or deep_vram_budget_mb <= 0 or max_age_seconds <= 0:
            raise ValueError("Limites de homeostase devem ser positivos")
        self.governance = governance
        self.pdag = pdag
        self.deep_vram_budget_mb = float(deep_vram_budget_mb)
        self.max_age_seconds = float(max_age_seconds)
        self._history = deque(maxlen=history_size)
        self._lock = threading.RLock()
        self._sample = None
        self._sample_time = None
        self._error = None

    @property
    def history(self):
        with self._lock:
            return tuple(self._history)

    def calculate_homeostasis_index(self, *, success_rate, vram_used_mb,
                                    vram_total_mb, cpu_used_pct):
        used, total, cpu = map(float, (vram_used_mb, vram_total_mb, cpu_used_pct))
        if not all(math.isfinite(x) for x in (used, total, cpu)):
            raise ValueError("Telemetria deve conter numeros finitos")
        if total <= 0 or not 0 <= used <= total or not 0 <= cpu <= 100:
            raise ValueError("Telemetria fora dos limites")
        success = None if success_rate is None else float(success_rate)
        if success is not None and (not math.isfinite(success) or not 0 <= success <= 1):
            raise ValueError("success_rate deve estar entre 0 e 1 ou ser None")
        free = total - used
        resource_index = min(1 - cpu / 100, free / self.deep_vram_budget_mb, 1.0)
        index = resource_index * (1.0 if success is None else 0.5 + 0.5 * success)
        with self._lock:
            self._sample = {"current_ih": index, "success_rate": success,
                            "vram_used_mb": used, "vram_total_mb": total,
                            "vram_free_mb": free, "cpu_used_pct": cpu,
                            "updated_at": time.time()}
            self._sample_time = time.monotonic()
            self._error = None
            self._history.append(index)
        return index

    def _observed_success_rate(self):
        uri = Path(self.pdag.db_path).resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=0.2)) as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(transitions)")}
            if "lambda_obs" not in columns:
                raise sqlite3.OperationalError("transitions.lambda_obs indisponivel")
            source = " AND source = 'observed'" if "source" in columns else ""
            rows = conn.execute(
                "SELECT lambda_obs FROM transitions WHERE lambda_obs IN (0, 1)"
                + source + " ORDER BY id DESC LIMIT 200"
            ).fetchall()
        return sum(row[0] for row in rows) / len(rows) if rows else None

    def update_from_system(self):
        cpu = self.governance.get_cpu_metrics()
        try:
            vram = self.governance.get_vram_metrics()
            vram_used_mb = vram.used_mb
            vram_total_mb = vram.total_mb
            if hasattr(self.governance, "_wmi_instance") and self.governance._wmi_instance is None:
                vram_used_mb = 0
                vram_total_mb = 0
        except Exception:
            vram_used_mb = 0
            vram_total_mb = 0

        # Fallback seguro para GPUs AMD (RX 580) onde o WMI falha
        if vram_used_mb <= 0 or vram_total_mb <= 0:
            logger.warning("[HOMEOSTASIS]: WMI de VRAM indisponivel. Assumindo 4096MB/8192MB para segurança.")
            vram_used_mb = 4096.0
            vram_total_mb = 8192.0

        return self.calculate_homeostasis_index(
            success_rate=self._observed_success_rate(),
            vram_used_mb=vram_used_mb, vram_total_mb=vram_total_mb,
            cpu_used_pct=cpu.total_usage_pct,
        )

    def mark_unavailable(self, error):
        with self._lock:
            self._error = str(error) or type(error).__name__

    def _available(self):
        return (self._sample is not None and self._error is None
                and time.monotonic() - self._sample_time <= self.max_age_seconds)

    def should_use_deep_brain(self, complexity):
        complexity = float(complexity)
        if not math.isfinite(complexity) or not 0 <= complexity <= 1:
            raise ValueError("Complexidade deve estar entre 0 e 1")
        with self._lock:
            if not self._available():
                return False
            sample = self._sample
            if sample["vram_free_mb"] < self.deep_vram_budget_mb or sample["cpu_used_pct"] >= 95:
                return False
            return sample["current_ih"] >= max(0.4, 0.65 - 0.25 * complexity)

    def snapshot(self):
        with self._lock:
            available = self._available()
            sample = dict(self._sample or {"current_ih": None, "success_rate": None})
            return {**sample, "history": list(self._history), "available": available,
                    "status": "NORMAL" if self.should_use_deep_brain(1.0) else "ECONOMY",
                    "error": self._error,
                    "deep_vram_budget_mb": self.deep_vram_budget_mb}
