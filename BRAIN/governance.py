"""
AI OS v7 - System Governance Subsystem
Target Architecture:
  - CPU: Intel Xeon E5-2680 v4 (14 Cores / 28 Threads)
  - RAM: 16 GB DDR4
  - GPU: AMD Radeon RX 580 (8 GB VRAM)
Platform: Windows 11 LTSC
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import contextlib
import logging
import threading
import time
from dataclasses import dataclass
from typing import Generator, List, Optional

import psutil

logger = logging.getLogger("AIOS.Governance")
logger.setLevel(logging.INFO)

# Windows API Constants
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102
WAIT_ABANDONED = 0x00000080
INFINITE = 0xFFFFFFFF

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE

kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD

kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
kernel32.ReleaseMutex.restype = wintypes.BOOL

kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL


@dataclass(slots=True, frozen=True)
class CPUMetrics:
    thread_count: int
    per_cpu_usage_pct: List[float]
    total_usage_pct: float


@dataclass(slots=True, frozen=True)
class RAMMetrics:
    total_mb: float
    available_mb: float
    used_mb: float
    percent_used: float


@dataclass(slots=True, frozen=True)
class VRAMMetrics:
    total_mb: float
    used_mb: float
    free_mb: float
    usage_pct: float


class WindowsNamedMutex:
    """Inter-process cross-execution lock using Win32 Named Mutex."""

    def __init__(self, name: str) -> None:
        self.name = f"Global\\{name}"
        self.handle = kernel32.CreateMutexW(None, False, self.name)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def acquire(self, timeout_ms: int = INFINITE) -> bool:
        result = kernel32.WaitForSingleObject(self.handle, timeout_ms)
        if result in (WAIT_OBJECT_0, WAIT_ABANDONED):
            return True
        elif result == WAIT_TIMEOUT:
            return False
        raise ctypes.WinError(ctypes.get_last_error())

    def release(self) -> None:
        if not kernel32.ReleaseMutex(self.handle):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        if self.handle:
            kernel32.CloseHandle(self.handle)
            self.handle = None

    def __del__(self) -> None:
        self.close()


class SystemGovernance:
    """Micro-kernel governance controller for scheduling and resource enforcement."""

    TOTAL_VRAM_MB: float = 8192.0  # AMD RX 580 (8 GB GDDR5)
    TOTAL_THREADS: int = 28       # Intel Xeon E5-2680 v4

    def __init__(self) -> None:
        self._thread_lock = threading.Lock()
        self._ipc_mutex = WindowsNamedMutex("AIOS_V7_RX580_MUTEX")
        self._wmi_instance = None
        self._last_vram_time: float = 0.0
        self._cached_vram: Optional[VRAMMetrics] = None
        self._init_wmi()
        psutil.cpu_percent(interval=None, percpu=True)

    def _init_wmi(self) -> None:
        try:
            import pythoncom

            pythoncom.CoInitialize()
            import wmi

            self._wmi_instance = wmi.WMI()
        except Exception as exc:
            # Importing wmi can itself open a COM connection. A missing or
            # restricted provider must not prevent loading the rest of the kernel.
            logger.warning("Provedor opcional COM/WMI indisponível (%s).", type(exc).__name__)

    def get_cpu_metrics(self) -> CPUMetrics:
        """Collects usage across all 28 execution threads of Xeon E5-2680 v4."""
        per_cpu = psutil.cpu_percent(interval=None, percpu=True)
        total = sum(per_cpu) / len(per_cpu) if per_cpu else 0.0
        return CPUMetrics(
            thread_count=len(per_cpu),
            per_cpu_usage_pct=per_cpu,
            total_usage_pct=round(total, 2)
        )

    def get_ram_metrics(self) -> RAMMetrics:
        """Collects system physical memory allocation state."""
        mem = psutil.virtual_memory()
        return RAMMetrics(
            total_mb=round(mem.total / (1024 ** 2), 2),
            available_mb=round(mem.available / (1024 ** 2), 2),
            used_mb=round(mem.used / (1024 ** 2), 2),
            percent_used=mem.percent
        )

    def get_vram_metrics(self) -> VRAMMetrics:
        """
        Polls dedicated video memory consumption for AMD RX 580.
        Possui cache de 250ms para evitar sobrecarga de chamadas COM em alta frequência.
        """
        now = time.time()
        if self._cached_vram and (now - self._last_vram_time) < 0.25:
            return self._cached_vram

        dedicated_bytes = 0
        if self._wmi_instance is not None:
            try:
                counters = self._wmi_instance.Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapterMemory()
                for c in counters:
                    usage = getattr(c, "DedicatedUsage", None)
                    if usage is not None:
                        dedicated_bytes += int(usage)
            except Exception:
                pass

        used_mb = round(dedicated_bytes / (1024 ** 2), 2)
        used_mb = min(used_mb, self.TOTAL_VRAM_MB)
        free_mb = round(max(0.0, self.TOTAL_VRAM_MB - used_mb), 2)
        usage_pct = round((used_mb / self.TOTAL_VRAM_MB) * 100, 2)

        metrics = VRAMMetrics(
            total_mb=self.TOTAL_VRAM_MB,
            used_mb=used_mb,
            free_mb=free_mb,
            usage_pct=usage_pct
        )
        self._cached_vram = metrics
        self._last_vram_time = now
        return metrics

    @contextlib.contextmanager
    def acquire_vram_lock(self, timeout_sec: float = 30.0) -> Generator[bool, None, None]:
        timeout_ms = int(timeout_sec * 1000) if timeout_sec > 0 else INFINITE
        acquired_thread = self._thread_lock.acquire(timeout=timeout_sec)
        if not acquired_thread:
            raise TimeoutError("Thread-level VRAM lock acquisition timed out.")

        try:
            acquired_ipc = self._ipc_mutex.acquire(timeout_ms=timeout_ms)
            if not acquired_ipc:
                raise TimeoutError("OS-level VRAM Named Mutex acquisition timed out.")
            try:
                yield True
            finally:
                self._ipc_mutex.release()
        finally:
            self._thread_lock.release()
