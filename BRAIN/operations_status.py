"""Read-only integration health and factual usage; explicit emergency cancellation."""
import asyncio
import importlib.util
import json
from pathlib import Path
import queue
import sqlite3
import time
import urllib.request
import threading
import copy


class RuntimeTelemetrySampler:
    """Bounded read-only collection, independent of UI polling."""
    def __init__(self, *, interval=10.0, opener=urllib.request.urlopen):
        self.interval = max(5.0, float(interval))
        self.opener = opener
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._snapshot = None
        self._thread = None
        self._cpu_ready = False
        self._process = None

    def collect(self):
        import psutil
        from assistant_prompts import OLLAMA_PS_URL
        started = time.monotonic()
        timestamp = time.time()
        result = {'timestamp': timestamp, 'source': 'psutil + Ollama /api/ps', 'hardware': {}, 'inference': {}}
        hw = result['hardware']
        try:
            cpu = psutil.cpu_percent(interval=None)
            if self._process is None:
                self._process = psutil.Process()
            process_cpu = self._process.cpu_percent(interval=None)
            hw['cpu_total_pct'] = cpu if self._cpu_ready else None
            hw['cpu_process_pct'] = process_cpu if self._cpu_ready else None
            self._cpu_ready = True
        except (OSError, psutil.Error):
            hw.update(cpu_total_pct=None, cpu_process_pct=None)
        try:
            mem = psutil.virtual_memory()
            hw.update(ram_total_bytes=mem.total, ram_used_bytes=mem.used, ram_available_bytes=mem.available,
                      process_rss_bytes=psutil.Process().memory_info().rss)
        except (OSError, psutil.Error):
            hw.update(ram_total_bytes=None, ram_used_bytes=None, ram_available_bytes=None, process_rss_bytes=None)
        hw.update(gpu_pct=None, vram_used_bytes=None, vram_available_bytes=None,
                  gpu_source='Sem sensor de uso AMD validado', temperature_c=None)
        processes = []
        try:
            for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
                try:
                    info = proc.info
                    if (info.get('name') or '').casefold() in ('ollama.exe', 'ollama', 'llama-server.exe', 'llama-server'):
                        memory = info.get('memory_info')
                        processes.append({'pid': info['pid'], 'name': info['name'], 'rss_bytes': memory.rss if memory else None})
                except (OSError, psutil.Error):
                    continue
        except (OSError, psutil.Error):
            processes = None
        result['inference']['processes'] = processes
        request_started = time.monotonic()
        try:
            with self.opener(OLLAMA_PS_URL, timeout=.75) as response:
                payload = json.loads(response.read(1024 * 1024))
            if not isinstance(payload, dict) or not isinstance(payload.get('models'), list):
                raise ValueError('invalid model list')
            result['inference']['ollama'] = {'available': True, 'endpoint': OLLAMA_PS_URL,
                'latency_ms': round((time.monotonic()-request_started)*1000, 2),
                'models': [{'name': item.get('name'), 'size_bytes': item.get('size'),
                            'vram_bytes': item.get('size_vram'), 'expires_at': item.get('expires_at')}
                           for item in payload['models'] if isinstance(item, dict)][:100]}
        except (OSError, ValueError, TypeError):
            result['inference']['ollama'] = {'available': False, 'endpoint': OLLAMA_PS_URL,
                                            'latency_ms': None, 'models': None}
        result['collection_ms'] = round((time.monotonic()-started)*1000, 2)
        with self._lock:
            self._snapshot = result
        return copy.deepcopy(result)

    def snapshot(self):
        with self._lock:
            result = copy.deepcopy(self._snapshot)
        if result is None:
            return {'available': False, 'reason': 'Aguardando primeira coleta'}
        result['stale'] = time.time() - result['timestamp'] > self.interval * 3
        result['available'] = True
        return result

    def _run(self):
        while not self._stop.is_set():
            try:
                self.collect()
            except Exception:
                pass
            self._stop.wait(self.interval)

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return False
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name='brainnet-runtime-telemetry', daemon=True)
            self._thread.start()
            return True

    def stop(self):
        self._stop.set()
        thread = self._thread
        if thread:
            thread.join(timeout=2)
        return not thread or not thread.is_alive()


