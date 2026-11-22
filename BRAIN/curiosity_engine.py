"""Detecta lacunas de conhecimento — o que o organismo viu mas não entendeu."""
import logging
import sqlite3
import time
from typing import List

logger = logging.getLogger("BRAINNET_Curiosity")


class CuriosityEngine:
    """Gera até 5 perguntas por ciclo a partir de 3 fontes:
       1. Apps em transitions sem conceito na ontologia
       2. Queries em hd_web_memory sem conceito na ontologia
       3. Intenções do P-DAG não mielinizadas
    """

    def __init__(self, kernel):
        self.kernel = kernel
        self.max_gaps = 5

    def detect_gaps(self) -> List[str]:
        gaps, seen = [], set()
        ontology = getattr(self.kernel, "ontology", None)
        cached = getattr(ontology, "_cached_aliases", {}) if ontology else {}

        # 1. Apps em transitions sem ontologia
        try:
            with sqlite3.connect(self.kernel.pdag.db_path, timeout=5) as conn:
                cur = conn.execute(
                    "SELECT DISTINCT app_name FROM transitions "
                    "WHERE timestamp > ? AND app_name IS NOT NULL AND app_name != 'unknown'",
                    (time.time() - 86400,)
                )
                apps = [r[0].removesuffix(".exe").strip() for r in cur.fetchall() if r[0]]
        except Exception as ex:
            logger.debug(f"[CURIOSITY]: transitions falhou: {ex}")
            apps = []
        for app in apps:
            if not app or len(app) < 2:
                continue
            if app not in seen and app.lower() not in cached:
                gaps.append(app)
                seen.add(app)

        # 2. Queries em hd_web_memory sem ontologia
        try:
            with sqlite3.connect(self.kernel.pdag.db_path, timeout=5) as conn:
                cur = conn.execute(
                    "SELECT DISTINCT query FROM hd_web_memory WHERE created_at > ? LIMIT 5",
                    (time.time() - 7 * 86400,)
                )
                queries = [r[0].strip() for r in cur.fetchall() if r[0]]
        except Exception:
            queries = []
        for q in queries:
            word = q.split()[0].lower() if q.split() else ""
            if word and len(word) > 2 and word not in seen and word not in cached:
                gaps.append(word)
                seen.add(word)

        # 3. Intenções do P-DAG não mielinizadas
        try:
            with sqlite3.connect(self.kernel.pdag.db_path, timeout=5) as conn:
                cur = conn.execute(
                    "SELECT DISTINCT intent FROM pdag_nodes "
                    "WHERE is_myelinated = 0 AND is_active = 1 LIMIT 5"
                )
                intents = [r[0].strip() for r in cur.fetchall() if r[0]]
        except Exception:
            intents = []
        for it in intents:
            word = it.split()[0].lower() if it.split() else ""
            if word and len(word) > 2 and word not in seen and word not in cached:
                gaps.append(word)
                seen.add(word)

        result = gaps[:self.max_gaps]
        if result:
            logger.info(f"[CURIOSITY]: {len(result)} lacuna(s): {result}")
        return result
