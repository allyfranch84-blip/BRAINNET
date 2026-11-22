# ==============================================================================
# BRAINNET v8 - CÓRTEX SINTÁTICO (GHRR)
# MODULO: ghrr_core.py
# FUNCAO: Matrizes Unitárias Não-Comutativas para Ordem e Sintaxe em C^10.000.
# ==============================================================================

from __future__ import annotations
import hashlib
import math
from typing import List, Optional, Tuple
import numpy as np

class GHRRHyperdimensionalEngine:
    """
    Motor GHRR (Generalized Holographic Reduced Representations).
    Substitui fasores escalares U(1) por matrizes unitárias U(M), 
    quebrando a comutatividade para preservar ordem e sintaxe.
    """

    __slots__ = ("dim", "matrix_size", "num_blocks", "seed", "rng")

    def __init__(self, dim: int = 10_000, matrix_size: int = 2, seed: int = 42) -> None:
        self.dim = int(dim)
        self.matrix_size = int(matrix_size) # M (ex: 2x2)
        
        if self.dim % self.matrix_size != 0:
            raise ValueError(f"Dimensão {self.dim} deve ser múltipla do tamanho da matriz {self.matrix_size}")
            
        self.num_blocks = self.dim // self.matrix_size # K
        self.seed = int(seed)
        self.rng = np.random.default_rng(self.seed)

    def generate_vector(self, label: Optional[str] = None) -> np.ndarray:
        """
        Gera um tensor de matrizes unitárias complexas.
        Shape resultante: (K, M, M) com dtype complex64.
        """
        if label is not None:
            digest = hashlib.sha256(label.encode("utf-8")).digest()
            local_seed = int.from_bytes(digest[:8], "little")
            rng = np.random.default_rng(local_seed)
        else:
            rng = self.rng

        # Gera matrizes complexas aleatórias
        random_matrices = rng.standard_normal(
            (self.num_blocks, self.matrix_size, self.matrix_size), 
            dtype=np.float32
        ) + 1j * rng.standard_normal(
            (self.num_blocks, self.matrix_size, self.matrix_size), 
            dtype=np.float32
        )

        # Decomposição QR para tornar as matrizes unitárias (ortogonais no espaço complexo)
        # np.linalg.qr opera em batch para arrays 3D
        q, r = np.linalg.qr(random_matrices)
        
        # Normaliza para garantir que o determinante seja 1 (matrizes em SU(M))
        # Extraímos a diagonal de R e ajustamos a fase
        diag_r = np.diagonal(r, axis1=1, axis2=2)
        phases = diag_r / np.abs(diag_r)
        
        # Multiplica cada coluna de q pela fase correspondente (equivale a q @ diag(phases))
        q = q * phases[:, np.newaxis, :]
        return q.astype(np.complex64)

    def bind(self, u: np.ndarray, v: np.ndarray) -> np.ndarray:
        """
        Ligação Não-Comutativa (Binding).
        U ⊠ V = U * V (multiplicação de matrizes bloco a bloco).
        """
        return np.matmul(u, v).astype(np.complex64)

    def unbind(self, bound: np.ndarray, key: np.ndarray) -> np.ndarray:
        """Compatibilidade: remove o fator da direita, retornando U de U @ V."""
        return self.unbind_right(bound, key)

    def unbind_right(self, bound: np.ndarray, key: np.ndarray) -> np.ndarray:
        """Para bound = U @ V e key = V, retorna U."""
        key_dagger = np.conj(np.swapaxes(key, 1, 2))
        return np.matmul(bound, key_dagger).astype(np.complex64)

    def unbind_left(self, bound: np.ndarray, key: np.ndarray) -> np.ndarray:
        """Para bound = U @ V e key = U, retorna V."""
        key_dagger = np.conj(np.swapaxes(key, 1, 2))
        return np.matmul(key_dagger, bound).astype(np.complex64)

    def bundle(self, vectors: List[np.ndarray]) -> np.ndarray:
        """
        Superposição (Bundling) de matrizes unitárias.
        Soma as matrizes e projeta o resultado de volta para o grupo unitário via SVD.
        """
        if not vectors:
            raise ValueError("bundle: lista vazia")
        if len(vectors) == 1:
            return vectors[0].copy()

        # Soma dos tensores (K, M, M)
        summed = np.sum(vectors, axis=0)
        
        # Projeção de volta para matriz unitária usando SVD
        # Para uma matriz A, a matriz unitária mais próxima é U * V^H
        u, s, vh = np.linalg.svd(summed)
        return np.matmul(u, vh).astype(np.complex64)

    def similarity(self, u: np.ndarray, v: np.ndarray) -> float:
        """
        Similaridade de Frobenius normalizada.
        Retorna um valor entre -1.0 e 1.0.
        """
        # Traço de (U^† * V) para cada bloco
        u_dagger = np.conj(np.swapaxes(u, 1, 2))
        product = np.matmul(u_dagger, v)
        
        # Soma os traços de todos os blocos (parte real)
        traces = np.trace(product, axis1=1, axis2=2)
        real_traces = np.real(traces)
        
        # Normaliza pelo número de blocos e tamanho da matriz
        return float(np.sum(real_traces) / (self.num_blocks * self.matrix_size))

