import asyncio
import pytest
from simulated_multibrain import Node, NodeRole, Task, Result, SimulatedCoordinator, aggregate


def node(**kw):
    data = dict(node_id='n1', role=NodeRole.EXECUTOR, paired=True, revoked=False,
                capabilities=frozenset({'research'}), permissions=frozenset({'research'}))
    data.update(kw)
    return Node(**data)


def test_dispatch_conflict_and_duplicate():
    async def worker(task): return Result(task.task_id, 'n1', 'OK', claims={'x': 'A'}, source='s1')
    coordinator = SimulatedCoordinator({'n1': worker})
    result = asyncio.run(coordinator.execute(node(), Task('t', 'research', 'consulta', 1)))
    assert result.status == 'OK'
    with pytest.raises(ValueError): asyncio.run(coordinator.execute(node(), Task('t', 'research', 'consulta', 1)))
    merged = aggregate([result, Result('t2', 'n2', 'OK', claims={'x': 'B'}, source='s2')])
    assert 'x' in merged['conflicts'] and not merged['verified']


def test_revoked_offline_and_observer_never_run_remote():
    async def worker(task): raise AssertionError('remote must not run')
    async def local(task): return Result(task.task_id, 'local', 'OK', source='local')
    for i, device in enumerate((node(revoked=True), node(online=False), node(role=NodeRole.OBSERVER))):
        result = asyncio.run(SimulatedCoordinator({'n1': worker}, local).execute(device, Task(str(i), 'research', '', 1)))
        assert result.node_id == 'local'


def test_timeout_no_retry_and_actuation_rejected():
    calls = []
    async def slow(task):
        calls.append(task.task_id)
        await asyncio.sleep(1)
    coordinator = SimulatedCoordinator({'n1': slow})
    result = asyncio.run(coordinator.execute(node(), Task('slow', 'research', '', 0.01)))
    assert result.status == 'TIMEOUT_UNCONFIRMED' and calls == ['slow']
    with pytest.raises(ValueError): asyncio.run(coordinator.execute(node(), Task('write', 'mouse', '', 1)))
