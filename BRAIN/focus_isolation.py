"""Short, reversible no-activation window for this process's MasterShell only."""
import ctypes
from ctypes import wintypes
import logging
import threading
import time

logger = logging.getLogger("BRAINNET_FocusIsolation")
_lock = threading.RLock()
_window = None
_state = None
_timer = None
_until = 0.0
_native = ctypes.WinDLL("user32", use_last_error=True)
_native.IsWindow.argtypes = [wintypes.HWND]
_native.IsWindow.restype = wintypes.BOOL
_native.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_native.GetWindowLongW.restype = wintypes.LONG
_native.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
_native.SetWindowLongW.restype = wintypes.LONG
NO_ACTIVATE = 0x08000000


def register_master_shell(window):
    global _window
    if window is not None:
        with _lock:
            _window = window


def _restore():
    global _state, _timer
    with _lock:
        remaining = _until - time.monotonic()
        if remaining > 0:
            _timer = threading.Timer(remaining, _restore)
            _timer.daemon = True
            _timer.start()
            return
        if _state:
            window, hwnd, original_focus, originally_disabled = _state
            try:
                if _native.IsWindow(hwnd):
                    style = _native.GetWindowLongW(hwnd, -20)
                    _native.SetWindowLongW(hwnd, -20, style | NO_ACTIVATE if originally_disabled else style & ~NO_ACTIVATE)
                window.focus = original_focus
            except Exception:
                logger.exception("Falha ao restaurar estilo de ativação do MasterShell")
            finally:
                _state = None
        _timer = None


def suspend_master_shell_focus(seconds=3.0):
    global _state, _until, _timer
    with _lock:
        if _window is None or getattr(_window, "native", None) is None:
            return False
        hwnd = int(_window.native.Handle.ToInt64())
        if not _native.IsWindow(hwnd):
            return False
        if _state is None:
            style = _native.GetWindowLongW(hwnd, -20)
            _state = (_window, hwnd, _window.focus, bool(style & NO_ACTIVATE))
        _window.focus = False
        style = _native.GetWindowLongW(hwnd, -20)
        _native.SetWindowLongW(hwnd, -20, style | NO_ACTIVATE)
        if not _native.GetWindowLongW(hwnd, -20) & NO_ACTIVATE:
            _window.focus = _state[2]
            _state = None
            raise RuntimeError("Não foi possível suspender a ativação do MasterShell")
        _until = max(_until, time.monotonic() + seconds)
        if _timer:
            _timer.cancel()
        _timer = threading.Timer(max(0, _until - time.monotonic()), _restore)
        _timer.daemon = True
        _timer.start()
        # Suppress DOM autoFocus as well; no layout or global CSS is changed.
        _window.evaluate_js("""(() => {
          window.__brainnetNoFocusUntil = Date.now() + 3000;
          if (!window.__brainnetOriginalFocus) {
            window.__brainnetOriginalFocus = HTMLElement.prototype.focus;
            HTMLElement.prototype.focus = function(...args) {
              if (Date.now() < (window.__brainnetNoFocusUntil || 0)) return;
              return window.__brainnetOriginalFocus.apply(this, args);
            };
          }
          if (document.activeElement) document.activeElement.blur();
        })()""")
        return True
