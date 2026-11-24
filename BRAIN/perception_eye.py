# ==============================================================================
# BRAINNET - SISTEMA OPERACIONAL COGNITIVO
# MODULO: perception_eye.py
# FUNCAO: Visão Semântica Estrutural via Windows UIA.
#         Extrai Affordances Físicas (ValuePattern, InvokePattern) sem regras.
# ==============================================================================

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import os
from pathlib import Path
import sys
import time
import psutil
from typing import Any, Dict, List, Optional, Tuple

BRAIN_DIR = Path(__file__).resolve().parent
if str(BRAIN_DIR) not in sys.path:
    sys.path.insert(0, str(BRAIN_DIR))

from hyperdimensional import FHRRHyperdimensionalEngine

try:
    import uiautomation as auto
    HAS_UIA_NATIVE = True
except ImportError:
    HAS_UIA_NATIVE = False

user32 = ctypes.WinDLL("user32", use_last_error=True)

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]

user32.GetWindowRect.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]

@dataclass(slots=True)
class UIControlElement:
    """Elemento nativo identificado na interface do Windows."""
    hwnd: int
    name: str
    class_name: str
    affordance: str # 'VALUE' (texto), 'INVOKE' (clique), 'SELECT' (menu), 'READ' (leitura)
    rect: Tuple[int, int, int, int]
    rel_center_pct: Tuple[float, float]

