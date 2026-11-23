import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from motor_simulation import VirtualMotor
from test_v98a2_9_pending import make_registered_bridge
from execution_authority import require_action_allowed


def setup_case():
    bridge = make_registered_bridge()
    response = bridge.send_command('mova o mouse 30 pixels para a direita, sem clicar')
    task_id = response['task_budget']['task_id']
    op = response['pending_operation_id']
    task = bridge._kernel._runtime_tasks[task_id]
    motor = VirtualMotor(hwnd=12, pid=42, safe_rect=(0, 0, 100, 100), position=(10, 20))
    evidence = {'hwnd': 12, 'pid': 42, 'safe_rect': (0, 0, 100, 100),
                'dx': 30, 'dy': 0, 'action': 'MOVE_CURSOR'}
    assert response['status'] == 'AUTHORIZATION_REQUIRED' and not response['dispatched']
    return bridge, task, op, motor, evidence


def call(b, t, op, motor, evidence, decision='approve'):
    return b._resume_motor_simulation(t.task_id, op, decision, evidence, motor)


def test_chat_to_single_verified_virtual_move_without_physical_authority():
    b, t, op, m, e = setup_case()
    with patch('effector.Effector.mouse_move', side_effect=AssertionError('physical motor')):
        result = call(b, t, op, m, e)
    assert result == {'task_id': t.task_id, 'operation_id': op, 'simulated': True,
                      'status': 'SUCCEEDED', 'before': (10, 20), 'after': (40, 20),
                      'tolerance_pixels': 0}
    assert m.dispatch_count == 1 and t.task_state == 'SUCCEEDED'
    assert t.task_id not in b._kernel._runtime_tasks
    assert t in b._kernel._runtime_recent_tasks
    with pytest.raises(PermissionError):
        require_action_allowed('MOVE_CURSOR')
    assert call(b, t, op, m, e)['status'] == 'REJECTED'
    assert m.dispatch_count == 1


def test_command_authority_is_revoked_when_chat_returns():
    with patch('owned_processes.release_processes') as release:
        setup_case()
    token = release.call_args.args[0]
    assert token.is_set()


def test_previously_bound_context_must_match_and_fake_type_is_required():
    b, t, op, m, e = setup_case()
    assert t.bind_motor_observation(op, hwnd=99, pid=42, safe_rect=(0, 0, 100, 100))
    assert call(b, t, op, m, e)['status'] == 'REJECTED' and m.dispatch_count == 0
    assert call(b, t, op, object(), e)['status'] == 'REJECTED'


@pytest.mark.parametrize('change', [
    {'action': 'click'}, {'action': 'hotkey'}, {'dx': 29}, {'hwnd': 13},
    {'pid': 43}, {'safe_rect': (0, 0, 99, 100)},
])
def test_mismatched_action_or_scene_never_dispatches(change):
    b, t, op, m, e = setup_case()
    assert call(b, t, op, m, {**e, **change})['status'] == 'REJECTED'
    assert m.dispatch_count == 0


def test_missing_approval_cross_task_unknown_operation_and_outside():
    b, t, op, m, e = setup_case()
    assert call(b, t, op, m, e, 'pending')['status'] == 'REJECTED'
    assert b._resume_motor_simulation('another-task', op, 'approve', e, m)['status'] == 'REJECTED'
    assert call(b, t, 'unknown', m, e)['status'] == 'REJECTED'
    m.position = (90, 20)
    assert call(b, t, op, m, e)['status'] == 'REJECTED'
    assert m.dispatch_count == 0


def test_cancel_before_and_after_approval_and_expiry():
    b, t, op, m, e = setup_case()
    assert call(b, t, op, m, e, 'cancel')['status'] == 'CANCELLED'
    assert call(b, t, op, m, e)['status'] == 'REJECTED' and m.dispatch_count == 0
    b, t, op, m, e = setup_case()
    assert t.bind_motor_observation(op, hwnd=12, pid=42, safe_rect=(0, 0, 100, 100))
    assert t.transition_motor_simulation(op, 'WAITING_AUTHORIZATION', 'AUTHORIZED', evidence=e)
    assert t.cancel_pending_motor(op)
    assert call(b, t, op, m, e)['status'] == 'REJECTED' and m.dispatch_count == 0
    b, t, op, m, e = setup_case()
    t._operations[op]['deadline_monotonic'] = time.monotonic() - 1
    assert call(b, t, op, m, e)['status'] == 'EXPIRED' and m.dispatch_count == 0


def test_concurrent_approvals_or_cancel_never_dispatch_twice():
    b, t, op, m, e = setup_case()
    gate = threading.Barrier(2)
    def run(decision):
        gate.wait()
        return call(b, t, op, m, e, decision)['status']
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(run, ['approve', 'approve']))
    assert sorted(outcomes) == ['REJECTED', 'SUCCEEDED'] and m.dispatch_count == 1
    b, t, op, m, e = setup_case()
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(run, ['approve', 'cancel']))
    assert m.dispatch_count in (0, 1) and ('SUCCEEDED' in outcomes) == (m.dispatch_count == 1)


def test_failed_dispatch_and_observation_never_claim_success():
    b, t, op, m, e = setup_case()
    with patch.object(VirtualMotor, 'move', side_effect=RuntimeError('fake error')):
        assert call(b, t, op, m, e)['status'] == 'EXECUTION_FAILED'
    assert t.task_state == 'FAILED'
    b, t, op, m, e = setup_case()
    original = VirtualMotor.observe
    def bad_observation(self):
        if self.dispatch_count:
            raise RuntimeError('fake sensor unavailable')
        return original(self)
    with patch.object(VirtualMotor, 'observe', bad_observation):
        assert call(b, t, op, m, e)['status'] == 'INCONCLUSIVE'
    assert t.task_state == 'INCONCLUSIVE' and m.dispatch_count == 1
    b, t, op, m, e = setup_case()
    with patch.object(VirtualMotor, 'move', lambda self, dx, dy: None):
        assert call(b, t, op, m, e)['status'] == 'VERIFICATION_FAILED'
    assert t.task_state == 'FAILED'
