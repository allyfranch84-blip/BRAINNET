import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from execution_authority import authorization_scope
from capability_lab import verify_relative_move
from test_v97r22_production import make_bridge


def test_natural_input_reaches_proposal_without_motor():
    b=make_bridge()
    result=b.send_command('mova o mouse lentamente 30 pixels para a direita, sem clicar')
    assert result['status']=='AUTHORIZATION_REQUIRED'
    assert result['motor_proposal']['dx']==30 and not result['motor_proposal']['execution_authorized']
    assert result['motor_proposal']['click'] is False


def test_move_requires_authorization_and_independent_observation():
    bridge=SimpleNamespace(dispatch=AsyncMock(return_value=SimpleNamespace(status='completed',result=True)))
    positions=iter([(10,10),(40,10)])
    with pytest.raises(PermissionError): asyncio.run(verify_relative_move(bridge,lambda:next(positions),(0,0,100,100),30,0))
    bridge.dispatch.assert_not_awaited()
    with authorization_scope(threading.Event()):
        result=asyncio.run(verify_relative_move(bridge,lambda:next(positions),(0,0,100,100),30,0))
    assert result['status']=='PASS' and result['observed']==(40,10) and not result['speed_verified']
    bridge.dispatch.assert_awaited_once_with('mouse_move',{'x':40,'y':10})


def test_failed_observation_and_bounds_do_not_claim_success():
    bridge=SimpleNamespace(dispatch=AsyncMock(return_value=SimpleNamespace(status='completed',result=True)))
    positions=iter([(10,10),(11,10)])
    with authorization_scope(threading.Event()):
        result=asyncio.run(verify_relative_move(bridge,lambda:next(positions),(0,0,100,100),30,0))
    assert result['status']=='FAIL'
    bridge.dispatch.reset_mock()
    with authorization_scope(threading.Event()):
        result=asyncio.run(verify_relative_move(bridge,lambda:(90,10),(0,0,100,100),30,0))
    assert result['status']=='INCONCLUSIVE';bridge.dispatch.assert_not_awaited()


def test_unavailable_final_sensor_returns_inconclusive():
    bridge=SimpleNamespace(dispatch=AsyncMock(return_value=SimpleNamespace(status='completed',result=True)))
    positions=iter([(10,10)])
    with authorization_scope(threading.Event()):
        result=asyncio.run(verify_relative_move(bridge,lambda:next(positions),(0,0,100,100),30,0))
    assert result['status']=='INCONCLUSIVE'
