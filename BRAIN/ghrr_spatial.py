# ==============================================================================
# BRAINNET v8 - CÓRTEX ESPACIAL VISUAL
# MODULO: ghrr_spatial.py
# FUNCAO: Fractional Binding para Coordenadas 2D e Rastreamento Suave de UI.
# ==============================================================================

from __future__ import annotations

import numpy as np
from typing import Tuple, Dict, Any
from hyperdimensional import FHRRHyperdimensionalEngine

class FractionalSpatialCortex:
    """
    Mapeador topológico espacial no toro complexo C^D.
    Associa representações visuais a coordenadas contínuas de tela (X, Y).
    """

    __slots__ = ("vsa", "dim", "base_x", "base_y")

    def __init__(self, vsa_engine: FHRRHyperdimensionalEngine) -> None:
        self.vsa = vsa_engine
        self.dim = vsa_engine.dim
        # Geradores ortogonais canônicos para os eixos X e Y
        self.base_x = self.vsa.generate_vector("__AXIS_SPATIAL_X__")
        self.base_y = self.vsa.generate_vector("__AXIS_SPATIAL_Y__")

    def encode_coordinates(self, x_norm: float, y_norm: float) -> np.ndarray:
        """
        Codifica coordenadas normalizadas [0.0, 1.0] por Fractional Binding:
        V(x, y) = (base_x ^ x) * (base_y ^ y)
        """
        # Multiplicação contínua da fase pelo escalar de posição
        phase_x = np.angle(self.base_x) * float(x_norm)
        phase_y = np.angle(self.base_y) * float(y_norm)

        v_x = np.exp(1j * phase_x).astype(np.complex64)
        v_y = np.exp(1j * phase_y).astype(np.complex64)

        return self.vsa.bind(v_x, v_y)

    def bind_element_to_position(
        self,
        element_vector: np.ndarray,
        x_norm: float,
        y_norm: float
    ) -> np.ndarray:
        """Vincula o descritor visual do elemento à sua posição na tela."""
        pos_vec = self.encode_coordinates(x_norm, y_norm)
        return self.vsa.bind(element_vector, pos_vec)

    def extract_element_at_position(
        self,
        scene_composite: np.ndarray,
        x_norm: float,
        y_norm: float
    ) -> np.ndarray:
        """Recupera o descritor do elemento presente em uma coordenada alvo."""
        pos_vec = self.encode_coordinates(x_norm, y_norm)
        return self.vsa.unbind(scene_composite, pos_vec)

    def calculate_drift_tolerance(
        self,
        pos_a: Tuple[float, float],
        pos_b: Tuple[float, float]
    ) -> float:
        """
        Calcula a similaridade entre duas posições:
        Decai monotonicamente com a distância euclidiana, provendo tolerância elástica.
        """
        va = self.encode_coordinates(pos_a[0], pos_a[1])
        vb = self.encode_coordinates(pos_b[0], pos_b[1])
        return self.vsa.similarity(va, vb)
