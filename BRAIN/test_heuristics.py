"""Synthetic fixtures only; compiling/loading must never actuate the desktop."""
import asyncio
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from extract_heuristics import compilar_tudo
from skill_loader import DynamicSkillLoader


CALC = [{"acao": "HOTKEY", "keys": ["win"]}, {"acao": "TYPE", "text": "calc"}, {"acao": "HOTKEY", "keys": ["enter"]}]


def database(tmp_path, count=10, failures=0, source="observed", app="calc", intent="abrir_app", pipelines=None):
    db = tmp_path / "transitions.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE transitions(id INTEGER PRIMARY KEY, app_name TEXT, intent_base TEXT, pipeline_spec TEXT, lambda_obs INTEGER, ncd REAL, source TEXT)")
        for i in range(count):
            steps = pipelines[i] if pipelines else CALC
            conn.execute("INSERT INTO transitions VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (i, app, intent, json.dumps({"passos": steps}), int(i >= failures), .3, source))
    return db


def test_ten_observed_calc_routes_generate_loadable_static_skill(tmp_path):
    db = database(tmp_path)
    directory = tmp_path / "HABILIDADES"
    result = compilar_tudo(db, directory)
    assert result["sucessos"] == 1
    path = directory / "auto_macro_calc_abrir_app.py"
    text = path.read_text(encoding="utf-8")
    assert "@skill(" in text and "effector.send_hotkey, ['win']" in text
    assert "effector.send_text, 'calc'" in text and "effector.send_hotkey, ['enter']" in text
    assert "execute_subgoal" in text
    loader = DynamicSkillLoader(directory)
    assert "macro_abrir_app_calc" in loader.registry
    assert compilar_tudo(db, directory)["sucessos"] == 0


@pytest.mark.parametrize("count,failures,source,expected", [(9, 0, "observed", 0), (10, 2, "observed", 0),
                                                           (10, 1, "observed", 0), (10, 0, "synthetic_seed", 0)])
def test_evidence_threshold_and_synthetic_exclusion(tmp_path, count, failures, source, expected):
    assert compilar_tudo(database(tmp_path, count, failures, source), tmp_path / "skills")["sucessos"] == expected


def test_parameterized_whatsapp_and_failed_verification_stops_next_step(tmp_path):
    pipelines = [[{"acao": "HOTKEY", "keys": ["ctrl", "f"]}, {"acao": "TYPE", "text": f"contato {i}"},
                  {"acao": "HOTKEY", "keys": ["enter"]}, {"acao": "TYPE", "text": f"mensagem {i}"},
                  {"acao": "HOTKEY", "keys": ["enter"]}] for i in range(10)]
    result = compilar_tudo(database(tmp_path, app="whatsapp", intent="enviar_mensagem", pipelines=pipelines), tmp_path / "skills")
    assert result["sucessos"] == 1
    loader = DynamicSkillLoader(tmp_path / "skills")
    effector = MagicMock()
    effector.send_hotkey.return_value = True
    async def verify(**kwargs):
        await kwargs["action_fn"]()
        return {"lambda_obs": 0}
    engine = SimpleNamespace(execute_subgoal=verify, _contract_for_action=lambda *args: {})
    outcome = asyncio.run(loader.registry["macro_enviar_mensagem_whatsapp"]("Davi", "oi", effector=effector, trajectory_engine=engine))
    assert outcome["status"] == "FALHA_REALIDADE"
    effector.send_hotkey.assert_called_once_with(["ctrl", "f"])
    effector.send_text.assert_not_called()


def test_legacy_hashes_are_not_reversed_or_invented(tmp_path):
    db = tmp_path / "legacy.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE transitions(id INTEGER, action_hash TEXT)")
    result = compilar_tudo(db, tmp_path / "skills")
    assert result["sucessos"] == 0 and result["avisos"]


def test_command_compiles_then_loads_without_calling_llm(tmp_path):
    from BRAINNET import BrainnetBridge
    bridge = object.__new__(BrainnetBridge)
    loader = DynamicSkillLoader(tmp_path / "skills")
    bridge._kernel = SimpleNamespace(skill_loader=loader, pdag=SimpleNamespace(db_path=database(tmp_path)))
    with patch("BRAINNET.urllib.request.urlopen", side_effect=AssertionError("LLM proibido")):
        result = bridge._executar_comando_interno("/compilar_heuristicas", "/compilar_heuristicas", "/compilar_heuristicas")
    assert "1 novas skills" in result["reply"]
    assert "macro_abrir_app_calc" in loader.registry
