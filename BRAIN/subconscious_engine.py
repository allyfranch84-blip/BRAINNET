# ==============================================================================
# BRAINNET v8 - MOTOR DE INCONSCIENTE E INTUIÇÃO PRÓ-ATIVA
# MODULO: subconscious_engine.py (Upgrade V8)
# ==============================================================================

import logging
import json
import os
import sqlite3
from pathlib import Path
import threading
import time
from typing import Any, Optional, Dict

logger = logging.getLogger("BRAINNET_Subconscious")
dream_logger = logging.getLogger("BRAINNET_DREAMS")

class SubconsciousEngine:
    """
    Motor de Associações Espontâneas e Intuição Pró-ativa.
    Monitora padrões temporais e projeta sugestões no MasterShell em background.
    """

    __slots__ = (
        "kernel", "_running", "_thread", "_idle_threshold",
        "dreams_processed", "_last_suggested_context"
    )

    def __init__(self, kernel: Any):
        self.kernel = kernel
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._idle_threshold = 120.0  # 2 minutos
        self.dreams_processed = 0
        self._last_suggested_context = ""

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._dream_loop, daemon=True)
        self._thread.start()
        logger.info("[SUBCONSCIOUS]: Inconsciente ativo e atento a padrões.")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info("[SUBCONSCIOUS]: Inconsciente em repouso.")

    def _is_media_playing(self) -> bool:
        try:
            ctx = self.kernel.context_engine.capture_foreground_context()
            proc = ctx.get("process_name", "").lower()
            title = ctx.get("title", "").lower()

            media_procs = ["vlc.exe", "mpv.exe", "wmplayer.exe", "spotify.exe"]
            if any(p in proc for p in media_procs):
                return True

            media_keywords = ["youtube", "netflix", "prime video", "disney+", "twitch", "playing"]
            return any(k in title for k in media_keywords)
        except Exception:
            return False

    def _evaluate_proactive_intuitions(self) -> None:
        """
        Avalia o contexto em primeiro plano. Se houver padrão forte no
        user_profile_engine (> 80% confiança), emite evento discreto para o MasterShell.
        """
        try:
            user_profile = getattr(self.kernel, "user_profile", None)
            bridge = getattr(self.kernel, "bridge", None)
            if not user_profile or not hasattr(self.kernel, "context_engine"):
                return

            ctx = self.kernel.context_engine.capture_foreground_context()
            app_atual = str(ctx.get("process_name", "")).removesuffix(".exe").lower().strip()
            if not app_atual or app_atual in ("desktop", "startmenuexperiencehost", "explorer"):
                return

            prediction = user_profile.predict_next(app_atual)
            if prediction and prediction.get("confidence", 0.0) >= 0.80:
                next_act = prediction["next_action"]
                if next_act != app_atual and next_act != self._last_suggested_context:
                    self._last_suggested_context = next_act
                    msg = f"💡 **Intuição:** Você costuma abrir `{next_act}` após `{app_atual}`. Deseja iniciar?"
                    logger.info(f"[INTUICAO]: Padrão detectado ({prediction['confidence']:.2%}): {app_atual} -> {next_act}")

                    # Empurra evento customizado via bridge do MasterShell
                    window = getattr(bridge, "_window", None)
                    if window:
                        payload = json.dumps({
                            "type": "INTUITION_PROPOSAL",
                            "source_app": app_atual,
                            "suggested_app": next_act,
                            "confidence": prediction["confidence"],
                            "message": msg
                        }, ensure_ascii=False)
                        window.evaluate_js(f"window.dispatchEvent(new CustomEvent('aios:intuition', {{ detail: {payload} }}));")
        except Exception as ex:
            logger.debug(f"[INTUICAO]: Falha na avaliação pró-ativa: {ex}")

    def _dream_loop(self) -> None:
        last_dream_ts = 0.0
        while self._running:
            time.sleep(10.0)
            self._evaluate_proactive_intuitions()

            agora = time.time()
            if agora - last_dream_ts < 300.0:  # Cooldown de 5 minutos
                continue

            last_dream_ts = agora
            try:
                # Pausa a curiosidade e o Physarum durante operações pesadas (ex: escrever livro)
                if getattr(self.kernel, "_heavy_operation_active", False):
                    continue
                    
                tier_fn = getattr(self.kernel, "_check_system_tier", None)
                tier = tier_fn() if callable(tier_fn) else "BUSY"
                if tier != "OPPORTUNITY":
                    continue

                lock = getattr(self.kernel, "_rem_lock", None)
                if lock is not None and lock.locked():
                    continue

                if self._is_media_playing():
                    continue

                self._process_memories()
            except Exception as e:
                logger.error(f"[SUBCONSCIOUS]: Erro no ciclo de sonho: {e}")

    def _process_memories(self) -> None:
        if self.kernel.pdag is None:
            return

        agora = time.time()
        janela = agora - 86400
        transicoes = []
        try:
            with sqlite3.connect(self.kernel.pdag.db_path, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    "SELECT app_name, intent, lambda_obs, ncd, timestamp, steps_json "
                    "FROM transitions WHERE timestamp >= ? AND lambda_obs = 1 AND ncd > 0.05 "
                    "ORDER BY timestamp DESC LIMIT 200",
                    (janela,)
                )
                transicoes = [dict(r) for r in cur.fetchall()]
        except Exception as ex:
            logger.debug(f"[SUBCONSCIOUS]: falha ao ler transitions: {ex}")
            return

        explore_fn = getattr(self.kernel, "_explore_autonomously", None)
        if callable(explore_fn):
            explore_fn()

        if not transicoes:
            return

        # Treinamento do WorldModel
        wm = getattr(self.kernel, "world_model_mlp", None)
        VALID_ACTIONS = {"LOCATE", "TRANSFORM", "WAIT", "ENSURE_APP", "FOCUS_WINDOW", "TYPE", "HOTKEY", "CLICK"}
        if wm is not None:
            for t in transicoes:
                app = str(t.get("app_name", "unknown"))
                intent_raw = str(t.get("intent", ""))
                intent = "CLICK" if intent_raw.upper().startswith("CLICK") else intent_raw.upper()
                if intent not in VALID_ACTIONS:
                    intent = "CLICK"
                ncd = float(t.get("ncd", 0.0))
                state = self.kernel.vsa.text_to_hypervector(f"{app}|{intent_raw}|before")
                next_state = self.kernel.vsa.text_to_hypervector(f"{app}|{intent_raw}|after|{ncd:.4f}")
                try:
                    wm.train_step(state, intent, next_state)
                except Exception:
                    pass

        self.dreams_processed += 1
        msg = f"🔮 SONHO #{self.dreams_processed} | Transições consolidadas: {len(transicoes)}"
        logger.info(f"[SUBCONSCIOUS] {msg}")
        dream_logger.info(msg)
