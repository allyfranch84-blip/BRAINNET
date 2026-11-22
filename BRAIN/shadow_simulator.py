# ==============================================================================
# BRAINNET v7 - SISTEMA OPERACIONAL COGNITIVO
# MODULO: shadow_simulator.py
# FUNCAO: Simulador Mental "As-If Loop", Inspecao Profunda de Chromium/Electron (UIA),
#         Verificador de Realidade do SO e Colapso de Multiverso em 10.000D.
# ==============================================================================

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import logging
import math
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

BRAIN_DIR = Path(__file__).resolve().parent
if str(BRAIN_DIR) not in sys.path:
    sys.path.insert(0, str(BRAIN_DIR))

from context_capture import ContextCapture
from perception_eye import PerceptionEye, UIControlElement
from hyperdimensional import FHRRHyperdimensionalEngine
from pdag_engine import MyelinatedPDAGEngine

logger = logging.getLogger("BRAINNET_ShadowCore")

user32 = ctypes.WinDLL("user32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102
MK_LBUTTON = 0x0001
DWMWA_CLOAKED = 14

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL

user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(POINT)]
user32.ScreenToClient.restype = wintypes.BOOL


def makelparam(x: int, y: int) -> int:
    return (int(y) << 16) | (int(x) & 0xFFFF)


class RealityVerifier:
    """[VERIFICADOR DE REALIDADE TOTAL]: Confirma se o SO realmente mudou de estado."""

    @staticmethod
    def is_window_real_and_active(hwnd: int) -> Dict[str, Any]:
        if not hwnd or not user32.IsWindow(hwnd):
            return {"ativa": False, "motivo": "HWND_INVALIDO"}

        if not user32.IsWindowVisible(hwnd):
            return {"ativa": False, "motivo": "JANELA_INVISIVEL"}

        cloaked = ctypes.c_int(0)
        dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        if cloaked.value != 0:
            return {"ativa": False, "motivo": "JANELA_CLOAKED_UWP"}

        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top

        return {
            "ativa": True,
            "largura": w,
            "altura": h,
            "is_foreground": (user32.GetForegroundWindow() == hwnd)
        }


