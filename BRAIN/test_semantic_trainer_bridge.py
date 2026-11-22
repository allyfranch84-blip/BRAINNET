import json
from unittest.mock import patch

import pytest

from BRAINNET import BrainnetBridge
from semantic_concepts import ConceptGraph
from test_semantic_concepts import semantic_bridge, SOURCES, response


def test_trainer_learning_returns_real_definition_and_refreshable_details(semantic_bridge):
    definition = {"definicao": "Tornar aberto.", "sinonimos": ["descerrar"], "antonimos": ["fechar"]}
    with patch.object(BrainnetBridge, "web_search_autonomous", return_value=SOURCES), \
         patch("urllib.request.urlopen", return_value=response(json.dumps(definition))):
        result = semantic_bridge.learn_concept_web("abrir")
        assert result["ok"] is True and result["definicao"] == definition["definicao"]
    rows = semantic_bridge.get_semantic_concepts()
    assert rows == [{"id": "abrir", **definition, "is_primario": True, "status": 0}]
    json.dumps(rows)  # Bridge payload contains metadata, never ndarray/BLOB.
    semantic_bridge._tom.evaluate_intent.assert_not_called()
    semantic_bridge._kernel.trajectory_engine.executar_trajetoria_completa.assert_not_called()


def test_composition_bridge_reports_true_only_after_persistence(semantic_bridge):
    graph = ConceptGraph(semantic_bridge._kernel.pdag.db_path, semantic_bridge._kernel.vsa)
    for name in ("abrir", "aplicativo"):
        graph.save(name, name, [], [], graph.vsa.text_to_hypervector(name), True, {})
    with patch("urllib.request.urlopen", return_value=response(json.dumps({"definicao": "Iniciar a execução de um aplicativo."}))):
        assert semantic_bridge.compose_concepts("abrir", "aplicativo")["ok"] is True
    rows = semantic_bridge.get_semantic_concepts()
    assert next(row for row in rows if row["id"] == "abrir_aplicativo")["is_primario"] is False
    assert semantic_bridge.compose_concepts("abrir", "aplicativo")["ok"] is False
    assert semantic_bridge.compose_concepts("abrir", "ausente")["ok"] is False
    assert len(semantic_bridge.get_semantic_concepts()) == 3


def test_failed_web_and_local_model_return_structured_error(semantic_bridge):
    with patch.object(BrainnetBridge, "web_search_autonomous", return_value={"ok": True, "results": []}), \
         patch("urllib.request.urlopen", side_effect=OSError("Ollama indisponível")):
        result = semantic_bridge.learn_concept_web("abrir")
    assert result == {"ok": False, "error": "Ollama indisponível"}
    assert semantic_bridge.get_semantic_concepts() == []


def test_teacher_state_blocks_writes_from_gui_but_allows_list(semantic_bridge):
    semantic_bridge._professor_mode = {"etapa": "conceito"}
    with patch.object(BrainnetBridge, "web_search_autonomous") as search:
        result = semantic_bridge.learn_concept_web("abrir")
        assert result["ok"] is False and "Professor" in result["error"]
        assert semantic_bridge.compose_concepts("abrir", "app")["ok"] is False
        assert semantic_bridge.get_semantic_concepts() == []
    search.assert_not_called()


def test_bridge_keeps_names_with_spaces_literal(semantic_bridge):
    graph = ConceptGraph(semantic_bridge._kernel.pdag.db_path, semantic_bridge._kernel.vsa)
    for name in ("abrir", "editor de texto"):
        graph.save(name, name, [], [], graph.vsa.text_to_hypervector(name), True, {})
    with patch("urllib.request.urlopen", return_value=response(json.dumps({"definicao": "Iniciar um editor de texto."}))):
        assert semantic_bridge.compose_concepts("abrir", "editor de texto")["ok"] is True
    assert any(row["id"] == "abrir_editor de texto" for row in semantic_bridge.get_semantic_concepts())
