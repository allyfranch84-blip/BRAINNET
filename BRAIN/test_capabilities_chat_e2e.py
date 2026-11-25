"""Integration through the chat entrypoint using a disposable project directory."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from BRAINNET import BrainnetBridge, BrainnetKernel
from engineering_agent import _find_node
from project_conversation import ProjectConversation
from research_sources import search_wikipedia


@pytest.fixture
def chat(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAINNET_MINIMAL", "1")
    monkeypatch.delenv("BRAINNET_MOTOR_SEMANTIC", raising=False)
    monkeypatch.delenv("BRAINNET_PERSIST_EXPERIENCES", raising=False)
    bridge = BrainnetBridge(BrainnetKernel())
    bridge._project_conversation = ProjectConversation(tmp_path / "projects")
    return bridge


def test_real_chat_clarifies_and_verifies_a_racing_project(chat, tmp_path):
    if _find_node() is None:
        pytest.skip("Node.js required for real runtime verification")
    first = chat.send_command("Faz um jogo d corida")
    assert first["status"] == "CLARIFICATION_REQUIRED"
    assert "navegador" in first["reply"] and "2D" in first["reply"]
    assert not (tmp_path / "projects").exists()
    second = chat.send_command("no navegador")
    assert second["status"] == "CLARIFICATION_REQUIRED"
    assert "2D" in second["reply"]
    final = chat.send_command("2d")
    assert final["status"] == "GOAL_VERIFIED", final
    assert first["project_id"] == second["project_id"] == final["project_id"]
    assert final["project_result"]["attempts"][0]["status"] == "GOAL_VERIFIED"
    assert final["dispatched"] is False
    output = Path(final["project_result"]["project_path"])
    assert (output / "index.html").is_file() and (output / "game.js").is_file()


def test_chat_keeps_unsupported_request_in_clarification(chat, tmp_path):
    assert chat.send_command("Faça um jogo de corrida em 3D para Windows")["status"] == "CLARIFICATION_REQUIRED"
    unrelated = chat.send_command("/codigo mapa actuator_bridge.py")
    assert unrelated["status"] == "OBSERVED"
    assert chat.send_command("/projeto cancelar")["status"] == "CANCELLED"
    assert chat.send_command("2D no navegador")["status"] == "UNAVAILABLE"
    assert not (tmp_path / "projects").exists()


def test_chat_returns_static_code_map_with_real_line_evidence(chat):
    result = chat.send_command("/código mapa actuator_bridge.py execution_authority.py")
    assert result["status"] == "OBSERVED" and result["dispatched"] is False
    report = result["code_summary"]
    assert report["analysis"] == "static_references_only"
    assert len(report["modules"]) == 2
    row = report["modules"][0]
    assert len(row["sha256"]) == 64 and row["symbols"] and row["dependencies"]
    assert any(s["name"] == "ActuatorBridge" for s in row["symbols"])
    assert chat.send_command("/codigo mapa ../train_lora.py")["status"] == "ACTION_BLOCKED"


def test_chat_checkup_reads_the_current_windows_process(chat):
    result = chat.send_command("/checkup")
    assert result["status"] == "OBSERVED"
    assert f"PID {os.getpid()}" in result["reply"]
    assert "RAM disponível:" in result["reply"]


def test_chat_asks_to_disambiguate_before_observation_or_inference(chat, monkeypatch):
    monkeypatch.setenv("BRAINNET_MOTOR_SEMANTIC", "1")
    with patch("capability_lab.observe_physical_monitor") as observe, \
         patch("inference_backend.HTTPInferenceBackend") as model:
        result = chat.send_command("Abra o Paint ou o Bloco de Notas")
    assert result["status"] == "CLARIFICATION_REQUIRED" and result["dispatched"] is False
    observe.assert_not_called()
    model.assert_not_called()


def test_chat_fast_path_for_a_typo_still_routes_through_motor_verification(chat, monkeypatch):
    monkeypatch.setenv("BRAINNET_MOTOR_SEMANTIC", "1")
    with patch("capability_lab.observe_physical_monitor", return_value={}), \
         patch("inference_backend.HTTPInferenceBackend.chat") as infer, \
         patch.object(chat, "_run_remembered_plan", return_value={"status": "ACTION_BLOCKED"}) as dispatch:
        result = chat.send_command("Abra o Blco de Notas")
    assert result["status"] == "ACTION_BLOCKED"
    assert dispatch.call_args.args[0]["steps"] == [{"action": "open_app", "target": "notepad"}]
    infer.assert_not_called()


def test_research_returns_only_bounded_mediawiki_identities():
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps({"query": {"search": [
        {"title": "Alan Turing", "pageid": 26201},
        {"title": "invalid", "pageid": "https://example.com"},
    ]}}).encode()
    with patch("research_sources.urlopen", return_value=response) as opener:
        results = search_wikipedia("Alan Turing")
    assert results == [{"url": "https://pt.wikipedia.org/?curid=26201", "title": "Alan Turing",
                        "page_id": 26201, "source": "wikipedia.pt"}]
    assert "srsearch=Alan+Turing" in opener.call_args.args[0].full_url


@pytest.mark.skipif(os.environ.get("BRAINNET_TEST_WIKIPEDIA") != "1", reason="opt-in public network integration")
def test_real_chat_searches_portuguese_wikipedia(chat):
    result = chat.send_command("/pesquisa Wikipédia Alan Turing")
    assert result["status"] == "SOURCES_FOUND", result
    assert any(item["title"] == "Alan Turing" and item["page_id"] > 0 for item in result["sources"])
    assert all(item["source"] == "wikipedia.pt" for item in result["sources"])
