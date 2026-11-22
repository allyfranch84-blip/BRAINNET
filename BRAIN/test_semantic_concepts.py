import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from BRAINNET import BrainnetBridge
from hyperdimensional import FHRRHyperdimensionalEngine
from pdag_engine import MyelinatedPDAGEngine
from semantic_concepts import ConceptGraph


@pytest.fixture
def semantic_bridge(tmp_path):
    vsa = FHRRHyperdimensionalEngine(dim=64)
    pdag = MyelinatedPDAGEngine(str(tmp_path / "semantic.db"), dim=64, max_nodes=4)
    bridge = object.__new__(BrainnetBridge)
    bridge._kernel = SimpleNamespace(vsa=vsa, pdag=pdag, trajectory_engine=MagicMock())
    bridge._clear_pending_actions = MagicMock()
    bridge._professor_mode = None
    bridge._tom = MagicMock()
    yield bridge
    pdag.close()


def send(bridge, text):
    return bridge._executar_comando_interno(text, text.casefold(), text.casefold())


def response(raw):
    mocked = MagicMock()
    mocked.__enter__.return_value.read.return_value = json.dumps({"response": raw}).encode()
    return mocked


SOURCES = {"ok": True, "results": [{"title": "Dicionário", "snippet": "Abrir significa tornar aberto. A palavra pode indicar remover uma barreira, permitir o acesso ou iniciar uma atividade.", "url": "https://example.org/abrir"}]}


def test_web_learning_persists_definition_vector_and_sources(semantic_bridge):
    data = {"definicao": "Tornar aberto.", "sinonimos": ["descerrar"], "antonimos": ["fechar"]}
    with patch.object(BrainnetBridge, "web_search_autonomous", return_value=SOURCES) as search, \
         patch("urllib.request.urlopen", return_value=response(json.dumps(data))) as llm:
        result = send(semantic_bridge, "/autoprofesor Abrir")
    assert "aprendido e salvo" in result["reply"]
    search.assert_called_once_with("O que significa abrir")
    payload = json.loads(llm.call_args.args[0].data)
    assert payload["model"] == "qwen2.5:1.5b" and payload["format"]["additionalProperties"] is False
    graph = ConceptGraph(semantic_bridge._kernel.pdag.db_path, semantic_bridge._kernel.vsa)
    np.testing.assert_array_equal(graph.load("abrir"), graph.vsa.text_to_hypervector("abrir"))
    with sqlite3.connect(graph.db_path) as conn:
        assert conn.execute("SELECT definicao, is_primario FROM concepts").fetchone() == ("Tornar aberto.", 1)
        assert "https://example.org/abrir" in conn.execute("SELECT evidence_json FROM concept_sources").fetchone()[0]
    semantic_bridge._tom.evaluate_intent.assert_not_called()
    semantic_bridge._kernel.trajectory_engine.executar_trajetoria_completa.assert_not_called()


def test_composition_is_exact_persistent_and_listed_alphabetically(semantic_bridge):
    graph = ConceptGraph(semantic_bridge._kernel.pdag.db_path, semantic_bridge._kernel.vsa)
    for name in ("abrir", "aplicativo"):
        graph.save(name, name, [], [], graph.vsa.text_to_hypervector(name), True, {})
    with patch("urllib.request.urlopen", side_effect=AssertionError("Sem LLM")):
        assert "/professor abrir_aplicativo" in send(semantic_bridge, "/compor abrir aplicativo")["reply"]
        assert send(semantic_bridge, "/ensinar")["reply"].splitlines() == ["[PRIMÁRIO] abrir", "[COMPOSTO] abrir_aplicativo", "[PRIMÁRIO] aplicativo"]
    reopened = ConceptGraph(graph.db_path, graph.vsa)
    np.testing.assert_allclose(reopened.load("abrir_aplicativo"), graph.vsa.bind(graph.load("abrir"), graph.vsa.permute(graph.load("aplicativo"), 1)))
    semantic_bridge._kernel.trajectory_engine.executar_trajetoria_completa.assert_not_called()


@pytest.mark.parametrize("raw", ['{}', '[]', '{"definicao":"","sinonimos":[],"antonimos":[]}',
                                '{"definicao":"teste","sinonimos":"x","antonimos":[]}'])
def test_invalid_extraction_saves_nothing(semantic_bridge, raw):
    with patch.object(BrainnetBridge, "web_search_autonomous", return_value=SOURCES), patch("urllib.request.urlopen", return_value=response(raw)):
        assert "não concluída" in send(semantic_bridge, "/autoprofesor abrir")["reply"]
    with sqlite3.connect(semantic_bridge._kernel.pdag.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0] == 0


def test_no_web_evidence_uses_model_with_explicit_local_provenance(semantic_bridge):
    data = {"definicao": "Tornar aberto.", "sinonimos": ["descerrar", "destrancar", "iniciar"], "antonimos": []}
    with patch.object(BrainnetBridge, "web_search_autonomous", return_value={"ok": True, "results": []}), \
         patch("urllib.request.urlopen", return_value=response(json.dumps(data))) as llm:
        assert "aprendido e salvo" in send(semantic_bridge, "/autoprofesor abrir")["reply"]
    assert "Sem consulta web" in json.loads(llm.call_args.args[0].data)["prompt"]
    with sqlite3.connect(semantic_bridge._kernel.pdag.db_path) as conn:
        evidence = json.loads(conn.execute("SELECT evidence_json FROM concept_sources").fetchone()[0])
    assert evidence["origin"] == "llm_local" and evidence["sources"] == []


def test_missing_parent_no_partial_composition(semantic_bridge):
    assert "não encontrado" in send(semantic_bridge, "/compor abrir ausente")["reply"]
    assert "Nenhum conceito" in send(semantic_bridge, "/ensinar")["reply"]


def test_sql_text_is_bound_and_duplicate_does_not_overwrite(semantic_bridge):
    graph = ConceptGraph(semantic_bridge._kernel.pdag.db_path, semantic_bridge._kernel.vsa)
    name = "x'; DROP TABLE concepts; --"
    vector = graph.vsa.text_to_hypervector(name)
    graph.save(name, "original", [], [], vector, True, {})
    with pytest.raises(sqlite3.IntegrityError):
        graph.save(name, "replacement", [], [], vector, False, {})
    assert graph.list_concepts() == [(name.casefold(), 1)]


def test_corrupt_vector_rejected(semantic_bridge):
    graph = ConceptGraph(semantic_bridge._kernel.pdag.db_path, semantic_bridge._kernel.vsa)
    with pytest.raises(ValueError):
        graph.save("ruim", "x", [], [], np.ones(3), True, {})


def test_teacher_session_has_priority_over_concept_commands(semantic_bridge):
    semantic_bridge._professor_mode = {"etapa": "conceito"}
    assert "Ensino ativo" in send(semantic_bridge, "/ensinar")["reply"]
