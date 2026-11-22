import sqlite3

import pytest

from semantic_concepts import ConceptGraph, ensure_concept_schema
from test_semantic_concepts import semantic_bridge, send


def save_concept(bridge, name="abrir aplicativo"):
    graph = ConceptGraph(bridge._kernel.pdag.db_path, bridge._kernel.vsa)
    graph.save(name, "Definição disponível", [], [], graph.vsa.text_to_hypervector(name), True, {})
    return graph


def test_migration_preserves_existing_definition(tmp_path):
    with sqlite3.connect(tmp_path / "old.db") as conn:
        conn.execute("CREATE TABLE concepts (id TEXT PRIMARY KEY, definicao TEXT, sinonimos TEXT, antonimos TEXT, vetor_fhrr BLOB, is_primario INTEGER)")
        conn.execute("INSERT INTO concepts VALUES ('abrir', 'Tornar aberto', '[]', '[]', X'00', 1)")
        ensure_concept_schema(conn)
        ensure_concept_schema(conn)
        assert conn.execute("SELECT definicao, status_habilidade FROM concepts").fetchone() == ("Tornar aberto", 0)


@pytest.mark.parametrize("feedbacks,expected", [
    ([{"lambda_obs": 1, "ncd_real": .21}], 2),
    ([{"lambda_obs": 1, "ncd_real": .20}], 1),
    ([{"lambda_obs": 0, "ncd_real": .99}], 1),
    ([{"lambda_obs": 1, "ncd_real": None}], 1),
    ([{"lambda_obs": 1, "ncd_real": .99}, {"lambda_obs": 0, "ncd_real": .01}], 1),
])
def test_only_successful_visual_route_validates(semantic_bridge, feedbacks, expected):
    graph = save_concept(semantic_bridge)
    pdag = semantic_bridge._kernel.pdag
    assert graph.details()[0]["status"] == 0
    pdag.link_semantic_skill("abrir aplicativo", "trajectory:abrir_app_generico")
    pdag.validate_semantic_skill("trajectory:unrelated", [{"feedback": {"lambda_obs": 1, "ncd_real": .99}}])
    assert graph.details()[0]["status"] == 1
    pdag.validate_semantic_skill("trajectory:abrir_app_generico", [{"feedback": f} for f in feedbacks])
    assert graph.details()[0]["status"] == expected
    pdag.link_semantic_skill("abrir aplicativo", "trajectory:abrir_app_generico")
    assert graph.details()[0]["status"] == expected


def test_gui_professor_preserves_concept_identity_and_teaches_only_on_finish(semantic_bridge):
    graph = save_concept(semantic_bridge)
    result = semantic_bridge.teach_semantic_concept("abrir aplicativo")
    assert result["ok"] and graph.details()[0]["status"] == 0
    assert semantic_bridge.teach_semantic_concept("abrir aplicativo")["ok"] is False
    send(semantic_bridge, "teste_teclado")
    session = semantic_bridge._professor_mode
    session["passos_executados"].append({"acao": "HOTKEY", "keys": ["esc"], "feedback": {"lambda_obs": 1, "ncd_real": .99}})
    assert "salvo" in send(semantic_bridge, "/fim")["reply"]
    assert graph.details()[0]["status"] == 1
    assert semantic_bridge._professor_mode is None
    semantic_bridge._tom.evaluate_intent.assert_not_called()
