# ==============================================================================
# BRAINNET v7 - MEMÓRIA HÍBRIDA MULTI-DIMENSIONAL (H-MEM)
# Árvore Temporal (Ano->Mês->Dia->Ação) + Árvore Semântica FHRR 10.000D.
# ==============================================================================

from __future__ import annotations

import datetime
from collections import OrderedDict
import json
from pathlib import Path
import sqlite3
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

BRAIN_DIR = Path(__file__).resolve().parent
if str(BRAIN_DIR) not in sys.path:
    sys.path.insert(0, str(BRAIN_DIR))

from hyperdimensional import FHRRHyperdimensionalEngine


class HMemEngine:
    """
    [H-MEM]: Impede colapso contextual diferenciando ordem cronológica de escopo semântico.
    Modo 1: Busca Sequencial (Âncora semântica expandida no tempo).
    Modo 2: Busca Intersectiva (Interseção rígida tempo x conceito).
    """

    SCHEMA = """
    PRAGMA journal_mode = WAL;
    PRAGMA synchronous = NORMAL;

    CREATE TABLE IF NOT EXISTS hmem_nodes (
        node_id TEXT PRIMARY KEY,
        timestamp REAL NOT NULL,
        year INTEGER NOT NULL,
        month INTEGER NOT NULL,
        day INTEGER NOT NULL,
        session_id TEXT NOT NULL,
        step_idx INTEGER NOT NULL,
        concept_label TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        context_tuple TEXT NOT NULL,
        access_count INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS hmem_schemas (
        schema_id TEXT PRIMARY KEY,
        concept_label TEXT NOT NULL,
        vector_blob BLOB NOT NULL,
        payload_json TEXT NOT NULL,
        sample_count INTEGER NOT NULL,
        access_count INTEGER DEFAULT 0,
        last_updated REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_hmem_schema_concept ON hmem_schemas (concept_label);

    CREATE INDEX IF NOT EXISTS idx_hmem_time ON hmem_nodes (year, month, day, timestamp);
    CREATE INDEX IF NOT EXISTS idx_hmem_concept ON hmem_nodes (concept_label);
    """

    __slots__ = ("vsa", "db_path", "_conn", "semantic_codebook")

    def __init__(self, vsa_engine: FHRRHyperdimensionalEngine, db_path: str = "hmem_memory.db") -> None:
        self.vsa = vsa_engine
        self.db_path = str(BRAIN_DIR / db_path)
        self.semantic_codebook: OrderedDict[str, np.ndarray] = OrderedDict()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, isolation_level=None)
        self._conn.executescript(self.SCHEMA)
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(hmem_nodes)")}
        if "access_count" not in columns:
            with self._conn:
                self._conn.execute("ALTER TABLE hmem_nodes ADD COLUMN access_count INTEGER DEFAULT 0")

    def record_episodic_node(
        self,
        concept: str,
        payload: Dict[str, Any],
        context_tuple: str,
        session_id: str = "default_session",
        step_idx: int = 1
    ) -> str:
        now = time.time()
        dt = datetime.datetime.fromtimestamp(now)
        node_id = f"HND_{int(now * 1000)}_{step_idx}"

        # Ancoragem Semântica em C^10.000
        if concept not in self.semantic_codebook:
            if len(self.semantic_codebook) >= 1000:
                self.semantic_codebook.popitem(last=False)
            self.semantic_codebook[concept] = self.vsa.generate_vector(concept)
        self.semantic_codebook.move_to_end(concept)

        payload_str = json.dumps(payload, ensure_ascii=False)

        with self._conn:
            self._conn.execute(
                """
                INSERT INTO hmem_nodes 
                (node_id, timestamp, year, month, day, session_id, step_idx, concept_label, payload_json, context_tuple)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (node_id, now, dt.year, dt.month, dt.day, session_id, step_idx, concept, payload_str, context_tuple)
            )

        return node_id

    def get_episodic_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve one stored episode by its exact identifier."""
        if not isinstance(node_id, str) or not node_id or len(node_id) > 128:
            raise ValueError('invalid node id')
        row = self._conn.execute(
            'SELECT node_id, timestamp, session_id, concept_label, payload_json, context_tuple '
            'FROM hmem_nodes WHERE node_id = ?', (node_id,)).fetchone()
        if not row:
            return None
        return {'node_id': row[0], 'timestamp': row[1], 'session_id': row[2],
                'concept': row[3], 'payload': json.loads(row[4]), 'context': row[5]}

    def preserve_episodes_to_schema(self, concept: str, keep_last: int = 3) -> int:
        """Experimental consolidation: stores source IDs and never removes episodes."""
        import uuid
        rows = self._conn.execute(
            'SELECT node_id, payload_json, context_tuple FROM hmem_nodes WHERE concept_label = ? ORDER BY timestamp DESC',
            (concept,)).fetchall()[keep_last:]
        vectors, sources = [], []
        for node_id, payload_json, context in rows:
            try:
                payload = json.loads(payload_json)
                vectors.append(self.vsa.text_to_hypervector(json.dumps(payload, ensure_ascii=False, sort_keys=True)))
                sources.append({'node_id': node_id, 'context': context})
            except (ValueError, TypeError):
                continue
        if not vectors: return 0
        summary = json.dumps({'concept': concept, 'sources': sources, 'strategy': 'preserve-v1'}, ensure_ascii=False)
        self._conn.execute(
            'INSERT INTO hmem_schemas (schema_id, concept_label, vector_blob, payload_json, sample_count, last_updated) VALUES (?, ?, ?, ?, ?, ?)',
            ('SCH_' + uuid.uuid4().hex, concept, self.vsa.bundle(vectors).tobytes(), summary, len(sources), time.time()))
        return len(sources)

    def compress_episodes_to_schema(self, concept: str, keep_last: int = 3) -> int:
        """Funde episódios antigos no 'Conceito Ideal' (FHRR Bundle).
        
        Preserva: is_permanent=1 e os keep_last mais recentes.
        Bundle: vetoriza o CONTEÚDO de cada payload, não o nome do conceito.
        Transação: BEGIN IMMEDIATE explícito (autocommit = isolation_level=None).
        """
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(hmem_nodes)")}
        perm_clause = " AND is_permanent = 0" if "is_permanent" in cols else ""
        cursor = self._conn.execute(
            f"SELECT node_id, payload_json, context_tuple FROM hmem_nodes "
            f"WHERE concept_label = ?{perm_clause} ORDER BY timestamp DESC",
            (concept,)
        )
        rows = cursor.fetchall()
        if len(rows) <= keep_last:
            return 0

        to_compress = rows[keep_last:]
        node_ids = [r[0] for r in to_compress]
        payload_vectors, payload_samples, contexts = [], [], {}
        for _node_id, payload_json, context_tuple in to_compress:
            try:
                payload = json.loads(payload_json)
                text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
                payload_vectors.append(self.vsa.text_to_hypervector(text))
                if len(payload_samples) < 5:
                    payload_samples.append({"context": context_tuple, "payload": payload})
                contexts[context_tuple] = contexts.get(context_tuple, 0) + 1
            except Exception:
                continue
        if not payload_vectors:
            return 0

        v_schema = self.vsa.bundle(payload_vectors)
        schema_id = f"SCH_{int(time.time() * 1000)}_{concept[:20]}"
        summary = {
            "concept": concept,
            "samples": len(to_compress),
            "most_common_context": max(contexts.items(), key=lambda kv: kv[1])[0] if contexts else "unknown",
            "sample_payloads": payload_samples,
        }
        payload_str = json.dumps(summary, ensure_ascii=False)

        try:
            self._conn.execute("BEGIN IMMEDIATE")
            self._conn.execute(
                """INSERT OR REPLACE INTO hmem_schemas
                   (schema_id, concept_label, vector_blob, payload_json, sample_count, last_updated)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (schema_id, concept, v_schema.tobytes(), payload_str, len(to_compress), time.time())
            )
            placeholders = ','.join('?' * len(node_ids))
            self._conn.execute(f"DELETE FROM hmem_nodes WHERE node_id IN ({placeholders})", node_ids)
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        return len(to_compress)

    def query_mode_1_sequential(self, concept_anchor: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Busca Semântica Ancorada seguida de Expansão Temporal."""
        if concept_anchor == "background_observer":
            cursor = self._conn.execute(
                "SELECT node_id, timestamp, concept_label, payload_json, context_tuple "
                "FROM hmem_nodes WHERE context_tuple = ? ORDER BY timestamp DESC, rowid DESC LIMIT ?",
                (concept_anchor, limit),
            )
            results = [{"node_id": r[0], "timestamp": r[1], "concept": r[2],
                        "payload": json.loads(r[3]), "context": r[4]}
                       for r in reversed(cursor.fetchall())]
            if results:
                with self._conn:
                    self._conn.executemany(
                        "UPDATE hmem_nodes SET access_count = access_count + 1 WHERE node_id = ?",
                        [(r["node_id"],) for r in results]
                    )
            return results
        # 1. Busca exata ou parcial (LIKE) primeiro no SQLite
        try:
            with self._conn:
                cursor = self._conn.execute(
                    "SELECT DISTINCT concept_label FROM hmem_nodes WHERE concept_label LIKE ? LIMIT 1",
                    (f"%{concept_anchor}%",)
                )
                row = cursor.fetchone()
                if row:
                    melhor_conceito = row[0]
                else:
                    # Se não achou no nodes, tenta nos schemas
                    cursor = self._conn.execute(
                        "SELECT DISTINCT concept_label FROM hmem_schemas WHERE concept_label LIKE ? LIMIT 1",
                        (f"%{concept_anchor}%",)
                    )
                    row = cursor.fetchone()
                    if row:
                        melhor_conceito = row[0]
                    else:
                        melhor_conceito = concept_anchor
        except Exception:
            melhor_conceito = concept_anchor

        # 2. Fallback: similaridade semântica na RAM (se a busca por texto não achar nada)
        if melhor_conceito == concept_anchor and self.semantic_codebook:
            v_target = self.vsa.generate_vector(concept_anchor)
            maior_sim = -1.0
            for c, v in self.semantic_codebook.items():
                sim = self.vsa.similarity(v_target, v)
                if sim > maior_sim:
                    maior_sim = sim
                    melhor_conceito = c

        cursor = self._conn.execute(
            "SELECT node_id, timestamp, concept_label, payload_json, context_tuple "
            "FROM hmem_nodes WHERE concept_label = ? ORDER BY timestamp DESC LIMIT ?",
            (melhor_conceito, limit)
        )
        rows = cursor.fetchall()

        if not rows:
            cursor = self._conn.execute(
                "SELECT schema_id, last_updated, concept_label, payload_json "
                "FROM hmem_schemas WHERE concept_label LIKE ?",
                (f"%{melhor_conceito}%",)
            )
            schema_rows = cursor.fetchall()
            results = [
                {"node_id": r[0], "timestamp": r[1], "concept": r[2],
                 "payload": json.loads(r[3]), "context": "SCHEMA_IDEAL"}
                for r in schema_rows
            ]
            if results:
                with self._conn:
                    self._conn.executemany(
                        "UPDATE hmem_schemas SET access_count = access_count + 1 WHERE schema_id = ?",
                        [(r["node_id"],) for r in results]
                    )
            return results

        results = [
            {"node_id": r[0], "timestamp": r[1], "concept": r[2],
             "payload": json.loads(r[3]), "context": r[4]}
            for r in rows
        ]
        if results:
            with self._conn:
                self._conn.executemany(
                    "UPDATE hmem_nodes SET access_count = access_count + 1 WHERE node_id = ?",
                    [(r["node_id"],) for r in results]
                )
        return results

    def query_mode_2_intersective(self, concept: str, days_ago: int = 0, limit: int = 5) -> List[Dict[str, Any]]:
        """Interseção Rígida: Filtra simultaneamente tempo exato e conceito."""
        dt_target = datetime.datetime.now() - datetime.timedelta(days=days_ago)

        cursor = self._conn.execute(
            """
            SELECT node_id, timestamp, concept_label, payload_json, context_tuple
            FROM hmem_nodes
            WHERE year = ? AND month = ? AND day = ? AND concept_label LIKE ?
            ORDER BY timestamp ASC LIMIT ?
            """,
            (dt_target.year, dt_target.month, dt_target.day, f"%{concept}%", limit)
        )
        rows = cursor.fetchall()
        results = [
            {"node_id": r[0], "timestamp": r[1], "concept": r[2], "payload": json.loads(r[3]), "context": r[4]}
            for r in rows
        ]

        # Atualiza o access_count para memórias acessadas
        if results:
            with self._conn:
                self._conn.executemany(
                    "UPDATE hmem_nodes SET access_count = access_count + 1 WHERE node_id = ?",
                    [(r["node_id"],) for r in results]
                )

        return results
