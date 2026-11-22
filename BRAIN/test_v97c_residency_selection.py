from unittest.mock import Mock
from model_residency_manager import ModelResidencyManager, ModelSpec, Residency


def test_recommends_only_resident_with_evidence_without_loading():
    driver = Mock()
    manager = ModelResidencyManager(lambda: {'ram': 1000}, lambda inventory, spec: {'decision': 'APPROVED'})
    manager.register(ModelSpec('small', 'fast', driver, None, {}, 100))
    runtime = manager.models['small']
    assert manager.recommend_resident(roles=['fast'], context_tokens=100, max_latency_ms=200)['model'] is None
    runtime.state = Residency.HOT
    assert manager.recommend_resident(roles=['fast'], context_tokens=100, max_latency_ms=200)['model'] is None
    runtime.measured = {'context_tokens': 2048, 'latency_ms': 50}
    result = manager.recommend_resident(roles=['fast'], context_tokens=100, max_latency_ms=200)
    assert result['model'] == 'small' and not result['execution_authorized']
    driver.load.assert_not_called()
    driver.unload.assert_not_called()
    assert manager.recommend_resident(roles=['fast'], context_tokens=4096, max_latency_ms=200)['model'] is None


def test_rejects_unknown_resource_budget():
    driver = Mock()
    manager = ModelResidencyManager(lambda: {}, lambda inventory, spec: {'decision': 'INSUFFICIENT_EVIDENCE'})
    manager.register(ModelSpec('small', 'fast', driver, None, {}, 100))
    runtime = manager.models['small']
    runtime.state = Residency.HOT
    runtime.measured = {'context_tokens': 2048, 'latency_ms': 50}
    assert manager.recommend_resident(roles=['fast'], context_tokens=100, max_latency_ms=200)['model'] is None
    driver.unload.assert_not_called()
