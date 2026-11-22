# ==============================================================================
# BRAINNET v7 - FRONTEIRA CIENTÍFICA: CONTROLE TERMODINÂMICO POR ENERGIA LIVRE
# MÓDULO: thermodynamic_trajectory.py
# FUNÇÃO: Minimização de Energia Livre de Friston (Active Inference), Colapso de
#         Superposição Multiversal de Hipóteses e Trajetórias de Mínima Ação.
# ==============================================================================

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

try:
    from numba import njit, prange
    HAS_NUMBA = True

    @njit(fastmath=True, parallel=True)
    def _jit_variational_free_energy(
        state_vec: np.ndarray,
        attractor_vec: np.ndarray,
        candidate_actions: np.ndarray,
        dissipation_costs: np.ndarray,
        temperature: float
    ) -> Tuple[int, np.ndarray]:
        """
        Calcula a Energia Livre Variacional de Friston para N hipóteses simultâneas:
        F = Divergência_KL(Estado_Projetado || Atrator_Meta) + Custo_Dissipação_Hardware
        Retorna o índice da rota de menor energia e o vetor de probabilidades de Gibbs.
        """
        n_candidates = candidate_actions.shape[0]
        dim = len(state_vec)
        free_energies = np.empty(n_candidates, dtype=np.float32)

        for c in prange(n_candidates):
            # Projeção contrafactual do futuro: s_next = state ⊙ action
            sim_dot = 0.0
            for i in range(dim):
                r_next = state_vec[i].real * candidate_actions[c, i].real - state_vec[i].imag * candidate_actions[c, i].imag
                im_next = state_vec[i].real * candidate_actions[c, i].imag + state_vec[i].imag * candidate_actions[c, i].real
                sim_dot += (r_next * attractor_vec[i].real + im_next * attractor_vec[i].imag)

            similarity = sim_dot / dim
            divergence = 1.0 - similarity
            
            # Energia Livre Variacional com penalidade entrópica
            free_energies[c] = divergence + dissipation_costs[c]

        # Distribuição de Boltzmann/Gibbs sobre o multiverso de caminhos
        min_f = 1e9
        best_idx = 0
        for c in range(n_candidates):
            if free_energies[c] < min_f:
                min_f = free_energies[c]
                best_idx = c

        # Cálculo de probabilidades relativas para colapso termodinâmico
        exp_weights = np.empty(n_candidates, dtype=np.float32)
        sum_exp = 0.0
        for c in range(n_candidates):
            val = np.exp(- (free_energies[c] - min_f) / max(temperature, 1e-4))
            exp_weights[c] = val
            sum_exp += val

        probs = exp_weights / max(sum_exp, 1e-6)
        return best_idx, probs

except ImportError:
    HAS_NUMBA = False


class ThermodynamicPathController:
    """
    [CÓRTEX CONTRAFACTUAL DE AÇÃO MÍNIMA]:
    Não escolhe caminhos por tentativa cega. Sustenta uma superposição contínua
    de probabilidades em C^10.000, calcula a curvatura do espaço de fase e colapsa
    o vetor de menor dissipação termodinâmica nos 14 núcleos do Xeon.
    """

    __slots__ = ("dim", "default_temperature")

    def __init__(self, dim: int = 10_000, default_temperature: float = 0.25) -> None:
        self.dim = dim
        self.default_temperature = default_temperature

    def select_least_action_path(
        self,
        current_state: np.ndarray,
        target_attractor: np.ndarray,
        candidate_branches: List[Dict[str, Any]],
        temperature: Optional[float] = None
    ) -> Tuple[Dict[str, Any], float, np.ndarray]:
        """
        Avalia o conjunto de ramificações prováveis e colapsa a onda de probabilidade.
        """
        t0 = time.perf_counter_ns()
        temp = temperature if temperature is not None else self.default_temperature

        if not candidate_branches:
            raise ValueError("O feixe de hipóteses contrafactuais não pode estar vazio.")

        n_branches = len(candidate_branches)
        
        # Converte o feixe de vetores para matriz complexa contígua em memória
        action_vectors = np.stack([b["vector"] for b in candidate_branches]).astype(np.complex64)
        costs = np.array([float(b.get("cost", 0.05)) for b in candidate_branches], dtype=np.float32)

        if HAS_NUMBA:
            best_idx, probs = _jit_variational_free_energy(
                current_state, target_attractor, action_vectors, costs, temp
            )
        else:
            best_idx = 0
            min_energy = 1e9
            energies = np.empty(n_branches, dtype=np.float32)
            
            for i, b in enumerate(candidate_branches):
                s_next = current_state * b["vector"]
                sim = float(np.real(np.vdot(s_next, target_attractor)) / self.dim)
                energy = (1.0 - sim) + costs[i]
                energies[i] = energy
                if energy < min_energy:
                    min_energy = energy
                    best_idx = i

            exp_w = np.exp(- (energies - min_energy) / temp)
            probs = exp_w / np.sum(exp_w)

        elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000.0
        vencedor = candidate_branches[best_idx]
        vencedor["__probabilidade_colapso__"] = float(probs[best_idx])

        return vencedor, elapsed_ms, probs

    def generate_counterfactual_hypotheses(
        self,
        base_vector: np.ndarray,
        n_hypotheses: int = 16,
        perturbation_sigma: float = 0.12 * np.pi
    ) -> List[np.ndarray]:
        """
        Gera um multiverso de variações ontológicas por rotação fasorial contínua,
        simulando diferentes nuances da mesma intenção em superposição.
        """
        orig_phases = np.angle(base_vector)
        hypotheses = [base_vector]

        for _ in range(n_hypotheses - 1):
            noise = np.random.normal(0.0, perturbation_sigma, self.dim).astype(np.float32)
            rot_phases = orig_phases + noise
            hypotheses.append(np.exp(1j * rot_phases).astype(np.complex64))

        return hypotheses