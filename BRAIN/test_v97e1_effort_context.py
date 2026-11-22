from unittest.mock import Mock, patch
from BRAINNET import BrainnetBridge, _EFFORT_LIMITS, _effort_for_command


def test_effort_context_is_per_command_and_restored():
    bridge = object.__new__(BrainnetBridge)
    bridge._chat_history = []
    bridge.get_effort_mode = Mock(return_value={'mode': 'FAST'})
    bridge._send_command_impl = Mock(side_effect=lambda text: {'reply': _effort_for_command.get(), 'logs': []})
    previous = _effort_for_command.get()
    result = bridge.send_command('pedido')
    assert result['reply'] == 'FAST'
    assert result['effort']['budget']['visual_steps'] == 3
    assert _effort_for_command.get() == previous
    assert _EFFORT_LIMITS['DEEP']['visual_steps'] > _EFFORT_LIMITS['FAST']['visual_steps']
