# ==============================================================================
# BRAINNET v7 - SISTEMA OPERACIONAL COGNITIVO
# MODULO: pdag_engine.py
# FUNCAO: Grafo Causal com Memoria Sinaptica Hibrida (RAM <-> SQLite WAL).
#         Plasticidade Hebbiana log-regularizada, Mielinizacao e Ebbinghaus.
# Tag: [BN_PDAG_ENGINE]
# ==============================================================================

from __future__ import annotations

from contextlib import closing, contextmanager
import hashlib
import json
import logging
import os
import queue
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("BRAINNET_PDAG")

class MyelinatedPDAGEngine:
    """
    Motor de Grafo Sinaptico Hibrido.
    - Autoridade de leitura e decisao: RAM contigua (Numpy AVX2).
    - Persistencia eventual: SQLite WAL (Write-Behind via queue.Queue).
    """

    def __init__(self, db_path: str = "core1_pdag.db", max_nodes: int = 5000, dim: int = 10_000) -> None:
        self.db_path = os.path.abspath(db_path)
        self.max_nodes = max_nodes
        self.dim = dim

        # --- CACHE RAM CONTIGUO ---
        self.phase_matrix: np.ndarray = np.zeros((max_nodes, dim), dtype=np.complex64)
        self.weights: np.ndarray = np.zeros(max_nodes, dtype=np.float32)
        self.alpha: np.ndarray = np.full(max_nodes, 0.5, dtype=np.float64)
        self.beta: np.ndarray = np.full(max_nodes, 0.5, dtype=np.float64)
        self._rng = np.random.default_rng()
        self.consecutive_successes: np.ndarray = np.zeros(max_nodes, dtype=np.int32)
        self.is_myelinated: np.ndarray = np.zeros(max_nodes, dtype=bool)
        self.teacher_verified: np.ndarray = np.zeros(max_nodes, dtype=bool)
        self.is_permanent: np.ndarray = np.zeros(max_nodes, dtype=bool) # STC Tag
        self.is_active: np.ndarray = np.ones(max_nodes, dtype=bool)
        self.last_active: np.ndarray = np.zeros(max_nodes, dtype=np.float64)
        
        self.node_ids: List[str] = []
        self.id_to_index: Dict[str, int] = {}
        self.active_count: int = 0

        # --- ESTRUTURAS DE PERSISTENCIA ---
        self._db_queue: queue.Queue = queue.Queue()
        self._db_thread: Optional[threading.Thread] = None
        self._running: bool = True
        self._lock = threading.Lock()

        self._init_db()
        self._load_from_db()
        self._start_db_writer()

    def _init_db(self) -> None:
        with closing(sqlite3.connect(self.db_path, check_same_thread=False, isolation_level=None)) as conn, conn:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            conn.execute("PRAGMA cache_size = -64000;")
            conn.execute("PRAGMA mmap_size = 2147483648;")
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pdag_nodes (
                    context_key TEXT PRIMARY KEY,
                    intent TEXT NOT NULL,
                    pipeline_spec TEXT NOT NULL,
                    phase_blob BLOB NOT NULL,
                    weight REAL NOT NULL DEFAULT 1.0,
                    alpha REAL NOT NULL DEFAULT 0.5,
                    beta REAL NOT NULL DEFAULT 0.5,
                    consecutive_successes INTEGER NOT NULL DEFAULT 0,
                    is_myelinated INTEGER NOT NULL DEFAULT 0,
                    teacher_verified INTEGER NOT NULL DEFAULT 0,
                    is_permanent INTEGER NOT NULL DEFAULT 0,
                    last_active REAL NOT NULL,
                    created_at REAL NOT NULL
                );
            """)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(pdag_nodes)")}
            for field, kind in (("qualia_formal", "TEXT"), ("qualia_telic", "TEXT"),
                                ("qualia_agentive", "TEXT"), ("qualia_vector", "BLOB"),
                                ("is_permanent", "INTEGER NOT NULL DEFAULT 0")):
                if field not in columns:
                    conn.execute(f"ALTER TABLE pdag_nodes ADD COLUMN {field} {kind}")
            with conn:
                if "alpha" not in columns:
                    conn.execute("ALTER TABLE pdag_nodes ADD COLUMN alpha REAL NOT NULL DEFAULT 0.5")
                    conn.execute("UPDATE pdag_nodes SET alpha = 0.5 + MAX(consecutive_successes, 0)")
                if "beta" not in columns:
                    conn.execute("ALTER TABLE pdag_nodes ADD COLUMN beta REAL NOT NULL DEFAULT 0.5")
                if "teacher_verified" not in columns:
                    conn.execute("ALTER TABLE pdag_nodes ADD COLUMN teacher_verified INTEGER NOT NULL DEFAULT 0")
                conn.execute("""UPDATE pdag_nodes SET is_myelinated = 0
                    WHERE teacher_verified = 0 AND (alpha / (alpha + beta) < 0.85
                    OR alpha * beta / ((alpha + beta) * (alpha + beta) * (alpha + beta + 1)) > 0.02)""")
            for field in ("version", "is_active"):
                if field not in {row[1] for row in conn.execute("PRAGMA table_info(pdag_nodes)")}:
                    conn.execute(f"ALTER TABLE pdag_nodes ADD COLUMN {field} INTEGER NOT NULL DEFAULT 1")
            conn.execute("""CREATE TABLE IF NOT EXISTS habits_history (
                context_key TEXT NOT NULL, version INTEGER NOT NULL, snapshot_json TEXT NOT NULL,
                created_at REAL NOT NULL, archived_at REAL NOT NULL, PRIMARY KEY(context_key, version))""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pdag_myelin ON pdag_nodes (is_myelinated, weight DESC);")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    event_type TEXT NOT NULL,
                    x INTEGER,
                    y INTEGER,
                    hwnd INTEGER,
                    process_name TEXT,
                    window_title TEXT
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS causal_blackbox (
                    snapshot_id TEXT PRIMARY KEY,
                    context_key TEXT NOT NULL,
                    failure_reason TEXT NOT NULL,
                    lambda_obs INTEGER NOT NULL,
                    timestamp REAL NOT NULL
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS transitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    state_before_hash TEXT NOT NULL,
                    action_hash TEXT NOT NULL,
                    state_after_hash TEXT NOT NULL,
                    lambda_obs INTEGER NOT NULL,
                    ncd REAL NOT NULL,
                    app_name TEXT NOT NULL,
                    timestamp REAL NOT NULL
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trans_app ON transitions(app_name, timestamp)")
            transition_columns = {row[1] for row in conn.execute("PRAGMA table_info(transitions)")}
            for field, kind in {
                "execution_id": "TEXT", "intent": "TEXT", "steps_json": "TEXT",
                "expected_delta": "REAL", "actual_delta": "REAL", "window_title": "TEXT",
                "trajectory_id": "TEXT", "step_index": "INTEGER", "step_count": "INTEGER",
                "source": "TEXT NOT NULL DEFAULT 'observed'", "elapsed_ms": "REAL",
            }.items():
                if field not in transition_columns:
                    conn.execute(f"ALTER TABLE transitions ADD COLUMN {field} {kind}")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trans_execution ON transitions(execution_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trans_trajectory ON transitions(trajectory_id, step_index)")
            from semantic_concepts import ensure_concept_schema
            ensure_concept_schema(conn)
            from field_tests import FIELD_TEST_SCHEMA
            conn.execute(FIELD_TEST_SCHEMA)

    def _load_from_db(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM pdag_nodes ORDER BY last_active DESC LIMIT ?", (self.max_nodes,))
            rows = cursor.fetchall()

            now = time.time()
            for row in rows:
                if self.active_count >= self.max_nodes:
                    break
                
                key = row["context_key"]
                idx = self.active_count
                
                self.node_ids.append(key)
                self.id_to_index[key] = idx
                
                phase = np.frombuffer(row["phase_blob"], dtype=np.complex64)
                if len(phase) == self.dim:
                    self.phase_matrix[idx] = phase
                else:
                    self.phase_matrix[idx] = np.zeros(self.dim, dtype=np.complex64)
                    
                self.weights[idx] = float(row["weight"])
                self.alpha[idx] = float(row["alpha"])
                self.beta[idx] = float(row["beta"])
                self.consecutive_successes[idx] = int(row["consecutive_successes"])
                self.is_myelinated[idx] = bool(row["is_myelinated"])
                self.teacher_verified[idx] = bool(row["teacher_verified"])
                self.is_permanent[idx] = bool(row["is_permanent"]) if "is_permanent" in row.keys() else False
                self.is_active[idx] = bool(row["is_active"])
                self.last_active[idx] = float(row["last_active"])
                
                self.active_count += 1

    @staticmethod
    def _archive_route(conn, key):
        cursor = conn.execute("SELECT * FROM pdag_nodes WHERE context_key = ?", (key,))
        row = cursor.fetchone()
        if row is None:
            return
        snapshot = dict(zip((column[0] for column in cursor.description), row))
        encoded = {k: {"bytes_hex": v.hex()} if isinstance(v, bytes) else v for k, v in snapshot.items()}
        conn.execute("INSERT INTO habits_history VALUES (?, ?, ?, ?, ?)",
                     (key, snapshot["version"], json.dumps(encoded), snapshot["created_at"], time.time()))

    def _route_key(self, conn, intent):
        value = str(intent).strip().casefold()
        key = value if value.startswith(("trajectory:", "qualia:")) else f"trajectory:{value}"
        if conn.execute("SELECT 1 FROM pdag_nodes WHERE context_key = ?", (key,)).fetchone():
            return key
        rows = conn.execute("SELECT context_key FROM pdag_nodes WHERE lower(context_key) = ? OR lower(intent) = ?", (key, value)).fetchall()
        if len(rows) != 1:
            raise ValueError("Rota não encontrada ou intenção ambígua. Informe a chave exata.")
        return rows[0][0]

    def route_versions(self, intent):
        with self._lock:
            if not self.flush_pending_writes(5.0):
                raise TimeoutError("Escritas de rotas pendentes")
            with closing(sqlite3.connect(self.db_path, timeout=5)) as conn, conn:
                key = self._route_key(conn, intent)
                rows = conn.execute("SELECT version, created_at, 0 FROM habits_history WHERE context_key = ?", (key,)).fetchall()
                rows += conn.execute("SELECT version, created_at, is_active FROM pdag_nodes WHERE context_key = ?", (key,)).fetchall()
                return [{"version": r[0], "created_at": r[1], "is_active": bool(r[2])} for r in sorted(rows)]

    def deactivate_route(self, intent):
        with self._lock:
            if not self.flush_pending_writes(5.0):
                raise TimeoutError("Escritas de rotas pendentes")
            with closing(sqlite3.connect(self.db_path, timeout=5)) as conn, conn:
                key = self._route_key(conn, intent)
                conn.execute("UPDATE pdag_nodes SET is_active = 0 WHERE context_key = ?", (key,))
            idx = self.id_to_index.get(key)
            if idx is not None:
                self.is_active[idx] = False
            return key

    def revert_route(self, intent):
        with self._lock:
            if not self.flush_pending_writes(5.0):
                raise TimeoutError("Escritas de rotas pendentes")
            with closing(sqlite3.connect(self.db_path, timeout=5)) as conn, conn:
                conn.execute("BEGIN IMMEDIATE")
                key = self._route_key(conn, intent)
                version = conn.execute("SELECT version FROM pdag_nodes WHERE context_key = ?", (key,)).fetchone()[0]
                previous = conn.execute("SELECT snapshot_json FROM habits_history WHERE context_key = ? AND version < ? ORDER BY version DESC LIMIT 1", (key, version)).fetchone()
                if previous is None:
                    raise ValueError("A rota não possui versão anterior.")
                snapshot = {k: bytes.fromhex(v["bytes_hex"]) if isinstance(v, dict) and "bytes_hex" in v else v
                            for k, v in json.loads(previous[0]).items()}
                self._archive_route(conn, key)
                snapshot.update(version=version + 1, is_active=1, created_at=time.time(), last_active=time.time())
                columns = [r[1] for r in conn.execute("PRAGMA table_info(pdag_nodes)") if r[1] != "context_key"]
                conn.execute("UPDATE pdag_nodes SET " + ", ".join(f"{column} = ?" for column in columns) + " WHERE context_key = ?",
                             tuple(snapshot[column] for column in columns) + (key,))
                conn.execute("UPDATE concepts SET status_habilidade = 1 WHERE id IN (SELECT concept_id FROM concept_skill_routes WHERE route_key = ?)", (key,))
            idx = self._get_or_create_node(key, snapshot["intent"])
            self.phase_matrix[idx] = np.frombuffer(snapshot["phase_blob"], dtype=np.complex64)
            for field in ("alpha", "beta", "consecutive_successes", "is_myelinated", "teacher_verified", "is_active", "last_active"):
                getattr(self, field)[idx] = snapshot[field]
            self.weights[idx] = snapshot["weight"]
            return version + 1

    def _start_db_writer(self) -> None:
        def worker():
            conn = sqlite3.connect(self.db_path, check_same_thread=False, isolation_level="DEFERRED")
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            
            while self._running or not self._db_queue.empty():
                try:
                    batch = []
                    try:
                        item = self._db_queue.get(timeout=0.1)
                        batch.append(item)
                    except queue.Empty:
                        continue

                    while len(batch) < 100:
                        try:
                            batch.append(self._db_queue.get_nowait())
                        except queue.Empty:
                            break

                    with conn:
                        conn.execute("BEGIN IMMEDIATE")
                        for i in batch:
                            if i["op"] == "upsert":
                                revision = bool(i.get("revision"))
                                if revision:
                                    self._archive_route(conn, i["key"])
                                conn.execute("""
                                    INSERT INTO pdag_nodes 
                                    (context_key, intent, pipeline_spec, phase_blob, weight, consecutive_successes, is_myelinated, is_permanent, last_active, created_at, alpha, beta, teacher_verified)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    ON CONFLICT(context_key) DO UPDATE SET
                                    pipeline_spec = excluded.pipeline_spec,
                                    phase_blob = excluded.phase_blob,
                                    weight = excluded.weight,
                                    alpha = excluded.alpha,
                                    beta = excluded.beta,
                                    teacher_verified = excluded.teacher_verified,
                                    consecutive_successes = excluded.consecutive_successes,
                                    is_myelinated = excluded.is_myelinated,
                                    is_permanent = excluded.is_permanent,
                                    last_active = excluded.last_active
                                """, (
                                    i["key"], i["intent"], i["spec"], i["phase"], 
                                    float(i["weight"]), int(i["successes"]), int(i["myelin"]), int(i.get("is_permanent", False)),
                                    float(i["time"]), float(i["time"]), float(i["alpha"]), float(i["beta"]), int(i.get("teacher_verified", False))
                                ))
                                if revision:
                                    conn.execute("""UPDATE pdag_nodes SET version = COALESCE(
                                        (SELECT MAX(version) + 1 FROM habits_history WHERE context_key = ?), 1),
                                        is_active = 1, created_at = ? WHERE context_key = ?""",
                                        (i["key"], i["time"], i["key"]))
                                    conn.execute("UPDATE concepts SET status_habilidade = 1 WHERE id IN (SELECT concept_id FROM concept_skill_routes WHERE route_key = ?)", (i["key"],))
                            elif i["op"] == "qualia":
                                conn.execute("""UPDATE pdag_nodes SET qualia_formal = ?, qualia_telic = ?,
                                    qualia_agentive = ?, qualia_vector = ? WHERE context_key = ?""",
                                    ("MACRO_ACTION", i["telic"], i["agentive"], i["vector"], i["key"]))
                            elif i["op"] == "transition":
                                conn.execute("""
                                    INSERT INTO transitions
                                    (state_before_hash, action_hash, state_after_hash, lambda_obs, ncd, app_name, timestamp,
                                     execution_id, intent, steps_json, expected_delta, actual_delta, window_title,
                                     trajectory_id, step_index, step_count, elapsed_ms)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, (i["state_before_hash"], i["action_hash"], i["state_after_hash"],
                                      i["lambda_obs"], i["ncd"], i["app_name"], i["timestamp"],
                                      i.get("execution_id"), i.get("intent"), i.get("steps_json"),
                                      i.get("expected_delta"), i.get("actual_delta"), i.get("window_title"),
                                      i.get("trajectory_id"), i.get("step_index"), i.get("step_count"), i.get("elapsed_ms")))
                            elif i["op"] == "delete":
                                conn.execute("DELETE FROM pdag_nodes WHERE context_key = ?", (i["key"],))
                            elif i["op"] == "blackbox":
                                conn.execute("""
                                    INSERT INTO causal_blackbox 
                                    (snapshot_id, context_key, failure_reason, lambda_obs, timestamp)
                                    VALUES (?, ?, ?, ?, ?)
                                """, (i["snapshot_id"], i["key"], i["reason"], i["lambda"], i["time"]))
                    
                    for _ in batch:
                        self._db_queue.task_done()
                        
                except Exception as e:
                    logger.error(f"[PDAG_DB_WRITER] Erro: {e}")
            conn.close()

        self._db_thread = threading.Thread(target=worker, daemon=True)
        self._db_thread.start()

    def record_transition(self, state_before_hash: str, action_hash: str, state_after_hash: str,
                          lambda_obs: int, ncd: Optional[float], app_name: str, *, execution_id=None,
                          intent=None, steps_json=None, expected_delta=None, window_title=None,
                          trajectory_id=None, step_index=None, step_count=None, elapsed_ms=None) -> None:
        self._db_queue.put({
            "op": "transition", "state_before_hash": state_before_hash,
            "action_hash": action_hash, "state_after_hash": state_after_hash,
            "lambda_obs": int(lambda_obs), "ncd": float(ncd) if ncd is not None else -1.0,
            "app_name": app_name, "timestamp": time.time(),
            "execution_id": execution_id, "intent": intent, "steps_json": steps_json,
            "expected_delta": expected_delta, "actual_delta": ncd, "window_title": window_title,
            "trajectory_id": trajectory_id, "step_index": step_index, "step_count": step_count,
            "elapsed_ms": elapsed_ms,
        })

    def hash_context(self, context_str: str) -> str:
        return hashlib.blake2b(context_str.encode("utf-8"), digest_size=16).hexdigest()

    def _get_or_create_node(self, context_key: str, intent: str, vsa_engine: Any = None) -> int:
        idx = self.id_to_index.get(context_key)
        if idx is not None:
            return idx

        if self.active_count >= self.max_nodes:
            # Eviction policy simples: menor last_active
            min_idx = int(np.argmin(self.last_active))
            old_key = self.node_ids[min_idx]
            del self.id_to_index[old_key]
            
            idx = min_idx
            self.node_ids[idx] = context_key
            self.id_to_index[context_key] = idx
        else:
            idx = self.active_count
            self.node_ids.append(context_key)
            self.id_to_index[context_key] = idx
            self.active_count += 1

        # Geracao de fase inicial
        if vsa_engine is not None:
            try:
                v = vsa_engine.text_to_hypervector(context_key)
            except Exception:
                v = np.zeros(self.dim, dtype=np.complex64)
        else:
            # Fallback deterministico
            seed = int.from_bytes(hashlib.sha256(context_key.encode()).digest()[:8], "little")
            rng = np.random.default_rng(seed)
            phases = rng.uniform(-np.pi, np.pi, self.dim).astype(np.float32)
            v = np.exp(1j * phases).astype(np.complex64)
            
        self.phase_matrix[idx] = v
        self.weights[idx] = 1.0
        self.alpha[idx] = 0.5
        self.beta[idx] = 0.5
        self.consecutive_successes[idx] = 0
        self.is_myelinated[idx] = False
        self.teacher_verified[idx] = False
        self.is_active[idx] = True
        self.last_active[idx] = time.time()
        
        return idx

    def find_myelinated_path(self, context_key: str, vsa_engine: Optional[Any] = None, exact_only: bool = False) -> Optional[Dict[str, Any]]:
        t0 = time.perf_counter_ns()
        
        # 1. Busca Exata (Hash)
        idx = self.id_to_index.get(context_key)
        if idx is not None and not self.is_active[idx]:
            return None
        if idx is not None and self.is_myelinated[idx]:
            with closing(sqlite3.connect(self.db_path)) as conn, conn:
                cursor = conn.execute("SELECT pipeline_spec FROM pdag_nodes WHERE context_key = ? AND is_active = 1", (context_key,))
                row = cursor.fetchone()
                if row:
                    spec = json.loads(row[0])
                    return {
                        "passos": spec.get("passos", []),
                        "meta_primitive": spec.get("meta_primitive"),
                        "slot_roles": spec.get("slot_roles", {}),
                        "slot_defaults": spec.get("slot_defaults", {}),
                        "__meta__": {
                            "weight": float(self.weights[idx]),
                            "consecutive_successes": int(self.consecutive_successes[idx]),
                            "is_myelinated": True,
                            "source": "ram_cache_exact",
                            "teacher_verified": bool(self.teacher_verified[idx]),
                            "context_key": context_key,
                            "alpha": float(self.alpha[idx]), "beta": float(self.beta[idx])
                        }
                    }

        if exact_only:
            return None
        # 2. Busca por Similaridade Fasorial
        if vsa_engine is not None and self.active_count > 0:
            try:
                q_vec = vsa_engine.text_to_hypervector(context_key)
            except Exception:
                return None
                
            sims = np.real(np.dot(self.phase_matrix[:self.active_count], np.conj(q_vec))) / self.dim
            sims[~self.is_myelinated[:self.active_count]] = -1.0
            sims[~self.is_active[:self.active_count]] = -1.0
            sims[self.teacher_verified[:self.active_count]] = -1.0  # Demonstracoes exigem invocacao exata.
            
            candidates = np.flatnonzero(sims >= 0.70)
            if not candidates.size:
                return None
            samples = self._rng.beta(self.alpha[candidates], self.beta[candidates])
            best_idx = int(candidates[np.argmax(samples)])
            best_sim = float(sims[best_idx])
            
            if best_sim >= 0.70:
                best_key = self.node_ids[best_idx]
                with closing(sqlite3.connect(self.db_path)) as conn, conn:
                    cursor = conn.execute("SELECT pipeline_spec FROM pdag_nodes WHERE context_key = ? AND is_active = 1", (best_key,))
                    row = cursor.fetchone()
                    if row:
                        spec = json.loads(row[0])
                        return {
                            "passos": spec.get("passos", []),
                            "__meta__": {
                                "weight": float(self.weights[best_idx]),
                                "consecutive_successes": int(self.consecutive_successes[best_idx]),
                                "is_myelinated": True,
                                "source": "ram_cache_thompson",
                                "context_key": best_key,
                                "alpha": float(self.alpha[best_idx]), "beta": float(self.beta[best_idx]),
                                "similarity": round(best_sim, 4)
                            }
                        }
        return None

    def update_hebbian(
        self,
        context_key: str,
        lambda_obs: int,
        delta_t: float,
        sigma_lat: float,
        intent: str = "",
        vsa_engine: Any = None,
        pipeline: Optional[Dict[str, Any]] = None,
        route_revision: bool = False,
    ) -> Tuple[float, int, bool]:
        
        if lambda_obs not in (0, 1):
            raise ValueError("lambda_obs deve ser 0 ou 1 (evidencia factual)")
        with self._lock:
            idx = self._get_or_create_node(context_key, intent, vsa_engine)
            if lambda_obs == 0:
                self.teacher_verified[idx] = False
            self.alpha[idx] += lambda_obs
            self.beta[idx] += 1 - lambda_obs
            posterior = self.alpha[idx] / (self.alpha[idx] + self.beta[idx])
            total = self.alpha[idx] + self.beta[idx]
            variance = self.alpha[idx] * self.beta[idx] / (total * total * (total + 1.0))
            
            # Peso agora e a media posterior; latencia nao altera evidencia factual.
            new_weight = 1.0 if self.teacher_verified[idx] and lambda_obs == 1 else posterior
            
            if lambda_obs == 1:
                self.consecutive_successes[idx] += 1
            else:
                self.consecutive_successes[idx] = 0
                self.is_myelinated[idx] = False
                
            self.weights[idx] = new_weight
            self.last_active[idx] = time.time()
            
            self.is_myelinated[idx] = bool(lambda_obs == 1 and (self.teacher_verified[idx] or (posterior >= 0.85 and variance <= 0.02)))
                
            # Enfileira persistencia
            spec_json = json.dumps(pipeline or {"passos": []})
            self._db_queue.put({
                "teacher_verified": bool(self.teacher_verified[idx]),
                "op": "upsert",
                "revision": route_revision,
                "key": context_key,
                "intent": intent,
                "spec": spec_json,
                "phase": self.phase_matrix[idx].tobytes(),
                "weight": float(self.weights[idx]),
                "alpha": float(self.alpha[idx]),
                "beta": float(self.beta[idx]),
                "successes": int(self.consecutive_successes[idx]),
                "myelin": int(self.is_myelinated[idx]),
                "time": float(self.last_active[idx])
            })
            
            return float(self.weights[idx]), int(self.consecutive_successes[idx]), bool(self.is_myelinated[idx])

    def _build_qualia(self, pipeline, vsa_engine):
        spec = dict(pipeline or {})
        telic = spec.get("telic", spec.get("qualia", {}).get("telic"))
        if telic is None:
            return spec, None
        if not isinstance(telic, str) or not telic.strip() or len(telic) > 64 or vsa_engine is None:
            raise ValueError("Qualia exige papel telico explicito e motor FHRR")
        telic = telic.strip().upper()
        agentive = spec.get("passos", spec.get("pipeline", []))
        if not isinstance(agentive, list):
            raise ValueError("Qualia agentive exige lista de passos")
        vector = np.ascontiguousarray(vsa_engine.encode_compositional(action=telic, target="QUALIA"), dtype=np.complex64)
        if vector.shape != (self.dim,) or not np.isfinite(vector).all():
            raise ValueError("Vetor Qualia invalido")
        spec["qualia"] = {"formal": "MACRO_ACTION", "telic": telic, "agentive": agentive,
                          "v_conceito": {"storage": "qualia_vector", "dtype": "complex64", "dim": self.dim}}
        return spec, vector

    def _queue_qualia(self, context_key, spec, vector):
        if vector is not None:
            self._db_queue.put({"op": "qualia", "key": context_key, "telic": spec["qualia"]["telic"],
                "agentive": json.dumps(spec["qualia"]["agentive"]), "vector": vector.tobytes()})

    def get_qualia(self, context_key):
        if not self.flush_pending_writes(5.0):
            raise TimeoutError("Qualia ainda nao persistida")
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            row = conn.execute("SELECT qualia_formal, qualia_telic, qualia_agentive, qualia_vector FROM pdag_nodes WHERE context_key = ?", (context_key,)).fetchone()
        if not row or row[3] is None:
            return None
        return {"formal": row[0], "telic": row[1], "agentive": json.loads(row[2]),
                "v_conceito": np.frombuffer(row[3], dtype=np.complex64).copy()}

    def record_execution(
        self,
        context_key: str,
        intent: str,
        pipeline: Dict[str, Any],
        reinforcement: float = 0.35,
        vsa_engine: Optional[Any] = None,
        route_revision: bool = False,
    ) -> bool:
        pipeline, qualia_vector = self._build_qualia(pipeline, vsa_engine)
        lambda_obs = 1 if reinforcement > 0 else 0
        
        # Extrai tempo se fornecido no pipeline
        delta_t = 1.0
        if "tempo_total_ms" in pipeline:
            delta_t = max(0.001, float(pipeline["tempo_total_ms"]) / 1000.0)
            
        w, s, m = self.update_hebbian(
            context_key=context_key,
            lambda_obs=lambda_obs,
            delta_t=delta_t,
            sigma_lat=0.0,
            intent=intent,
            vsa_engine=vsa_engine,
            pipeline=pipeline, route_revision=route_revision
        )
        self._queue_qualia(context_key, pipeline, qualia_vector)
        return m

    def link_semantic_skill(self, concept, route_key):
        from semantic_concepts import concept_id
        with closing(sqlite3.connect(self.db_path, timeout=5)) as conn, conn:
            name = concept_id(concept)
            if conn.execute("SELECT 1 FROM concepts WHERE id = ?", (name,)).fetchone():
                conn.execute("INSERT OR IGNORE INTO concept_skill_routes VALUES (?, ?)", (name, route_key))
                conn.execute("UPDATE concepts SET status_habilidade = MAX(status_habilidade, 1) WHERE id = ?", (name,))

    def validate_semantic_skill(self, route_key, steps):
        # Human confirmation and process-only opening are not measured visual validation.
        feedbacks = [step.get("feedback", {}) for step in steps]
        if not feedbacks or not all(f.get("lambda_obs") == 1 for f in feedbacks):
            return
        if not any(isinstance(f.get("ncd_real"), (int, float)) and np.isfinite(f["ncd_real"])
                   and f["ncd_real"] > 0.20 for f in feedbacks):
            return
        with closing(sqlite3.connect(self.db_path, timeout=5)) as conn, conn:
            conn.execute("UPDATE concepts SET status_habilidade = 2 WHERE id IN (SELECT concept_id FROM concept_skill_routes WHERE route_key = ?)", (route_key,))

    def propose_verified_procedure(self, context_key, current_context):
        """Exact verified-route lookup; proposal alone never permits execution."""
        if not isinstance(context_key, str) or not context_key:
            return None
        if not isinstance(current_context, dict) or not current_context.get('hwnd') or not current_context.get('pid'):
            return None
        route = self.find_myelinated_path(context_key, exact_only=True)
        if not isinstance(route, dict) or route.get('__meta__', {}).get('teacher_verified') is not True:
            return None
        steps = route.get('passos')
        if not isinstance(steps, list) or not steps:
            return None
        import copy
        return {'status':'PROPOSED', 'steps':copy.deepcopy(steps), 'source':context_key,
                'historically_verified':True, 'context_revalidation_required':True,
                'execution_authorized':False}

    def is_verified_demonstration(self, intent: str) -> bool:
        key = f"trajectory:{intent.casefold().strip()}"
        with self._lock:
            idx = self.id_to_index.get(key)
            return bool(idx is not None and self.is_active[idx] and self.teacher_verified[idx] and self.is_myelinated[idx])

    def record_user_confirmed_route(self, context_key, intent, pipeline, vector, vsa_engine):
        """Explicit /fim attestation; retains original NCD, never fabricates step feedback."""
        spec = dict(pipeline, human_confirmed=True, evidence_source="HUMAN_CONFIRMATION")
        json.dumps(spec)  # Validate before changing RAM flags.
        vector = np.ascontiguousarray(vector, dtype=np.complex64)
        if vector.shape != (self.dim,) or not np.isfinite(vector).all():
            raise ValueError("Vetor confirmado invalido")
        with self._lock:
            idx = self._get_or_create_node(context_key, intent, vsa_engine)
            self.phase_matrix[idx] = vector
            self.teacher_verified[idx] = True
            self.is_active[idx] = True
            self.is_permanent[idx] = True # STC: Confirmação humana imuniza a rota
        promoted = self.record_execution(context_key, intent, spec, reinforcement=1.0, vsa_engine=vsa_engine, route_revision=True)
        if promoted is not True or not self.flush_pending_writes(5.0):
            raise RuntimeError("Persistencia da confirmacao humana nao concluida")
        return True

    def record_human_demonstration(self, context_key: str, intent: str, pipeline: Dict[str, Any], vsa_engine: Any = None) -> bool:
        """Persiste instrucao humana sem inventar evidencia Beta/NCD ou mielinizacao."""
        steps = pipeline.get("passos", [])
        if not isinstance(steps, list) or len(steps) > 100 or any(step.get("acao") not in ("HOTKEY", "TYPE", "CLICK") for step in steps):
            raise ValueError("Captura humana invalida")
        spec, qualia_vector = self._build_qualia(dict(pipeline, human_taught=True, pending_validation=True), vsa_engine)
        with self._lock:
            idx = self._get_or_create_node(context_key, intent, vsa_engine)
            self.teacher_verified[idx] = self.is_myelinated[idx] = False
            self.is_active[idx] = True
            if spec.get("meta_primitive") == "OPEN_APP" and vsa_engine is not None:
                from role_binding import encode_open_concept
                self.phase_matrix[idx] = encode_open_concept(vsa_engine)
            self._db_queue.put({"op": "upsert", "revision": True, "key": context_key, "intent": intent,
                "spec": json.dumps(spec), "phase": self.phase_matrix[idx].tobytes(),
                "weight": float(self.weights[idx]), "alpha": float(self.alpha[idx]), "beta": float(self.beta[idx]),
                "successes": int(self.consecutive_successes[idx]), "myelin": 0, "teacher_verified": False,
                "is_permanent": True,
                "time": float(self.last_active[idx])})
            self._queue_qualia(context_key, spec, qualia_vector)
        if not self.flush_pending_writes(5.0):
            raise RuntimeError("SQLite nao confirmou a captura humana")
        return True

    def find_taught_path(self, context_key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            if context_key not in self.id_to_index or not self.is_active[self.id_to_index[context_key]]:
                return None
            with closing(sqlite3.connect(self.db_path)) as conn, conn:
                row = conn.execute("SELECT pipeline_spec FROM pdag_nodes WHERE context_key = ? AND is_active = 1", (context_key,)).fetchone()
            spec = json.loads(row[0]) if row else {}
            if spec.get("human_taught") is not True:
                return None
            return {**spec, "__meta__": {"context_key": context_key, "source": "human_instruction",
                    "teacher_verified": False, "human_taught": True, "is_myelinated": False}}

    def record_demonstration(self, context_key: str, intent: str, pipeline: Dict[str, Any], vsa_engine: Any = None) -> bool:
        steps = pipeline.get("passos", [])
        if not steps or len(steps) > 100:
            raise ValueError("Demonstracao exige de 1 a 100 passos verificados")
        for step in steps:
            evidence = step.get("feedback", {})
            ncd = evidence.get("ncd_real")
            if step.get("acao") not in ("HOTKEY", "TYPE", "CLICK") or evidence.get("lambda_obs") != 1 or not isinstance(ncd, (int, float)) or not np.isfinite(ncd) or ncd < 0.02 or not evidence.get("observed_hwnd"):
                raise ValueError("Todos os passos precisam de NCD e HWND factuais confirmados")
        self.record_execution(context_key=context_key, intent=intent, pipeline=pipeline, reinforcement=1.0, vsa_engine=vsa_engine, route_revision=True)
        with self._lock:
            idx = self.id_to_index[context_key]
            self.teacher_verified[idx] = self.is_myelinated[idx] = True
            self.is_active[idx] = True
            self.weights[idx] = 1.0
            if pipeline.get("meta_primitive") == "OPEN_APP" and vsa_engine is not None:
                from role_binding import encode_open_concept
                self.phase_matrix[idx] = encode_open_concept(vsa_engine)
            self._db_queue.put({"op": "upsert", "key": context_key, "intent": intent,
                "spec": json.dumps(pipeline), "phase": self.phase_matrix[idx].tobytes(),
                "weight": 1.0, "alpha": float(self.alpha[idx]), "beta": float(self.beta[idx]),
                "successes": int(self.consecutive_successes[idx]), "myelin": 1,
                "teacher_verified": True, "time": float(self.last_active[idx])})
        if not self.flush_pending_writes(5.0):
            raise RuntimeError("SQLite nao confirmou a persistencia da demonstracao")
        return True

    def find_abstract_opening(self, app: str, vsa_engine: Any) -> Optional[Dict[str, Any]]:
        """Compara o papel ACTION, sem confundir alvo novo com acao nova."""
        from role_binding import encode_open_concept, substitute_slots
        if not isinstance(app, str) or not app.strip():
            raise ValueError("Transferencia exige aplicativo explicito")
        intention = vsa_engine.encode_compositional(action="OPEN", target=app)
        query = encode_open_concept(vsa_engine)
        with self._lock:
            candidates = range(self.active_count)
            with closing(sqlite3.connect(self.db_path)) as conn, conn:
                matches = []
                for idx in candidates:
                    if not self.is_active[idx]:
                        continue
                    score = float(vsa_engine.similarity(query, self.phase_matrix[idx]))
                    if not np.isfinite(score) or score <= 0.70:
                        continue
                    row = conn.execute("SELECT pipeline_spec FROM pdag_nodes WHERE context_key = ? AND is_active = 1", (self.node_ids[idx],)).fetchone()
                    if row is None:
                        continue
                    spec = json.loads(row[0])
                    verified = self.teacher_verified[idx] and self.is_myelinated[idx]
                    instructed = spec.get("human_taught") is True and self.beta[idx] <= self.alpha[idx]
                    if not (verified or instructed):
                        continue
                    if (spec.get("meta_primitive") != "OPEN_APP" or spec.get("concept_encoding") != "FHRR_ACTION_V1"
                            or spec.get("meta_pipeline") != [{"acao": "OPEN_APP", "app": "{SLOT_APP}"}]):
                        continue
                    matches.append((score, int(idx), spec))
                if not matches:
                    return None
                score, idx, spec = max(matches, key=lambda item: item[0])
                return {"pipeline": substitute_slots(spec["meta_pipeline"], {"SLOT_APP": app}),
                        "source": self.node_ids[idx], "similarity": score, "similarity_space": "ROLE_ACTION",
                        "pending_validation": not bool(self.teacher_verified[idx]),
                        "raw_intent_similarity": float(vsa_engine.similarity(intention, self.phase_matrix[idx]))}

    def apply_user_report_penalty(self, intent: str, reason: str = "") -> Dict[str, Any]:
        with self._lock:
            idx = self.id_to_index.get(f"trajectory:{intent.lower().strip()[:40]}")
            if idx is not None:
                self.teacher_verified[idx] = False
                self.beta[idx] += 1.0
                new_weight = self.alpha[idx] / (self.alpha[idx] + self.beta[idx])
                self.weights[idx] = new_weight
                self.consecutive_successes[idx] = 0
                self.is_myelinated[idx] = False
                self.last_active[idx] = time.time()
                
                self._db_queue.put({
                    "op": "upsert",
                    "key": self.node_ids[idx],
                    "intent": intent,
                    "spec": json.dumps({"status": "punished"}),
                    "phase": self.phase_matrix[idx].tobytes(),
                    "weight": float(new_weight),
                    "alpha": float(self.alpha[idx]),
                    "beta": float(self.beta[idx]),
                    "successes": 0,
                    "myelin": 0,
                    "time": float(self.last_active[idx])
                })
                
                snapshot_id = f"SNAP_{int(time.time()*1000)}"
                self._db_queue.put({
                    "op": "blackbox",
                    "snapshot_id": snapshot_id,
                    "key": self.node_ids[idx],
                    "reason": reason or "Report manual",
                    "lambda": 0,
                    "time": time.time()
                })
                
                return {"status": "PENALTY_APPLIED", "snapshot_id": snapshot_id, "new_weight": new_weight}
                
            return {"status": "NOT_FOUND"}

    def apply_ebbinghaus_decay(self, days_elapsed: float = 0.0) -> int:
        pruned = 0
        now = time.time()
        cutoff_days = max(days_elapsed, 90.0) * 86400.0
        
        with self._lock:
            for idx in range(self.active_count):
                if self.is_myelinated[idx] or self.is_permanent[idx]:
                    continue
                    
                age = now - self.last_active[idx]
                if age > cutoff_days:
                    # Decaimento de Ebbinghaus
                    lam = np.log(2) / (30.0 * 86400.0)
                    w_decayed = float(self.weights[idx]) * np.exp(-lam * age)
                    
                    if w_decayed < 0.05:
                        pruned += 1
                        self.weights[idx] = 0.0
                        self.is_myelinated[idx] = False
                        self.consecutive_successes[idx] = 0
                        self._db_queue.put({"op": "delete", "key": self.node_ids[idx]})
                        
        return pruned

    @contextmanager
    def node_snapshot(self, myelinated_only: bool = False):
        if not self.flush_pending_writes(5.0):
            raise TimeoutError("P-DAG nao concluiu as escritas pendentes")
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            where = "WHERE is_active = 1 AND is_myelinated = 1" if myelinated_only else "WHERE is_active = 1"
            rows = conn.execute(
                f"SELECT context_key, intent, pipeline_spec, weight, consecutive_successes, is_myelinated FROM pdag_nodes {where} ORDER BY last_active DESC LIMIT ?",
                (self.max_nodes,),
            ).fetchall()
        yield [dict(row) for row in rows]

    def get_node_phases(self, context_key: str) -> Optional[np.ndarray]:
        idx = self.id_to_index.get(context_key)
        if idx is not None and self.is_active[idx]:
            return self.phase_matrix[idx].copy()
        return None

    def flush_pending_writes(self, timeout_sec: float = 2.0) -> bool:
        start = time.time()
        while time.time() - start < timeout_sec:
            if self._db_queue.unfinished_tasks == 0:
                return True
            time.sleep(0.05)
        return False

    def close(self) -> None:
        self._running = False
        self.flush_pending_writes(2.0)
        if self._db_thread is not None:
            self._db_thread.join(timeout=2.0)

# Alias canonico
HybridPDAGEngine = MyelinatedPDAGEngine
