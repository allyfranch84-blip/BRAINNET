import asyncio
import threading

from actuator_bridge import ActuatorBridge
from execution_authority import authorization_scope


def test_concurrent_pending_pointers_have_independent_ids_and_clear():
    async def exercise():
        bridge = ActuatorBridge()
        bridge._running = True
        events = []
        bridge.pointer_observer = events.append
        with authorization_scope(threading.Event()):
            tasks = [asyncio.create_task(bridge.dispatch("mouse_move", {"x": x, "y": 20}))
                     for x in (10, 30)]
            await asyncio.sleep(0)
            assert [item["target"] for item in events] == [(10, 20), (30, 20)]
            assert len({item["id"] for item in events}) == 2
            first, second = [bridge._queue.get_nowait() for _ in tasks]
            second.fut.set_result(None)
            await tasks[1]
            assert events[-1] == {"id": second.cmd_id, "active": False}
            first.fut.set_result(None)
            await tasks[0]
            assert events[-1] == {"id": first.cmd_id, "active": False}

    asyncio.run(exercise())
