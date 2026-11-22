from unittest.mock import Mock
from test_v97r22_production import make_bridge


def test_real_chat_binds_proposal_to_task_without_dispatch():
    bridge = make_bridge()
    bridge._kernel.bridge = Mock()
    result = bridge.send_command('mova o mouse 30 pixels para a direita, sem clicar')
    assert result['status'] == 'AUTHORIZATION_REQUIRED'
    assert result['motor_proposal']['task_id'] == result['task_budget']['task_id']
    assert result['motor_proposal']['execution_authorized'] is False
    bridge._kernel.bridge.dispatch.assert_not_called()
