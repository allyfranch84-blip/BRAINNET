"""P4.4 direct move contract: all native input is mocked in this file."""
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import Mock, patch

from BRAINNET import BrainnetBridge, BrainnetKernel


def _bridge(observation):
    patches = [
        patch.dict('os.environ', {'BRAINNET_MINIMAL':'1', 'BRAINNET_P4_PHYSICAL_PROPOSALS':'1', 'BRAINNET_P4_DIRECT_MOVE':'1'}),
        patch('BRAINNET.FHRRHyperdimensionalEngine'), patch('BRAINNET.ContextCapture'),
        patch('BRAINNET.PerceptionEye'), patch('BRAINNET.Effector'), patch('BRAINNET.ActuatorBridge'),
        patch('BRAINNET.DigitalProprioceptionGate'), patch('BRAINNET.TheoryOfMindEngine'),
        patch('capability_lab.observe_physical_monitor', return_value=observation),
        patch('capability_lab.observe_cursor_monitors', return_value={'interactive_desktop_verified':True}),
    ]
    for item in patches: item.start()
    kernel = BrainnetKernel(); kernel.loop = Mock(); kernel.loop.is_running.return_value = True
    bridge = BrainnetBridge(kernel)
    bridge.get_effort_mode = Mock(return_value={'mode':'FAST'})
    bridge.get_conversation_status = Mock(return_value={})
    return bridge, kernel, patches


def _success_submit(before, target):
    future = Future()
    future.set_result(SimpleNamespace(status='completed', result={
        'status':'EFFECT_VERIFIED', 'code':'EFFECT_VERIFIED',
        'before':before, 'target':target, 'after':target, 'latency_ms':1.2,
    }))
    def submit(coro, loop):
        coro.close()
        return future
    return submit


def test_exact_delegated_command_dispatches_one_bounded_physical_operation():
    obs = {'status':'OBSERVED','coordinate_space':'PHYSICAL','cursor':(100,50),'monitor':'DISPLAY1','monitor_rect':(0,0,500,300)}
    bridge, kernel, patches = _bridge(obs)
    try:
        with patch('BRAINNET.asyncio.run_coroutine_threadsafe', side_effect=_success_submit((100,50),(110,50))) as submit:
            result = bridge.send_command('mova o mouse em qualquer direção')
        assert result['status'] == 'EFFECT_VERIFIED'
        assert result['before'] == (100,50) and result['target'] == (110,50)
        assert 'Movi o mouse 10 pixels para a direita.' == result['reply']
        assert submit.call_count == 1
    finally:
        for item in reversed(patches): item.stop()


def test_only_delegated_literal_path_can_reach_direct_dispatch():
    obs = {'status':'OBSERVED','coordinate_space':'PHYSICAL','cursor':(100,50),'monitor':'DISPLAY1','monitor_rect':(0,0,500,300)}
    bridge, kernel, patches = _bridge(obs)
    try:
        with patch.object(bridge, '_dispatch_direct_p4_move') as dispatch:
            result = bridge.send_command('explique como mover o mouse em qualquer direção')
        dispatch.assert_not_called()
        assert result['status'] == 'UNAVAILABLE'
    finally:
        for item in reversed(patches): item.stop()


def test_boundary_uses_left_direction_without_expanding_the_limit():
    obs = {'status':'OBSERVED','coordinate_space':'PHYSICAL','cursor':(495,50),'monitor':'DISPLAY1','monitor_rect':(0,0,500,300)}
    bridge, kernel, patches = _bridge(obs)
    try:
        with patch('BRAINNET.asyncio.run_coroutine_threadsafe', side_effect=_success_submit((495,50),(485,50))):
            result = bridge.send_command('mova o mouse em qualquer direção')
        assert result['target'] == (485,50)
        assert 'esquerda' in result['reply']
    finally:
        for item in reversed(patches): item.stop()


def test_bad_observation_never_dispatches():
    obs = {'status':'OBSERVED','coordinate_space':'LOGICAL','cursor':(100,50),'monitor':'DISPLAY1','monitor_rect':(0,0,500,300)}
    bridge, kernel, patches = _bridge(obs)
    try:
        with patch.object(bridge, '_dispatch_direct_p4_move') as dispatch:
            result = bridge.send_command('mova o mouse em qualquer direção')
        dispatch.assert_not_called()
        assert result['status'] == 'ACTION_BLOCKED'
    finally:
        for item in reversed(patches): item.stop()
