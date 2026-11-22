# ==============================================================================
# BRAINNET v7 - SISTEMA OPERACIONAL COGNITIVO
# MODULO: causal_trajectory.py
# FUNCAO: Motor de Invariância Conceitual, Superposição Probabilística de
#         Affordances e Prova Factual de Transição de Estado (PoST).
# Tag: [BN_CAUSAL_TRAJECTORY]
# ==============================================================================

from __future__ import annotations

import asyncio
import ctypes
import hashlib
from ctypes import wintypes
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import threading
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
import urllib.parse
import urllib.request
import winreg

import numpy as np
import psutil

BRAIN_DIR = Path(__file__).resolve().parent
if str(BRAIN_DIR) not in sys.path:
    sys.path.insert(0, str(BRAIN_DIR))

from context_capture import ContextCapture
from execution_authority import authorized_trajectory, require_action_allowed
from owned_processes import track_process
from system_intent import application_matches, find_app_process, has_system_terms, is_web_navigation, system_launch_target
from htn_planner import compile_primitives, parse_objectives
from contextvars import ContextVar
from assistant_prompts import GENERAL_TEXT_PROMPT
from perception_eye import PerceptionEye
from effector import Effector
from actuator_bridge import ActuatorBridge, CommandPriority
from hyperdimensional import FHRRHyperdimensionalEngine
from pdag_engine import MyelinatedPDAGEngine
from shadow_simulator import ShadowSimulator
from cybernetic_verifier import CyberneticVerifier
from ghrr_spatial import FractionalSpatialCortex

logger = logging.getLogger("BRAINNET_Trajectory")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

DWMWA_CLOAKED = 14
SW_RESTORE = 9
HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_NOMOVE, SWP_NOSIZE = 0x0002, 0x0001
VK_MENU = 0x12
VK_ESCAPE = 0x1B

user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.SetWindowPos.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.BringWindowToTop.restype = wintypes.BOOL
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.AttachThreadInput.restype = wintypes.BOOL


class DynamicAppInventory:
    """
    [ESCANER PROBABILÍSTICO DO CORPO DO SO]:
    Mapeia portais do sistema sem depender de listas manuais estáticas.
    """
    __slots__ = ("_inventory", "_last_scan")

    def __init__(self) -> None:
        self._inventory: Dict[str, Dict[str, str]] = {}
        self._last_scan: float = 0.0

    def refresh_inventory(self, force: bool = False) -> Dict[str, Dict[str, str]]:
        now = time.time()
        if not force and self._inventory and (now - self._last_scan) < 60.0:
            return self._inventory

        t0 = time.perf_counter_ns()
        novo_inventario: Dict[str, Dict[str, str]] = {}

        # 1. HKLM & HKCU App Paths
        for hkey in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hkey, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths") as base_k:
                    num_subkeys = winreg.QueryInfoKey(base_k)[0]
                    for i in range(num_subkeys):
                        try:
                            subkey_name = winreg.EnumKey(base_k, i)
                            with winreg.OpenKey(base_k, subkey_name) as k:
                                val, _ = winreg.QueryValueEx(k, "")
                                if val and os.path.exists(val):
                                    stem = subkey_name.lower().replace(".exe", "")
                                    novo_inventario[stem] = {"tipo": "PATH", "cmd": val}
                        except OSError:
                            continue
            except OSError:
                pass

        # 2. Resolução de Atalhos do Menu Iniciar (.lnk)
        pastas_atalhos = [
            os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"),
            os.path.expandvars(r"%AppData%\Microsoft\Windows\Start Menu\Programs")
        ]
        for pasta in pastas_atalhos:
            if os.path.exists(pasta):
                for root, _, files in os.walk(pasta):
                    for f in files:
                        if f.endswith(".lnk"):
                            nome_limpo = f[:-4].lower().strip()
                            if not any(ign in nome_limpo for ign in ["desinstalar", "uninstall", "help", "readme"]):
                                if nome_limpo not in novo_inventario:
                                    novo_inventario[nome_limpo] = {
                                        "tipo": "LNK",
                                        "cmd": os.path.join(root, f)
                                    }

        # 3. Protocolos Universais Canônicos
        protocolos_padrao = {
            "whatsapp": "whatsapp:",
            "configuracoes": "ms-settings:",
            "settings": "ms-settings:",
            "bluetooth": "ms-settings:bluetooth",
            "som": "ms-settings:sound",
            "rede": "ms-settings:network",
            "wifi": "ms-settings:network-wifi",
            "terminal": "wt.exe",
            "cmd": "cmd.exe",
            "bloco de notas": "notepad.exe",
            "notepad": "notepad.exe",
            "calculadora": "calc.exe",
            "calc": "calc.exe",
            "explorer": "explorer.exe"
        }
        for k, v in protocolos_padrao.items():
            if k not in novo_inventario:
                novo_inventario[k] = {"tipo": "PROTOCOL_OR_EXE", "cmd": v}

        self._inventory = novo_inventario
        self._last_scan = now
        elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000.0
        logger.info(f"[DYNAMIC_INVENTORY]: {len(novo_inventario)} affordances indexadas em {elapsed_ms:.2f}ms.")
        return self._inventory

    def resolve_app_probabilistic(self, target_concept: str, vsa: FHRRHyperdimensionalEngine) -> Optional[Dict[str, str]]:
        t = target_concept.lower().strip()
        inv = self.refresh_inventory(force=False)

        if t in inv:
            return inv[t]

        v_target = vsa.text_to_hypervector(t)
        melhor_match = None
        maior_sim = -1.0

        for nome, dados in inv.items():
            if t not in nome and nome not in t:
                continue
            v_cand = vsa.text_to_hypervector(nome)
            sim = vsa.similarity(v_target, v_cand)
            if t in nome or nome in t:
                sim += 0.35

            if sim > maior_sim:
                maior_sim = sim
                melhor_match = dados

        if maior_sim >= 0.20:
            return melhor_match

        return None


