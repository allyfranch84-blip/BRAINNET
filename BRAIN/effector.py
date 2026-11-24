# Teste de Integridade v1
# ==============================================================================
# BRAINNET v7 - SISTEMA OPERACIONAL COGNITIVO
# MODULO: effector.py
# FUNCAO: Atuador Biomecanico (Bezier Cubico, Jitter Gaussiano e Injecao Win32).
# ==============================================================================

from __future__ import annotations

import ctypes
from ctypes import wintypes
import math
import random
import time
from typing import Sequence
from execution_authority import require_action_allowed

user32 = ctypes.windll.user32

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class INPUT(ctypes.Structure):
    class _INPUT_UNION(ctypes.Union):
        class _MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
            ]
        class _KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
            ]
        _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]
    _fields_ = [("type", ctypes.c_ulong), ("u", _INPUT_UNION)]

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK_MAP = {
    "ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B,
    "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "backspace": 0x08,
    "space": 0x20, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "f4": 0x73,
    "c": 0x43, "v": 0x56, "x": 0x58, "a": 0x41, "s": 0x53, "z": 0x5A,
}


class Effector:
    """Os Musculos Biomecanicos do BRAINNET."""

    def mouse_move(self, x: int, y: int, *, profile: str = "bezier", tolerance: int = 0) -> bool:
        """Movimento autorizado; sucesso exige leitura independente da posição final."""
        require_action_allowed("MOVE_CURSOR")
        if type(x) is not int or type(y) is not int or profile not in ("bezier", "deterministic", "physical_diagnostic") or type(tolerance) is not int or not 0 <= tolerance <= 3:
            raise ValueError("Parâmetros inválidos de movimento")
        if profile == "physical_diagnostic":
            from execution_authority import require_specific_physical_move
            require_specific_physical_move(x, y)
            before = POINT()
            if not user32.GetPhysicalCursorPos(ctypes.byref(before)):
                return False
            from execution_authority import _physical_move_scope
            if (before.x, before.y) != _physical_move_scope.get().start:
                return False
            # Do not turn an intentional move into an accidental drag.
            if any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (1, 2, 4, 5, 6)):
                raise PermissionError('MOUSE_BUTTON_HELD')
            proposal = _physical_move_scope.get()
            if proposal.duration_ms:
                # A straight physical trajectory; every sample remains within the
                # approved segment and stops if the operator takes over.
                frames = max(1, proposal.duration_ms // 20)
                start = (before.x, before.y)
                last = start
                started = time.monotonic()
                for index in range(1, frames + 1):
                    remaining = started + index * proposal.duration_ms / (1000 * frames) - time.monotonic()
                    if remaining > 0:
                        time.sleep(remaining)
                    require_specific_physical_move(x, y)
                    current = POINT()
                    if not user32.GetPhysicalCursorPos(ctypes.byref(current)) or (current.x, current.y) != last:
                        return False
                    if any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (1, 2, 4, 5, 6)):
                        raise PermissionError('MOUSE_BUTTON_HELD')
                    point = (round(start[0] + (x - start[0]) * index / frames),
                             round(start[1] + (y - start[1]) * index / frames))
                    if not user32.SetPhysicalCursorPos(*point):
                        return False
                    last = point
            else:
                require_specific_physical_move(x, y)
                if not user32.SetPhysicalCursorPos(x, y):
                    return False
            require_specific_physical_move(x, y)
            after = POINT()
            if not user32.GetPhysicalCursorPos(ctypes.byref(after)):
                return False
            return abs(after.x - x) <= tolerance and abs(after.y - y) <= tolerance
        def verified():
            require_action_allowed("MOVE_CURSOR")
            position = POINT()
            if not user32.GetCursorPos(ctypes.byref(position)):
                return False
            return abs(position.x - x) <= tolerance and abs(position.y - y) <= tolerance
        pt_atual = POINT()
        if not user32.GetCursorPos(ctypes.byref(pt_atual)):
            return False
        x0, y0 = pt_atual.x, pt_atual.y
        x3, y3 = int(x), int(y)

        dist = math.hypot(x3 - x0, y3 - y0)
        if profile == "deterministic" or dist < 4:
            require_action_allowed("MOVE_CURSOR")
            if not user32.SetCursorPos(x3, y3):
                return False
            return verified()

        # Pontos de controle intermediários
        desvio = dist * random.uniform(0.12, 0.25)
        angulo = math.atan2(y3 - y0, x3 - x0) + random.choice([-1, 1]) * math.pi / random.uniform(4.0, 6.0)

        x1 = x0 + math.cos(angulo) * desvio
        y1 = y0 + math.sin(angulo) * desvio
        x2 = x3 - math.cos(angulo) * (desvio * 0.7)
        y2 = y3 - math.sin(angulo) * (desvio * 0.7)

        passos = int(max(15, min(50, dist / 20.0)))
        for i in range(passos + 1):
            t = i / float(passos)
            u = 1.0 - t
            bx = (u**3 * x0) + (3 * u**2 * t * x1) + (3 * u * t**2 * x2) + (t**3 * x3)
            by = (u**3 * y0) + (3 * u**2 * t * y1) + (3 * u * t**2 * y2) + (t**3 * y3)

            # Micro-jitter gaussiano (sigma <= 0.65px)
            if i < passos:
                bx += random.gauss(0, 0.65)
                by += random.gauss(0, 0.65)

            require_action_allowed("MOVE_CURSOR")
            if not user32.SetCursorPos(int(bx), int(by)):
                return False
            time.sleep(random.uniform(0.003, 0.006))

        return verified()

    def mouse_click(self, button: str = "left", count: int = 1) -> bool:
        """Diferenciacao real entre clique esquerdo, direito e central."""
        require_action_allowed("CLICK")
        b = button.lower().strip()
        if b in ("right", "direito"):
            flag_down, flag_up = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
        elif b in ("middle", "meio", "scroll"):
            flag_down, flag_up = MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP
        else:
            flag_down, flag_up = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP

        for _ in range(count):
            require_action_allowed("CLICK")
            inp_down = INPUT(type=INPUT_MOUSE)
            inp_down.u.mi.dwFlags = flag_down
            if user32.SendInput(1, ctypes.byref(inp_down), ctypes.sizeof(INPUT)) != 1:
                return False

            tempo_contato = max(0.035, min(0.080, random.gammavariate(9, 5) / 1000.0))
            time.sleep(tempo_contato)

            inp_up = INPUT(type=INPUT_MOUSE)
            inp_up.u.mi.dwFlags = flag_up
            if user32.SendInput(1, ctypes.byref(inp_up), ctypes.sizeof(INPUT)) != 1:
                return False

            if count > 1:
                time.sleep(0.08)
        return True

    def mouse_scroll(self, direction: str, clicks: int = 1) -> bool:
        require_action_allowed("SCROLL")
        if direction not in ("up", "down"):
            raise ValueError("direction deve ser up ou down")
        if isinstance(clicks, bool) or not isinstance(clicks, int) or not 1 <= clicks <= (2**31 - 1) // 120:
            raise ValueError("clicks deve ser inteiro positivo dentro do limite Win32")
        delta = 120 * clicks if direction == "up" else -120 * clicks
        event = INPUT(type=INPUT_MOUSE)
        event.u.mi.dwFlags = MOUSEEVENTF_WHEEL
        event.u.mi.mouseData = ctypes.c_ulong(delta).value
        return user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)) == 1

    def mouse_drag(self, x1: int, y1: int, x2: int, y2: int) -> bool:
        """Move ate o inicio, arrasta com o botao esquerdo e sempre o libera."""
        require_action_allowed("DRAG")
        if self.mouse_move(x1, y1) is not True:
            return False
        down = INPUT(type=INPUT_MOUSE)
        down.u.mi.dwFlags = MOUSEEVENTF_LEFTDOWN
        if user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT)) != 1:
            return False
        try:
            require_action_allowed("DRAG")
            return self.mouse_move(x2, y2) is True
        finally:
            up = INPUT(type=INPUT_MOUSE)
            up.u.mi.dwFlags = MOUSEEVENTF_LEFTUP
            if user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT)) != 1:
                raise RuntimeError("Falha ao liberar o botão esquerdo após arrastar")

    def send_text(self, text: str) -> bool:
        for char in text:
            code = ord(char)
            inp_d = INPUT(type=INPUT_KEYBOARD)
            inp_d.u.ki.wScan = code
            inp_d.u.ki.dwFlags = KEYEVENTF_UNICODE
            user32.SendInput(1, ctypes.byref(inp_d), ctypes.sizeof(INPUT))
            time.sleep(0.004)

            inp_u = INPUT(type=INPUT_KEYBOARD)
            inp_u.u.ki.wScan = code
            inp_u.u.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
            user32.SendInput(1, ctypes.byref(inp_u), ctypes.sizeof(INPUT))
            time.sleep(0.004)
        return True

    def send_hotkey(self, keys: Sequence[str]) -> bool:
        """Executa combinacoes de teclas reais (ex: ['ctrl', 'c']) via SendInput."""
        vk_codes = [VK_MAP.get(k.lower(), ord(k.upper()) if len(k) == 1 else 0) for k in keys]
        vk_codes = [vk for vk in vk_codes if vk != 0]
        if not vk_codes:
            return False

        # Pressiona em ordem
        for vk in vk_codes:
            inp = INPUT(type=INPUT_KEYBOARD)
            inp.u.ki.wVk = vk
            user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            time.sleep(0.005)

        time.sleep(0.02)

        # Solta em ordem inversa
        for vk in reversed(vk_codes):
            inp = INPUT(type=INPUT_KEYBOARD)
            inp.u.ki.wVk = vk
            inp.u.ki.dwFlags = KEYEVENTF_KEYUP
            user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
            time.sleep(0.005)

        return True

    def minimize_window(self, hwnd: int) -> bool:
        return bool(user32.ShowWindow(hwnd, 6))  # SW_MINIMIZE

    def maximize_window(self, hwnd: int) -> bool:
        return bool(user32.ShowWindow(hwnd, 3))  # SW_MAXIMIZE
