# ==============================================================================
# BRAINNET v7 - SISTEMA OPERACIONAL COGNITIVO
# MODULO: context_capture.py
# FUNCAO: Extracao ultrarrapida de contexto da janela ativa e sensor DWM de Menu Iniciar.
# ==============================================================================

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import time
from typing import Any, Dict, List, Tuple

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
DWMWA_CLOAKED = 14

user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetForegroundWindow.argtypes = []

user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]

user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]

kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]

kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]

kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


user32.GetWindowRect.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]

user32.IsIconic.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]

user32.IsZoomed.restype = wintypes.BOOL
user32.IsZoomed.argtypes = [wintypes.HWND]


class ContextCapture:
    """Extrator de contexto com sensor nativo DWM do Menu Iniciar."""

    __slots__ = ("_path_buf", "_path_size")

    def __init__(self) -> None:
        self._path_buf = ctypes.create_unicode_buffer(1024)
        self._path_size = wintypes.DWORD(1024)

    def is_start_menu_open(self) -> bool:
        menu_aberto = False

        def enum_janelas(hwnd: int, _: int) -> bool:
            nonlocal menu_aberto
            if not user32.IsWindowVisible(hwnd):
                return True

            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == 0:
                return True

            h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
            if not h_proc:
                return True

            try:
                buf = ctypes.create_unicode_buffer(512)
                size = wintypes.DWORD(512)
                if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
                    nome = os.path.basename(buf.value).lower()
                    if nome == "startmenuexperiencehost.exe":
                        cls_buf = ctypes.create_unicode_buffer(256)
                        user32.GetClassNameW(hwnd, cls_buf, 256)
                        if cls_buf.value in ("Windows.UI.Core.CoreWindow", "TopLevelWindowForOverflow"):
                            rect = RECT()
                            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                                largura = rect.right - rect.left
                                altura = rect.bottom - rect.top
                                if largura > 150 and altura > 200:
                                    cloaked = ctypes.c_int(0)
                                    dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
                                    if cloaked.value == 0:
                                        menu_aberto = True
                                        return False
            finally:
                kernel32.CloseHandle(h_proc)
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_janelas), 0)
        return menu_aberto

    def capture_foreground_context(self) -> Dict[str, Any]:
        t0 = time.perf_counter_ns()
        hwnd = user32.GetForegroundWindow()
        menu_aberto = self.is_start_menu_open()

        if not hwnd:
            return {
                "hwnd": 0,
                "title": "Menu Iniciar" if menu_aberto else "",
                "pid": 0,
                "process_name": "startmenuexperiencehost.exe" if menu_aberto else "desktop.exe",
                "executable_path": "",
                "window_rect": (0, 0, 0, 0),
                "start_menu_open": menu_aberto,
                "latency_ms": (time.perf_counter_ns() - t0) / 1_000_000,
            }

        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            title_buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title_buf, length + 1)
            window_title = title_buf.value
        else:
            window_title = "Sem Titulo"

        pid_val = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_val))
        pid = pid_val.value

        proc_path = ""
        proc_name = "desconhecido.exe"
        if pid != 0:
            h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if h_proc:
                try:
                    self._path_size.value = 1024
                    if kernel32.QueryFullProcessImageNameW(
                        h_proc, 0, self._path_buf, ctypes.byref(self._path_size)
                    ):
                        proc_path = self._path_buf.value
                        proc_name = os.path.basename(proc_path).lower()
                finally:
                    kernel32.CloseHandle(h_proc)

        rect = RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            win_rect = (rect.left, rect.top, rect.right, rect.bottom)
        else:
            win_rect = (0, 0, 0, 0)

        if menu_aberto:
            window_title = "Menu Iniciar"
            proc_name = "startmenuexperiencehost.exe"

        elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000
        return {
            "hwnd": hwnd,
            "title": window_title,
            "pid": pid,
            "process_name": proc_name,
            "executable_path": proc_path,
            "window_rect": win_rect,
            "start_menu_open": menu_aberto,
            "latency_ms": elapsed_ms,
        }

    def escanear_estado_janelas(self) -> List[Dict[str, Any]]:
        """
        [PROPRIOCEPÇÃO ESPACIAL WIN32 (<0.1ms)]:
        Mapeia todas as janelas do SO, identificando quem está em foco,
        quem está minimizado na barra de tarefas e quem está maximizado.
        """
        janelas: List[Dict[str, Any]] = []
        hwnd_foco_atual = user32.GetForegroundWindow()

        def enum_cb(hwnd: int, _: int) -> bool:
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    titulo = buf.value.strip()

                    # Ignora janelas utilitárias sem nome
                    if titulo and len(titulo) > 1:
                        pid = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                        
                        is_min = bool(user32.IsIconic(hwnd))
                        is_max = bool(user32.IsZoomed(hwnd))
                        is_foco = (hwnd == hwnd_foco_atual)

                        janelas.append({
                            "hwnd": hwnd,
                            "pid": pid.value,
                            "titulo": titulo,
                            "em_foco": is_foco,
                            "minimizada": is_min,
                            "maximizada": is_max
                        })
            return True

        WNDENUM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUM(enum_cb), 0)
        return janelas