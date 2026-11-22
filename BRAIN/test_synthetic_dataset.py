"""Synthetic labels never count as observed OS transitions or reinforce habits."""
from copy import deepcopy
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from dataset_io import APPS,ACTIONS,read_dataset,write_dataset,import_dataset
from local_distiller import distill
from pdag_engine import MyelinatedPDAGEngine
from seed_generator import generate_seed
from telemetry_status import world_model_status
from test_professor_mode import bridge,send


def test_5000_unique_logical_seed_examples():
    rows = generate_seed()
    assert len(rows) == len({row["id"] for row in rows}) == 5000
    assert {row["app"] for row in rows} == set(APPS)
    assert {row["action"] for row in rows} == set(ACTIONS)
    assert all(not (row["app"] == "calc" and row["action"] == "pesquisar") for row in rows)
    assert all(row["source"] == "synthetic_seed" for row in rows)
    assert all("lambda_obs" not in step for row in rows for step in row["pipeline"]["passos"])


def test_distillation_preserves_labels_and_resumes(tmp_path):
    seed, final = tmp_path/"seed.json",tmp_path/"final.json"
    seeds = generate_seed(4)
    write_dataset(seed,seeds)
    with patch("local_distiller.paraphrase",side_effect=lambda command,*args:["Agora, "+command]) as model:
        result = distill(seed,final,limit=2)
    assert result == {"total":6,"paraphrases":2,"errors":0}
    assert model.call_count == 2
    parents = {row["id"]:row for row in seeds}
    for row in read_dataset(final):
        if row["source"] == "synthetic_paraphrase":
            assert row["pipeline"] == parents[row["parent_id"]]["pipeline"]
            assert row["semantic_validation"] == "lexical_only"
    with patch("local_distiller.paraphrase") as model:
        assert distill(seed,final,limit=2)["total"] == 6
    model.assert_not_called()


def test_wrong_app_paraphrase_rejected(tmp_path):
    seed, final = tmp_path/"seed.json",tmp_path/"final.json"
    write_dataset(seed,generate_seed(1))
    with patch("local_distiller.paraphrase",return_value=["abra whatsapp"]):
        assert distill(seed,final)["paraphrases"] == 0


def test_offline_model_does_not_loop_over_thousands_of_calls(tmp_path):
    seed, final = tmp_path/"seed.json",tmp_path/"final.json"
    write_dataset(seed,generate_seed(20))
    with patch("local_distiller.paraphrase",side_effect=ConnectionError("offline")) as model:
        result = distill(seed,final)
    assert result == {"total":20,"paraphrases":0,"errors":5}
    assert model.call_count == 5
    assert len(read_dataset(final)) == 20


def test_synthetic_import_idempotent_and_real_count_unchanged(tmp_path):
    path = str(tmp_path/"dataset.db")
    pdag = MyelinatedPDAGEngine(path,dim=8,max_nodes=4)
    dataset = tmp_path/"final.json"
    write_dataset(dataset,generate_seed(30))
    try:
        pdag.record_transition("before","click","after",1,.4,"app.exe")
        assert pdag.flush_pending_writes(5)
        assert import_dataset(dataset,path) == {"inserted":30,"duplicates":0,"total":30}
        assert import_dataset(dataset,path) == {"inserted":0,"duplicates":30,"total":30}
        status = world_model_status(SimpleNamespace(pdag=pdag,world_model_status_path=tmp_path/"none.json"))
        assert status["transitions"] == 1
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM transitions").fetchone()[0] == 31
            assert conn.execute("SELECT DISTINCT lambda_obs,ncd,state_after_hash FROM transitions WHERE source != 'observed'").fetchall() == [(-1,-1.0,"UNOBSERVED")]
            command,spec = conn.execute("SELECT command_text,pipeline_spec FROM transitions WHERE source != 'observed' LIMIT 1").fetchone()
            assert command and json.loads(spec)["provenance"]["observed"] is False
            assert conn.execute("SELECT COUNT(*) FROM pdag_nodes").fetchone()[0] == 0
        pdag.record_transition("second","scroll","third",1,.1,"app.exe")
        assert pdag.flush_pending_writes(5)
        assert world_model_status(SimpleNamespace(pdag=pdag,world_model_status_path=tmp_path/"none.json"))["transitions"] == 2
    finally:
        pdag.close()


def test_invalid_row_does_not_partially_import(tmp_path):
    pdag = MyelinatedPDAGEngine(str(tmp_path/"invalid.db"),dim=8,max_nodes=4)
    path = tmp_path/"final.json"
    rows = generate_seed(2)
    rows[1]["pipeline"]["passos"][0]["acao"] = "EXEC_SHELL"
    write_dataset(path,rows)
    try:
        with pytest.raises(ValueError):
            import_dataset(path,pdag.db_path)
        with sqlite3.connect(pdag.db_path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM transitions").fetchone()[0] == 0
    finally:
        pdag.close()


def test_dataset_command_requires_leaving_professor_and_never_uses_llm(bridge):
    bridge._professor_mode = {"conceito":"pending","passos":[]}
    with patch("dataset_io.import_dataset",return_value={"inserted":10000,"duplicates":0}) as importer:
        result = send(bridge,"/importar_dataset")
        assert "Ensino ativo" in result["reply"]
        importer.assert_not_called()
        send(bridge,"/cancelar")
        result = send(bridge,"/importar_dataset")
    assert "10000 exemplos sintéticos" in result["reply"]
    assert importer.call_args.args[0].name == "dataset_final.json"
    bridge._tom.evaluate_intent.assert_not_called()
    bridge._kernel.trajectory_engine.execute_professor_step.assert_not_awaited()
