import time
import ctypes
from ctypes import wintypes
import psutil
import logging

logger = logging.getLogger("BRAINNET_WorldState")

class WorldStateCompressor:
    """Comprime o estado do SO em um bloco de texto (~200 tokens) para injetar no LLM."""
    
    __slots__ = ("_cache", "_last_update", "_hwnd", "_ttl")
    
    def __init__(self, ttl_seconds: float = 3.0):
        self._cache: str = ""
        self._last_update: float = 0.0
        self._hwnd: int = 0
        self._ttl = ttl_seconds
        user32 = ctypes.windll.user32
        self._hwnd = user32.GetForegroundWindow()
        
    def get_context(self) -> str:
        """Retorna o contexto comprimido. Se em cache válido, retorna imediatamente."""
        now = time.time()
        user32 = ctypes.windll.user32
        current_hwnd = user32.GetForegroundWindow()
        
        # Se o cache expirou OU a janela em foco mudou, recompõe
        if (now - self._last_update > self._ttl) or (current_hwnd != self._hwnd):
            self._hwnd = current_hwnd
            self._cache = self._build_context()
            self._last_update = now
        
        return self._cache

    def _build_context(self) -> str:
        try:
            import win32gui
            import win32process
            
            # 1. Janela Ativa
            hwnd = self._hwnd
            title = win32gui.GetWindowText(hwnd) if hwnd else "Desconhecida"
            _, pid = win32process.GetWindowThreadProcessId(hwnd) if hwnd else (None, 0)
            proc_name = "Desconhecido"
            if pid:
                try:
                    proc_name = psutil.Process(pid).name()
                except psutil.NoSuchProcess:
                    pass

            # 2. Top Janelas Abertas (Lista Rápida)
            janelas = []
            def enum_cb(h, _):
                if win32gui.IsWindowVisible(h):
                    t = win32gui.GetWindowText(h)
                    if t and len(t) > 2 and t.lower() not in ("default ime", "msctfime ui"):
                        janelas.append(t[:30])
                return True
            win32gui.EnumWindows(enum_cb, None)
            top_janelas = ", ".join(list(dict.fromkeys(janelas))[:5]) or "Nenhuma"

            # 3. Hardware
            ram = psutil.virtual_memory()
            ram_livre = round(ram.available / (1024**2), 0)
            
            # 4. Tempo de sessão
            import datetime
            hora = datetime.datetime.now().strftime("%H:%M")

            return (
                f"[JANELA ATIVA]: '{title}' (Processo: {proc_name}) | "
                f"[TOP JANELAS]: {top_janelas} | "
                f"[HARDWARE]: RAM Livre {ram_livre}MB | "
                f"[HORA]: {hora}"
            )
        except Exception as e:
            logger.error(f"[WORLD STATE]: Falha ao comprimir estado: {e}")
            return "[CONTEXTO]: Indisponível"
