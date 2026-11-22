import hashlib
import json
import sqlite3
from unittest.mock import patch

import numpy as np
import pytest

from semantic_concepts import ConceptGraph
from test_semantic_concepts import semantic_bridge, response


DEFINITION = "Um aplicativo BrainNet organiza conceitos em uma rede para apoiar tarefas computacionais. Essa composição descreve uma função conceitual."


def parents(bridge):
    graph = ConceptGraph(bridge._kernel.pdag.db_path, bridge._kernel.vsa)
    for name, definition in [("brainnet", "Sistema cognitivo local."), ("aplicativo", "Programa para executar tarefas.")]:
        graph.save(name, definition, [], [], graph.vsa.text_to_hypervector(name), True, {})
    return graph


def test_synthesis_runs_after_fhrr_persistence_and_updates_definition(semantic_bridge):
    graph = parents(semantic_bridge)
    expected = graph.vsa.bind(graph.load("brainnet"), graph.vsa.permute(graph.load("aplicativo"), 1))
    def generate(request, **kwargs):
        # The vector is already durable before contacting Ollama.
        np.testing.assert_array_equal(graph.load("brainnet_aplicativo"), expected)
        payload = json.loads(request.data)
        assert payload["model"] == "qwen2.5:1.5b" and payload["keep_alive"] == -1
        assert "no máximo 2 frases" in payload["prompt"]
        assert "Sistema cognitivo local." in payload["prompt"]
        return response(json.dumps({"definicao": DEFINITION}))
    with patch("urllib.request.urlopen", side_effect=generate):
        result = semantic_bridge.compose_concepts("brainnet", "aplicativo")
    assert result == {"ok": True, "id": "brainnet_aplicativo", "definicao": DEFINITION, "synthesis_ok": True}
    assert graph.details("brainnet_aplicativo")[0]["definicao"] == DEFINITION
    assert graph.details("brainnet_aplicativo")[0]["status"] == 0
    np.testing.assert_array_equal(graph.load("brainnet_aplicativo"), expected)
    with sqlite3.connect(graph.db_path) as conn:
        evidence = json.loads(conn.execute("SELECT evidence_json FROM concept_sources WHERE concept_id = 'brainnet_aplicativo'").fetchone()[0])
    assert evidence["parents"] == ["brainnet", "aplicativo"]
    assert evidence["semantic_synthesis"]["model"] == "qwen2.5:1.5b"


@pytest.mark.parametrize("answer", [{"definicao": ""}, {"definicao": "Uma frase. Duas frases. Três frases."}, {"outro": "sem schema"}])
def test_invalid_synthesis_never_replaces_stored_definition(semantic_bridge, answer):
    graph = parents(semantic_bridge)
    with patch("urllib.request.urlopen", return_value=response(json.dumps(answer))):
        result = semantic_bridge.compose_concepts("brainnet", "aplicativo")
    assert result["ok"] and not result["synthesis_ok"] and result["definicao"] is None
    assert graph.details("brainnet_aplicativo")[0]["definicao"] == "Composição ordenada de brainnet e aplicativo."


def test_offline_model_preserves_composition_and_reports_pending_synthesis(semantic_bridge):
    graph = parents(semantic_bridge)
    with patch("urllib.request.urlopen", side_effect=OSError("Ollama offline")):
        result = semantic_bridge.compose_concepts("brainnet", "aplicativo")
    assert result["ok"] and result["synthesis_ok"] is False
    assert "offline" in result["warning"]
    assert graph.load("brainnet_aplicativo").dtype == np.complex64
    with patch("urllib.request.urlopen") as model:
        assert semantic_bridge.compose_concepts("brainnet", "aplicativo")["ok"] is False
    model.assert_not_called()


def test_details_returns_actual_vector_digest_and_validation_status(semantic_bridge):
    graph = parents(semantic_bridge)
    with sqlite3.connect(graph.db_path) as conn:
        conn.execute("UPDATE concepts SET status_habilidade = 1, sinonimos = ? WHERE id = 'brainnet'", (json.dumps(["sistema cognitivo"]),))
    result = semantic_bridge.get_semantic_concept_details("brainnet")
    assert result["ok"] and result["status"] == 1
    assert result["sinonimos"] == ["sistema cognitivo"]
    assert result["vector_id"] == "sha256:" + hashlib.sha256(graph.load("brainnet").tobytes()).hexdigest()
    json.dumps(result)  # No vector/BLOB is exposed to React.
    assert semantic_bridge.get_semantic_concept_details("inexistente")["ok"] is False
    semantic_bridge._kernel.trajectory_engine.executar_trajetoria_completa.assert_not_called()
