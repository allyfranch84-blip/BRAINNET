"""Ghost-execution regressions. All actuators, browser calls and plans are mocked."""
import ast
import asyncio
import inspect
import queue
import textwrap
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import BRAINNET
from BRAINNET import BrainnetBridge, BrainnetKernel
from actuator_bridge import ActuatorBridge, PrioritizedCommand
from browser_bridge import BrowserDeepBridge
from causal_trajectory import CausalTrajectoryEngine, WindowsAppResolver
from execution_authority import authorization_scope, authorized_trajectory, background_only, require_action_allowed
from theory_of_mind import MotorGateState


@pytest.mark.parametrize("action", ["TYPE", "CLICK", "ENSURE_APP", "HOTKEY", "FOCUS_WINDOW", "WAIT"])
def test_background_step_blocks_before_any_actuation(action, caplog):
    engine = object.__new__(CausalTrajectoryEngine)
    with pytest.raises(PermissionError, match="BLOQUEIO_DE_SEGURANCA"):
        asyncio.run(engine._executar_passo_individual({"acao": action}, is_background=True))
    assert "Ação de escrita em background" in caplog.text


@pytest.mark.parametrize("action", ["READ", "INSPECT"])
def test_background_read_only_steps_remain_available(action):
    engine = object.__new__(CausalTrajectoryEngine)
    engine.ctx_engine = MagicMock()
    engine.ctx_engine.capture_foreground_context.return_value = {"hwnd": 77}
    assert asyncio.run(engine._executar_passo_individual({"acao": action}, is_background=True)) == {"hwnd": 77}


def test_background_cannot_override_provenance_using_false_flag():
    engine = object.__new__(CausalTrajectoryEngine)
    @background_only
    async def background():
        await engine._executar_passo_individual({"acao": "TYPE"}, is_background=False)
    with pytest.raises(PermissionError, match="background"):
        asyncio.run(background())


@pytest.mark.parametrize("method", [WindowsAppResolver.launch_app, WindowsAppResolver.find_and_focus_window])
def test_resolver_rejects_background_before_reading_or_focusing_windows(method):
    with pytest.raises(PermissionError, match="background"):
        method("notepad", is_background=True)


def test_background_cannot_start_or_replay_a_trajectory():
    engine = object.__new__(CausalTrajectoryEngine)
    with pytest.raises(PermissionError, match="background"):
        asyncio.run(engine.executar_trajetoria_completa("old command", is_background=True))


def test_cancellation_revokes_authority_in_executor_thread():
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    result = []
    def delayed_worker():
        entered.set()
        release.wait(2)
        try:
            require_action_allowed("TYPE")
            result.append("UNSAFE")
        except PermissionError:
            result.append("BLOCKED")
        finally:
            finished.set()
    @authorized_trajectory
    async def action():
        await asyncio.to_thread(delayed_worker)
    async def scenario():
        task = asyncio.create_task(action())
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()
        assert await asyncio.to_thread(finished.wait, 2)
    asyncio.run(scenario())
    assert result == ["BLOCKED"]


@pytest.mark.parametrize("cancelled", [True, False])
def test_actuator_discards_cancelled_or_revoked_queued_commands(cancelled):
    async def scenario():
        bridge = ActuatorBridge(None, None)
        bridge._running = True
        future = asyncio.get_running_loop().create_future()
        token = threading.Event()
        if cancelled:
            future.cancel()
        else:
            token.set()
        bridge._queue.put_nowait(PrioritizedCommand(1, 0, "old", "send_text", {"text": "old feedback"}, 1, future, token))
        with patch.object(ActuatorBridge, "_route_execution", new_callable=AsyncMock) as route:
            worker = asyncio.create_task(bridge._worker_loop("test"))
            await asyncio.wait_for(bridge._queue.join(), 2)
            bridge._running = False
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
            route.assert_not_awaited()
        if not cancelled:
            assert future.result().status == "failed"
    asyncio.run(scenario())


def test_actuator_clears_pending_futures_without_running_them():
    async def scenario():
        bridge = ActuatorBridge(None, None)
        future = asyncio.get_running_loop().create_future()
        bridge._queue.put_nowait(PrioritizedCommand(1, 0, "old", "send_text", {}, 1, future))
        assert await bridge.clear_pending_actions() == 1
        assert future.cancelled()
        await asyncio.wait_for(bridge._queue.join(), 1)
    asyncio.run(scenario())


