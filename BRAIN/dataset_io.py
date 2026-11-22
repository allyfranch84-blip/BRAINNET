"""Offline action labels and explicitly unobserved synthetic transition imports."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time

APPS = ("brave", "whatsapp", "notepad", "code", "calc")
ACTIONS = ("abrir", "digitar", "pesquisar", "enter", "fechar")


def example_id(command, pipeline):
    payload = json.dumps([" ".join(command.casefold().split()), pipeline], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def validate_example(row):
    if not isinstance(row, dict) or row.get("app") not in APPS or row.get("action") not in ACTIONS:
        raise ValueError("Aplicativo/acao fora do catalogo")
    if row.get("source") not in ("synthetic_seed", "synthetic_paraphrase"):
        raise ValueError("Dataset deve identificar origem sintetica")
    command, pipeline = row.get("command"), row.get("pipeline")
    if not isinstance(command, str) or not 1 <= len(command) <= 4096 or not isinstance(pipeline, dict):
        raise ValueError("Comando/pipeline invalido")
    steps = pipeline.get("passos")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 8:
        raise ValueError("Pipeline deve conter de 1 a 8 passos")
    for number, step in enumerate(steps, 1):
        if not isinstance(step, dict) or step.get("passo") != number:
            raise ValueError("Passos fora de ordem")
        action = step.get("acao")
        if action in ("ENSURE_APP", "FOCUS_WINDOW"):
            valid = set(step) == {"passo", "acao", "app"} and step["app"] == row["app"]
        elif action == "TYPE":
            valid = set(step) == {"passo", "acao", "text"} and isinstance(step["text"],str) and 0 < len(step["text"]) <= 3000
        elif action == "HOTKEY":
            valid = set(step) == {"passo", "acao", "keys"} and step["keys"] in (["ctrl","f"],["ctrl","l"],["enter"],["alt","f4"])
        else:
            valid = False
        if not valid:
            raise ValueError("Passo fora do schema de acoes sinteticas")
    if row.get("id") != example_id(command, pipeline):
        raise ValueError("ID nao corresponde ao comando/pipeline")
    return row


def read_dataset(path):
    path = Path(path)
    if path.stat().st_size > 64*1024*1024:
        raise ValueError("Dataset excede 64 MiB")
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows,list) or len(rows) > 100000:
        raise ValueError("Dataset deve ser lista com ate 100000 exemplos")
    for row in rows:
        validate_example(row)
    return rows


def write_dataset(path, rows):
    path = Path(path).resolve()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",dir=path.parent,delete=False,suffix=".tmp") as handle:
            temporary = Path(handle.name)
            json.dump(rows,handle,ensure_ascii=False,indent=2)
        os.replace(temporary,path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def import_dataset(path, db_path):
    rows = read_dataset(path)  # Validate everything before changing the database.
    inserted = 0
    with sqlite3.connect(db_path,timeout=10) as conn:
        conn.execute("BEGIN IMMEDIATE")
        columns = {row[1] for row in conn.execute("PRAGMA table_info(transitions)")}
        if not columns:
            raise ValueError("Tabela transitions ausente; inicialize o kernel")
        for name, sql_type in (("source","TEXT NOT NULL DEFAULT 'observed'"),("command_text","TEXT"),
                               ("pipeline_spec","TEXT"),("dataset_id","TEXT")):
            if name not in columns:
                conn.execute(f"ALTER TABLE transitions ADD COLUMN {name} {sql_type}")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_trans_dataset ON transitions(dataset_id) WHERE dataset_id IS NOT NULL")
        for row in rows:
            payload = dict(row["pipeline"], provenance={"source":row["source"], "id":row["id"], "observed":False})
            cursor = conn.execute("""INSERT OR IGNORE INTO transitions
                (state_before_hash, action_hash, state_after_hash, lambda_obs, ncd, app_name, timestamp,
                 source, command_text, pipeline_spec, dataset_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("UNOBSERVED", row["id"][:16], "UNOBSERVED", -1, -1.0, row["app"], time.time(),
                 row["source"], row["command"], json.dumps(payload,ensure_ascii=False), row["id"]))
            inserted += cursor.rowcount
    return {"inserted":inserted,"duplicates":len(rows)-inserted,"total":len(rows)}
