"""Read-only explicit-window UIA summary for the Chat bridge.

No focus changes, input, screenshots, model inference, or persistent state.
Windows inspection is lazy so deterministic contract tests run without Win32.
"""
from __future__ import annotations

from collections import Counter
import os
import re
import time


def inspect_window(hwnd: int):
    """Independently validate the native HWND/PID, process lifetime and rectangle."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    import psutil

    class RECT(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                    ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL

    if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
        return None
    native_pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(native_pid))
    if not native_pid.value:
        return None
    proc = psutil.Process(native_pid.value)
    rect = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return {"pid": native_pid.value, "started": proc.create_time(),
            "rect": (rect.left, rect.top, rect.right, rect.bottom)}


def _control_type(row):
    value = row.get("control_type")
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,40}", value) else "Unknown"


def scan_explicit_window(hwnd, pid, *, scanner, provider_available, inspector=None, clock=time.perf_counter):
    """One bounded, explicitly selected read. Never returns UIA names or raw controls.

    Empty lists are ambiguous in the existing PerceptionEye API, so never claim
    OBSERVED on an empty response. The process/window lifetime is checked on both
    sides of the UIA call. This only validates an observation, not an action.
    """
    started_at = clock()
    result = {"status": "TARGET_INVALID", "hwnd": hwnd, "pid": pid,
              "control_count": None, "types": [], "examples": [],
              "execution_authorized": False}

    def done(status, reason=None):
        result["status"] = status
        if reason:
            result["reason"] = reason
        result["elapsed_ms"] = round((clock() - started_at) * 1000, 3)
        return result

    if type(hwnd) is not int or type(pid) is not int or hwnd <= 0 or pid <= 0:
        return done("TARGET_INVALID", "HWND/PID inválidos")
    if pid == os.getpid():
        return done("TARGET_INVALID", "A própria sessão da BRAINNET não é um alvo externo")
    inspect = inspector if inspector is not None else inspect_window
    try:
        before = inspect(hwnd)
    except Exception:
        return done("UNAVAILABLE", "Não foi possível inspecionar a janela")
    if not isinstance(before, dict) or before.get("pid") != pid or not before.get("started") or not before.get("rect"):
        return done("TARGET_INVALID", "Identidade ou geometria da janela não confirmada")
    if not provider_available:
        return done("PROVIDER_UNAVAILABLE", "Biblioteca UIA indisponível")
    try:
        rows = scanner(hwnd, max_controls=100)
        after = inspect(hwnd)
    except Exception as exc:
        return done("UNAVAILABLE", "Leitura UIA indisponível: " + type(exc).__name__)
    if not isinstance(after, dict) or any(after.get(k) != before.get(k) for k in ("pid", "started", "rect")):
        return done("CONTEXT_CHANGED", "Janela, processo ou geometria mudaram durante a leitura")
    if not isinstance(rows, list):
        return done("UNAVAILABLE", "Resposta UIA inválida")
    if not rows:
        result["control_count"] = 0
        return done("EMPTY_OR_PROVIDER_UNAVAILABLE", "Lista vazia não comprova provedor funcional")
    valid = [x for x in rows if isinstance(x, dict) and
             (_control_type(x) != "Unknown" or (
                 isinstance(x.get("rect"), (tuple, list)) and len(x["rect"]) == 4
                 and all(type(v) is int for v in x["rect"])))]
    result["control_count"] = len(rows)
    if not valid:
        return done("INSUFFICIENT_EVIDENCE", "Elementos sem tipo ou geometria utilizável")
    counts = Counter(_control_type(x) for x in valid)
    result["types"] = [{"type": kind, "count": count} for kind, count in counts.most_common(6)]
    for item in valid[:3]:
        rect = item.get("rect")
        safe_rect = list(rect) if isinstance(rect, (tuple, list)) and len(rect) == 4 and all(type(v) is int for v in rect) else None
        result["examples"].append({"control_type": _control_type(item), "rect": safe_rect})
    return done("OBSERVED")


def chat_reply(result):
    status = result["status"]
    if status == "OBSERVED":
        kinds = ", ".join(f"{item['type']} ({item['count']})" for item in result["types"])
        examples = "; ".join(f"{e['control_type']} {e['rect']}" for e in result["examples"])
        return (f"UIA OBSERVED: HWND {result['hwnd']}, PID {result['pid']}; "
                f"{result['control_count']} elementos; tipos: {kinds}; "
                f"exemplos: {examples}; latência {result['elapsed_ms']} ms. "
                "Somente leitura; nenhuma ação autorizada.")
    return (f"UIA {status}: HWND {result.get('hwnd')}, PID {result.get('pid')}; "
            f"{result.get('reason', 'sem evidência válida')}. "
            f"Latência {result['elapsed_ms']} ms. Nenhuma observação confirmada.")