class WindowsAppResolver:
    """
    [RESOLVEDOR PROBABILÍSTICO DE PORTAIS WIN32]:
    Localiza, foca e quebra o Foreground Lockout.
    """
    _inventory_engine = DynamicAppInventory()
    _start_menu_lock = threading.RLock()

    def __init__(self, effector=None):
        self._effector = effector if effector is not None else Effector()

    @staticmethod
    def _start_menu_has_focus():
        hwnd = user32.GetForegroundWindow()
        pid = wintypes.DWORD()
        if not hwnd:
            return False
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            return psutil.Process(pid.value).name().casefold() in (
                "startmenuexperiencehost.exe", "searchhost.exe", "searchapp.exe")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def _open_via_start_menu(self, app_name: str):
        require_action_allowed("ENSURE_APP")
        if not isinstance(app_name, str) or not app_name.strip() or len(app_name) > 120:
            raise ValueError("Nome de aplicativo inválido")
        with self._start_menu_lock:
            from focus_isolation import suspend_master_shell_focus
            suspend_master_shell_focus(3.0)
            user32.keybd_event(0x5B, 0, 0, 0)
            user32.keybd_event(0x5B, 0, 2, 0)
            time.sleep(0.8)
            require_action_allowed("TYPE")
            if not self._start_menu_has_focus():
                raise RuntimeError("Menu Iniciar sem foco; nenhuma digitacao foi enviada")
            if self._effector.send_text(app_name) is not True:
                raise RuntimeError("Nome do aplicativo não foi digitado")
            time.sleep(0.5)
            require_action_allowed("HOTKEY")
            if not self._start_menu_has_focus():
                raise RuntimeError("Foco saiu da busca; Enter bloqueado")
            user32.keybd_event(0x0D, 0, 0, 0)
            user32.keybd_event(0x0D, 0, 2, 0)
            return True

    @classmethod
    def resolve_app_probabilistic(cls, target_concept: str, vsa: Optional[FHRRHyperdimensionalEngine] = None) -> Optional[Dict[str, str]]:
        """Delegador publico ao DynamicAppInventory para grounding conceitual."""
        return cls._inventory_engine.resolve_app_probabilistic(target_concept, vsa)

    @classmethod
    def is_process_running(cls, proc_name: str) -> bool:
        alvo = proc_name.lower().replace(".exe", "").strip()
        for p in psutil.process_iter(['name']):
            try:
                pname = p.info['name'].lower()
                if alvo in pname:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    @classmethod
    def foreground_app_hwnd(cls, target: str) -> Optional[int]:
        return cls.app_hwnd(target, user32.GetForegroundWindow())

    @classmethod
    def app_hwnd(cls, target: str, hwnd: int) -> Optional[int]:
        """Read-only Win32 identity check, including Canvas/Electron window titles."""
        if not hwnd or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return None
        title = ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(hwnd) + 1)
        user32.GetWindowTextW(hwnd, title, len(title))
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            process = psutil.Process(pid.value).name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None
        if process.casefold() == "applicationframehost.exe":
            from system_intent import hosted_app_window
            return hwnd if hosted_app_window(target, hwnd) else None
        from system_intent import app_process_names
        return hwnd if process.casefold() in app_process_names(target) or application_matches(target, process, title.value) else None

    @classmethod
    def focus_window_handle(cls, hwnd: int) -> bool:
        require_action_allowed("FOCUS_WINDOW")
        if not hwnd or not user32.IsWindow(hwnd):
            return False
        current = kernel32.GetCurrentThreadId()
        foreground_thread = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
        attached = user32.AttachThreadInput(current, foreground_thread, True)
        try:
            require_action_allowed("FOCUS_WINDOW")
            user32.ShowWindow(hwnd, SW_RESTORE)
            try:
                user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
            finally:
                user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
            user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(current, foreground_thread, False)
        return user32.GetForegroundWindow() == hwnd and bool(user32.IsWindowVisible(hwnd))

    @classmethod
    def find_and_focus_window(cls, app_substr: str, is_background: bool = False) -> Optional[int]:
        require_action_allowed("FOCUS_WINDOW", is_background)
        target = app_substr.lower().replace(".exe", "").strip()
        matching_pids = set()

        for p in psutil.process_iter(['pid', 'name']):
            try:
                pname = p.info['name'].lower()
                if target in pname:
                    matching_pids.add(p.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if not matching_pids:
            from system_intent import hosted_app_window
            hosted = hosted_app_window(target)
            return hosted["hwnd"] if hosted and cls.focus_window_handle(hosted["hwnd"]) else None

        found_hwnds: List[int] = []

        def enum_win(hwnd: int, _: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True

            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True

            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.strip()

            titulos_ignorados = ("default ime", "msctfime ui", "gdi+ window", "program manager", "settings")
            if not title or title.lower() in titulos_ignorados:
                return True

            if user32.GetWindow(hwnd, 4) != 0:
                return True

            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in matching_pids:
                cloaked = ctypes.c_int(0)
                dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
                if cloaked.value == 0:
                    rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    w = rect.right - rect.left
                    h = rect.bottom - rect.top
                    if user32.IsIconic(hwnd) or (rect.left > -1000 and rect.top > -1000 and w > 280 and h > 200):
                        found_hwnds.append(hwnd)
                        return False
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_win), 0)

        if found_hwnds:
            require_action_allowed("FOCUS_WINDOW", is_background)
            target_hwnd = found_hwnds[0]
            cur_thread = kernel32.GetCurrentThreadId()
            fg_hwnd = user32.GetForegroundWindow()
            fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)

            attached = user32.AttachThreadInput(cur_thread, fg_thread, True)
            try:
                user32.ShowWindow(target_hwnd, SW_RESTORE)
                try:
                    user32.SetWindowPos(target_hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
                finally:
                    user32.SetWindowPos(target_hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
                user32.SetForegroundWindow(target_hwnd)
            finally:
                if attached:
                    user32.AttachThreadInput(cur_thread, fg_thread, False)
            time.sleep(0.12)
            return target_hwnd if user32.GetForegroundWindow() == target_hwnd and user32.IsWindowVisible(target_hwnd) else None

        from system_intent import hosted_app_window
        hosted = hosted_app_window(target)
        return hosted["hwnd"] if hosted and cls.focus_window_handle(hosted["hwnd"]) else None

    @classmethod
    def launch_app(cls, app_concept: str, vsa: Optional[FHRRHyperdimensionalEngine] = None, is_background: bool = False) -> bool:
        require_action_allowed("ENSURE_APP", is_background)
        vsa_eng = vsa or FHRRHyperdimensionalEngine(10_000)
        target = app_concept.lower().strip()

        if any(m in target for m in ["menu iniciar", "start menu"]):
            user32.keybd_event(0x5B, 0, 0, 0)
            time.sleep(0.04)
            user32.keybd_event(0x5B, 0, 2, 0)
            time.sleep(0.3)
            return True

        hwnd_existente = cls.find_and_focus_window(target)
        if hwnd_existente and user32.GetForegroundWindow() == hwnd_existente:
            return True

        if "whatsapp" in target:
            try:
                track_process(subprocess.Popen(["powershell", "-WindowStyle", "Hidden", "-Command", 'Start-Process "whatsapp:"'], creationflags=0x08000000))
            except Exception:
                pass

        dados = cls._inventory_engine.resolve_app_probabilistic(target, vsa_eng)
        require_action_allowed("ENSURE_APP", is_background)
        if dados:
            cmd = dados["cmd"]
            tipo = dados["tipo"]
            try:
                if tipo == "PATH" and os.path.exists(cmd):
                    os.startfile(cmd)
                elif tipo == "LNK" and os.path.exists(cmd):
                    os.startfile(cmd)
                elif tipo == "PROTOCOL_OR_EXE":
                    track_process(subprocess.Popen(f"start {cmd}", shell=True))
                else:
                    track_process(subprocess.Popen(cmd, shell=True))
            except Exception as e:
                logger.warning(f"Erro ao disparar comando '{cmd}': {e}")

        for _ in range(24):
            time.sleep(0.3)
            hwnd_novo = cls.find_and_focus_window(target)
            if hwnd_novo:
                return True

        require_action_allowed("ENSURE_APP", is_background)
        cls()._open_via_start_menu(target)
        if target.casefold() in ("calc", "calc.exe", "calculator", "calculadora", "calculatorapp"):
            time.sleep(3.0)
        for _ in range(20):
            time.sleep(0.3)
            if find_app_process(target):
                return True

        return False


_located_element = ContextVar("brainnet_located_element", default=None)
_visual_click = ContextVar("brainnet_visual_click", default=None)
_last_clicked = ContextVar("brainnet_last_clicked", default=None)


class TargetMismatchError(RuntimeError):
    """A requested message recipient was not confirmed in the conversation header."""


class CausalTrajectoryEngine:
    """
    [CÓRTEX DE SUPERPOSIÇÃO CONCEITUAL E AÇÃO NÃO-LINEAR]:
    Motor de trajetórias que obriga a validação física M_SO antes de reportar sucesso.
    """

    __slots__ = (
        "ctx_engine", "eye", "effector", "bridge", "vsa", "pdag",
        "shadow", "resolver", "verifier", "hmem", "ontology",
        "browser_bridge", "concept_communicator", "concept_navigator",
        "concept_transcriptor", "concept_system", "concept_inspector",
        "concept_cortex", "blackbox", "vision_eye", "syntactic_pdag",
        "spatial_cortex",
    )

    def __init__(
        self,
        ctx_engine: ContextCapture,
        eye: PerceptionEye,
        effector: Effector,
        bridge: ActuatorBridge,
        vsa: FHRRHyperdimensionalEngine,
        pdag: MyelinatedPDAGEngine,
        shadow: ShadowSimulator,
        verifier: CyberneticVerifier,
    ) -> None:
        self.ctx_engine = ctx_engine
        self.eye = eye
        self.effector = effector
        self.bridge = bridge
        self.vsa = vsa
        self.pdag = pdag
        self.shadow = shadow
        self.resolver = WindowsAppResolver(self.effector)
        self.verifier = verifier
        self.browser_bridge = None
        self.concept_cortex = None
        self.blackbox = None
        self.vision_eye = None
        self.syntactic_pdag = None
        
        # Tática 2: Córtex Espacial (Fractional Power Encoding no FHRR)
        self.spatial_cortex = FractionalSpatialCortex(self.vsa)

        self.concept_communicator = self.vsa.text_to_hypervector("CONCEITO_PORTAL_COMUNICACAO_MENSAGEM_CHAT_CONTATO_INTERACAO")
        self.concept_navigator = self.vsa.text_to_hypervector("CONCEITO_PORTAL_NAVEGACAO_INFORMACAO_WEB_BUSCA_URL_PAGINA")
        self.concept_transcriptor = self.vsa.text_to_hypervector("CONCEITO_PORTAL_TRANSCRICAO_DOCUMENTO_CODIGO_ESCRITA_REGISTRO")
        self.concept_system = self.vsa.text_to_hypervector("CONCEITO_PORTAL_SISTEMA_EXECUTAVEL_APLICATIVO_HARDWARE_TERMINAL")
        self.concept_inspector = self.vsa.text_to_hypervector("CONCEITO_PORTAL_INSPECAO_PERCEPCAO_TELA_MONITOR_LEITURA")

    def _projetar_onda_de_probabilidade(self, intencao: str) -> Dict[str, float]:
        if has_system_terms(intencao):
            route = "NAVEGACAO" if is_web_navigation(intencao) else "ESTADO_SISTEMA"
            return {name: float(name == route) for name in ("COMUNICACAO", "NAVEGACAO", "TRANSCRICAO", "ESTADO_SISTEMA", "INSPECAO")}
        v_intencao = self.vsa.text_to_hypervector(intencao.lower().strip())
        
        sims = {
            "COMUNICACAO": max(0.0, self.vsa.similarity(v_intencao, self.concept_communicator)),
            "NAVEGACAO": max(0.0, self.vsa.similarity(v_intencao, self.concept_navigator)),
            "TRANSCRICAO": max(0.0, self.vsa.similarity(v_intencao, self.concept_transcriptor)),
            "ESTADO_SISTEMA": max(0.0, self.vsa.similarity(v_intencao, self.concept_system)),
            "INSPECAO": max(0.0, self.vsa.similarity(v_intencao, self.concept_inspector)),
        }

        s_vals = np.array(list(sims.values()), dtype=np.float32)
        exp_s = np.exp(s_vals * 10.0)
        probs = exp_s / np.sum(exp_s)

        return {k: float(probs[i]) for i, k in enumerate(sims.keys())}

    def _generate_creative_text(self, instruction: str, task_budget=None) -> str:
        if task_budget is not None:
            task_budget.reserve('inference', estimated_tokens=2048)
        payload = {"model": "iaos-qwen:latest", "stream": False, "keep_alive": "5m",
                   "prompt": GENERAL_TEXT_PROMPT + "Gere somente o texto solicitado, completo, sem preâmbulo nem blocos de código.\nPEDIDO: " + instruction,
                   "options": {"temperature": 0.6, "num_ctx": 8192, "num_thread": 14, "num_predict": 2048}}
        request = urllib.request.Request("http://localhost:11434/api/generate", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
        text = result.get("response", "")
        if result.get("done") is not True or result.get("done_reason") == "length" or not isinstance(text, str) or not text.strip():
            raise RuntimeError("O 7B nao retornou o texto criativo completo; nenhuma digitacao foi autorizada")
        return text.strip()

    def extrair_proposito(self, v_qualia):
        return self.vsa.unbind(v_qualia, self.vsa.role_telic)

    def decompor_trajetoria_cognitiva(self, objetivo: str, task_budget=None) -> Dict[str, Any]:
        if task_budget is not None:
            task_budget.reserve('planning')
        generate_text = lambda instruction: self._generate_creative_text(instruction, task_budget)
        # A recovered legacy route is a proposal only; it never becomes motor steps.
        if getattr(self, "syntactic_pdag", None) is not None:
            route_key = f"trajectory:ghrr:{objetivo.lower().strip()[:40]}"
            proposal = self.syntactic_pdag.propose_route(route_key)
            if proposal:
                return {
                    "monologo_socratico": ["Rota GHRR exige revisão de contexto e autorização."],
                    "passos": [], "pipeline": [], "goals": [],
                    "ghrr_proposal": proposal, "source_route_key": route_key
                }

        from teacher_slots import instantiate_message
        if isinstance(objetivo, str):
            message_route = instantiate_message(getattr(self, "pdag", None), objetivo)
            if message_route is not None:
                message_route["source_route_key"] = "trajectory:enviar_mensagem_generico"
                return message_route
        from parser_contract import normalize_input
        objetivo, blocked = normalize_input(objetivo)
        if blocked:
            return {"passos": [], "pipeline": [], "goals": []}
        substituicoes_foneticas = {
            r"\b(thoruym|toryum|torium|thoruim|thorium|notorium|torio|tório)\b": "thorium",
            r"\b(navageaor|navegador|navagador|nabegador)\b": "navegador",
            r"\b(whatsappp|whatsap|uatsap|zapzap|uati|zap)\b": "whatsapp",
            r"\b(bloco de nootas|bloco de nota)\b": "bloco de notas",
            r"\b(dige|digite|digiti)\b": "digite",
        }
        partes = re.split(r'''("[^"]*"|'[^']*'|“[^”]*”)''', objetivo)
        for padrao, sub in substituicoes_foneticas.items():
            for index in range(0, len(partes), 2):
                partes[index] = re.sub(padrao, sub, partes[index], flags=re.IGNORECASE)
        objetivo = "".join(partes)
        t_low = objetivo.lower().strip()
        
        # Rota cirúrgica de encerramento
        match_close = re.match(r"^(?:feche|fechar|encerre|encerrar|mate|matar|finalize)\s+(?:o\s+|a\s+)?(.+)", t_low)
        if match_close:
            app_to_close = match_close.group(1).strip()
            return {"monologo_socratico": [f"Rota de encerramento cirúrgico para '{app_to_close}'."],
                    "passos": [{"passo": 1, "acao": "FOCUS_WINDOW", "app": app_to_close}, {"passo": 2, "acao": "HOTKEY", "keys": ["alt", "f4"]}],
                    "pipeline": [{"p": "FOCUS_WINDOW", "app": app_to_close}, {"p": "HOTKEY", "keys": ["alt", "f4"]}]}

        # Rota cirúrgica de minimização
        match_min = re.match(r"^(?:minimize|minimizar)\s+(?:o\s+|a\s+)?(.+)", t_low)
        if match_min:
            app_to_min = match_min.group(1).strip()
            return {"monologo_socratico": [f"Rota de minimização cirúrgica para '{app_to_min}'."],
                    "passos": [{"passo": 1, "acao": "FOCUS_WINDOW", "app": app_to_min}, {"passo": 2, "acao": "MINIMIZE_WINDOW", "app": app_to_min}],
                    "pipeline": [{"p": "FOCUS_WINDOW", "app": app_to_min}, {"p": "MINIMIZE_WINDOW", "app": app_to_min}]}

        # Rota cirúrgica de maximização
        match_max = re.match(r"^(?:maximize|maximizar|restaure|restaurar)\s+(?:o\s+|a\s+)?(.+)", t_low)
        if match_max:
            app_to_max = match_max.group(1).strip()
            return {"monologo_socratico": [f"Rota de maximização cirúrgica para '{app_to_max}'."],
                    "passos": [{"passo": 1, "acao": "FOCUS_WINDOW", "app": app_to_max}, {"passo": 2, "acao": "MAXIMIZE_WINDOW", "app": app_to_max}],
                    "pipeline": [{"p": "FOCUS_WINDOW", "app": app_to_max}, {"p": "MAXIMIZE_WINDOW", "app": app_to_max}]}

        goals = parse_objectives(objetivo)
        if len(goals) == 1 and goals[0]["kind"] == "OPEN_APP":
            from concept_cortex import ConceptCortex
            generic_route = ConceptCortex.instantiate_generic_opening(getattr(self, "pdag", None), goals[0]["roles"]["APP_ALVO"])
            if generic_route is not None:
                steps = generic_route["pipeline"]["passos"]
                return {"monologo_socratico": ["Rota abstrata instanciada sem LLM."], "passos": steps,
                        "pipeline": [{"p": step["acao"], **{k: v for k, v in step.items() if k not in ("acao", "passo", "feedback")}} for step in steps],
                        "goals": goals, "source_route_key": "trajectory:abrir_app_generico"}
        if goals and goals[0]["kind"] == "OPEN_APP":
            target = goals[0]["roles"]["APP_ALVO"]
            from qualia_algebra import retrieve_opening
            qualia = retrieve_opening(self, target)
            if qualia is not None:
                plan = compile_primitives(goals, generate_text=generate_text, web_search=is_web_navigation(objetivo))
                plan["pipeline"][0] = qualia["pipeline"][0]
                plan["qualia_transfer"] = qualia
                return plan
            finder = getattr(getattr(self, "pdag", None), "find_abstract_opening", None)
            transfer = finder(target, self.vsa) if callable(finder) and getattr(self, "vsa", None) is not None else None
            if isinstance(transfer, dict) and transfer.get("similarity", 0) > 0.70:
                plan = compile_primitives(goals, generate_text=generate_text, web_search=is_web_navigation(objetivo))
                plan["transferencia_conceitual"] = transfer
                plan["pipeline"][0] = {"p": "OPEN_APP", "app": transfer["pipeline"][0]["app"]}
                return plan
        generic = self._generic_opening_available()
        if goals and (len(goals) > 1 or generic or goals[0]["kind"] == "CLICK_TEXT"):
            return compile_primitives(goals, generate_text=generate_text, web_search=is_web_navigation(objetivo))

        distribuicao = self._projetar_onda_de_probabilidade(t_low)
        conceito_dominante = max(distribuicao, key=distribuicao.get)
        app_literal = system_launch_target(objetivo)
        if app_literal and not is_web_navigation(objetivo):
            return {"monologo_socratico": [f"Busca nativa no Menu Iniciar por '{app_literal}', seguida de verificacao HWND."],
                    "passos": [{"passo": 1, "acao": "START_MENU_SEARCH", "app": app_literal}],
                    "pipeline": [{"p": "OPEN_APP", "app": app_literal}]}
        if has_system_terms(objetivo) and conceito_dominante == "COMUNICACAO":
            conceito_dominante = "ESTADO_SISTEMA"

        if conceito_dominante == "TRANSCRICAO":
            editor = "code" if any(w in t_low for w in ["code", "vscode", "script"]) else "notepad"
            payload = objetivo
            match_aspas = re.search(r"['\"“](.+?)['\"”]", objetivo)
            if match_aspas:
                payload = match_aspas.group(1)
            elif re.search(r"\b(?:poema|poesia|soneto|haicai)\b", objetivo, re.I):
                payload = generate_text(objetivo)

            passos = [
                {"passo": 1, "acao": "ENSURE_APP", "app": editor},
                {"passo": 2, "acao": "FOCUS_WINDOW", "app": editor},
                {"passo": 3, "acao": "WAIT", "seconds": 0.4},
                {"passo": 4, "acao": "TYPE", "text": f"\n{payload}\n"}
            ]
            return {
                "monologo_socratico": [
                    f"1. Invariante: Transcrição em Editor ({distribuicao['TRANSCRICAO']:.2%}).",
                    f"2. Editor: '{editor}'."
                ],
                "passos": passos
            }

        else:
            app_alvo = system_launch_target(objetivo)
            if not app_alvo:
                return {"monologo_socratico": ["Nenhum alvo literal de abertura foi identificado; sem substituicao por comunicacao."], "passos": []}
            passos = [
                {"passo": 1, "acao": "ENSURE_APP", "app": app_alvo},
                {"passo": 2, "acao": "FOCUS_WINDOW", "app": app_alvo}
            ]
            return {
                "monologo_socratico": [
                    f"1. Invariante: Abertura de Portal de Sistema ({distribuicao['ESTADO_SISTEMA']:.2%}).",
                    f"2. Alvo: '{app_alvo}'."
                ],
                "passos": passos
            }

    @staticmethod
    def _expected_app_for_step(steps, index):
        action = steps[index].get("p", steps[index].get("acao"))
        if action not in ("TYPE", "HOTKEY", "CLICK", "RIGHT_CLICK", "SCROLL"):
            return None
        for prior in reversed(steps[:index]):
            if prior.get("p", prior.get("acao")) in ("OPEN_APP", "ENSURE_APP", "START_MENU_SEARCH"):
                return prior.get("app")
        return None

    @staticmethod
    def _contract_for_action(action: str, app: str = "") -> Dict[str, Any]:
        action = action.upper()
        if action == "OPEN_APP":
            return {"action": "START_MENU_SEARCH", "app": app, "expects_new_pid": False, "min_ncd": 0.0}
        if action in ("LOCATE", "LOCATE_VISUAL"):
            return {"action": action, "expects_new_pid": False, "min_ncd": 0.0}
        if action == "START_MENU_SEARCH":
            return {"action": action, "app": app, "expects_new_pid": False, "min_ncd": 0.0}
        if action in ("TYPE", "HOTKEY", "WAIT"):
            return {"action": action, "expects_new_pid": False, "min_ncd": 0.05 if action == "TYPE" else 0.02,
                    **({"app": app} if app else {})}
        if action in ("CLICK", "DRAG", "RIGHT_CLICK", "FOCUS_WINDOW", "SCROLL"):
            threshold = 0.02 if action in ("RIGHT_CLICK", "SCROLL") else 0.03 if action == "FOCUS_WINDOW" else 0.05
            return {"action": action, "expects_new_pid": False, "min_ncd": threshold}
        if action in ("MINIMIZE_WINDOW", "MAXIMIZE_WINDOW"):
            return {"action": action, "app": app, "expects_new_pid": False, "min_ncd": 0.05}
        return {"action": action, "app": app, "expects_new_pid": True}

    @staticmethod
    def _recipe_text_or_excerpt(generated: str, text_excerpt: str) -> str:
        if not isinstance(generated, str) or len(generated.strip()) < 200 or "coletados da página" in generated.casefold() or "coletados da pagina" in generated.casefold():
            if not isinstance(text_excerpt, str) or not text_excerpt.strip():
                raise ValueError("Pagina sem texto extraido; nenhuma receita generica sera salva")
            return text_excerpt
        return generated

    @staticmethod
    def _click_target_for_step(step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if str(step.get("p", step.get("acao", ""))).upper() != "CLICK":
            return None
        element = step.get("element") or step.get("target") or f"xy({step.get('x')},{step.get('y')})"
        return {"element": str(element), "x": step.get("x"), "y": step.get("y")}

    def _learn_click_feedback(self, intent_hash, click_target, pre_state, post_state, feedback):
        change = self.verifier.classificar_tipo_mudanca(pre_state, post_state)
        element = str(click_target["element"])
        app_name = str(pre_state.get("process_name", "unknown"))
        context = f"{app_name}|{str(pre_state.get('title', ''))[:30]}"
        ncd = feedback.get("ncd_real")
        low_ncd = isinstance(ncd, (int, float)) and np.isfinite(ncd) and 0.0 <= ncd < 0.20
        if low_ncd:
            change = "NADA"
        vector = self.vsa.encode_compositional(action="CLICK", target=element, param=change, context=context)
        concept = f"ELEMENTO_{change}"
        prototype_success = None
        if feedback["lambda_obs"] == 1 and change != "NADA":
            self.concept_cortex.learn_exemplar(vector, concept, success=True)
            self.vsa.register_cleanup(f"{concept}|ELEM_{time.time_ns()}|{context}|{element}", vector)
            prototype_success = True
        elif (low_ncd and pre_state.get("hwnd")
              and pre_state.get("hwnd") == post_state.get("hwnd")
              and pre_state.get("pid") == post_state.get("pid")):
            self.concept_cortex.learn_exemplar(vector, "ELEMENTO_NADA", success=False)
            self.vsa.register_cleanup(f"ELEMENTO_NADA|ELEM_{time.time_ns()}|{context}|{element}", vector)
            prototype_success = False
        audit_id = self.concept_cortex.log_click(
            intent_hash, element, app_name, change, pre_state, post_state,
            feedback["lambda_obs"] == 1, feedback["expected_delta"], prototype_success,
        )
        return {"audit_id": audit_id, "element": element, "app_name": app_name,
                "change_type": change, "prototype_success": prototype_success}

    async def _persist_semantic_transition(self, img_pre, context, feedback, metadata):
        try:
            img_post = await asyncio.to_thread(self.verifier.capture_state_bytes)
            before, after = await asyncio.to_thread(lambda: (
                hashlib.sha256(img_pre).hexdigest()[:16], hashlib.sha256(img_post).hexdigest()[:16]))
            self.pdag.record_transition(before, feedback["intent_hash"], after, feedback["lambda_obs"],
                feedback["ncd_real"], context.get("process_name", "unknown"),
                execution_id=metadata["execution_id"], intent=metadata["intent"],
                steps_json=metadata["steps_json"], expected_delta=feedback["expected_delta"],
                window_title=context.get("title", ""), trajectory_id=metadata["trajectory_id"],
                step_index=metadata["step_index"], step_count=metadata["step_count"], elapsed_ms=feedback.get("execution_elapsed_ms", feedback.get("elapsed_ms")))
        except Exception:
            logger.exception("Falha ao registrar transicao semantica; resultado factual preservado")

    async def execute_subgoal(
        self,
        intent_hash: str,
        action_fn: Callable[[], Awaitable[None]],
        timeout_sec: float = 5.0,
        expected_ncd: Optional[float] = None,
        contract: Optional[Dict[str, Any]] = None,
        click_target: Optional[Dict[str, Any]] = None,
        is_background: bool = False,
        intent: Optional[str] = None,
        step: Optional[Dict[str, Any]] = None,
        pipeline: Optional[List[Dict[str, Any]]] = None,
        trajectory_id: Optional[str] = None,
        step_index: int = 0,
        step_count: int = 1,
    ) -> Dict[str, Any]:
        action_name = (contract or {}).get("action", "EXECUTE")
        require_action_allowed("INSPECT" if action_name in ("LOCATE", "LOCATE_VISUAL") else action_name, is_background)
        if action_name in ("LOCATE", "LOCATE_VISUAL"):
            try:
                await action_fn()
                return {"status": "OBSERVED", "lambda_obs": 1, "ncd_real": None,
                        "expected_delta": None, "reward": None, "failure_reason": ""}
            except Exception as ex:
                return {"status": "FAILED_OBSERVATION", "lambda_obs": 0, "ncd_real": None,
                        "expected_delta": None, "reward": None, "failure_reason": str(ex)}
        contract = dict(contract or {})
        if click_target is not None:
            _visual_click.set(None)
            contract.update(action="CLICK", expects_new_pid=False, min_ncd=0.05)
        has_expected_ncd = expected_ncd is not None
        default_ncd = (contract or {}).get("min_ncd", 0.05) if (contract or {}).get("expects_new_pid") is False else self.verifier.ncd_threshold
        expected_ncd = default_ncd if expected_ncd is None else float(expected_ncd)
        if not 0.0 <= expected_ncd <= 1.0:
            raise ValueError("expected_ncd deve estar entre 0 e 1")
        t0 = time.perf_counter()
        loop = asyncio.get_running_loop()
        pre_context = dict(await loop.run_in_executor(None, self.ctx_engine.capture_foreground_context))
        if action_name == "TYPE":
            contract.setdefault("app", contract.get("expected_app") or str(pre_context.get("process_name", "")).removesuffix(".exe"))
        execution_id = str(uuid.uuid4())
        clean = lambda value: {k: v for k, v in value.items() if k not in ("feedback", "prior_feedback")}
        executed_step = clean(step) if step is not None else {"acao": action_name}
        recorded_pipeline = [clean(item) for item in pipeline] if pipeline is not None else [executed_step]
        metadata = {"execution_id": execution_id, "intent": intent or str(executed_step.get("acao", executed_step.get("p", action_name))),
                    "trajectory_id": trajectory_id or execution_id, "step_index": step_index, "step_count": step_count,
                    "steps_json": json.dumps({"passos": recorded_pipeline, "executed_step": executed_step}, ensure_ascii=False)}
        if click_target is not None:
            if self.concept_cortex is None or self.blackbox is None:
                raise RuntimeError("Instrumentacao CLICK exige Cortex e Caixa Preta conectados")
            if not isinstance(click_target.get("element"), str) or not click_target["element"].strip():
                raise ValueError("CLICK exige identidade textual ou coordenadas observadas")
        pids_before = await loop.run_in_executor(None, self.verifier.snapshot_pids)
        
        # Tática 1: ROI (Region of Interest) para isolar a medição do NCD
        target_hwnd = contract.get("target_hwnd") if contract else None
        bbox = None
        if target_hwnd:
            try:
                import win32gui
                r = win32gui.GetWindowRect(target_hwnd)
                if r[2] - r[0] > 50 and r[3] - r[1] > 50:
                    bbox = (r[0], r[1], r[2], r[3])
            except Exception:
                pass

        img_pre = await loop.run_in_executor(None, lambda: self.verifier.capture_state_bytes(bbox=bbox))
        if contract.get("action") in ("TYPE", "HOTKEY", "WAIT", "CLICK", "DRAG", "RIGHT_CLICK", "SCROLL", "PROFESSOR_STEP"):
            target_context = pre_context or dict(await loop.run_in_executor(None, self.ctx_engine.capture_foreground_context))
            pre_context = target_context
            contract.setdefault("target_hwnd", target_context.get("hwnd", 0))

        try:
            expected_app = contract.get("expected_app")
            if expected_app:
                focused_hwnd = await asyncio.to_thread(self.resolver.foreground_app_hwnd, expected_app)
                if not focused_hwnd:
                    await asyncio.to_thread(self.resolver.find_and_focus_window, expected_app)
                    focused_hwnd = await asyncio.to_thread(self.resolver.foreground_app_hwnd, expected_app)
                if not focused_hwnd:
                    raise RuntimeError(f"App '{expected_app}' aberto sem foco; entrada bloqueada")
                contract["target_hwnd"] = focused_hwnd
            action_result = await action_fn()
            if isinstance(action_result, dict) and (action_result.get("target_hwnd") or action_result.get("pid")) and contract.get("action") in ("OPEN_APP", "ENSURE_APP", "START_MENU_SEARCH"):
                contract.update(target_hwnd=action_result.get("target_hwnd", 0), target_pid=action_result.get("pid"), expects_new_pid=False,
                                action="START_MENU_SEARCH", min_ncd=0.0)
            elif contract.get("action") == "PROFESSOR_STEP" and isinstance(action_result, dict):
                contract["target_hwnd"] = action_result.get("professor_target_hwnd", 0)
            elif contract.get("action") == "TYPE" and isinstance(action_result, dict):
                contract["target_hwnd"] = action_result.get("professor_target_hwnd", action_result.get("target_hwnd", contract.get("target_hwnd", 0)))
        except Exception as ex:
            elapsed = (time.perf_counter() - t0) * 1000.0
            feedback = {
                "execution_id": execution_id,
                "status": "FAILED_FACTUAL",
                "lambda_obs": 0,
                "elapsed_ms": elapsed,
                "discovered_pid": None,
                "failure_reason": f"ACTION_EXCEPTION: {type(ex).__name__}: {ex}",
                "intent_hash": intent_hash,
                "ncd_real": None,
                "expected_delta": expected_ncd,
                "reward": None,
            }
            await self._persist_semantic_transition(img_pre, pre_context, feedback, metadata)
            return feedback

        if contract.get("action") == "ENSURE_APP":
            post_app = dict(await loop.run_in_executor(None, self.ctx_engine.capture_foreground_context))
            app = str(contract.get("app", "")).casefold().replace(".exe", "").strip()
            app = "notepad" if app in ("bloco de notas", "editor de texto") else app
            process_name = str(post_app.get("process_name", "")).casefold().replace(".exe", "")
            if app and app in process_name and post_app.get("pid") in pids_before and post_app.get("hwnd"):
                contract.update(expects_new_pid=False, reuse_existing=True, min_ncd=0.0, target_hwnd=post_app["hwnd"])
                if not has_expected_ncd:
                    expected_ncd = 0.0

        verification_started = time.perf_counter()
        lambda_obs, elapsed_ms, failure_reason, discovered_pid, actual_ncd, expected_ncd = await loop.run_in_executor(
            None, lambda: self.verifier.measure_collapse(
            pid_snapshot_before=pids_before,
            img_pre_bytes=img_pre,
            img_post_bytes=b"",
            timeout_sec=timeout_sec,
            expected_delta=expected_ncd,
            contract={**contract, "capture_bbox": bbox},
            ),
        )

        feedback = {
            "execution_id": execution_id,
            "status": "SUCCESS" if lambda_obs == 1 else "FAILED_FACTUAL",
            "lambda_obs": lambda_obs,
            "elapsed_ms": elapsed_ms,
            "discovered_pid": discovered_pid,
            "failure_reason": failure_reason,
            "intent_hash": intent_hash,
            "ncd_real": actual_ncd,
            "expected_delta": expected_ncd,
            "reward": -(expected_ncd - actual_ncd) ** 2,
            "verification_ms": (time.perf_counter() - verification_started) * 1000.0,
        }
        feedback["execution_elapsed_ms"] = (time.perf_counter() - t0) * 1000.0
        await self._persist_semantic_transition(img_pre, pre_context, feedback, metadata)
        visual = _visual_click.get() if click_target is not None else None
        _visual_click.set(None)
        if visual and lambda_obs == 1 and actual_ncd > 0.05:
            await asyncio.to_thread(self._record_visual_success, visual, feedback)
        if contract.get("action") == "PROFESSOR_STEP":
            feedback["observed_hwnd"] = contract.get("target_hwnd", 0)
        if click_target is not None:
            post_context = dict(await loop.run_in_executor(None, self.ctx_engine.capture_foreground_context))
            post_context["ncd_real"] = actual_ncd
            feedback["click_event"] = await loop.run_in_executor(
                None, self._learn_click_feedback, intent_hash, click_target, pre_context, post_context, feedback,
            )
        return feedback

    @authorized_trajectory
    async def executar_trajetoria_completa(
        self,
        objetivo: str,
        mechanism_hint: Optional[Dict[str, Any]] = None,
        is_background: bool = False,
        authorization_token: Optional[Any] = None,
    ) -> Dict[str, Any]:
        require_action_allowed("EXECUTE", is_background)
        _located_element.set(None)
        _visual_click.set(None)
        _last_clicked.set(None)
        
        if mechanism_hint:
            logger.info(f"[TRAJECTORY]: Consumindo mechanism_hint: {mechanism_hint}")

        t0 = time.perf_counter_ns()
        semantic_route_id = str(uuid.uuid4())
        chave_pdag = f"trajectory:{objetivo.lower().strip()[:40]}"

        # 1. Fast-path mielinizado (Sistema 1)
        habito = self.pdag.find_myelinated_path(chave_pdag, vsa_engine=self.vsa)
        if not habito:
            reader = getattr(self.pdag, "find_taught_path", None)
            captured = reader(chave_pdag) if callable(reader) else None
            if isinstance(captured, dict):
                habito = captured
        goals = parse_objectives(objetivo)
        if goals:
            habito = None  # Compose fresh bindings; never replay an old message/query payload.
        if habito and habito.get("meta_primitive") == "OPEN_APP":
            return {"status": "NEED_BINDING", "sucesso_real": False, "rota_mielinizada": False,
                    "passos_concluidos": "0/0", "detalhes": [], "monologo": ["Informe APP_ALVO: abra <nome do aplicativo>."],
                    "tempo_total_ms": 0.0}
        if habito:
            route_key = habito.get("__meta__", {}).get("context_key", chave_pdag)
            passos_mielinizados = []
            if "passos" in habito:
                passos_mielinizados = habito["passos"]
            elif "pipeline_spec" in habito:
                spec = habito["pipeline_spec"]
                try:
                    passos_mielinizados = json.loads(spec).get("passos", []) if isinstance(spec, str) else spec.get("passos", [])
                except Exception:
                    passos_mielinizados = []
            
            if passos_mielinizados:
                literal = system_launch_target(objetivo)
                if literal and not is_web_navigation(objetivo):
                    launches = [p for p in passos_mielinizados if p.get("acao") in ("START_MENU_SEARCH", "ENSURE_APP")]
                    compound_text = re.search(r"\be\s+(?:escreva|digite|redija|componha|crie)\b", objetivo, re.I) and not re.search(r"menu iniciar|start menu", objetivo, re.I)
                    if not launches or (not compound_text and any(p.get("acao") not in ("START_MENU_SEARCH", "ENSURE_APP", "FOCUS_WINDOW") for p in passos_mielinizados)):
                        logger.error("[ROUTING]: Reflexo sem lancamento literal seguro foi descartado")
                        passos_mielinizados = []
                    for cached in passos_mielinizados:
                        app = str(cached.get("app", "")).casefold()
                        if (app and app not in (literal, "notepad" if literal == "bloco de notas" else literal)):
                            logger.error("[ROUTING]: Reflexo descartado: app armazenado difere do alvo literal")
                            passos_mielinizados = []
                            break
            if passos_mielinizados:
                try:
                    for semantic_index, p in enumerate(passos_mielinizados):
                        async def _acao_reflexa(passo=p):
                            return await self._executar_passo_individual(passo)
                        if habito.get("__meta__", {}).get("teacher_verified") is True:
                            resultado = await self.execute_professor_step(p, intent_hash=route_key,
                                semantic_context={"intent": objetivo, "pipeline": passos_mielinizados,
                                    "trajectory_id": semantic_route_id, "step_index": semantic_index, "step_count": len(passos_mielinizados)})
                        else:
                            resultado = await self.execute_subgoal(
                                intent_hash=route_key, action_fn=_acao_reflexa,
                                expected_ncd=p.get("expected_ncd"),
                                contract={**self._contract_for_action(str(p.get("acao", "")), str(p.get("app", ""))),
                                          "expected_app": self._expected_app_for_step(passos_mielinizados, semantic_index)},
                                click_target=self._click_target_for_step(p),
                                intent=objetivo, step=p, pipeline=passos_mielinizados,
                                trajectory_id=semantic_route_id, step_index=semantic_index, step_count=len(passos_mielinizados),
                            )
                        p["feedback"] = {key: resultado[key] for key in ("lambda_obs", "ncd_real", "expected_delta", "reward")}
                        if resultado["lambda_obs"] != 1:
                            raise RuntimeError(resultado["failure_reason"])
                    elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000.0
                    self.pdag.record_execution(
                        route_key, objetivo, {"passos": passos_mielinizados, "tempo_total_ms": elapsed_ms},
                        reinforcement=1.0, vsa_engine=self.vsa,
                    )
                    await asyncio.to_thread(self.pdag.validate_semantic_skill, route_key, passos_mielinizados)
                    return {
                        "status": "CONCLUIDO",
                        "monologo": ["Reflexo neuromotor executado e confirmado pelo verificador factual."],
                        "rota_mielinizada": habito.get("__meta__", {}).get("is_myelinated", True), "sucesso_real": True,
                        "passos_concluidos": f"{len(passos_mielinizados)}/{len(passos_mielinizados)}",
                        "tempo_total_ms": round(elapsed_ms, 2),
                        "detalhes": passos_mielinizados
                    }
                except Exception as ex:
                    self.pdag.record_execution(
                        route_key, objetivo, {"passos": passos_mielinizados, "failure_reason": str(ex)},
                        reinforcement=0.0, vsa_engine=self.vsa,
                    )
                    return {
                        "status": "FALHA_REALIDADE",
                        "monologo": ["Falha no fast-path mielinizado."],
                        "rota_mielinizada": True, "sucesso_real": False,
                        "passos_concluidos": "0/1",
                        "tempo_total_ms": round((time.perf_counter_ns() - t0) / 1_000_000.0, 2),
                        "detalhes": {"failure_reason": f"FAST_PATH_EXCEPTION: {type(ex).__name__}: {ex}"}
                    }

        # 2. Decomposição Probabilística
        from adaptive_resource_controller import current_task_budget
        task_budget = current_task_budget.get()
        decomposicao = await asyncio.get_running_loop().run_in_executor(None, self.decompor_trajetoria_cognitiva, objetivo, task_budget)
        monologo = decomposicao.get("monologo_socratico", [])
        passos = decomposicao.get("pipeline", decomposicao.get("passos", []))

        if not passos:
            elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000.0
            return {"status": "FALHA_REALIDADE", "monologo": monologo, "passos_concluidos": "0/0", "tempo_total_ms": round(elapsed_ms, 2), "detalhes": [], "rota_mielinizada": False, "sucesso_real": False}

        # 3. Execução com Medição (PoST)
        for idx, p in enumerate(passos):
            async def _acao(passo=p):
                return await self._executar_passo_individual(passo)

            resultado = await self.execute_subgoal(
                intent_hash=f"{chave_pdag}::step_{idx}",
                action_fn=_acao,
                timeout_sec=5.0,
                expected_ncd=p.get("expected_ncd"),
                contract={**self._contract_for_action(str(p.get("p", p.get("acao", ""))), str(p.get("app", ""))),
                          "expected_app": self._expected_app_for_step(passos, idx)},
                click_target=self._click_target_for_step(p),
                intent=objetivo, step=p, pipeline=passos,
                trajectory_id=semantic_route_id, step_index=idx, step_count=len(passos),
            )
            p["feedback"] = {
                key: resultado[key] for key in ("lambda_obs", "ncd_real", "expected_delta", "reward")
            }

            if resultado["lambda_obs"] == 0 and p.get("p", p.get("acao")) == "CLICK" and p.get("target"):
                try:
                    await self._executar_primitiva("LOCATE_VISUAL", {"target": p["target"], "force_vlm": True,
                                                                    "exclude_point": _last_clicked.get()})
                    async def visual_action():
                        return await self._executar_primitiva("CLICK", {"target": p["target"]})
                    retry = await self.execute_subgoal(f"{chave_pdag}::visual_retry_{idx}", visual_action,
                        contract=self._contract_for_action("CLICK"), click_target={"element": p["target"]},
                        intent=objetivo, step=p, pipeline=passos, trajectory_id=semantic_route_id,
                        step_index=idx, step_count=len(passos))
                    p["prior_feedback"], p["visual_retry"] = p["feedback"], True
                    p.pop("x", None)
                    p.pop("y", None)
                    resultado = retry
                    p["feedback"] = {key: retry[key] for key in ("lambda_obs", "ncd_real", "expected_delta", "reward")}
                except Exception as ex:
                    logger.warning("[VISUAL]: Recuperacao limitada falhou: %s", ex, exc_info=True)

            if resultado["lambda_obs"] == 0:
                self.pdag.record_execution(
                    context_key=chave_pdag,
                    intent=objetivo,
                    pipeline={"status": "FAILED_FACTUAL", "failure_reason": resultado["failure_reason"], "step": idx, "passos": passos},
                    reinforcement=0.0,
                    vsa_engine=self.vsa,
                )
                return {
                    "status": "FALHA_REALIDADE",
                    "monologo": monologo,
                    "passos_concluidos": f"{idx}/{len(passos)}",
                    "rota_mielinizada": False, "sucesso_real": False,
                    "tempo_total_ms": round((time.perf_counter_ns() - t0) / 1_000_000.0, 2),
                    "detalhes": {
                        "failed_step": p,
                        "failure_reason": resultado["failure_reason"],
                        "lambda_obs": 0,
                        "feedback": p["feedback"],
                    },
                }

            await asyncio.sleep(0.3)

        # 4. Mielinização com Recompensa Afetiva
        self.pdag.record_execution(
            context_key=chave_pdag,
            intent=objetivo,
            pipeline={"passos": passos},
            reinforcement=0.85,
            vsa_engine=self.vsa,
        )
        # Salva a rota no P-DAG Sintático (GHRR)
        if getattr(self, "syntactic_pdag", None) is not None:
            try:
                self.syntactic_pdag.store_route(f"trajectory:ghrr:{objetivo.lower().strip()[:40]}", objetivo, passos)
            except Exception as e:
                logger.warning(f"[GHRR]: Falha ao salvar rota sintática: {e}")
        
        v_sucesso = self.vsa.bind(self.vsa.text_to_hypervector(objetivo), self.vsa.text_to_hypervector("__SOMATIC_RELIEF_REWARD__"))
        await asyncio.to_thread(self.pdag.validate_semantic_skill, chave_pdag, passos)
        if decomposicao.get("source_route_key"):
            await asyncio.to_thread(self.pdag.validate_semantic_skill, decomposicao["source_route_key"], passos)
        self.vsa.register_cleanup(f"TRAJ_{int(time.time())}", v_sucesso)

        return {
            "status": "CONCLUIDO",
            "monologo": monologo,
            "rota_mielinizada": False, "sucesso_real": True,
            "passos_concluidos": f"{len(passos)}/{len(passos)}",
            "tempo_total_ms": round((time.perf_counter_ns() - t0) / 1_000_000.0, 2),
            "detalhes": [],
        }

    @authorized_trajectory
    async def execute_professor_step(self, step: Dict[str, Any], intent_hash: str, expected_hwnd: int = 0,
                                     authorization_token: Optional[Any] = None, teaching: bool = False,
                                     settle_sec: float = 0.15, semantic_context=None) -> Dict[str, Any]:
        require_action_allowed(step.get("acao", "EXECUTE"))
        if step.get("acao") not in ("HOTKEY", "TYPE", "CLICK", "WAIT"):
            raise ValueError("Passo de professor nao suportado")
        if expected_hwnd and step.get("acao") != "CLICK" and step.get("keys") != ["win"]:
            current = await asyncio.to_thread(self.ctx_engine.capture_foreground_context)
            if current.get("hwnd") != expected_hwnd:
                if not await asyncio.to_thread(self.resolver.focus_window_handle, expected_hwnd):
                    raise RuntimeError("Janela da demonstracao nao pode ser restaurada; nenhuma entrada foi enviada")
        async def action():
            result = await self._executar_passo_individual(step)
            if result is not True:
                raise RuntimeError("Atuador nao confirmou o passo")
            await asyncio.sleep(settle_sec)
            observed = await asyncio.to_thread(self.ctx_engine.capture_foreground_context)
            return {"professor_target_hwnd": observed.get("hwnd", 0)}
        return await self.execute_subgoal(intent_hash, action, timeout_sec=0.5 if teaching else 5.0,
            contract={"action": "PROFESSOR_STEP", "expects_new_pid": False, "min_ncd": 0.02},
            step=step, **(semantic_context or {}))

    @authorized_trajectory
    async def execute_professor_batch(self, steps, concept, authorization_token=None, on_step=None):
        if any(re.search(r"\{[A-Z][A-Z0-9_]*\}", str(step.get("text", ""))) for step in steps):
            return [{"lambda_obs": None, "failure_reason": "SYMBOLIC_CAPTURE_ONLY"} for step in steps]
        feedbacks, actuator_failed = [], False
        semantic_route_id = str(uuid.uuid4())
        for step_index, step in enumerate(steps):
            require_action_allowed(step.get("acao", "EXECUTE"))
            if actuator_failed:
                feedbacks.append({"lambda_obs": None, "failure_reason": "NOT_EXECUTED_PRIOR_ACTUATOR_ERROR"})
                continue
            feedback = await self.execute_professor_step(step, f"professor:{concept}:{step['passo']}", teaching=True, settle_sec=0.8,
                semantic_context={"intent": concept, "pipeline": steps, "trajectory_id": semantic_route_id,
                                  "step_index": step_index, "step_count": len(steps)})
            feedbacks.append(feedback)
            actuator_failed = str(feedback.get("failure_reason", "")).startswith("ACTION_EXCEPTION:")
            if on_step is not None and not actuator_failed:
                on_step(step, feedback)
        return feedbacks

    @authorized_trajectory
    async def save_professor_session(self, session: Dict[str, Any], authorization_token: Optional[Any] = None,
                                     capture_only: bool = False) -> bool:
        steps, concept = session.get("passos", []), session["conceito"]
        if capture_only:
            from role_binding import abstract_app_demonstration
            template = {"passos": steps}
            target = session.get("app_alvo", "") or (steps[1].get("text", "") if len(steps) == 3 else "")
            try:
                if session.get("telic") not in (None, "ABRIR_APP"):
                    raise ValueError("Papel telico nao corresponde a abertura de aplicativo")
                template = abstract_app_demonstration(steps, target)
                concept = "abrir_app_generico"
            except ValueError:
                logger.info("[PROFESSOR]: Captura literal; demonstracao nao corresponde a abertura generica")
            if session.get("telic"):
                template["telic"] = session["telic"]
            session["saved_concept"] = concept
            return await asyncio.to_thread(self.pdag.record_human_demonstration, f"trajectory:{concept}", concept, template, self.vsa)
        if not steps or session.get("failed_step"):
            raise ValueError("Demonstracao vazia ou com passo nao confirmado")
        from concept_cortex import ConceptCortex
        target = session.get("app_alvo", "")
        template = ConceptCortex.abstract_application_route(steps, target)
        hwnd = steps[-1]["feedback"].get("observed_hwnd", 0)
        if not await asyncio.to_thread(self.resolver.app_hwnd, target, hwnd):
            raise ValueError("A janela do aplicativo ensinado nao foi confirmada; rota nao foi salva")
        return await asyncio.to_thread(self.pdag.record_demonstration, "trajectory:abrir_app_generico", "abrir_app_generico", template, self.vsa)

    def _generic_opening_available(self):
        pdag = getattr(self, "pdag", None)
        return pdag is not None and pdag.is_verified_demonstration("abrir_app_generico") is True

    async def _execute_generic_opening(self, target):
        from concept_cortex import ConceptCortex
        generic = ConceptCortex.instantiate_generic_opening(self.pdag, target)
        if generic is None:
            return None
        executed_steps = []
        for step in generic["pipeline"]["passos"]:
            feedback = await self.execute_professor_step(step, intent_hash="trajectory:abrir_app_generico")
            executed_steps.append({**step, "feedback": feedback})
            if feedback["lambda_obs"] != 1:
                raise RuntimeError("Meta-primitiva de abertura nao foi confirmada")
        hwnd = await asyncio.to_thread(self.resolver.foreground_app_hwnd, target)
        if not hwnd:
            raise RuntimeError(f"Janela alvo '{target}' nao confirmada apos a instanciacao")
        self.pdag.record_execution("trajectory:abrir_app_generico", "abrir_app_generico", generic["template"],
                                   reinforcement=1.0, vsa_engine=self.vsa)
        await asyncio.to_thread(self.pdag.validate_semantic_skill, "trajectory:abrir_app_generico", executed_steps)
        return {"target_hwnd": hwnd, "app": target}

    async def _start_menu_search(self, target: str) -> Dict[str, Any]:
        require_action_allowed("START_MENU_SEARCH")
        if not target:
            raise ValueError("Busca no Menu Iniciar exige nome literal do app")
        async with self.bridge._input_lock:
            await asyncio.to_thread(self.resolver._open_via_start_menu, target)
        for _ in range(60):
            hwnd = await asyncio.to_thread(self.resolver.foreground_app_hwnd, target)
            if hwnd:
                return {"target_hwnd": hwnd, "app": target}
            process = await asyncio.to_thread(find_app_process, target)
            if process:
                hwnd = await asyncio.to_thread(self.verifier._find_top_level_hwnd, process["pid"])
                if hwnd:
                    await asyncio.to_thread(self.resolver.focus_window_handle, hwnd)
                return {"target_hwnd": hwnd or 0, "app": target, "pid": process["pid"]}
            await asyncio.sleep(0.1)
        raise RuntimeError(f"Janela alvo '{target}' nao confirmada apos a busca nativa")

    async def _deduzir_alvo_visual(self, target, exclude_point=None):
        if self.concept_cortex is None:
            raise RuntimeError("Deducao visual exige ConceptCortex conectado")
        image, rect, ctx = await asyncio.to_thread(self.vision_eye.capture_ui_observation, self.ctx_engine)
        context = f"{ctx.get('process_name', '')}|{ctx.get('title', '')[:50]}"

        # --- FASE 3: Memória Visual FHRR (Cache Hit Espacial) ---
        try:
            regions = await asyncio.to_thread(self.vision_eye.encontrar_regioes_de_interesse, image)
            for region in regions:
                crop = region["crop"]
                v_hash = self.concept_cortex.hash_visual_para_fhrr(crop)
                
                # Tática 2: Combina o Hash Visual com a Posição Fracionária
                x, y, w, h = region["x"], region["y"], region["w"], region["h"]
                cx, cy = x + w // 2, y + h // 2
                width, height = max(1, rect[2] - rect[0]), max(1, rect[3] - rect[1])
                x_norm, y_norm = (cx - rect[0]) / width, (cy - rect[1]) / height
                
                # Gera o vetor espacial dinamicamente para a query
                spatial_query = self.spatial_cortex.bind_element_to_position(v_hash, x_norm, y_norm)
                
                # Busca no cleanup considerando a posição (tolerância a UI-Drift)
                match = self.vsa.cleanup_query(spatial_query, threshold=0.75)
                if match:
                    key, sim = match
                    if target.lower() in key.lower() and sim > 0.5:
                        logger.info(f"[VISAO FHRR]: Cache hit espacial para '{target}' (sim={sim:.2f})")
                        point = self.vision_eye.protocol_point_to_screen((cx, cy), image.size, rect)
                        if exclude_point and abs(point[0]-exclude_point[0]) < 8 and abs(point[1]-exclude_point[1]) < 8:
                            continue
                        digest = hashlib.sha256(crop.convert("RGB").tobytes()).hexdigest()
                        meta = {"target": target, "description": "FHRR_CACHED", "context": context, "rect": rect,
                                "box": (x, y, x+w, y+h), "digest": digest, "hwnd": ctx.get("hwnd"), "similaridade": sim, "roi": crop}
                        return point, meta
        except Exception as ex:
            logger.debug(f"[VISAO FHRR]: Falha no cache visual: {ex}")

        # --- Fallback: VLM (Qwen-VL) ---
        candidates = await asyncio.to_thread(self.vision_eye.propor_candidatos_visuais, image, target, context)
        if not candidates:
            raise RuntimeError("VLM nao encontrou candidato visual")
        candidate = candidates[0]  # Uma tentativa; nunca percorre icones clicando em background.
        x, y = candidate["x"], candidate["y"]
        point = self.vision_eye.protocol_point_to_screen((x, y), image.size, rect)
        if exclude_point and abs(point[0]-exclude_point[0]) < 8 and abs(point[1]-exclude_point[1]) < 8:
            raise RuntimeError("Candidato repete o clique nao confirmado")
        box = candidate.get("box", (max(0, x-48), max(0, y-48), min(image.width, x+48), min(image.height, y+48)))
        roi = image.crop(box)
        description = candidate.get("descricao") or await asyncio.to_thread(self.vision_eye.descrever_elemento_visual, roi)
        deduction = await asyncio.to_thread(self.concept_cortex.deduzir_funcao_visual, description, target, context)
        if deduction.get("encontrado") is not True or deduction.get("similaridade", 0) <= 0.40:
            raise RuntimeError("Hipotese visual abaixo do limiar FHRR")
        digest = hashlib.sha256(roi.convert("RGB").tobytes()).hexdigest()
        meta = {"target": target, "description": description, "context": context, "rect": rect,
                "box": box, "digest": digest, "hwnd": ctx.get("hwnd"), "similaridade": deduction["similaridade"], "roi": roi}
        await self._validar_observacao_visual(meta)
        return point, meta

    async def _validar_observacao_visual(self, meta):
        image, rect, ctx = await asyncio.to_thread(self.vision_eye.capture_ui_observation, self.ctx_engine)
        digest = hashlib.sha256(image.crop(meta["box"]).convert("RGB").tobytes()).hexdigest()
        if not meta["hwnd"] or ctx.get("hwnd") != meta["hwnd"] or rect != meta["rect"] or digest != meta["digest"]:
            raise RuntimeError("Observacao visual expirou: foco, geometria ou icone mudou")

    def _record_visual_success(self, meta, feedback):
        ncd = feedback.get("ncd_real")
        if feedback.get("lambda_obs") != 1 or not isinstance(ncd, (int, float)) or not np.isfinite(ncd) or ncd <= 0.05:
            return False
        slug = re.sub(r"[^\w]+", "_", meta["target"].casefold()).strip("_")[:32]
        app_hash = hashlib.sha256(meta["context"].encode()).hexdigest()[:8]
        if meta.get("roi") is not None:
            vector = self.concept_cortex.hash_visual_para_fhrr(meta["roi"])
            self.vsa.register_cleanup(f"FORMA_{slug}_{app_hash}", vector)
            
            # Tática 2: Fractional Spatial Cortex (UI-Drift tracking)
            if "box" in meta and "rect" in meta and getattr(self, "spatial_cortex", None) is not None:
                box = meta["box"]
                rect = meta["rect"]
                cx = (box[0] + box[2]) // 2
                cy = (box[1] + box[3]) // 2
                width = max(1, rect[2] - rect[0])
                height = max(1, rect[3] - rect[1])
                
                # Normalizar para [0.0, 1.0] conforme exigido pelo FractionalSpatialCortex
                x_norm = (cx - rect[0]) / width
                y_norm = (cy - rect[1]) / height
                
                spatial_vec = self.spatial_cortex.bind_element_to_position(vector, x_norm, y_norm)
                self.vsa.register_cleanup(f"SPATIAL_{slug}_{app_hash}", spatial_vec)
        self.pdag.record_execution(context_key=f"trajectory:{slug}_via_icone:{app_hash}", intent=meta["target"],
            pipeline={"visual_variant": True, "context": meta["context"], "description": meta["description"],
                      "passos": [{"p": "LOCATE_VISUAL", "target": meta["target"]},
                                 {"p": "CLICK", "target": meta["target"], "feedback": {
                                     key: feedback[key] for key in ("lambda_obs", "ncd_real", "expected_delta", "reward")}}]},
            reinforcement=1.0, vsa_engine=self.vsa)
        return True

    async def _executar_primitiva(self, primitiva: str, kwargs: dict):
        """Catalogo factual; escrita segue pelo barramento autorizado existente."""
        primitive = str(primitiva).upper()
        if primitive not in ("OPEN_APP", "LOCATE", "LOCATE_VISUAL", "CLICK", "TYPE", "HOTKEY"):
            raise ValueError(f"Primitiva desconhecida: {primitive}")
        require_action_allowed("INSPECT" if primitive in ("LOCATE", "LOCATE_VISUAL") else primitive)
        if primitive == "OPEN_APP":
            return await self._start_menu_search(str(kwargs.get("app", "")).strip())
        if primitive in ("LOCATE", "LOCATE_VISUAL"):
            _located_element.set(None)
            if self.vision_eye is None:
                from vision_eye import RealVisionEngine
                self.vision_eye = RealVisionEngine()
            before = await asyncio.to_thread(self.ctx_engine.capture_foreground_context)
            target = str(kwargs.get("target", ""))
            point = None if kwargs.get("force_vlm") else await asyncio.to_thread(self.vision_eye.encontrar_elemento_por_texto, target)
            visual = None
            if point is None:
                point, visual = await self._deduzir_alvo_visual(target, kwargs.get("exclude_point"))
            after = await asyncio.to_thread(self.ctx_engine.capture_foreground_context)
            if point is None or not before.get("hwnd") or after.get("hwnd") != before["hwnd"]:
                raise RuntimeError("LOCATE sem alvo inequivoco na janela observada")
            _located_element.set((kwargs.get("target"), point, after["hwnd"], time.monotonic(), visual))
            return point
        payload = dict(kwargs)
        if primitive == "CLICK" and ("x" not in payload or "y" not in payload):
            observed = _located_element.get()
            _located_element.set(None)
            ctx = await asyncio.to_thread(self.ctx_engine.capture_foreground_context)
            if (not observed or observed[0] != payload.get("target") or ctx.get("hwnd") != observed[2]
                    or time.monotonic() - observed[3] > 2.0):
                raise RuntimeError("CLICK bloqueado: execute LOCATE novamente na janela alvo")
            payload.update(x=observed[1][0], y=observed[1][1])
            visual = observed[4] if len(observed) > 4 else None
            if visual:
                await self._validar_observacao_visual(visual)
                _visual_click.set(visual)
        if primitive == "CLICK":
            _last_clicked.set((payload.get("x"), payload.get("y")))
        return await self._executar_passo_individual({**payload, "acao": primitive})

    async def _validate_message_target(self, contact):
        import unicodedata
        def normalized(value):
            return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())
        failure = f"❌ Falha de Segurança: O contato '{contact}' não foi visualizado no cabeçalho da conversa. A mensagem não foi enviada."
        try:
            if not isinstance(contact, str) or not contact.strip() or "{" in contact:
                raise TargetMismatchError(failure)
            if self.vision_eye is None:
                from vision_eye import RealVisionEngine
                self.vision_eye = RealVisionEngine()
            image, _, before = await asyncio.to_thread(self.vision_eye.capture_ui_observation, self.ctx_engine)
            width, height = image.size
            # Exclude search/sidebar results and the message body: only the chat header counts.
            header = image.crop((int(width * .35), 0, width, max(1, int(height * .18))))
            rows = await asyncio.to_thread(self.vision_eye.extrair_texto_e_coordenadas, header)
            after = await asyncio.to_thread(self.ctx_engine.capture_foreground_context)
            matched = any(normalized(row.get("texto", "")) == normalized(contact)
                          and .90 <= float(row.get("confianca", 0)) <= 1.0 for row in rows or [])
            if not matched or not before.get("hwnd") or after.get("hwnd") != before["hwnd"]:
                raise TargetMismatchError(failure)
        except TargetMismatchError:
            logger.error("[TARGET_GATE]: %s", failure)
            raise
        except Exception as ex:
            logger.exception("[TARGET_GATE]: OCR indisponível; envio bloqueado")
            raise TargetMismatchError(failure) from ex

    async def _executar_passo_individual(self, passo: Dict[str, Any], is_background: bool = False) -> Any:
        if "p" in passo:
            primitive = str(passo["p"]).upper()
            require_action_allowed("INSPECT" if primitive in ("LOCATE", "LOCATE_VISUAL") else primitive, is_background)
            if primitive == "DRAG":
                passo = {**{key: value for key, value in passo.items() if key != "p"}, "acao": "DRAG"}
            else:
                return await self._executar_primitiva(primitive, {key: value for key, value in passo.items() if key != "p"})
        acao = str(passo.get("acao", "")).upper()
        require_action_allowed(acao, is_background)
        if "target_contact" in passo and (acao == "TYPE" or (acao == "HOTKEY" and passo.get("keys") == ["enter"])):
            await self._validate_message_target(passo["target_contact"])
            require_action_allowed(acao, is_background)
        if acao in ("READ", "INSPECT"):
            return await asyncio.to_thread(self.ctx_engine.capture_foreground_context)

        if acao == "START_MENU_SEARCH":
            return await self._start_menu_search(str(passo.get("app", "")))

        if acao == "ENSURE_APP":
            target = str(passo.get("app", "")).casefold().strip()
            if self._generic_opening_available():
                generic = await self._execute_generic_opening(target)
                if generic is not None:
                    return generic
            inventory = await asyncio.to_thread(self.resolver._inventory_engine.refresh_inventory, force=False)
            if target not in inventory:
                return await self._start_menu_search(target)
            if not await asyncio.to_thread(self.resolver.launch_app, passo.get("app", ""), self.vsa):
                raise RuntimeError(f"Falha ao iniciar ou focar {passo.get('app')}")
            return True

        elif acao == "FOCUS_WINDOW":
            app = passo.get("app", "")
            for _ in range(10):
                if await asyncio.to_thread(self.resolver.find_and_focus_window, app):
                    return True
                await asyncio.sleep(0.3)
            raise RuntimeError(f"Falha ao focar janela {app}")

        elif acao == "CLICK":
            x, y = passo.get("x"), passo.get("y")
            if any(isinstance(v, bool) or not isinstance(v, int) for v in (x, y)):
                raise ValueError("CLICK exige coordenadas x/y inteiras observadas")
            button, count = passo.get("button", "left"), passo.get("count", 1)
            if button not in ("left", "right", "middle") or count not in (1, 2):
                raise ValueError("Botao ou contagem de CLICK invalidos")
            res = await self.bridge.dispatch("mouse_click_at", {"x": x, "y": y, "button": button, "count": count}, priority=CommandPriority.HIGH)
            if res.status != "completed" or res.result is not True:
                raise RuntimeError(f"Clique falhou: {res.status}")
            return True

        elif acao == "DRAG":
            coords = tuple(passo.get(key) for key in ("x1", "y1", "x2", "y2"))
            if any(isinstance(v, bool) or not isinstance(v, int) for v in coords):
                raise ValueError("DRAG exige coordenadas inteiras observadas")
            if coords[:2] == coords[2:]:
                raise ValueError("DRAG exige pontos distintos")
            ctx = await asyncio.to_thread(self.ctx_engine.capture_foreground_context)
            rect = ctx.get("window_rect")
            if not ctx.get("hwnd") or not isinstance(rect, (tuple, list)) or len(rect) != 4:
                raise ValueError("DRAG exige janela ativa com geometria observada")
            left, top, right, bottom = rect
            if not all(left <= x < right and top <= y < bottom for x, y in (coords[:2], coords[2:])):
                raise ValueError("DRAG fora da janela observada")
            res = await self.bridge.dispatch("mouse_drag", dict(zip(("x1", "y1", "x2", "y2"), coords)), priority=CommandPriority.HIGH)
            if res.status != "completed" or res.result is not True:
                raise RuntimeError(f"Arrasto falhou: {res.status}")
            return True

        elif acao == "RIGHT_CLICK":
            res = await self.bridge.dispatch("right_click", {}, priority=CommandPriority.HIGH)
            if res.status != "completed" or res.result is not True:
                raise RuntimeError(f"Clique direito falhou: {res.status}")
            return True

        elif acao == "SCROLL":
            res = await self.bridge.dispatch("scroll", {"direction": passo.get("direction", "down"), "clicks": passo.get("clicks", 1)}, priority=CommandPriority.HIGH)
            if res.status != "completed" or res.result is not True:
                raise RuntimeError(f"Scroll falhou: {res.status}")
            return True

        elif acao == "HOTKEY":
            res = await self.bridge.dispatch("hotkey", {"keys": passo.get("keys", [])}, priority=CommandPriority.HIGH)
            if res.status != "completed" or res.result is not True:
                raise RuntimeError(f"Hotkey falhou: {res.status}")
            return True

        elif acao == "TYPE":
            if re.search(r"\{[A-Z][A-Z0-9_]*\}", str(passo.get("text", ""))):
                raise ValueError("TYPE bloqueado: preencha os slots abstratos antes de executar")
            res = await self.bridge.dispatch("send_text", {"text": passo.get("text", "")}, priority=CommandPriority.HIGH)
            if res.status != "completed" or res.result is not True:
                raise RuntimeError(f"Digitação falhou: {res.status}")
            return True

        elif acao == "OPEN_NTH_LINK":
            if self.browser_bridge:
                res = self.browser_bridge.open_cached_nth_link(passo.get("index", 1))
                if not res.get("ok", False):
                    raise RuntimeError("Falha ao abrir link ordinal")
                return True
            raise RuntimeError("BrowserBridge não disponível")

        elif acao == "MINIMIZE_WINDOW":
            hwnd = await asyncio.to_thread(self.resolver.foreground_app_hwnd, passo.get("app", ""))
            if not hwnd:
                raise RuntimeError("Janela não encontrada para minimizar")
            if not await asyncio.to_thread(self.effector.minimize_window, hwnd):
                raise RuntimeError("Falha nativa ao minimizar")
            return True

        elif acao == "MAXIMIZE_WINDOW":
            hwnd = await asyncio.to_thread(self.resolver.foreground_app_hwnd, passo.get("app", ""))
            if not hwnd:
                raise RuntimeError("Janela não encontrada para maximizar")
            if not await asyncio.to_thread(self.effector.maximize_window, hwnd):
                raise RuntimeError("Falha nativa ao maximizar")
            return True

        elif acao == "WAIT":
            await asyncio.sleep(float(passo.get("seconds", 0.5)))
            return True

        raise ValueError(f"Ação desconhecida: {acao}")
