# ==============================================================================
# BRAINNET v7 - SISTEMA OPERACIONAL COGNITIVO
# MODULO: BRAINNET.PY (O MAESTRO E INTEGRATION ENGINE UNIFICADO)
# FUNCAO: Núcleo Factual Grounded, Teoria da Mente, Gating Go/No-Go,
#         Metas Compostas (HTN), Mielinização Zero-LLM e P-DAG SQLite WAL.
# ==============================================================================

from __future__ import annotations

import ast
import asyncio
from concept_cortex import ConceptCortex
from error_blackbox import ErrorBlackBoxEngine
from ui_tars_protocol import UIProtocolController
from collections import deque
import ctypes
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import threading
from contextvars import ContextVar
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import urllib.parse
import urllib.request
import uuid
import winreg
import numpy as np
import webview

sys.setrecursionlimit(5000)

from context_capture import ContextCapture
from governance import SystemGovernance
from router import AdaptiveInferenceRouter, RouteDecision
from hyperdimensional import FHRRHyperdimensionalEngine
from hdc_projector import HDCProjector
from pdag_engine import MyelinatedPDAGEngine
from perception_eye import PerceptionEye
from effector import Effector
from actuator_bridge import ActuatorBridge, CommandPriority
from sandbox_mirror import SandboxMirror
from rem_sleep_engine import REMSleepEngine
from skill_loader import DynamicSkillLoader
from audio_ear import AudioEar
from vision_eye import RealVisionEngine
from speech_voice import SpeechVoiceEngine
from world_model_engine import WorldModelEngine
from shadow_simulator import ShadowSimulator
from error_blackbox import ErrorBlackBoxEngine
from dual_tier_arbitration import DualTierArbitrator
from causal_trajectory import CausalTrajectoryEngine
from proprioception_gate import DigitalProprioceptionGate
from theory_of_mind import MentalizingJudgment, MotorGateState, TheoryOfMindEngine
from liquid_reservoir import PalimpsestLiquidReservoir
from browser_bridge import BrowserDeepBridge
from epistemic_ontology import EpistemicOntologyEngine
from autonomous_harvester import AutonomousHarvester
from metacognition import MetacognitionEngine
from execution_authority import command_authority, current_authorization
from assistant_prompts import OLLAMA_GENERATE_URL

# ------------------------------------------------------------------------------
# CONFIGURAÇÕES E TELEMETRIA
# ------------------------------------------------------------------------------

CONFIG_FILE = Path(__file__).resolve().parent / "brainnet_config.json"

# Limites aplicados ao caminho conversacional; não concedem autorização.
_EFFORT_LIMITS = {
    'FAST': {'num_predict': 200, 'num_ctx': 2048, 'timeout': 15, 'visual_steps': 3},
    'BALANCED': {'num_predict': 450, 'num_ctx': 4096, 'timeout': 30, 'visual_steps': 8},
    'DEEP': {'num_predict': 800, 'num_ctx': 8192, 'timeout': 60, 'visual_steps': 12},
}
from contextvars import ContextVar as _EffortContextVar
_effort_for_command = _EffortContextVar('brainnet_effort', default='BALANCED')
_conversation_for_command = _EffortContextVar('brainnet_conversation', default=None)
_conversation_finish_reason = _EffortContextVar('brainnet_conversation_finish_reason', default=None)

def _effective_effort(mode, text):
    if mode not in ('FAST', 'BALANCED', 'DEEP', 'AUTO'):
        mode = 'AUTO'
    if mode == 'AUTO':
        return 'DEEP' if len(text) > 400 else ('FAST' if len(text) < 80 else 'BALANCED')
    return mode

def _load_app_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"theme": "dark", "shortcuts": []}

def _save_app_config(data: dict) -> None:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d [%(levelname)s] [Brainnet] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("BRAINNET")

ALLOWED_THEMES = ("dark", "light", "aurora", "natureza", "biomecanico", "cerebro", "skynet")
NATIVE_SKILLS = [
    {
        "id": "shortcuts",
        "name": "Atalhos Locais",
        "icon": "file",
        "description": "Cadastre caminhos de executáveis Windows (.exe) para a BRAINNET abrir na hora.",
        "folder": "Atalhos Locais (.exe)",
    },
    {
        "id": "web_search",
        "name": "Pesquisa Web Autônoma",
        "icon": "search",
        "description": "Varreduras automáticas na internet gerenciadas pelo Kernel.",
        "folder": None,
    },
]

class MemoryRingLogHandler(logging.Handler):
    def __init__(self, maxlen: int = 400) -> None:
        super().__init__()
        self.records = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.records.append({"level": record.levelname, "core": "Core1", "msg": msg})
        except Exception:
            self.handleError(record)

ring_handler = MemoryRingLogHandler(maxlen=400)
ring_handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(ring_handler)


# ------------------------------------------------------------------------------
# KERNEL PRINCIPAL (O ORGANISMO VIVO)
# ------------------------------------------------------------------------------

_situation_task = ContextVar('situation_task', default=None)

class BrainnetKernel:
    def record_situation_event(self, task_id, event, *, intent=None, verified=False):
        """Optional derived memory; it never approves actions or verifies goals."""
        if self.situation_memory is None or self.situation_index is None:
            return
        from situation_memory import Observation
        from situation_fhrr_index import IndexedSnapshot
        now = time.time()
        fields = {'state': event}
        if intent:
            fields['intent'] = str(intent)[:80]
        snapshot_id = uuid.uuid4().hex
        with self._situation_lock:
            self.situation_memory.update(Observation(snapshot_id, fields, 'kernel', now, now + 300,
                                                       task_id=task_id, verified=verified))
            self.situation_index.put(IndexedSnapshot(task_id, snapshot_id, now, 'kernel', now + 300,
                                                      'VERIFIED' if verified else 'UNVERIFIED', fields))

    def read_situation_evidence(self, task_id):
        """Read current task evidence only; never a substitute for current UI state."""
        if self.situation_memory is None or self.situation_index is None:
            return None
        with self._situation_lock:
            snapshot = self.router.read_situation(self.situation_memory, task_id)
            matches = self.situation_index.search(task_id, 'state task_started', limit=3)
            valid_ids = {o.key for o in snapshot.observations}
            return {'snapshot': snapshot, 'matches': [m for m in matches if m['snapshot'].snapshot_id in valid_ids],
                    'execution_authorized': False}

    def __init__(self) -> None:
        self.perceptual_present = None
        self.minimal_mode = os.getenv('BRAINNET_MINIMAL') == '1'
        self.rem_maintenance_enabled = False  # Requires separate review and authorization.
        if self.minimal_mode:
            # Existing read-only and actuator components only; no database or REM.
            self.context_engine = ContextCapture()
            self.vsa = FHRRHyperdimensionalEngine(dimension=10_000)
            self.eye = PerceptionEye(vsa_engine=self.vsa)
            self.effector = Effector()
            self.bridge = ActuatorBridge(effector_instance=self.effector, perception_instance=self.eye, max_workers=1)
            self.pdag = None
            self.rem_engine = None
            self.ontology = None
            self.router = None
            self.situation_memory = None
            self.situation_index = None
            self.skill_registry = {}
            self.ultimo_toque_ai = time.time()
            self.esta_dormindo = False
            self.is_running = False
            self.loop = None
            self._adaptive_observer = None
            self._runtime_telemetry = None
            self._runtime_task_lock = threading.RLock()
            self._runtime_tasks = {}
            self._runtime_recent_tasks = deque(maxlen=32)
            logger.info("Perfil mínimo: REM, P-DAG, memória persistente e inferência não inicializados.")
            return
        logger.info("Inicializando subsistemas cognitivos do Brainnet Kernel...")

        self.context_engine = ContextCapture()
        self.governance = SystemGovernance()
        self.vsa = FHRRHyperdimensionalEngine(dimension=10_000)
        self.situation_memory = None
        self.situation_index = None
        self._situation_lock = threading.RLock()
        if os.getenv('BRAINNET_SITUATION_FHRR') == '1':
            from situation_memory import SituationMemory
            from situation_fhrr_index import SituationFHRRIndex
            self.situation_memory = SituationMemory(enabled=True, max_bytes=65536)
            self.situation_index = SituationFHRRIndex(self.vsa, max_bytes=1048576)
        self.router = AdaptiveInferenceRouter(vsa_engine=self.vsa)
        self.hdc = HDCProjector(dimension=10_000)
        
        if not self.hdc.load_model():
            self.hdc.train_one_shot("SISTEMA_ARQUIVOS", "crie um arquivo texto e salve na pasta")
            self.hdc.train_one_shot("CONTROLE_JANELA", "abra o menu iniciar e maximize a janela")
            self.hdc.save_model()

        self.pdag = MyelinatedPDAGEngine(db_path="core1_pdag.db")
        self.eye = PerceptionEye(vsa_engine=self.vsa)
        self.effector = Effector()
        self.bridge = ActuatorBridge(effector_instance=self.effector, perception_instance=self.eye, max_workers=2)
        self.sandbox = SandboxMirror(max_ram_mb=256, timeout_sec=5.0)

        self.vision = RealVisionEngine()
        self.voice = SpeechVoiceEngine()

        base_dir = Path(__file__).resolve().parent
        hab_dir = base_dir.parent / "HABILIDADES"
        if not hab_dir.exists():
            hab_dir.mkdir(parents=True, exist_ok=True)

        self.rem_engine = REMSleepEngine(db_path="core1_pdag.db", skills_dir=hab_dir, idle_threshold_sec=900.0, pdag_engine=self.pdag)
        
        self.world_model = WorldModelEngine(self.context_engine, self.governance, self.eye, self.vsa, self.pdag)
        self.shadow = ShadowSimulator(self.context_engine, self.eye, self.vsa, self.pdag)
        self.blackbox = ErrorBlackBoxEngine(self.context_engine, self.vsa, self.pdag, self.sandbox)
        self.arbitrator = DualTierArbitrator(self.vsa, self.pdag, self.blackbox, consensus_threshold=0.70)
        
        # 1. Trajetória Causal Factual
        from cybernetic_verifier import CyberneticVerifier
        from PIL import ImageGrab
        def _capture_roi(bbox=None):
            img = ImageGrab.grab(bbox=bbox) if bbox else ImageGrab.grab(all_screens=True)
            return img.tobytes()
        self.verifier = CyberneticVerifier(capture_fn=_capture_roi)
        self.metacognition = MetacognitionEngine()
        self.trajectory_engine = CausalTrajectoryEngine(self.context_engine, self.eye, self.effector, self.bridge, self.vsa, self.pdag, self.shadow, self.verifier)
        # --- V9.5 FIX: Instanciando Cortex e Blackbox ---

        self.concept_cortex = ConceptCortex(hdc=self.vsa, resolver=self.trajectory_engine.resolver, db_path="core1_pdag.db", dim=self.vsa.dim)
        self.trajectory_engine.concept_cortex = self.concept_cortex
        self.trajectory_engine.blackbox = self.blackbox
        self.blackbox.concept_cortex = self.concept_cortex
                # V9.5-WIRING: Conecta Cortex e Blackbox ao Motor (exigido para cliques e UI-TARS)
        self.trajectory_engine.concept_cortex = getattr(self, 'concept_cortex', None)
        self.trajectory_engine.blackbox = getattr(self, 'blackbox', None)

        self.ui_protocol = UIProtocolController(self.vision, self.trajectory_engine, self.context_engine)
        
        # 2. Ponte do Navegador Thorium / Chromium (Conexão bidirecional com Trajectory)
        self.browser_bridge = BrowserDeepBridge(self.vsa, self.trajectory_engine.resolver, self.effector, db_path="core1_pdag.db")
        self.trajectory_engine.browser_bridge = self.browser_bridge
        
        # 3. Reservatório Líquido Denso em RAM (8000 nós recorrentes)
        self.reservoir = PalimpsestLiquidReservoir(n_nodes=8000, dim_input=64, alpha=0.35)

        # 4. Ontologia Epistêmica
        try:
            self.ontology = EpistemicOntologyEngine(self.vsa, self.pdag)
        except Exception:
            self.ontology = None
        # 5. Motor de Colheita Autônoma Contínua (Frente 2)
        try:
            self.harvester = AutonomousHarvester(
                vsa=self.vsa,
                governance=self.governance,
                browser_bridge=self.browser_bridge,
                db_path="core1_pdag.db"
            )
            logger.info("[HARVESTER]: Substrato de aprendizagem em background pronto.")
        except Exception as e:
            logger.error(f"[HARVESTER]: Erro ao inicializar harvester: {e}")
            self.harvester = None

        self.skill_loader = DynamicSkillLoader(skills_dir=hab_dir)
        self.skill_registry: Dict[str, Callable[..., Any]] = self.skill_loader.registry

        # Rastreamento de Inatividade da IA (Dorme aos 180s sem uso)
        self.ultimo_toque_ai: float = time.time()
        self.esta_dormindo: bool = False

        self.is_running = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._adaptive_observer = None
        from operations_status import RuntimeTelemetrySampler
        self._runtime_telemetry = RuntimeTelemetrySampler()
        self._runtime_task_lock = threading.RLock()
        self._runtime_tasks = {}
        self._runtime_recent_tasks = deque(maxlen=32)

    def observe_ui_scene(self, *, dom=(), ocr=(), visual=(), target=None, required=False):
        """Explicit, opt-in read-only scene observation; never invokes a model."""
        if not required and os.getenv('BRAINNET_UI_SCENE_OBSERVE') != '1':
            return {'status': 'DISABLED'}
        from ui_scene_graph import build_scene_graph
        before = self.context_engine.capture_foreground_context() or {}
        hwnd, pid = before.get('hwnd'), before.get('pid')
        if not hwnd or not pid:
            return {'status': 'CONTEXT_UNAVAILABLE'}
        try:
            import psutil
            started = psutil.Process(pid).create_time()
            rows = self.eye.scan_uia_properties(hwnd)
            after = self.context_engine.capture_foreground_context() or {}
            if (after.get('hwnd') != hwnd or after.get('pid') != pid or
                    after.get('window_rect') != before.get('window_rect') or
                    psutil.Process(pid).create_time() != started):
                return {'status': 'CONTEXT_CHANGED'}
        except Exception:
            return {'status': 'OBSERVATION_UNAVAILABLE'}
        graph = build_scene_graph(app={**before, 'process_started': started}, frame={'coordinate_space': 'screen_physical',
            'window_rect': before.get('window_rect'), 'dpi': 'UNKNOWN'}, uia=rows,
            dom=dom, ocr=ocr, visual=visual)
        result = {'status': 'OBSERVED', 'scene': graph.to_dict()}
        if target is not None:
            result['target_assessment'] = graph.assess_target(target)
        return result

    async def _circadian_rem_watchdog(self) -> None:
        while self.is_running:
            await asyncio.sleep(3.0)
            try:
                inatividade = time.time() - self.ultimo_toque_ai

                # Dorme quando a IA fica 3 minutos (180s) sem o usuário mandar mensagem ou falar
                if self.rem_maintenance_enabled and inatividade >= 180.0 and not self.esta_dormindo:
                    self.esta_dormindo = True
                    logger.info("[SONO REM]: 3 minutos sem interação com a IA. Entrando em sono REM...")
                    threading.Thread(target=self._executar_rem_completo, daemon=True).start()

                # Se acordada, alimenta os 64 canais entrópicos do reservatório líquido em RAM
                if not self.esta_dormindo:
                    ctx = self.context_engine.capture_foreground_context()
                    cpu = self.governance.get_cpu_metrics()
                    ram = self.governance.get_ram_metrics()
                    vram = self.governance.get_vram_metrics()
                    
                    vetor_denso = self.reservoir.pack_dense_telemetry(
                        dhash_hex="0",
                        cpu_total_pct=cpu.total_usage_pct,
                        ram_used_pct=ram.percent_used,
                        vram_used_pct=vram.usage_pct,
                        hwnd_val=ctx.get("hwnd", 0),
                        start_menu_open=ctx.get("start_menu_open", False),
                        mouse_velocity=0.0
                    )
                    self.reservoir.inject_system_event(vetor_denso)
                    
                    # Calibração periódica do estimador ótimo de Wiener a cada 60s
                    if int(time.time()) % 60 == 0:
                        self.reservoir.fit_wiener_filter()

            except Exception as e:
                logger.debug(f"Ciclo circadiano: {e}")

    def _executar_rem_completo(self) -> None:
        if not self.rem_maintenance_enabled:
            raise PermissionError("Manutenção REM desativada; requer autorização específica")
        logger.info("[SONO REM]: Injetando ruído de fase (sigma = 0.15*pi) e reciclando memória...")
        self.rem_engine.execute_full_rem_cycle()
        self.rem_engine.dream_and_immunize_ui_drifts(self.vsa)
        if self.ontology:
            self.ontology.run_deep_rem_dissolution()

    async def start(self) -> None:
        if self.is_running:
            return
        self.is_running = True
        self.loop = asyncio.get_running_loop()
        watchdog = None
        try:
            await self.bridge.start()
            if os.getenv('BRAINNET_PERCEPTUAL_PRESENT')=='1':
                from perceptual_present import PerceptualPresent
                self.perceptual_present=PerceptualPresent(self.eye)
                self.perceptual_present.start()
            if not getattr(self, 'minimal_mode', False):
                self._runtime_telemetry.start()
                watchdog = asyncio.create_task(self._circadian_rem_watchdog())
            else:
                logger.info("REM automático e telemetria desativados no perfil mínimo.")
            if os.getenv('BRAINNET_ADAPTIVE_OBSERVE') == '1':
                try:
                    if self._adaptive_observer is None:
                        from adaptive_observer import AdaptiveObserver
                        self._adaptive_observer = AdaptiveObserver(self, os.getenv('BRAINNET_ADAPTIVE_INTERVAL', '30'))
                    self._adaptive_observer.start()
                except Exception as exc:
                    logger.warning('[ADAPTIVE-OBSERVE] indisponivel: %s', type(exc).__name__)
            logger.info("Kernel iniciado; disponibilidade dos subsistemas opcionais não verificada.")
            while self.is_running:
                await asyncio.sleep(1.0)
        finally:
            self.is_running = False
            if self.perceptual_present is not None:
                stopped=await asyncio.to_thread(self.perceptual_present.stop)
                if not stopped:
                    logger.warning('[PRESENT] Sensor encerramento pendente; nao confirmado.')
            if getattr(self, 'minimal_mode', False):
                await self.bridge.stop()
            if self._runtime_telemetry is not None and not await asyncio.to_thread(self._runtime_telemetry.stop):
                logger.warning('[TELEMETRY] encerramento ainda pendente')
            if self._adaptive_observer is not None:
                stopped = await asyncio.to_thread(self._adaptive_observer.stop)
                if not stopped:
                    logger.warning('[ADAPTIVE-OBSERVE] sensor nao terminou no prazo; reinicio bloqueado ate sua saida')
            if watchdog is not None:
                watchdog.cancel()
                await asyncio.gather(watchdog, return_exceptions=True)


# ------------------------------------------------------------------------------
# PONTE PYWEBVIEW // MASTERSHELL REACT
# ------------------------------------------------------------------------------