class PerceptionEye:
    __slots__ = ("vsa", "_shadow_dom")

    def __init__(self, vsa_engine: Optional[FHRRHyperdimensionalEngine] = None) -> None:
        self.vsa = vsa_engine or FHRRHyperdimensionalEngine(dimension=10_000, seed=42)
        self._shadow_dom: Dict[int, Dict[str, Any]] = {}

    def get_window_bounds(self, hwnd: int) -> Tuple[int, int, int, int]:
        rect = RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            w = max(1, rect.right - rect.left)
            h = max(1, rect.bottom - rect.top)
            return (rect.left, rect.top, w, h)
        return (0, 0, 1920, 1080)

    def scan_uia_properties(self, hwnd: int, *, max_controls: int = 1000,
                            include_sensitive: bool = True, max_depth: int = 6) -> List[Dict[str, Any]]:
        """Read current UIA properties in this thread; never return COM objects.

        Unknown/unavailable properties remain None. When include_sensitive is
        false, Name and AutomationId are not requested from the UIA provider.
        No cached element, screen
        coordinate, or positive result from this read authorizes a later action.
        """
        if not hwnd or not HAS_UIA_NATIVE:
            return []
        if isinstance(max_controls, bool) or not isinstance(max_controls, int) or not 1 <= max_controls <= 5000:
            raise ValueError('invalid max_controls')
        if type(max_depth) is not int or not 1 <= max_depth <= 32:
            raise ValueError('invalid max_depth')
        if type(include_sensitive) is not bool:
            raise ValueError('invalid include_sensitive')

        def read(fn):
            try: return fn()
            except Exception: return None

        out = []
        with auto.UIAutomationInitializerInThread():
            root = auto.ControlFromHandle(hwnd)
            if not root.Exists(0, 0):
                return []
            for entry in auto.WalkTree(root, getChildren=lambda c: c.GetChildren()):
                control, depth = entry[:2]
                if depth > max_depth:
                    continue
                if len(out) >= max_controls:
                    break
                rect = read(lambda: control.BoundingRectangle)
                rect = read(lambda: (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))) if rect is not None else None
                runtime = read(lambda: tuple(int(x) for x in control.GetRuntimeId()))
                def pattern_supported(getter):
                    pattern = read(getter)
                    # A failed query is unknown, not evidence of unsupported behavior.
                    return True if pattern is not None and getattr(pattern, 'pattern', None) is not None else None
                out.append({'name': read(lambda: control.Name) if include_sensitive else None,
                    'automation_id': read(lambda: control.AutomationId) if include_sensitive else None,
                    'control_type': read(lambda: control.ControlTypeName),
                    'process_id': read(lambda: control.ProcessId), 'runtime_id': runtime,
                    'is_enabled': read(lambda: control.IsEnabled),
                    'is_offscreen': read(lambda: control.IsOffscreen), 'rect': rect,
                    'invoke_supported': pattern_supported(lambda: control.GetInvokePattern()),
                    'expand_collapse_supported': pattern_supported(lambda: control.GetExpandCollapsePattern())})
        return out

    def scan_window_controls(self, hwnd: int) -> List[UIControlElement]:
        if not hwnd: return []

        now = time.time()
        context = self._window_context(hwnd)
        if hwnd in self._shadow_dom and self._shadow_dom[hwnd].get("context") == context and (now - self._shadow_dom[hwnd]["timestamp"]) < 1.5:
            return self._shadow_dom[hwnd]["elements"]

        win_x, win_y, win_w, win_h = self.get_window_bounds(hwnd)
        elements: List[UIControlElement] = []

        if HAS_UIA_NATIVE and hwnd:
            try:
                ctrl = auto.ControlFromHandle(hwnd)
                if ctrl.Exists(0, 0):
                    for child, depth in auto.WalkTree(ctrl, getChildren=lambda c: c.GetChildren()):
                        if depth > 6: 
                            continue
                            
                        name = (child.Name or "").strip()
                        c_type = child.ControlTypeName
                        
                        # Extração de Affordance (Padrões de Automação)
                        affordance = "NONE"
                        try:
                            if child.GetValuePattern():
                                affordance = "VALUE"
                            elif child.GetInvokePattern() or c_type in ("ButtonControl", "HyperlinkControl"):
                                affordance = "INVOKE"
                            elif child.GetTextPattern() or c_type in ("TextControl", "ListItemControl"):
                                affordance = "READ"
                            elif child.GetSelectionItemPattern():
                                affordance = "SELECT"
                        except Exception:
                            if c_type == "EditControl": affordance = "VALUE"
                            elif c_type in ("ButtonControl", "MenuItemControl"): affordance = "INVOKE"
                            elif c_type == "TextControl": affordance = "READ"

                        if affordance != "NONE" or name or c_type in ("DocumentControl", "PaneControl", "CustomControl"):
                            r = child.BoundingRectangle
                            if r and (r.right > r.left) and (r.bottom > r.top):
                                cx = (r.left + r.right) // 2
                                cy = (r.top + r.bottom) // 2
                                if c_type in ("DocumentControl", "PaneControl", "CustomControl") and affordance in ("NONE", "READ"):
                                    affordance = self._observed_affordance(name or f"xy({cx},{cy})", context)
                                rx = round(((cx - win_x) / win_w) * 100.0, 2)
                                ry = round(((cy - win_y) / win_h) * 100.0, 2)
                                
                                elements.append(UIControlElement(
                                    hwnd=hwnd, name=name, class_name=c_type,
                                    affordance=affordance,
                                    rect=(r.left, r.top, r.right, r.bottom),
                                    rel_center_pct=(rx, ry)
                                ))
                    
                    if elements:
                        self._shadow_dom[hwnd] = {"elements": elements, "timestamp": now, "context": context}
                        return elements
            except Exception:
                pass

        # Fallback Win32 Clássico
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def enum_child_proc(child_hwnd: int, _: int) -> bool:
            if not user32.IsWindowVisible(child_hwnd): return True
            rect = RECT()
            if user32.GetWindowRect(child_hwnd, ctypes.byref(rect)):
                if rect.right <= rect.left or rect.bottom <= rect.top: return True

                length = user32.GetWindowTextLengthW(child_hwnd)
                name_buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(child_hwnd, name_buf, length + 1)
                text = name_buf.value.strip()

                cls_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(child_hwnd, cls_buf, 256)
                cls_name = cls_buf.value.strip()

                affordance = "VALUE" if "edit" in cls_name.lower() else ("INVOKE" if "button" in cls_name.lower() else "NONE")

                if text or affordance != "NONE":
                    c_x = (rect.left + rect.right) // 2
                    c_y = (rect.top + rect.bottom) // 2
                    rel_x = round(((c_x - win_x) / win_w) * 100.0, 2)
                    rel_y = round(((c_y - win_y) / win_h) * 100.0, 2)
                    elements.append(UIControlElement(child_hwnd, text, cls_name, affordance, (rect.left, rect.top, rect.right, rect.bottom), (rel_x, rel_y)))
            return True

        user32.EnumChildWindows(hwnd, WNDENUMPROC(enum_child_proc), 0)
        self._shadow_dom[hwnd] = {"elements": elements, "timestamp": now, "context": context}
        return elements

    def _window_context(self, hwnd: int) -> str:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        title = ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(hwnd) + 1)
        user32.GetWindowTextW(hwnd, title, len(title))
        try:
            process_name = psutil.Process(pid.value).name() if pid.value else ""
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            process_name = ""
        return f"{process_name}|{title.value[:30]}"

    def _observed_affordance(self, element: str, context: str) -> str:
        suffix = f"|{context}|{element}"
        latest = next((key for key in reversed(self.vsa.cleanup_keys) if key.endswith(suffix)), None)
        if latest is None:
            return "UNKNOWN"
        label = latest.split("|", 1)[0]
        change = label.removeprefix("ELEMENTO_")
        vector = self.vsa.encode_compositional(action="CLICK", target=element, param=change, context=context)
        match = self.vsa.cleanup_query(vector, threshold=0.30)
        if not match or match[1] <= 0.30 or match[0] != latest:
            return "UNKNOWN"
        return {"ELEMENTO_ABRIU_JANELA_NOVA": "INVOKE", "ELEMENTO_MUDOU_ESTADO_INTERNO": "INVOKE"}.get(label, "UNKNOWN")
