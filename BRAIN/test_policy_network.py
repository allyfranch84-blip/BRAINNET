"""Verificacao numerica de PPO NumPy; nao executa acoes no Windows."""
import copy

import numpy as np
import pytest

from policy_network import PPOPolicy


def small(**kwargs):
    options = dict(observation_dim=3, hidden_dim=4, rollout_size=16,
                   minibatch_size=8, seed=17)
    options.update(kwargs)
    return PPOPolicy(**options)


def collect(policy, count=8):
    observation = np.ones(policy.observation_dim, dtype=np.float32)
    for _ in range(count):
        decision = policy.act(observation)
        actual = 0.2 if decision["action"] == 0 else 0.8
        policy.record_transition(observation, decision, observation,
                                 {"expected_delta": 0.2, "ncd_real": actual}, terminated=True)


def test_action_mask_and_probability():
    policy = small(action_names=("LOCATE", "TRANSFORM", "WAIT"))
    observation = np.zeros(3)
    for _ in range(10):
        decision = policy.act(observation, [False, True, False])
        assert decision["action"] == 1 and decision["action_name"] == "TRANSFORM"
        assert decision["log_prob"] == 0.0
        assert decision["confidence"] == 1.0
        assert not decision["needs_planner"]
    with pytest.raises(ValueError):
        policy.act(observation, [False, False, False])


@pytest.mark.parametrize("observation", [np.ones(2), [1.0, np.nan, 0.0], [0.0, np.inf, 1.0], np.ones(3, dtype=complex)])
def test_bad_observations_rejected(observation):
    with pytest.raises(ValueError):
        small().act(observation)


@pytest.mark.parametrize("result", [
    {"expected_delta": 0.2, "ncd_real": 0.5},
    (0, 1.0, "PID ausente", None, 0.5, 0.2),
])
def test_reward_uses_real_ncd_without_turning_it_into_success(result):
    assert PPOPolicy.reward_from_verifier(result) == pytest.approx(-0.09)


@pytest.mark.parametrize("actual", [None, np.nan, np.inf, True, 1e308])
def test_missing_or_invalid_ncd_does_not_create_training_evidence(actual):
    policy = small()
    observation = np.zeros(3)
    decision = policy.act(observation)
    with pytest.raises(ValueError):
        policy.record_transition(observation, decision, observation,
                                 {"ncd_real": actual, "expected_delta": 0.2})
    assert policy.buffer_size == 0


def test_gae_terminal_and_truncation_have_different_bootstraps():
    advantages, returns = PPOPolicy._compute_gae(
        np.array([1.0, 2.0, 3.0]), np.array([0.5, 0.6, 0.7]),
        np.array([0.6, 9.0, 99.0]), np.array([False, False, True]),
        np.array([False, True, False]), 0.9, 0.8,
    )
    np.testing.assert_allclose(advantages, [7.88, 9.5, 2.3])
    np.testing.assert_allclose(returns, [8.38, 10.1, 3.0])


def test_manual_gradients_match_central_finite_differences():
    policy = small(clip_value_loss=False, entropy_coef=0.07)
    # Float64 so the check measures derivatives rather than float32 rounding.
    policy.params = {key: value.astype(np.float64) for key, value in policy.params.items()}
    obs = np.array([[0.2, -0.4, 0.7], [0.5, 0.1, -0.3], [-0.3, 0.6, 0.1]])
    actions = np.array([0, 1, 0])
    masks = np.ones((3, 2), dtype=bool)
    logits, _ = policy._forward("actor", obs)
    _, logs, _, _ = policy._distribution(logits, masks)
    old_logs = logs[np.arange(3), actions].copy()
    values, _ = policy._forward("critic", obs)
    args = (obs, actions, old_logs, values[:, 0].copy(),
            np.array([0.4, -0.7, 0.2]), np.array([0.3, -0.2, 0.8]), masks)
    _, analytic = policy._loss_and_gradients(*args)
    epsilon = 1e-6
    for name, parameter in policy.params.items():
        for index in np.ndindex(parameter.shape):
            original = parameter[index]
            parameter[index] = original + epsilon
            positive = policy._loss_and_gradients(*args)[0]["loss"]
            parameter[index] = original - epsilon
            negative = policy._loss_and_gradients(*args)[0]["loss"]
            parameter[index] = original
            numeric = (positive - negative) / (2 * epsilon)
            assert analytic[name][index] == pytest.approx(numeric, rel=2e-4, abs=2e-7), (name, index)


@pytest.mark.parametrize("ratio, advantage", [(1.5, 1.0), (0.5, -1.0)])
def test_policy_clipping_stops_gradient_in_saturated_direction(ratio, advantage):
    policy = small(entropy_coef=0.0, value_coef=0.0)
    obs = np.ones((1, 3), dtype=np.float32)
    masks = np.ones((1, 2), dtype=bool)
    logits, _ = policy._forward("actor", obs)
    _, logs, _, _ = policy._distribution(logits, masks)
    _, grads = policy._loss_and_gradients(
        obs, np.array([0]), np.array([logs[0, 0] - np.log(ratio)]),
        np.zeros(1), np.array([advantage]), np.zeros(1), masks,
    )
    assert all(np.all(g == 0) for name, g in grads.items() if name.startswith("actor"))


