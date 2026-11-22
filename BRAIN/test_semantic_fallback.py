import json
import sqlite3
from unittest.mock import patch

import pytest

from BRAINNET import BrainnetBridge
from semantic_concepts import normalize_concept
from test_semantic_concepts import semantic_bridge, response


LOCAL = {"definicao": "Um aplicativo é um programa para realizar tarefas.", "sinonimos": ["programa", "software", "aplicação"], "antonimos": []}


@pytest.mark.parametrize("name", ["o que é aplicativo?", "O que significa aplicativo", "explique aplicativo", "qual é o significado de aplicativo", "aplicativo"])
def test_query_normalization(name):
    assert normalize_concept(name) == "aplicativo"


@pytest.mark.parametrize("web", [{"ok": True, "results": []}, {"ok": False},
                                 {"ok": True, "results": [{"snippet": "breve", "url": "https://example.org"}]}])
def test_missing_or_short_web_falls_back_and_saves(semantic_bridge, web):
    with patch.object(BrainnetBridge, "web_search_autonomous", return_value=web) as search, \
         patch("urllib.request.urlopen", return_value=response(json.dumps(LOCAL))) as model:
        result = semantic_bridge.learn_concept_web("o que é aplicativo")
    assert result["ok"] is True and result["definicao"] == LOCAL["definicao"]
    assert result["origem"] == "llm_local" and result["validado_web"] is False
    search.assert_called_once_with("O que significa aplicativo")
    payload = json.loads(model.call_args.args[0].data)
    assert payload["model"] == "qwen2.5:1.5b" and payload["format"]["additionalProperties"] is False
    assert "aplicativo" in payload["prompt"]
    rows = semantic_bridge.get_semantic_concepts()
    assert rows[0]["id"] == "aplicativo" and rows[0]["sinonimos"] == LOCAL["sinonimos"]


def test_web_exception_and_repeat_do_not_require_an_extension(semantic_bridge):
    with patch.object(BrainnetBridge, "web_search_autonomous", side_effect=OSError("Site bloqueado")), \
         patch("urllib.request.urlopen", return_value=response(json.dumps(LOCAL))):
        assert semantic_bridge.learn_concept_web("aplicativo")["ok"] is True
    with patch.object(BrainnetBridge, "web_search_autonomous", side_effect=AssertionError("Já salvo")):
        assert semantic_bridge.learn_concept_web("o que é aplicativo")["ok"] is True
    assert len(semantic_bridge.get_semantic_concepts()) == 1


@pytest.mark.parametrize("data", [{"definicao": "", "sinonimos": ["a", "b", "c"], "antonimos": []},
                                 {"definicao": "x", "sinonimos": ["a"], "antonimos": []}, {}])
def test_invalid_local_answer_is_not_persisted(semantic_bridge, data):
    with patch.object(BrainnetBridge, "web_search_autonomous", return_value={"ok": False}), \
         patch("urllib.request.urlopen", return_value=response(json.dumps(data))):
        result = semantic_bridge.learn_concept_web("aplicativo")
    assert result["ok"] is False and result["error"]
    assert semantic_bridge.get_semantic_concepts() == []


def test_pdag_initialization_creates_full_concepts_schema(semantic_bridge):
    with sqlite3.connect(semantic_bridge._kernel.pdag.db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(concepts)")}
    assert {"id", "definicao", "sinonimos", "antonimos", "vetor_fhrr", "is_primario"} <= columns
