# ==============================================================================
# BRAINNET v7 - SISTEMA OPERACIONAL COGNITIVO
# MODULO: epistemic_ontology.py
# FUNCAO: Motor de Auto-Interrogação Epistêmica, Ontologia Dinâmica Viva (Zero-APP_MAP)
#         e Projeção de Conceitos em Hipervetores C^10.000 (FHRR).
# ==============================================================================

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
import sqlite3
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.request
import numpy as np

BRAIN_DIR = Path(__file__).resolve().parent
if str(BRAIN_DIR) not in sys.path:
    sys.path.insert(0, str(BRAIN_DIR))

from hyperdimensional import FHRRHyperdimensionalEngine

logger = logging.getLogger("BRAINNET_Ontology")


class EpistemicOntologyEngine:
    """
    [ONTOLOGIA VIVA & AUTO-INTERROGAÇÃO CONCEITUAL]:
    Substitui dicionários engessados (APP_MAP). Constrói o conhecimento
    semântico do SO via auto-questionamento pós-tarefa e projeção fasorial.
    """

    SCHEMA = """
    PRAGMA journal_mode = WAL;
    CREATE TABLE IF NOT EXISTS learned_concepts (
        concept_key TEXT PRIMARY KEY,
        category TEXT NOT NULL,
        functional_purpose TEXT NOT NULL,
        executable_hint TEXT NOT NULL,
        confidence REAL NOT NULL DEFAULT 0.5,
        access_count INTEGER NOT NULL DEFAULT 1,
        vector_bytes BLOB NOT NULL,
        last_interrogated REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_concept_cat ON learned_concepts (category);
    """

    __slots__ = ("vsa", "db_path", "_conn", "pending_reflections", "_cached_aliases")

    def __init__(self, vsa_engine: FHRRHyperdimensionalEngine, db_path: str = "concept_ontology.db") -> None:
        self.vsa = vsa_engine
        self.db_path = str(BRAIN_DIR / db_path)
        self.pending_reflections: List[str] = []
        self._cached_aliases: Dict[str, str] = {}
        try:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False, isolation_level=None)
            self._conn.executescript(self.SCHEMA)
        except sqlite3.Error as ex:
            logger.exception(
                "[ONTOLOGIA]: falha ao abrir/criar %s: %s", self.db_path, ex
            )
            raise RuntimeError(f"Ontologia não pôde ser aberta: {ex}") from ex
        try:
            self._carregar_cache_memoria()
        except sqlite3.Error as ex:
            logger.exception(
                "[ONTOLOGIA]: falha ao carregar cache de aliases (tabela learned_concepts): %s", ex
            )
            raise RuntimeError(f"learned_concepts inacessível: {ex}") from ex

    def _carregar_cache_memoria(self) -> None:
        """Carrega aliases e executáveis aprendidos na RAM para resposta em <0.1ms."""
        cursor = self._conn.execute("SELECT concept_key, executable_hint FROM learned_concepts WHERE executable_hint != '';")
        for key, exe in cursor.fetchall():
            self._cached_aliases[key.lower().strip()] = exe

    def resolve_executable_dynamically(self, app_name: str) -> Optional[str]:
        """
        [RESOLUÇÃO EPISTÊMICA NÃO-LINEAR EM C^10.000]:
        Localiza executáveis por ressonância analógica contra o cache fasorial
        em RAM, sem dicionários rígidos de termos pré-fixados.
        """
        target = app_name.lower().strip()
        
        # 1. Correspondência direta no cache quente em RAM
        if target in self._cached_aliases:
            return self._cached_aliases[target]

        # 2. Ressonância Fasorial contra Conceitos Consolidados em RAM
        if self._cached_aliases:
            v_target = self.vsa.generate_vector(target)
            melhor_exe = None
            maior_sim = -1.0

            for conceito, exe in self._cached_aliases.items():
                v_conceito = self.vsa.generate_vector(conceito)
                sim = self.vsa.similarity(v_target, v_conceito)
                if target in conceito or conceito in target:
                    sim += 0.30

                if sim > maior_sim:
                    maior_sim = sim
                    melhor_exe = exe

            # Se a ressonância semântica atingir o limiar Hebbiano
            if maior_sim >= 0.45 and melhor_exe:
                return melhor_exe

        return None

    def queue_post_action_reflection(self, target_entity: str) -> None:
        """Enfileira um alvo recém-utilizado para o ciclo de auto-interrogação."""
        alvo = target_entity.strip().lower()
        if len(alvo) >= 2 and alvo not in self.pending_reflections:
            self.pending_reflections.append(alvo)
            logger.info(f"[ONTOLOGIA]: '{alvo}' agendado para auto-interrogação epistêmica.")

    def run_socratic_self_interrogation(self, target_entity: str) -> Dict[str, Any]:
        """
        [MOTOR INTERNO DE AUTO-INTERROGAÇÃO]:
        Questiona o conceito: 'O que é isso? Qual seu propósito? Como interagir?'
        Grava a representação relacional em C^10.000.
        """
        t0 = time.perf_counter_ns()
        alvo = target_entity.strip().lower()

        # Prompt restrito ao Qwen 1.5B para destilação ontológica
        prompt = (
            "Você é o Córtex de Conceitualização da BRAINNET v7.\n"
            f"Analise o conceito ou aplicativo: '{alvo}'.\n"
            "Responda EXCLUSIVAMENTE um JSON estruturado:\n"
            "{\n"
            '  "categoria": "ex: REDE_SOCIAL | NAVEGADOR | EDITOR_TEXTO | SISTEMA",\n'
            '  "proposito": "ex: troca de mensagens instantâneas entre usuários",\n'
            '  "executavel_sugerido": "ex: whatsapp ou notepad.exe ou thorium"\n'
            "}"
        )
        url = "http://localhost:11434/api/generate"
        payload = {"model": "qwen2.5:1.5b", "prompt": prompt, "format": "json", "stream": False, "options": {"temperature": 0.2, "num_predict": 180}}

        cat = "SOFTWARE_UTILITARIO"
        prop = "interação no sistema operacional"
        exe = alvo

        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                dados = json.loads(json.loads(resp.read().decode("utf-8")).get("response", "{}"))
                cat = dados.get("categoria", cat)
                prop = dados.get("proposito", prop)
                exe = dados.get("executavel_sugerido", exe)
        except Exception:
            pass

        # Codificação Role-Value Binding em C^10.000
        v_conceito = self.vsa.encode_compositional(
            action="ONTOLOGY_CONCEPT",
            target=alvo,
            param=cat,
            context=prop
        )

        now = time.time()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO learned_concepts 
                (concept_key, category, functional_purpose, executable_hint, confidence, access_count, vector_bytes, last_interrogated)
                VALUES (?, ?, ?, ?, 0.7, 1, ?, ?)
                ON CONFLICT(concept_key) DO UPDATE SET
                    category = excluded.category,
                    functional_purpose = excluded.functional_purpose,
                    executable_hint = excluded.executable_hint,
                    confidence = MIN(1.0, confidence + 0.1),
                    access_count = access_count + 1,
                    vector_bytes = excluded.vector_bytes,
                    last_interrogated = excluded.last_interrogated;
                """,
                (alvo, cat, prop, exe, v_conceito.tobytes(), now)
            )

        self._cached_aliases[alvo] = exe
        self.vsa.register_cleanup(f"ONTO_{alvo}", v_conceito)
        elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000.0

        logger.info(f"[ONTOLOGIA APRENDIDA]: '{alvo}' -> Categoria: {cat} | Propósito: {prop} ({elapsed_ms:.2f}ms)")
        return {"conceito": alvo, "categoria": cat, "proposito": prop, "executavel": exe, "tempo_ms": elapsed_ms}

    def process_pending_cochilo(self) -> int:
        """Executado durante Cochilos Rápidos (1 a 3 min de ociosidade)."""
        processados = 0
        while self.pending_reflections and processados < 3:
            alvo = self.pending_reflections.pop(0)
            self.run_socratic_self_interrogation(alvo)
            processados += 1
        return processados