def test_value_loss_clipping_stops_saturated_critic_gradient():
    policy = small(entropy_coef=0.0)
    obs = np.ones((1, 3), dtype=np.float32)
    masks = np.ones((1, 2), dtype=bool)
    logits, _ = policy._forward("actor", obs)
    _, logs, _, _ = policy._distribution(logits, masks)
    values, _ = policy._forward("critic", obs)
    metrics, grads = policy._loss_and_gradients(
        obs, np.array([0]), np.array([logs[0, 0]]), values[:, 0] - 1.0,
        np.zeros(1), values[:, 0] + 1.0, masks,
    )
    assert metrics["value_loss"] == pytest.approx(0.5 * 1.8 ** 2)
    assert all(np.all(g == 0) for name, g in grads.items() if name.startswith("critic"))


def test_adam_first_step_and_global_gradient_clipping():
    policy = small(max_grad_norm=0.5)
    old = {key: value.copy() for key, value in policy.params.items()}
    grads = {key: np.ones_like(value) for key, value in policy.params.items()}
    norm = policy._apply_gradients(grads)
    assert norm > policy.max_grad_norm
    clipped = 0.5 / (norm + 1e-8)
    expected_step = policy.learning_rate * clipped / (clipped + 1e-5)
    for name in policy.params:
        np.testing.assert_allclose(old[name] - policy.params[name], expected_step, rtol=2e-3, atol=1e-7)


def test_rollout_capacity_and_stale_or_greedy_decisions():
    policy = small(rollout_size=2)
    observation = np.ones(3)
    decision = policy.act(observation, deterministic=True)
    with pytest.raises(ValueError):
        policy.record_transition(observation, decision, observation, (1, 0, "", None, 0.2, 0.2))
    old_decision = policy.act(observation)
    collect(policy, 2)
    with pytest.raises(OverflowError):
        collect(policy, 1)
    policy.update()
    assert policy.buffer_size == 0
    with pytest.raises(ValueError):
        policy.record_transition(observation, old_decision, observation, (1, 0, "", None, 0.2, 0.2))


def test_synthetic_ncd_bandit_learns_better_primitive():
    policy = small(observation_dim=1, hidden_dim=8, rollout_size=64,
                   minibatch_size=32, learning_rate=0.01, entropy_coef=0.0,
                   target_kl=None, seed=9)
    observation = np.ones(1)
    initial = policy.act(observation, deterministic=True)["probabilities"][0]
    for _ in range(10):
        collect(policy, 64)
        metrics = policy.update()
        assert np.isfinite(metrics["loss"])
    final = policy.act(observation, deterministic=True)["probabilities"][0]
    assert final > 0.85 and final > initial + 0.3


def test_context_encoder_is_stable_goal_conditioned_and_reads_beta():
    policy = PPOPolicy()
    context = {"hwnd": 123, "pid": 10, "process_name": "brave.exe", "title": "Pesquisa",
               "window_rect": (0, 0, 1920, 1080), "start_menu_open": False}
    stats = {"alpha": 4.5, "beta": 0.5, "is_myelinated": True}
    first = policy.encode_context(context, "pesquisar clima", stats)
    second = policy.encode_context(context, "salvar documento", stats)
    np.testing.assert_array_equal(first, policy.encode_context(context, "pesquisar clima", stats))
    assert first.dtype == np.float32 and first.shape == (64,)
    assert not np.array_equal(first, second)
    assert first[11] == pytest.approx(0.9) and first[12] == pytest.approx(4 * 0.015)
    assert policy.allocated_array_bytes < 1024 * 1024


def test_checkpoint_restores_parameters_adam_and_rng(tmp_path):
    policy = small()
    collect(policy)
    policy.update()
    destination = tmp_path / "policy.npz"
    policy.save(destination)
    restored = PPOPolicy.load(destination)
    assert restored.policy_version == policy.policy_version
    assert restored._adam_step == policy._adam_step
    for name in policy.params:
        np.testing.assert_array_equal(restored.params[name], policy.params[name])
        np.testing.assert_array_equal(restored._adam_m[name], policy._adam_m[name])
        np.testing.assert_array_equal(restored._adam_v[name], policy._adam_v[name])
    for _ in range(5):
        assert policy.act(np.ones(3))["action"] == restored.act(np.ones(3))["action"]
    collect(restored, 2)
    with pytest.raises(ValueError):
        restored.save(destination)


def test_failed_update_rolls_back_and_keeps_rollout(monkeypatch):
    policy = small()
    collect(policy)
    original = copy.deepcopy(policy.params)
    real = policy._loss_and_gradients
    calls = 0

    def bad_loss(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise FloatingPointError("simulated failure after one optimizer step")
        return real(*args)

    monkeypatch.setattr(policy, "_loss_and_gradients", bad_loss)
    with pytest.raises(FloatingPointError):
        policy.update()
    assert policy.buffer_size == 8 and policy._adam_step == 0 and policy.policy_version == 0
    for name in original:
        np.testing.assert_array_equal(policy.params[name], original[name])


def test_target_kl_stops_optimizer_epochs():
    policy = small(target_kl=1e-12, learning_rate=0.05, entropy_coef=0.0)
    collect(policy, 16)
    metrics = policy.update()
    assert metrics["kl_early_stop"]
    assert metrics["gradient_steps"] < policy.update_epochs * 2
