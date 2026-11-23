from types import SimpleNamespace
from unittest.mock import Mock, patch

from p1_uia_diagnostic import diagnose
from test_v97r22_production import make_bridge


def bridge_with(context, scan):
    bridge = make_bridge()
    bridge._kernel.context_engine = SimpleNamespace(capture_foreground_context=context)
    bridge._kernel.eye = SimpleNamespace(scan_uia_properties=scan)
    return bridge


def test_real_handler_missing_window_and_provider_exception():
    scan = Mock()
    bridge = bridge_with(Mock(return_value={'hwnd': 0}), scan)
    assert bridge.send_command('/uia scan')['status'] == 'UNAVAILABLE'
    scan.assert_not_called()
    bridge = bridge_with(Mock(return_value={'hwnd': 42, 'pid': 20}), Mock(side_effect=OSError('fake')))
    assert bridge.send_command('/uia scan')['status'] == 'UNAVAILABLE'


def test_characterizes_existing_empty_list_false_observed():
    bridge = bridge_with(Mock(return_value={'hwnd': 42, 'pid': 20}), Mock(return_value=[]))
    result = bridge.send_command('/uia scan')
    # Characterization of a known defect: OBSERVED does not prove UIA evidence.
    assert result['status'] == 'OBSERVED' and result['controls'] == []
    assert 'lista vazia' in result['reply']


def test_characterizes_focus_captured_once_and_reply_omits_details():
    context = Mock(side_effect=[{'hwnd': 42, 'pid': 20}, {'hwnd': 99, 'pid': 30}])
    scan = Mock(return_value=[{'name': 'TESTE A', 'control_type': 'ButtonControl', 'rect': None}])
    result = bridge_with(context, scan).send_command('/uia scan')
    assert context.call_count == 1
    scan.assert_called_once_with(42, max_controls=100)
    assert result['controls'][0]['name'] == 'TESTE A'
    assert 'TESTE A' not in result['reply'] and '42' not in result['reply']


def test_diagnostic_distinguishes_missing_target_provider_empty_and_error():
    window = {'pid': 20, 'started': 123, 'controlled': True}
    scan = Mock(return_value=[])
    assert diagnose(42, 20, inspect=lambda _: None, scan=scan, provider_available=True)['status'] == 'TARGET_INVALID'
    assert diagnose(42, 20, inspect=lambda _: window, scan=scan, provider_available=False)['status'] == 'PROVIDER_UNAVAILABLE'
    result = diagnose(42, 20, inspect=lambda _: window, scan=scan, provider_available=True)
    assert result['status'] == 'EMPTY_OR_PROVIDER_UNAVAILABLE' and result['control_count'] == 0
    result = diagnose(42, 20, inspect=lambda _: window, scan=Mock(side_effect=RuntimeError()), provider_available=True)
    assert result['status'] == 'ERROR' and result['reason'] == 'RuntimeError'


def test_diagnostic_context_change_and_private_fields():
    window = {'pid': 20, 'started': 123, 'controlled': True}
    scan = Mock(return_value=[{'name': 'confidencial', 'control_type': 'ButtonControl', 'rect': (1, 2, 3, 4)}])
    result = diagnose(42, 20, inspect=lambda _: window, scan=scan, provider_available=True)
    assert result['status'] == 'OBSERVED' and result['control_count'] == 1
    assert 'name' not in result['examples'][0] and 'confidencial' not in str(result)
    result = diagnose(42, 20, inspect=Mock(side_effect=[window, {**window, 'started': 124}]),
                      scan=scan, provider_available=True)
    assert result['status'] == 'CONTEXT_CHANGED' and 'examples' not in result


def test_diagnostic_missing_fields_never_claims_evidence():
    window = {'pid': 20, 'started': 123, 'controlled': True}
    result = diagnose(42, 20, inspect=lambda _: window, scan=lambda _: [{}], provider_available=True)
    assert result['status'] == 'INSUFFICIENT_EVIDENCE'
    assert result['uia_provider_status'] == 'UNKNOWN'


def test_existing_provider_flag_returns_empty_indistinguishably():
    import perception_eye
    eye = perception_eye.PerceptionEye.__new__(perception_eye.PerceptionEye)
    with patch.object(perception_eye, 'HAS_UIA_NATIVE', False):
        assert eye.scan_uia_properties(42) == []
