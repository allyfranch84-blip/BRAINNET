from types import SimpleNamespace
from unittest.mock import Mock, patch

from p1_uia_diagnostic import diagnose
from test_v97r22_production import make_bridge


def bridge_with(context, scan):
    bridge = make_bridge()
    bridge._kernel.context_engine = SimpleNamespace(capture_foreground_context=context)
    bridge._kernel.eye = SimpleNamespace(scan_uia_properties=scan)
    return bridge


def test_chat_refuses_implicit_foreground_and_unavailable_scanner():
    foreground = Mock(return_value={'hwnd': 999, 'pid': 99})
    scan = Mock()
    bridge = bridge_with(foreground, scan)
    assert bridge.send_command('/uia scan')['status'] == 'TARGET_REQUIRED'
    foreground.assert_not_called()
    scan.assert_not_called()
    bridge._kernel.eye = None
    assert bridge.send_command('/uia scan 42 20')['status'] == 'UNAVAILABLE'


def test_chat_empty_list_never_claims_observed():
    window = {'pid': 20, 'started': 123.0, 'rect': (0, 0, 100, 100)}
    bridge = bridge_with(Mock(), Mock(return_value=[]))
    with patch('uia_chat_readonly.inspect_window', return_value=window), patch('perception_eye.HAS_UIA_NATIVE', True):
        result = bridge.send_command('/uia scan 42 20')
    assert result['status'] == 'EMPTY_OR_PROVIDER_UNAVAILABLE' and result['control_count'] == 0
    assert 'Nenhuma observação confirmada' in result['reply']


def test_chat_explicit_window_revalidates_and_redacts_names():
    window = {'pid': 20, 'started': 123.0, 'rect': (0, 0, 100, 100)}
    foreground = Mock(return_value={'hwnd': 999, 'pid': 99})
    scan = Mock(return_value=[{'name': 'CONFIDENCIAL', 'control_type': 'ButtonControl', 'rect': None}])
    bridge = bridge_with(foreground, scan)
    with patch('uia_chat_readonly.inspect_window', return_value=window) as check, patch('perception_eye.HAS_UIA_NATIVE', True):
        result = bridge.send_command('/uia scan 42 20')
    assert foreground.call_count == 0
    assert check.call_count == 2
    scan.assert_called_once_with(42, max_controls=100)
    assert result['status'] == 'OBSERVED'
    assert result['control_count'] == 1
    assert result['types'][0]['type'] == 'ButtonControl'
    assert 'CONFIDENCIAL' not in str(result)
    assert '42' in result['reply']


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
