# ==============================================================================
# BRAINNET v7 - SISTEMA OPERACIONAL COGNITIVO
# MODULO: hyperdimensional.py
# FUNCAO: Algebra Hiperdimensional Fourier (FHRR) pura em T^10.000 (complex64).
# Tag: [BN_FHRR_CORE]
# ==============================================================================

from __future__ import annotations

from collections import OrderedDict, deque
import hashlib
import math
import re
from typing import Any, Dict, List, Optional, Tuple, Sequence
import numpy as np

try:
    from numba import njit, prange
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False

if HAS_NUMBA:
    @njit(fastmath=True, parallel=True, cache=True)
    def _jit_bind(u: np.ndarray, v: np.ndarray) -> np.ndarray:
        n = u.shape[0]
        out = np.empty(n, dtype=np.complex64)
        for i in prange(n):
            out[i] = u[i] * v[i]
        return out

    @njit(fastmath=True, parallel=True, cache=True)
    def _jit_unbind(bound: np.ndarray, key: np.ndarray) -> np.ndarray:
        n = bound.shape[0]
        out = np.empty(n, dtype=np.complex64)
        for i in prange(n):
            kr = key[i].real
            ki = -key[i].imag
            out[i] = bound[i] * complex(kr, ki)
        return out

    @njit(fastmath=True, parallel=True, cache=True)
    def _jit_similarity(u: np.ndarray, v: np.ndarray) -> float:
        n = u.shape[0]
        acc = 0.0
        for i in prange(n):
            acc += u[i].real * v[i].real + u[i].imag * v[i].imag
        return acc / n


