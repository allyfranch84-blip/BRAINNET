import json
import sqlite3

import numpy as np
import pytest

from test_semantic_concepts import semantic_bridge, send


def teach(bridge, text):
    vsa, pdag = bridge._kernel.vsa, bridge._kernel.pdag
    vector = vsa.generate_vector(text)
    assert pdag.record_user_confirmed_route("trajectory:teste", "teste",
        {"passos": [{"acao": "TYPE", "text": text}]}, vector, vsa)
    return vector


def test_revert_command_restores_v1_as_active_v3(semantic_bridge):
    pdag = semantic_bridge._kernel.pdag
    original = teach(semantic_bridge, "v1")
    teach(semantic_bridge, "v2")
    with sqlite3.connect(pdag.db_path) as conn:
        archived = conn.execute("SELECT snapshot_json FROM habits_history WHERE version = 1").fetchone()
        assert json.loads(json.loads(archived[0])["pipeline_spec"])["passos"][0]["text"] == "v1"
        assert conn.execute("SELECT version FROM pdag_nodes").fetchone()[0] == 2
    assert "versão 3" in send(semantic_bridge, "/reverter teste")["reply"]
    restored = pdag.find_myelinated_path("trajectory:teste", exact_only=True)
    assert restored["passos"][0]["text"] == "v1"
    np.testing.assert_array_equal(pdag.get_node_phases("trajectory:teste"), original)
    with sqlite3.connect(pdag.db_path) as conn:
        assert conn.execute("SELECT version, is_active FROM pdag_nodes").fetchone() == (3, 1)
    versions = send(semantic_bridge, "/versoes teste")["reply"]
    assert all(f"v{i}" in versions for i in (1, 2, 3))
    assert "UTC" in versions


def test_deactivated_routes_block_exact_and_similarity_and_restart(semantic_bridge):
    pdag = semantic_bridge._kernel.pdag
    teach(semantic_bridge, "v1")
    assert "desativada" in send(semantic_bridge, "/desativar teste")["reply"]
    assert pdag.find_myelinated_path("trajectory:teste", semantic_bridge._kernel.vsa) is None
    assert pdag.is_verified_demonstration("teste") is False
    assert pdag.find_taught_path("trajectory:teste") is None
    assert pdag.get_node_phases("trajectory:teste") is None
    from pdag_engine import MyelinatedPDAGEngine
    reloaded = MyelinatedPDAGEngine(pdag.db_path, dim=64, max_nodes=4)
    try:
        assert not reloaded.is_active[reloaded.id_to_index["trajectory:teste"]]
        assert reloaded.find_myelinated_path("trajectory:teste") is None
    finally:
        reloaded.close()


def test_revert_without_history_does_not_mutate_route(semantic_bridge):
    pdag = semantic_bridge._kernel.pdag
    teach(semantic_bridge, "v1")
    assert "não possui versão anterior" in send(semantic_bridge, "/reverter teste")["reply"]
    assert pdag.route_versions("teste")[0]["version"] == 1
    assert pdag.find_myelinated_path("trajectory:teste")["passos"][0]["text"] == "v1"


def test_reteaching_reactivates_and_versions_disabled_route(semantic_bridge):
    pdag = semantic_bridge._kernel.pdag
    teach(semantic_bridge, "v1")
    pdag.deactivate_route("teste")
    teach(semantic_bridge, "v2")
    assert pdag.route_versions("teste")[-1]["version"] == 2
    assert pdag.find_myelinated_path("trajectory:teste")["passos"][0]["text"] == "v2"
