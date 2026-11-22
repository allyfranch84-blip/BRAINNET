import logging
import sqlite3
from contextlib import closing
import time
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("BRAINNET_MemoryConsolidator")

class MemoryConsolidator:
    __slots__ = ("pdag_db_path", "hmem_db_path", "long_context_db_path")

    def __init__(self, pdag_db_path: str = "core1_pdag.db", hmem_db_path: str = "hmem_memory.db", long_context_db_path: str = "long_context.db"):
        self.pdag_db_path = str(Path(__file__).resolve().parent / pdag_db_path)
        self.hmem_db_path = str(Path(__file__).resolve().parent / hmem_db_path)
        self.long_context_db_path = str(Path(__file__).resolve().parent / long_context_db_path)

    def prune_short_term_memory(self, ttl_minutes: int = 20) -> int:
        """Remove eventos de uso antigos (Curto Prazo) do banco do P-DAG."""
        cutoff = time.time() - (ttl_minutes * 60)
        deleted = 0
        try:
            with closing(sqlite3.connect(self.pdag_db_path)) as conn, conn:
                cur = conn.execute("DELETE FROM usage_events WHERE started_at < ?", (cutoff,))
                deleted += cur.rowcount
                conn.commit()
        except sqlite3.OperationalError:
            pass  # Tabela ainda não existe
        except Exception as e:
            logger.error(f"[MEMORY]: Falha ao podar curto prazo: {e}")
        return deleted

    def consolidate_long_term_memory(self, ttl_days: int = 60) -> int:
        """Aplica o Ebbinghaus nas memórias episódicas, protegendo as permanentes."""
        cutoff = time.time() - (ttl_days * 86400)
        deleted = 0
        try:
            with closing(sqlite3.connect(self.hmem_db_path)) as conn, conn:
                columns = {row[1] for row in conn.execute("PRAGMA table_info(hmem_nodes)")}
                if "is_permanent" not in columns:
                    conn.execute("ALTER TABLE hmem_nodes ADD COLUMN is_permanent INTEGER DEFAULT 0")
                
                cur = conn.execute(
                    "DELETE FROM hmem_nodes WHERE timestamp < ? AND is_permanent = 0", 
                    (cutoff,)
                )
                deleted += cur.rowcount
                conn.commit()
        except Exception as e:
            logger.error(f"[MEMORY]: Falha ao consolidar longo prazo: {e}")
        return deleted

    def promote_to_permanent(self, min_access_count: int = 3) -> int:
        """Promove para permanente as memórias com alta frequência de acesso."""
        promoted = 0
        try:
            with closing(sqlite3.connect(self.hmem_db_path)) as conn, conn:
                columns = {row[1] for row in conn.execute("PRAGMA table_info(hmem_nodes)")}
                if "is_permanent" not in columns:
                    conn.execute("ALTER TABLE hmem_nodes ADD COLUMN is_permanent INTEGER DEFAULT 0")
                if "access_count" not in columns:
                    conn.execute("ALTER TABLE hmem_nodes ADD COLUMN access_count INTEGER DEFAULT 0")
                
                cur = conn.execute(
                    "UPDATE hmem_nodes SET is_permanent = 1 WHERE access_count >= ? AND is_permanent = 0",
                    (min_access_count,)
                )
                promoted += cur.rowcount
                conn.commit()
        except Exception as e:
            logger.error(f"[MEMORY]: Falha ao promover para permanente: {e}")
        return promoted

    def consolidate_all(self) -> Dict[str, int]:
        short = self.prune_short_term_memory()
        perm = self.promote_to_permanent()
        long = self.consolidate_long_term_memory()
        logger.info(f"[MEMORY]: Consolidação concluída. Curto: {short}, Longo: {long}, Permanente: {perm}")
        return {"short_term_pruned": short, "long_term_pruned": long, "permanent_promoted": perm}
