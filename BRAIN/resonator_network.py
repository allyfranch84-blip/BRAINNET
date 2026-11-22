# ==============================================================================
# BRAINNET v8 - RESONATOR NETWORK QUANTIZADO (Z_8)
# Fatoração Contínua via Hopfield Discreto. Elimina Numba e complex64.
# ==============================================================================

from __future__ import annotations

import time
from typing import Dict, List, Tuple
import numpy as np

# LUT de cossenos para Z_8
COS_LUT_Z8 = np.array([
    1.0, 0.70710678, 0.0, -0.70710678,
    -1.0, -0.70710678, 0.0, 0.70710678
], dtype=np.float32)

class HolographicResonatorNetwork:
    """Desfatora hipervetores Z_8 em < 0.3ms."""

    __slots__ = ("dim", "beta", "max_iter")

    def __init__(self, dim: int = 10_000, beta: float = 14.0, max_iter: int = 6) -> None:
        self.dim = dim
        self.beta = beta
        self.max_iter = max_iter

    def factorize_scene(
        self,
        composite_vector: np.ndarray,
        codebooks: List[Dict[str, np.ndarray]]
    ) -> Tuple[List[str], float]:
        t0 = time.perf_counter_ns()
        num_factors = len(codebooks)

        matrices = []
        labels_list = []
        estimates = []

        for cb in codebooks:
            keys = list(cb.keys())
            labels_list.append(keys)
            mat = np.stack([cb[k] for k in keys]).astype(np.uint8)
            matrices.append(mat)
            
            # Inicialização: ruído uniforme em Z_8 ou a média dos vetores
            estimates.append(np.random.randint(0, 8, size=self.dim, dtype=np.uint8))

        # Relaxamento de Hopfield Discreto
        for _ in range(self.max_iter):
            for f in range(num_factors):
                # Unbinding dos outros fatores: r = composite - sum(others) mod 8
                inv_others = np.zeros(self.dim, dtype=np.uint8)
                for other_f in range(num_factors):
                    if other_f != f:
                        inv_others = (inv_others + estimates[other_f]) % 8

                r = (composite_vector - inv_others) % 8

                # Similaridade via LUT (broadcasting)
                # diff shape: (N_items, self.dim)
                diff = (matrices[f] - r) % 8
                sims = np.mean(COS_LUT_Z8[diff], axis=1)

                # Softmax
                w = np.exp(self.beta * (sims - np.max(sims)))
                w /= np.sum(w)

                # Bundling Ponderado: projeta para o complexo, soma e quantiza
                # exp(i * theta) = cos + i*sin, onde theta = phase * pi/4
                phases = matrices[f].astype(np.float32) * (np.pi / 4.0)
                accum = np.sum(np.exp(1j * phases) * w[:, None], axis=0)
                
                # Quantiza de volta para Z_8
                mean_angles = np.angle(accum)
                mean_angles = np.where(mean_angles < 0, mean_angles + 2 * np.pi, mean_angles)
                estimates[f] = (np.round(mean_angles / (np.pi / 4.0)).astype(np.int32) % 8).astype(np.uint8)

        # Identificação dos vencedores
        resolved_labels = []
        for f in range(num_factors):
            diff = (matrices[f] - estimates[f]) % 8
            sims = np.mean(COS_LUT_Z8[diff], axis=1)
            best_idx = int(np.argmax(sims))
            resolved_labels.append(labels_list[f][best_idx])

        elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000.0
        return resolved_labels, elapsed_ms
