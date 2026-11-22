import json
import logging
import sqlite3
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("BRAINNET_LongContext")

class ProvenanceContext:
    """Opt-in, in-memory chunk ledger; extracted claims are not verified facts."""
    def __init__(self, task_id):
        if not task_id:
            raise ValueError('task_id obrigatório')
        self.task_id = task_id
        self.blocks = {}

    def add_block(self, block_id, source, location, *, dependencies=()):
        if not block_id or block_id in self.blocks or not source or location is None:
            raise ValueError('identidade ou proveniência inválida')
        self.blocks[block_id] = {'task_id': self.task_id, 'block_id': block_id,
            'source': source, 'location': location, 'facts': [], 'evidence': [],
            'current_state': None, 'confirmed_decisions': [], 'hypotheses': [],
            'contradictions': [], 'pending': [], 'dependencies': list(dependencies),
            'status': 'PENDING'}

    def record(self, block_id, *, status, extracted_claims=(), evidence=(),
               hypotheses=(), contradictions=(), pending=(), current_state=None):
        if status not in ('PROCESSED', 'FAILED', 'PARTIAL'):
            raise ValueError('estado não permitido para extração')
        block = self.blocks[block_id]
        block.update(status=status, hypotheses=list(hypotheses),
                     contradictions=list(contradictions), pending=list(pending),
                     current_state=current_state)
        block['evidence'] = list(evidence)
        # Extraction remains a hypothesis even when returned by an LLM.
        block['hypotheses'].extend(extracted_claims)

    def select(self, block_ids):
        import copy
        return [copy.deepcopy(self.blocks[block_id]) for block_id in block_ids]

class LongContextEngine:
    """
    Motor de Leitura Longa (Recursive Summarization / Map-Reduce).
    Lê um texto grande em chunks, mantém um resumo cumulativo e persiste em SQLite.
    """
    __slots__ = ("db_path", "_conn")

    def __init__(self, db_path: str = "long_context.db"):
        if db_path == ":memory:":
            self.db_path = ":memory:"
        else:
            self.db_path = str(Path(__file__).resolve().parent / db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, isolation_level=None)
        self._init_schema()

    def _init_schema(self):
        with self._conn:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS long_context_state (
                    doc_id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    source_path TEXT,
                    total_chunks INTEGER DEFAULT 0,
                    current_chunk INTEGER DEFAULT 0,
                    cumulative_summary TEXT,
                    status TEXT DEFAULT 'PENDING',
                    created_at REAL,
                    updated_at REAL
                );
            """)

    def _call_llm_summary(self, current_summary: str, chunk: str) -> str:
        """Chama o LLM local para atualizar o resumo."""
        prompt = f"""Você é um sintetizador de texto. Sua tarefa é atualizar o resumo abaixo com as informações do novo trecho.
        
RESUMO ATUAL:
{current_summary if current_summary else "(Nenhum resumo ainda. Este é o primeiro trecho.)"}

NOVO TRECHO:
{chunk}

Instrução: Escreva um resumo atualizado e coeso que incorpore as informações do novo trecho ao resumo atual. Seja detalhado, mas conciso. Máximo de 800 palavras. Retorne APENAS o texto do resumo, sem introduções ou explicações.
"""
        payload = {
            "model": "qwen2.5-coder:7b",
            "prompt": prompt,
            "stream": False,
            "keep_alive": "5m",
            "options": {"temperature": 0.1, "num_ctx": 8192, "num_thread": 14, "num_predict": 1000}
        }
        
        try:
            req = urllib.request.Request("http://localhost:11434/api/generate", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                summary = data.get("response", "").strip()
                if not summary:
                    raise ValueError("Resposta de resumo vazia")
                return summary
        except Exception as ex:
            logger.error(f"[LONG CONTEXT]: Falha ao chamar LLM para resumo: {ex}")
            raise RuntimeError("Falha na inferência do resumo") from ex

    def process_long_text(self, text: str, doc_id: str, source_path: str = "chat_input") -> Dict[str, Any]:
        """Processa o texto longo em chunks, mantendo o resumo cumulativo."""
        chunk_size = 2500
        chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
        total = len(chunks)
        
        now = time.time()
        with self._conn:
            self._conn.execute("""
                INSERT INTO long_context_state (doc_id, source_type, source_path, total_chunks, current_chunk, cumulative_summary, status, created_at, updated_at)
                VALUES (?, 'chat', ?, ?, 0, '', 'IN_PROGRESS', ?, ?)
                ON CONFLICT(doc_id) DO UPDATE SET
                    total_chunks = excluded.total_chunks,
                    current_chunk = 0,
                    cumulative_summary = '',
                    status = 'IN_PROGRESS',
                    updated_at = excluded.updated_at
            """, (doc_id, source_path, total, now, now))

        current_summary = ""
        for i, chunk in enumerate(chunks):
            logger.info(f"[LONG CONTEXT]: Processando chunk {i+1}/{total} do doc '{doc_id}'...")
            try:
                new_summary = self._call_llm_summary(current_summary, chunk)
                if not isinstance(new_summary, str) or not new_summary.strip():
                    raise ValueError("Resposta de resumo vazia")
            except Exception as ex:
                with self._conn:
                    self._conn.execute("UPDATE long_context_state SET status = 'FAILED', updated_at = ? WHERE doc_id = ?", (time.time(), doc_id))
                return {"status": "FAILED", "doc_id": doc_id, "chunks": total,
                        "processed_chunks": i, "failed_chunk": i + 1,
                        "final_summary": current_summary, "error": type(ex).__name__}
            current_summary = new_summary
            
            with self._conn:
                self._conn.execute("""
                    UPDATE long_context_state 
                    SET current_chunk = ?, cumulative_summary = ?, updated_at = ?
                    WHERE doc_id = ?
                """, (i + 1, current_summary, time.time(), doc_id))

        with self._conn:
            self._conn.execute("""
                UPDATE long_context_state 
                SET status = 'DONE', updated_at = ?
                WHERE doc_id = ?
            """, (time.time(), doc_id))

        return {"status": "DONE", "doc_id": doc_id, "chunks": total, "final_summary": current_summary}

    def get_summary(self, doc_id: str) -> Optional[str]:
        """Recupera o resumo cumulativo de um documento."""
        try:
            cursor = self._conn.execute("SELECT cumulative_summary FROM long_context_state WHERE doc_id = ? AND status = 'DONE'", (doc_id,))
            row = cursor.fetchone()
            if row and row[0]:
                return row[0]
        except Exception:
            pass
        return None
