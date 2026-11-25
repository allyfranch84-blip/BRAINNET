# ==============================================================================
# BRAINNET v7 - SISTEMA OPERACIONAL COGNITIVO
# MODULO: browser_bridge.py
# FUNCAO: Ponte Local HTTP Long-Polling (127.0.0.1:9876) com Extensão Chromium,
#         Abertura Preferencial no Thorium, Pesquisa Multi-Aba com Histórico Real (Ctrl+H),
#         Caixas de Colisão Exatas (Hitboxes) e Ingestão Hiperdimensional FHRR.
# ==============================================================================

from __future__ import annotations

from browser_bridge_transport import BrowserTransport
import json
import logging
import os
from browser_bridge_protocol import valid_token
from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar
import re
import sqlite3
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional
import urllib.parse
import uuid

BRAIN_DIR = Path(__file__).resolve().parent
_research_scope = ContextVar("brainnet_research_scope", default=None)

from hyperdimensional import FHRRHyperdimensionalEngine

logger = logging.getLogger("BRAINNET_BrowserBridge")


class BrowserDeepBridge:
    SCHEMA_WEB_HD = """
    CREATE TABLE IF NOT EXISTS hd_web_memory (
        mem_id TEXT PRIMARY KEY,
        query TEXT NOT NULL,
        url TEXT NOT NULL,
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        summary_text TEXT NOT NULL,
        salience_score REAL NOT NULL,
        access_count INTEGER NOT NULL DEFAULT 1,
        is_consolidated INTEGER NOT NULL DEFAULT 0,
        vector_bytes BLOB NOT NULL,
        created_at REAL NOT NULL,
        last_accessed REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_web_salience ON hd_web_memory (is_consolidated, salience_score);
    """

    def __init__(self, vsa: FHRRHyperdimensionalEngine, resolver: Any, effector: Any, db_path: str = "core1_pdag.db", port: int = 9876) -> None:
        self.vsa = vsa
        self.resolver = resolver
        self.effector = effector
        self.db_path = str(BRAIN_DIR / db_path)
        self.port = port
        self._bridge_token = os.environ.get('BRAINNET_BROWSER_TOKEN', '')

        self._transport = None
        self.last_links_cache: List[Dict[str, Any]] = []
        self.last_page_context: Dict[str, Any] = {}
        self._research_tab_ids = set()

        self._init_db()
        self._start_server()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(self.SCHEMA_WEB_HD)

    def _extract_youtube_transcript(self, url: str) -> str:
        """Extrai as legendas reais do YouTube (XML) sem precisar de API paga."""
        import urllib.request
        import re
        import html
        
        try:
            # 1. Pega o HTML da página
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                html_content = resp.read().decode("utf-8", errors="ignore")
                
            # 2. Encontra a URL da legenda no JSON do YouTube
            match = re.search(r'"captionTracks":\[{"baseUrl":"([^"]+)"', html_content)
            if not match:
                logger.warning("[YOUTUBE]: Nenhuma legenda encontrada (captionTracks vazio).")
                return ""
                
            caption_url = match.group(1).replace("\\u0026", "&")
            
            # 3. Baixa o XML da legenda
            req_xml = urllib.request.Request(caption_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req_xml, timeout=10) as resp_xml:
                xml_content = resp_xml.read().decode("utf-8", errors="ignore")
                
            # 4. Extrai o texto
            texts = re.findall(r'<text[^>]*>(.*?)</text>', xml_content)
            full_text = " ".join(html.unescape(t) for t in texts)
            
            # Tenta extrair o título do vídeo do HTML
            title_match = re.search(r'<title>(.*?)</title>', html_content)
            video_title = title_match.group(1).replace(" - YouTube", "").strip() if title_match else "Vídeo Desconhecido"
            
            final_text = f"[TÍTULO DO VÍDEO: {video_title}]\n\n{full_text}"
            logger.info(f"[YOUTUBE]: Transcrição extraída com sucesso ({len(final_text)} chars).")
            return final_text
        except Exception as ex:
            logger.error(f"[YOUTUBE]: Falha ao extrair transcrição: {ex}")
            return ""

    def _start_server(self) -> None:
        if not valid_token(self._bridge_token):
            logger.warning("[DOM BRIDGE] Configure BRAINNET_BROWSER_TOKEN; extensão indisponível.")
            return
        try:
            self._transport = BrowserTransport(self._bridge_token, self.port)
            self.port = self._transport.port
            logger.info("Ponte DOM Chromium ativa em http://127.0.0.1:%s", self.port)
        except OSError as exc:
            logger.error("Falha ao iniciar ponte DOM na porta %s: %s", self.port, exc)

    def close(self):
        transport = getattr(self, "_transport", None)
        if transport is not None:
            transport.close()

    @property
    def extension_connected(self) -> bool:
        transport = getattr(self, "_transport", None)
        if transport is not None:
            return transport.connected
        return False

    def send_command(self, action: str, timeout: float = 10.0, **kwargs: Any) -> Dict[str, Any]:
        transport = getattr(self, "_transport", None)
        if transport is None:
            return {"ok": False, "error": "Ponte autenticada indisponível.", "dispatch_state": "NOT_DISPATCHED"}
        if action in ("OPEN_TAB_AND_WAIT", "NAVIGATE_ACTIVE_TAB"):
            kwargs.setdefault("extract_options", {"preferred_tags": ["main", "article", "p", "h1"], "max_chars": 3000})
        return transport.send(action, timeout, **kwargs)

    def research_background(self, query: str) -> Dict[str, Any]:
        """Explicit read-only research. Never launch or focus a browser as fallback."""
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 500:
            return {"ok": False, "error": "Consulta inválida"}
        if not self.extension_connected:
            return {"ok": False, "error": "Extensão autenticada indisponível"}
        result = self.send_command("RESEARCH_BACKGROUND", query=query.strip(), timeout=20.0)
        if result.get("ok") is True and not isinstance(result.get("links"), list):
            return {"ok": False, "error": "Resposta de pesquisa inválida"}
        return result

    def ensure_preferred_browser(self, initial_url: Optional[str] = None) -> str:
        ordem = ["thorium", "brave", "chrome"]
        for nav in ordem:
            if self.resolver.is_process_running(nav):
                # Força o foco na janela que já existe para não abrir outra
                for _ in range(5):
                    if self.resolver.find_and_focus_window(nav):
                        break
                    time.sleep(0.5)
                return nav

        for nav in ordem:
            ok = self.resolver.launch_app(nav)
            if ok:
                for _ in range(20):
                    if self.extension_connected:
                        break
                    time.sleep(0.3)
                return nav
        return "thorium"

    @staticmethod
    def _clean_excerpt(text: str) -> str:
        from html.parser import HTMLParser
        class VisibleText(HTMLParser):
            def __init__(self):
                super().__init__()
                self.parts, self.hidden = [], 0
            def handle_starttag(self, tag, attrs):
                if tag in ("script", "style", "nav", "header", "footer", "aside", "noscript"):
                    self.hidden += 1
            def handle_endtag(self, tag):
                if tag in ("script", "style", "nav", "header", "footer", "aside", "noscript"):
                    self.hidden = max(0, self.hidden - 1)
                elif tag in ("p", "h1", "h2", "li", "article", "main", "div", "br"):
                    self.parts.append("\n")
            def handle_data(self, data):
                if not self.hidden:
                    self.parts.append(data)
        text = str(text or "")
        if re.search(r"</?(?:html|body|main|article|p|h[1-6]|div|script|style|nav)\b", text, re.I):
            parser = VisibleText()
            parser.feed(text)
            text = "".join(parser.parts)
        return text.strip()[:6000]

    def _prepare_page_data(self, page_data: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(page_data)
        raw = str(data.get("text_excerpt") or "")
        if len(raw) > 6000 and isinstance(data.get("tab_id"), int) and self.extension_connected:
            preferred = self.send_command("DOM_ACTION", tab_id=data["tab_id"],
                payload={"mode": "EXTRACT", "preferred_tags": ["main", "article", "p", "h1"], "max_chars": 6000}, timeout=6.0)
            if preferred.get("ok") is True and isinstance(preferred.get("text_excerpt"), str) and preferred["text_excerpt"].strip():
                raw = preferred["text_excerpt"]
        data["text_excerpt"] = BrowserDeepBridge._clean_excerpt(raw)
        for key in ("html", "raw_html", "outerHTML", "innerHTML", "body_html"):
            data.pop(key, None)
        return data

    def memorize_in_hyperdimension(self, query: str, page_data: Dict[str, Any], summary: str) -> Dict[str, Any]:
        page_data = BrowserDeepBridge._prepare_page_data(self, page_data)
        summary = BrowserDeepBridge._clean_excerpt(summary)
        url = page_data.get("url", "")
        title = page_data.get("title", "Sem título")
        raw_text = page_data.get("text_excerpt", "")

        palavras = re.findall(r"\w{4,}", raw_text.lower())
        diversidade = len(set(palavras)) / max(len(palavras), 1)
        fator_tam = min(1.0, len(raw_text) / 1200.0)
        salience = round((diversidade * 0.5) + (fator_tam * 0.5), 4)

        categoria = "PESQUISA_GERAL"
        if page_data.get("links"):
            categoria = page_data["links"][0].get("category", "PESQUISA_GERAL")

        v_mem = self.vsa.encode_compositional(
            action="WEB_RESEARCH",
            target=query.lower().strip()[:60],
            param=categoria,
            context=title[:80]
        )
        mem_id = f"WHD_{uuid.uuid4().hex[:10]}"
        now = time.time()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO hd_web_memory
                (mem_id, query, url, title, category, summary_text, salience_score, access_count, is_consolidated, vector_bytes, created_at, last_accessed)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?, ?)
                """,
                (mem_id, query, url, title, categoria, summary, salience, v_mem.tobytes(), now, now)
            )

        self.vsa.register_cleanup(mem_id, v_mem)
        return {"mem_id": mem_id, "salience": salience, "category": categoria}

    @contextmanager
    def research_tab_scope(self):
        owned = set()
        token = _research_scope.set(owned)
        try:
            yield
        finally:
            _research_scope.reset(token)
            if owned:
                try:
                    result = self.close_research_tabs(tab_ids=owned)
                    if result.get("ok") is not True:
                        logger.warning("[CONCEITOS]: Extração concluída; fechamento das abas não confirmado: %s", result)
                except Exception:
                    logger.exception("[CONCEITOS]: Falha ao fechar abas de pesquisa identificadas")

    def _remember_research_tab(self, page):
        tab_id = page.get("tab_id")
        if type(tab_id) is int:
            if not hasattr(self, "_research_tab_ids"):
                self._research_tab_ids = set()
            self._research_tab_ids.add(tab_id)
            scope = _research_scope.get()
            if scope is not None:
                scope.add(tab_id)

    def deep_search_and_optionally_open_link(self, query: str, open_link_index: Optional[int] = None) -> Dict[str, Any]:
        url_google = "https://www.google.com/search?q=" + urllib.parse.quote(query)
        nav_usado = self.ensure_preferred_browser()

        if not self.extension_connected:
            return {"ok": False, "browser": nav_usado, "error": "Extensão desconectada."}

        serp_data = self.send_command("OPEN_TAB_AND_WAIT", url=url_google, timeout=12.0)
        BrowserDeepBridge._remember_research_tab(self, serp_data)
        if not serp_data.get("ok"):
            return serp_data
        serp_data = BrowserDeepBridge._prepare_page_data(self, serp_data)

        self.last_links_cache = serp_data.get("links", [])
        self.last_page_context = serp_data

        visited_link = None
        final_page = serp_data
        if open_link_index is not None and 1 <= open_link_index <= len(self.last_links_cache) and type(serp_data.get("tab_id")) is int:
            alvo = self.last_links_cache[open_link_index - 1]
            visited_link = alvo
            sub_page = self.send_command("NAVIGATE_ACTIVE_TAB", tab_id=serp_data["tab_id"], url=alvo["url"], timeout=12.0)
            BrowserDeepBridge._remember_research_tab(self, sub_page)
            if sub_page.get("ok"):
                final_page = BrowserDeepBridge._prepare_page_data(self, sub_page)
                self.last_page_context = final_page
                if sub_page.get("links"):
                    self.last_links_cache = sub_page["links"]

        return {
            "ok": True,
            "browser": nav_usado,
            "serp_links": serp_data.get("links", []),
            "visited_link": visited_link,
            "active_page": final_page,
            "text_excerpt": final_page.get("text_excerpt", ""),
        }

    def open_cached_nth_link(self, index: int, use_physical_mouse: bool = False) -> Dict[str, Any]:
        if not self.extension_connected:
            return {"ok": False, "error": "Extensão desconectada."}

        current = self.send_command("DOM_ACTION", payload={"mode": "EXTRACT"}, timeout=6.0)
        if current.get("ok") and current.get("links"):
            self.last_links_cache = current["links"]

        if not self.last_links_cache or index < 1 or index > len(self.last_links_cache):
            return {"ok": False, "error": f"Link #{index} fora do alcance ({len(self.last_links_cache)} links mapeados)."}

        alvo = self.last_links_cache[index - 1]
        hb = alvo.get("hitbox")

        if use_physical_mouse and hb:
            self.effector.mouse_move(hb["screen_x"], hb["screen_y"])
            self.effector.mouse_click("left", 1)
            time.sleep(1.5)
            page = self.send_command("DOM_ACTION", payload={"mode": "EXTRACT"}, timeout=8.0)
        else:
            page = self.send_command("NAVIGATE_ACTIVE_TAB", url=alvo["url"], timeout=12.0)

        self.last_page_context = page
        return {"ok": True, "chosen_link": alvo, "page": page}

    def control_video_or_click_hitbox(self, action_mode: str = "toggle", physical_click: bool = False, button_text: str = "") -> Dict[str, Any]:
        if not self.extension_connected:
            import ctypes
            ctypes.windll.user32.keybd_event(0xB3, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0xB3, 0, 2, 0)
            return {"ok": True, "method": "WIN32_MEDIA_KEY_FALLBACK"}

        if button_text:
            res = self.send_command("DOM_ACTION", payload={"mode": "CLICK_ELEMENT", "target_text": button_text, "only_coords": physical_click})
            if res.get("ok") and physical_click and res.get("hitbox"):
                hb = res["hitbox"]
                self.effector.mouse_move(hb["screen_x"], hb["screen_y"])
                self.effector.mouse_click("left", 1)
                res["method"] = "PHYSICAL_MOUSE_HITBOX"
            return res

        res = self.send_command("DOM_ACTION", payload={"mode": "VIDEO_CONTROL", "video_action": action_mode})
        if res.get("ok") and physical_click and res.get("hitbox"):
            hb = res["hitbox"]
            self.effector.mouse_move(hb["screen_x"], hb["screen_y"])
        return res

    def close_research_tabs(self, tab_ids=None) -> Dict[str, Any]:
        tab_ids = sorted(self._research_tab_ids if tab_ids is None else self._research_tab_ids.intersection(tab_ids))
        if not tab_ids or not self.extension_connected:
            return {"ok": False, "error": "Sem IDs de pesquisa confirmados ou extensao desconectada"}
        result = self.send_command("CLOSE_TABS", tab_ids=tab_ids, timeout=5.0)
        if result.get("ok") is True and result.get("closed_count") == len(tab_ids):
            self._research_tab_ids.difference_update(tab_ids)
            return {"ok": True, "closed_count": len(tab_ids)}
        logger.warning("[LIMPEZA DE ABAS]: Sem confirmacao; nenhum Ctrl+W sera enviado")
        return {"ok": False, "error": "Extensao nao confirmou fechamento dos IDs de pesquisa"}

    def _close_research_tabs_keyboard(self, tab_ids):
        """Close only a freshly identified active research tab; never the last tab."""
        remaining, closed = set(tab_ids), set()
        try:
            for _ in range(len(remaining)):
                if not self.extension_connected:
                    break
                hwnd_before = self.resolver.foreground_app_hwnd("thorium")
                if not hwnd_before:
                    break
                state = self.send_command("TAB_STATE", timeout=2.0)
                tabs = state.get("tabs", [])
                if (state.get("ok") is not True or state.get("focused") is not True
                        or type(state.get("window_id")) is not int
                        or not isinstance(tabs, list) or len(tabs) <= 1):
                    break
                ids = {tab.get("id") for tab in tabs}
                active = [tab for tab in tabs if tab.get("active") is True]
                if (len(ids) != len(tabs) or not all(type(i) is int for i in ids) or len(active) != 1
                        or any(tab.get("window_id") != state.get("window_id") for tab in tabs)
                        or active[0]["id"] not in remaining):
                    break
                if self.resolver.foreground_app_hwnd("thorium") != hwnd_before:
                    break
                target = active[0]["id"]
                if self.effector.send_hotkey(["ctrl", "w"]) is not True:
                    break
                after = self.send_command("TAB_STATE", timeout=2.0)
                after_ids = {tab.get("id") for tab in after.get("tabs", [])}
                if (after.get("ok") is not True or after.get("window_id") != state.get("window_id")
                        or after_ids != ids - {target}):
                    logger.warning("[LIMPEZA DE ABAS]: Ctrl+W sem confirmação; limpeza interrompida")
                    break
                closed.add(target)
                remaining.remove(target)
                self._research_tab_ids.discard(target)
        except Exception:
            logger.exception("[LIMPEZA DE ABAS]: Fallback interrompido; preservar abas restantes")
        if remaining:
            logger.warning("[LIMPEZA DE ABAS]: Sem foco Thorium, IDs/contagem seguros ou confirmação; abas preservadas")
        return {"ok": not remaining, "closed_count": len(closed)}

    def deep_multi_tab_research(self, query: str) -> Dict[str, Any]:
        nav = self.ensure_preferred_browser()
        if not self.extension_connected:
            return {"ok": False, "error": "Extensão do navegador desconectada. Ative-a no Thorium."}

        abas_para_fechar = []

        # 1. Abre aba de busca no Google (registrado no histórico nativo Ctrl+H)
        url_google = "https://www.google.com/search?q=" + urllib.parse.quote(query)
        serp = self.send_command("OPEN_TAB_AND_WAIT", url=url_google, timeout=12.0)
        serp = BrowserDeepBridge._prepare_page_data(self, serp)
        if serp.get("tab_id"):
            abas_para_fechar.append(serp["tab_id"])
            self._research_tab_ids.add(serp["tab_id"])
        links = serp.get("links", [])[:3]

        textos = [f"=== GOOGLE: {query.upper()} ===\n" + serp.get("text_excerpt", "")[:1200]]
        paginas = [serp.get("title", "Busca Google")]

        # 2. Abre aba da Wikipedia (registrado no histórico nativo Ctrl+H)
        url_wiki = f"https://pt.wikipedia.org/wiki/{urllib.parse.quote(query.replace(' ', '_'))}"
        wiki_res = self.send_command("OPEN_TAB_AND_WAIT", url=url_wiki, timeout=10.0)
        wiki_res = BrowserDeepBridge._prepare_page_data(self, wiki_res)
        if wiki_res.get("tab_id"):
            abas_para_fechar.append(wiki_res["tab_id"])
            self._research_tab_ids.add(wiki_res["tab_id"])
        if wiki_res.get("ok") and len(wiki_res.get("text_excerpt", "")) > 100:
            textos.append(f"\n=== WIKIPEDIA ===\n" + wiki_res.get("text_excerpt", "")[:1500])
            paginas.append(wiki_res.get("title", "Wikipedia"))

        # 3. Abre abas reais para os 3 links orgânicos (registrados no histórico nativo Ctrl+H)
        for idx, l in enumerate(links):
            sub = self.send_command("OPEN_TAB_AND_WAIT", url=l["url"], timeout=10.0)
            sub = BrowserDeepBridge._prepare_page_data(self, sub)
            if sub.get("tab_id"):
                abas_para_fechar.append(sub["tab_id"])
                self._research_tab_ids.add(sub["tab_id"])
            if sub.get("ok") and len(sub.get("text_excerpt", "")) > 80:
                textos.append(f"\n=== LINK [{idx+1}]: {l['title']} ===\n" + sub.get("text_excerpt", "")[:1200])
                paginas.append(l["title"])

        texto_consolidado = "\n".join(textos)

        # 4. Ingestão confirmada na Hiperdimensão C^10.000
        mem_info = self.memorize_in_hyperdimension(
            query=query,
            page_data={"url": url_google, "title": f"Pesquisa: {query}", "text_excerpt": texto_consolidado, "links": links},
            summary=texto_consolidado[:600]
        )

        # 5. DWELL-TIME CALIBRADO E FECHAMENTO FACTUAL MULTI-CAMADA
        def _fechar_abas_async():
            # Aguarda 4.5 segundos para garantir que o operador veja o conteúdo e a absorção ocorra
            time.sleep(4.5)
            sucesso_fechamento = False
            
            # Tentativa 1: Fechamento via API da Extensão Chromium
            research_tabs = list(dict.fromkeys(abas_para_fechar))
            if self.extension_connected and research_tabs:
                try:
                    res = self.send_command("CLOSE_TABS", tab_ids=research_tabs, timeout=2.0)
                    if res.get("ok") is True and res.get("closed_count") == len(research_tabs):
                        sucesso_fechamento = True
                        getattr(self, "_research_tab_ids", set()).difference_update(research_tabs)
                        logger.info(f"[LIMPEZA DE ABAS]: {len(research_tabs)} abas fechadas via Extensão.")
                except Exception as e:
                    logger.warning(f"Extensão falhou ao fechar abas: {e}")

            # Sem confirmacao dos IDs de pesquisa, preservar todas as abas restantes.
            if not sucesso_fechamento and research_tabs:
                fallback = getattr(self, "_close_research_tabs_keyboard", None)
                if fallback is not None:
                    fallback(research_tabs)
                else:
                    logger.warning("[LIMPEZA DE ABAS]: Sem identificação segura; abas preservadas")

        threading.Thread(target=_fechar_abas_async, daemon=True).start()

        return {
            "ok": True,
            "browser": nav,
            "query": query,
            "mem_id": mem_info["mem_id"],
            "salience": mem_info["salience"],
            "paginas_visitadas": paginas,
            "texto_total": texto_consolidado
        }
