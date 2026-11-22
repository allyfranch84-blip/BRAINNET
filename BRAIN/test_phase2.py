"""World Model NumPy: aprendizado sintetico e derivadas numericas."""
import numpy as np
import pytest

from world_model import WorldModel


def test_world_model_default_loss_decreases_after_ten_steps():
    model = WorldModel(seed=42)
    rng = np.random.default_rng(19)
    phases = rng.uniform(-np.pi, np.pi, 10_000).astype(np.float32)
    state = np.exp(1j * phases).astype(np.complex64)
    next_state = np.exp(1j * (phases + 0.2)).astype(np.complex64)
    target = np.angle(next_state)
    initial = float(np.mean((model.predict(state, "TRANSFORM") - target) ** 2))
    for _ in range(10):
        assert np.isfinite(model.train_step(state, "TRANSFORM", next_state))
    predicted = model.predict(state, "TRANSFORM")
    final = float(np.mean((predicted - target) ** 2))
    print(f"World Model MSE: {initial:.6f} -> {final:.6f} apos 10 iteracoes")
    assert final < initial
    assert model.steps == 10
    assert predicted.shape == (10_000,) and predicted.dtype == np.float32
    assert model.params["w1"].shape == (10_064, 512)
    assert model.params["w2"].shape == (512, 256)
    assert model.params["w3"].shape == (256, 10_000)
    assert all(p.dtype == np.float32 and np.all(np.isfinite(p)) for p in model.params.values())
    assert model.allocated_array_bytes < 100 * 1024 * 1024


def tiny():
    return WorldModel(state_dim=3, action_dim=4, hidden_dims=(4, 3),
                      action_names=("LOCATE", "TRANSFORM", "WAIT"), seed=5)


def test_world_model_input_is_exact_phases_and_one_hot():
    model = tiny()
    state = np.exp(1j * np.array([0.2, -0.4, 0.8])).astype(np.complex64)
    features = model._encode_input(state, "WAIT")
    np.testing.assert_array_equal(features[:3], np.angle(state))
    np.testing.assert_array_equal(features[3:], [0, 0, 1, 0])
    np.testing.assert_array_equal(model.predict(state, "WAIT"), model.predict(state, 2))
    vector = model.predict_vector(state, "WAIT")
    assert vector.dtype == np.complex64
    np.testing.assert_allclose(np.abs(vector), 1.0, atol=1e-6)


def test_world_model_gradients_match_finite_differences():
    model = tiny()
    model.params = {name: p.astype(np.float64) for name, p in model.params.items()}
    state = np.exp(1j * np.array([0.2, -0.4, 0.8]))
    features = model._encode_input(state, "LOCATE")
    target = np.array([0.1, -0.5, 0.3], dtype=np.float64)
    _, analytic = model._loss_and_gradients(features, target)
    for name in ("w1", "w2", "w3"):
        assert np.any(np.abs(analytic[name]) > 1e-12)
    epsilon = 1e-6
    for name, parameter in model.params.items():
        for index in np.ndindex(parameter.shape):
            original = parameter[index]
            parameter[index] = original + epsilon
            positive = model._loss_and_gradients(features, target)[0]
            parameter[index] = original - epsilon
            negative = model._loss_and_gradients(features, target)[0]
            parameter[index] = original
            assert analytic[name][index] == pytest.approx((positive - negative) / (2 * epsilon), rel=1e-4, abs=1e-7)


@pytest.mark.parametrize("state", [np.ones(3), np.ones(2, dtype=complex),
                                   np.zeros(3, dtype=complex), np.array([1, 1, np.nan], dtype=complex)])
def test_world_model_rejects_invalid_state(state):
    with pytest.raises(ValueError):
        tiny().predict(state, "WAIT")


@pytest.mark.parametrize("action", ["UNKNOWN", -1, 3, True])
def test_world_model_rejects_invalid_action_without_updating(action):
    model = tiny()
    state = np.ones(3, dtype=np.complex64)
    before = {name: p.copy() for name, p in model.params.items()}
    with pytest.raises(ValueError):
        model.train_step(state, action, state)
    assert model.steps == 0
    for name, p in before.items():
        np.testing.assert_array_equal(model.params[name], p)
