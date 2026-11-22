"""Experimental in-process cooperative analysis; no network or actuator access."""
import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Awaitable


class NodeRole(str, Enum):
    COORDINATOR = 'coordinator'
    EXECUTOR = 'executor'
    OBSERVER = 'observer'


@dataclass(frozen=True)
class Node:
    node_id: str
    role: NodeRole
    paired: bool
    revoked: bool
    capabilities: frozenset[str]
    permissions: frozenset[str]
    models: tuple[str, ...] = ()
    ram_bytes: int | None = None
    gpu: str | None = None
    load: float | None = None
    latency_ms: float | None = None
    online: bool = True


@dataclass(frozen=True)
class Task:
    task_id: str
    kind: str
    payload: str
    timeout_s: float


@dataclass
class Result:
    task_id: str
    node_id: str
    status: str
    output: str = ''
    claims: dict[str, str] = field(default_factory=dict)
    source: str = ''


_ALLOWED = frozenset({'research', 'critique', 'code_analysis', 'verification'})


class SimulatedCoordinator:
    """Workers are injected async functions; input must already be minimized.

    Only pure analysis is supported. No retries/fallback after dispatch: a timeout
    cannot prove a worker has stopped, so re-execution would risk duplication.
    """
    def __init__(self, workers: dict[str, Callable[[Task], Awaitable[Result]]], local_worker=None):
        self.workers = dict(workers)
        self.local_worker = local_worker
        self._issued = set()

    async def execute(self, node: Node, task: Task) -> Result:
        if not task.task_id or task.task_id in self._issued:
            raise ValueError('missing or duplicate task id')
        if task.kind not in _ALLOWED or not isinstance(task.payload, str) or not 0 < task.timeout_s <= 60:
            raise ValueError('unsupported task or deadline')
        self._issued.add(task.task_id)
        eligible = (node.role == NodeRole.EXECUTOR and node.paired and not node.revoked
                    and node.online and task.kind in node.capabilities and task.kind in node.permissions)
        worker = self.workers.get(node.node_id) if eligible else None
        node_id = node.node_id
        if worker is None:
            worker, node_id = self.local_worker, 'local'
        if worker is None:
            return Result(task.task_id, node_id, 'UNAVAILABLE')
        try:
            result = await asyncio.wait_for(worker(task), timeout=task.timeout_s)
        except asyncio.TimeoutError:
            return Result(task.task_id, node_id, 'TIMEOUT_UNCONFIRMED')
        except asyncio.CancelledError:
            raise
        except Exception:
            return Result(task.task_id, node_id, 'WORKER_FAILED')
        if not isinstance(result, Result) or result.task_id != task.task_id or result.node_id != node_id:
            return Result(task.task_id, node_id, 'INVALID_RESULT')
        return result


def aggregate(results: list[Result]) -> dict:
    claims = {}
    for result in results:
        if result.status != 'OK' or not result.source:
            continue
        for key, value in result.claims.items():
            claims.setdefault(key, []).append({'value': value, 'node_id': result.node_id, 'source': result.source})
    conflicts = {key: entries for key, entries in claims.items() if len({e['value'] for e in entries}) > 1}
    return {'claims': claims, 'conflicts': conflicts, 'verified': False}
