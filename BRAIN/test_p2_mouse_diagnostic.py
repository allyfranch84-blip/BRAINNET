import threading
from unittest.mock import patch
import pytest
import effector
from execution_authority import authorization_scope
from actuator_bridge import ActuatorBridge

class FakeUser32:
    def __init__(self, *, fail_get=0, fail_set=False, mismatch=False):
        self.pos=(100,100);self.calls=0;self.sets=0;self.fail_get=fail_get;self.fail_set=fail_set;self.mismatch=mismatch
    def GetCursorPos(self,p):
        self.calls+=1
        if self.calls==self.fail_get:return 0
        p._obj.x,p._obj.y=self.pos
        return 1
    def SetCursorPos(self,x,y):
        self.sets+=1
        if self.fail_set:return 0
        self.pos=(x+1,y) if self.mismatch else (x,y)
        return 1

def test_no_authorization_and_revocation_never_move():
    f=FakeUser32()
    with patch.object(effector,'user32',f):
        with pytest.raises(PermissionError): effector.Effector().mouse_move(130,100,profile='deterministic')
        token=threading.Event();token.set()
        with authorization_scope(token),pytest.raises(PermissionError): effector.Effector().mouse_move(130,100,profile='deterministic')
    assert f.sets==0

@pytest.mark.parametrize('kwargs,expected_sets', [({'fail_get':1},0),({'fail_set':True},1),({'fail_get':2},1),({'mismatch':True},1)])
def test_failures_are_not_success(kwargs,expected_sets):
    f=FakeUser32(**kwargs)
    with patch.object(effector,'user32',f),authorization_scope(threading.Event()):
        assert effector.Effector().mouse_move(130,100,profile='deterministic') is False
    assert f.sets==expected_sets

def test_bridge_callable_checks_and_propagates():
    f=FakeUser32()
    with patch.object(effector,'user32',f),authorization_scope(threading.Event()):
        assert ActuatorBridge._invoke_actuator('mouse_move',effector.Effector().mouse_move,130,100,profile='deterministic') is True
    assert f.sets==1

def test_route_propagates_actuator_failure():
    import asyncio
    from unittest.mock import AsyncMock,Mock
    bridge=ActuatorBridge(effector_instance=Mock())
    with patch.object(ActuatorBridge, '_complete_physical', AsyncMock(return_value=False)), patch('actuator_bridge.asyncio.get_running_loop', return_value=Mock()), authorization_scope(threading.Event()):
        coro=bridge._route_execution('mouse_move',{'x':130,'y':100,'profile':'deterministic'})
        try:
            coro.send(None)
        except StopIteration as done:
            assert done.value is False
        else:
            raise AssertionError('A rota simulada não terminou imediatamente')
