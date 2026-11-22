import json
from unittest.mock import Mock, patch
import pytest
from PIL import Image
from causal_trajectory import CausalTrajectoryEngine
from vision_eye import RealVisionEngine

def test_ghrr_recovery_is_proposal_without_motor_steps():
    engine = object.__new__(CausalTrajectoryEngine)
    engine.syntactic_pdag = Mock()
    engine.syntactic_pdag.propose_route.return_value = {
        'status': 'REVIEW_REQUIRED', 'execution_authorized': False,
        'historical_verification': 'UNKNOWN', 'steps': [{'acao': 'CLICK'}]}
    plan = engine.decompor_trajetoria_cognitiva('clique')
    assert plan['passos'] == [] and plan['pipeline'] == []
    assert plan['ghrr_proposal']['execution_authorized'] is False

def test_visual_json_keep_alive_configured_without_network(monkeypatch):
    monkeypatch.setenv('BRAINNET_VISION_KEEP_ALIVE', '5m')
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = json.dumps({'done': True, 'message': {'content': '{}'}}).encode()
    with patch('vision_eye.urllib.request.urlopen', return_value=response) as send:
        result = RealVisionEngine()._consultar_visual_json(Image.new('RGB', (8, 8)), 'x', {})
    assert result == {}
    assert json.loads(send.call_args.args[0].data)['keep_alive'] == '5m'

@pytest.mark.parametrize('point,image,rect,expected', [
    ((50,25),(100,50),(-1920,100,-1720,200),(-1820,150)),
    ((0,0),(100,100),(30,40,230,240),(30,40)),
])
def test_scaled_coordinates(point,image,rect,expected):
    assert RealVisionEngine.protocol_point_to_screen(point,image,rect) == expected

def test_invalid_coordinates_rejected():
    with pytest.raises(ValueError):
        RealVisionEngine.protocol_point_to_screen((100,0),(100,100),(0,0,100,100))
