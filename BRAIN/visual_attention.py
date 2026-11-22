"""Opt-in passive observation. No model inference is performed by the scanner."""
import hashlib
import logging
import threading
import time

logger=logging.getLogger('BRAINNET_VisionAttention')

class VisualAttentionManager:
    def __init__(self, kernel, refresh_interval=30.0, *, min_capture_interval=30.0, min_observation_interval=1.0,
                 enable_ocr=False, include_sensitive=False, allow_capture=True, clock=time.monotonic):
        if refresh_interval<=0 or min_capture_interval<=0 or min_observation_interval<=0: raise ValueError('intervals must be positive')
        self.kernel=kernel;self.refresh_interval=float(refresh_interval);self.min_capture_interval=float(min_capture_interval)
        self.enable_ocr=enable_ocr;self.include_sensitive=include_sensitive;self.clock=clock
        self.allow_capture=allow_capture
        self.min_observation_interval=float(min_observation_interval);self._last_scan=None
        self._last_summary=None;self._last_focus_hash=None;self._last_capture=None;self._last_window=None
        self._last_controls=None;self._last_uia_focus=None;self._last_region=None;self._region_persistence=0
        self._running=False;self._thread=None;self._lock=threading.Lock();self._stop_event=threading.Event()
    def start(self):
        if self._running:return
        self._running=True;self._stop_event.clear();self._thread=threading.Thread(target=self._loop,daemon=True);self._thread.start()
    def stop(self):self._running=False;self._stop_event.set()
    def _loop(self):
        while not self._stop_event.is_set():
            try:self._scan_peripheral()
            except Exception as e:logger.debug('[VISION] passive observation failed: %s',type(e).__name__)
            self._stop_event.wait(self.refresh_interval)
    @staticmethod
    def _image_hash(img, roi=None):
        if roi is not None:
            if len(roi)!=4 or not all(isinstance(v,int) for v in roi):raise ValueError('invalid ROI')
            left,top,right,bottom=roi
            if not (0<=left<right<=img.width and 0<=top<bottom<=img.height):raise ValueError('ROI outside image')
            img=img.crop(roi)
        img=img.resize((32,32)).convert('L')
        return hashlib.sha256(img.tobytes()).hexdigest()
    def _compute_focus_hash(self):
        # Compatibility helper, only called explicitly; scanner enforces its own capture interval.
        img,_,_=self.kernel.vision.capture_ui_observation(self.kernel.context_engine)
        return self._image_hash(img)
    def _scan_peripheral(self, *, roi=None):
        with self._lock:
            now=self.clock(); degraded=[]
            if self._last_scan is not None and now-self._last_scan<self.min_observation_interval:
                return {**self._last_summary, 'rate_limited':True}
            self._last_scan=now
            try:ctx=self.kernel.context_engine.capture_foreground_context() or {}
            except Exception:ctx={};degraded.append('foreground_unavailable')
            hwnd=ctx.get('hwnd');pid=ctx.get('pid');window=(hwnd,pid)
            window_changed=self._last_window is not None and window!=self._last_window
            self._last_window=window
            if window_changed:
                self._last_controls=None;self._last_uia_focus=None;self._last_focus_hash=None;self._last_region=None;self._region_persistence=0
            control_changed=False;focus_changed=False;uia_available=False
            eye=getattr(self.kernel,'eye',None)
            if eye is not None and hwnd:
                try:
                    controls=eye.scan_window_controls(hwnd)
                    # Store only a digest, never control names or text.
                    identity=sorted((str(getattr(c,'name','')),str(getattr(c,'class_name','')),str(getattr(c,'affordance',''))) for c in controls)
                    control_hash=hashlib.sha256(repr(identity).encode()).hexdigest()
                    control_changed=self._last_controls is not None and control_hash!=self._last_controls
                    self._last_controls=control_hash;uia_available=True
                    # Optional focus provider: absent is unknown rather than a guessed focused element.
                    focus=getattr(eye,'get_focused_control',None)
                    if callable(focus):
                        f=focus(hwnd); marker=hashlib.sha256(repr(f).encode()).hexdigest()
                        focus_changed=self._last_uia_focus is not None and marker!=self._last_uia_focus;self._last_uia_focus=marker
                except Exception:degraded.append('uia_unavailable')
            else:degraded.append('uia_unavailable')
            visual_changed=False;captured=False;ocr_status='disabled';region_persistent=False
            vision=getattr(self.kernel,'vision',None)
            # Only inspect pixels for a task ROI or newly focused window, and never exceed rate cap.
            due=self._last_capture is None or now-self._last_capture>=self.min_capture_interval
            if self.allow_capture and vision is not None and due and (roi is not None or window_changed):
                self._last_capture=now
                try:
                    img,_,_=vision.capture_ui_observation(self.kernel.context_engine);captured=True
                    marker=self._image_hash(img,roi)
                    visual_changed=self._last_focus_hash is not None and marker!=self._last_focus_hash
                    self._last_focus_hash=marker
                    self._region_persistence=self._region_persistence+1 if marker==self._last_region and visual_changed is False else 1
                    region_persistent=roi is not None and self._region_persistence>=2
                    self._last_region=marker
                    if self.enable_ocr:
                        try:
                            regions=vision.extrair_texto_e_coordenadas(img.crop(roi) if roi else img)
                            ocr_status='available' if regions else 'empty'
                        except Exception:ocr_status='unavailable';degraded.append('ocr_unavailable')
                except Exception:degraded.append('capture_unavailable')
            elif self.allow_capture and vision is None:degraded.append('visual_capture_unavailable')
            self._last_summary={'focused_window':str(ctx.get('title',''))[:80] if self.include_sensitive else '',
                'focused_process':str(ctx.get('process_name','unknown')),'hwnd':hwnd,'pid':pid,
                'window_changed':window_changed,'uia_changed':control_changed,'uia_focus_changed':focus_changed,
                'uia_available':uia_available,'visual_changed':visual_changed,'region_persistent':region_persistent,
                'capture_performed':captured,'ocr_status':ocr_status,'degraded':degraded,'scanned_at':time.time()}
            return dict(self._last_summary)
    def observe(self, *, roi=None): return self._scan_peripheral(roi=roi)
    def escalate_visual(self, image, *, authorized=False):
        if authorized is not True:raise PermissionError('explicit escalation required')
        return self.kernel.vision.descrever_elemento_visual(image)
    def get_summary(self):
        with self._lock:
            if not self._last_summary:return '[VISAO]: sem leitura ainda.'
            s=self._last_summary
            return f"[VISAO PERIFERICA] Processo: {s['focused_process']} | UIA: {'disponivel' if s['uia_available'] else 'indisponivel'}"
    def refresh(self): return self._scan_peripheral()