def diagnostics(bridge):
    from assistant_prompts import OLLAMA_BASE_URL
    cached = getattr(bridge, "_diagnostics_cache", None)
    if cached and time.monotonic() - cached[0] < 5:
        return cached[1]
    def installed(name):
        try:
            return importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):
            return False
    ollama = False
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/tags", timeout=.75) as response:
            payload = json.loads(response.read())
            ollama = isinstance(payload, dict) and isinstance(payload.get("models"), list)
    except (OSError, ValueError):
        ollama = False
    voice = getattr(bridge._kernel, "voice", None)
    thread = getattr(voice, "_thread", None)
    result = {"ollama": {"ok": ollama},
        "ocr": {"ok": installed("rapidocr_onnxruntime") and installed("onnxruntime"),
                "detail": "Disponibilidade das dependências; sem executar OCR"},
        "extension": {"ok": bool(getattr(getattr(bridge._kernel, "browser_bridge", None), "extension_connected", False))},
        "voice": {"ok": bool(thread and thread.is_alive() and installed("pygame") and installed("edge_tts")),
                  "pyaudio": installed("pyaudio"), "pygame": installed("pygame"),
                  "detail": "Player e dependências; microfone/dispositivo não testado"}, "updated_at": time.time()}
    bridge._diagnostics_cache = (time.monotonic(), result)
    return result


def usage_report(pdag):
    path = Path(pdag.db_path).resolve()
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=.2) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(transitions)")}
        if "lambda_obs" not in columns:
            raise sqlite3.OperationalError("Tabela transitions ou coluna lambda_obs indisponível")
        observed = "source = 'observed' AND " if "source" in columns else ""
        latency = "CASE WHEN elapsed_ms >= 0 THEN elapsed_ms END" if "elapsed_ms" in columns else "NULL"
        row = conn.execute(f"SELECT COUNT(*), AVG(lambda_obs) * 100.0, AVG({latency}), COUNT({latency}) FROM transitions WHERE {observed}lambda_obs IN (0, 1)").fetchone()
    return {"available": True, "total_executions": row[0], "success_rate": row[1], "average_latency_ms": row[2],
            "latency_samples": row[3], "updated_at": time.time()}


def panic_stop(bridge):
    from execution_authority import revoke_all_commands
    from owned_processes import stop_owned_processes
    tokens = revoke_all_commands()
    errors = []
    bridge._professor_mode = None
    token = getattr(bridge, "_execution_token", None)
    if token is not None:
        token.set()
    future = getattr(bridge, "_execution_future", None)
    if future is not None:
        if isinstance(future, asyncio.Future):
            if not future.done():
                future.get_loop().call_soon_threadsafe(future.cancel)
        else:
            future.cancel()
    count, process_errors = stop_owned_processes(tokens)
    errors.extend(process_errors)
    bridge._execution_token = bridge._execution_future = None
    bridge._last_executed_task = bridge._last_completed_task = ""
    for method in (getattr(getattr(bridge, "_ear", None), "stop_listening", None),
                   getattr(getattr(bridge._kernel, "voice", None), "parar", None)):
        if method:
            try:
                method()
            except Exception as ex:
                errors.append(str(ex))
    bridge._voice_active = False
    async def stop_actuator():
        actuator = getattr(bridge._kernel, "bridge", None)
        cleared = 0
        if actuator is not None:
            await actuator.stop()
            cleared = await actuator.clear_pending_actions()
        for owner in (bridge, bridge._kernel):
            pending = getattr(owner, "_action_queue", None)
            if isinstance(pending, list):
                pending.clear()
            elif isinstance(pending, (queue.Queue, asyncio.Queue)):
                while True:
                    try:
                        pending.get_nowait()
                        pending.task_done()
                        cleared += 1
                    except (queue.Empty, asyncio.QueueEmpty):
                        break
        return cleared
    loop = getattr(bridge._kernel, "loop", None)
    cleared = 0
    try:
        if isinstance(loop, asyncio.AbstractEventLoop) and loop.is_running():
            cleared = asyncio.run_coroutine_threadsafe(stop_actuator(), loop).result(timeout=3)
        else:
            cleared = asyncio.run(stop_actuator())
    except Exception as ex:
        errors.append(str(ex))
    return {"ok": not errors, "stopped": True, "cleared_actions": cleared, "terminated_processes": count, "errors": errors}
