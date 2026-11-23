"""Explicitly virtual motor fixture; never accesses an OS actuator or screen.

This is a deterministic fixture, not independent observation of a physical
screen. Its task lock intentionally spans the fake move and observation:
concurrent cancellation must wait for those calls to return. Never reuse that
locking contract for physical, slow, or blocking operations. Expired pending
tasks are checked when resumed, but no automatic expiry/reaper is provided.

Safe-full environment limitation: test_inference_backend.py::
TestSupervisorAddendum::test_absent_gpu_counter_is_unknown loads
../llama_cpp_independent/b12255/benchmark_003c1.py. The benchmark is excluded
from the Git snapshot; the test reproducibly fails with FileNotFoundError in
the Git copy and passes in the operational tree where the file is present.
That failure occurs before GPU or virtual-motor behavior is tested.
"""


class VirtualMotor:
    def __init__(self, *, hwnd, pid, safe_rect, position):
        self.hwnd, self.pid = hwnd, pid
        self.safe_rect = tuple(safe_rect)
        self.position = tuple(position)
        self.dispatch_count = 0

    def observe(self):
        return {'hwnd': self.hwnd, 'pid': self.pid,
                'safe_rect': self.safe_rect, 'position': self.position}

    def move(self, dx, dy):
        self.dispatch_count += 1
        self.position = (self.position[0] + dx, self.position[1] + dy)


def resume(bridge, task_id, operation_id, decision, evidence, motor):
    result = _resume(bridge, task_id, operation_id, decision, evidence, motor)
    if result.get('status') in ('SUCCEEDED', 'EXECUTION_FAILED', 'VERIFICATION_FAILED',
                               'INCONCLUSIVE', 'CANCELLED', 'EXPIRED'):
        kernel = bridge._kernel
        with kernel._runtime_task_lock:
            task = kernel._runtime_tasks.get(task_id)
            if task is not None and task.task_state in ('SUCCEEDED', 'FAILED', 'INCONCLUSIVE', 'CANCELLED', 'EXPIRED'):
                kernel._runtime_tasks.pop(task_id, None)
                recent = getattr(kernel, '_runtime_recent_tasks', None)
                if recent is not None:
                    recent.append(task)
    return result


def _resume(bridge, task_id, operation_id, decision, evidence, motor):
    """Internal simulation entry point. Evidence and motor are fixture data only."""
    if type(motor) is not VirtualMotor or decision not in ('approve', 'cancel'):
        return {'status': 'REJECTED', 'task_id': task_id, 'operation_id': operation_id}
    kernel = bridge._kernel
    with kernel._runtime_task_lock:
        task = kernel._runtime_tasks.get(task_id)
    if task is None or task.task_id != task_id:
        return {'status': 'REJECTED', 'task_id': task_id, 'operation_id': operation_id}
    result = {'task_id': task_id, 'operation_id': operation_id, 'simulated': True}
    with task._lock:
        op = task._operations.get(operation_id)
        if not op or op.get('kind') != 'motor_proposal':
            return {**result, 'status': 'REJECTED'}
        if decision == 'cancel':
            return {**result, 'status': 'CANCELLED' if task.cancel_pending_motor(operation_id) else 'REJECTED'}
        if task.expire_pending_motor(operation_id):
            return {**result, 'status': 'EXPIRED'}
        if op['status'] != 'WAITING_AUTHORIZATION' or task.cancellation_event.is_set():
            return {**result, 'status': 'REJECTED'}
        if op['action'] != 'MOVE_CURSOR' or (op['dx'], op['dy']) != (30, 0):
            return {**result, 'status': 'REJECTED'}
        if not isinstance(evidence, dict) or evidence.get('action') != 'MOVE_CURSOR':
            return {**result, 'status': 'REJECTED'}
        try:
            before = VirtualMotor.observe(motor)
        except Exception:
            return {**result, 'status': 'OBSERVATION_UNAVAILABLE'}
        try:
            rect = tuple(evidence['safe_rect'])
            point = tuple(before['position'])
            expected = (point[0] + 30, point[1])
            if (len(rect) != 4 or len(point) != 2 or
                any(type(v) is not int for v in rect + point) or
                any(evidence.get(k) != before.get(k) for k in ('hwnd', 'pid', 'safe_rect')) or
                (evidence.get('dx'), evidence.get('dy')) != (30, 0) or
                not all(rect[0] <= x < rect[2] and rect[1] <= y < rect[3] for x, y in (point, expected))):
                return {**result, 'status': 'REJECTED'}
            if op['hwnd'] is None:
                if not task.bind_motor_observation(operation_id, hwnd=evidence['hwnd'], pid=evidence['pid'], safe_rect=rect):
                    return {**result, 'status': 'REJECTED'}
            if not task.transition_motor_simulation(operation_id, 'WAITING_AUTHORIZATION', 'AUTHORIZED', evidence=evidence):
                return {**result, 'status': 'REJECTED'}
            if not task.transition_motor_simulation(operation_id, 'AUTHORIZED', 'EXECUTING', evidence=evidence):
                return {**result, 'status': 'REJECTED'}
        except (KeyError, TypeError, ValueError, IndexError):
            return {**result, 'status': 'REJECTED'}
        try:
            VirtualMotor.move(motor, 30, 0)
        except Exception:
            if not task.transition_motor_simulation(operation_id, 'EXECUTING', 'FAILED'):
                op['status'] = task.task_state = 'INCONCLUSIVE'
                return {**result, 'status': 'INCONCLUSIVE'}
            return {**result, 'status': 'EXECUTION_FAILED'}
        if not task.transition_motor_simulation(operation_id, 'EXECUTING', 'VERIFYING'):
            op['status'] = task.task_state = 'INCONCLUSIVE'
            return {**result, 'status': 'INCONCLUSIVE'}
        try:
            after = VirtualMotor.observe(motor)
            if any(after.get(k) != before.get(k) for k in ('hwnd', 'pid', 'safe_rect')):
                raise ValueError('context changed')
            observed = tuple(after['position'])
            if len(observed) != 2 or any(type(v) is not int for v in observed):
                raise ValueError('invalid observation')
        except Exception:
            if not task.transition_motor_simulation(operation_id, 'VERIFYING', 'INCONCLUSIVE'):
                op['status'] = task.task_state = 'INCONCLUSIVE'
            return {**result, 'status': 'INCONCLUSIVE'}
        state = 'SUCCEEDED' if observed == expected else 'FAILED'
        if not task.transition_motor_simulation(operation_id, 'VERIFYING', state):
            op['status'] = task.task_state = 'INCONCLUSIVE'
            return {**result, 'status': 'INCONCLUSIVE'}
        return {**result, 'status': 'SUCCEEDED' if state == 'SUCCEEDED' else 'VERIFICATION_FAILED',
                'before': point, 'after': observed, 'tolerance_pixels': 0}