class FHRRHyperdimensionalEngine:
    """
    Motor de Algebra Hiperdimensional Fourier (FHRR) em T^10.000.
    """

    __slots__ = (
        "dim", "seed", "rng", "cleanup_keys", "cleanup_matrix",
        "somatic_dor", "somatic_alivio", "somatic_frustracao", "somatic_rigor",
        "role_action", "role_target", "role_param", "role_context",
        "role_formal", "role_constitutive", "role_telic", "role_agentive",
        "_token_cache", "_cleanup_write_idx"
    )

    def __init__(self, dimension: int = 10_000, seed: int = 42, dim: Optional[int] = None) -> None:
        if dim is not None:
            dimension = dim
        self.dim = int(dimension)
        self.seed = int(seed)
        self.rng = np.random.default_rng(self.seed)
        self.cleanup_matrix = np.zeros((0, self.dim), dtype=np.complex64)
        self.cleanup_keys = deque(maxlen=10000)
        self._cleanup_write_idx = 0
        self._token_cache = OrderedDict()

        # Marcadores Somáticos
        self.somatic_dor = self.generate_vector("__SOMATIC_PAIN_PUNISHMENT__")
        self.somatic_alivio = self.generate_vector("__SOMATIC_RELIEF_REWARD__")
        self.somatic_frustracao = self.generate_vector("__SOMATIC_FRUSTRATION_STAGNATION__")
        self.somatic_rigor = self.generate_vector("__SOMATIC_ANTI_SHORTCUT_EFFORT__")

        # Papeis
        self.role_action = self.generate_vector("__ROLE_ACTION__")
        self.role_target = self.generate_vector("__ROLE_TARGET__")
        self.role_param = self.generate_vector("__ROLE_PARAM__")
        self.role_context = self.generate_vector("__ROLE_CONTEXT__")
        self.role_formal = self.generate_vector("__ROLE_QUALIA_FORMAL__")
        self.role_constitutive = self.generate_vector("__ROLE_QUALIA_CONSTITUTIVE__")
        self.role_telic = self.generate_vector("__ROLE_QUALIA_TELIC__")
        self.role_agentive = self.generate_vector("__ROLE_QUALIA_AGENTIVE__")

    def generate_vector(self, label: Optional[str] = None) -> np.ndarray:
        if label is not None:
            digest = hashlib.sha256(label.encode("utf-8")).digest()
            local_seed = int.from_bytes(digest[:8], "little")
            rng = np.random.default_rng(local_seed)
        else:
            rng = self.rng
        phases = rng.uniform(-np.pi, np.pi, self.dim).astype(np.float32)
        return np.exp(1j * phases).astype(np.complex64)

    def text_to_hypervector(self, text: str) -> np.ndarray:
        tokens = re.findall(r"\w+", text.lower())
        if not tokens:
            return self.generate_vector("__EMPTY_TEXT__")

        parts: List[np.ndarray] = []
        for pos, tok in enumerate(tokens):
            if tok not in self._token_cache:
                if len(self._token_cache) >= 5000:
                    self._token_cache.popitem(last=False)
                self._token_cache[tok] = self.generate_vector(tok)
            self._token_cache.move_to_end(tok)
            v_tok = self._token_cache[tok]
            
            parts.append(self.permute(v_tok, shift=(pos + 1) % self.dim))
            if len(tok) >= 3:
                for k in range(len(tok) - 2):
                    ngram = tok[k:k + 3]
                    if ngram not in self._token_cache:
                        if len(self._token_cache) >= 5000:
                            self._token_cache.popitem(last=False)
                        self._token_cache[ngram] = self.generate_vector(ngram)
                    self._token_cache.move_to_end(ngram)
                    parts.append(self._token_cache[ngram])

        return self.bundle(parts)

    def permute(self, v: np.ndarray, shift: int = 1) -> np.ndarray:
        """Rotacao circular para codificacao posicional invariante (Pi^n)."""
        return np.roll(v, int(shift))

    def bind(self, u: np.ndarray, v: np.ndarray) -> np.ndarray:
        uu = np.ascontiguousarray(u, dtype=np.complex64)
        vv = np.ascontiguousarray(v, dtype=np.complex64)
        if HAS_NUMBA:
            return _jit_bind(uu, vv)
        return (uu * vv).astype(np.complex64)

    def unbind(self, bound: np.ndarray, key: np.ndarray) -> np.ndarray:
        bb = np.ascontiguousarray(bound, dtype=np.complex64)
        kk = np.ascontiguousarray(key, dtype=np.complex64)
        if HAS_NUMBA:
            return _jit_unbind(bb, kk)
        return (bb * np.conj(kk)).astype(np.complex64)

    def similarity(self, u: np.ndarray, v: np.ndarray) -> float:
        uu = np.ascontiguousarray(u, dtype=np.complex64)
        vv = np.ascontiguousarray(v, dtype=np.complex64)
        if HAS_NUMBA:
            return float(_jit_similarity(uu, vv))
        return float(np.real(np.vdot(uu, vv)) / self.dim)

    def bundle(self, vectors: List[np.ndarray]) -> np.ndarray:
        if not vectors:
            raise ValueError("bundle: lista vazia")
        if len(vectors) == 1:
            return np.ascontiguousarray(vectors[0], dtype=np.complex64).copy()

        matrix = np.stack(vectors).astype(np.complex64)
        accum = np.sum(matrix, axis=0)
        mag = np.abs(accum)
        accum[mag < 1e-12] = 1.0 + 0.0j
        phases = np.angle(accum)
        return np.exp(1j * phases).astype(np.complex64)

    def bundle_weighted(self, vectors: List[np.ndarray], weights: Sequence[float]) -> np.ndarray:
        if not vectors or not weights or len(vectors) != len(weights):
            raise ValueError("bundle_weighted: dimensoes inconsistentes")
        matrix = np.stack(vectors).astype(np.complex64)
        w = np.asarray(weights, dtype=np.float32)
        accum = np.sum(matrix * w[:, None], axis=0)
        mag = np.abs(accum)
        accum[mag < 1e-12] = 1.0 + 0.0j
        return np.exp(1j * np.angle(accum)).astype(np.complex64)

    def bind_recursive(self, *vectors: np.ndarray) -> np.ndarray:
        if not vectors:
            raise ValueError("bind_recursive: lista vazia")
        result = np.ascontiguousarray(vectors[0], dtype=np.complex64).copy()
        for vector in vectors[1:]:
            result = self.bind(result, vector)
        return result

    def fractional_bind(self, base: np.ndarray, alpha: float) -> np.ndarray:
        phases = np.angle(np.ascontiguousarray(base, dtype=np.complex64))
        return np.exp(1j * (phases * float(alpha))).astype(np.complex64)

    def phase_shift(self, v: np.ndarray, delta: float) -> np.ndarray:
        phases = np.angle(np.ascontiguousarray(v, dtype=np.complex64))
        return np.exp(1j * (phases + float(delta))).astype(np.complex64)

    def immunize_failure(self, v_concept: np.ndarray) -> np.ndarray:
        return self.phase_shift(v_concept, math.pi)

    def evaluate_somatic_valence(self, vector: np.ndarray) -> Dict[str, float]:
        return {
            "dor": self.similarity(vector, self.somatic_dor),
            "alivio": self.similarity(vector, self.somatic_alivio),
            "frustracao": self.similarity(vector, self.somatic_frustracao),
            "rigor": self.similarity(vector, self.somatic_rigor),
        }

    def register_cleanup(self, key: str, vector: np.ndarray) -> None:
        v = np.ascontiguousarray(vector, dtype=np.complex64)
        mag = np.abs(v)
        unit = (v / np.maximum(mag, 1e-12)).astype(np.complex64)
        v_2d = unit.reshape(1, -1)
        if len(self.cleanup_keys) == self.cleanup_keys.maxlen:
            self.cleanup_matrix[self._cleanup_write_idx] = v_2d[0]
        else:
            self.cleanup_matrix = np.vstack([self.cleanup_matrix, v_2d])
        self.cleanup_keys.append(str(key))
        self._cleanup_write_idx = (self._cleanup_write_idx + 1) % self.cleanup_keys.maxlen

    def cleanup_query(self, noisy_vector: np.ndarray, threshold: float = 0.25, beta: float = 12.0) -> Optional[Tuple[str, float]]:
        if self.cleanup_matrix is None or len(self.cleanup_keys) == 0:
            return None

        q = np.ascontiguousarray(noisy_vector, dtype=np.complex64)
        mag = np.abs(q)
        q_norm = (q / np.maximum(mag, 1e-12)).astype(np.complex64)

        scores = np.real(self.cleanup_matrix @ np.conj(q_norm)) / self.dim
        best_idx = int(np.argmax(scores))
        best_score = float(scores[best_idx])

        if best_score < threshold:
            return None

        exp_scores = np.exp(beta * (scores - np.max(scores)))
        prob_scores = exp_scores / np.sum(exp_scores)
        confidence = float(prob_scores[best_idx])

        if confidence >= 0.35:
            key_idx = (best_idx - self._cleanup_write_idx) % len(self.cleanup_keys)
            return self.cleanup_keys[key_idx], best_score
        return None

    def encode_compositional(self, action: str, target: str, param: str = "", context: str = "") -> np.ndarray:
        v_a = self.bind(self.role_action, self.text_to_hypervector(action))
        v_t = self.bind(self.role_target, self.text_to_hypervector(target))
        partes = [v_a, v_t]

        if param:
            partes.append(self.bind(self.role_param, self.text_to_hypervector(param)))
        if context:
            partes.append(self.bind(self.role_context, self.text_to_hypervector(context)))

        return self.bundle(partes)

    def extract_role_value(self, composite_vector: np.ndarray, role_name: str) -> np.ndarray:
        role_map = {
            "action": self.role_action,
            "target": self.role_target,
            "param": self.role_param,
            "context": self.role_context,
        }
        r_vec = role_map.get(role_name.lower().strip(), self.role_action)
        return self.unbind(composite_vector, r_vec)