# ==============================================================================
# TESTE DE FOGO (NÃO-COMUTATIVIDADE)
# ==============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("TESTE DO PIPELINE GHRR (P-DAG SINTÁTICO)")
    print("=" * 60)

    engine = GHRRHyperdimensionalEngine(dim=10_000, matrix_size=2)

    # Vetores das ações (role-filler abstrato)
    v_open = engine.generate_vector("OPEN_APP_BRAVE")
    v_ctrl = engine.generate_vector("HOTKEY_CTRL_L")
    v_type = engine.generate_vector("TYPE_PYTHON")
    v_enter = engine.generate_vector("HOTKEY_ENTER")

    # Encoding do Pipeline: (OPEN_APP ⊠ HOTKEY) ⊠ TYPE ⊠ HOTKEY
    pipeline = engine.bind(engine.bind(engine.bind(v_open, v_ctrl), v_type), v_enter)

    # Desassociando para extrair o 3º passo (TYPE)
    # Fórmula: v_open^H ⊠ v_ctrl^H ⊠ pipeline ⊠ v_enter^H = v_type
    v_open_dagger = np.conj(np.swapaxes(v_open, 1, 2))
    v_ctrl_dagger = np.conj(np.swapaxes(v_ctrl, 1, 2))
    v_enter_dagger = np.conj(np.swapaxes(v_enter, 1, 2))

    # Multiplicando em ordem não-comutativa
    partial_1 = np.matmul(v_open_dagger, pipeline)
    partial_2 = np.matmul(v_ctrl_dagger, partial_1)
    reconstruido_type = np.matmul(partial_2, v_enter_dagger).astype(np.complex64)

    sim_type = engine.similarity(reconstruido_type, v_type)
    print(f"\n[1] Similaridade do passo 'TYPE' reconstruído: {sim_type:.4f}")

    # Desassociando o passo 1 (OPEN_APP)
    v_enter_dagger_1 = np.conj(np.swapaxes(v_enter, 1, 2))
    v_type_dagger = np.conj(np.swapaxes(v_type, 1, 2))
    v_ctrl_dagger_1 = np.conj(np.swapaxes(v_ctrl, 1, 2))
    
    partial_open = np.matmul(pipeline, v_enter_dagger_1)
    partial_open_2 = np.matmul(partial_open, v_type_dagger)
    reconstruido_open = np.matmul(partial_open_2, v_ctrl_dagger_1).astype(np.complex64)
    
    sim_open = engine.similarity(reconstruido_open, v_open)
    print(f"[2] Similaridade do passo 'OPEN_APP' reconstruído: {sim_open:.4f}")
    print("    (Se ambos forem ~1.0000, o P-DAG pode usar o GHRR para planejar sequências!)")

    print("\n" + "=" * 60)
