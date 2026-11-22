"""Modelo de transicao FHRR em CPU: fases(s), one-hot(a) -> fases(s').

NumPy/BLAS faz os produtos de matrizes; nao ha dependencias de treino pesadas,
rollouts acumulados nem integracao automatica com o Kernel. A loss e MSE linear
das fases, sem diferenca angular circular ou wrapping dentro da loss.
"""
from __future__ import annotations

from threading import RLock
from typing import Any, Dict, Sequence, Tuple

import numpy as np
from telemetry_status import write_training_status


class WorldModel:
    """MLP 10064 -> 512 -> 256 -> 10000, ReLU e Adam em float32.

    predict retorna fases reais; predict_vector reconstroi um FHRR unitario.
    train_step retorna a MSE medida ANTES da atualizacao, como loss de treino.
    state_dim/hidden_dims menores permitem verificacao numerica em testes.
    """

    def __init__(
        self, state_dim: int = 10_000, action_dim: int = 64,
        hidden_dims: Tuple[int, int] = (512, 256),
        action_names: Sequence[str] = (
            "LOCATE", "TRANSFORM", "WAIT", "ENSURE_APP",
            "FOCUS_WINDOW", "TYPE", "HOTKEY", "CLICK",
        ),
        learning_rate: float = 1e-4, max_grad_norm: float = 1.0,
        seed: int = 42, telemetry_path: Any = None,
    ) -> None:
        dimensions = (state_dim, action_dim, *hidden_dims)
        if len(hidden_dims) != 2 or any(
            isinstance(d, bool) or not isinstance(d, (int, np.integer)) or d < 1
            for d in dimensions
        ):
            raise ValueError("Dimensoes devem ser positivas, com exatamente duas camadas ocultas")
        if isinstance(action_names, str):
            raise ValueError("action_names deve ser uma sequencia de rotulos")
        names = tuple(action_names)
        if not names or any(not isinstance(name, str) or not name.strip() for name in names):
            raise ValueError("Defina ao menos uma acao com rotulo nao vazio")
        self.action_names = tuple(name.strip().upper() for name in names)
        if len(set(self.action_names)) != len(names) or len(names) > action_dim:
            raise ValueError("Acoes devem ser distintas e caber no one-hot")
        if not np.isfinite(learning_rate) or learning_rate <= 0:
            raise ValueError("learning_rate deve ser positivo e finito")
        if not np.isfinite(max_grad_norm) or max_grad_norm <= 0:
            raise ValueError("max_grad_norm deve ser positivo e finito")
        self.state_dim, self.action_dim = int(state_dim), int(action_dim)
        self.hidden_dims = tuple(int(d) for d in hidden_dims)
        self.learning_rate, self.max_grad_norm = float(learning_rate), float(max_grad_norm)
        self._action_indices = {name: i for i, name in enumerate(self.action_names)}
        self._lock, self._rng = RLock(), np.random.default_rng(seed)
        self.params: Dict[str, np.ndarray] = {}
        h1, h2 = self.hidden_dims
        for layer, (fan_in, fan_out, gain) in enumerate((
            (self.state_dim + self.action_dim, h1, np.sqrt(2.0)),
            (h1, h2, np.sqrt(2.0)), (h2, self.state_dim, 1.0),
        ), 1):
            weight = self._rng.standard_normal((fan_in, fan_out), dtype=np.float32)
            weight *= np.float32(gain / np.sqrt(fan_in))
            self.params[f"w{layer}"] = weight
            self.params[f"b{layer}"] = np.zeros(fan_out, dtype=np.float32)
        self._adam_m = {name: np.zeros_like(p) for name, p in self.params.items()}
        self._adam_v = {name: np.zeros_like(p) for name, p in self.params.items()}
        self.steps = 0
        self.last_grad_norm = 0.0
        self.last_mse, self.telemetry_path = None, telemetry_path

    @property
    def allocated_array_bytes(self) -> int:
        """Parametros e momentos persistentes; temporarios de treino nao incluidos."""
        return sum(p.nbytes for group in (self.params, self._adam_m, self._adam_v)
                   for p in group.values())

    def _phases(self, state: Any) -> np.ndarray:
        vector = np.asarray(state)
        if vector.shape != (self.state_dim,) or not np.iscomplexobj(vector):
            raise ValueError(f"Estado FHRR deve ser complexo, com shape ({self.state_dim},)")
        if not np.all(np.isfinite(vector)) or np.any(np.abs(vector) <= 1e-12):
            raise ValueError("Estado FHRR exige componentes finitas com fase definida")
        return np.angle(vector).astype(np.float32)

    def _encode_input(self, state: Any, action: Any) -> np.ndarray:
        phases = self._phases(state)
        if isinstance(action, str):
            key = action.strip().upper()
            if key not in self._action_indices:
                raise ValueError(f"Acao desconhecida: {action}")
            index = self._action_indices[key]
        elif isinstance(action, (int, np.integer)) and not isinstance(action, (bool, np.bool_)):
            index = int(action)
            if not 0 <= index < len(self.action_names):
                raise ValueError("Indice de acao fora do catalogo")
        else:
            raise ValueError("Acao deve ser rotulo ou indice inteiro do catalogo")
        features = np.zeros(self.state_dim + self.action_dim, dtype=np.float32)
        features[:self.state_dim] = phases
        features[self.state_dim + index] = 1.0
        return features

    def _forward(self, features: np.ndarray):
        p = self.params
        h1 = np.maximum(features @ p["w1"] + p["b1"], 0.0)
        h2 = np.maximum(h1 @ p["w2"] + p["b2"], 0.0)
        predicted = h2 @ p["w3"] + p["b3"]
        if not np.all(np.isfinite(predicted)):
            raise FloatingPointError("World Model produziu fases nao finitas")
        return predicted, (features, h1, h2)

    def predict(self, state: Any, action: Any) -> np.ndarray:
        """Preve state_dim fases em float32; nenhuma acao e executada."""
        with self._lock:
            predicted, _ = self._forward(self._encode_input(state, action))
            return predicted.copy()

    def predict_vector(self, state: Any, action: Any) -> np.ndarray:
        """Reconstrucao FHRR complex64 com modulo unitario."""
        return np.exp(1j * self.predict(state, action)).astype(np.complex64)

    def _loss_and_gradients(self, features: np.ndarray, target: np.ndarray):
        predicted, (x, h1, h2) = self._forward(features)
        error = predicted - target
        loss = float(np.mean(error.astype(np.float64) ** 2))
        output_gradient = (2.0 / self.state_dim) * error
        hidden2_gradient = (self.params["w3"] @ output_gradient) * (h2 > 0)
        hidden1_gradient = (self.params["w2"] @ hidden2_gradient) * (h1 > 0)
        grads = {
            "w1": np.outer(x, hidden1_gradient), "b1": hidden1_gradient,
            "w2": np.outer(h1, hidden2_gradient), "b2": hidden2_gradient,
            "w3": np.outer(h2, output_gradient), "b3": output_gradient,
        }
        if not np.isfinite(loss) or not all(np.all(np.isfinite(g)) for g in grads.values()):
            raise FloatingPointError("Loss ou gradiente nao finito no World Model")
        return loss, grads

    def train_step(self, state: Any, action: Any, next_state: Any) -> float:
        """Uma atualizacao supervisionada; descarta temporarios ao terminar."""
        with self._lock:
            features, target = self._encode_input(state, action), self._phases(next_state)
            loss, grads = self._loss_and_gradients(features, target)
            norm = float(np.sqrt(sum(np.einsum("i,i->", g.ravel(), g.ravel(), dtype=np.float64)
                                     for g in grads.values())))
            if not np.isfinite(norm):
                raise FloatingPointError("Norma de gradiente nao finita")
            scale = min(1.0, self.max_grad_norm / (norm + 1e-8))
            self.steps += 1
            for name, param in self.params.items():
                grad = (grads[name] * scale).astype(np.float32)
                m, v = self._adam_m[name], self._adam_v[name]
                m *= 0.9
                m += 0.1 * grad
                v *= 0.999
                v += 0.001 * grad * grad
                m_hat, v_hat = m / (1 - 0.9 ** self.steps), v / (1 - 0.999 ** self.steps)
                param -= self.learning_rate * m_hat / (np.sqrt(v_hat) + 1e-8)
            self.last_grad_norm = norm
            self.last_mse = float(loss)
            if self.telemetry_path is not None:
                write_training_status(self.telemetry_path, self.last_mse, self.steps)
            return loss