class BrainnetBridge:
    def _resume_motor_simulation(self, task_id, operation_id, decision, evidence, motor):
        """Internal test-only path; cannot authorize or dispatch physical actions."""
        from motor_simulation import resume
        return resume(self, task_id, operation_id, decision, evidence, motor)

    def __init__(self, kernel: BrainnetKernel) -> None:
        self._kernel = kernel
        self._window: Optional[webview.Window] = None
        self._voice_active: bool = False
        self._ear = AudioEar(on_speech_detected=self._on_voice_input)
        self._last_vision_memory: str = ""
        self._last_executed_task: str = ""
        self._last_task_event = None
        self._skill_abort = threading.Event()
        self._widget_mode = False
        self._restore_geom: Dict[str, int] = {}
        self._modo_coder_ativo: bool = False
        self._modo_operacao: str = "TRAJETORIA"
        self._proprioception = DigitalProprioceptionGate(self._kernel.vsa)
        self._tom = TheoryOfMindEngine(self._kernel.vsa, threshold_go=0.75)
        self._chat_history: List[Dict[str, str]] = []
        self._p4_lock = threading.Lock()
        self._p4_pending = {}
        self._motor_plan_cache = {}
        self._last_motor_direction = None
        self._ui_motor_window = None
        from contextual_grounder import ContextualGrounder
        import psutil
        self._contextual_grounder = ContextualGrounder(
            self._kernel.context_engine, self._kernel.eye,
            lambda pid: psutil.Process(pid).create_time())

    def _falar_seguro(self, texto: str) -> None:
        try:
            if hasattr(self._kernel, "voice") and self._kernel.voice:
                self._kernel.voice.falar(texto)
        except Exception as e:
            logger.error(f"Falha ao acionar voz neural: {e}")

    def _push_event(self, name: str, detail: Any) -> None:
        if not getattr(self, '_window', None):
            return
        try:
            payload = json.dumps(detail, ensure_ascii=False)
            self._window.evaluate_js(f"window.dispatchEvent(new CustomEvent({json.dumps(name)}, {{ detail: {payload} }}));")
        except Exception as e:
            logger.debug(f"Falha ao empurrar evento: {e}")

    def _on_voice_input(self, text: str) -> None:
        logger.info(f"Voz detectada: '{text}'")
        # V9.5-FIX: Envia o texto falado para o chat como mensagem do usuário
        self._push_event("aios:message", {"role": "user", "text": text})
        res = self.send_command(text)
        if self._window and res.get("reply"):
            try:
                reply_json = json.dumps(res["reply"])
                self._window.evaluate_js(f"window.dispatchEvent(new CustomEvent('aios:message', {{ detail: {{ role: 'ai', text: {reply_json} }} }}));")
            except Exception:
                pass

    def copy_text(self, text: str) -> Dict[str, Any]:
        try:
            subprocess.run(["clip.exe"], input=str(text or "").encode("utf-16le"), check=True, timeout=5)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "log": str(e)}

    def web_search_autonomous(self, query: str) -> Dict[str, Any]:
        from adaptive_resource_controller import current_task_budget, BudgetExhausted
        budget = current_task_budget.get()
        operation = budget.begin_tool('duckduckgo_search') if budget else None
        completed = False
        q = (query or "").strip()
        results: List[Dict[str, str]] = []
        try:
            url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(q)
            html = ""
            if budget:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                with urllib.request.urlopen(req, timeout=min(7, max(.001, budget.deadline_monotonic-time.monotonic()))) as r:
                    html = r.read().decode("utf-8", errors="ignore")
                completed = True
                budget.check_active()
            else:
                try:
                    from curl_cffi import requests as cffi_req
                    sess = cffi_req.Session(impersonate="chrome120")
                    resp = sess.get(url, timeout=7)
                    html = resp.text
                except Exception:
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                    with urllib.request.urlopen(req, timeout=7) as r:
                        html = r.read().decode("utf-8", errors="ignore")

            chunks = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.I | re.S)
            snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, flags=re.I | re.S)

            for i, (href, title) in enumerate(chunks[:5]):
                clean_t = re.sub(r"<[^>]+>", "", title).strip()
                clean_s = re.sub(r"<[^>]+>", "", snippets[i]).strip() if i < len(snippets) else ""
                if clean_t:
                    results.append({"title": clean_t, "snippet": clean_s, "url": href})
        except BudgetExhausted:
            raise
        except Exception as e:
            logger.debug(f"Falha na busca web: {e}")
        finally:
            if budget and operation:
                budget.finish_inference(operation, confirmed=completed)
        return {"ok": True, "query": q, "results": results, "log": f"Pesquisa: {len(results)} fontes."}

    def _processar_ordem_codigo_arquivo(self, prompt: str) -> Optional[Dict[str, Any]]:
        p_low = prompt.lower().strip()
        termos_arquivo = ["arquivo", "script", "código", "codigo", ".txt", ".py", ".json", ".md", ".jsx", ".js", ".css", ".bat"]
        termos_acao = ["crie", "criar", "faça", "fazer", "mude", "mudar", "altere", "alterar", "troque", "trocar", "substitua", "substituir", "adicione", "editar"]

        if not (any(t in p_low for t in termos_arquivo) and any(a in p_low for a in termos_acao)) and not p_low.startswith(("/code", "/file", "/patch")):
            return None

        prompt_coder = (
            "Você é o Engenheiro de Software do BRAINNET v7.\n"
            "Sua raiz permitida é estritamente 'A:\\BRAINNET'. NUNCA altere arquivos em 'AUTOrecover' ou 'BRAINNET_LOG.txt'.\n"
            "Retorne EXCLUSIVAMENTE um JSON estruturado:\n"
            '{"acao": "criar" ou "editar", "caminho_relativo": "...", "conteudo_novo": "...", "trecho_antigo": "...", "trecho_novo": "...", "resumo": "..."}\n'
            f"PEDIDO: '{prompt}'"
        )
        url = OLLAMA_GENERATE_URL
        payload = {"model": "qwen2.5-coder:7b", "prompt": prompt_coder, "format": "json", "stream": False, "options": {"temperature": 0.1, "num_predict": 1200}}

        from adaptive_resource_controller import current_task_budget
        budget = current_task_budget.get()
        operation = budget.begin_inference(estimated_tokens=1200) if budget else None
        completed = False
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
            timeout = min(50, max(0.001, budget.deadline_monotonic - time.monotonic())) if budget else 50
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                envelope = json.loads(resp.read().decode("utf-8"))
            completed = envelope.get('done') is True
            if not completed:
                raise RuntimeError('Resposta de código incompleta')
            if budget and (budget.cancellation_event.is_set() or time.monotonic() >= budget.deadline_monotonic):
                budget.cancellation_event.set()
                raise RuntimeError('Cancelamento solicitado; resultado de código descartado')
            data = json.loads(envelope.get("response", "{}"))

            acao = str(data.get("acao", "criar")).strip().lower()
            rel_path = data.get("caminho_relativo", "").strip().replace("\\", "/")
            resumo = data.get("resumo", "Operação concluída.")
            base_dir = Path(__file__).resolve().parent
            destino = (base_dir.parent / rel_path).resolve()
            caminho_str = str(destino).lower()

            if "autorecover" in caminho_str or "brainnet_log.txt" in caminho_str or not caminho_str.startswith(str(base_dir.parent).lower()):
                return {"reply": "Ação bloqueada: tentativa de alteração fora de A:\\BRAINNET ou em zonas protegidas.", "logs": []}

            vault_dir = base_dir / "code_vault"
            vault_dir.mkdir(parents=True, exist_ok=True)
            ts = int(time.time() * 1000)

            if acao == "editar":
                if not destino.exists():
                    return {"reply": f"Erro: Arquivo '{rel_path}' não encontrado para edição.", "logs": []}
                trecho_antigo = data.get("trecho_antigo", "")
                trecho_novo = data.get("trecho_novo", "")
                conteudo_atual = destino.read_text(encoding="utf-8")
                if trecho_antigo not in conteudo_atual:
                    return {"reply": f"Não consegui localizar o trecho original exato em '{rel_path}'.", "logs": []}

                (vault_dir / f"{destino.stem}_{ts}{destino.suffix}").write_bytes(destino.read_bytes())
                conteudo_modificado = conteudo_atual.replace(trecho_antigo, trecho_novo, 1)

                if destino.suffix == ".py":
                    try:
                        ast.parse(conteudo_modificado)
                    except SyntaxError as syn_err:
                        return {"reply": f"Edição rejeitada por validação AST (linha {syn_err.lineno}): {syn_err.msg}.", "logs": []}

                destino.write_text(conteudo_modificado, encoding="utf-8")
                self._falar_seguro(f"Arquivo {destino.name} atualizado.")
                return {"reply": f"Alteração aplicada em '{rel_path}': {resumo}", "logs": [{"level": "INFO", "core": "Coder7B", "msg": f"Patch: {destino}"}]}
            else:
                conteudo = data.get("conteudo_novo", "")
                if destino.exists():
                    (vault_dir / f"{destino.stem}_{ts}{destino.suffix}").write_bytes(destino.read_bytes())
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_text(conteudo, encoding="utf-8")
                self._falar_seguro(f"Arquivo {destino.name} criado com sucesso.")
                return {"reply": f"Arquivo '{rel_path}' criado com sucesso.\nResumo: {resumo}", "logs": [{"level": "INFO", "core": "Coder7B", "msg": f"Criado: {destino}"}]}
        except Exception as e:
            return {"reply": f"Falha no Coder 7B: {e}", "logs": [{"level": "ERROR", "core": "Coder7B", "msg": str(e)}]}
        finally:
            if budget and operation:
                budget.finish_inference(operation, confirmed=completed)

    @command_authority
    def send_command(self, text: str) -> Dict[str, Any]:
        from adaptive_resource_controller import ExecutionLimits, SharedTaskBudget, BudgetExhausted, current_task_budget
        configured = self.get_effort_mode()['mode']
        effective = _effective_effort(configured, text)
        limits = _EFFORT_LIMITS[effective]
        command_started = time.perf_counter()
        p4_requested = getattr(getattr(self, '_kernel', None), 'minimal_mode', False) and os.getenv('BRAINNET_P4_PHYSICAL_PROPOSALS') == '1' and text.strip().casefold() == 'mova o mouse em qualquer direção'
        semantic_motor = getattr(self._kernel, 'minimal_mode', False) and os.getenv('BRAINNET_MOTOR_SEMANTIC') == '1' and not text.strip().startswith('/')
        task_deadline = 60 if semantic_motor else (180 if p4_requested else limits['timeout'])
        task_budget = SharedTaskBudget(uuid.uuid4().hex, effective, time.monotonic() + task_deadline,
                                       current_authorization(), ExecutionLimits(8, 8, limits['visual_steps'], limits['num_predict'] * 8))
        kernel = getattr(self, '_kernel', None)
        registry = getattr(kernel, '_runtime_tasks', None)
        registry_lock = getattr(kernel, '_runtime_task_lock', None)
        if registry is not None and registry_lock is not None:
            with registry_lock:
                registry[task_budget.task_id] = task_budget
        self._push_event('aios:task', {'phase': 'PROCESSING', 'configured': configured, 'effective': effective,
                                      'budget': task_budget.snapshot()})
        self._push_event('aios:reasoning', {'task_id': task_budget.task_id, 'source': 'BrainnetBridge.send_command',
                         'timestamp': time.time(), 'state': 'PROCESSING', 'kind': 'task_started',
                         'configured_mode': configured, 'effective_mode': effective})
        budget_token = current_task_budget.set(task_budget)
        token = _effort_for_command.set(effective)
        conversation_token = _conversation_for_command.set(self.get_conversation_status())
        finish_token = _conversation_finish_reason.set(None)
        awaiting_approval = False
        try:
            try:
                result = self._send_command_impl(text)
                if _conversation_finish_reason.get() in ('length', 'max_tokens') and not result.get('status'):
                    result['status'] = 'INCOMPLETE'
                awaiting_approval = result.get('status') in ('AUTHORIZATION_REQUIRED', 'PENDING_APPROVAL') and result.get('pending_operation_id') is not None
            except BudgetExhausted as exc:
                result = {'reply': str(exc), 'logs': [], 'status': 'BUDGET_EXHAUSTED', 'sucesso_real': False}
            except BaseException as exc:
                self._push_event('aios:task', {'phase': 'ERROR', 'configured': configured, 'effective': effective,
                                              'budget': task_budget.snapshot(), 'error_type': type(exc).__name__})
                raise
        finally:
            _effort_for_command.reset(token)
            _conversation_for_command.reset(conversation_token)
            _conversation_finish_reason.reset(finish_token)
            current_task_budget.reset(budget_token)
            if registry is not None and registry_lock is not None:
                with registry_lock:
                    if not awaiting_approval:
                        registry.pop(task_budget.task_id, None)
                    recent = getattr(kernel, '_runtime_recent_tasks', None)
                    if recent is not None and not awaiting_approval:
                        recent.append(task_budget)
        result['task_budget'] = task_budget.snapshot()
        if getattr(kernel, 'minimal_mode', False):
            logger.info('[P3] pid=%s task_id=%s route=%s status=%s dispatched=%s elapsed_ms=%.3f',
                        os.getpid(), task_budget.task_id,
                        'delegated_move' if (result.get('motor_proposal') or {}).get('direction_delegated') else 'other',
                        result.get('status'), result.get('dispatched'), (time.perf_counter()-command_started)*1000)

        task_phase = ('WAITING_AUTHORIZATION' if awaiting_approval else
                      'INCOMPLETE' if result.get('status') == 'INCOMPLETE' else
                      'CANCEL_REQUESTED' if task_budget.cancellation_event.is_set()
                      else 'PENDING' if result['task_budget'].get('inflight') else 'FINISHED')
        self._push_event('aios:task', {'phase': task_phase, 'configured': configured, 'effective': effective,
                                      'budget': result['task_budget'], 'result_status': result.get('status'),
                                      'goal_state': (result.get('visual_result') or {}).get('goal_state')})
        self._push_event('aios:reasoning', {'task_id': task_budget.task_id, 'source': 'BrainnetBridge.send_command',
                         'timestamp': time.time(), 'state': task_phase, 'kind': 'task_finished',
                         'result_status': result.get('status'), 'budget': result['task_budget']})
        result['effort'] = {'configured': configured, 'effective': effective,
                            'budget': dict(_EFFORT_LIMITS[effective]),
                            'scope': 'conversation_and_visual_steps', 'thinking': 'não confirmado'}
        if not text.strip().lower().startswith(('/copy', '/copie')):
            history = getattr(self, '_chat_history', None)
            if history is not None:
                for role, content in (('user', text.strip()), ('ai', result.get('reply', ''))):
                    history.append({'role': role, 'text': content, 'id': uuid.uuid4().hex,
                                    'timestamp': time.time()})
                del history[:-120]
        return result

    def _manual_capability_command(self, text: str, normalized: str):
        """Explicit control commands; selecting a capability never grants authority."""
        mode_match = re.fullmatch(r'/modo\s+(auto|fast|balanced|deep)', normalized)
        if mode_match:
            result = self.set_effort_mode(mode_match.group(1).upper())
            return {'reply': (f"Modo cognitivo {result['mode']} configurado para as próximas tarefas." if result.get('ok')
                              else f"Não foi possível alterar o modo: {result.get('error', 'erro desconhecido')}"),
                    'logs': [], 'status': 'CONFIGURED' if result.get('ok') else 'UNAVAILABLE'}
        profile_match = re.fullmatch(r'/modo\s+(livre|padrao|padrão|status)', normalized)
        if profile_match:
            choice = profile_match.group(1)
            if choice != 'status':
                cfg = _load_app_config()
                cfg['conversation_profile'] = 'LIVRE' if choice == 'livre' else 'PADRAO'
                _save_app_config(cfg)
                if _load_app_config().get('conversation_profile') != cfg['conversation_profile']:
                    return {'reply':'Não foi possível salvar o perfil conversacional.', 'logs':[], 'status':'UNAVAILABLE'}
            current = self.get_conversation_status()
            return {'reply':f"Perfil configurado: {current['profile']}; modo cognitivo: {self.get_effort_mode()['mode']}; modelo conversacional configurado: {current['model']} (disponibilidade não verificada). O perfil não altera pesos, autorização ou verificação.",
                    'logs':[], 'status':'CONFIGURED', 'conversation':current}
        if normalized == '/modelo listar' or normalized.startswith('/modelo usar '):
            try:
                url = OLLAMA_GENERATE_URL.removesuffix('/api/generate') + '/api/tags'
                with urllib.request.urlopen(url, timeout=3) as response:
                    data = json.loads(response.read(1024*1024).decode('utf-8'))
                models = sorted({item['name'] for item in data.get('models', [])
                                 if isinstance(item, dict) and isinstance(item.get('name'), str)})
            except Exception as exc:
                return {'reply':f'Catálogo do Ollama indisponível ({type(exc).__name__}); nenhum modelo selecionado.', 'logs':[], 'status':'UNAVAILABLE'}
            if normalized == '/modelo listar':
                return {'reply':'Modelos informados pelo Ollama: '+(', '.join(models) if models else 'nenhum'),
                        'logs':[], 'status':'AVAILABLE', 'models':models}
            requested = text.split(None, 2)[2].strip()
            if requested not in models:
                return {'reply':'Modelo não encontrado no catálogo atual; seleção não alterada.', 'logs':[], 'status':'NOT_FOUND'}
            cfg = _load_app_config(); cfg['conversation_model'] = requested; _save_app_config(cfg)
            if _load_app_config().get('conversation_model') != requested:
                return {'reply':'Não foi possível salvar o modelo.', 'logs':[], 'status':'UNAVAILABLE'}
            return {'reply':f'Modelo {requested} selecionado para conversação nas próximas tarefas; compatibilidade de geração não foi verificada.', 'logs':[], 'status':'CONFIGURED', 'model':requested}
        if normalized == '/visao agora':
            vision = getattr(self._kernel, 'vision', None)
            if not callable(getattr(vision, 'descrever_tela', None)):
                return {'reply':'Visão indisponível: módulo de captura e descrição não está conectado.', 'logs':[], 'status':'UNAVAILABLE'}
            try:
                description = vision.descrever_tela('Descreva somente o que está visível.')
                return {'reply':str(description), 'logs':[], 'status':'OBSERVATION_UNVERIFIED'}
            except Exception as exc:
                return {'reply':f'Visão indisponível: falha de captura ou modelo ({type(exc).__name__}).', 'logs':[], 'status':'UNAVAILABLE'}
        if normalized == '/uia scan' or normalized.startswith('/uia scan '):
            # Explicit external window only: foreground could be our PyWebView.
            target = re.fullmatch(r'/uia scan\s+([0-9]+)\s+([0-9]+)', normalized)
            if target is None:
                return {'reply':'Indique uma janela externa: /uia scan <HWND> <PID>. Não usamos automaticamente a janela em foco.', 'logs':[], 'status':'TARGET_REQUIRED'}
            eye = getattr(self._kernel, 'eye', None)
            if not callable(getattr(eye, 'scan_uia_properties', None)):
                return {'reply':'UIA indisponível: percepção não conectada.', 'logs':[], 'status':'UNAVAILABLE'}
            try:
                from perception_eye import HAS_UIA_NATIVE
                from uia_chat_readonly import scan_explicit_window, chat_reply
                result = scan_explicit_window(int(target.group(1)), int(target.group(2)),
                                              scanner=eye.scan_uia_properties, provider_available=HAS_UIA_NATIVE)
                return {'reply':chat_reply(result), 'logs':[], **result}
            except Exception as exc:
                return {'reply':f'UIA indisponível ({type(exc).__name__}).', 'logs':[], 'status':'UNAVAILABLE'}
        return None

    def _send_command_impl(self, text: str) -> Dict[str, Any]:
        from parser_contract import analyze_literal_intent, parse_supervised_mouse_move
        prompt_raw = text.strip()
        p_low = prompt_raw.lower()
        p_norm = re.sub(r"\s+", " ", p_low).strip()
        # Local chat functions must work even without model or full kernel.
        if p_norm in ('/copy all', '/copie all', '/copy tudo', '/copie tudo', '/copy-all', '/copietudo', '/copy', '/copie'):
            history = list(self._chat_history)
            if p_norm in ('/copy','/copie'):
                history = history[-2:]
            if not history:
                return {'reply':'O histórico de conversa ainda está vazio.', 'logs':[]}
            lines = ['=== HISTÓRICO DE CONVERSA - BRAINNET v7 ===']
            for msg in history:
                author = 'USUÁRIO' if msg['role'] == 'user' else 'BRAINNET'
                lines.append(f"\n[{author}]:\n{msg['text']}")
            result = self.copy_text('\n'.join(lines))
            if result.get('ok') is not True:
                return {'status':'ACTION_FAILED','reply':'Não foi possível copiar o histórico.','logs':[]}
            return {'status':'COPIED','reply':f'Histórico copiado ({len(history)} mensagens).','logs':[]}
        if p_norm == '/ui clear':
            with self._p4_lock:
                self._ui_motor_window = None
            return {'status':'CLEARED','reply':'Contexto de interface removido.','logs':[]}
        if p_norm == '/ui context' or p_norm.startswith('/ui context '):
            from ui_motor_context import find_window
            query = prompt_raw[len('/ui context'):].strip()
            with self._p4_lock:
                self._ui_motor_window = None
            if not query:
                return {'status':'TARGET_REQUIRED','reply':'Use /ui context <nome do aplicativo ou título da janela aberta>.','logs':[]}
            try:
                found = find_window(query)
            except Exception as exc:
                return {'status':'UNAVAILABLE','reply':f'Contexto de janela indisponível ({type(exc).__name__}).','logs':[]}
            if found['status'] != 'BOUND':
                return {'status':found['status'],'reply':f"Janela não identificada unicamente ({found.get('count',0)} correspondências). Abra uma única janela e use um nome mais específico.",'logs':[]}
            with self._p4_lock:
                self._ui_motor_window = found['window']
            window = found['window']
            return {'status':'BOUND','reply':f"Contexto: {window['app']}, HWND {window['hwnd']}, PID {window['pid']}. Use /ui controls para observar os controles.",'logs':[]}
        if p_norm == '/checkup':
            from pathlib import Path
            import psutil
            k=self._kernel
            present=getattr(k,'perceptual_present',None)
            state=present.snapshot() if present else {}
            ram=psutil.virtual_memory()
            lines=[f"Perfil: {'mínimo' if k.minimal_mode else 'completo'}; PID {os.getpid()}",
                   f"RAM disponível: {ram.available//1048576} MiB; processo: {psutil.Process().memory_info().rss//1048576} MiB.",
                   f"Kernel: {'ativo' if k.is_running else 'inativo'}; workers: {sum(not w.done() for w in getattr(k.bridge,'_workers',()))}."]
            for attr,label in [('perceptual_present','Presente perceptivo'),('situation_memory','Memória situacional'),
                    ('situation_index','Índice FHRR situacional'),('pdag','P-DAG'),('rem_engine','REM'),
                    ('world_model','Modelo preditivo'),('shadow','Simulação contrafactual'),
                    ('reservoir','Reservatório líquido'),('concept_cortex','Córtex de conceitos'),
                    ('vision','Visão'),('skill_loader','Habilidades cristalizadas')]:
                lines.append(f"{label}: {'instanciado (funcionamento não comprovado)' if getattr(k,attr,None) is not None else 'não inicializado'}")
            vsa=getattr(k,'vsa',None)
            if vsa is not None:
                lines.append(f"FHRR: {vsa.dim} dimensões; cleanup {len(vsa.cleanup_keys)} vetores, {vsa.cleanup_matrix.nbytes} bytes; cache de tokens {len(vsa._token_cache)}.")
            with self._p4_lock:
                lines.append(f"Memória motora de sessão: {len(self._motor_plan_cache)} planos; histórico de chat: {len(self._chat_history)} mensagens.")
            lines.append(f"REM de manutenção habilitado: {getattr(k,'rem_maintenance_enabled',False)}.")
            lines.append('Arquivos locais (presença não comprova integridade):')
            for name in ('core1_pdag.db','hmem_memory.db'):
                p=Path(__file__).resolve().parent/name
                try:
                    size=p.stat().st_size
                    lines.append(f'{name}: {size} bytes')
                except OSError:
                    lines.append(f'{name}: ausente ou inacessível')
            skills=Path(__file__).resolve().parent.parent/'HABILIDADES'
            try:
                lines.append(f'Habilidades Python no diretório: {sum(1 for p in skills.glob("*.py") if p.is_file())}')
            except OSError:
                lines.append('Diretório de habilidades indisponível.')
            lines.append(f"Janelas no presente: {len(state.get('windows',[]))}; canais: " + ', '.join(f"{n}={s['status']}" for n,s in state.get('channels',{}).items()))
            return {'status':'OBSERVED','reply':'\n'.join(lines),'logs':[]}
        if p_norm in ('/context','/ui world'):
            present=getattr(self._kernel,'perceptual_present',None)
            if present is None:
                return {'status':'UNAVAILABLE','reply':'Percepção contínua não inicializada.','logs':[]}
            snapshot=present.snapshot()
            windows=snapshot['windows']
            lines=[f"Presente v{snapshot['version']}: foco {snapshot['foreground']} ({snapshot['focus_state']}); {len(windows)} janelas observadas."]
            for name,sample in snapshot['channels'].items():
                value=sample.get('value') or {}
                lines.append(f"{name}: {sample['status']}/{value.get('status','')} — idade {sample.get('age_ms')} ms")
            spatial=(snapshot['channels']['spatial'].get('value') or {})
            inventory=(snapshot['channels']['windows'].get('value') or {})
            lines.append(f"Inventário: {inventory.get('visible_candidates','?')} candidatos, {inventory.get('rejected','?')} rejeitados, erros: {inventory.get('errors',{})}.")
            lines.append(f"Monitores: {spatial.get('monitor_status','UNKNOWN')}; cursor: {spatial.get('cursor',{}).get('cursor')}; monitor atual: {spatial.get('cursor_monitor')}.")
            for m in spatial.get('monitors',[]):
                lines.append(f"{m['device']} | {m['rect']} | DPI {m['dpi']}" + (' | primário' if m['primary'] else ''))
            for w in windows[:40]:
                state='minimizada' if w['minimized'] is True else 'aberta' if w['minimized'] is False else 'estado desconhecido'
                lines.append(f"{w['app']} | HWND {w['hwnd']} | {state} | {w['rect']}" + (' | foco' if w['hwnd']==snapshot['foreground'] else ''))
            if len(windows)>40:
                lines.append('Lista limitada a 40 janelas.')
            return {'status':snapshot['channels']['windows']['status'],
                    'reply':'\n'.join(lines),'logs':[]}
        if p_norm == '/ui controls':
            from adaptive_resource_controller import current_task_budget
            from execution_authority import authorization_scope
            import win32gui
            with self._p4_lock:
                window = self._ui_motor_window
            if window is None:
                present=getattr(self._kernel,'perceptual_present',None)
                if present is not None:
                    window=present.snapshot().get('last_external')
            if window is None:
                return {'status':'TARGET_REQUIRED','reply':'Nenhuma janela externa recente identificada. Use /ui context <aplicativo>.','logs':[]}
            budget=current_task_budget.get()
            if budget is None or not self._kernel.loop or not self._kernel.loop.is_running():
                return {'status':'UNAVAILABLE','reply':'Kernel indisponível para observação ativa.','logs':[]}
            from ui_motor_context import stable_foreground
            foreground=stable_foreground(deadline=budget.deadline_monotonic)
            token=budget.cancellation_event
            async def scan_active():
                with authorization_scope(token):
                    return await self._kernel.bridge.dispatch('ui_observe_active', {
                        'window':window,'expected_foreground':foreground,'deadline':budget.deadline_monotonic},
                        timeout_sec=min(12,max(.01,budget.deadline_monotonic-time.monotonic())))
            future=None
            try:
                budget.check_active()
                future=asyncio.run_coroutine_threadsafe(scan_active(),self._kernel.loop)
                command=future.result(timeout=min(14,max(.01,budget.deadline_monotonic-time.monotonic())))
                scene=command.result if command.status=='completed' and isinstance(command.result,dict) else {'status':'SCAN_UNCONFIRMED'}
            except Exception:
                token.set()
                if future is not None:
                    future.cancel()
                scene={'status':'SCAN_UNCONFIRMED'}
            if scene['status'] != 'OBSERVED':
                return {'status':scene['status'],'reply':f"Controles UIA indisponíveis ({scene.get('code',scene['status'])}). Foco atual: {scene.get('observed_focus')}; alvo: {window['hwnd']}.",'logs':[]}
            names = [f"{c['name']} ({c['type'].removesuffix('Control')})" for c in scene['controls']]
            shown = names[:60]
            rejected = '; '.join(f"{k}: {v}" for k,v in scene.get('rejection_counts',{}).items())
            focus_note='em primeiro plano' if scene.get('foreground_verified') else f"leitura sem foco confirmado ({scene.get('focus_code','UNKNOWN')})"
            return {'status':'OBSERVED','reply':f"{window['app']} ({focus_note}): {len(names)} controles elegíveis (de {scene.get('raw_count',0)} elementos UIA).\n" + '\n'.join(shown) + ('\nLista limitada a 60.' if len(names)>60 else '') + f'\nDescartados: {rejected or "nenhum"}.','logs':[]}
        if p_norm == '/motor status':
            from assistant_prompts import MODELO_PARSER
            from urllib.request import urlopen
            import json
            endpoint = OLLAMA_GENERATE_URL.removesuffix('/api/generate')
            model = os.getenv('BRAINNET_MOTOR_MODEL', MODELO_PARSER)
            try:
                with urlopen(endpoint+'/api/tags', timeout=3) as response:
                    models = [m.get('name') for m in json.load(response).get('models', [])]
                ready = model in models
                return {'status':'READY' if ready else 'UNAVAILABLE','reply':f'Ollama: conectado em {endpoint}. Modelo {model}: {"instalado" if ready else "não encontrado"}. Modelos locais: {", ".join(str(m) for m in models) or "nenhum"}.','logs':[]}
            except Exception as exc:
                return {'status':'UNAVAILABLE','reply':f'Ollama indisponível em {endpoint} ({type(exc).__name__}). Modelo: {model}. Movimento básico continua disponível.','logs':[]}
        if p_norm == '/kernel status':
            kernel = self._kernel
            bridge = kernel.bridge
            loop = kernel.loop
            workers = getattr(bridge, '_workers', ())
            active_workers = sum(not worker.done() for worker in workers)
            ready = bool(kernel.is_running and loop and loop.is_running()
                         and getattr(bridge, '_running', False) and active_workers)
            minimal = bool(kernel.minimal_mode)
            direct = minimal and os.getenv('BRAINNET_P4_PHYSICAL_PROPOSALS') == '1' and os.getenv('BRAINNET_P4_DIRECT_MOVE') == '1'
            return {'status': 'READY' if ready else 'UNAVAILABLE',
                    'reply': f"Kernel real: {'pronto' if ready else 'indisponível'}; PID {os.getpid()}; perfil {'mínimo' if minimal else 'completo'}; workers ativos: {active_workers}; movimento direto configurado: {'sim' if direct else 'não'}.",
                    'logs': [], 'pid': os.getpid(), 'minimal': minimal,
                    'active_workers': active_workers, 'direct_move_enabled': direct}
        if (getattr(self._kernel, 'minimal_mode', False)
                and os.getenv('BRAINNET_MOTOR_SEMANTIC') == '1' and not prompt_raw.startswith('/')):
            return self._execute_semantic_motor(prompt_raw)
        if getattr(self._kernel, 'minimal_mode', False) and not (p_norm.startswith('/uia scan') or parse_supervised_mouse_move(prompt_raw)):
            return {'reply': 'Capacidade indisponível no perfil mínimo experimental.', 'logs': [], 'status': 'UNAVAILABLE'}
        manual = self._manual_capability_command(prompt_raw, p_norm)
        if manual is not None:
            return manual
        intent_contract = analyze_literal_intent(prompt_raw)
        motor_proposal = parse_supervised_mouse_move(prompt_raw)
        if motor_proposal is not None and motor_proposal.get('direction_delegated') and getattr(self._kernel, 'minimal_mode', False) and os.getenv('BRAINNET_P4_PHYSICAL_PROPOSALS') == '1':
            from adaptive_resource_controller import current_task_budget
            from capability_lab import observe_physical_monitor, observe_cursor_monitors
            from execution_authority import PhysicalMoveProposal, PhysicalMoveApproval
            budget = current_task_budget.get()
            observation = observe_physical_monitor()
            desktop = observe_cursor_monitors()
            if budget is None or observation.get('status') != 'OBSERVED' or desktop.get('interactive_desktop_verified') is not True:
                return {'status':'ACTION_BLOCKED', 'reply':'Observação física ou desktop indisponível.', 'logs':[], 'dispatched':False}
            if observation.get('coordinate_space') != 'PHYSICAL':
                return {'status':'ACTION_BLOCKED','code':'COORDINATE_SPACE_MISMATCH',
                        'reply':'Observação não está em coordenadas físicas; nenhum movimento executado.',
                        'logs':[],'dispatched':False}
            # P4.4 is deliberately narrow: only the literal, user-originated
            # delegated move reaches this path.  It does not accept a model
            # proposal, and it reuses the physical bridge's one-use approval.
            if os.getenv('BRAINNET_P4_DIRECT_MOVE') == '1':
                start = tuple(observation.get('cursor', ()))
                rect = tuple(observation.get('monitor_rect', ()))
                if (len(start) != 2 or len(rect) != 4 or
                    any(type(v) is not int for v in (*start, *rect))):
                    return {'status':'ACTION_BLOCKED','code':'COORDINATE_SPACE_MISMATCH',
                            'reply':'Coordenadas físicas incompletas; nenhum movimento executado.','logs':[],'dispatched':False}
                left, top, right, bottom = rect
                if not (left <= start[0] < right and top <= start[1] < bottom):
                    return {'status':'ACTION_BLOCKED','code':'CURSOR_OUTSIDE_MONITOR',
                            'reply':'Cursor fora dos limites físicos do monitor; nenhum movimento executado.','logs':[],'dispatched':False}
                # Visible direct diagnostic: right 150 pixels, or left at the edge.
                distance = 150
                dx = distance if start[0] + distance < right else -distance
                target = (start[0] + dx, start[1])
                if not (left <= target[0] < right and top <= target[1] < bottom):
                    return {'status':'ACTION_BLOCKED','code':'MONITOR_BOUNDARY',
                            'reply':'Não há deslocamento horizontal de 150 pixels dentro do monitor atual.','logs':[],'dispatched':False}
                operation_id = uuid.uuid4().hex
                proposal = PhysicalMoveProposal(budget.task_id, operation_id, start, target,
                                                observation['monitor'], rect, 0, budget.deadline_monotonic, max_distance=distance)
                approval = PhysicalMoveApproval(proposal)
                # This approval derives only from this exact command received
                # by the local MasterShell bridge, never from LLM output.
                if not approval.approve_explicitly(operation_id):
                    return {'status':'ACTION_BLOCKED','code':'APPROVAL_MISSING',
                            'reply':'Autorização interna do comando não pôde ser criada.','logs':[],'dispatched':False}
                return self._dispatch_direct_p4_move(proposal, approval, budget)
            from capability_lab import find_verified_safe_region
            from execution_authority import RelativePhysicalMoveProposal
            region = find_verified_safe_region(observation)
            if region.get('status') != 'VERIFIED' or region.get('coordinate_space') != 'PHYSICAL':
                return {'status':'ACTION_BLOCKED','code':'SAFE_REGION_UNVERIFIED','reply':'Região segura livre de controles não foi confirmada; nenhum movimento proposto.', 'logs':[], 'dispatched':False}
            try:
                safe_rect = tuple(region['safe_rect']); hwnd = region['lab_hwnd']; pid = region['lab_pid']
                if len(safe_rect) != 4 or any(type(v) is not int for v in safe_rect) or safe_rect[0]>=safe_rect[2] or safe_rect[1]>=safe_rect[3] or type(hwnd) is not int or hwnd <= 0 or type(pid) is not int or pid <= 0:
                    raise ValueError('invalid region')
            except (KeyError,TypeError,ValueError):
                return {'status':'ACTION_BLOCKED','code':'SAFE_REGION_UNVERIFIED','reply':'Evidência da região segura inválida.', 'logs':[], 'dispatched':False}
            operation_id = budget.begin_pending_motor({'dx':10,'dy':0})
            budget.cancellation_event = threading.Event()
            proposal = RelativePhysicalMoveProposal(budget.task_id, operation_id, 10, 0, observation['monitor'], tuple(observation['monitor_rect']), safe_rect, hwnd, pid, 0, budget.deadline_monotonic)
            approval = PhysicalMoveApproval(proposal)
            with self._p4_lock:
                self._p4_pending[operation_id] = (proposal, approval, budget)
            display = observation['monitor'].split('\\')[-1].replace('.', '')
            remaining = int(max(0, proposal.deadline_monotonic-time.monotonic()))
            reply = (f'Movimento único de 10 pixels para a direita, sem clique ou arrasto. '
                     f'Monitor {display}; região segura {safe_rect}; tolerância 0; validade {remaining} s. '
                     'A posição será observada novamente após sua autorização e deve permanecer na região segura.')
            return {'status':'PENDING_APPROVAL','reply':reply,'logs':[],'task_id':budget.task_id,'pending_operation_id':operation_id,
                    'physical_proposal':{'task_id':proposal.task_id,'proposal_id':proposal.proposal_id,'relative':True,'dx':10,'dy':0,
                                         'safe_rect':safe_rect,'monitor':display,'tolerance':0,'expires_in_ms':remaining*1000},'dispatched':False}
        if motor_proposal is not None and motor_proposal.get('direction_delegated') and not getattr(self._kernel, 'minimal_mode', False):
            from adaptive_resource_controller import current_task_budget
            budget = current_task_budget.get()
            motor_proposal['task_id'] = budget.task_id if budget else None
            return {'reply': 'A direção e distância foram delegadas; é necessário observar cursor, monitor e região segura antes de propor um deslocamento e solicitar aprovação específica.', 'logs': [], 'status': 'ACTION_BLOCKED', 'motor_stage': 'INTENT_RECOGNIZED', 'next_requirement': 'OBSERVATION_REQUIRED', 'motor_proposal': motor_proposal, 'dispatched': False}
        if motor_proposal is not None and motor_proposal.get('direction_delegated'):
            from adaptive_resource_controller import current_task_budget
            budget = current_task_budget.get()
            motor_proposal['task_id'] = budget.task_id if budget else None
            kernel = getattr(self, '_kernel', None)
            registry = getattr(kernel, '_runtime_tasks', None)
            registry_lock = getattr(kernel, '_runtime_task_lock', None)
            result = {'reply': 'Direção e distância delegadas. Aguardando autorização específica; antes de qualquer movimento serão necessárias observação atual e proposta física exata.', 'logs': [], 'status': 'AUTHORIZATION_REQUIRED', 'motor_stage': 'INTENT_RECOGNIZED', 'next_requirement': 'OBSERVATION_REQUIRED', 'motor_proposal': motor_proposal, 'dispatched': False}
            if budget is not None and registry is not None and registry_lock is not None:
                pending = {**motor_proposal, 'dx': None, 'dy': None}
                operation_id = budget.begin_pending_motor(pending)
                budget.cancellation_event = threading.Event()
                result['pending_operation_id'] = operation_id
                motor_proposal['operation_id'] = operation_id
                result['reply'] += f" Tarefa {budget.task_id}; proposta {operation_id}."
            else:
                result['status'] = 'ACTION_BLOCKED'
                result['reply'] = 'Registro de tarefa indisponível; nenhuma ação autorizável.'
            return result
        if motor_proposal is not None:
            from adaptive_resource_controller import current_task_budget
            task_budget = current_task_budget.get()
            motor_proposal['task_id'] = task_budget.task_id if task_budget is not None else None
            kernel = getattr(self, '_kernel', None)
            registry = getattr(kernel, '_runtime_tasks', None)
            registry_lock = getattr(kernel, '_runtime_task_lock', None)
            result = {'reply': 'Movimento reconhecido como proposta. A execução real exige teste supervisionado e autorização específica; nenhum movimento foi executado.',
                      'logs': [], 'motor_proposal': motor_proposal, 'status': 'AUTHORIZATION_REQUIRED',
                      'motor_stage': 'AUTHORIZATION_REQUIRED', 'dispatched': False}
            if task_budget is not None and registry is not None and registry_lock is not None:
                operation_id = task_budget.begin_pending_motor(motor_proposal)
                # The command token is revoked when this call returns; waiting is
                # not an authorization, so keep a separate cancellation signal.
                task_budget.cancellation_event = threading.Event()
                result['pending_operation_id'] = operation_id
                motor_proposal['operation_id'] = operation_id
            else:
                result['pending_unavailable'] = 'Registro de tarefas indisponível'
            return result
        if re.fullmatch(r'(?:mova|mover|movimente)\s+o\s+mouse\s+em\s+qualquer\s+dire[cç][aã]o[.!]?', p_norm):
            return {'reply':'Movimento reconhecido, mas faltam direção e distância para preparar uma proposta verificável. Nenhuma ação foi despachada.',
                    'logs':[], 'status':'CLARIFICATION_REQUIRED', 'motor_stage':'INTENT_RECOGNIZED', 'dispatched':False}
        long_request = re.match(r'^/escreva\s+(.+)$', prompt_raw, re.IGNORECASE | re.DOTALL)
        if long_request:
            return self._write_long_draft(long_request.group(1).strip())
        natural_long = re.fullmatch(r'(?:escreva|redija)\s+(?:um\s+)?(?:texto\s+longo|ensaio\s+detalhado)\s+(?:sobre|a respeito de)\s+(.+)', prompt_raw, re.IGNORECASE | re.DOTALL)
        if natural_long:
            return self._write_long_draft(natural_long.group(1).strip())
        resume_request = re.fullmatch(r'/continue\s+([0-9a-f]{32})', prompt_raw, re.IGNORECASE)
        if resume_request:
            return self._write_long_draft('', resume_id=resume_request.group(1).lower())
        conceptual_analysis = None
        if os.getenv('BRAINNET_CONCEPTUAL_OBSERVE') == '1' and prompt_raw:
            from natural_comprehension import conceptual_hypotheses, retrieve_concept_candidates
            conceptual_analysis = conceptual_hypotheses(prompt_raw)
            try:
                conceptual_analysis['concept_candidates'] = retrieve_concept_candidates(self._kernel.vsa, prompt_raw)
            except Exception:
                conceptual_analysis['concept_candidates'] = []
                conceptual_analysis['concept_retrieval_status'] = 'UNAVAILABLE'
        # Exact low-impact alias; reuse the existing help handler without
        # constructing slash commands from arbitrary natural-language input.
        if p_norm in ('mostre seus comandos', 'mostra seus comandos'):
            p_low = p_norm = '/help'

        # Read prior user events before this turn is appended by send_command.
        if re.search(r'\b(?:primeira|[uú]ltima)\s+mensagem\b', p_norm) and re.search(r'\b(?:mandei|enviei|escrevi)\b', p_norm):
            messages = [m.get('text', '') for m in getattr(self, '_chat_history', [])
                        if m.get('role') == 'user']
            if not messages:
                return {'reply': 'Não há mensagem anterior do usuário disponível neste histórico.', 'logs': []}
            selected = messages[0] if re.search(r'\bprimeira\s+mensagem\b', p_norm) else messages[-1]
            return {'reply': selected, 'logs': []}

        # A report of a previous failure is not an instruction to operate.
        if re.search(r'\b(?:n[aã]o conseguiu|n[aã]o consegui|n[aã]o funcionou)\b', p_norm) and not p_norm.startswith('/'):
            return {'reply': 'Entendi o relato de falha. Nenhuma ação foi iniciada; posso ajudar a diagnosticar com os registros disponíveis.', 'logs': []}

        if intent_contract['negated'] and re.match(r'^\s*(?:n[aã]o|nunca)\s+(?:abra|abre|abrir|inicie|execute|clique|click|digite)\b', p_norm):
            result = {'reply': 'Entendido. Não executarei essa ação.', 'logs': [], 'intent_contract': intent_contract}
            if conceptual_analysis is not None:
                result['conceptual_analysis'] = conceptual_analysis
            return result

        if re.search(r'(?:o que deu errado|por que (?:a )?a[cç][aã]o falhou|a[cç][aã]o falhou)', p_norm):
            event = getattr(self, '_last_task_event', None)
            blackbox = getattr(getattr(self._kernel, 'blackbox', None), 'buffer_circular', ())
            last_failure = next((item for item in reversed(list(blackbox)) if isinstance(item, dict)), None)
            if event and event.get('failure_reason'):
                return {'reply': f"Última falha registrada: {event['failure_reason']}. Tarefa: {event['task']}. Etapa: {event.get('step') or 'não identificada'}.", 'logs': []}
            if last_failure:
                reason = last_failure.get('motivo_punicao') or 'motivo não disponível'
                return {'reply': f"A Caixa Preta registra uma falha: {reason}. A etapa e a relação com a tarefa atual precisam ser confirmadas.", 'logs': []}
            return {'reply': 'Não encontrei evidência de falha nesta sessão. Faltam o identificador da execução e os registros anteriores para um diagnóstico.', 'logs': []}

        if re.match(r'^\s*(?:tente novamente de outro jeito|continue de onde parou)', p_norm):
            return {'reply': 'Para retomar com segurança, preciso revalidar o contexto e o plano da última tarefa; a retomada automática ainda não está disponível.', 'logs': []}

        # Desperta a IA imediatamente se ela estiver em sono REM
        if self._kernel.esta_dormindo:
            self._kernel.esta_dormindo = False
            self._push_event("aios:message", {"role": "ai", "text": "⚡ **Acordando!** Processando seu comando..."})
            self._falar_seguro("Acordando. Processando seu comando.")
        self._kernel.ultimo_toque_ai = time.time()

        if self._window:
            try:
                self._window.evaluate_js("if(document.activeElement) document.activeElement.blur();")
            except Exception:
                pass

        # Conversational messages must not replace the last operational task.
        operational = (not prompt_raw.startswith('/') and
                       (intent_contract.get('intent_kind') in ('OPEN_APP', 'COMPOUND') or
                        intent_contract.get('action') == 'CLICK' or
                        bool(re.match(r'^\s*(?:pinte|desenhe|clique|arraste|digite|feche|pesquise|inicie|execute)\b', p_norm))))
        if operational:
            self._last_executed_task = prompt_raw

        from adaptive_resource_controller import current_task_budget
        task_budget = current_task_budget.get()
        task_id = task_budget.task_id if task_budget else uuid.uuid4().hex
        if operational:
            self._last_task_event = {'task_id':task_id, 'task':prompt_raw, 'status':'STARTED', 'failure_reason':None, 'step':None}
        situation_token = _situation_task.set(task_id)
        try:
            self._kernel.record_situation_event(task_id, 'task_started', intent=intent_contract.get('action'))
        except Exception:
            logger.debug('Memória situacional indisponível', exc_info=True)
        try:
            resultado = self._executar_comando_interno(prompt_raw, p_low, p_norm)
            visual = resultado.get('visual_result')
            if operational and isinstance(visual, dict):
                trace = visual.get('trace') or []
                last = trace[-1] if trace and isinstance(trace[-1], dict) else {}
                feedback = last.get('feedback') if isinstance(last.get('feedback'), dict) else {}
                reason = visual.get('failure_reason') or feedback.get('failure_reason')
                self._last_task_event.update(status=visual.get('status','UNKNOWN'),
                    failure_reason=reason if visual.get('sucesso_real') is not True else None,
                    step=last.get('action_type'))
            if isinstance(visual, dict) and visual.get('sucesso_real') is True and visual.get('goal_state') == 'GOAL_VERIFIED':
                try:
                    self._kernel.record_situation_event(task_id, 'goal_verified', verified=True)
                except Exception:
                    logger.debug('Memória situacional indisponível', exc_info=True)
        except BaseException:
            if operational:
                self._last_task_event.update(status='FAILED', failure_reason='A execução levantou uma exceção; detalhes adicionais não foram registrados.')
            try:
                self._kernel.record_situation_event(task_id, 'task_failed')
            except Exception:
                logger.debug('Memória situacional indisponível', exc_info=True)
            raise
        finally:
            try:
                self._kernel.record_situation_event(task_id, 'task_finished')
            except Exception:
                logger.debug('Memória situacional indisponível', exc_info=True)
            _situation_task.reset(situation_token)
        resultado['intent_contract'] = intent_contract
        if conceptual_analysis is not None:
            resultado['conceptual_analysis'] = conceptual_analysis
        resposta_texto = resultado.get("reply", "")

        return resultado

    def _prepare_contextual_scene(self, descriptor):
        """Reobserve a named UIA target; this is evidence, never authorization."""
        name = descriptor.get('name')
        if not name or not descriptor.get('runtime_id'):
            return {'status': 'ACTION_BLOCKED', 'reason': 'Identidade do alvo incompleta.'}
        for attempt in range(2):
            try:
                observation = self._kernel.observe_ui_scene(target=name, required=True)
                scene = observation.get('scene') or {}
                app = scene.get('app') or {}
                assessment = observation.get('target_assessment') or {}
                now = time.monotonic()
                age = now - scene.get('observed_at', float('-inf'))
                elements = [e for e in scene.get('elements', []) if str(e.get('name', '')).casefold() == str(name).casefold()]
                reference = str(descriptor['runtime_id'])
                matched = (len(elements) == 1 and any(e.get('source') == 'UIA' and e.get('reference') == reference
                           for e in elements[0].get('evidence', [])))
                frame = scene.get('frame') or {}
                rect = frame.get('window_rect')
                valid_rect = isinstance(rect, (tuple, list)) and len(rect) == 4 and rect[0] < rect[2] and rect[1] < rect[3]
                if (observation.get('status') == 'OBSERVED' and scene.get('observation_id') and app.get('hwnd') == descriptor.get('hwnd')
                        and app.get('pid') == descriptor.get('pid') and app.get('process_started') == descriptor.get('process_started')
                        and 0 <= age <= 5 and valid_rect and matched
                        and assessment.get('recommendation') == 'REVALIDATE_BEFORE_ACTION'):
                    return {'status': 'READY', 'scene_id': scene.get('observation_id'), 'attempts': attempt + 1}
            except Exception:
                pass
        return {'status': 'ACTION_BLOCKED', 'reason': 'Cena indisponível, alterada, alvo ausente ou ambíguo após reobservação.'}

    def _budgeted_conversation(self, prompt, *, return_result=False):
        """Main conversational inference; no retry or implicit backend fallback."""
        from adaptive_resource_controller import current_task_budget, BudgetExhausted
        from inference_backend import HTTPInferenceBackend, InferenceRequest, InferenceResult
        budget = current_task_budget.get()
        if budget is None:
            raise RuntimeError('Contexto da tarefa indisponível')
        limits = _EFFORT_LIMITS[budget.reasoning_mode]
        operation_id = budget.begin_inference(estimated_tokens=limits['num_predict'])
        remaining = budget.deadline_monotonic - time.monotonic()
        if remaining <= 0 or budget.cancellation_event.is_set():
            budget.cancellation_event.set()
            budget.finish_inference(operation_id)
            raise BudgetExhausted('Prazo ou cancelamento antes da inferência')
        settings = _conversation_for_command.get() or self.get_conversation_status()
        model = settings['model']
        if settings['profile'] == 'LIVRE':
            prompt = ('Responda de forma direta e completa; indique incertezas e não afirme ações ou fatos sem evidência.\n' + prompt)
        budget.record_inference('ollama', model, 'INFERENCE_RUNNING')
        self._push_event('aios:reasoning', {'task_id': budget.task_id, 'source': 'BrainnetBridge._budgeted_conversation',
                         'timestamp': time.time(), 'state': 'INFERENCE_RUNNING', 'kind': 'model_selected',
                         'model': model, 'backend': 'ollama', 'native_thinking': 'UNKNOWN'})
        backend = HTTPInferenceBackend(OLLAMA_GENERATE_URL.removesuffix('/api/generate'), model, 'ollama')
        inference_started = time.perf_counter()
        message_id = None
        sequence = 0
        try:
            request = InferenceRequest(prompt=prompt, model=model, request_id=budget.task_id,
                timeout=min(remaining, limits['timeout']), max_tokens=limits['num_predict'],
                context_tokens=limits['num_ctx'])
            if budget.reasoning_mode == 'DEEP' and not return_result:
                message_id = uuid.uuid4().hex
                chunks = []
                sequence = 0
                finish_reason = None
                reported_tokens = None
                for fragment in backend.stream_events(request):
                    budget.check_active()
                    if fragment['channel'] == 'CONTENT': chunks.append(fragment['text'])
                    if fragment['channel'] == 'OPERATIONAL':
                        finish_reason = fragment.get('finish_reason')
                        value = fragment.get('output_tokens')
                        reported_tokens = value if type(value) is int and value >= 0 else None
                    self._push_event('aios:stream', {'task_id': budget.task_id, 'message_id': message_id,
                        'sequence': sequence, 'channel': fragment['channel'], 'text': fragment.get('text', ''),
                        'state': fragment.get('state', 'STREAMING'), 'source': 'HTTPInferenceBackend', 'timestamp':time.time()})
                    sequence += 1
                result = InferenceResult(budget.task_id, model, ''.join(chunks), 'ollama', reported_tokens, None, finish_reason)
            else:
                result = backend.generate(request)
        except Exception as exc:
            if message_id:
                self._push_event('aios:stream', {'task_id':budget.task_id, 'message_id':message_id,
                    'sequence':sequence, 'channel':'OPERATIONAL', 'text':'',
                    'state':'CANCEL_REQUESTED' if budget.cancellation_event.is_set() else 'ERROR',
                    'error_type':type(exc).__name__, 'source':'HTTPInferenceBackend', 'timestamp':time.time()})
            budget.finish_inference(operation_id, confirmed=False)
            budget.record_inference('ollama', model, 'INFERENCE_FAILED')
            self._push_event('aios:reasoning', {'task_id': budget.task_id, 'source': 'BrainnetBridge._budgeted_conversation',
                             'timestamp': time.time(), 'state': 'INFERENCE_FAILED', 'kind': 'inference_error',
                             'error_type': type(exc).__name__})
            raise
        budget.finish_inference(operation_id, reported_tokens=getattr(result, 'output_tokens', None))
        if budget.cancellation_event.is_set() or time.monotonic() >= budget.deadline_monotonic:
            budget.cancellation_event.set()
            budget.record_inference('ollama', model, 'CANCEL_REQUESTED')
            raise BudgetExhausted('Prazo ou cancelamento após inferência; resultado não utilizado')
        budget.record_inference(result.backend, result.model, 'INFERENCE_FINISHED')
        self._push_event('aios:reasoning', {'task_id': budget.task_id, 'source': 'BrainnetBridge._budgeted_conversation',
                         'timestamp': time.time(), 'state': 'INFERENCE_FINISHED', 'kind': 'inference_completed',
                         'model': result.model, 'backend': result.backend,
                         'duration_ms': round((time.perf_counter()-inference_started)*1000, 1),
                         'output_tokens': getattr(result, 'output_tokens', None)})
        if return_result:
            return result
        text = result.text.strip()
        _conversation_finish_reason.set(getattr(result, 'finish_reason', None))
        if getattr(result, 'finish_reason', None) in ('length', 'max_tokens'):
            text += '\n\n⚠️ Resposta interrompida pelo limite de geração.'
        return text

    def _write_long_draft(self, goal, *, resume_id=None):
        from adaptive_resource_controller import current_task_budget
        from long_workflows import BookDraft
        budget = current_task_budget.get()
        if budget is None:
            return {'reply': 'Não há contexto de tarefa para gerar o texto.', 'logs': [], 'status': 'INCOMPLETE'}
        directory = Path(__file__).resolve().parent / 'long_drafts'
        directory.mkdir(exist_ok=True)
        draft_id = resume_id or budget.task_id
        if not re.fullmatch(r'[0-9a-f]{32}', draft_id):
            return {'reply':'Identificador de rascunho inválido.', 'logs':[], 'status':'INCOMPLETE'}
        destination = directory / (draft_id + '.json')
        if resume_id:
            try:
                draft = BookDraft.restore(destination.read_text(encoding='utf-8'))
            except (OSError, ValueError, KeyError, TypeError):
                return {'reply':'Rascunho indisponível ou inválido.', 'logs':[], 'status':'INCOMPLETE'}
        else:
            draft = BookDraft(goal, ['Introdução', 'Desenvolvimento', 'Conclusão'])
        def checkpoint(value):
            temporary = destination.with_suffix('.tmp')
            temporary.write_text(value.serialize(), encoding='utf-8')
            temporary.replace(destination)
        def emit(index, text):
            self._push_event('aios:long_section', {'task_id': draft_id, 'index': index, 'text': text})
        state = draft.generate_sections(lambda prompt: self._budgeted_conversation(prompt, return_result=True),
                                        checkpoint, cancelled=budget.cancellation_event.is_set, emit=emit)
        text='\n\n'.join(c['text'] for c in draft.chapters if c['text'])
        suffix='Rascunho gerado; fatos e coerência não foram verificados.' if state == 'DRAFT_COMPLETE' else 'Geração incompleta; o rascunho foi preservado.'
        return {'reply': (text + '\n\n' if text else '') + suffix, 'logs': [], 'status': state,
                'long_task_id': draft_id, 'incomplete': state != 'DRAFT_COMPLETE'}

    def _get_kiwix_hmem(self):
        from contextlib import nullcontext
        lock = getattr(self._kernel, '_situation_lock', None)
        with lock if lock is not None else nullcontext():
            existing = getattr(self._kernel, '_kiwix_hmem', None)
            if existing is not None:
                return existing
            vsa = getattr(self._kernel, 'vsa', None)
            if vsa is None:
                return None
            from hmem_engine import HMemEngine
            self._kernel._kiwix_hmem = HMemEngine(vsa)
            return self._kernel._kiwix_hmem

    def _executar_comando_interno(self, prompt_raw: str, p_low: str, p_norm: str) -> Dict[str, Any]:
        from adaptive_resource_controller import current_task_budget
        if p_norm.startswith('/offline-ref '):
            from kiwix_knowledge import KiwixKnowledge, recall_reference
            reference_id = prompt_raw[len('/offline-ref '):].strip()
            if not re.fullmatch(r'HND_\d+_\d+', reference_id):
                return {'reply':'Identificador de referência inválido.', 'logs':[], 'status':'INVALID_REFERENCE'}
            memory = self._get_kiwix_hmem()
            if memory is None:
                return {'reply':'Memória episódica indisponível.', 'logs':[], 'status':'MEMORY_UNAVAILABLE'}
            knowledge = getattr(self, '_kiwix_knowledge', None)
            if knowledge is None:
                knowledge = self._kiwix_knowledge = KiwixKnowledge(Path(__file__).resolve().parent.parent / 'knowledge' / 'zim')
            from contextlib import nullcontext
            lock = getattr(self._kernel, '_situation_lock', None)
            with lock if lock is not None else nullcontext():
                result = recall_reference(knowledge, memory, reference_id)
            messages = {'SOURCE_MISSING':'O arquivo ZIM original não está disponível.',
                        'SOURCE_CHANGED':'O arquivo ZIM foi alterado; faça uma nova consulta.',
                        'SOURCE_UNAVAILABLE':'Não foi possível ler a fonte original.',
                        'REFERENCE_NOT_FOUND':'Referência não encontrada.'}
            return {'reply':result.get('reply', messages.get(result['status'], 'Fonte indisponível.')),
                    'logs':[], 'status':result['status'], 'reference_id':reference_id,
                    'sources':[result['source']] if 'source' in result else []}
        if p_norm.startswith('/offline '):
            from kiwix_knowledge import KiwixKnowledge, record_reference
            directory = Path(__file__).resolve().parent.parent / 'knowledge' / 'zim'
            knowledge = getattr(self, '_kiwix_knowledge', None)
            if knowledge is None:
                knowledge = self._kiwix_knowledge = KiwixKnowledge(directory)
            available = [x for x in knowledge.catalog() if x.get('status') == 'AVAILABLE']
            if not available:
                return {'reply':'Nenhum arquivo ZIM local disponível em knowledge/zim.', 'logs':[], 'status':'NOT_FOUND'}
            query = prompt_raw[len('/offline '):].strip()
            selected, separator, query_part = query.partition('::')
            if separator:
                filename = selected.strip()
                query = query_part.strip()
                if filename not in {item['file'] for item in available}:
                    return {'reply':'Arquivo ZIM selecionado não está disponível.', 'logs':[], 'status':'NOT_FOUND'}
            elif len(available) != 1:
                return {'reply':'Há vários arquivos ZIM. Use /offline arquivo.zim :: consulta.', 'logs':[], 'status':'AMBIGUOUS'}
            else:
                filename = available[0]['file']
            try:
                result = knowledge.answer(filename, query)
                reference_id = None
                if result['sources']:
                    budget = current_task_budget.get()
                    memory = getattr(self._kernel, 'situation_memory', None)
                    hmem = self._get_kiwix_hmem()
                    from contextlib import nullcontext
                    lock = getattr(self._kernel, '_situation_lock', None)
                    with lock if lock is not None else nullcontext():
                        reference_id = record_reference(result['sources'][0], journal_directory=Path(__file__).resolve().parent / 'development_logs',
                            memory=memory if getattr(memory, 'enabled', False) is True else None,
                            task_id=budget.task_id if budget else None, hmem=hmem)
                    if hmem is None:
                        reference_id = None
                        result['reply'] += '\nMemória episódica indisponível; a fonte não pode ser retomada por ID.'
                    else:
                        result['reply'] += '\nReferência: ' + reference_id
                return {'reply':result['reply'], 'logs':[], 'status':result['status'], 'sources':result['sources'], 'reference_id':reference_id}
            except Exception as exc:
                return {'reply':'Não foi possível consultar o arquivo ZIM local.', 'logs':[], 'status':'SOURCE_ERROR', 'error_type':type(exc).__name__}
        if p_norm in ("/help", "/?", "/ajuda"):
            from command_catalog import render_help
            return {"reply": render_help(self._kernel), "logs": []}

        # Natural and slash search share the existing read-only source discovery.
        search = re.match(r'^/?(?:pesquise|pesquisa|pesquisar|busque|buscar|search)\s+(.+)$', prompt_raw.strip(), re.I | re.S)
        if search and not re.search(r'\s+e\s+(?:abra|digite|escreva|salve|clique)\b', search.group(1), re.I):
            query = search.group(1).strip()
            found = self.web_search_autonomous(query)
            sources = found.get('results') or []
            if not sources:
                return {'reply': 'Não encontrei fontes suficientes para verificar essa pesquisa.', 'logs': [], 'search_state': 'SEARCH_STARTED'}
            lines = [f"• {item.get('title', '')} — {item.get('url', '')}" for item in sources[:5]]
            return {'reply': 'Fontes encontradas; o conteúdo e as afirmações ainda não foram verificados:\n' + '\n'.join(lines),
                    'logs': [], 'search_state': 'SOURCES_FOUND', 'sources': sources[:5]}
        # MSS indices do not necessarily match the labels shown by Windows.
        if re.match(r'^\s*(?:o que|descreva|leia|veja|e a|e o)\b', p_norm) and re.search(r'\b(?:tela|monitor)\s*[12]\b', p_norm):
            return {'reply':'Não consigo confirmar qual índice de captura corresponde ao número exibido pelo Windows. Preciso dessa identificação para descrever a tela solicitada.', 'logs':[]}
        if re.search(r'\b(?:duas|ambas as)\s+telas\b', p_norm):
            try:
                geometry = self._kernel.vision.obter_geometria_monitores()
                indices = sorted(int(key[1:]) for key in geometry if re.fullmatch(r'm\d+', key))
                if len(indices) < 2:
                    return {'reply':'Não foi possível identificar duas telas independentes.', 'logs':[]}
                descriptions=[]
                for index in indices[:2]:
                    try:
                        text = self._kernel.vision.descrever_tela('Descreva apenas o que está visível.', monitor_alvo=index)
                        descriptions.append(f"Índice MSS {index} ({time.strftime('%Y-%m-%d %H:%M:%S')}): {text}")
                    except Exception:
                        descriptions.append(f'Índice MSS {index}: captura ou análise indisponível.')
                return {'reply':'\n'.join(descriptions)+'\nA correspondência com os números do Windows não foi confirmada.', 'logs':[]}
            except Exception:
                return {'reply':'Não foi possível identificar os monitores.', 'logs':[]}
        from contextual_grounder import parse_click
        from system_intent import system_launch_target
        literal_app = system_launch_target(prompt_raw)
        if literal_app and re.match(r'^\s*(?:abra|abre|abrir|inicie|execute)\b', prompt_raw, re.I):
            self._contextual_grounder.context = None
        click_intent = parse_click(prompt_raw)
        if click_intent:
            result = self._contextual_grounder.resolve(click_intent)
            if result.get('status') == 'READY_FOR_UIA':
                scene_check = self._prepare_contextual_scene(result['target_descriptor'])
                if scene_check['status'] != 'READY':
                    return {'reply': f"ACTION_BLOCKED: {scene_check['reason']}", 'logs': [], 'contextual_result': scene_check}
                from execution_authority import command_authority
                from uia_control_executor import last_input_snapshot
                @command_authority
                def execute_contextual():
                    baseline = last_input_snapshot()
                    if baseline is None:
                        return {'status':'ACTION_BLOCKED','reason':'Atividade do usuario indisponivel.'}
                    payload={'target':result['target_descriptor'],'intent':'CLICK','baseline_input':baseline}
                    async def dispatch():
                        bridge=self._kernel.bridge
                        owned=not bridge._running
                        if owned: await bridge.start()
                        try: return await bridge.dispatch('activate_ui_control',payload)
                        finally:
                            if owned: await bridge.stop()
                    loop=self._kernel.loop
                    if loop and loop.is_running():
                        try:
                            if asyncio.get_running_loop() is loop:
                                return {'status':'ACTION_BLOCKED','reason':'Nao e possivel bloquear o loop do Kernel.'}
                        except RuntimeError: pass
                        future=asyncio.run_coroutine_threadsafe(dispatch(),loop)
                        try: command=future.result(timeout=15)
                        except Exception:
                            token = current_authorization()
                            if token is not None:
                                token.set()
                            future.cancel()
                            raise
                    else: command=asyncio.run(dispatch())
                    return command.result if command.status=='completed' and isinstance(command.result,dict) else {
                        'status':'ACTION_BLOCKED','reason':command.error or 'Atuador indisponivel.'}
                try: result=execute_contextual()
                except Exception as exc: result={'status':'ACTION_BLOCKED','reason':f'Atuador indisponivel: {type(exc).__name__}'}
            elif result.get('status') == 'TARGET_NOT_FOUND':
                result['visual_fallback']={'status':'REQUIRES_EXPLICIT_AUTHORIZATION','automatic':False}
            return {'reply': f"{result['status']}: {result['reason']}", 'logs': [], 'contextual_result': result}
        # --- INÍCIO DO HOOK DE VISÃO-AÇÃO (UI-TARS) ---
        # Desvia comandos que exigem interação visual (pintar, clicar, alterar)
        # para o cérebro visual (qwen3-vl:8b) em vez de tentar achar macros.
        visual_actions = ["clique", "pinte", "desenhe", "altere", "colorir", "arraste", "botao", "botão", "icone"]
        if any(w in p_low for w in visual_actions) and not p_norm.startswith('/'):
            # P03: Roteamento Composto
            if " e " in prompt_raw:
                parts = prompt_raw.split(" e ", 1)
                cmd1, cmd2 = parts[0].strip(), parts[1].strip()
                if re.match(r'^\s*(?:abra|abre|abrir|inicie)\b', cmd1, re.I):
                    self._push_event("aios:message", {"role": "ai", "text": f"⚙️ Passo 1: {cmd1}"})
                    fut = None
                    try:
                        # P03-FIX-2: Usa o asyncio global. Timeout reduzido para 15s.
                        loop = self._kernel.loop
                        if loop and loop.is_running():
                            fut = asyncio.run_coroutine_threadsafe(
                                self._kernel.trajectory_engine.executar_trajetoria_completa(cmd1), loop
                            )
                            res_abrir = fut.result(timeout=15.0)
                        else:
                            res_abrir = asyncio.run(self._kernel.trajectory_engine.executar_trajetoria_completa(cmd1))
                            
                        if res_abrir.get("status") not in ("CONCLUIDO", "SUCESSO_MIELINIZADO"):
                            return {"reply": f"❌ Falha no passo 1 ({cmd1}): {res_abrir.get('status')}", "logs": []}
                    except TimeoutError:
                        token = current_authorization()
                        if token is not None:
                            token.set()
                        if fut is not None:
                            fut.cancel()
                        return {"reply": "❌ Tempo limite no primeiro passo; autorização será revogada.", "logs": []}
                    except Exception as e:
                        return {"reply": f"❌ Erro no passo 1: {e}", "logs": []}
                    prompt_raw = cmd2
                    p_low = cmd2.lower()
                    p_norm = p_low
            self._falar_seguro("Acionando córtex visual.")
            self._push_event("aios:message", {"role": "ai", "text": f"👁️ Analisando a tela para: {prompt_raw}..."})
            future = None
            try:
                # Se o loop assíncrono do Kernel estiver rodando (GUI ativa)
                if self._kernel.loop and self._kernel.loop.is_running():
                    future = asyncio.run_coroutine_threadsafe(
                        self._kernel.ui_protocol.run_task(prompt_raw, max_steps=_EFFORT_LIMITS[_effort_for_command.get()]['visual_steps'], task_budget=current_task_budget.get()), self._kernel.loop
                    )
                    # Timeout aumentado para 180s (cold start do VLM na RX580)
                    res = future.result(timeout=180)
                else:
                    # No terminal o Kernel nao iniciou os workers da ponte de atuacao.
                    async def _run_visual_terminal():
                        bridge = self._kernel.bridge
                        if bridge._running:
                            raise RuntimeError("Ponte de atuacao ja ativa sem loop do Kernel; reinicie o Kernel.")
                        await bridge.start()
                        try:
                            return await self._kernel.ui_protocol.run_task(prompt_raw, max_steps=_EFFORT_LIMITS[_effort_for_command.get()]['visual_steps'], task_budget=current_task_budget.get())
                        finally:
                            await bridge.stop()
                    res = asyncio.run(_run_visual_terminal())
                
                status = res.get("status", "DESCONHECIDO")
                trace = res.get("trace") or []
                feedback = trace[-1].get("feedback", {}) if trace else {}
                reason = feedback.get("failure_reason") or res.get("failure_reason") or ""
                success = res.get("sucesso_real") is True
                icon = "✅" if success else "⚠️"
                detail = f"\nDetalhe: {reason}" if reason else ""
                return {"reply": f"{icon} **Ação Visual:** {status}{detail}", "logs": [], "visual_result": res}
                
            except TimeoutError:
                token = current_authorization()
                if token is not None:
                    token.set()
                if future is not None:
                    future.cancel()
                logger.error("[VISION-ACTION] Timeout; cancelamento solicitado e autorizacao sera revogada.")
                return {"reply": "❌ **Timeout:** cancelamento solicitado; o término da tarefa ainda não foi confirmado.", "logs": []}
            except Exception as e:
                err_name = type(e).__name__
                err_msg = str(e) or "Sem detalhes"
                logger.error(f"[VISION-ACTION] Falhou: {err_name} - {err_msg}")
                return {"reply": f"❌ Falha visual ({err_name}): {err_msg}", "logs": []}
        # --- FIM DO HOOK DE VISÃO-AÇÃO ---

        ctx_agora = self._kernel.context_engine.capture_foreground_context()

        if os.getenv('BRAINNET_PROCEDURAL_PROPOSALS') == '1' and isinstance(ctx_agora, dict):
            try:
                key = f"trajectory:{prompt_raw.lower().strip()[:40]}"
                proposal = self._kernel.pdag.propose_verified_procedure(key, ctx_agora)
                if proposal is not None:
                    ctx_agora = dict(ctx_agora)
                    ctx_agora['procedural_proposal'] = proposal
            except Exception:
                logger.debug('Consulta procedural indisponível', exc_info=True)

        task_id = _situation_task.get()
        if task_id and isinstance(ctx_agora, dict):
            try:
                evidence = self._kernel.read_situation_evidence(task_id)
                if evidence is not None:
                    ctx_agora = dict(ctx_agora)
                    ctx_agora['situation_evidence'] = evidence
            except Exception:
                logger.debug('Leitura situacional indisponível', exc_info=True)

        # ----------------------------------------------------------------------
        # 1. TEORIA DA MENTE (mPFC) & GÂNGLIOS DA BASE (GO / NO-GO)
        # V9.5-FIX: Fim do dicionário de bypass. Usa o Router Semântico.
        try:
            _route = self._kernel.router.evaluate_route(prompt_raw, ctx_agora)
            _is_operational = (_route.mode == "DETERMINISTIC_ACTION")
        except Exception as e:
            logger.debug(f"[ROUTER] Falha ao classificar intenção: {e}")
            _is_operational = False

        if _is_operational:
            julgamento = MentalizingJudgment(
                gate=MotorGateState.GO, intended_goal=prompt_raw,
                underlying_meaning="Comando classificado como OPERACIONAL pelo Semantic Router.",
                is_physical_world=False, requires_social_dialogue=False, confidence_evidence=1.0,
                explanation_to_user="Acionando motor."
            )
        else:
            julgamento = self._tom.evaluate_intent(prompt_raw, ctx_agora)

        if julgamento.gate == MotorGateState.NO_GO and julgamento.is_physical_world:
            self._falar_seguro(julgamento.explanation_to_user)
            return {"reply": julgamento.explanation_to_user, "logs": [{"level": "INFO", "core": "TheoryOfMind", "msg": "Afeto acolhido."}]}

        if julgamento.gate == MotorGateState.PRAGMATIC_REJECT:
            self._falar_seguro(julgamento.explanation_to_user)
            return {
                "reply": f"🛑 **Comando Rejeitado por Inviabilidade Pragmática:**\n\n{julgamento.explanation_to_user}",
                "logs": [{"level": "WARN", "core": "TheoryOfMind", "msg": julgamento.underlying_meaning}]
            }

        if julgamento.gate == MotorGateState.CLARIFICATION:
            self._falar_seguro(julgamento.explanation_to_user)
            return {
                "reply": f"🤔 **Esclarecimento Necessário:**\n\n{julgamento.explanation_to_user}",
                "logs": [{"level": "INFO", "core": "TheoryOfMind", "msg": "Ambiguidade detectada"}]
            }

        # ----------------------------------------------------------------------
        # 2. CANAL DE FEEDBACK FACTUAL E COMANDOS SLASH
        # ----------------------------------------------------------------------
        if p_norm.startswith(("/report", "/repot", "/repor", "/falha")):
            explicacao = re.sub(r"^/(?:report|repot|repor|falha)\s*", "", prompt_raw, flags=re.IGNORECASE).strip() or "Erro relatado pelo operador"
            tarefa_falha = self._last_executed_task or "última ação executada"

            ctx_hash = self._kernel.pdag.hash_context(f"trajectory:{tarefa_falha.lower().strip()[:40]}")
            with self._kernel.pdag._conn:
                self._kernel.pdag._conn.execute(
                    "UPDATE habits SET myelination_weight = MAX(0.1, myelination_weight - 0.5), is_myelinated = 0 WHERE context_hash = ?;",
                    (ctx_hash,)
                )

            snap = self._kernel.blackbox.registrar_falha_e_punir(
                intencao_original=tarefa_falha,
                acao_executada={"tipo": "USER_REPORT"},
                estado_esperado={"conclusao": True},
                estado_observado={"feedback": explicacao},
                motivo_punicao=explicacao
            )
            cura = self._kernel.blackbox.disparar_auto_cura(snap)

            resp_report = (
                f"🛑 **Falha Gravada no P-DAG (SQLite WAL):**\n"
                f"• **Tarefa:** '{tarefa_falha}'\n"
                f"• **Seu Feedback:** '{explicacao}'\n"
                f"• **Penalidade Factual:** Aresta rebaixada no banco de dados e rota desmielinizada.\n"
                f"• **Diagnóstico Causal:** {cura.get('causa_raiz', 'Causa aprendida e isolada no P-DAG')}."
            )
            self._falar_seguro("Falha registrada no banco de dados e rota desmielinizada.")
            return {"reply": resp_report, "logs": [{"level": "WARN", "core": "P-DAG", "msg": f"Punido: {tarefa_falha}"}]}

        if p_norm in ("/certo", "/correto", "/perfeito", "/certo!") or p_norm.startswith("/certo"):
            tarefa_acerto = self._last_executed_task or "última ação executada"
            ctx_hash = self._kernel.pdag.hash_context(f"trajectory:{tarefa_acerto.lower().strip()[:40]}")
            with self._kernel.pdag._conn:
                self._kernel.pdag._conn.execute(
                    "UPDATE habits SET myelination_weight = myelination_weight + 2.0, consecutive_successes = consecutive_successes + 2, is_myelinated = 1 WHERE context_hash = ?;",
                    (ctx_hash,)
                )
            resp_certo = f"🌟 **Mielinização Confirmada no SQLite!**\n• Tarefa: '{tarefa_acerto}'\n• Status: Rota consolidada como reflexo estático Zero-LLM (<2ms)."
            self._falar_seguro("Hábito mielinizado com sucesso.")
            return {"reply": resp_certo, "logs": [{"level": "INFO", "core": "P-DAG", "msg": f"Mielinizado: {tarefa_acerto}"}]}

        if p_norm.startswith(("/esquecer", "/purge", "/limpar")):
            termo = re.sub(r"^/(?:esquecer|purge|limpar)\s*", "", prompt_raw, flags=re.IGNORECASE).strip()
            with self._kernel.pdag._conn:
                if not termo or termo.lower() in ("tudo", "all", "cache"):
                    self._kernel.pdag._conn.execute("DELETE FROM habits;")
                    self._kernel.pdag._conn.execute("VACUUM;")
                    msg_esq = "🧹 **Memória Sináptica Resetada**: Todos os hábitos foram expurgados do SQLite."
                else:
                    cur = self._kernel.pdag._conn.execute("DELETE FROM habits WHERE intent LIKE ?;", (f"%{termo}%",))
                    self._kernel.pdag._conn.execute("VACUUM;")
                    msg_esq = f"✂️ **Sinaptectomia**: {cur.rowcount} rota(s) contendo '{termo}' foram expurgadas."
            self._falar_seguro("Memória sináptica expurgada.")
            return {"reply": msg_esq, "logs": []}

        if p_norm in ("/switch mode", "/modo"):
            self._modo_operacao = "CONSENSO" if self._modo_operacao == "TRAJETORIA" else "TRAJETORIA"
            msg_modo = f"🛡️ **Modo Alterado para:** `{self._modo_operacao}`."
            self._falar_seguro(f"Modo alterado para {self._modo_operacao}.")
            return {"reply": msg_modo, "logs": []}

        if p_norm in ("/rem parar", "/rem stop", "/acordar"):
            self._kernel.esta_dormindo = False
            self._falar_seguro("Sono REM interrompido. Estou acordada.")
            return {"reply": "⚡ **Sono REM Interrompido:** Organismo desperto e pronto para comandos.", "logs": []}
