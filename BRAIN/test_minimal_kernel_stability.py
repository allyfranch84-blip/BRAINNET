import asyncio
from unittest.mock import AsyncMock,Mock,patch
from BRAINNET import BrainnetKernel,BrainnetBridge

def test_minimal_kernel_starts_and_stops_without_rem_or_db():
    with patch.dict('os.environ',{'BRAINNET_MINIMAL':'1','BRAINNET_ADAPTIVE_OBSERVE':'0'}), \
         patch('BRAINNET.FHRRHyperdimensionalEngine') as vsa, \
         patch('BRAINNET.ContextCapture'), patch('BRAINNET.PerceptionEye'), patch('BRAINNET.Effector'), \
         patch('BRAINNET.ActuatorBridge') as bridge_cls, patch('BRAINNET.MyelinatedPDAGEngine') as db, \
         patch('BRAINNET.REMSleepEngine') as rem:
        bridge_cls.return_value.start=AsyncMock()
        bridge_cls.return_value.stop=AsyncMock()
        kernel=BrainnetKernel()
        assert kernel.pdag is None and kernel.rem_engine is None
        async def stop_once(seconds): kernel.is_running=False
        with patch('BRAINNET.asyncio.get_running_loop',return_value=Mock()),patch('BRAINNET.asyncio.sleep',side_effect=stop_once), \
             patch.object(kernel,'_circadian_rem_watchdog',side_effect=AssertionError('REM must not start')):
            task=kernel.start()
            try: task.send(None)
            except StopIteration: pass
            else: raise AssertionError('Unexpected suspension')
        bridge_cls.return_value.start.assert_awaited_once()
        bridge_cls.return_value.stop.assert_awaited_once()
        assert kernel.is_running is False
        db.assert_not_called();rem.assert_not_called()

def test_minimal_profile_returns_proposal_and_blocks_rem():
    with patch.dict('os.environ',{'BRAINNET_MINIMAL':'1'}),patch('BRAINNET.FHRRHyperdimensionalEngine'), \
         patch('BRAINNET.ContextCapture'),patch('BRAINNET.PerceptionEye'),patch('BRAINNET.Effector'), \
         patch('BRAINNET.ActuatorBridge'),patch('BRAINNET.DigitalProprioceptionGate'),patch('BRAINNET.TheoryOfMindEngine'):
        k=BrainnetKernel();b=BrainnetBridge(k)
        with patch.object(b,'get_effort_mode',return_value={'mode':'FAST'}),patch.object(b,'get_conversation_status',return_value={}):
            r=b.send_command('mova o mouse 30 pixels para a direita, sem clicar')
            assert r['status']=='AUTHORIZATION_REQUIRED' and not r['dispatched']
            assert b.send_command('/rem')['status']=='UNAVAILABLE'

def test_rem_missing_injection_preserves_memory(tmp_path):
    import sqlite3,time
    import pytest
    from rem_sleep_engine import REMSleepEngine
    path=tmp_path/'disposable.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE hmem_nodes (timestamp REAL)')
        db.execute('INSERT INTO hmem_nodes VALUES (?)',(time.time()-40*86400,))
    engine=REMSleepEngine(db_path=str(path),skills_dir=tmp_path/'skills')
    with pytest.raises(RuntimeError,match='injecao do pdag_engine'):
        engine.execute_full_rem_cycle()
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM hmem_nodes').fetchone()[0]==1

def test_minimal_delegated_proposal_uses_same_task_without_dispatch():
    with patch.dict('os.environ',{'BRAINNET_MINIMAL':'1'}),patch('BRAINNET.FHRRHyperdimensionalEngine'), \
         patch('BRAINNET.ContextCapture'),patch('BRAINNET.PerceptionEye'),patch('BRAINNET.Effector'), \
         patch('BRAINNET.ActuatorBridge'),patch('BRAINNET.DigitalProprioceptionGate'),patch('BRAINNET.TheoryOfMindEngine'):
        k=BrainnetKernel();b=BrainnetBridge(k)
        with patch.object(b,'get_effort_mode',return_value={'mode':'FAST'}),patch.object(b,'get_conversation_status',return_value={}):
            r=b.send_command('mova o mouse em qualquer direção')
        assert r['status']=='AUTHORIZATION_REQUIRED' and not r['dispatched']
        assert r['task_budget']['task_id']==r['motor_proposal']['task_id']
        assert r['pending_operation_id']==r['motor_proposal']['operation_id']
        assert r['next_requirement']=='OBSERVATION_REQUIRED'

def test_minimal_skills_never_start_loader():
    with patch.dict('os.environ',{'BRAINNET_MINIMAL':'1'}),patch('BRAINNET.FHRRHyperdimensionalEngine'), \
         patch('BRAINNET.ContextCapture'),patch('BRAINNET.PerceptionEye'),patch('BRAINNET.Effector'), \
         patch('BRAINNET.ActuatorBridge'),patch('BRAINNET.DigitalProprioceptionGate'),patch('BRAINNET.TheoryOfMindEngine'):
        assert BrainnetBridge(BrainnetKernel()).list_skills()==[]
