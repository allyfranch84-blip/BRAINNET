"""
AI OS v7 - Actuator Bridge Subsystem (Windows 11 LTSC | Python 3.12)
Asynchronous hardware isolation bridge between Kernel 1 (Mind) and Kernel 2 (Body).
"""

from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from enum import IntEnum
import time
from typing import Any, Callable, Coroutine, Optional
import uuid
from execution_authority import authorization_scope, current_authorization, require_action_allowed


class CommandPriority(IntEnum):
    EMERGENCY = 0
    HIGH = 1
    NORMAL = 2
    BACKGROUND = 3


@dataclass(slots=True, frozen=True)
class CommandResult:
    cmd_id: str
    action: str
    status: str
    result: Any
    latency_ms: float
    error: Optional[str] = None
    queue_wait_ms: float = 0.0


@dataclass(slots=True, order=True)
class PrioritizedCommand:
    priority: int
    timestamp: float
    cmd_id: str = field(compare=False)
    action: str = field(compare=False)
    payload: dict[str, Any] = field(compare=False)
    timeout_sec: float = field(compare=False)
    fut: asyncio.Future[CommandResult] = field(compare=False)
    authorization_token: Any = field(default=None, compare=False)


class ActuatorBridge:
    """Isolated, concurrency-safe dispatch bus executing Kernel 1 intents on Kernel 2 hardware."""

    __slots__ = (
        "_effector",
        "_perception",
        "_queue",
        "_workers",
        "_running",
        "_input_lock",
        "_sensor_sem",
        "_max_workers",
    )

    def __init__(
        self,
        effector_instance: Any = None,
        perception_instance: Any = None,
        max_workers: int = 4,
        max_queue_depth: int = 256,
    ) -> None:
        self._effector = effector_instance
        self._perception = perception_instance
        self._queue: asyncio.PriorityQueue[PrioritizedCommand] = asyncio.PriorityQueue(maxsize=max_queue_depth)
        self._workers: list[asyncio.Task[None]] = []
        self._running = False
        self._input_lock = asyncio.Lock()
        self._sensor_sem = asyncio.Semaphore(2)
        self._max_workers = max_workers

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        loop = asyncio.get_running_loop()
        for i in range(self._max_workers):
            task = loop.create_task(self._worker_loop(f"actuator_bridge_w{i}"))
            self._workers.append(task)

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def dispatch(
        self,
        action: str,
        payload: dict[str, Any],
        priority: CommandPriority = CommandPriority.NORMAL,
        timeout_sec: float = 5.0,
    ) -> CommandResult:
        require_action_allowed(action, priority == CommandPriority.BACKGROUND)
        if not self._running:
            raise RuntimeError("ActuatorBridge is offline.")

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[CommandResult] = loop.create_future()
        cmd_id = f"cmd_{uuid.uuid4().hex[:8]}"

        item = PrioritizedCommand(
            priority=int(priority),
            timestamp=time.perf_counter(),
            cmd_id=cmd_id,
            action=action,
            payload=payload,
            timeout_sec=timeout_sec,
            fut=fut,
            authorization_token=current_authorization(),
        )

        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            return CommandResult(
                cmd_id=cmd_id,
                action=action,
                status="dropped",
                result=None,
                latency_ms=0.0,
                error="Bridge queue full; command dropped under high pressure.",
            )

        try:
            return await fut
        except asyncio.CancelledError:
            # A queued or in-flight write must not outlive its caller's authority.
            if action.lower() not in ("read", "inspect", "capture_screen", "emergency_stop"):
                token = item.authorization_token
                if token is not None:
                    token.set()
            raise

    async def _worker_loop(self, worker_name: str) -> None:
        while self._running:
            try:
                cmd_item = await self._queue.get()
            except asyncio.CancelledError:
                break

            t0 = time.perf_counter_ns()
            queue_wait_ms = max(0.0, time.perf_counter() - cmd_item.timestamp) * 1000.0
            try:
                if cmd_item.fut.cancelled():
                    continue
                coro = self._execute_authorized(cmd_item)
                token = cmd_item.authorization_token
                is_write = cmd_item.action.lower() not in ("read", "inspect", "capture_screen", "emergency_stop")
                # wait_for waits for native cleanup; revoke at the deadline itself.
                timer = asyncio.get_running_loop().call_later(cmd_item.timeout_sec, token.set) if is_write and token is not None else None
                try:
                    exec_result = await asyncio.wait_for(coro, timeout=cmd_item.timeout_sec)
                finally:
                    if timer is not None:
                        timer.cancel()
                elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000.0

                if not cmd_item.fut.done():
                    cmd_item.fut.set_result(
                        CommandResult(
                            cmd_id=cmd_item.cmd_id,
                            action=cmd_item.action,
                            status="completed",
                            result=exec_result,
                            latency_ms=elapsed_ms,
                            queue_wait_ms=queue_wait_ms,
                        )
                    )
            except asyncio.TimeoutError:
                elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000.0
                if not cmd_item.fut.done():
                    cmd_item.fut.set_result(
                        CommandResult(
                            cmd_id=cmd_item.cmd_id,
                            action=cmd_item.action,
                            status="timed_out",
                            result=None,
                            latency_ms=elapsed_ms,
                            error=f"Execution exceeded budget of {cmd_item.timeout_sec}s",
                            queue_wait_ms=queue_wait_ms,
                        )
                    )
            except Exception as ex:
                elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000.0
                if not cmd_item.fut.done():
                    cmd_item.fut.set_result(
                        CommandResult(
                            cmd_id=cmd_item.cmd_id,
                            action=cmd_item.action,
                            status="failed",
                            result=None,
                            latency_ms=elapsed_ms,
                            error=str(ex),
                            queue_wait_ms=queue_wait_ms,
                        )
                    )
            finally:
                self._queue.task_done()

    async def clear_pending_actions(self) -> int:
        cleared = 0
        while True:
            try:
                item = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return cleared
            if not item.fut.done():
                item.fut.cancel()
            self._queue.task_done()
            cleared += 1

    async def _execute_authorized(self, item):
        with authorization_scope(item.authorization_token):
            require_action_allowed(item.action)
            return await self._route_execution(item.action, item.payload)

    @staticmethod
    def _invoke_actuator(action, operation, *args, **kwargs):
        require_action_allowed(action)
        return operation(*args, **kwargs)

    @staticmethod
    async def _complete_physical(operation, *args, **kwargs):
        """Keep the actuator lock until a native worker really ends on cancellation."""
        worker = asyncio.create_task(asyncio.to_thread(operation, *args, **kwargs))
        cancelled = False
        while True:
            try:
                result = await asyncio.shield(worker)
                break
            except asyncio.CancelledError:
                if worker.cancelled():
                    raise
                cancelled = True
        if cancelled:
            raise asyncio.CancelledError
        return result

    async def _route_execution(self, action: str, payload: dict[str, Any]) -> Any:
        require_action_allowed(action)
        match action:
            case "activate_ui_control":
                async with self._input_lock:
                    require_action_allowed(action)
                    from uia_control_executor import activate_ui_control
                    # Cancellation/timeout does not stop a native COM call. Keep
                    # the exclusive lock until the worker really terminates.
                    return await self._complete_physical(
                        activate_ui_control, payload.get('target'), payload.get('intent'),
                        value=payload.get('value'), baseline_input=payload.get('baseline_input'))
            # Physical Actuator Layer (Exclusive Lock)
            case "mouse_move" | "mouse_click" | "mouse_click_at" | "right_click" | "scroll" | "send_text" | "hotkey" | "mouse_drag":
                async with self._input_lock:
                    require_action_allowed(action)
                    if self._effector is None:
                        raise ValueError("Effector subsystem not mounted.")
                    loop = asyncio.get_running_loop()
                    match action:
                        case "mouse_drag":
                            return await self._complete_physical(
                                self._invoke_actuator, action, self._effector.mouse_drag,
                                payload["x1"], payload["y1"], payload["x2"], payload["y2"],
                            )
                        case "mouse_click_at":
                            def move_and_click():
                                require_action_allowed(action)
                                if self._effector.mouse_move(payload["x"], payload["y"]) is not True:
                                    raise RuntimeError("Movimento do mouse falhou")
                                require_action_allowed(action)
                                return self._effector.mouse_click(payload.get("button", "left"), payload.get("count", 1))
                            return await self._complete_physical(move_and_click)
                        case "mouse_move":
                            return await self._complete_physical(
                                self._invoke_actuator, action, self._effector.mouse_move, payload.get("x", 0), payload.get("y", 0)
                            )
                        case "mouse_click":
                            return await self._complete_physical(
                                self._invoke_actuator, action,
                                self._effector.mouse_click,
                                payload.get("button", "left"),
                                payload.get("count", 1),
                            )
                        case "right_click":
                            return await self._complete_physical(self._invoke_actuator, action, self._effector.mouse_click, "right")
                        case "scroll":
                            return await self._complete_physical(
                                self._invoke_actuator, action, self._effector.mouse_scroll,
                                direction=payload.get("direction", "down"), clicks=payload.get("clicks", 1),
                            )
                        case "send_text":
                            return await self._complete_physical(
                                self._invoke_actuator, action, self._effector.send_text, payload.get("text", "")
                            )
                        case "hotkey":
                            return await self._complete_physical(
                                self._invoke_actuator, action, self._effector.send_hotkey, payload.get("keys", [])
                            )

            # Visual Sensor Layer (Shared Concurrency Limit)
            case "capture_screen":
                async with self._sensor_sem:
                    if self._perception is None:
                        raise ValueError("Perception subsystem not mounted.")
                    loop = asyncio.get_running_loop()
                    roi = payload.get("roi")
                    return await loop.run_in_executor(None, self._perception.capture, roi)

            # Failsafe Hardware Abort
            case "emergency_stop":
                async with self._input_lock:
                    # Clear pending commands in queue
                    while not self._queue.empty():
                        try:
                            item = self._queue.get_nowait()
                            if not item.fut.done():
                                item.fut.set_result(
                                    CommandResult(
                                        cmd_id=item.cmd_id,
                                        action=item.action,
                                        status="aborted",
                                        result=None,
                                        latency_ms=0.0,
                                        error="Aborted by emergency stop signal.",
                                    )
                                )
                            self._queue.task_done()
                        except asyncio.QueueEmpty:
                            break
                    return True

            case _:
                raise NotImplementedError(f"Unsupported actuator bridge command: {action}")
