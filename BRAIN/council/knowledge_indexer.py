# =============================================================================
# council/knowledge_indexer.py — Memória Não-Estruturada (Textos, Logs, Markdown)
# =============================================================================

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("Council.Knowledge")

class KnowledgeIndexer:
    """
    Indexa conhecimento textual (Markdown, Logs, Mission Reports).
    Diferente do ArchitectureIndexer (que foca em código AST), este indexa 
    linguagem natural e histórico.
    """
    
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.index_file = self.root / "knowledge_index.json"
        self.documents: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.index_file.exists():
            try:
                self.documents = json.loads(self.index_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(f"Erro ao carregar KnowledgeIndex: {e}")

    def save(self) -> None:
        self.index_file.write_text(json.dumps(self.documents, indent=2, ensure_ascii=False), encoding="utf-8")

    def ingest_file(self, path: Path) -> None:
        """Lê um arquivo de texto e o adiciona ao índice."""
        if not path.exists() or not path.is_file():
            return
        
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return

        doc_id = str(path.relative_to(self.root))
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        # Evita reprocessar se o hash for o mesmo
        if doc_id in self.documents and self.documents[doc_id]["hash"] == content_hash:
            return

        self.documents[doc_id] = {
            "hash": content_hash,
            "path": str(path),
            "content": content[:5000], # Guarda um snippet para busca rápida
            "length": len(content),
            "updated_at": str(path.stat().st_mtime)
        }
        logger.info(f"Ingerido no KnowledgeIndex: {doc_id}")

    def ingest_directory(self, extensions: list[str] = [".md", ".txt", ".log"]) -> int:
        """Varre uma pasta em busca de conhecimento."""
        count = 0
        for ext in extensions:
            for p in self.root.rglob(f"*{ext}"):
                if "node_modules" in str(p) or ".git" in str(p):
                    continue
                self.ingest_file(p)
                count += 1
        self.save()
        return count

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """
        Busca textual simples (TF-IDF simplificado / Regex).
        Pode ser expandido para embeddings vetoriais no futuro.
        """
        query_tokens = set(re.findall(r"\w+", query.lower()))
        if not query_tokens:
            return []

        results = []
        for doc_id, doc in self.documents.items():
            content_lower = doc["content"].lower()
            score = sum(content_lower.count(tok) for tok in query_tokens)
            if score > 0:
                results.append({
                    "doc_id": doc_id,
                    "path": doc["path"],
                    "score": score,
                    "snippet": doc["content"][:300] + "..."
                })
        
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]