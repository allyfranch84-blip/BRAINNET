import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from browser_bridge import BrowserDeepBridge
from test_semantic_concepts import semantic_bridge, response, SOURCES
from test_semantic_fallback import LOCAL


TEXT = "Um aplicativo é um programa de computador destinado a realizar tarefas específicas para o usuário. Ele oferece funções e ferramentas para atender uma necessidade."


def browser_for(bridge, *, navigation_error=False, excerpt=TEXT):
    browser = object.__new__(BrowserDeepBridge)
    browser._transport = SimpleNamespace(connected=True)
    browser._research_tab_ids = {55}  # An unrelated previous research tab must survive.
    browser.ensure_preferred_browser = MagicMock(return_value="thorium")
    browser.effector = MagicMock()
    def command(action, **kwargs):
        if action == "OPEN_TAB_AND_WAIT":
            return {"ok": True, "tab_id": 17, "url": "https://www.google.com/search?q=app", "text_excerpt": "resultado", "links": [{"title": "Aplicativo", "url": "https://example.org/aplicativo"}]}
        if action == "NAVIGATE_ACTIVE_TAB":
            assert kwargs["tab_id"] == 17
            if navigation_error:
                raise RuntimeError("Extension unavailable")
            return {"ok": True, "tab_id": 17, "url": "https://example.org/aplicativo", "title": "Aplicativo", "text_excerpt": f"<nav>lixo do menu</nav><main><article><p>{excerpt}</p></article></main><script>bad()</script>", "links": []}
        if action == "CLOSE_TABS":
            assert kwargs["tab_ids"] == [17]
            return {"ok": True, "closed_count": 1}
        raise AssertionError(action)
    browser.send_command = MagicMock(side_effect=command)
    bridge._kernel.browser_bridge = browser
    return browser


def test_api_failure_uses_clean_browser_dom_before_local_knowledge(semantic_bridge):
    browser = browser_for(semantic_bridge)
    with patch.object(semantic_bridge, "web_search_autonomous", return_value={"ok": False}), \
         patch.object(semantic_bridge, "_push_event") as progress, \
         patch("urllib.request.urlopen", return_value=response(json.dumps(LOCAL))) as model:
        result = semantic_bridge.learn_concept_web("o que é aplicativo", "request-1")
    assert result["ok"] and result["origem"] == "browser" and result["validado_web"]
    payload = json.loads(model.call_args.args[0].data)
    assert TEXT in payload["prompt"]
    assert "lixo do menu" not in payload["prompt"] and "bad()" not in payload["prompt"]
    assert "Sem consulta web" not in payload["prompt"]
    assert [c.args[0] for c in browser.send_command.call_args_list] == ["OPEN_TAB_AND_WAIT", "NAVIGATE_ACTIVE_TAB", "CLOSE_TABS"]
    assert browser._research_tab_ids == {55}
    stages = [call.args[1]["stage"] for call in progress.call_args_list]
    assert stages == ["api", "browser", "extracting", "saving"]
    assert all(call.args[1]["request_id"] == "request-1" for call in progress.call_args_list)
    with sqlite3.connect(semantic_bridge._kernel.pdag.db_path) as conn:
        evidence = json.loads(conn.execute("SELECT evidence_json FROM concept_sources").fetchone()[0])
    assert evidence["sources"][0]["url"] == "https://example.org/aplicativo"
    assert evidence["origin"] == "browser"


@pytest.mark.parametrize("navigation_error,excerpt", [(True, TEXT), (False, "curto")])
def test_only_browser_failure_or_short_excerpt_allows_local_fallback(semantic_bridge, navigation_error, excerpt):
    browser = browser_for(semantic_bridge, navigation_error=navigation_error, excerpt=excerpt)
    with patch.object(semantic_bridge, "web_search_autonomous", return_value={"ok": True, "results": []}), \
         patch.object(semantic_bridge, "_push_event") as progress, \
         patch("urllib.request.urlopen", return_value=response(json.dumps(LOCAL))) as model:
        result = semantic_bridge.learn_concept_web("aplicativo", "request-2")
    assert result["ok"] and result["origem"] == "llm_local" and not result["validado_web"]
    assert "Sem consulta web" in json.loads(model.call_args.args[0].data)["prompt"]
    assert browser._research_tab_ids == {55}
    assert browser.send_command.call_args_list[-1].args == ("CLOSE_TABS",)
    assert [call.args[1]["stage"] for call in progress.call_args_list] == ["api", "browser", "local", "saving"]


def test_good_api_evidence_does_not_open_browser(semantic_bridge):
    browser = browser_for(semantic_bridge)
    with patch.object(semantic_bridge, "web_search_autonomous", return_value=SOURCES), \
         patch("urllib.request.urlopen", return_value=response(json.dumps(LOCAL))):
        result = semantic_bridge.learn_concept_web("aplicativo")
    assert result["ok"] and result["origem"] == "web"
    browser.ensure_preferred_browser.assert_not_called()
    browser.send_command.assert_not_called()


def test_disconnected_extension_is_attempted_before_model_fallback(semantic_bridge):
    browser = browser_for(semantic_bridge)
    browser._transport.connected = False
    with patch.object(semantic_bridge, "web_search_autonomous", return_value={"ok": False}), \
         patch("urllib.request.urlopen", return_value=response(json.dumps(LOCAL))):
        result = semantic_bridge.learn_concept_web("aplicativo")
    assert result["ok"] and result["origem"] == "llm_local"
    browser.ensure_preferred_browser.assert_called_once()
    browser.send_command.assert_not_called()
