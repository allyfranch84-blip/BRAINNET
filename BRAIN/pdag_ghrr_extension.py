"""
Extensão Sintática do P-DAG: Armazena pipelines ordenados usando GHRR.
Não substitui o FHRR. Convive em paralelo para preservar a ordem das ações.
"""
from __future__ import annotations
import json
import sqlite3
from contextlib import closing
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from ghrr_core import GHRRHyperdimensionalEngine

class SyntacticPDAG:
    @staticmethod
    def route_key(intent: str, context: dict) -> str:
        """Versioned identity; does not migrate or overwrite legacy route keys."""
        import hashlib
        if not isinstance(intent, str) or not intent.strip() or not isinstance(context, dict):
            raise ValueError('intent and context required')
        payload=json.dumps({'version':1,'intent':' '.join(intent.casefold().split()),'context':context},
                           sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
        return 'trajectory:ghrr:v1:' + hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def propose_route(self, context_key: str) -> Optional[Dict[str, Any]]:
        """Return a legacy route for review only, never as authorization to act."""
        route = self.retrieve_route(context_key)
        if route is None: return None
        return {'status':'REVIEW_REQUIRED', 'execution_authorized':False,
                'historical_verification':'UNKNOWN', 'context_key':context_key,
                'intent':route['intent'], 'steps':route['steps'],
                'representation_version':'LEGACY_UNVERSIONED'}

    def propose_similar(self, steps, context, candidates, *, threshold=0.8):
        """Rank explicitly supplied, verified-context candidates; never execute."""
        required = ('process', 'window', 'target')
        if not isinstance(context, dict) or any(not context.get(k) for k in required):
            return []
        if not 0 <= threshold <= 1:
            raise ValueError('invalid threshold')
        query = self._encode_sequence(steps)
        proposals = []
        for candidate in candidates:
            if not isinstance(candidate, dict) or not candidate.get('source') or candidate.get('historical_verified') is not True:
                continue
            candidate_context = candidate.get('context')
            if not isinstance(candidate_context, dict) or any(candidate_context.get(k) != context[k] for k in required):
                continue
            try:
                similarity = self.engine.similarity(query, self._encode_sequence(candidate['steps']))
            except (KeyError, TypeError, ValueError):
                continue
            if np.isfinite(similarity) and similarity >= threshold:
                proposals.append({'status':'REVIEW_REQUIRED', 'execution_authorized':False,
                    'source':candidate['source'], 'context':dict(candidate_context),
                    'steps':json.loads(json.dumps(candidate['steps'])), 'similarity':similarity})
        return sorted(proposals, key=lambda item:item['similarity'], reverse=True)

    def __init__(self, db_path: str, engine: GHRRHyperdimensionalEngine):
        self.db_path = str(Path(db_path).resolve())
        self.engine = engine
        self._init_schema()

    def _init_schema(self):
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pdag_syntactic_routes (
                    context_key TEXT PRIMARY KEY,
                    intent TEXT NOT NULL,
                    pipeline_steps TEXT NOT NULL,
                    ghrr_blob BLOB NOT NULL,
                    weight REAL DEFAULT 1.0,
                    is_active INTEGER DEFAULT 1,
                    last_active REAL NOT NULL
                );
            """)
            conn.commit()

    def _encode_sequence(self, steps: List[Dict[str, Any]]) -> np.ndarray:
        """Codifica a sequência de passos em um único hipervetor GHRR."""
        if not steps:
            raise ValueError("Pipeline vazio")
        
        # Gera um vetor para cada passo (usando JSON como string única)
        step_vectors = [
            self.engine.generate_vector(json.dumps(step, sort_keys=True, ensure_ascii=False))
            for step in steps
        ]
        
        # Encadeia com bind não-comutativo (da esquerda para a direita)
        sequence = step_vectors[0]
        for vec in step_vectors[1:]:
            sequence = self.engine.bind(sequence, vec)
        
        return sequence

    def store_route(self, context_key: str, intent: str, steps: List[Dict[str, Any]]) -> bool:
        """Armazena uma rota sintática no banco."""
        vector = self._encode_sequence(steps)
        pipeline_json = json.dumps(steps, ensure_ascii=False)
        
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute("""
                INSERT OR REPLACE INTO pdag_syntactic_routes
                (context_key, intent, pipeline_steps, ghrr_blob, last_active)
                VALUES (?, ?, ?, ?, ?)
            """, (context_key, intent, pipeline_json, vector.tobytes(), time.time()))
            conn.commit()
        return True

    def retrieve_route(self, context_key: str) -> Optional[Dict[str, Any]]:
        """Recupera e decodifica a rota sintática."""
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            row = conn.execute(
                "SELECT intent, pipeline_steps, ghrr_blob FROM pdag_syntactic_routes WHERE context_key = ? AND is_active = 1",
                (context_key,)
            ).fetchone()
        
        if not row:
            return None
        
        intent, pipeline_json, blob = row
        # Reconstrói o vetor GHRR a partir do blob
        vector_shape = (self.engine.num_blocks, self.engine.matrix_size, self.engine.matrix_size)
        expected_bytes = int(np.prod(vector_shape)) * np.dtype(np.complex64).itemsize
        if not isinstance(blob, bytes) or len(blob) != expected_bytes:
            raise ValueError("Blob GHRR incompatível ou truncado")
        vector = np.frombuffer(blob, dtype=np.complex64).reshape(vector_shape).copy()
        if not np.isfinite(vector).all():
            raise ValueError("Blob GHRR contém valores não finitos")
        
        return {
            "context_key": context_key,
            "intent": intent,
            "steps": json.loads(pipeline_json),
            "vector": vector,
            "num_steps": len(json.loads(pipeline_json))
        }

    def verify_sequence(self, context_key: str, candidate_steps: List[Dict[str, Any]]) -> float:
        """Verifica se uma sequência é compatível com a rota armazenada."""
        route = self.retrieve_route(context_key)
        if route is None:
            return 0.0
        
        candidate_vector = self._encode_sequence(candidate_steps)
        return self.engine.similarity(route["vector"], candidate_vector)
