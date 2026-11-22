"""Opt-in observer: bounded telemetry, passive UIA and advice only."""
from collections import deque
import ctypes
import logging
import math
import os
import threading
import time
from types import SimpleNamespace

from adaptive_resource_controller import AdaptiveResourceController, ResourceSample
from visual_attention import VisualAttentionManager

logger=logging.getLogger('BRAINNET_AdaptiveObserve')

def configured_interval(value):
    try:n=float(value)
    except (TypeError,ValueError):return 30.0
    return min(300.0,max(5.0,n)) if math.isfinite(n) else 30.0

def user_idle_seconds():
    if os.name!='nt':return None
    class LASTINPUTINFO(ctypes.Structure):
        _fields_=[('cbSize',ctypes.c_uint),('dwTime',ctypes.c_uint32)]
    info=LASTINPUTINFO();info.cbSize=ctypes.sizeof(info)
    try:
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):return None
        # GetTickCount and LASTINPUTINFO are both 32-bit counters, including wraparound.
        tick=ctypes.windll.kernel32.GetTickCount() & 0xffffffff
        return ((tick-info.dwTime)&0xffffffff)/1000.0
    except (OSError,AttributeError):return None

class AdaptiveObserver:
    def __init__(self,kernel,interval=30.0,*,sensor=None,controller=None,clock=time.monotonic):
        self.kernel=kernel;self.interval=configured_interval(interval);self.clock=clock
        if sensor is None:
            # Dedicated sensor instances avoid mutating the motor path's UIA cache.
            from context_capture import ContextCapture
            from perception_eye import PerceptionEye
            isolated=SimpleNamespace(context_engine=ContextCapture(),eye=PerceptionEye(),vision=None)
            sensor=VisualAttentionManager(isolated,refresh_interval=self.interval,
                min_observation_interval=self.interval,allow_capture=False,enable_ocr=False,include_sensitive=False,clock=clock)
        self.sensor=sensor
        self.controller=controller or AdaptiveResourceController(clock=clock)
        self.records=deque(maxlen=100);self._stop=threading.Event();self._thread=None;self._lock=threading.Lock()
        self._cpu_ready=False
    def tick(self):
        t0=self.clock();cpu=ram=idle=None;degraded=[]
        try:
            import psutil
            measured=psutil.cpu_percent(interval=None)
            if self._cpu_ready:cpu=measured
            else:self._cpu_ready=True;degraded.append('cpu_warmup')
        except Exception:degraded.append('cpu_unavailable')
        try:
            import psutil
            ram=psutil.virtual_memory().available/(1024*1024)
        except Exception:degraded.append('ram_unavailable')
        try:idle=user_idle_seconds()
        except Exception:degraded.append('user_activity_unavailable')
        if idle is None:degraded.append('user_activity_unavailable')
        try:obs=self.sensor.observe()
        except Exception:obs={};degraded.append('passive_observation_unavailable')
        before=self.controller.state.value
        sample=ResourceSample(cpu_pct=cpu,gpu_pct=None,ram_available_mb=ram,
            user_active=(idle<30 if idle is not None else None),user_idle_seconds=idle,
            active_tasks=None,timestamp=self.clock(),sources={'cpu':'psutil' if cpu is not None else 'UNKNOWN',
            'ram':'psutil' if ram is not None else 'UNKNOWN','gpu':'UNKNOWN','user_activity':'GetLastInputInfo' if idle is not None else 'UNKNOWN','tasks':'UNKNOWN'})
        decision=self.controller.update_observation(sample,obs)
        advice=self.controller.residency_advice(decision,{'models':[]})
        # Whitelist only non-sensitive fields, never observations, window names, titles or prompts.
        record={'previous_state':before,'state':decision['state'],'attention':decision['attention'],
            'reason':decision['reason'],'metrics':decision['metrics'],'unknown_metrics':decision['unknown_metrics'],
            'confidence':decision['confidence'],'residency_advice':advice,'degraded':sorted(set(degraded+list(obs.get('degraded',[])))),
            'window_changed':bool(obs.get('window_changed')),'uia_changed':bool(obs.get('uia_changed')),
            'capture_performed':bool(obs.get('capture_performed')),'processing_ms':round((self.clock()-t0)*1000,3)}
        with self._lock:self.records.append(record)
        logger.debug('[ADAPTIVE-OBSERVE] state=%s attention=%s unknown=%s processing_ms=%s',
                     record['state'],record['attention'],','.join(record['unknown_metrics']),record['processing_ms'])
        return record
    def _run(self):
        initialized=False
        try:
            try:
                import pythoncom
                pythoncom.CoInitialize();initialized=True
            except Exception as exc:
                logger.debug('[ADAPTIVE-OBSERVE] COM unavailable: %s',type(exc).__name__)
            while not self._stop.is_set():
                try:self.tick()
                except Exception as exc:logger.warning('[ADAPTIVE-OBSERVE] sensor error: %s',type(exc).__name__)
                self._stop.wait(self.interval)
        finally:
            if initialized:pythoncom.CoUninitialize()
    def start(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():return False
            self._stop.clear();self._thread=threading.Thread(target=self._run,name='brainnet-adaptive-observer',daemon=True);self._thread.start();return True
    def stop(self,timeout=2.0):
        self._stop.set();thread=self._thread
        if thread and thread is not threading.current_thread():thread.join(timeout)
        return not (thread and thread.is_alive())
