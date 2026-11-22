import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("BRAINNET_UserProfile")

class UserProfileEngine:
    """
    Aprende os padrões de uso do usuário (frequência de apps, sequências de ações)
    para antecipar intenções e economizar processamento.
    """
    __slots__ = ("db_path", "_conn")

    def __init__(self, db_path: str = "core1_pdag.db"):
        # Se for memória, não prefixar com o caminho do arquivo
        if db_path == ":memory:":
            self.db_path = ":memory:"
        else:
            self.db_path = str(Path(__file__).resolve().parent / db_path)
            
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, isolation_level=None)
        self._init_schema()

    def _init_schema(self):
        with self._conn:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_name TEXT NOT NULL,
                    window_title TEXT,
                    started_at REAL NOT NULL,
                    duration_seconds REAL DEFAULT 0,
                    category TEXT
                );
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS user_profile_patterns (
                    context_key TEXT PRIMARY KEY,
                    next_action TEXT NOT NULL,
                    confidence REAL DEFAULT 0.5,
                    sample_count INTEGER DEFAULT 1,
                    last_updated REAL NOT NULL
                );
            """)

    def record_event(self, app_name: str, window_title: str, category: str = "other"):
        """Registra um evento de uso e atualiza a projeção de rotina."""
        now = time.time()
        with self._conn:
            self._conn.execute(
                "INSERT INTO usage_events (app_name, window_title, started_at, category) VALUES (?, ?, ?, ?)",
                (app_name.lower(), window_title[:100], now, category)
            )
        
        # Atualiza o padrão (último app -> próximo app)
        self._update_pattern(app_name)

    def _update_pattern(self, current_app: str):
        """Aprende qual foi a transição (App A -> App B)."""
        try:
            with self._conn:
                # Pega o penúltimo app aberto
                cursor = self._conn.execute(
                    "SELECT app_name FROM usage_events ORDER BY started_at DESC LIMIT 2"
                )
                rows = cursor.fetchall()
                if len(rows) < 2:
                    return
                
                previous_app = rows[1][0]
                context_key = f"after_{previous_app}"
                next_action = current_app

                self._conn.execute("""
                    INSERT INTO user_profile_patterns (context_key, next_action, confidence, sample_count, last_updated)
                    VALUES (?, ?, 0.5, 1, ?)
                    ON CONFLICT(context_key) DO UPDATE SET
                        confidence = (confidence * sample_count + 1.0) / (sample_count + 1),
                        sample_count = sample_count + 1,
                        next_action = CASE 
                            WHEN (confidence * sample_count + 1.0) / (sample_count + 1) > confidence 
                            THEN excluded.next_action 
                            ELSE next_action 
                        END,
                        last_updated = excluded.last_updated;
                """, (context_key, next_action, time.time()))
        except Exception as e:
            logger.error(f"[USER PROFILE]: Falha ao aprender padrão: {e}")

    def predict_next(self, current_app: str) -> Optional[Dict[str, Any]]:
        """Prevê a próxima ação do usuário com base no app atual."""
        app_key = f"after_{current_app.lower().strip()}"
        try:
            cursor = self._conn.execute(
                "SELECT next_action, confidence, sample_count FROM user_profile_patterns WHERE context_key = ?",
                (app_key,)
            )
            row = cursor.fetchone()
            if row and row[1] > 0.6:
                return {"next_action": row[0], "confidence": row[1], "samples": row[2]}
        except Exception:
            pass
        return None

    def get_profile_summary(self) -> str:
        """Resumo do perfil para injeção no prompt."""
        try:
            cursor = self._conn.execute("SELECT app_name, COUNT(*) FROM usage_events GROUP BY app_name ORDER BY COUNT(*) DESC LIMIT 3")
            apps = cursor.fetchall()
            if not apps:
                return "Nenhum padrão consolidado ainda."
            top_apps = ", ".join([f"{app} ({count}x)" for app, count in apps])
            return f"Apps mais usados: {top_apps}"
        except Exception:
            return "Perfil indisponível."
