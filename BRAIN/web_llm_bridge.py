"""WebLLM bridge: automação verificada de LLMs via navegador.

Toda entrada (click/type/hotkey) passa por CausalTrajectoryEngine.execute_subgoal,
o que garante require_action_allowed + CyberneticVerifier.measure_collapse (NCD/PID/HWND).
A aba criada é registrada em _web_llm_tab_ids e só ela é fechada ao final."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import sqlite3
from contextlib import closing
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("BRAINNET_WebLLM")


class WebLLMBridge:
    """Automação verificada de web LLMs (Gemini, ChatGPT)."""

    __slots__ = ("browser", "trajectory", "vision", "kernel", "resolver",
                 "_web_llm_tab_ids", "_rate", "_lock")

    TARGETS = {
        "gemini":  {"url": "https://gemini.google.com/app", "hints": ("Pergunte", "Ask", "Mensagem")},
        "chatgpt": {"url": "https://chatgpt.com/", "hints": ("Message", "Pergunte", "Ask")},
    }
    RATE_LIMIT = 5
    COOLDOWN_SEC = 12

    def __init__(self, browser, trajectory, vision, kernel):
        self.browser = browser
        self.trajectory = trajectory
        self.vision = vision
        self.kernel = kernel
        self.resolver = trajectory.resolver
        self._web_llm_tab_ids: set[int] = set()
        self._rate = {"count": 0, "reset_at": 0.0}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Rate limit / jitter                                                 #
    # ------------------------------------------------------------------ #
    def _can_proceed(self) -> bool:
        now = time.time()
        with self._lock:
            if now >= self._rate["reset_at"]:
                self._rate["count"] = 0
                self._rate["reset_at"] = now + 60.0
            if self._rate["count"] >= self.RATE_LIMIT:
                logger.warning("[WEB_LLM]: rate limit atingido")
                return False
            self._rate["count"] += 1
            return True

    @staticmethod
    def _jitter(lo: float = 2.0, hi: float = 5.0) -> None:
        time.sleep(random.uniform(lo, hi))

    # ------------------------------------------------------------------ #
    # Sub-rotinas                                                          #
    # ------------------------------------------------------------------ #
    def _snapshot_dom(self, tab_id: int) -> str:
        try:
            r = self.browser.send_command("DOM_ACTION", tab_id=tab_id,
                payload={"mode": "EXTRACT", "preferred_tags": ["main","article","div","p"],
                         "max_chars": 20000}, timeout=8.0)
            return (r.get("text_excerpt") or "") if r.get("ok") else ""
        except Exception as ex:
            logger.debug(f"[WEB_LLM]: snapshot falhou: {ex}")
            return ""

    def _find_input_field(self, target: str) -> Optional[tuple[int, int]]:
        try:
            for hint in self.TARGETS[target]["hints"]:
                point = self.vision.encontrar_elemento_por_texto(hint)
                if point:
                    return point
        except Exception as ex:
            logger.warning(f"[WEB_LLM]: OCR falhou: {ex}")
        return None

    def _focused_on(self, target: str) -> bool:
        try:
            return self.resolver.foreground_app_hwnd(target) is not None
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # Ação via execute_subgoal (CyberneticVerifier obrigatório)           #
    # ------------------------------------------------------------------ #
    def _run_subgoal_sync(self, intent: str, coro_factory, timeout: float = 30.0):
        """Executa execute_subgoal respeitando o event loop existente."""
        loop = getattr(self.kernel, "loop", None)
        coro = coro_factory()
        try:
            if loop and loop.is_running():
                fut = asyncio.run_coroutine_threadsafe(coro, loop)
                return fut.result(timeout=timeout)
            return asyncio.run(coro)
        except Exception:
            coro.close()
            raise

    def _do_click(self, target: str, x: int, y: int) -> Dict[str, Any]:
        async def action():
            return await self.trajectory._executar_passo_individual(
                {"acao": "CLICK", "x": int(x), "y": int(y), "button": "left", "count": 1})

        async def _run():
            return await self.trajectory.execute_subgoal(
                intent_hash=f"web_llm:{target}:focus",
                action_fn=action,
                timeout_sec=5.0,
                contract={"action": "CLICK", "expects_new_pid": False,
                          "min_ncd": 0.02, "expected_app": target},
            )
        return self._run_subgoal_sync(f"web_llm:{target}:focus", _run)

    def _do_type(self, target: str, text: str) -> Dict[str, Any]:
        async def action():
            return await self.trajectory._executar_passo_individual(
                {"acao": "TYPE", "text": text})

        async def _run():
            return await self.trajectory.execute_subgoal(
                intent_hash=f"web_llm:{target}:type",
                action_fn=action,
                timeout_sec=8.0,
                contract={"action": "TYPE", "expects_new_pid": False,
                          "min_ncd": 0.02, "expected_app": target},
            )
        return self._run_subgoal_sync(f"web_llm:{target}:type", _run)

    def _do_enter(self, target: str) -> Dict[str, Any]:
        async def action():
            return await self.trajectory._executar_passo_individual(
                {"acao": "HOTKEY", "keys": ["enter"]})

        async def _run():
            return await self.trajectory.execute_subgoal(
                intent_hash=f"web_llm:{target}:submit",
                action_fn=action,
                timeout_sec=5.0,
                contract={"action": "HOTKEY", "expects_new_pid": False,
                          "min_ncd": 0.01, "expected_app": target},
            )
        return self._run_subgoal_sync(f"web_llm:{target}:submit", _run)

    # ------------------------------------------------------------------ #
    # Extração por delta (só a resposta, não o DOM inteiro)               #
    # ------------------------------------------------------------------ #
    def _extract_response(self, tab_id: int, pre_dom: str, prompt: str,
                          deadline_sec: float = 90.0) -> Optional[str]:
        last_text, stable_count = "", 0
        end = time.time() + deadline_sec
        anchor = prompt[:100].strip()
        while time.time() < end:
            time.sleep(3.0)
            cur = self._snapshot_dom(tab_id)
            if not cur or len(cur) <= len(pre_dom):
                continue
            if cur == last_text:
                stable_count += 1
                if stable_count >= 2 and len(cur) > 200:
                    return self._delta(pre_dom, cur, anchor)
            else:
                stable_count = 0
                last_text = cur
        return self._delta(pre_dom, last_text, anchor) if last_text else None

    @staticmethod
    def _delta(pre: str, post: str, anchor: str) -> str:
        # Tentativa 1: cortar no último aparecimento do prompt
        if anchor:
            idx = post.rfind(anchor)
            if idx >= 0:
                tail = post[idx + len(anchor):].strip()
                if len(tail) > 40:
                    return tail
        # Fallback: delta puro
        if len(post) > len(pre):
            tail = post[len(pre):].strip()
            if len(tail) > 40:
                return tail
        return ""

    # ------------------------------------------------------------------ #
    # Ingestão nas camadas de memória (mesma do 14B)                      #
    # ------------------------------------------------------------------ #
    def _ingest(self, prompt: str, response: str, target: str) -> Dict[str, Any]:
        topic_id = f"web_llm_{int(time.time())}"
        t0 = time.perf_counter_ns()
        v_composite = None
        try:
            v_composite = self.kernel.vsa.bind(
                self.kernel.vsa.text_to_hypervector(prompt),
                self.kernel.vsa.text_to_hypervector(response[:2000]))
            self.kernel.vsa.register_cleanup(f"WEB_LLM_{topic_id}", v_composite)
        except Exception as ex:
            logger.warning(f"[WEB_LLM]: FHRR falhou: {ex}")

        try:
            db = str(Path(__file__).resolve().parent / "long_context.db")
            with closing(sqlite3.connect(db, timeout=5)) as conn:
                conn.execute("""INSERT OR REPLACE INTO long_context_state
                    (doc_id, source_type, source_path, total_chunks, current_chunk,
                     cumulative_summary, status, created_at, updated_at)
                    VALUES (?, 'web_llm', ?, 1, 1, ?, 'DONE', ?, ?)""",
                    (topic_id, f"{target}:{prompt[:100]}", response, time.time(), time.time()))
                conn.commit()
        except Exception as ex:
            logger.warning(f"[WEB_LLM]: long_context falhou: {ex}")

        if v_composite is not None:
            try:
                with closing(sqlite3.connect(self.kernel.pdag.db_path, timeout=5)) as conn:
                    conn.execute("""INSERT OR REPLACE INTO hd_web_memory
                        (mem_id, query, url, title, category, summary_text,
                         salience_score, access_count, is_consolidated,
                         vector_bytes, created_at, last_accessed)
                        VALUES (?, ?, ?, ?, 'WEB_LLM_AUTONOMOUS', ?, 0.95, 1, 1, ?, ?, ?)""",
                        (f"WLL_{topic_id}", prompt, f"web_llm:{target}",
                         f"{target.title()}: {prompt[:80]}", response,
                         v_composite.tobytes(), time.time(), time.time()))
                    conn.commit()
            except Exception as ex:
                logger.warning(f"[WEB_LLM]: hd_web_memory falhou: {ex}")

        try:
            path = Path(__file__).resolve().parent / "dataset_web_llm.jsonl"
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"prompt": prompt, "response": response,
                                    "source": target, "timestamp": time.time()},
                                   ensure_ascii=False) + "\n")
        except Exception as ex:
            logger.warning(f"[WEB_LLM]: dataset falhou: {ex}")

        return {"topic_id": topic_id,
                "ingestion_ms": (time.perf_counter_ns() - t0) / 1e6}

    # ------------------------------------------------------------------ #
    # Entrada pública                                                      #
    # ------------------------------------------------------------------ #
    def ask(self, prompt: str, target: str = "gemini") -> Dict[str, Any]:
        target = target.lower().strip()
        if target not in self.TARGETS:
            return {"ok": False, "error": f"Target inválido: {target}"}
        if not prompt or len(prompt) > 8000:
            return {"ok": False, "error": "Prompt vazio ou excessivo (max 8000)"}
        if not self._can_proceed():
            return {"ok": False, "error": "Rate limit 5/min atingido"}
        if not self.browser.extension_connected:
            return {"ok": False, "error": "Extensão do navegador desconectada"}

        url = self.TARGETS[target]["url"]
        serp = self.browser.send_command("OPEN_TAB_AND_WAIT", url=url, timeout=20.0)
        tab_id = serp.get("tab_id")
        if not serp.get("ok") or not isinstance(tab_id, int):
            return {"ok": False, "error": f"Falha ao abrir {target}: {serp.get('error')}"}

        self._web_llm_tab_ids.add(tab_id)
        try:
            self._jitter(1.5, 2.5)
            if not self._focused_on(target):
                # tenta focar a janela; se falhar, aborta
                try:
                    self.resolver.find_and_focus_window(target)
                except Exception:
                    pass
                self._jitter(0.5, 1.0)
                if not self._focused_on(target):
                    return {"ok": False, "error": "Aba do web LLM não está em foco"}

            pre_dom = self._snapshot_dom(tab_id)
            point = self._find_input_field(target)
            if not point:
                return {"ok": False, "error": "Input não localizado por OCR"}

            click_fb = self._do_click(target, point[0], point[1])
            if click_fb.get("lambda_obs") != 1:
                return {"ok": False, "error": f"Click não confirmado: {click_fb.get('failure_reason')}"}
            self._jitter(0.4, 1.0)

            type_fb = self._do_type(target, prompt)
            if type_fb.get("lambda_obs") != 1:
                return {"ok": False, "error": f"Digitação não confirmada: {type_fb.get('failure_reason')}"}
            self._jitter(0.5, 1.2)

            enter_fb = self._do_enter(target)
            if enter_fb.get("lambda_obs") != 1:
                return {"ok": False, "error": f"Enter não confirmado: {enter_fb.get('failure_reason')}"}

            response = self._extract_response(tab_id, pre_dom, prompt, deadline_sec=90.0)
            if not response:
                return {"ok": False, "error": "Resposta vazia ou timeout (90s)"}

            ingestion = self._ingest(prompt, response, target)
            return {"ok": True, "response": response, "target": target,
                    "tab_id": tab_id, "ingestion": ingestion}
        finally:
            if tab_id in self._web_llm_tab_ids:
                try:
                    self.browser.send_command("CLOSE_TABS", tab_ids=[tab_id], timeout=5.0)
                except Exception:
                    pass
                self._web_llm_tab_ids.discard(tab_id)
