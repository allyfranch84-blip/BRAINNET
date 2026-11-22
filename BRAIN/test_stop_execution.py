import asyncio
from pathlib import Path
import subprocess
import shutil
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from BRAINNET import BrainnetBridge


@pytest.mark.parametrize("result,expected", [
    ({"ok": True, "cleared_actions": 3}, {"ok": True}),
    ({"ok": False, "errors": ["queue unavailable"]}, {"ok": False, "errors": ["queue unavailable"]}),
])
def test_stop_execution_reports_only_confirmed_stop(result, expected):
    bridge = object.__new__(BrainnetBridge)
    with patch.object(BrainnetBridge, "panic_stop", return_value=result) as stop:
        assert bridge.stop_execution() == expected
    stop.assert_called_once_with()


def test_stop_execution_cancels_execution_task_without_cancelling_kernel_tasks():
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever)
    thread.start()
    async def setup():
        return asyncio.create_task(asyncio.sleep(300)), asyncio.create_task(asyncio.sleep(300))
    execution, observer = asyncio.run_coroutine_threadsafe(setup(), loop).result(2)
    bridge = object.__new__(BrainnetBridge)
    bridge._kernel = SimpleNamespace(loop=loop, bridge=SimpleNamespace(stop=AsyncMock(), clear_pending_actions=AsyncMock(return_value=1)), voice=SimpleNamespace(parar=MagicMock()))
    bridge._ear = SimpleNamespace(stop_listening=MagicMock())
    bridge._skill_abort = threading.Event()
    bridge._execution_token = threading.Event()
    bridge._execution_future = execution
    try:
        assert bridge.stop_execution() == {"ok": True}
        async def states():
            await asyncio.sleep(0)
            return execution.cancelled(), observer.done()
        assert asyncio.run_coroutine_threadsafe(states(), loop).result(2) == (True, False)
        bridge._kernel.voice.parar.assert_called_once()
        bridge._kernel.bridge.clear_pending_actions.assert_awaited_once()
    finally:
        async def cleanup():
            observer.cancel()
            execution.cancel()
            await asyncio.gather(observer, execution, return_exceptions=True)
        asyncio.run_coroutine_threadsafe(cleanup(), loop).result(2)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(2)
        loop.close()


def test_frontend_toggle_waits_for_stop_and_ignores_cancelled_response():
    root = Path(__file__).resolve().parents[1]
    ui = root / "INTERFACE DE USUARIO" / "BRAINDET IU" / "project"
    node_exe = shutil.which("node") or str(root / "node.exe")
    result = subprocess.run([node_exe, str(Path(__file__).parent / "test_data" / "send_stop_test.cjs"), str(ui)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Send/Stop behavior OK" in result.stdout
