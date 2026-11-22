# ==============================================================================
# BRAINNET v8 - CÓRTEX HIPERDIMENSIONAL QUANTIZADO (QFHRR)
# MODULO: qfhrr_core.py
# FUNCAO: Algebra Hiperdimensional Quantizada em 3-bits (Z_8).
#         Consumo de ~3.75 KB por vetor de 10.000D, operado via Look-Up Tables.
# ==============================================================================

from __future__ import annotations

import hashlib
import numpy as np
from typing import List, Optional, Tuple, Sequence

# Tabela de Cossenos pré-computada para Z_8: cos(k * pi / 4)
# k in [0, 1, 2, 3, 4, 5, 6, 7]
COS_LUT_Z8 = np.array([
    1.0,
    0.70710678,
    0.0,
    -0.70710678,
    -1.0,
    -0.70710678,
    0.0,
    0.70710678
], dtype=np.float32)

class QFHRRHyperdimensionalEngine:
    """
    Motor QFHRR de 3 bits.
    Armazena fases em uint8 restritas ao anel modular Z_8 = {0, 1, 2, 3, 4, 5, 6, 7}.
    Elimina números complexos e operações transcendentais em tempo de execução.
    """

    __slots__ = ("dim", "seed", "rng", "lut_cos", "sparsity")

    def __init__(self, dimension: int = 10_000, seed: int = 42, sparsity: float = 0.1) -> None:
        self.dim = int(dimension)
        self.seed = int(seed)
        self.rng = np.random.default_rng(self.seed)
        self.lut_cos = COS_LUT_Z8
        self.sparsity = float(sparsity)

    def generate_vector(self, label: Optional[str] = None) -> np.ndarray:
        """Gera um hipervetor ESPARSO em Z_8 (padrão: 10% das dimensões ativas)."""
        if label is not None:
            digest = hashlib.sha256(label.encode("utf-8")).digest()
            local_seed = int.from_bytes(digest[:8], "little")
            rng = np.random.default_rng(local_seed)
        else:
            rng = self.rng
            
        vec = rng.integers(0, 8, size=self.dim, dtype=np.uint8)
        
        # Cria uma máscara booleana com 10% de True (sparsity)
        mask = rng.random(self.dim) < self.sparsity
        # Zera o restante (dimensões neutras)
        vec[~mask] = 0
        
        return vec

    def bind(self, u: np.ndarray, v: np.ndarray) -> np.ndarray:
        """
        Ligação Não-Linear em Z_8:
        (u + v) mod 8 implementado via bitwise AND (u + v) & 7.
        """
        return np.bitwise_and(u + v, 7).astype(np.uint8)

    def unbind(self, bound: np.ndarray, key: np.ndarray) -> np.ndarray:
        """
        Desassociação em Z_8:
        (bound - key) mod 8 implementado como (bound + 8 - key) & 7.
        """
        return np.bitwise_and(bound + 8 - key, 7).astype(np.uint8)

    def similarity(self, u: np.ndarray, v: np.ndarray) -> float:
        """
        Similaridade de cosseno discreta avaliada por indexação direta na LUT.
        Ignora dimensões onde AMBOS são nulos (0) para não inflar o resultado.
        """
        diff = np.bitwise_and(u + 8 - v, 7)
        # Máscara booleana: True onde pelo menos um dos vetores tem fase ativa
        mask = (u != 0) | (v != 0)
        if not np.any(mask):
            return 1.0 # Dois vetores totalmente vazios são iguais
        return float(np.mean(self.lut_cos[diff][mask]))

    def bundle(self, vectors: Sequence[np.ndarray]) -> np.ndarray:
        """
        Superposição por média fasorial quantizada.
        Ignora as dimensões nulas (0) durante a média para não diluir a fase.
        """
        if not vectors:
            raise ValueError("bundle: lista de vetores vazia")
        if len(vectors) == 1:
            return vectors[0].copy()

        vectors_arr = np.stack(vectors)
        angles = vectors_arr.astype(np.float32) * (np.pi / 4.0)
        
        # Máscara onde os vetores têm fase ativa
        mask = (vectors_arr != 0)
        
        # Acumula apenas os ativos
        sum_cos = np.sum(np.cos(angles) * mask, axis=0)
        sum_sin = np.sum(np.sin(angles) * mask, axis=0)
        
        # Identifica dimensões onde todos os vetores foram nulos
        all_null = ~np.any(mask, axis=0)

        # Determina o ângulo resultante
        mean_angles = np.arctan2(sum_sin, sum_cos)
        mean_angles = np.where(mean_angles < 0, mean_angles + 2 * np.pi, mean_angles)

        # Quantiza de volta para Z_8
        sectors = np.round(mean_angles / (np.pi / 4.0)).astype(np.int32) % 8
        
        # Garante que dimensões mortas continuem mortas (0)
        sectors[all_null] = 0
        return sectors.astype(np.uint8)

    def permute(self, v: np.ndarray, shift: int = 1) -> np.ndarray:
        """Permutação circular para ordenação posicional/sintática."""
        return np.roll(v, int(shift))

    def text_to_hypervector(self, text: str) -> np.ndarray:
        """Tokeniza e cria um bundle espacial de palavras em Z_8."""
        import re
        tokens = re.findall(r"\w+", text.lower())
        if not tokens:
            return self.generate_vector("__EMPTY_TEXT__")
        parts = []
        for pos, tok in enumerate(tokens):
            v_tok = self.generate_vector(tok)
            parts.append(self.permute(v_tok, shift=(pos + 1) % self.dim))
        return self.bundle(parts)

    def fractional_bind(self, v: np.ndarray, alpha: float) -> np.ndarray:
        """Fractional Power Encoding (FPE) em Z_8.
        Rotaciona as fases por um fator contínuo 'alpha' (ex: coordenada X ou Y).
        """
        # Converte a fração contínua para o setor discreto Z_8 mais próximo
        shift = int(round(alpha * 8.0 / (2.0 * np.pi)))
        return (v + shift) % 8

    def pack_to_bits(self, v: np.ndarray) -> bytes:
        """
        Compactação de 3 bits por dimensão:
        Empacota 8 elementos de 3 bits em 3 bytes (24 bits).
        10.000 dimensões cabem em 3.750 bytes.
        """
        flat = v.astype(np.uint32)
        pad_len = (8 - (len(flat) % 8)) % 8
        if pad_len > 0:
            flat = np.pad(flat, (0, pad_len))

        chunks = (flat.reshape(-1, 8) & 7).astype(np.uint8)
        packed = np.empty((len(chunks), 3), dtype=np.uint8)
        packed[:, 0] = chunks[:, 0] | (chunks[:, 1] << 3) | ((chunks[:, 2] & 3) << 6)
        packed[:, 1] = (chunks[:, 2] >> 2) | (chunks[:, 3] << 1) | (chunks[:, 4] << 4) | ((chunks[:, 5] & 1) << 7)
        packed[:, 2] = (chunks[:, 5] >> 1) | (chunks[:, 6] << 2) | (chunks[:, 7] << 5)
        return packed.tobytes()

    def pack_masked_v2(self, phases: np.ndarray, present: np.ndarray) -> bytes:
        """Versioned Z8 values with explicit presence; legacy Z8 stays unchanged."""
        import struct
        phases = np.asarray(phases)
        present = np.asarray(present)
        if phases.shape != (self.dim,) or present.shape != (self.dim,):
            raise ValueError('invalid dimension')
        if phases.dtype.kind not in 'iu' or np.any(phases < 0) or np.any(phases > 7) or present.dtype != np.bool_:
            raise ValueError('invalid phases or presence mask')
        return (struct.pack('<4sIB', b'QF2\0', self.dim, 8) +
                self.pack_to_bits(phases) + np.packbits(present, bitorder='little').tobytes())

    def unpack_masked_v2(self, data: bytes) -> tuple[np.ndarray, np.ndarray]:
        import struct
        if len(data) < 9: raise ValueError('truncated header')
        magic, dim, levels = struct.unpack('<4sIB', data[:9])
        if magic != b'QF2\0' or levels != 8 or dim != self.dim:
            raise ValueError('unsupported representation')
        phase_bytes = ((dim + 7) // 8) * 3
        mask_bytes = (dim + 7) // 8
        if len(data) != 9 + phase_bytes + mask_bytes: raise ValueError('truncated or excess data')
        phases = self.unpack_from_bits(data[9:9+phase_bytes], dim)
        mask = np.unpackbits(np.frombuffer(data[9+phase_bytes:], dtype=np.uint8), bitorder='little')[:dim].astype(bool)
        return phases, mask

    def unpack_from_bits(self, data: bytes, target_dim: int) -> np.ndarray:
        """Desempacota a sequência de 3 bytes para 8 valores de 3 bits."""
        arr = bytearray(data)
        num_chunks = len(arr) // 3
        out = np.empty(num_chunks * 8, dtype=np.uint8)

        for i in range(num_chunks):
            b0, b1, b2 = arr[i*3], arr[i*3 + 1], arr[i*3 + 2]
            idx = i * 8
            out[idx]     = b0 & 0x7
            out[idx + 1] = (b0 >> 3) & 0x7
            out[idx + 2] = ((b0 >> 6) & 0x3) | ((b1 & 0x1) << 2)
            out[idx + 3] = (b1 >> 1) & 0x7
            out[idx + 4] = (b1 >> 4) & 0x7
            out[idx + 5] = ((b1 >> 7) & 0x1) | ((b2 & 0x3) << 1)
            out[idx + 6] = (b2 >> 2) & 0x7
            out[idx + 7] = (b2 >> 5) & 0x7

        return out[:target_dim]