class ShadowSimulator:
    """
    [O ESPELHO COGNITIVO UNIVERSAL]:
    Conecta Percepção UIA Profunda, Ações Fantasmas em Background e Colapso Fasorial FHRR.
    """

    __slots__ = ("ctx_engine", "eye", "vsa", "pdag", "reality")

    def __init__(
        self,
        ctx_engine: ContextCapture,
        eye: PerceptionEye,
        vsa: FHRRHyperdimensionalEngine,
        pdag: MyelinatedPDAGEngine
    ) -> None:
        self.ctx_engine = ctx_engine
        self.eye = eye
        self.vsa = vsa
        self.pdag = pdag
        self.reality = RealityVerifier()

    def ghost_click(self, hwnd: int, client_x: int, client_y: int) -> bool:
        """Dispara clique em background sem mover o mouse físico."""
        lparam = makelparam(client_x, client_y)
        user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lparam)
        time.sleep(0.015)
        user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
        time.sleep(0.035)
        user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam)
        return True

    def ghost_type(self, hwnd: int, text: str) -> bool:
        """Injeta texto em segundo plano caractere a caractere."""
        for ch in text:
            user32.PostMessageW(hwnd, WM_CHAR, ord(ch), 0)
            time.sleep(0.003)
        return True

    def ghost_hotkey(self, hwnd: int, vk_code: int) -> bool:
        user32.PostMessageW(hwnd, WM_KEYDOWN, vk_code, 0)
        time.sleep(0.02)
        user32.PostMessageW(hwnd, WM_KEYUP, vk_code, 0)
        return True

    def dissecar_affordances_profundas(self, hwnd: int) -> List[Dict[str, Any]]:
        """
        [DISSECTOR CHROMIUM/ELECTRON/WIN32]:
        Extrai controles nativos e perfura o canvas com coordenadas percentuais invariantes.
        """
        controles = self.eye.scan_window_controls(hwnd)
        bounds = self.eye.get_window_bounds(hwnd)
        win_w, win_h = max(1, bounds[2]), max(1, bounds[3])

        affordances = []
        for c in controles:
            pt = POINT(x=(c.rect[0] + c.rect[2]) // 2, y=(c.rect[1] + c.rect[3]) // 2)
            user32.ScreenToClient(hwnd, ctypes.byref(pt))
            affordances.append({
                "nome": c.name or "[Controle Sem Nome]",
                "classe": c.class_name,
                "affordance": c.affordance,
                "client_x": pt.x,
                "client_y": pt.y,
                "pct_x": c.rel_center_pct[0],
                "pct_y": c.rel_center_pct[1],
                "rect_cliente": (c.rect[0] - bounds[0], c.rect[1] - bounds[1], c.rect[2] - bounds[0], c.rect[3] - bounds[1])
            })

        # Se o aplicativo for um canvas monolítico (ex: VS Code / WhatsApp),
        # sintetiza âncoras funcionais baseadas em padrões semióticos de navegação
        if len(affordances) <= 3:
            affordances.extend([
                {"nome": "Barra Lateral de Navegação", "classe": "Synthetic_Affordance", "client_x": int(win_w * 0.03), "client_y": int(win_h * 0.5), "pct_x": 3.0, "pct_y": 50.0},
                {"nome": "Área Central de Trabalho", "classe": "Synthetic_Affordance", "client_x": int(win_w * 0.5), "client_y": int(win_h * 0.5), "pct_x": 50.0, "pct_y": 50.0},
                {"nome": "Caixa de Entrada / Rodapé", "classe": "Synthetic_Affordance", "client_x": int(win_w * 0.5), "client_y": int(win_h * 0.92), "pct_x": 50.0, "pct_y": 92.0},
            ])

        return affordances

    def simular_multiverso_de_possibilidades(
        self,
        hwnd: int,
        objetivo_geral: str,
        limite_hipoteses: int = 6
    ) -> Dict[str, Any]:
        """
        [AS-IF LOOP CONTRAFACTUAL NÃO-INTRUSIVO]:
        Simula a transição de estado internamente em C^10.000 através da álgebra
        de affordances sem disparar cliques físicos invasivos na tela do usuário.
        """
        t0 = time.perf_counter_ns()
        verif_inicial = self.reality.is_window_real_and_active(hwnd)
        if not verif_inicial["ativa"]:
            return {"status": "FALHA_REALIDADE", "motivo": verif_inicial["motivo"]}

        affordances = self.dissecar_affordances_profundas(hwnd)
        v_meta = self.vsa.generate_vector(objetivo_geral)
        v_estado_atual = self.vsa.generate_vector(f"ESTADO_HWND_{hwnd}")

        ramificacoes_simuladas = []
        melhor_rota = None
        menor_energia_livre = 1e9

        for aff in affordances[:limite_hipoteses]:
            rotulo = aff["nome"]
            classe = aff["classe"]
            pct_x, pct_y = aff["pct_x"], aff["pct_y"]

            # Modelagem da Affordance como Operador de Fase (Binding)
            v_affordance = self.vsa.encode_compositional(
                action="INVOCAR_AFFORDANCE",
                target=rotulo,
                param=classe,
                context=f"{pct_x:.1f}_{pct_y:.1f}"
            )

            # Projeção mental do futuro: s_projetado = s_atual ⊙ v_affordance
            s_futuro_projetado = self.vsa.bind(v_estado_atual, v_affordance)
            
            # Cálculo de Divergência Variacional (Karl Friston)
            sim_meta = max(0.0, self.vsa.similarity(s_futuro_projetado, v_meta))
            divergencia = 1.0 - sim_meta
            
            # Custo de dissipação termodinâmica proporcional à distância do centro
            custo_dissipacao = 0.02 + (abs(pct_x - 50.0) + abs(pct_y - 50.0)) / 4000.0
            energia_livre = divergencia + custo_dissipacao

            ramificacoes_simuladas.append({
                "alvo": aff,
                "energia_livre": round(energia_livre, 4),
                "ressonancia_meta": round(sim_meta, 4)
            })

            if energia_livre < menor_energia_livre:
                menor_energia_livre = energia_livre
                melhor_rota = aff

        elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000.0

        return {
            "status": "MULTIVERSO_MENTAL_COLAPSADO",
            "tempo_ms": round(elapsed_ms, 2),
            "melhor_caminho": melhor_rota,
            "menor_energia_livre": round(menor_energia_livre, 4),
            "possibilidades_avaliadas": len(ramificacoes_simuladas),
            "detalhes": ramificacoes_simuladas
        }
