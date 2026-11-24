"""Deterministic tests only. No Windows, GUI, microphone or physical actuator."""
import os
import struct
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch

from uia_chat_readonly import chat_reply, scan_explicit_window


class ReadonlyUIAContractTests(unittest.TestCase):
    def setUp(self):
        self.window = {'hwnd': 42, 'pid': 2341, 'started': 12345.125, 'rect': (10, 20, 400, 300)}
        self.inspector = Mock(return_value=self.window)
        self.scanner = Mock(return_value=[
            {'name': 'segredo', 'automation_id': 'hidden-identifier',
             'control_type': 'EditControl', 'rect': (10, 30, 80, 70)},
            {'name': 'outro segredo', 'control_type': 'ButtonControl', 'rect': None},
        ])

    def read(self, *, inspector=None, scanner=None, available=True, hwnd=42, pid=2341):
        return scan_explicit_window(
            hwnd, pid, scanner=scanner or self.scanner, inspector=inspector or self.inspector,
            provider_available=available)

    def test_valid_observation_is_bounded_read_only_and_redacted(self):
        result = self.read()
        self.assertEqual(result['status'], 'OBSERVED')
        self.assertEqual(result['control_count'], 2)
        self.assertEqual(result['types'][0]['type'], 'EditControl')
        self.scanner.assert_called_once_with(42, max_controls=100, include_sensitive=False)
        self.assertEqual(self.inspector.call_count, 2)
        self.assertFalse(result['execution_authorized'])
        self.assertNotIn('segredo', str(result))
        self.assertNotIn('hidden-identifier', str(result))
        self.assertIn('EditControl', chat_reply(result))
        self.assertIn('HWND 42', chat_reply(result))
        self.assertNotIn('segredo', chat_reply(result))

    def test_not_a_foreground_scan_and_not_an_action(self):
        self.read()
        self.assertEqual(self.inspector.call_args_list[0].args, (42,))
        self.assertEqual(self.inspector.call_args_list[1].args, (42,))

    def test_no_target_or_wrong_pid_refuses_before_uia(self):
        for hwnd, pid in [(0, 2341), (-1, 2341), (42, 0), (42, -1), (True, 2341), (42, False),
                          (42, 9999), (2 ** (8 * struct.calcsize('P')), 2341), (42, 2 ** 32)]:
            with self.subTest(hwnd=hwnd, pid=pid):
                result = self.read(hwnd=hwnd, pid=pid)
                self.assertEqual(result['status'], 'TARGET_INVALID')
        self.scanner.assert_not_called()

    def test_self_process_is_rejected(self):
        result = self.read(pid=os.getpid())
        self.assertEqual(result['status'], 'TARGET_INVALID')
        self.scanner.assert_not_called()

    def test_missing_provider_is_explicit(self):
        result = self.read(available=False)
        self.assertEqual(result['status'], 'PROVIDER_UNAVAILABLE')
        self.scanner.assert_not_called()

    def test_empty_scan_is_not_observed(self):
        self.scanner.return_value = []
        result = self.read()
        self.assertEqual(result['status'], 'EMPTY_OR_PROVIDER_UNAVAILABLE')
        self.assertEqual(result['control_count'], 0)
        self.assertNotIn('OBSERVED', chat_reply(result))

    def test_scan_failure_is_not_observed(self):
        self.scanner.side_effect = RuntimeError('private exception data')
        result = self.read()
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertNotIn('private exception data', str(result))

    def test_changed_process_lifetime_refused(self):
        inspector = Mock(side_effect=[self.window, {**self.window, 'started': 12345.9}])
        result = self.read(inspector=inspector)
        self.assertEqual(result['status'], 'CONTEXT_CHANGED')

    def test_changed_hwnd_and_pid_refused(self):
        for change in ({'hwnd': 43}, {'pid': 2342}):
            with self.subTest(change=change):
                inspector = Mock(side_effect=[self.window, {**self.window, **change}])
                result = self.read(inspector=inspector)
                self.assertEqual(result['status'], 'CONTEXT_CHANGED')
                self.assertEqual(result['examples'], [])

    def test_invalid_initial_identity_and_rectangle_fail_closed(self):
        for change in ({'hwnd': 43}, {'started': float('nan')},
                       {'started': True}, {'rect': (0, 0, 0, 0)}):
            with self.subTest(change=change):
                result = self.read(inspector=Mock(return_value={**self.window, **change}))
                self.assertEqual(result['status'], 'TARGET_INVALID')
        self.scanner.assert_not_called()

    def test_changed_rectangle_refused(self):
        inspector = Mock(side_effect=[self.window, {**self.window, 'rect': (10, 20, 401, 300)}])
        self.assertEqual(self.read(inspector=inspector)['status'], 'CONTEXT_CHANGED')

    def test_unavailable_or_invalid_initial_inspection(self):
        self.assertEqual(self.read(inspector=Mock(return_value=None))['status'], 'TARGET_INVALID')
        self.assertEqual(self.read(inspector=Mock(side_effect=OSError('private')))['status'], 'UNAVAILABLE')

    def test_insufficient_evidence_never_claims_observation(self):
        self.scanner.return_value = [{'name': 'confidencial', 'automation_id': 'private'}]
        result = self.read()
        self.assertEqual(result['status'], 'INSUFFICIENT_EVIDENCE')
        self.assertEqual(result['control_count'], 1)
        self.assertNotIn('confidencial', str(result))

    def test_bad_scan_return_type_is_unavailable(self):
        self.scanner.return_value = None
        self.assertEqual(self.read()['status'], 'UNAVAILABLE')

    def test_control_type_is_whitelisted_shape(self):
        self.scanner.return_value = [{'control_type': 'private\nsecret', 'rect': [1, 2, 3, 4]}]
        result = self.read()
        self.assertEqual(result['status'], 'OBSERVED')
        self.assertEqual(result['types'][0]['type'], 'Unknown')
        self.assertNotIn('private', str(result))

    def test_type_cannot_expose_alphanumeric_private_text(self):
        self.scanner.return_value = [{'control_type': 'PrivateSecret123', 'rect': [1, 2, 3, 4]}]
        result = self.read()
        self.assertEqual(result['status'], 'OBSERVED')
        self.assertEqual(result['types'][0]['type'], 'Unknown')
        self.assertNotIn('PrivateSecret123', str(result))
        self.assertNotIn('PrivateSecret123', chat_reply(result))

    def test_degenerate_geometry_and_oversized_result_are_not_observed(self):
        self.scanner.return_value = [{'rect': (0, 0, 0, 0)}]
        self.assertEqual(self.read()['status'], 'INSUFFICIENT_EVIDENCE')
        self.scanner.return_value = [{'control_type': 'ButtonControl'}] * 101
        result = self.read()
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertEqual(result['examples'], [])

    def test_real_scanner_does_not_request_sensitive_uia_properties(self):
        from perception_eye import PerceptionEye
        access = []
        class FakeControl:
            @property
            def Name(self):
                access.append('name')
                return 'private'
            @property
            def AutomationId(self):
                access.append('automation_id')
                return 'private'
            ControlTypeName = 'ButtonControl'
            ProcessId = 2341
            IsEnabled = True
            IsOffscreen = False
            BoundingRectangle = SimpleNamespace(left=1, top=2, right=10, bottom=20)
            def GetRuntimeId(self): return (1, 2)
            def GetInvokePattern(self): return None
            def GetExpandCollapsePattern(self): return None
        root = SimpleNamespace(Exists=lambda *args: True)
        fake = SimpleNamespace(UIAutomationInitializerInThread=lambda: nullcontext(),
                               ControlFromHandle=lambda hwnd: root,
                               WalkTree=lambda *args, **kwargs: [(FakeControl(), 0)])
        with patch('perception_eye.auto', fake), patch('perception_eye.HAS_UIA_NATIVE', True):
            eye = PerceptionEye.__new__(PerceptionEye)
            result = eye.scan_uia_properties(42, max_controls=100, include_sensitive=False)
        self.assertEqual(access, [])
        self.assertIsNone(result[0]['name'])
        self.assertIsNone(result[0]['automation_id'])
        self.assertEqual(result[0]['control_type'], 'ButtonControl')


if __name__ == '__main__':
    unittest.main()
