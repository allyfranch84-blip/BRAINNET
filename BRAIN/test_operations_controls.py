import asyncio
import json
import sqlite3
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from BRAINNET import BrainnetBridge, BrainnetKernel
from execution_authority import command_authority, require_action_allowed
from operations_status import diagnostics, panic_stop, usage_report
from owned_processes import track_process
from semantic_concepts import ConceptGraph
from test_semantic_concepts import semantic_bridge


def test_logger_exits_when_thread_executor_is_shutting_down(caplog):
    kernel = object.__new__(BrainnetKernel)
    kernel.is_running = True
    kernel.context_engine = SimpleNamespace(capture_foreground_context=MagicMock())
    with patch("BRAINNET.asyncio.sleep", new_callable=AsyncMock), \
         patch("BRAINNET.asyncio.to_thread", new_callable=AsyncMock, side_effect=RuntimeError("cannot schedule new futures after shutdown")) as worker:
        asyncio.run(kernel._continuous_context_logger())
    worker.assert_awaited_once()
    assert "Falha ao registrar contexto" not in caplog.text


def test_usage_counts_only_observed_outcomes_and_measured_latency(semantic_bridge):
    pdag = semantic_bridge._kernel.pdag
    for success, latency in [(1, 50), (0, 150), (1, None)]:
        pdag.record_transition("a", "b", "c", success, .3, "notepad", elapsed_ms=latency)
    assert pdag.flush_pending_writes(2)
    with sqlite3.connect(pdag.db_path) as conn:
        conn.execute("INSERT INTO transitions (state_before_hash, action_hash, state_after_hash, lambda_obs, ncd, app_name, timestamp, source) VALUES ('a','b','c',1,.3,'synthetic',0,'synthetic')")
    report = usage_report(pdag)
    assert report["total_executions"] == 3
    assert report["success_rate"] == pytest.approx(200/3)
    assert report["average_latency_ms"] == 100
    assert report["latency_samples"] == 2


def test_usage_does_not_invent_latency_for_old_data(semantic_bridge):
    pdag = semantic_bridge._kernel.pdag
    pdag.record_transition("a", "b", "c", 1, .3, "notepad")
    assert pdag.flush_pending_writes(2)
    assert usage_report(pdag)["average_latency_ms"] is None


def test_diagnostics_reports_disconnection_without_loading_models(semantic_bridge):
    semantic_bridge._kernel.browser_bridge = SimpleNamespace(extension_connected=True)
    with patch("operations_status.urllib.request.urlopen", side_effect=OSError("offline")) as ping, \
         patch("operations_status.importlib.util.find_spec", return_value=None):
        result = diagnostics(semantic_bridge)
        assert result["ollama"]["ok"] is False
        assert result["ocr"]["ok"] is False
        assert result["voice"]["ok"] is False
        assert result["extension"]["ok"] is True
        assert diagnostics(semantic_bridge) == result
        ping.assert_called_once()


def test_routes_api_and_reversion_reset_semantic_validation(semantic_bridge):
    pdag, vsa = semantic_bridge._kernel.pdag, semantic_bridge._kernel.vsa
    graph = ConceptGraph(pdag.db_path, vsa)
    graph.save("teste", "Teste", [], [], vsa.generate_vector("test"), True, {})
    for text in ("v1", "v2"):
        assert pdag.record_user_confirmed_route("trajectory:teste", "teste", {"passos": [{"acao": "TYPE", "text": text}]}, vsa.generate_vector(text), vsa)
        pdag.link_semantic_skill("teste", "trajectory:teste")
    pdag.validate_semantic_skill("trajectory:teste", [{"feedback": {"lambda_obs": 1, "ncd_real": .3}}])
    assert graph.details()[0]["status"] == 2
    assert semantic_bridge.get_routes()[0]["version"] == 2
    assert semantic_bridge.manage_route("revert", "trajectory:teste")["ok"]
    assert graph.details()[0]["status"] == 1
    assert semantic_bridge.get_routes()[0]["version"] == 3
    assert len(semantic_bridge.get_route_versions("teste")) == 3
    assert semantic_bridge.manage_route("deactivate", "teste")["ok"]
    assert semantic_bridge.get_routes() == []
    assert semantic_bridge.manage_route("invalid", "teste")["ok"] is False


def test_panic_revokes_waiting_command_clears_audio_and_owned_processes():
    started, release = threading.Event(), threading.Event()
    outcomes = []
    process = MagicMock(pid=123)
    process.poll.return_value = None
    @command_authority
    def waiting_command():
        track_process(process)
        started.set()
        release.wait(3)
        try:
            require_action_allowed("TYPE")
            outcomes.append("unsafe")
        except PermissionError:
            outcomes.append("blocked")
    thread = threading.Thread(target=waiting_command)
    thread.start()
    assert started.wait(2)
    actuator = SimpleNamespace(stop=AsyncMock(), clear_pending_actions=AsyncMock(return_value=2))
    bridge = SimpleNamespace(_execution_token=threading.Event(),
        _execution_future=MagicMock(), _professor_mode={"conceito": "pending"},
        _ear=SimpleNamespace(stop_listening=MagicMock()),
        _kernel=SimpleNamespace(loop=None, bridge=actuator, voice=SimpleNamespace(parar=MagicMock()), _action_queue=["stale"]),
        _action_queue=["stale"], _last_executed_task="stale", _last_completed_task="stale")
    owner = MagicMock()
    owner.children.return_value = []
    try:
        with patch("psutil.Process", return_value=owner), patch("psutil.wait_procs", return_value=([owner], [])):
            result = panic_stop(bridge)
    finally:
        release.set()
        thread.join(3)
    assert result["ok"] and result["terminated_processes"] == 1 and result["cleared_actions"] == 2
    process.terminate.assert_called_once()
    actuator.stop.assert_awaited_once()
    actuator.clear_pending_actions.assert_awaited_once()
    bridge._kernel.voice.parar.assert_called_once()
    assert outcomes == ["blocked"]
    assert bridge._professor_mode is None and bridge._action_queue == bridge._kernel._action_queue == []
    # _skill_abort era vestigial e foi removido do código de produção.
    # O cancelamento real vem de revoke_all_commands() + execution_token.set().
    @command_authority
    def fresh_command():
        require_action_allowed("TYPE")
        return True
    assert fresh_command()
