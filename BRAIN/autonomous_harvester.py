# ==============================================================================
# BRAINNET v7 - SISTEMA OPERACIONAL COGNITIVO
# MODULO: autonomous_harvester.py
# FUNCAO: Modo Treinamento Contínuo com Autolimitação de Hardware (Xeon/RAM),
#         Busca Multi-Aba em Thorium/Chromium, Rotação Anti-Bloqueio e Poda.
# ==============================================================================

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional
import urllib.parse
import urllib.request

BRAIN_DIR = Path(__file__).resolve().parent

from governance import SystemGovernance
from hyperdimensional import FHRRHyperdimensionalEngine
from browser_bridge import BrowserDeepBridge

logger = logging.getLogger("BRAINNET_Harvester")


class AutonomousHarvester:
    """
    Motor de Aprendizado e Mineração em Background.
    Monitora uso de RAM/CPU em tempo real para escalar paralelismo com segurança.
    """

    __slots__ = (
        "vsa",
        "governance",
        "browser_bridge",
        "db_path",
        "is_active",
        "_worker_thread",
        "harvested_count",
        "max_concurrent_tabs",
        "last_log",
        "trajectory_engine",
        "kernel"
    )

    def __init__(
        self,
        vsa: FHRRHyperdimensionalEngine,
        governance: SystemGovernance,
        browser_bridge: BrowserDeepBridge,
        trajectory_engine: Any = None,
        kernel: Any = None,
        db_path: str = "core1_pdag.db"
    ) -> None:
        self.trajectory_engine = trajectory_engine
        self.kernel = kernel
        self.vsa = vsa
        self.governance = governance
        self.browser_bridge = browser_bridge
        self.db_path = str(BRAIN_DIR / db_path)
        self.is_active = False
        self._worker_thread: Optional[threading.Thread] = None
        self.harvested_count = 0
        self.max_concurrent_tabs = 4
        self.last_log = "Modo treinamento inativo."

    def start(self) -> str:
        if self.is_active:
            return "O modo de treinamento já está ativo em segundo plano."

        self.is_active = True
        self._worker_thread = threading.Thread(target=self._harvest_loop, daemon=True)
        self._worker_thread.start()
        logger.info("[TREINAMENTO]: Modo de colheita autônoma iniciado.")
        return "🚀 **Modo Treinamento Ativado:** Mineração de conceitos e absorção hiperdimensional em background iniciada."

    def stop(self) -> str:
        if not self.is_active:
            return "O modo de treinamento já está inativo."

        self.is_active = False
        logger.info("[TREINAMENTO]: Modo de colheita autônoma interrompido.")
        return f"⏹️ **Modo Treinamento Desativado:** Conhecimentos acumulados salvos. Total de conceitos minerados: {self.harvested_count}."

    def get_status(self) -> Dict[str, Any]:
        ram = self.governance.get_ram_metrics()
        cpu = self.governance.get_cpu_metrics()
        return {
            "ativo": self.is_active,
            "conceitos_minerados": self.harvested_count,
            "ram_usada_mb": ram.used_mb,
            "ram_livre_mb": ram.available_mb,
            "ram_pct": ram.percent_used,
            "cpu_pct": cpu.total_usage_pct,
            "ultimo_log": self.last_log
        }

    def _obter_termos_pendentes(self) -> List[str]:
        """Resgata palavras e conceitos que ainda não têm memória densa consolidada."""
        termos = []
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            # 1. Pega conceitos da Ontologia Epistêmica com baixa confiança
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='learned_concepts';")
            if cur.fetchone():
                try:
                    cur.execute(
                        "SELECT concept_key FROM learned_concepts WHERE confidence < 0.9 "
                        "ORDER BY last_interrogated DESC LIMIT 10;"
                    )
                    termos.extend([r[0] for r in cur.fetchall()])
                except sqlite3.OperationalError:
                    pass

            # 2. Pega intenções do P-DAG que ainda não têm pipeline rico
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pdag_nodes';")
            if cur.fetchone():
                cur.execute("SELECT intent FROM pdag_nodes WHERE is_myelinated = 0 ORDER BY last_active DESC LIMIT 8;")
                for r in cur.fetchall():
                    limpo = re.sub(r"^(?:abra|inicie|pesquise|busque)\s+", "", r[0], flags=re.IGNORECASE).strip()
                    if len(limpo) > 2 and limpo not in termos:
                        termos.append(limpo)

        return termos or ["engenharia de computadores", "sistema operacional cognitivo", "redes neurais recorrentes", "windows 11 ltsc"]

    def _buscar_wikipedia_api(self, termo: str) -> Optional[Dict[str, str]]:
        """Consulta ultrarrápida via API pública da Wikipedia (Zero Bloqueio, <80ms)."""
        url = f"https://pt.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(termo.replace(' ', '_'))}"
        req = urllib.request.Request(url, headers={"User-Agent": "BRAINNET_AI_OS/7.0 (academic_research)"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read().decode("utf-8"))
                extract = data.get("extract", "")
                if len(extract) > 40:
                    return {
                        "url": data.get("content_urls", {}).get("desktop", {}).get("page", url),
                        "title": data.get("title", termo),
                        "text_excerpt": extract
                    }
        except Exception:
            pass
        return None

    def _avaliar_resultado(self, termo: str, texto: str) -> dict:
        """Avalia se o texto responde à intenção da busca. Se não, sugere nova query."""
        prompt = (
            "Você é o Avaliador Crítico da BRAINNET.\n"
            f"O usuário/IA tentou pesquisar sobre: '{termo}'.\n"
            f"O texto extraído da web foi: '{texto[:800]}'.\n"
            "Este texto é útil para explicar o que é o termo, ou é apenas uma página de login, download, erro, ou conteúdo irrelevante?\n"
            "Responda EXCLUSIVAMENTE um JSON no formato:\n"
            '{"util": true ou false, "motivo": "breve justificativa", "nova_query": "uma pergunta melhor para encontrar a explicação"}\n'
            "Se for útil, nova_query deve ser null."
        )
        try:
            import urllib.request
            import json
            payload = {"model": "qwen2.5:1.5b", "prompt": prompt, "format": "json", "stream": False, "options": {"temperature": 0.1}}
            req = urllib.request.Request("http://localhost:11434/api/generate", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                res = json.loads(json.loads(resp.read().decode("utf-8")).get("response", "{}"))
                return res
        except Exception as e:
            logger.debug(f"[CRITIC]: Falha ao avaliar resultado: {e}")
            return {"util": True} # Em caso de falha do LLM, assume que é útil para não perder o dado


    def _buscar_duckduckgo_http(self, termo: str, profundidade: int = 0) -> dict:
        """Busca em background. Se o resultado for inútil, a IA reformula e tenta de novo."""
        import urllib.parse
        import urllib.request
        import re
        
        # Limite de recursão para não entrar em loop infinito
        if profundidade > 2:
            return {}
            
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(termo)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        try:
            with urllib.request.urlopen(req, timeout=7) as r:
                html = r.read().decode("utf-8", errors="ignore")
            snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL)
            if snippets:
                clean = re.sub(r"<[^>]+>", "", snippets[0]).strip()
                if len(clean) > 60:
                    # --- INÍCIO DA AUTO-CORREÇÃO ---
                    avaliacao = self._avaliar_resultado(termo, clean)
                    if avaliacao.get("util") is False and avaliacao.get("nova_query"):
                        nova_q = avaliacao["nova_query"]
                        logger.info(f"[AUTO-CORREÇÃO]: '{termo}' gerou lixo ({avaliacao.get('motivo')}). Reformulando para: '{nova_q}'")
                        # Chama a si mesmo com a nova pergunta
                        resultado_corrigido = self._buscar_duckduckgo_http(nova_q, profundidade + 1)
                        if resultado_corrigido:
                            resultado_corrigido["title"] = f"Busca (Auto-Corrigida): {nova_q}"
                            return resultado_corrigido
                    
                    return {"ok": True, "text_excerpt": clean, "url": url, "title": f"Busca: {termo}"}
        except Exception:
            pass
        return {}

    def harvest_batch(self, terms: List[str], budget: int = 3) -> int:
        """Colhe uma lista explícita de termos. Fallback para HTTP se extensão estiver off."""
        if not terms:
            return 0
        try:
            ram = self.governance.get_ram_metrics()
            if ram.percent_used > 82.0:
                self.last_log = f"RAM {ram.percent_used}% — batch abortado."
                return 0
        except Exception:
            return 0
        absorbed = 0
        for termo in terms[:budget]:
            try:
                dados_pagina = self._buscar_wikipedia_api(termo)
                
                # Fallback 1: Roteamento Cognitivo (Sovereign Idle) - AGORA É O PRIMEIRO
                if not dados_pagina:
                    try:
                        from execution_authority import sovereign_idle_scope
                        with sovereign_idle_scope(idle_threshold_sec=60.0) as token:
                            logger.info(f"[HARVESTER]: Autorizado. Acionando trajetória cognitiva para '{termo}'...")
                            
                            if getattr(self, "trajectory_engine", None) and getattr(self, "kernel", None) and self.kernel.loop:
                                import asyncio
                                import sqlite3
                                coro = self.trajectory_engine.executar_trajetoria_completa(
                                    f"abra o thorium e pesquise sobre {termo}",
                                    is_background=False,
                                    authorization_token=token
                                )
                                fut = asyncio.run_coroutine_threadsafe(coro, self.kernel.loop)
                                res_traj = fut.result(timeout=60)
                                
                                with sqlite3.connect(self.db_path) as conn:
                                    row = conn.execute(
                                        "SELECT summary_text FROM hd_web_memory WHERE query LIKE ? ORDER BY created_at DESC LIMIT 1", 
                                        (f"%{termo}%",)
                                    ).fetchone()
                                    if row and len(row[0]) > 60:
                                        dados_pagina = {"text_excerpt": row[0], "title": f"Pesquisa: {termo}", "url": "trajectory_auto"}
                            else:
                                self.browser_bridge.ensure_preferred_browser()
                                time.sleep(3.0)
                                if self.browser_bridge.extension_connected:
                                    res = self.browser_bridge.deep_search_and_optionally_open_link(termo, open_link_index=1)
                                    if res.get("ok"):
                                        dados_pagina = res.get("active_page")
                    except PermissionError as ex:
                        logger.info(f"[HARVESTER]: Navegador bloqueado ({ex}). Usando apenas HTTP.")
                        
                # Fallback 2: DuckDuckGo (HTTP Puro) - SÓ SE O COGNITIVO FALHAR
                if not dados_pagina:
                    dados_pagina = self._buscar_duckduckgo_http(termo)
                    try:
                        from execution_authority import sovereign_idle_scope
                        with sovereign_idle_scope(idle_threshold_sec=300.0) as token:
                            logger.info(f"[HARVESTER]: Autorizado pela ociosidade. Acionando trajetória cognitiva para '{termo}'...")
                            
                            if getattr(self, "trajectory_engine", None) and getattr(self, "kernel", None) and self.kernel.loop:
                                import asyncio
                                import sqlite3
                                # A IA usa o próprio cérebro para planejar como pesquisar
                                coro = self.trajectory_engine.executar_trajetoria_completa(
                                    f"abra o thorium e pesquise sobre {termo}",
                                    is_background=False,
                                    authorization_token=token
                                )
                                fut = asyncio.run_coroutine_threadsafe(coro, self.kernel.loop)
                                res_traj = fut.result(timeout=60)
                                
                                # Puxa o texto que a trajetória acabou de salvar no banco
                                with sqlite3.connect(self.db_path) as conn:
                                    row = conn.execute(
                                        "SELECT summary_text FROM hd_web_memory WHERE query LIKE ? ORDER BY created_at DESC LIMIT 1", 
                                        (f"%{termo}%",)
                                    ).fetchone()
                                    if row and len(row[0]) > 60:
                                        dados_pagina = {"text_excerpt": row[0], "title": f"Pesquisa: {termo}", "url": "trajectory_auto"}
                            else:
                                # Fallback bruto caso o motor cognitivo esteja offline
                                self.browser_bridge.ensure_preferred_browser()
                                time.sleep(3.0)
                                if self.browser_bridge.extension_connected:
                                    res = self.browser_bridge.deep_search_and_optionally_open_link(termo, open_link_index=1)
                                    if res.get("ok"):
                                        dados_pagina = res.get("active_page")
                    except PermissionError as ex:
                        logger.info(f"[HARVESTER]: Navegador bloqueado ({ex}). Usando apenas HTTP.")

                if dados_pagina and len(dados_pagina.get("text_excerpt", "")) > 60:
                    trecho = dados_pagina["text_excerpt"][:1500]
                    resumo = trecho[:300] + "..."
                    self.browser_bridge.memorize_in_hyperdimension(termo, dados_pagina, resumo)
                    self.harvested_count += 1
                    absorbed += 1
                    self.last_log = f"Absorvido: '{termo}' ({self.harvested_count} total)."
                time.sleep(1.5)
            except Exception as ex:
                logger.debug(f"[HARVESTER]: batch falhou em '{termo}': {ex}")
        return absorbed

    def _harvest_loop(self) -> None:
        """Loop de fundo com controle homeostático de CPU e RAM."""
        while self.is_active:
            try:
                # 1. Checagem Homeostática de Hardware (Friston Feedback)
                ram = self.governance.get_ram_metrics()
                cpu = self.governance.get_cpu_metrics()

                # Se o usuário estiver usando muito a máquina, reduz a marcha e espera
                if ram.percent_used > 82.0 or cpu.total_usage_pct > 80.0:
                    self.last_log = f"Hardware em alta demanda (RAM {ram.percent_used}%, CPU {cpu.total_usage_pct}%). Pausando colheita..."
                    time.sleep(5.0)
                    continue

                termos = self._obter_termos_pendentes()
                for termo in termos:
                    if not self.is_active:
                        break

                    self.last_log = f"Minerando conhecimento sobre: '{termo}'..."

                    # Tentativa 1: API Estruturada Rápida
                    dados_pagina = self._buscar_wikipedia_api(termo)

                    # Tentativa 2: Busca profunda no Thorium via Ponte se a extensão estiver conectada
                    if not dados_pagina and self.browser_bridge.extension_connected:
                        res = self.browser_bridge.deep_search_and_optionally_open_link(termo, open_link_index=1)
                        if res.get("ok"):
                            dados_pagina = res.get("active_page")

                    # Se coletou conteúdo denso, grava na Hiperdimensão C^10.000
                    if dados_pagina and len(dados_pagina.get("text_excerpt", "")) > 60:
                        trecho = dados_pagina["text_excerpt"][:1500]
                        resumo_direto = trecho[:300] + "..."
                        self.browser_bridge.memorize_in_hyperdimension(termo, dados_pagina, resumo_direto)
                        self.harvested_count += 1
                        self.last_log = f"Absorvido em 10.000D: '{termo}' ({self.harvested_count} itens)."

                    time.sleep(3.0)  # Intervalo para não saturar a rede

                # Pequena pausa antes da próxima rodada de termos
                time.sleep(6.0)

            except Exception as e:
                self.last_log = f"Falha temporária no harvester: {e}"
                time.sleep(4.0)