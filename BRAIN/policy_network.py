"""PPO discreto em NumPy para BRAINNET; nao executa acoes nem confirma sucesso.

Referencia algoritmica: https://github.com/vwxyzjn/cleanrl/blob/master/cleanrl/ppo.py
Reimplementacao com backpropagation explicito, buffers limitados e adapters locais.
O controlador fornece observacoes, mapeia rotulos para primitivas e aplica as
travas factuais. Uma escolha do LLM substituindo a politica nao e dado on-policy.

MIT License -- Copyright (c) 2019 CleanRL developers
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
from __future__ import annotations

from collections.abc import Mapping
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from threading import RLock
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np


class PPOPolicy:
    """Actor/critic separados, dois hidden layers tanh e Adam, todos float32.

    Uso: encode_context -> act -> controlador/verificador -> record_transition.
    update consome um rollout; terminated zera bootstrap, truncated somente
    interrompe GAE. next_observation deve ser o estado final, antes de um reset.
    Os rotulos LOCATE/TRANSFORM sao abstratos: o controlador define o executor.
    """

    def __init__(
        self, observation_dim: int = 64,
        action_names: Sequence[str] = ("LOCATE", "TRANSFORM"),
        hidden_dim: int = 64, rollout_size: int = 256,
        learning_rate: float = 3e-4, gamma: float = 0.99,
        gae_lambda: float = 0.95, clip_coef: float = 0.2,
        value_coef: float = 0.5, entropy_coef: float = 0.01,
        max_grad_norm: float = 0.5, update_epochs: int = 4,
        minibatch_size: int = 64, target_kl: Optional[float] = 0.02,
        normalize_advantages: bool = True, clip_value_loss: bool = True,
        min_confidence: float = 0.6, seed: int = 42,
    ) -> None:
        for name, number in (("observation_dim", observation_dim), ("hidden_dim", hidden_dim),
                             ("rollout_size", rollout_size), ("update_epochs", update_epochs),
                             ("minibatch_size", minibatch_size)):
            if isinstance(number, bool) or not isinstance(number, (int, np.integer)) or number < 1:
                raise ValueError(f"{name} deve ser inteiro positivo")
        if rollout_size < 2:
            raise ValueError("rollout_size deve ser >= 2")
        if isinstance(action_names, str):
            raise ValueError("action_names deve ser sequencia de rotulos")
        self.action_names = tuple(action_names)
        if any(not isinstance(name, str) or not name.strip() for name in self.action_names):
            raise ValueError("Rotulos de acao devem ser strings nao vazias")
        if len(set(self.action_names)) != len(self.action_names) or len(self.action_names) < 2:
            raise ValueError("Defina ao menos duas acoes distintas")
        numbers = [learning_rate, gamma, gae_lambda, clip_coef, value_coef, entropy_coef,
                   max_grad_norm, min_confidence]
        if not np.all(np.isfinite(numbers)):
            raise ValueError("Hiperparametros devem ser finitos")
        if learning_rate <= 0 or max_grad_norm <= 0 or not 0 < clip_coef < 1:
            raise ValueError("learning_rate/max_grad_norm positivos e 0 < clip_coef < 1")
        if not 0 <= gamma <= 1 or not 0 <= gae_lambda <= 1 or not 0 <= min_confidence <= 1:
            raise ValueError("gamma, gae_lambda e min_confidence devem estar em [0, 1]")
        if value_coef < 0 or entropy_coef < 0:
            raise ValueError("Coeficientes de loss nao podem ser negativos")
        if target_kl is not None and (not np.isfinite(target_kl) or target_kl <= 0):
            raise ValueError("target_kl deve ser positivo ou None")
        self.observation_dim, self.hidden_dim = int(observation_dim), int(hidden_dim)
        self.rollout_size, self.num_actions = int(rollout_size), len(self.action_names)
        self.learning_rate, self.gamma, self.gae_lambda = learning_rate, gamma, gae_lambda
        self.clip_coef, self.value_coef, self.entropy_coef = clip_coef, value_coef, entropy_coef
        self.max_grad_norm, self.update_epochs = max_grad_norm, int(update_epochs)
        self.minibatch_size, self.target_kl = int(minibatch_size), target_kl
        self.normalize_advantages, self.clip_value_loss = normalize_advantages, clip_value_loss
        self.min_confidence = min_confidence
        self._rng, self._lock = np.random.default_rng(seed), RLock()
        self._config = {
            "observation_dim": int(observation_dim), "action_names": list(self.action_names),
            "hidden_dim": int(hidden_dim), "rollout_size": int(rollout_size),
            "learning_rate": learning_rate, "gamma": gamma, "gae_lambda": gae_lambda,
            "clip_coef": clip_coef, "value_coef": value_coef, "entropy_coef": entropy_coef,
            "max_grad_norm": max_grad_norm, "update_epochs": int(update_epochs),
            "minibatch_size": int(minibatch_size), "target_kl": target_kl,
            "normalize_advantages": normalize_advantages, "clip_value_loss": clip_value_loss,
            "min_confidence": min_confidence, "seed": int(seed),
        }
        self.params: Dict[str, np.ndarray] = {}
        for prefix, output, gain in (("actor", self.num_actions, 0.01), ("critic", 1, 1.0)):
            for layer, (rows, cols, scale) in enumerate((
                (self.observation_dim, self.hidden_dim, np.sqrt(2)),
                (self.hidden_dim, self.hidden_dim, np.sqrt(2)),
                (self.hidden_dim, output, gain),
            ), 1):
                self.params[f"{prefix}_w{layer}"] = self._orthogonal(rows, cols, scale)
                self.params[f"{prefix}_b{layer}"] = np.zeros(cols, dtype=np.float32)
        self._adam_m = {key: np.zeros_like(value) for key, value in self.params.items()}
        self._adam_v = {key: np.zeros_like(value) for key, value in self.params.items()}
        self._adam_step = self.policy_version = self._count = 0
        self._obs = np.empty((self.rollout_size, self.observation_dim), dtype=np.float32)
        self._masks = np.empty((self.rollout_size, self.num_actions), dtype=bool)
        self._actions = np.empty(self.rollout_size, dtype=np.int64)
        self._old_logs = np.empty(self.rollout_size, dtype=np.float32)
        self._values = np.empty(self.rollout_size, dtype=np.float32)
        self._next_values = np.empty(self.rollout_size, dtype=np.float32)
        self._rewards = np.empty(self.rollout_size, dtype=np.float32)
        self._terminated = np.empty(self.rollout_size, dtype=bool)
        self._truncated = np.empty(self.rollout_size, dtype=bool)

    def _orthogonal(self, rows: int, cols: int, gain: float) -> np.ndarray:
        matrix = self._rng.normal(size=(max(rows, cols), min(rows, cols)))
        q, r = np.linalg.qr(matrix)
        q *= np.where(np.diag(r) >= 0, 1.0, -1.0)
        return (gain * (q if rows >= cols else q.T)).astype(np.float32)

    @property
    def buffer_size(self) -> int:
        return self._count

    @property
    def allocated_array_bytes(self) -> int:
        """Arrays persistentes; exclui temporarios de treino e overhead Python."""
        arrays = [self._obs, self._masks, self._actions, self._old_logs, self._values,
                  self._next_values, self._rewards, self._terminated, self._truncated]
        arrays += list(self.params.values()) + list(self._adam_m.values()) + list(self._adam_v.values())
        return sum(array.nbytes for array in arrays)

    def _observation(self, observation: Any) -> np.ndarray:
        if np.iscomplexobj(observation):
            raise ValueError("Projete o FHRR complexo em features reais antes da politica")
        x = np.asarray(observation, dtype=np.float32)
        if x.shape != (self.observation_dim,) or not np.all(np.isfinite(x)):
            raise ValueError(f"Observacao deve ter shape ({self.observation_dim},) e valores finitos")
        return x

    def _mask(self, mask: Any = None) -> np.ndarray:
        if mask is None:
            return np.ones(self.num_actions, dtype=bool)
        result = np.asarray(mask)
        if result.shape != (self.num_actions,) or result.dtype != np.bool_ or not result.any():
            raise ValueError("action_mask deve ser bool, ter uma posicao por acao e permitir ao menos uma")
        return result.copy()

    def _forward(self, prefix: str, x: np.ndarray):
        p = self.params
        h1 = np.tanh(x @ p[f"{prefix}_w1"] + p[f"{prefix}_b1"])
        h2 = np.tanh(h1 @ p[f"{prefix}_w2"] + p[f"{prefix}_b2"])
        output = h2 @ p[f"{prefix}_w3"] + p[f"{prefix}_b3"]
        return output, (x, h1, h2)

    @staticmethod
    def _distribution(logits: np.ndarray, masks: np.ndarray):
        masked = np.where(masks, logits, -np.inf)
        shifted = masked - masked.max(axis=1, keepdims=True)
        logs = shifted - np.log(np.exp(shifted).sum(axis=1, keepdims=True))
        probs = np.exp(logs)
        safe_logs = np.where(masks, logs, 0.0)
        entropy = -(probs * safe_logs).sum(axis=1)
        return probs, logs, safe_logs, entropy

    def act(self, observation: Any, action_mask: Any = None, deterministic: bool = False) -> Dict[str, Any]:
        """Retorna uma sugestao; needs_planner nao chama o 7B automaticamente."""
        with self._lock:
            x, mask = self._observation(observation), self._mask(action_mask)
            logits, _ = self._forward("actor", x[None, :])
            probs, logs, _, _ = self._distribution(logits, mask[None, :])
            value, _ = self._forward("critic", x[None, :])
            if not np.all(np.isfinite(probs)) or not np.all(np.isfinite(value)):
                raise FloatingPointError("Inferencia nao finita")
            action = int(np.argmax(probs[0])) if deterministic else int(self._rng.choice(self.num_actions, p=probs[0].astype(np.float64) / probs[0].sum(dtype=np.float64)))
            confidence = float(probs[0, action])
            return {"action": action, "action_name": self.action_names[action],
                    "log_prob": float(logs[0, action]), "value": float(value[0, 0]),
                    "confidence": confidence, "needs_planner": confidence < self.min_confidence,
                    "policy_version": self.policy_version, "deterministic": bool(deterministic),
                    "action_mask": mask, "probabilities": probs[0].copy()}

    @staticmethod
    def reward_from_verifier(result: Any) -> float:
        """Aceita feedback de execute_subgoal ou a tupla de measure_collapse.

        Reward nao substitui lambda_obs/PID/HWND e nao mieliniza o P-DAG.
        Falta de medicao (por exemplo ACTION_EXCEPTION) nao vira reward inventado.
        """
        if isinstance(result, Mapping):
            actual, expected = result.get("ncd_real"), result.get("expected_delta")
        elif isinstance(result, (tuple, list)) and len(result) == 6:
            actual, expected = result[4], result[5]
        else:
            raise ValueError("Feedback deve conter NCD real e esperado do verificador")
        if actual is None or expected is None or isinstance(actual, (bool, np.bool_)) or isinstance(expected, (bool, np.bool_)):
            raise ValueError("Nao ha medicao NCD numerica utilizavel")
        actual, expected = float(actual), float(expected)
        if not np.isfinite(actual) or not np.isfinite(expected) or not 0 <= expected <= 1:
            raise ValueError("NCD deve ser finito e expected_delta deve estar em [0, 1]")
        difference = expected - actual
        if not np.isfinite(difference) or abs(difference) > float(np.sqrt(np.finfo(np.float32).max)):
            raise ValueError("Reward fora da faixa float32")
        reward = -(difference ** 2)
        return float(reward)

    def record_transition(
        self, observation: Any, decision: Mapping, next_observation: Any,
        verifier_result: Any, terminated: bool = False, truncated: bool = False,
    ) -> float:
        """Guarda uma transicao on-policy; nao registra escolhas substituidas pelo LLM."""
        with self._lock:
            if self._count >= self.rollout_size:
                raise OverflowError("Rollout cheio: execute update ou discard_rollout")
            if decision.get("policy_version") != self.policy_version or decision.get("deterministic") is not False:
                raise ValueError("A transicao exige uma decisao estocastica da versao atual")
            if not isinstance(terminated, (bool, np.bool_)) or not isinstance(truncated, (bool, np.bool_)):
                raise ValueError("terminated e truncated devem ser bool")
            action = decision.get("action")
            if isinstance(action, bool) or not isinstance(action, (int, np.integer)) or not 0 <= action < self.num_actions:
                raise ValueError("Indice de acao invalido")
            x, next_x = self._observation(observation), self._observation(next_observation)
            mask = self._mask(decision.get("action_mask"))
            if not mask[action]:
                raise ValueError("Acao nao permitida pela mascara")
            logits, _ = self._forward("actor", x[None, :])
            _, logs, _, _ = self._distribution(logits, mask[None, :])
            value, _ = self._forward("critic", x[None, :])
            if not np.isclose(decision.get("log_prob", np.nan), logs[0, action], rtol=1e-5, atol=1e-6) or not np.isclose(decision.get("value", np.nan), value[0, 0], rtol=1e-5, atol=1e-6):
                raise ValueError("Observacao, log_prob ou value nao correspondem a politica de coleta")
            reward = self.reward_from_verifier(verifier_result)
            next_value, _ = self._forward("critic", next_x[None, :])
            if not np.all(np.isfinite(next_value)):
                raise FloatingPointError("Bootstrap nao finito")
            i = self._count
            self._obs[i], self._masks[i], self._actions[i] = x, mask, action
            self._old_logs[i], self._values[i] = logs[0, action], value[0, 0]
            self._next_values[i], self._rewards[i] = 0.0 if terminated else next_value[0, 0], reward
            self._terminated[i], self._truncated[i] = terminated, truncated
            self._count += 1
            return reward

    @staticmethod
    def _compute_gae(rewards, values, next_values, terminated, truncated, gamma, gae_lambda):
        advantages = np.zeros(len(rewards), dtype=np.float64)
        carry = 0.0
        for i in range(len(rewards) - 1, -1, -1):
            bootstrap = 0.0 if terminated[i] else float(next_values[i])
            delta = float(rewards[i]) + gamma * bootstrap - float(values[i])
            carry = delta + gamma * gae_lambda * (not (terminated[i] or truncated[i])) * carry
            advantages[i] = carry
        return advantages, advantages + values

    def _backward(self, prefix: str, cache, output_gradient: np.ndarray):
        x, h1, h2 = cache
        p = self.params
        dz2 = (output_gradient @ p[f"{prefix}_w3"].T) * (1 - h2 ** 2)
        dz1 = (dz2 @ p[f"{prefix}_w2"].T) * (1 - h1 ** 2)
        return {f"{prefix}_w3": h2.T @ output_gradient,
                f"{prefix}_b3": output_gradient.sum(axis=0),
                f"{prefix}_w2": h1.T @ dz2, f"{prefix}_b2": dz2.sum(axis=0),
                f"{prefix}_w1": x.T @ dz1, f"{prefix}_b1": dz1.sum(axis=0)}

    def _loss_and_gradients(self, obs, actions, old_logs, old_values, advantages, returns, masks):
        logits, actor_cache = self._forward("actor", obs)
        values, critic_cache = self._forward("critic", obs)
        values = values[:, 0]
        probs, logs, safe_logs, entropy = self._distribution(logits, masks)
        rows = np.arange(len(obs))
        log_ratio = logs[rows, actions].astype(np.float64) - old_logs
        with np.errstate(over="raise", invalid="raise"):
            ratios = np.exp(log_ratio)
        clipped = np.clip(ratios, 1 - self.clip_coef, 1 + self.clip_coef)
        policy_loss = -np.minimum(ratios * advantages, clipped * advantages).mean()
        active = ((advantages >= 0) & (ratios <= 1 + self.clip_coef)) | ((advantages < 0) & (ratios >= 1 - self.clip_coef))
        score_gradient = -probs.copy()
        score_gradient[rows, actions] += 1.0
        actor_gradient = score_gradient * (-advantages * ratios * active / len(obs))[:, None]
        actor_gradient += self.entropy_coef * probs * (safe_logs + entropy[:, None]) / len(obs)
        actor_gradient = np.where(masks, actor_gradient, 0.0)
        error = values - returns
        if self.clip_value_loss:
            displacement = values - old_values
            clipped_values = old_values + np.clip(displacement, -self.clip_coef, self.clip_coef)
            clipped_error = clipped_values - returns
            use_unclipped = error ** 2 >= clipped_error ** 2
            value_loss = 0.5 * np.maximum(error ** 2, clipped_error ** 2).mean()
            value_gradient = np.where(use_unclipped, error, clipped_error * (np.abs(displacement) <= self.clip_coef))
        else:
            value_loss, value_gradient = 0.5 * (error ** 2).mean(), error
        grads = self._backward("actor", actor_cache, actor_gradient)
        grads.update(self._backward("critic", critic_cache, (self.value_coef * value_gradient / len(obs))[:, None]))
        metrics = {"loss": float(policy_loss + self.value_coef * value_loss - self.entropy_coef * entropy.mean()),
                   "policy_loss": float(policy_loss), "value_loss": float(value_loss),
                   "entropy": float(entropy.mean()),
                   "approx_kl": float(np.mean((ratios - 1.0) - log_ratio)),
                   "clip_fraction": float(np.mean(np.abs(ratios - 1.0) > self.clip_coef))}
        if not all(np.isfinite(value) for value in metrics.values()) or not all(np.all(np.isfinite(g)) for g in grads.values()):
            raise FloatingPointError("Loss ou gradiente nao finito")
        return metrics, grads

    def _apply_gradients(self, grads: Dict[str, np.ndarray]) -> float:
        norm = float(np.sqrt(sum(np.square(g.astype(np.float64)).sum() for g in grads.values())))
        if not np.isfinite(norm):
            raise FloatingPointError("Norma do gradiente nao finita")
        scale = min(1.0, self.max_grad_norm / (norm + 1e-8))
        self._adam_step += 1
        for key in self.params:
            g = (grads[key] * scale).astype(np.float32)
            m, v = self._adam_m[key], self._adam_v[key]
            m *= 0.9
            m += 0.1 * g
            v *= 0.999
            v += 0.001 * g * g
            m_hat, v_hat = m / (1 - 0.9 ** self._adam_step), v / (1 - 0.999 ** self._adam_step)
            self.params[key] -= self.learning_rate * m_hat / (np.sqrt(v_hat) + 1e-5)
        if not all(np.all(np.isfinite(p)) for p in self.params.values()):
            raise FloatingPointError("Adam produziu parametros nao finitos")
        return norm

    def update(self) -> Dict[str, Any]:
        """Treina somente o rollout atual. Erros restauram modelo/Adam e preservam dados."""
        with self._lock:
            n = self._count
            if n < 2:
                raise ValueError("PPO exige ao menos duas transicoes")
            advantages, returns = self._compute_gae(
                self._rewards[:n], self._values[:n], self._next_values[:n],
                self._terminated[:n], self._truncated[:n], self.gamma, self.gae_lambda,
            )
            if self.normalize_advantages:
                advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
            backup = [{key: value.copy() for key, value in group.items()}
                      for group in (self.params, self._adam_m, self._adam_v)]
            old_step, rng_state = self._adam_step, copy.deepcopy(self._rng.bit_generator.state)
            steps, epochs, grad_norm, stopped = 0, 0, 0.0, False
            try:
                for _ in range(self.update_epochs):
                    indices = self._rng.permutation(n)
                    for start in range(0, n, self.minibatch_size):
                        batch = indices[start:start + self.minibatch_size]
                        metrics, grads = self._loss_and_gradients(
                            self._obs[batch], self._actions[batch], self._old_logs[batch],
                            self._values[batch], advantages[batch], returns[batch], self._masks[batch],
                        )
                        if self.target_kl is not None and metrics["approx_kl"] > self.target_kl:
                            stopped = True
                            break
                        grad_norm = max(grad_norm, self._apply_gradients(grads))
                        steps += 1
                    if stopped:
                        break
                    epochs += 1
                metrics, _ = self._loss_and_gradients(
                    self._obs[:n], self._actions[:n], self._old_logs[:n], self._values[:n],
                    advantages, returns, self._masks[:n],
                )
                predicted, _ = self._forward("critic", self._obs[:n])
                variance = float(np.var(returns))
                explained = float(1 - np.var(returns - predicted[:, 0]) / variance) if variance > 1e-12 else None
            except Exception:
                self.params, self._adam_m, self._adam_v = backup
                self._adam_step, self._rng.bit_generator.state = old_step, rng_state
                raise
            self._count = 0
            self.policy_version += 1
            metrics.update(samples=n, gradient_steps=steps, epochs_completed=epochs,
                           grad_norm=grad_norm, kl_early_stop=stopped, explained_variance=explained)
            return metrics

    def discard_rollout(self) -> None:
        with self._lock:
            self._count = 0

    def encode_context(self, context: Mapping, intent: str = "", pdag_stats: Optional[Mapping] = None) -> np.ndarray:
        """Codifica ContextCapture + objetivo + __meta__ do P-DAG, sem Win32/LLM.

        Features fixas evitam alterar a normalizacao durante o rollout. P-DAG
        fornece alpha/beta/is_myelinated; suas rotas antigas nao sao rollouts PPO.
        """
        if self.observation_dim < 17:
            raise ValueError("encode_context exige observation_dim >= 17")
        features = np.zeros(self.observation_dim, dtype=np.float32)
        rect = np.asarray(context.get("window_rect", (0, 0, 0, 0)), dtype=np.float64)
        if rect.shape != (4,) or not np.all(np.isfinite(rect)):
            raise ValueError("window_rect deve conter quatro coordenadas finitas")
        features[0:3] = [bool(context.get("hwnd")), bool(context.get("pid")), bool(context.get("start_menu_open"))]
        features[3:7] = np.clip(rect / 8192.0, -1.0, 1.0)
        features[7:9] = np.clip([(rect[2] - rect[0]) / 8192.0, (rect[3] - rect[1]) / 8192.0], 0, 1)
        title = str(context.get("title", ""))[:256]
        features[9:11] = [len(title) / 256.0, bool(context.get("executable_path"))]
        if pdag_stats is not None:
            a, b = float(pdag_stats.get("alpha", 0.5)), float(pdag_stats.get("beta", 0.5))
            if not np.isfinite(a + b) or a <= 0 or b <= 0:
                raise ValueError("Parametros Beta do P-DAG devem ser positivos e finitos")
            total = a + b
            features[11:16] = [a / total, 4 * (a / total) * (b / total) / (total + 1),
                               bool(pdag_stats.get("is_myelinated")), min(1.0, np.log1p(total) / 16), 1.0]
        sources = {"process": str(context.get("process_name", ""))[:128], "title": title, "intent": str(intent)[:512]}
        for prefix, text in sources.items():
            for token in re.findall(r"\w+", text.casefold()):
                digest = int.from_bytes(hashlib.blake2b(f"{prefix}:{token}".encode("utf-8"), digest_size=8).digest(), "little")
                features[16 + (digest >> 1) % (self.observation_dim - 16)] += 1.0 if digest & 1 else -1.0
        norm = np.linalg.norm(features[16:])
        if norm > 0:
            features[16:] /= norm
        return features

    def save(self, path: Any) -> None:
        """Checkpoint atomico, sem pickle; salve entre rollouts."""
        with self._lock:
            if self._count:
                raise ValueError("Finalize ou descarte o rollout antes do checkpoint")
            destination = Path(path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            metadata = {"format_version": 1, "config": self._config,
                        "policy_version": self.policy_version, "adam_step": self._adam_step,
                        "rng_state": self._rng.bit_generator.state}
            arrays = {f"{prefix}:{key}": array for prefix, group in
                      (("param", self.params), ("m", self._adam_m), ("v", self._adam_v))
                      for key, array in group.items()}
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".npz", delete=False) as handle:
                    temporary = Path(handle.name)
                    np.savez(handle, metadata=np.array(json.dumps(metadata)), **arrays)
                os.replace(temporary, destination)
            finally:
                if temporary is not None and temporary.exists():
                    temporary.unlink()

    @classmethod
    def load(cls, path: Any) -> "PPOPolicy":
        with np.load(path, allow_pickle=False) as archive:
            metadata = json.loads(str(archive["metadata"].item()))
            if metadata.get("format_version") != 1:
                raise ValueError("Versao de checkpoint nao suportada")
            policy = cls(**metadata["config"])
            for prefix, group in (("param", policy.params), ("m", policy._adam_m), ("v", policy._adam_v)):
                for key, target in group.items():
                    value = archive[f"{prefix}:{key}"]
                    if value.shape != target.shape or value.dtype != np.float32 or not np.all(np.isfinite(value)):
                        raise ValueError(f"Array invalido no checkpoint: {prefix}:{key}")
                    if prefix == "v" and np.any(value < 0):
                        raise ValueError("Segundo momento de Adam nao pode ser negativo")
                    target[:] = value
            policy.policy_version, policy._adam_step = metadata["policy_version"], metadata["adam_step"]
            if any(isinstance(value, bool) or not isinstance(value, int) or value < 0
                   for value in (policy.policy_version, policy._adam_step)):
                raise ValueError("Contadores invalidos no checkpoint")
            policy._rng.bit_generator.state = metadata["rng_state"]
        return policy
