# ==============================================================================
# BRAINNET v7 - SISTEMA OPERACIONAL COGNITIVO
# MODULO: cybernetic_verifier.py
# FUNCAO: Operador de Medicao Fisica M_SO (PID ∧ HWND ∧ NCD).
# Tag: [BN_CYBERNETIC_VERIFIER]
# ==============================================================================

from __future__ import annotations

import hashlib
import ctypes
from ctypes import wintypes
import time
import math
from typing import Any, Callable, Dict, Optional, Set, Tuple

import psutil

try:
    import lz4.frame
    HAS_LZ4 = True
except ImportError:
    import zlib
    HAS_LZ4 = False

user32 = ctypes.WinDLL("user32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

DWMWA_CLOAKED = 14


class CyberneticVerifier:
    """
    Operador de medicao fisica M_SO.
    Retorna lambda=1 somente quando a conjuncao tripartite e satisfeita:
        lambda = [novo_PID] AND [HWND_visivel_nao_cloaked] AND [NCD >= 0.20]
    """

    __slots__ = ("ncd_threshold", "poll_interval", "capture_fn")

    def __init__(
        self,
        ncd_threshold: float = 0.20,
        poll_interval: float = 0.5,
        capture_fn: Optional[Callable[[], bytes]] = None,
    ) -> None:
        if capture_fn is None:
            raise ValueError("capture_fn deve ser injetado (Callable[[], bytes]). Nao ha fallback silencioso.")
        self.ncd_threshold = float(ncd_threshold)
        self.poll_interval = float(poll_interval)
        self.capture_fn = capture_fn

    # -------------------------------------------------------------------------
    # Auxiliares obrigatorios
    # -------------------------------------------------------------------------

    def snapshot_pids(self) -> Set[int]:
        """Captura o conjunto de PIDs ativos no instante atual."""
        return set(psutil.pids())

    def capture_state_bytes(self, bbox: Optional[Tuple[int, int, int, int]] = None) -> bytes:
        """Captura o estado observavel atual via injecao. Se bbox for fornecido, usa ROI."""
        if bbox is not None:
            try:
                return self.capture_fn(bbox=bbox)
            except TypeError:
                # Fallback para funcoes de captura antigas que nao aceitam bbox (ex: mocks de teste)
                pass
        return self.capture_fn()

    def calculate_mlzjd(self, state_before: bytes, state_after: bytes, k: int = 4) -> float:
        """Calcula a Distância de Jaccard usando MinHash de substrings. Extremamente rápido."""
        if state_before == state_after:
            return 0.0

        def get_hashes(data):
            if len(data) < k: return set()
            return {hash(data[i:i+k]) for i in range(0, len(data) - k, max(1, k//2))}

        set_a = get_hashes(state_before)
        set_b = get_hashes(state_after)

        if not set_a or not set_b:
            return 1.0 if set_a != set_b else 0.0

        intersection = len(set_a.intersection(set_b))
        union = len(set_a.union(set_b))
        
        distance = 1.0 - (intersection / union)
        return round(float(distance), 4)

    def calculate_ncd_lz4(self, state_before: bytes, state_after: bytes) -> float:
        """Calcula a Distancia de Compressao Normalizada (NCD)."""
        if state_before == state_after:
            return 0.0

        b_xy = state_before + state_after

        if HAS_LZ4:
            c_x = len(lz4.frame.compress(state_before))
            c_y = len(lz4.frame.compress(state_after))
            c_xy = len(lz4.frame.compress(b_xy))
        else:
            c_x = len(zlib.compress(state_before, level=1))
            c_y = len(zlib.compress(state_after, level=1))
            c_xy = len(zlib.compress(b_xy, level=1))

        ncd = (c_xy - min(c_x, c_y)) / max(c_x, c_y)
        return round(float(ncd), 4)

    def _check_hwnd_liveness(self, hwnd: int) -> Tuple[bool, str]:
        """Verifica HWND visivel, nao-cloaked, dimensoes minimas."""
        if not user32.IsWindow(hwnd):
            return (False, "HWND_INVALIDO")
        if not user32.IsWindowVisible(hwnd):
            return (False, "JANELA_INVISIVEL")

        cloaked = ctypes.c_int(0)
        dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        if cloaked.value != 0:
            return (False, "JANELA_CLOAKED")

        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w <= 100 or h <= 100:
            return (False, "DIMENSOES_INSUFICIENTES")

        return (True, "")

    def _find_top_level_hwnd(self, pid: int) -> int:
        """Localiza o primeiro HWND top-level visivel do PID."""
        found_hwnd = [0]

        def enum_cb(hwnd: int, _: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            win_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(win_pid))
            if win_pid.value == pid:
                # Ignora janelas de ferramentas (WS_EX_TOOLWINDOW)
                ex_style = user32.GetWindowLongW(hwnd, -20) # GWL_EXSTYLE = -20
                if not (ex_style & 0x00000080):
                    found_hwnd[0] = hwnd
                    return False # Para a enumeracao
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        return found_hwnd[0]

    def _build_failure_reason(self, pid_ok: bool, hwnd_ok: bool, ncd_ok: bool, ncd_value: float) -> str:
        """Retorna string de falha estruturada para o error_blackbox."""
        return f"SENSOR_FALHOU: pid={pid_ok} hwnd={hwnd_ok} ncd={ncd_ok} valor_ncd={ncd_value:.4f}"

    # -------------------------------------------------------------------------
    # Nucleo: medicao fisica com colapso
    # -------------------------------------------------------------------------

    def classificar_tipo_mudanca(self, pre_state: Dict[str, Any], post_state: Dict[str, Any]) -> str:
        pid_before, pid_after = pre_state.get("pid"), post_state.get("pid")
        if not pid_before or not pid_after or not post_state.get("hwnd"):
            return "NADA"
        ncd = post_state.get("ncd_real", post_state.get("ncd"))
        if ncd is None or not isinstance(ncd, (int, float)) or not math.isfinite(ncd):
            return "NADA"
        if pid_after != pid_before:
            return "ABRIU_JANELA_NOVA"
        return "MUDOU_ESTADO_INTERNO" if ncd > 0.20 else "NADA"

    def measure_collapse(
        self,
        pid_snapshot_before: Set[int],
        img_pre_bytes: bytes,
        img_post_bytes: bytes,
        timeout_sec: float = 5.0,
        expected_delta: Optional[float] = None,
        contract: Optional[Dict[str, Any]] = None,
    ) -> Tuple[int, float, str, Optional[int], float, float]:
        """
        Mede a transicao de estado fisico.
        Retorna: (lambda_obs, elapsed_ms, failure_reason, discovered_pid, ncd_real, expected_delta)
        """
        contract = {} if contract is None else contract
        action = str(contract.get("action", "")).upper()
        opening = action in ("OPEN_APP", "ENSURE_APP", "START_MENU_SEARCH") and bool(contract.get("app"))
        expects_new_pid = contract.get("expects_new_pid", True)
        if not isinstance(expects_new_pid, bool):
            raise ValueError("expects_new_pid deve ser bool")
        if action in ("TYPE", "HOTKEY", "WAIT", "CLICK", "DRAG", "RIGHT_CLICK", "SCROLL", "MINIMIZE_WINDOW", "MAXIMIZE_WINDOW"):
            expects_new_pid = False
        min_ncd = self.ncd_threshold if expects_new_pid else float(contract.get("min_ncd", 0.02 if action in ("RIGHT_CLICK", "SCROLL") else 0.05))
        if not 0.0 <= min_ncd <= 1.0:
            raise ValueError("min_ncd deve estar entre 0 e 1")
        expected_delta = min_ncd if expected_delta is None else float(expected_delta)
        if not 0.0 <= expected_delta <= 1.0:
            raise ValueError("expected_delta deve estar entre 0 e 1")
        t0 = time.perf_counter()
        deadline = t0 + timeout_sec

        last_pid_ok = False
        last_hwnd_ok = False
        last_ncd_ok = False
        last_ncd_val = 0.0

        # Avaliacao inicial do img_post_bytes (se fornecido)
        if img_post_bytes:
            last_ncd_val = self.calculate_ncd_lz4(img_pre_bytes, img_post_bytes)
            last_ncd_ok = last_ncd_val >= min_ncd

        while time.perf_counter() <= deadline:
            # Sensor 1 - PID novo
            pids_now = self.snapshot_pids()
            new_pids = pids_now - pid_snapshot_before
            last_pid_ok = len(new_pids) > 0

            # Sensor 2 - HWND visivel e nao-cloaked
            last_hwnd_ok = False
            discovered_pid = None

            if not expects_new_pid:
                hwnd = contract.get("target_hwnd") or user32.GetForegroundWindow()
                pid_val = wintypes.DWORD()
                if hwnd:
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_val))
                    last_pid_ok = pid_val.value in pids_now
                    last_hwnd_ok, _ = self._check_hwnd_liveness(hwnd)
                    if last_pid_ok and last_hwnd_ok:
                        discovered_pid = pid_val.value
                else:
                    last_pid_ok = False
            elif last_pid_ok:
                for pid in new_pids:
                    try:
                        p = psutil.Process(pid)
                        if p.status() in (psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD):
                            continue
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

                    hwnd = self._find_top_level_hwnd(pid)
                    if hwnd:
                        alive, _ = self._check_hwnd_liveness(hwnd)
                        if alive:
                            last_hwnd_ok = True
                            discovered_pid = pid
                            break

            # Sensor 3 - NCD
            # Se img_post_bytes foi passado e ja validou, usa. Senao, re-captura.
            if img_post_bytes and last_ncd_ok:
                pass
            else:
                # ATENÇÃO VISUAL ADAPTATIVA: Se tiver target_hwnd, usa ROI. Senão, Visão Global.
                if contract.get("target_hwnd"):
                    img_now = self.capture_state_bytes(bbox=contract.get("capture_bbox"))
                else:
                    img_now = self.capture_state_bytes()
                last_ncd_val = self.calculate_ncd_lz4(img_pre_bytes, img_now)
                last_ncd_ok = last_ncd_val >= min_ncd

            # Colapso
            if opening:
                from system_intent import find_app_process, app_process_names
                process = find_app_process(contract["app"])
                target = contract.get("target_hwnd")
                if process is None and target and user32.IsWindow(target):
                    owner = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(target, ctypes.byref(owner))
                    try:
                        if psutil.Process(owner.value).name().casefold() in app_process_names(contract["app"]):
                            process = {"pid": owner.value}
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        process = None
                if process is None:
                    from system_intent import find_app_window_by_title
                    process = find_app_window_by_title(contract["app"])
                if process:
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    return (1, elapsed_ms, "", process["pid"], last_ncd_val, expected_delta)
                # A different foreground PID/HWND is never evidence for the requested app.
                last_pid_ok = False
                time.sleep(self.poll_interval)
                continue
            if not expects_new_pid:
                focused = user32.GetForegroundWindow() == hwnd
                if action == "TYPE":
                    last_ncd_ok = last_ncd_val > 0.05
                    target_app = contract.get("app") or contract.get("expected_app")
                    if target_app:
                        from system_intent import find_app_process
                        process = find_app_process(target_app)
                        last_pid_ok = process is not None
                        last_hwnd_ok = last_pid_ok
                        discovered_pid = process["pid"] if process else None
                elif action in ("HOTKEY", "WAIT"):
                    last_ncd_ok = last_ncd_val > 0.02 or focused
                elif (action == "ENSURE_APP" and contract.get("reuse_existing") is True) or (action == "START_MENU_SEARCH" and contract.get("target_hwnd")):
                    last_hwnd_ok = last_hwnd_ok and focused
                    last_ncd_ok = True
                else:
                    last_hwnd_ok = last_hwnd_ok and focused
                    if action == "CLICK":
                        last_ncd_ok = last_ncd_val > 0.05
                    elif action in ("RIGHT_CLICK", "SCROLL"):
                        last_ncd_ok = last_ncd_val >= min_ncd
            if last_pid_ok and last_hwnd_ok and last_ncd_ok:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                return (1, elapsed_ms, "", discovered_pid, last_ncd_val, expected_delta)

            time.sleep(self.poll_interval)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        reason = self._build_failure_reason(last_pid_ok, last_hwnd_ok, last_ncd_ok, last_ncd_val)
        return (0, elapsed_ms, reason, None, last_ncd_val, expected_delta)
