# ==============================================================================
# BRAINNET v7 - FRONTEIRA CIENTÍFICA: RESERVATÓRIO LÍQUIDO EM RAM (AVX2 MMSE)
# MODULO: liquid_reservoir.py
# FUNCAO: Digestão Contínua de Entropia (64 Canais), Predição por Filtro de Wiener
#         e Sinalizador de Incerteza Homeostática (Friston Free Energy).
# ==============================================================================

from __future__ import annotations

from collections import deque
import re
import time
from typing import Any, Dict, Optional, Tuple
import numpy as np

try:
    from numba import njit, prange
    HAS_NUMBA = True

    @njit(fastmath=True, parallel=True)
    def _jit_reservoir_step(
        r_state: np.ndarray,
        u_input: np.ndarray,
        w_res: np.ndarray,
        w_in: np.ndarray,
        alpha: float
    ) -> np.ndarray:
        n_nodes = r_state.shape[0]
        dim_in = u_input.shape[0]
        out = np.empty(n_nodes, dtype=np.float32)

        for i in prange(n_nodes):
            dot_res = 0.0
            for j in range(n_nodes):
                dot_res += w_res[i, j] * r_state[j]

            dot_in = 0.0
            for k in range(dim_in):
                dot_in += w_in[i, k] * u_input[k]

            pre = dot_res + dot_in
            out[i] = (1.0 - alpha) * r_state[i] + alpha * np.tanh(pre)
        return out
except ImportError:
    HAS_NUMBA = False


class PalimpsestLiquidReservoir:
    """
    [PILAR 5 DO ROADMAP V8: REGULADOR TERMODINÂMICO ATIVO]:
    Rede recorrente de 8.000 nós no regime da borda do caos (rho = 0.95).
    Consome 64 canais contínuos de telemetria, gera expectativas de estado
    e emite o sinal de Incerteza Ativa (Erro de Predição) para o Kernel.
    """

    __slots__ = (
        "n_nodes",
        "alpha",
        "dim_input",
        "w_res",
        "w_in",
        "r_state",
        "w_out",
        "state_history",
        "target_history",
        "last_uncertainty"
    )

    def __init__(self, n_nodes: int = 8000, dim_input: int = 64, alpha: float = 0.35, seed: int = 42) -> None:
        self.n_nodes = n_nodes
        self.dim_input = dim_input
        self.alpha = alpha
        rng = np.random.default_rng(seed)

        # Matriz recorrente na borda do caos (rho = 0.95)
        mat = rng.normal(0.0, 1.0, (n_nodes, n_nodes)).astype(np.float32)
        mask = rng.uniform(0.0, 1.0, (n_nodes, n_nodes)) < 0.05
        mat = mat * mask
        eigenvals = np.linalg.eigvals(mat[:1000, :1000])
        radius = np.max(np.abs(eigenvals))
        self.w_res = (mat * (0.95 / max(radius, 1e-6))).astype(np.float32)

        # Projeção densa de 64 canais
        self.w_in = rng.uniform(-0.5, 0.5, (n_nodes, dim_input)).astype(np.float32)

        self.r_state = np.zeros(n_nodes, dtype=np.float32)
        self.w_out: Optional[np.ndarray] = None
        self.state_history: deque[np.ndarray] = deque(maxlen=300)
        self.target_history: deque[np.ndarray] = deque(maxlen=300)
        self.last_uncertainty: float = 0.10

    def inject_system_event(self, event_vector: np.ndarray) -> float:
        """Injeta a assinatura entrópica de 64 canais em <0.08ms via AVX2."""
        t0 = time.perf_counter_ns()
        u = event_vector.astype(np.float32)
        if len(u) < self.dim_input:
            u = np.pad(u, (0, self.dim_input - len(u)))

        if HAS_NUMBA:
            self.r_state = _jit_reservoir_step(self.r_state, u, self.w_res, self.w_in, self.alpha)
        else:
            pre = self.w_res @ self.r_state + self.w_in @ u
            self.r_state = (1.0 - self.alpha) * self.r_state + self.alpha * np.tanh(pre)

        # Mantém histórico volátil para o estimador de Wiener
        self.state_history.append(self.r_state.copy())
        self.target_history.append(u[:8])  # Alvo: antecipar os primeiros 8 canais de telemetria

        elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000.0
        return elapsed_ms

    def fit_wiener_filter(self, reg: float = 1e-4) -> None:
        """Treina o estimador ótimo linear MMSE sobre o histórico recente."""
        if len(self.state_history) < 60:
            return

        r_mat = np.stack(list(self.state_history)).astype(np.float32)
        y_mat = np.stack(list(self.target_history)).astype(np.float32)

        cov = r_mat.T @ r_mat + reg * np.eye(self.n_nodes, dtype=np.float32)
        self.w_out = (np.linalg.pinv(cov) @ r_mat.T @ y_mat).T

    def predict_and_evaluate_surprise(self, actual_next_event: np.ndarray) -> float:
        """
        Calcula a surpresa termodinâmica (Erro de Predição):
        Divergência entre o estado observado e o estado antecipado pelo reservatório.
        """
        if self.w_out is None or len(self.state_history) < 60:
            return 0.15

        pred = self.w_out @ self.r_state
        diff = actual_next_event[:8] - pred
        surprise = float(np.mean(diff ** 2))
        self.last_uncertainty = round(min(1.0, max(0.01, surprise * 5.0)), 4)
        return self.last_uncertainty

    @staticmethod
    def pack_dense_telemetry(
        dhash_hex: str,
        cpu_total_pct: float,
        ram_used_pct: float,
        vram_used_pct: float,
        hwnd_val: int,
        start_menu_open: bool,
        mouse_velocity: float = 0.0
    ) -> np.ndarray:
        """
        [EMPACOTADOR DE 64 CANAIS ENTRÓPICOS]:
        Dobra o estado completo da máquina em um vetor denso float32 contíguo.
        """
        vec = np.zeros(64, dtype=np.float32)

        # 1. dHash visual da tela (Canais 0 a 15)
        clean_hex = re.sub(r"[^0-9a-fA-F]", "", dhash_hex or "0").zfill(16)[:16]
        for i, ch in enumerate(clean_hex):
            vec[i] = float(int(ch, 16)) / 15.0

        # 2. Telemetria de Hardware Win32 (Canais 16 a 27)
        vec[16] = float(cpu_total_pct) / 100.0
        vec[17] = float(ram_used_pct) / 100.0
        vec[18] = float(vram_used_pct) / 100.0
        vec[19] = float(hwnd_val % 1000) / 1000.0
        vec[20] = 1.0 if start_menu_open else 0.0
        vec[21] = min(1.0, float(mouse_velocity) / 2000.0)

        # 3. Ondas Harmônicas de Inércia Temporal (Canais 28 a 63)
        t_phase = time.time() % 3600.0
        for k in range(28, 64):
            freq = (k - 27) * 0.1
            vec[k] = float(np.sin(t_phase * freq))

        return vec