# COMANDOS DO MODO TREINAMENTO CONTÍNUO (FRENTE 2)
        if p_norm in ("/treino on", "/treino start", "/treinar", "/iniciar treino"):
            if self._kernel.harvester:
                msg_harv = self._kernel.harvester.start()
                self._falar_seguro("Modo de treinamento autônomo ativado em segundo plano.")
                return {"reply": msg_harv, "logs": [{"level": "INFO", "core": "Harvester", "msg": "Treinamento iniciado"}]}
            return {"reply": "⚠️ Módulo de Harvester não disponível no Kernel.", "logs": []}

        if p_norm in ("/treino off", "/treino stop", "/parar treino"):
            if self._kernel.harvester:
                msg_harv = self._kernel.harvester.stop()
                self._falar_seguro("Modo de treinamento pausado.")
                return {"reply": msg_harv, "logs": [{"level": "INFO", "core": "Harvester", "msg": "Treinamento desativado"}]}
            return {"reply": "⚠️ Módulo de Harvester não disponível no Kernel.", "logs": []}

        if p_norm in ("/treino status", "/status treino", "/treinamento"):
            if self._kernel.harvester:
                st = self._kernel.harvester.get_status()
                st_txt = "🟢 **Ativo** (Minerando na Web)" if st["ativo"] else "🔴 **Inativo** (Pausado)"
                corpo_st = (
                    f"🌾 **Status da Colheita Autônoma (Harvester):**\n"
                    f"• **Estado:** {st_txt}\n"
                    f"• **Conceitos Absorvidos em 10.000D:** `{st['conceitos_minerados']}`\n"
                    f"• **Pressão de Hardware:** RAM `{st['ram_pct']}%` | CPU `{st['cpu_pct']}%`\n"
                    f"• **Último Registro:** *{st['ultimo_log']}*"
                )
                return {"reply": corpo_st, "logs": []}
            return {"reply": "⚠️ Harvester offline.", "logs": []}
        if p_norm in ("/rem status", "/sono status"):
            st_sono = "😴 Dormindo (Processando em segundo plano)" if self._kernel.esta_dormindo else "⚡ Acordada (Atenta ao operador)"
            inatividade_s = int(time.time() - self._kernel.ultimo_toque_ai)
            return {
                "reply": (
                    f"🌙 **Status Circadiano:**\n• Estado: {st_sono}\n"
                    f"• Inatividade da IA: `{inatividade_s}s` (Dorme aos 180s sem interação)\n"
                    f"• Ruído de Fase Ativo: `σ = 0.15π (~0.471 rad)` aplicado nas fases complexas em C^10.000."
                ),
                "logs": []
            }

        if p_norm.startswith("/rem"):
            if not getattr(self._kernel, 'rem_maintenance_enabled', False):
                return {'reply': 'Manutenção REM desativada; requer revisão e autorização específica.', 'logs': [], 'status': 'UNAVAILABLE'}
            def _rem_th():
                self._kernel.rem_engine.execute_full_rem_cycle()
                self._kernel.rem_engine.dream_and_immunize_ui_drifts(self._kernel.vsa)
            threading.Thread(target=_rem_th, daemon=True).start()
            self._falar_seguro("Sono REM e vacinação estocástica iniciados.")
            return {"reply": "🌙 **Sono REM Ativado**: Poda sináptica e vacina de UI iniciadas.", "logs": []}

        if p_norm in ("/code", "/code on"):
            self._modo_coder_ativo = True
            return {"reply": "⚡ **Modo Coder 7B Ativado.**", "logs": []}
        if p_norm in ("/code exit", "/code off"):
            self._modo_coder_ativo = False
            return {"reply": "Modo Coder desativado.", "logs": []}

        if self._modo_coder_ativo:
            resp_c = self._processar_ordem_codigo_arquivo(prompt_raw)
            if resp_c:
                return resp_c

        # HISTÓRICO WEB REAL
        if p_norm in ("/logs web", "/log web", "/historico web", "/historico-web"):
            with sqlite3.connect(self._kernel.pdag.db_path) as conn:
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='hd_web_memory';")
                if not cur.fetchone():
                    return {"reply": "📋 Nenhuma pesquisa web registrada na hiperdimensão ainda.", "logs": []}
                cur.execute("SELECT query, title, url, salience_score, created_at FROM hd_web_memory ORDER BY created_at DESC LIMIT 8;")
                linhas = cur.fetchall()

            if not linhas:
                return {"reply": "📋 Nenhuma pesquisa recente localizada.", "logs": []}

            lista_fmt = ["🌐 **Últimas Pesquisas Web Gravadas na Hiperdimensão (e no Histórico do Thorium):**\n"]
            for q, t, u, s, ts in linhas:
                hora = time.strftime('%H:%M:%S', time.localtime(ts))
                lista_fmt.append(f"• `[{hora}]` **{q.upper()}** (Densidade: `{s}`)\n  ↳ Título: *{t[:60]}*\n  ↳ URL: `{u[:65]}...`")

            return {"reply": "\n".join(lista_fmt), "logs": []}

        # PESQUISA MULTI-ABA FACTUAL (ACEITA /pesquise, /pesquisa, /busque, /buscar, /search)
        if p_norm.startswith(("/pesquisa ", "/pesquisar ", "/pesquise ", "/busque ", "/buscar ", "/search ")):
            termo = re.sub(r"^/(?:pesquisa|pesquisar|pesquise|busque|buscar|search)\s*", "", prompt_raw, flags=re.IGNORECASE).strip()
            if len(termo) < 2:
                return {"reply": "Informe o assunto da pesquisa. Ex: `/pesquise o que é física de partículas`", "logs": []}

            self._falar_seguro(f"Iniciando pesquisa factual sobre {termo}. Abrindo abas reais no Thorium.")
            res_multi = self._kernel.browser_bridge.deep_multi_tab_research(termo)
            if not res_multi.get("ok"):
                return {"reply": f"⚠️ **Falha na Navegação:** {res_multi.get('error')}", "logs": []}

            prompt_res = (
                f"Você é a BRAINNET v7. Com base nos textos extraídos das abas reais do navegador abaixo sobre '{termo}', "
                f"escreva uma explicação detalhada e estruturada com os principais pontos descobertos.\n\n"
                f"{res_multi['texto_total'][:3000]}\n\nResposta:"
            )
            try:
                req = urllib.request.Request(
                    OLLAMA_GENERATE_URL,
                    data=json.dumps({"model": "qwen2.5:1.5b", "prompt": prompt_res, "stream": False, "options": {"temperature": 0.3, "num_predict": 450}}).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=25) as r:
                    resumo_final = json.loads(r.read().decode("utf-8")).get("response", "").strip()
            except Exception:
                resumo_final = f"Conteúdo sobre '{termo}' absorvido com sucesso das abas abertas."

            self._falar_seguro(resumo_final)
            paginas_txt = "\n".join(f"  • {p}" for p in res_multi["paginas_visitadas"])
            msg_p = (
                f"🌐 **Pesquisa Factual via {res_multi['browser'].title()} Concluída!**\n"
                f"*(Todas as abas foram abertas e constam no histórico `Ctrl + H` do navegador).*\n\n"
                f"📑 **Páginas e Fontes Mapeadas:**\n{paginas_txt}\n\n"
                f"🧠 **Conhecimento Sintetizado:**\n\n{resumo_final}\n\n"
                f"🧬 *Absorvido em C^10.000 (`{res_multi['mem_id']}` | Densidade={res_multi['salience']}) para reciclagem no REM.*"
            )
            return {"reply": msg_p, "logs": []}

        # TRAVA ABSOLUTA DE SEGURANÇA: NENHUM COMANDO INICIADO COM BARRA VAZA PARA O SO!
        if p_norm.startswith("/"):
            return {"reply": f"⚠️ Comando slash '{prompt_raw}' não reconhecido. Digite `/help` para ver os comandos válidos.", "logs": []}

        # ----------------------------------------------------------------------
        # 3. DIAGNÓSTICO RETROSPECTIVO DA CAIXA PRETA
        # ----------------------------------------------------------------------
        if any(p in p_norm for p in ["qual a causa", "qual foi a causa", "por que falhou", "o que houve", "motivo do erro"]):
            if self._kernel.blackbox.buffer_circular:
                snap = self._kernel.blackbox.buffer_circular[-1]
                diag = (
                    f"🔍 **Diagnóstico da Caixa Preta ({snap['snapshot_id']}):**\n"
                    f"• **Tarefa Falha:** '{snap['intencao_original']}'\n"
                    f"• **Causa Apurada:** {snap['motivo_punicao']}\n"
                    f"• **Ação que Falhou:** {json.dumps(snap.get('acao_executada', {}), ensure_ascii=False)}"
                )
                self._falar_seguro(f"A causa registrada foi: {snap['motivo_punicao']}")
                return {"reply": diag, "logs": []}

        # ----------------------------------------------------------------------
        # 4. SENSORES FACTUAIS DO WINDOWS 11 (ZERO ALUCINAÇÃO)
        # ----------------------------------------------------------------------
        if "navegador padr" in p_norm:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice") as key:
                    prog_id, _ = winreg.QueryValueEx(key, "ProgId")
                nav = "Brave Browser" if "Brave" in prog_id else ("Google Chrome" if "Chrome" in prog_id else ("Microsoft Edge" if "Edge" in prog_id else prog_id))
                resp_nav = f"Seu navegador padrão configurado no Windows 11 é o **{nav}** (`{prog_id}`)."
            except Exception:
                resp_nav = "Não foi possível ler a chave de Registro do navegador padrão."
            self._falar_seguro(resp_nav)
            return {"reply": resp_nav, "logs": []}

        if ("menu iniciar" in p_norm or "start menu" in p_norm) and any(a in p_norm for a in ["aplicativo", "app", "programa", "quais", "listar", "tenho"]):
            pastas = [Path(os.environ.get("ProgramData", "")) / "Microsoft\\Windows\\Start Menu\\Programs", Path(os.environ.get("APPDATA", "")) / "Microsoft\\Windows\\Start Menu\\Programs"]
            apps_reais = set()
            for pasta in pastas:
                if pasta.exists():
                    for lnk in pasta.rglob("*.lnk"):
                        nome = lnk.stem
                        if not any(ign in nome.lower() for ign in ["uninstall", "desinstalar", "help", "readme"]):
                            apps_reais.add(nome)
            lista = sorted(list(apps_reais))[:12]
            resp_apps = "Estes são os principais aplicativos reais instalados no seu Menu Iniciar:\n\n" + "\n".join(f"{i+1}. {a}" for i, a in enumerate(lista)) if lista else "Nenhum atalho localizado."
            self._falar_seguro("Listei os aplicativos reais instalados no seu Menu Iniciar.")
            return {"reply": resp_apps, "logs": []}

        if any(j in p_norm for j in ["quais aplicativos estao abertos", "quais aplicativos estão abertos", "quais janelas estao abertas", "quais janelas estão abertas"]):
            janelas = self._kernel.context_engine.escanear_estado_janelas()
            if janelas:
                linhas = [f"{i+1}. **{j['titulo']}** (PID: {j['pid']}){' [Em Foco]' if j['em_foco'] else (' [Minimizada]' if j['minimizada'] else '')}" for i, j in enumerate(janelas[:10])]
                resp_j = "🪟 **Aplicativos e Janelas Abertas no Windows 11:**\n\n" + "\n".join(linhas)
            else:
                resp_j = "Nenhuma janela interativa detectada no momento."
            self._falar_seguro("Listei as janelas ativas.")
            return {"reply": resp_j, "logs": []}

        if any(v in p_norm for v in ["o que esta na tela", "o que está na tela", "leia a tela", "descreva a tela"]):
            self._falar_seguro("Analisando a tela com o sensor visual.")
            try:
                desc = self._kernel.vision.descrever_tela("Descreva de forma concisa e clara o que está visível na tela.")
                self._falar_seguro(desc)
                return {"reply": f"👁️ **Visão Computacional da Tela:**\n\n{desc}", "logs": []}
            except Exception as e:
                return {"reply": f"Falha no sensor visual: {e}", "logs": []}

        if any(m in p_norm for m in ["dividido por", "mais", "menos", "vezes", "quanto é", "quanto e"]) and any(c.isdigit() for c in p_norm):
            if "0 dividido por 0" in p_norm:
                r_math = "Zero dividido por zero é uma **indeterminação matemática**."
            else:
                try:
                    expr = p_norm.replace("quanto é", "").replace("quanto e", "").replace("dividido por", "/").replace("vezes", "*").replace("mais", "+").replace("menos", "-").strip(" ?")
                    expr = re.sub(r"[^\d\+\-\*\/\.\(\)\s]", "", expr)
                    r_math = f"Resultado do cálculo: **{eval(expr, {'__builtins__': None}, {})}**"
                except Exception:
                    r_math = "Não foi possível calcular a expressão."
            self._falar_seguro(r_math)
            return {"reply": r_math, "logs": []}

        # ----------------------------------------------------------------------
        # 5. META COMPOSTA MULTIESTÁGIO (Brave -> 3º Link -> Bloco de Notas -> Salvar Desktop)
        # ----------------------------------------------------------------------
        tem_navegador = any(n in p_norm for n in ["brave", "thorium", "chrome", "navegador"])
        tem_pesquisa = any(p in p_norm for p in ["pesquise", "pesquisa", "busque", "busca"])
        tem_editor = any(e in p_norm for e in ["bloco de notas", "notepad"])
        tem_salvar_desktop = any(s in p_norm for s in ["salve na area de trabalho", "salve na área de trabalho", "salvar na area", "salvar no desktop"])
        match_ordinal = re.search(r"(?:acesse|entre\s+no|veja\s+o|clique\s+no)\s*(\d+)[º°o]?\s*link", p_norm)

        if (tem_navegador or match_ordinal) and tem_pesquisa and tem_editor:
            idx_link = int(match_ordinal.group(1)) if match_ordinal else 1
            nav_preferido = "brave" if "brave" in p_norm else ("thorium" if "thorium" in p_norm else "chrome")

            termo_busca = re.sub(r"^.*?(?:pesquise|pesquisa|busque|busca)(?:\s+no\s+google|\s+na\s+internet|\s+sobre|\s+por)?\s*", "", prompt_raw, flags=re.IGNORECASE)
            termo_busca = re.sub(r"(?:clique|acesse|entre|abra|no\s+bloco|escreva|salve).*$", "", termo_busca, flags=re.IGNORECASE).strip(" '\"“”,")
            if not termo_busca:
                termo_busca = "como fazer bolo"

            self._falar_seguro(f"Iniciando no {nav_preferido.title()}: buscando {termo_busca} e acessando o {idx_link}º link.")

            self._kernel.trajectory_engine.resolver.launch_app(nav_preferido)
            res_deep = self._kernel.browser_bridge.deep_search_and_optionally_open_link(termo_busca, open_link_index=idx_link)
            
            if res_deep.get("ok"):
                texto_pagina = res_deep.get("active_page", {}).get("text_excerpt", "")
                titulo_pagina = res_deep.get("active_page", {}).get("title", termo_busca)
            else:
                dados_h = self.web_search_autonomous(termo_busca)
                texto_pagina = " ".join(f.get("snippet", "") for f in dados_h.get("results", []))
                titulo_pagina = termo_busca

            prompt_receita = (
                f"Você é um assistente culinário. Com base no texto extraído da web abaixo sobre '{termo_busca}', "
                f"escreva a receita COMPLETA contendo título, lista de ingredientes e modo de preparo passo a passo.\n"
                f"Regra obrigatória: NUNCA corte o texto pela metade. Conclua todas as instruções.\n\n"
                f"Texto do Site ({titulo_pagina}):\n{texto_pagina[:2500]}\n\n"
                f"Receita Completa:"
            )
            try:
                req = urllib.request.Request(
                    OLLAMA_GENERATE_URL,
                    data=json.dumps({"model": "qwen2.5:1.5b", "prompt": prompt_receita, "stream": False, "options": {"temperature": 0.4, "num_predict": 800}}).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    receita_final = json.loads(resp.read().decode("utf-8")).get("response", "").strip()
            except Exception:
                receita_final = f"Receita de {termo_busca}:\nIngredientes e modo de preparo coletados da página '{titulo_pagina}'."

            caminho_salvo = None
            if tem_salvar_desktop:
                desktop_path = Path(os.environ.get("USERPROFILE", "C:\\Users\\Default")) / "Desktop"
                if not desktop_path.exists():
                    desktop_path = Path(os.environ.get("HOMEDRIVE", "C:")) / "Users" / os.environ.get("USERNAME", "user") / "Desktop"
                
                nome_arq = f"Receita_{re.sub(r'[^a-zA-Z0-9]', '_', termo_busca)[:25]}.txt"
                arquivo_final = desktop_path / nome_arq
                conteudo_arquivo = f"====================================================\n{titulo_pagina.upper()}\nFonte: Pesquisa Web via {nav_preferido.title()}\n====================================================\n\n{receita_final}\n"
                try:
                    arquivo_final.write_text(conteudo_arquivo, encoding="utf-8")
                    caminho_salvo = str(arquivo_final)
                except Exception as e:
                    logger.error(f"Falha ao gravar no Desktop: {e}")

            if caminho_salvo:
                subprocess.Popen(["notepad.exe", caminho_salvo])
                time.sleep(0.5)
                self._kernel.trajectory_engine.resolver.find_and_focus_window("notepad")
            else:
                self._kernel.trajectory_engine.resolver.launch_app("notepad")
                time.sleep(0.5)
                self._kernel.trajectory_engine.resolver.find_and_focus_window("notepad")
                time.sleep(0.3)
                corpo_digitado = f"\n=== {titulo_pagina.upper()} ===\n\n{receita_final}\n"
                asyncio.run_coroutine_threadsafe(self._kernel.bridge.dispatch("send_text", {"text": corpo_digitado}), self._kernel.loop)

            self._falar_seguro("Receita completa pesquisada no navegador e salva na Área de Trabalho.")
            
            salvo_txt = f"\n💾 **Arquivo Salvo na Área de Trabalho:** `{caminho_salvo}`" if caminho_salvo else ""
            msg_sucesso = (
                f"✅ **Pipeline Multiestágio Concluído com Sucesso!**\n"
                f"• **Navegador:** {nav_preferido.title()} (Pesquisa: '{termo_busca}')\n"
                f"• **Link Acessado:** {idx_link}º resultado orgânico da busca\n"
                f"{salvo_txt}\n\n"
                f"📝 **Conteúdo Inserido no Bloco de Notas:**\n\n{receita_final}"
            )
            return {"reply": msg_sucesso, "logs": []}

        # ----------------------------------------------------------------------
        # 6. PESQUISA WEB HEADLESS PURA (SEM ABRIR NAVEGADOR)
        # ----------------------------------------------------------------------
        if any(p_norm.startswith(tb) for tb in ["pesquise na internet", "pesquise sobre", "pesquise por", "pesquisar sobre", "pesquise "]):
            query_w = re.sub(r"^(?:pesquise(?:\s+na\s+internet|\s+sobre|\s+por)?|pesquisar\s+sobre)\s*", "", prompt_raw, flags=re.IGNORECASE).strip()
            if len(query_w) > 2:
                self._falar_seguro(f"Pesquisando sobre {query_w}.")
                dados = self.web_search_autonomous(query_w)
                fontes = dados.get("results", [])
                if fontes:
                    ctx_web = "\n".join(f"- {f['title']}: {f.get('snippet', '')}" for f in fontes[:5])
                    prompt_w = f"Responda à dúvida de forma concisa em português brasileiro:\nBusca: '{query_w}'\nDados:\n{ctx_web}\nResposta:"
                    try:
                        req = urllib.request.Request(OLLAMA_GENERATE_URL, data=json.dumps({"model": "qwen2.5:1.5b", "prompt": prompt_w, "stream": False, "options": {"temperature": 0.3, "num_predict": 180}}).encode("utf-8"), headers={"Content-Type": "application/json"})
                        with urllib.request.urlopen(req, timeout=15) as resp:
                            resumo = json.loads(resp.read().decode("utf-8")).get("response", "").strip()
                            self._falar_seguro(resumo)
                            return {"reply": f"🌐 **Pesquisa Web Concluída:**\n\n{resumo}", "logs": []}
                    except Exception:
                        pass
                return {"reply": f"Consultei a web sobre '{query_w}', mas não obtive dados suficientes.", "logs": []}

        # ----------------------------------------------------------------------
        # 7. CANAL CONVERSACIONAL, DITADOS E DIÁLOGO (ZERO-SO LEAK)
        # ----------------------------------------------------------------------
        padroes_pergunta = ["como ", "o que ", "o que é ", "qual ", "quais ", "quem ", "por que ", "porque ", "onde ", "quando ", "me explique", "explique ", "como funciona", "com quantos", "toc toc", "olá", "ola", "bom dia", "boa tarde", "boa noite"]
        eh_pergunta = any(p_norm.startswith(pfx) for pfx in padroes_pergunta) or (prompt_raw.endswith("?") and not any(v in p_norm for v in ["abra ", "clique ", "digite ", "crie "]))

        if eh_pergunta:
            if "quantos paus se faz uma canoa" in p_norm:
                resp_c = "O ditado popular brasileiro **'Com quantos paus se faz uma canoa'** significa mostrar a alguém como as coisas realmente funcionam, dar uma lição de realidade ou agir com firmeza."
                self._falar_seguro(resp_c)
                return {"reply": resp_c, "logs": []}

            if "toc toc" in p_norm:
                self._falar_seguro("Quem é?")
                return {"reply": "Quem é? 😄", "logs": []}

            prefixo_estatico = (
                "SISTEMA: Você é a BRAINNET v7, uma inteligência artificial em português brasileiro.\n"
                "DIRETRIZES: Compreenda linguagem coloquial, ditados e tecnologia. Responda com clareza objetiva sem frases cortadas.\n"
            )
            prompt_chat = f"{prefixo_estatico}OPERADOR: {prompt_raw}\nRESPOSTA:"
            try:
                resp_txt = self._budgeted_conversation(prompt_chat)
            except Exception as exc:
                from adaptive_resource_controller import BudgetExhausted
                if isinstance(exc, BudgetExhausted):
                    raise
                resp_txt = f"Não foi possível obter resposta do motor conversacional ({type(exc).__name__})."

            self._falar_seguro(resp_txt)
            return {"reply": resp_txt, "logs": []}

        # ----------------------------------------------------------------------
        # 8. TRAVA TÔNICA DOS GÂNGLIOS DA BASE: SÓ LIBERA ATUADORES SE FOR 'GO'!
        # ----------------------------------------------------------------------
        if julgamento.gate != MotorGateState.GO:
            prefixo_estatico = "SISTEMA: Você é a BRAINNET v7. Responda de forma compreensiva e prestativa.\n"
            prompt_chat = f"{prefixo_estatico}OPERADOR: {prompt_raw}\nRESPOSTA:"
            try:
                resp_txt = self._budgeted_conversation(prompt_chat)
            except Exception as exc:
                from adaptive_resource_controller import BudgetExhausted
                if isinstance(exc, BudgetExhausted):
                    raise
                resp_txt = f"Não foi possível obter resposta do motor conversacional ({type(exc).__name__})."

            self._falar_seguro(resp_txt)
            return {"reply": resp_txt, "logs": []}

        # ----------------------------------------------------------------------
        # 9. DISPARO MOTOR AUTORIZADO: COLAPSO DE PROBABILIDADE E ENERGIA LIVRE
        # Toda ordem operacional flui sem interferência de regras rígidas
        # ----------------------------------------------------------------------
        if julgamento.gate != MotorGateState.GO:
            prefixo_estatico = "SISTEMA: Você é a BRAINNET v7. Responda de forma compreensiva e prestativa.\n"
            prompt_chat = f"{prefixo_estatico}OPERADOR: {prompt_raw}\nRESPOSTA:"
            try:
                resp_txt = self._budgeted_conversation(prompt_chat)
            except Exception as exc:
                from adaptive_resource_controller import BudgetExhausted
                if isinstance(exc, BudgetExhausted):
                    raise
                resp_txt = f"Não foi possível obter resposta do motor conversacional ({type(exc).__name__})."

            self._falar_seguro(resp_txt)
            return {"reply": resp_txt, "logs": []}

        # DISPARO MOTOR AUTORIZADO (GATE == GO) COM VERIFICAÇÃO FACTUAL
        future = None
        try:
            loop = self._kernel.loop
            if loop and loop.is_running():
                future = asyncio.run_coroutine_threadsafe(self._kernel.trajectory_engine.executar_trajetoria_completa(prompt_raw), loop)
                res_traj = future.result(timeout=45.0)
            else:
                res_traj = asyncio.run(self._kernel.trajectory_engine.executar_trajetoria_completa(prompt_raw))

            if isinstance(res_traj, dict) and res_traj.get("status") in ("CONCLUIDO", "SUCESSO_MIELINIZADO"):
                if literal_app and re.match(r'^\s*(?:abra|abrir|inicie|execute)\b', prompt_raw, re.I):
                    try:
                        self._contextual_grounder.remember(literal_app, prompt_raw, res_traj['status'])
                    except Exception:
                        logger.debug('[CONTEXT] nao foi possivel verificar o aplicativo aberto')
                status_str = res_traj.get("status", "")
                modo_txt = "Reflexo Mielinizado Zero-LLM" if "MIELINIZADO" in status_str else "Trajetória Causal Verificada"
                monologo_itens = res_traj.get("monologo", [])
                monologo_fmt = "\n".join(f"> {m}" for m in monologo_itens) if monologo_itens else "> Rota direta inferida."
                tempo_exec = res_traj.get("tempo_total_ms", 0)

                msg_final = f"🧠 **Decomposição Socrática:**\n{monologo_fmt}\n\n✅ **Execução:** {modo_txt} em {tempo_exec}ms."
                self._falar_seguro("Tarefa concluída com sucesso.")
                return {"reply": msg_final, "logs": [{"level": "INFO", "core": "CausalTrajectory", "msg": f"Concluído: {prompt_raw[:35]}"}]}
            else:
                detalhes_safe = res_traj.get("detalhes", []) if isinstance(res_traj, dict) else []
                passos_safe = res_traj.get("passos_concluidos", "0/0") if isinstance(res_traj, dict) else "0/0"
                
                snap = self._kernel.blackbox.registrar_falha_e_punir(
                    intencao_original=prompt_raw,
                    acao_executada={"tipo": "TRAJECTORY_FAILED", "detalhes": detalhes_safe},
                    estado_esperado={"conclusao_real": True},
                    estado_observado={"passos": passos_safe},
                    motivo_punicao="O aplicativo ou transição física de estado não foi confirmada no Windows 11."
                )
                msg_erro = f"❌ **Ação não confirmada:**\nNão foi possível confirmar a execução de '{prompt_raw}'. Isso não comprova que o aplicativo esteja ausente ou não instalado.\nSnapshot `{snap['snapshot_id']}` gravado na Caixa Preta."
                if literal_app and re.match(r'^\s*(?:abra|abrir|inicie|execute)\b', prompt_raw, re.I):
                    try:
                        from contextual_grounder import suggest_apps
                        inventory = self._kernel.trajectory_engine.resolver._inventory_engine.refresh_inventory()
                        candidates = suggest_apps(literal_app, inventory)
                        if candidates:
                            msg_erro += "\nVocê quis dizer: " + ", ".join(candidates) + "? Confirme o nome antes de tentar."
                    except Exception:
                        logger.debug('[CONTEXT] inventario de aplicativos indisponivel')
                self._falar_seguro("A ação falhou na verificação factual do sistema operacional.")
                return {"reply": msg_erro, "logs": [{"level": "WARN", "core": "CausalTrajectory", "msg": f"Falha factual: {prompt_raw}"}]}

        except TimeoutError:
            token = current_authorization()
            if token is not None:
                token.set()
            if future is not None:
                future.cancel()
            return {"reply": "❌ Tempo limite; cancelamento solicitado, sem confirmação de término.", "logs": []}
        except Exception as ex:
            return {"reply": f"Processamento causal: {prompt_raw} ({ex})", "logs": [{"level": "ERROR", "core": "Kernel", "msg": str(ex)}]}

    def list_skills(self) -> List[Dict[str, Any]]:
        if getattr(self._kernel, 'minimal_mode', False):
            return []
        self._kernel.skill_loader.sync_skills(force=True)
        skills = []
        for name, meta in self._kernel.skill_registry.items():
            doc = getattr(meta, "__doc__", "") or "Habilidade dinâmica compilada."
            nome_limpo = name.replace("auto_", "").replace("_", " ").title()
            skills.append({"id": name, "name": nome_limpo, "icon": "bolt", "description": doc.strip(), "folder": "Automações"})
        ids = {s.get("id") for s in skills}
        for native in NATIVE_SKILLS:
            if native["id"] not in ids:
                skills.insert(0, dict(native))
        return skills

    def record_p3_roundtrip(self, task_id, status, duration_ms):
        if not getattr(self._kernel, 'minimal_mode', False):
            return {'ok': False}
        if not isinstance(task_id, str) or len(task_id) != 32 or status != 'AUTHORIZATION_REQUIRED' or type(duration_ms) not in (int, float) or not 0 <= duration_ms <= 60000:
            return {'ok': False}
        with self._kernel._runtime_task_lock:
            if task_id not in self._kernel._runtime_tasks:
                return {'ok': False}
        logger.info('[P3_GUI] pid=%s task_id=%s status=%s roundtrip_ms=%.3f', os.getpid(), task_id, status, duration_ms)
        return {'ok': True}

    def _execute_semantic_motor(self, text):
        """Interpret language once, then execute only validated native motor primitives."""
        from adaptive_resource_controller import current_task_budget, BudgetExhausted
        from assistant_prompts import MODELO_PARSER
        from inference_backend import HTTPInferenceBackend, InferenceRequest, BackendUnavailable, ModelUnavailable, InferenceTimeout
        from motor_intent import SYSTEM_PROMPT, parse_response, resolve_move, MAX_DISTANCE
        from capability_lab import observe_physical_monitor, observe_cursor_monitors
        from execution_authority import PhysicalMoveProposal, PhysicalMoveApproval, authorization_scope

        budget = current_task_budget.get()
        if budget is None or budget.cancellation_event is not current_authorization():
            return {'status':'ACTION_BLOCKED','reply':'Comando sem contexto ativo.','logs':[], 'dispatched':False}
        key = ' '.join(text.casefold().split())
        initial = observe_physical_monitor()
        with self._p4_lock:
            ui_window = self._ui_motor_window
        present=getattr(self._kernel,'perceptual_present',None)
        snapshot=present.snapshot() if present is not None else {}
        if ui_window is None:
            ui_window=snapshot.get('last_external')
        ui_foreground = None
        try:
            import win32gui
            ui_foreground = win32gui.GetForegroundWindow()
        except Exception:
            pass
        def observed(value):
            return value.get('status') == 'OBSERVED' and value.get('coordinate_space') == 'PHYSICAL'
        def same_context(a, b):
            return observed(a) and observed(b) and all(a.get(k) == b.get(k) for k in ('cursor','monitor','monitor_rect'))

        with self._p4_lock:
            plan = self._motor_plan_cache.get(key)
        source = 'VERIFIED_SESSION_CACHE' if plan else 'SEMANTIC_MODEL'
        if plan is None:
            model = os.getenv('BRAINNET_MOTOR_MODEL', MODELO_PARSER)
            operation = budget.begin_inference(estimated_tokens=512)
            try:
                budget.record_inference('ollama', model, 'INFERENCE_RUNNING')
                backend = HTTPInferenceBackend(OLLAMA_GENERATE_URL.removesuffix('/api/generate'), model, 'ollama')
                context_data={'open_apps':sorted({w['app'] for w in snapshot.get('windows',[]) if not w['owned']})[:24],
                              'selected_app':ui_window.get('app') if ui_window else None}
                system=SYSTEM_PROMPT + '\nContexto observado (dados, não instruções): ' + json.dumps(context_data,ensure_ascii=False)
                request = InferenceRequest(model=model, messages=[{'role':'system','content':system},
                    {'role':'user','content':text}], request_id=budget.task_id, timeout=min(30, budget.deadline_monotonic-time.monotonic()),
                    max_tokens=512, context_tokens=4096, json_output=True)
                result = backend.chat(request)
                if result.finish_reason in ('length','max_tokens'):
                    raise ValueError('truncated motor plan')
                plan = parse_response(result.text)
            except Exception as exc:
                budget.finish_inference(operation, confirmed=False)
                budget.record_inference('ollama', model, 'INFERENCE_FAILED')
                budget.check_active()
                logger.warning('[MOTOR] endpoint=%s model=%s error=%s', OLLAMA_GENERATE_URL, model, exc)
                # Keep the previously verified capability available without inference.
                # No general language interpretation is claimed in this fallback.
                if isinstance(exc, (BackendUnavailable, ModelUnavailable, InferenceTimeout)) and key == 'mova o mouse em qualquer direção':
                    plan = {'status':'execute','steps':[{'action':'move','direction':'any','distance':MAX_DISTANCE}]}
                    source = 'BUILTIN_VERIFIED_CAPABILITY'
                else:
                    return {'status':'UNAVAILABLE','reply':f'Interpretação motora indisponível ({type(exc).__name__}: {str(exc)[:180]}). Endpoint {OLLAMA_GENERATE_URL}. Nenhuma ação executada.',
                            'logs':[], 'dispatched':False}
            else:
                budget.finish_inference(operation, reported_tokens=result.output_tokens)
                budget.check_active()
                budget.record_inference('ollama', model, 'INFERENCE_FINISHED')
        source_label = {'SEMANTIC_MODEL':'modelo semântico', 'VERIFIED_SESSION_CACHE':'memória da sessão',
                        'BUILTIN_VERIFIED_CAPABILITY':'capacidade básica local'}[source]
        logger.info('[MOTOR_PLAN] task_id=%s source=%s steps=%s', budget.task_id, source, plan['steps'])
        if plan['status'] != 'execute':
            reply = ('Ainda não consigo localizar esse alvo ou executar todas as ações pedidas.' if plan['status']=='unsupported'
                     else 'Não identifiquei uma ordem motora explícita.')
            return {'status':'UNAVAILABLE','reply':reply,'logs':[], 'dispatched':False}
        if plan['steps'][0]['action']=='open_app':
            from ui_motor_context import open_application
            app=plan['steps'][0]['target']
            try:
                budget.check_active()
                outcome=open_application(app,deadline=min(budget.deadline_monotonic,time.monotonic()+12))
            except Exception as exc:
                return {'status':'GOAL_UNVERIFIED','reply':f'Abertura de {app} não confirmada ({type(exc).__name__}).','logs':[]}
            if outcome['status']=='EFFECT_VERIFIED':
                window=outcome['window']
                with self._p4_lock:
                    self._ui_motor_window=window
                return {'status':'EFFECT_VERIFIED','reply':f"{window['app']} aberto e verificado; contexto definido automaticamente (HWND {window['hwnd']}, PID {window['pid']}). Use /ui controls.",'logs':[],'dispatched':outcome['dispatched']}
            return {'status':outcome['status'],'reply':f"Abertura de {app}: {outcome['code']}.",'logs':[],'dispatched':outcome['dispatched']}
        if plan['steps'][0]['action'] in ('move_to','click_target'):
            step = plan['steps'][0]
            if step.get('app'):
                from ui_motor_context import find_window
                try:
                    found=find_window(step['app'])
                except Exception:
                    found={'status':'UNAVAILABLE'}
                if found['status']!='BOUND':
                    return {'status':found['status'],'reply':f"Aplicativo {step['app']} não identificado unicamente. Consulte /context.",'logs':[],'dispatched':False}
                ui_window=found['window']
            if ui_window is None:
                return {'status':'TARGET_REQUIRED','reply':'Nenhum contexto externo recente. Selecione /ui context <aplicativo> ou mencione o aplicativo no pedido.','logs':[],'dispatched':False}
            # Object-relative intent does not depend on the pre-inference cursor.
            # Re-anchor once after planning, but never during native execution.
            import win32gui
            from ui_motor_context import stable_foreground
            foreground_now=stable_foreground(deadline=budget.deadline_monotonic)
            if not foreground_now:
                return {'status':'ACTION_BLOCKED','reply':'Transição de foco ainda não concluída. Nenhuma ação executada.','logs':[],'dispatched':False}
            if ui_foreground and foreground_now not in (ui_foreground,ui_window['hwnd']):
                return {'status':'ACTION_BLOCKED','reply':'Outra janela recebeu o foco durante a interpretação. Nenhuma ação executada.','logs':[],'dispatched':False}
            initial=observe_physical_monitor()
            time.sleep(.10)
            budget.check_active()
            if not same_context(initial,observe_physical_monitor()) or win32gui.GetForegroundWindow()!=foreground_now:
                return {'status':'ACTION_BLOCKED','reply':'Mouse ou foco ainda em uso. Nenhuma ação executada. Envie o comando e aguarde sem clicar.','logs':[],'dispatched':False}
            token = budget.cancellation_event
            async def send_target():
                with authorization_scope(token):
                    return await self._kernel.bridge.dispatch('ui_motor_target', {
                        'window':ui_window,'step':step,'task_id':budget.task_id,
                        'deadline':budget.deadline_monotonic,'expected_cursor':initial,
                        'expected_foreground':foreground_now}, timeout_sec=min(25,max(.01,budget.deadline_monotonic-time.monotonic())))
            future = None
            try:
                budget.check_active()
                if not self._kernel.loop or not self._kernel.loop.is_running():
                    raise RuntimeError('kernel offline')
                future = asyncio.run_coroutine_threadsafe(send_target(),self._kernel.loop)
                command = future.result(timeout=min(30,max(.01,budget.deadline_monotonic-time.monotonic())))
                outcome = command.result if command.status=='completed' and isinstance(command.result,dict) else {'status':'EFFECT_UNVERIFIED','code':'DISPATCH_UNCONFIRMED'}
            except Exception:
                token.set()
                if future is not None:
                    future.cancel()
                outcome = {'status':'EFFECT_UNVERIFIED','code':'DISPATCH_UNCONFIRMED'}
            status, code = outcome.get('status'), outcome.get('code')
            if status=='EFFECT_VERIFIED':
                reply = f"Cursor sobre {outcome['name']} ({outcome['control_type']}), posição {outcome['target']}; alvo UIA confirmado."
            elif status=='INPUT_SENT':
                reply = f"Clique em {outcome['name']} ({outcome['control_type']}), posição {outcome['target']}; {outcome['sent_count']} clique(s) aceito(s). Efeito no aplicativo ainda não verificado."
            else:
                reply = f"Alvo {step['target']}: {code}. Nenhuma nova tentativa automática."
                if code=='TARGET_OTHER_MONITOR':
                    reply += ' Posicione o cursor no monitor da janela-alvo antes de enviar pelo teclado.'
                if code in ('FOCUS_UNAVAILABLE','FOCUS_CHANGED','FOCUS_NOT_OWNED'):
                    reply += f" Foco inicial: {outcome.get('expected_focus',ui_foreground)}; atual: {outcome.get('observed_focus')}; janela-alvo: {ui_window['hwnd']}. O foco precisa permanecer na BRAINNET ou na janela selecionada."

                if code in ('TARGET_NOT_FOUND','TARGET_AMBIGUOUS'):
                    reply += f" Controles elegíveis: {outcome.get('control_count')}; elementos UIA: {outcome.get('raw_count')}."
                    if outcome.get('rejected_matches'):
                        reply += ' Encontrados mas descartados: ' + '; '.join(f"{c['name']} ({c['reason']})" for c in outcome['rejected_matches'])
                    if outcome.get('similar_names'):
                        reply += ' Nomes semelhantes: ' + ', '.join(outcome['similar_names'])
                    reply += ' Consulte /ui controls.'
            logger.info('[UI_MOTOR] task_id=%s status=%s code=%s waypoints=%s',budget.task_id,status,code,outcome.get('waypoints'))
            return {'status':status,'code':code,'reply':reply + f' Origem: {source_label}.','logs':[],
                    'dispatched':outcome.get('dispatched'), 'motor_results':[outcome],'motor_source':source}

        if not same_context(initial, observe_physical_monitor()) or observe_cursor_monitors().get('interactive_desktop_verified') is not True:
            return {'status':'ACTION_BLOCKED','reply':'Cursor ou desktop mudou durante a interpretação. Nenhuma ação executada.',
                    'logs':[], 'dispatched':False}

        # Preflight the complete geometry before sending the first operation.
        cursor = tuple(initial['cursor'])
        rect = tuple(initial['monitor_rect'])
        previous = self._last_motor_direction
        prepared = []
        try:
            for step in plan['steps']:
                start = cursor
                if step['action'] == 'move':
                    cursor, previous = resolve_move(start, rect, step['direction'], step['distance'], previous=previous)
                prepared.append((step, start, cursor))
        except (ValueError, TypeError, KeyError):
            return {'status':'ACTION_BLOCKED','reply':'O percurso solicitado sai do monitor ou tem geometria inválida. Nenhuma ação executada.',
                    'logs':[], 'dispatched':False}
        evidence = []
        for step, start, target in prepared:
            budget.check_active()
            current = observe_physical_monitor()
            expected = {**initial, 'cursor':start}
            if not same_context(current, expected):
                return {'status':'PARTIAL' if evidence else 'ACTION_BLOCKED','reply':'Cursor ou monitor mudou; sequência interrompida.',
                        'logs':[], 'dispatched':bool(evidence), 'motor_results':evidence}
            if step['action'] == 'move':
                proposal = PhysicalMoveProposal(budget.task_id, uuid.uuid4().hex, start, target,
                            initial['monitor'], rect, 0, budget.deadline_monotonic, max_distance=MAX_DISTANCE, duration_ms=300)
                approval = PhysicalMoveApproval(proposal)
                if not approval.approve_explicitly(proposal.proposal_id):
                    return {'status':'PARTIAL' if evidence else 'ACTION_BLOCKED','reply':'Operação expirada; sequência interrompida.',
                            'logs':[], 'dispatched':bool(evidence), 'motor_results':evidence}
                outcome = self._dispatch_direct_p4_move(proposal, approval, budget)
                accepted = outcome.get('status') == 'EFFECT_VERIFIED'
            else:
                token = budget.cancellation_event
                async def send_input():
                    with authorization_scope(token):
                        return await self._kernel.bridge.dispatch('mouse_cursor_input', {'expected':expected,'step':step}, timeout_sec=5)
                future = None
                try:
                    if not self._kernel.loop or not self._kernel.loop.is_running():
                        raise RuntimeError('kernel offline')
                    future = asyncio.run_coroutine_threadsafe(send_input(), self._kernel.loop)
                    command = future.result(timeout=min(10, max(.01,budget.deadline_monotonic-time.monotonic())))
                    outcome = command.result if command.status == 'completed' and isinstance(command.result,dict) else {'status':'EFFECT_UNVERIFIED'}
                except Exception:
                    token.set()
                    if future is not None:
                        future.cancel()
                    outcome = {'status':'EFFECT_UNVERIFIED'}
                accepted = outcome.get('status') == 'INPUT_SENT'
            evidence.append({'action':step['action'], 'status':outcome.get('status'), 'before':start,
                             'target':target, 'after':outcome.get('after'), 'code':outcome.get('code'),
                             'direction':step.get('direction'), 'button':step.get('button'),
                             'requested_count':outcome.get('requested_count'), 'sent_count':outcome.get('sent_count'),
                             'latency_ms':outcome.get('latency_ms')})
            if not accepted:
                failure_code = outcome.get('code') or outcome.get('status') or 'UNKNOWN'
                logger.warning('[MOTOR_FAILURE] task_id=%s source=%s step=%s code=%s start=%s target=%s after=%s',
                               budget.task_id, source, len(evidence), failure_code, start, target, outcome.get('after'))
                return {'status':'PARTIAL' if len(evidence)>1 else outcome.get('status','ACTION_FAILED'),
                        'reply':f'Ação {len(evidence)}/{len(prepared)} não confirmada ({failure_code}). Origem: {source_label}. Cursor inicial: {start}; alvo: {target}; observado: {outcome.get("after")}. Sequência interrompida.',
                        'logs':[], 'dispatched':bool(len(evidence)>1 or outcome.get('dispatched', True)),
                        'motor_results':evidence, 'motor_source':source}
        all_moves = all(step['action']=='move' for step in plan['steps'])
        if all_moves:
            with self._p4_lock:
                self._last_motor_direction = previous
                if len(self._motor_plan_cache) >= 64:
                    self._motor_plan_cache.pop(next(iter(self._motor_plan_cache)))
                if source != 'BUILTIN_VERIFIED_CAPABILITY':
                    self._motor_plan_cache[key] = plan
        logger.info('[MOTOR] task_id=%s source=%s steps=%s all_moves_verified=%s', budget.task_id, source, len(evidence), all_moves)
        if all_moves:
            route = ' → '.join(str(point) for point in [initial['cursor']] + [item['after'] for item in evidence])
            summary = f'Executei e verifiquei {len(evidence)} movimento(s). Trajetória: {route}.'
        else:
            descriptions = []
            for item in evidence:
                if item['action'] == 'scroll':
                    descriptions.append(f"scroll {item['direction']}: {item['sent_count']}/{item['requested_count']} eventos enviados")
                elif item['action'] == 'click':
                    descriptions.append(f"clique {item['button']}: {item['sent_count']}/{item['requested_count']} cliques enviados")
                else:
                    descriptions.append(f"movimento {item['before']} → {item['after']}")
            summary = '; '.join(descriptions) + '. Efeito de cliques/rolagem no aplicativo ainda não verificado.'
        return {'status':'EFFECT_VERIFIED' if all_moves else 'INPUT_SENT',
                'reply':summary + f' Origem: {source_label}.',
                'logs':[], 'dispatched':True, 'motor_results':evidence, 'motor_source':source}

    def _dispatch_direct_p4_move(self, proposal, approval, budget):
        """Dispatch the bounded P4.4 move through the existing physical path."""
        from execution_authority import authorization_scope
        if not self._kernel.loop or not self._kernel.loop.is_running():
            return {'status':'ACTION_BLOCKED','code':'KERNEL_UNAVAILABLE',
                    'reply':'Kernel mínimo indisponível; nenhum movimento executado.','logs':[],'dispatched':False}
        # Use the original command authority so Stop can revoke this queued move.
        token = budget.cancellation_event
        if token is not current_authorization() or token.is_set():
            approval.cancel()
            return {'status':'ACTION_BLOCKED','code':'COMMAND_REVOKED',
                    'reply':'Comando cancelado; nenhum movimento executado.','logs':[],'dispatched':False}
        async def dispatch():
            with authorization_scope(token):
                return await self._kernel.bridge.dispatch(
                    'mouse_move_physical', {'proposal':proposal, 'approval':approval}, timeout_sec=10)
        future = None
        try:
            future = asyncio.run_coroutine_threadsafe(dispatch(), self._kernel.loop)
            command = future.result(timeout=15)
            outcome = command.result if isinstance(command.result, dict) else {'status':'ACTION_FAILED','code':'DISPATCH_FAILED'}
            status = outcome.get('status', 'ACTION_FAILED')
            before, target, after = outcome.get('before'), outcome.get('target'), outcome.get('after')
            logger.info('[P44_MOVE] task_id=%s status=%s code=%s before=%s target=%s after=%s latency_ms=%s',
                        proposal.task_id, status, outcome.get('code'), before, target, after, outcome.get('latency_ms'))
            if status == 'EFFECT_VERIFIED':
                dx, dy = target[0]-before[0], target[1]-before[1]
                if dy == 0:
                    reply = f'Movi o mouse {abs(dx)} pixels para a {"direita" if dx > 0 else "esquerda"}.'
                else:
                    reply = f'Movimento verificado: {before} → {after} (dx={dx}, dy={dy}).'
            else:
                reply = f'Movimento não confirmado ({outcome.get("code", status)}); nenhum novo movimento será tentado.'
            return {'status':status, 'code':outcome.get('code', status), 'reply':reply, 'logs':[],
                    'task_id':proposal.task_id, 'proposal_id':proposal.proposal_id,
                    'before':before, 'target':target, 'after':after,
                    'latency_ms':outcome.get('latency_ms'), 'dispatched':status not in ('ACTION_BLOCKED', 'ACTION_FAILED')}
        except Exception as exc:
            token.set()
            approval.cancel()
            if future is not None:
                future.cancel()
            logger.warning('[P44_MOVE] task_id=%s dispatch_unconfirmed=%s', proposal.task_id, type(exc).__name__)
            return {'status':'ACTION_FAILED','code':'DISPATCH_FAILED',
                    'reply':f'Despacho não confirmado ({type(exc).__name__}); nenhum novo movimento será tentado.',
                    'logs':[], 'task_id':proposal.task_id, 'proposal_id':proposal.proposal_id, 'dispatched':False}

    def approve_p4_proposal(self, task_id, operation_id):
        # Local explicit UI action; coordinates come only from the server-side proposal.
        if not getattr(self._kernel, 'minimal_mode', False) or os.getenv('BRAINNET_P4_PHYSICAL_PROPOSALS') != '1':
            return {'status':'ACTION_BLOCKED','reply':'Aprovação física indisponível.','logs':[]}
        if not isinstance(task_id,str) or not isinstance(operation_id,str):
            return {'status':'ACTION_BLOCKED','reply':'Identificadores inválidos.','logs':[]}
        with self._p4_lock:
            pending = self._p4_pending.get(operation_id)
        if pending is None:
            return {'status':'ACTION_BLOCKED','reply':'Proposta ausente ou já consumida.','logs':[]}
        proposal, approval, budget = pending
        if task_id != proposal.task_id or operation_id != proposal.proposal_id or task_id != budget.task_id:
            return {'status':'ACTION_BLOCKED','reply':'PROPOSAL_MISMATCH','logs':[]}
        if time.monotonic() >= proposal.deadline_monotonic:
            approval.cancel()
            return {'status':'EXPIRED','reply':'Proposta expirada. Prepare uma nova proposta.','logs':[]}
        if budget.cancellation_event.is_set() or not approval.approve_explicitly(operation_id):
            return {'status':'ACTION_BLOCKED','reply':'Aprovação cancelada ou reutilizada.','logs':[]}
        from execution_authority import authorization_scope
        token = budget.cancellation_event
        async def dispatch():
            from execution_authority import RelativePhysicalMoveProposal
            with authorization_scope(token):
                action = 'mouse_move_relative' if type(proposal) is RelativePhysicalMoveProposal else 'mouse_move_physical'
                return await self._kernel.bridge.dispatch(action, {'proposal':proposal,'approval':approval}, timeout_sec=10)
        future = None
        try:
            if not self._kernel.loop or not self._kernel.loop.is_running():
                return {'status':'ACTION_BLOCKED','reply':'Kernel mínimo indisponível.','logs':[]}
            future = asyncio.run_coroutine_threadsafe(dispatch(), self._kernel.loop)
            command = future.result(timeout=15)
            outcome = command.result if isinstance(command.result,dict) else {'status':'ACTION_FAILED','code':'DISPATCH_FAILED'}
            status = outcome.get('status','ACTION_FAILED')
            logger.info('[P4] task_id=%s proposal_id=%s bridge_status=%s result=%s', task_id, operation_id, command.status, status)
            return {'status':status,'reply':f"{status}: {outcome}",'logs':[],'task_id':task_id,'proposal_id':operation_id}
        except Exception as exc:
            token.set()
            if future is not None: future.cancel()
            return {'status':'ACTION_FAILED','reply':f'Despacho não confirmado: {type(exc).__name__}', 'logs':[], 'task_id':task_id,'proposal_id':operation_id}
        finally:
            token.set()
            with self._p4_lock:
                self._p4_pending.pop(operation_id,None)

    def cancel_p4_proposal(self, task_id, operation_id):
        if not isinstance(task_id, str) or not isinstance(operation_id, str):
            return {'status':'ACTION_BLOCKED','reply':'Identificadores inválidos.'}
        with self._p4_lock:
            pending = self._p4_pending.get(operation_id)
            if pending is None or pending[0].task_id != task_id:
                return {'status':'ACTION_BLOCKED','reply':'Proposta ausente ou incompatível.'}
            proposal, approval, budget = pending
            if not approval.cancel():
                return {'status':'ACTION_BLOCKED','reply':'Cancelamento não confirmado; operação já iniciada ou finalizada.'}
            budget.cancellation_event.set()
            self._p4_pending.pop(operation_id, None)
        return {'status':'CANCELLED','reply':'Proposta cancelada; nenhum movimento autorizado.'}

    def get_logs(self) -> List[Dict[str, Any]]:
        return list(ring_handler.records)

    def get_theme(self) -> str:
        return _load_app_config().get("theme", "dark")

    def get_runtime_telemetry(self) -> Dict[str, Any]:
        sampler = getattr(self._kernel, '_runtime_telemetry', None)
        if sampler is None:
            return {'available': False, 'reason': 'Coletor indisponível'}
        result = sampler.snapshot()
        lock = getattr(self._kernel, '_runtime_task_lock', None)
        registry = getattr(self._kernel, '_runtime_tasks', {})
        if lock is not None:
            with lock:
                tasks = [task.snapshot() for task in registry.values()]
                recent = [task.snapshot() for task in getattr(self._kernel, '_runtime_recent_tasks', ())]
        else:
            tasks = []
            recent = []
        result['kernel'] = {'running': bool(getattr(self._kernel, 'is_running', False)),
                            'active_tasks': tasks, 'recent_tasks': recent, 'queue': None,
                            'reason': 'Fila e modelos ocupados não possuem fonte comum confirmada'}
        return result

    def get_effort_mode(self) -> Dict[str, Any]:
        mode = _load_app_config().get('effort_mode', 'AUTO')
        return {'ok': True, 'mode': mode if mode in ('AUTO', 'FAST', 'BALANCED', 'DEEP') else 'AUTO'}

    def get_conversation_status(self) -> Dict[str, Any]:
        cfg = _load_app_config()
        profile = cfg.get('conversation_profile', 'PADRAO')
        model = cfg.get('conversation_model', 'qwen2.5:1.5b')
        if profile not in ('PADRAO', 'LIVRE'): profile = 'PADRAO'
        if not isinstance(model, str) or not model.strip(): model = 'qwen2.5:1.5b'
        return {'ok': True, 'profile': profile, 'model': model, 'availability': 'UNKNOWN',
                'scope': 'conversational_inference_only'}

    def set_effort_mode(self, mode: str) -> Dict[str, Any]:
        if mode not in ('AUTO', 'FAST', 'BALANCED', 'DEEP'):
            return {'ok': False, 'error': 'Modo inválido'}
        cfg = _load_app_config()
        cfg['effort_mode'] = mode
        _save_app_config(cfg)
        if _load_app_config().get('effort_mode') != mode:
            return {'ok': False, 'error': 'Não foi possível salvar a preferência'}
        return {'ok': True, 'mode': mode}

    def set_theme(self, theme: str) -> None:
        cfg = _load_app_config()
        cfg["theme"] = str(theme or "dark").strip().lower()
        _save_app_config(cfg)

    def list_shortcuts(self) -> List[Dict[str, Any]]:
        return list(_load_app_config().get("shortcuts") or [])

    def add_shortcut(self, name: str, path: str) -> Dict[str, Any]:
        cfg = _load_app_config()
        items = list(cfg.get("shortcuts") or [])
        item = {"id": uuid.uuid4().hex[:12], "name": name, "path": path}
        items.append(item)
        cfg["shortcuts"] = items
        _save_app_config(cfg)
        return {"ok": True, "item": item, "items": items, "log": f"Atalho '{name}' salvo."}

    def remove_shortcut(self, shortcut_id: str) -> Dict[str, Any]:
        cfg = _load_app_config()
        items = [x for x in (cfg.get("shortcuts") or []) if x.get("id") != shortcut_id]
        cfg["shortcuts"] = items
        _save_app_config(cfg)
        return {"ok": True, "items": items, "log": "Atalho removido."}

    def launch_shortcut(self, shortcut_id: str) -> Dict[str, Any]:
        items = self.list_shortcuts()
        item = next((x for x in items if x.get("id") == shortcut_id), None)
        if not item:
            return {"ok": False, "log": "Atalho não encontrado."}
        try:
            os.startfile(item["path"])
            return {"ok": True, "log": f"Atalho '{item['name']}' aberto."}
        except Exception as e:
            return {"ok": False, "log": str(e)}

    def set_voice(self, enabled: bool) -> Dict[str, Any]:
        self._voice_active = enabled
        if enabled:
            self._ear.start_listening()
        else:
            self._ear.stop_listening()
            self._kernel.voice.parar()
        return {"ok": True, "active": enabled}

    def stop_execution(self) -> Dict[str, Any]:
        """Revoke active command authority; do not claim native work has ended."""
        from execution_authority import revoke_all_commands
        tokens = revoke_all_commands()
        with self._kernel._runtime_task_lock:
            for budget in self._kernel._runtime_tasks.values():
                budget.cancellation_event.set()
        with self._p4_lock:
            for _, approval, budget in self._p4_pending.values():
                approval.cancel()
                budget.cancellation_event.set()
            self._p4_pending.clear()
        self._skill_abort.set()
        self._voice_active = False
        self._ear.stop_listening()
        logger.info('[STOP] cancellation requested; revoked_commands=%s', len(tokens))
        return {'ok': True, 'status': 'CANCEL_REQUESTED',
                'reply': 'Cancelamento solicitado; encerramento das operações em andamento ainda não confirmado.'}

    def stop_skill(self, skill_id: str = "") -> Dict[str, Any]:
        self._skill_abort.set()
        return {"ok": True, "aborted": True, "log": "Interrompido."}

    def run_skill(self, skill_id: str, action: str, payload: dict) -> Dict[str, Any]:
        payload = payload or {}
        sid = (skill_id or "").lower()
        if sid in self._kernel.skill_registry:
            func = self._kernel.skill_registry[sid]
            from skill_loader import normalize_skill_result
            res = normalize_skill_result(func(**payload) if payload else func())
            return {"ok": not (isinstance(res, dict) and res.get('status') == 'PROPOSAL_ONLY'), "result": res, "log": str(res)}
        return {"ok": False, "log": f"Skill '{sid}' não encontrada."}

    def toggle_fullscreen(self) -> bool:
        if self._window:
            self._window.toggle_fullscreen()
            return True
        return False

    def set_widget_mode(self, enabled: bool) -> Dict[str, Any]:
        self._widget_mode = bool(enabled)
        if not self._window:
            return {"ok": False, "widget": self._widget_mode}
        sw = ctypes.windll.user32.GetSystemMetrics(0)
        sh = ctypes.windll.user32.GetSystemMetrics(1)
        if enabled:
            self._window.resize(128, 128)
            self._window.move(sw - 160, sh - 200)
            return {"ok": True, "widget": True}
        self._window.resize(int(sw * 0.94), int(sh * 0.90))
        self._window.move(int(sw * 0.03), int(sh * 0.05))
        return {"ok": True, "widget": False}


# ------------------------------------------------------------------------------
# PONTO DE ENTRADA DO KERNEL & MASTERSHELL
# ------------------------------------------------------------------------------

def start_kernel_thread(kernel_inst: BrainnetKernel) -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(kernel_inst.start())


if __name__ == "__main__":
    kernel = BrainnetKernel()
    bridge = BrainnetBridge(kernel)

    t = threading.Thread(target=start_kernel_thread, args=(kernel,), daemon=True)
    t.start()

    time.sleep(0.8)
    logger.info("Lançando MasterShell React via PyWebView...")

    user32 = ctypes.windll.user32
    screen_w = user32.GetSystemMetrics(0)
    screen_h = user32.GetSystemMetrics(1)

    win_w = int(screen_w * 0.94)
    win_h = int(screen_h * 0.90)
    win_x = int((screen_w - win_w) / 2)
    win_y = int((screen_h - win_h) / 2)

    if kernel.minimal_mode:
        p3_port = int(os.getenv('BRAINNET_MINIMAL_GUI_PORT', '5197'))
        if not 1024 <= p3_port <= 65535:
            raise ValueError('Porta inválida para perfil mínimo')
        shell_url = f"http://127.0.0.1:{p3_port}"
    else:
        shell_url = "http://localhost:5173"
    window = webview.create_window(
        title="BRAINNET v7 - Master Shell (Kernel mínimo experimental)" if kernel.minimal_mode else "BRAINNET v7 - Master Shell",
        url=shell_url,
        js_api=bridge,
        transparent=False,
        frameless=False,
        resizable=True,
        width=win_w,
        height=win_h,
        x=win_x,
        y=win_y,
        background_color="#0d0d14",
    )
    bridge._window = window

    shutdown_guard = threading.Lock()
    shutdown_started = threading.Event()
    def shutdown_minimal():
        if not kernel.minimal_mode:
            return
        with shutdown_guard:
            if shutdown_started.is_set():
                return
            shutdown_started.set()
            logger.info('[P4_SHUTDOWN] started pid=%s', os.getpid())
            from execution_authority import revoke_all_commands
            revoke_all_commands()
            with bridge._p4_lock:
                for _, approval, budget in bridge._p4_pending.values():
                    approval.cancel()
                    budget.cancellation_event.set()
            kernel.is_running = False
            if kernel.loop and kernel.loop.is_running():
                kernel.loop.call_soon_threadsafe(lambda: None)
            t.join(timeout=3.0)
            remaining = sum(1 for worker in kernel.bridge._workers if not worker.done())
            logger.info('[P4_SHUTDOWN] completed=%s kernel_thread_alive=%s remaining_workers=%s',
                        not t.is_alive() and remaining == 0, t.is_alive(), remaining)
    if kernel.minimal_mode:
        window.events.closing += shutdown_minimal
    try:
        webview.start(debug=False, private_mode=False)
    finally:
        if kernel.minimal_mode:
            shutdown_minimal()
        elif os.getenv('BRAINNET_ADAPTIVE_OBSERVE') == '1':
            kernel.is_running = False
            t.join(timeout=4.0)
            if t.is_alive():
                logger.warning('[ADAPTIVE-OBSERVE] encerramento do kernel ainda pendente')
