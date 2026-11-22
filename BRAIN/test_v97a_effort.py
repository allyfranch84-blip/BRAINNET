from unittest.mock import patch
from BRAINNET import BrainnetBridge, _effective_effort, _EFFORT_LIMITS

def test_modes_and_limits():
    assert _effective_effort('AUTO', 'oi') == 'FAST'
    assert _effective_effort('AUTO', 'x' * 500) == 'DEEP'
    assert _effective_effort('DEEP', 'oi') == 'DEEP'
    assert _EFFORT_LIMITS['FAST']['num_predict'] < _EFFORT_LIMITS['DEEP']['num_predict']

def test_config_persistence_and_invalid_mode():
    bridge = object.__new__(BrainnetBridge)
    config = {}
    with patch('BRAINNET._load_app_config', side_effect=lambda: dict(config)), patch('BRAINNET._save_app_config', side_effect=lambda c: config.update(c)):
        assert bridge.set_effort_mode('DEEP')['ok']
        assert bridge.get_effort_mode()['mode'] == 'DEEP'
        assert not bridge.set_effort_mode('BAD')['ok']
        assert bridge.get_effort_mode()['mode'] == 'DEEP'

def test_failed_persistence_is_reported():
    bridge = object.__new__(BrainnetBridge)
    with patch('BRAINNET._load_app_config', side_effect=lambda: {}), patch('BRAINNET._save_app_config'):
        assert not bridge.set_effort_mode('FAST')['ok']