def test_executor_rechecks_revoked_authority_before_hardware_call():
    token = threading.Event()
    hardware = MagicMock()
    async def scenario():
        with authorization_scope(token):
            token.set()
            with pytest.raises(PermissionError, match="revogada"):
                await asyncio.to_thread(ActuatorBridge._invoke_actuator, "send_text", hardware, "old feedback")
    asyncio.run(scenario())
    hardware.assert_not_called()


def test_dom_bridge_skips_expired_commands_before_extension_poll():
    commands = queue.Queue()
    commands.put({"id": "expired", "action": "OPEN_TAB_AND_WAIT"})
    commands.put({"id": "current", "action": "CLOSE_TABS"})
    browser = SimpleNamespace(_cmd_queue=commands, _pending_results={"current": queue.Queue()})
    assert BrowserDeepBridge._next_active_command(browser, timeout=1)["id"] == "current"


@pytest.mark.parametrize("name", ["_continuous_context_logger"])
def test_observer_loops_have_no_execution_or_rem_dispatch(name):
    tree = ast.parse(textwrap.dedent(inspect.getsource(getattr(BrainnetKernel, name))))
    calls = {node.func.attr for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and not (node.func.attr == "start"
                      and ast.unparse(node.func.value) == "self.subconscious")}
    # O motor observacional também não pode chamar atuadores ou iniciar outros workers.
    from subconscious_engine import SubconsciousEngine
    subconscious_tree = ast.parse(textwrap.dedent(inspect.getsource(SubconsciousEngine)))
    subconscious_calls = {node.func.attr for node in ast.walk(subconscious_tree)
                          if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert subconscious_calls.isdisjoint({"executar_trajetoria_completa", "dispatch", "launch_app", "send_text", "send_hotkey", "mouse_click"})
    assert calls.isdisjoint({"executar_trajetoria_completa", "_executar_rem_completo", "dispatch", "launch_app", "Thread", "start"})


def test_rem_watchdog_uses_daemon_thread_and_no_actuators():
    """
    O watchdog pode disparar o ciclo REM em background, desde que seja daemon thread
    e não chame atuadores físicos. Consolidar memória é SQLite puro.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(BrainnetKernel._circadian_rem_watchdog)))
    source = textwrap.dedent(inspect.getsource(BrainnetKernel._circadian_rem_watchdog))
    # Permite threading.Thread(target=self._executar_rem_completo, daemon=True)
    assert "daemon=True" in source
    calls = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    forbidden_actuators = {"dispatch", "launch_app", "executar_trajetoria_completa", "mouse_click", "send_text", "send_hotkey"}
    assert calls.isdisjoint(forbidden_actuators)


@pytest.fixture
def bridge():
    obj = object.__new__(BrainnetBridge)
    obj._kernel, obj._tom = MagicMock(), MagicMock()
    obj._kernel.loop = None
    obj._kernel.metacognition.registrar_resultado.return_value = 0.0
    obj._kernel.blackbox.registrar_falha_e_punir.return_value = {"snapshot_id": "test"}
    obj._tom.evaluate_intent.return_value = SimpleNamespace(gate=MotorGateState.GO)
    obj._modo_coder_ativo = False
    obj._last_executed_task = "old action"
    obj._falar_seguro = MagicMock()
    obj._action_queue = queue.Queue()
    obj._action_queue.put("stale command")
    return obj


@pytest.mark.parametrize("success", [True, False])
def test_completed_or_failed_action_clears_motor_state(bridge, success):
    bridge._kernel.trajectory_engine.executar_trajetoria_completa = AsyncMock(return_value={
        "sucesso_real": success, "status": "CONCLUIDO" if success else "FALHA_REALIDADE"})
    bridge._executar_comando_interno("execute tarefa alfa", "execute tarefa alfa", "execute tarefa alfa")
    assert bridge._last_executed_task == ""
    assert bridge._action_queue.empty()
    assert bridge._last_completed_task == "execute tarefa alfa"
    token = bridge._kernel.trajectory_engine.executar_trajetoria_completa.call_args.kwargs["authorization_token"]
    assert token.is_set()


def test_bridge_timeout_cancels_future_and_revokes_token(bridge, tmp_path, monkeypatch):
    monkeypatch.setattr(BRAINNET, "__file__", str(tmp_path / "BRAINNET.py"))
    bridge._kernel.loop = MagicMock()
    bridge._kernel.trajectory_engine.executar_trajetoria_completa = AsyncMock()
    pending = MagicMock()
    pending.result.side_effect = TimeoutError("deadline")
    def submit(coroutine, loop):
        coroutine.close()
        return pending
    with patch("BRAINNET.asyncio.run_coroutine_threadsafe", side_effect=submit):
        bridge._executar_comando_interno("execute tarefa alfa", "execute tarefa alfa", "execute tarefa alfa")
    pending.cancel.assert_called_once()
    assert bridge._last_executed_task == "" and bridge._action_queue.empty()
    assert bridge._kernel.trajectory_engine.executar_trajetoria_completa.call_args.kwargs["authorization_token"].is_set()


def test_old_tab_feedback_never_reaches_llm_or_motor(bridge):
    bridge._kernel.browser_bridge.close_research_tabs.return_value = {"ok": True, "closed_count": 2}
    text = "abriu abas e não fechou"
    with patch("BRAINNET.urllib.request.urlopen", side_effect=AssertionError("No LLM")):
        result = bridge._executar_comando_interno(text, text, text)
    bridge._tom.evaluate_intent.assert_not_called()
    bridge._kernel.trajectory_engine.executar_trajetoria_completa.assert_not_called()
    bridge._kernel.browser_bridge.close_research_tabs.assert_called_once()
    assert "confirmado" in result["reply"]
    assert bridge._last_executed_task == "" and bridge._action_queue.empty()


def test_feedback_revokes_and_cancels_a_previous_live_execution(bridge):
    token, pending = threading.Event(), MagicMock()
    pending.done.return_value = False
    bridge._execution_token, bridge._execution_future = token, pending
    bridge._kernel.browser_bridge.close_research_tabs.return_value = {"ok": True}
    text = "abriu abas e não fechou"
    bridge._executar_comando_interno(text, text, text)
    assert token.is_set()
    pending.cancel.assert_called_once()
    assert bridge._execution_token is None and bridge._execution_future is None


def test_early_state_response_also_clears_stale_queue(bridge):
    bridge._kernel.context_engine.escanear_estado_janelas.return_value = []
    bridge._executar_comando_interno("você abriu?", "você abriu?", "você abriu?")
    assert bridge._action_queue.empty()
    assert bridge._last_executed_task == ""
    bridge._kernel.trajectory_engine.executar_trajetoria_completa.assert_not_called()


def test_observer_executor_preserves_background_restriction(caplog):
    kernel = object.__new__(BrainnetKernel)
    kernel.is_running = True
    kernel._last_logged_hwnd = 0
    kernel.context_engine = MagicMock()
    def accidental_write():
        kernel.is_running = False
        require_action_allowed("TYPE")
        return {"hwnd": 77}
    kernel.context_engine.capture_foreground_context.side_effect = accidental_write
    with patch("BRAINNET.asyncio.sleep", new_callable=AsyncMock):
        asyncio.run(kernel._continuous_context_logger())
    assert "Ação de escrita em background" in caplog.text


def test_actuator_rejects_background_priority_before_enqueuing():
    from actuator_bridge import CommandPriority
    bridge = ActuatorBridge(None, None)
    with pytest.raises(PermissionError, match="background"):
        asyncio.run(bridge.dispatch("send_text", {"text": "old"}, priority=CommandPriority.BACKGROUND))
    assert bridge._queue.empty()


@pytest.mark.parametrize("ack,success", [({"ok": True, "closed_count": 2}, True), ({"ok": True}, False)])
def test_tab_feedback_closes_only_recorded_research_ids(ack, success):
    browser = SimpleNamespace(_research_tab_ids={17, 23}, extension_connected=True,
                              send_command=MagicMock(return_value=ack))
    result = BrowserDeepBridge.close_research_tabs(browser)
    browser.send_command.assert_called_once_with("CLOSE_TABS", tab_ids=[17, 23], timeout=5.0)
    assert result["ok"] is success


def test_tab_feedback_without_research_ids_does_not_close_anything():
    browser = SimpleNamespace(_research_tab_ids=set(), extension_connected=True, send_command=MagicMock())
    assert BrowserDeepBridge.close_research_tabs(browser)["ok"] is False
    browser.send_command.assert_not_called()
