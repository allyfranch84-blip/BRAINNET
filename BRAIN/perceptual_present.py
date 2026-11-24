"""In-memory perceptual present: independently sampled, versioned sensor evidence.
No inference, persistence, screenshots, native input or authorization."""
from copy import deepcopy
import os
import threading
import time


def read_spatial():
    import win32gui, win32api
    from capability_lab import observe_physical_cursor
    cursor=observe_physical_cursor()
    monitors=[]
    errors=[]
    for handle,_,_ in win32api.EnumDisplayMonitors():
        try:
            info=win32api.GetMonitorInfo(handle)
            mode=win32api.EnumDisplaySettingsEx(info['Device'],-1,0)
            x,y=int(mode.Position_x),int(mode.Position_y)
            w,h=int(mode.PelsWidth),int(mode.PelsHeight)
            if w<=0 or h<=0:
                raise ValueError('invalid display mode')
            monitors.append({'device':info['Device'],'rect':(x,y,x+w,y+h),
                             'primary':bool(info.get('Flags',0)&1),'dpi':'UNKNOWN'})
        except Exception as exc:
            errors.append(type(exc).__name__)
    p=cursor.get('cursor')
    matches=[m['device'] for m in monitors if p and m['rect'][0]<=p[0]<m['rect'][2] and m['rect'][1]<=p[1]<m['rect'][3]]
    return {'foreground':int(win32gui.GetForegroundWindow() or 0),
            'cursor':cursor,'monitors':monitors,'cursor_monitor':matches[0] if len(matches)==1 else None,
            'monitor_errors':errors,'monitor_status':'OBSERVED' if monitors and not errors else 'PARTIAL' if monitors else 'UNAVAILABLE'}


def read_windows():
    import win32gui, psutil
    from collections import Counter
    from uia_chat_readonly import inspect_window
    windows=[]
    errors=Counter()
    visible=0
    rejected=0
    truncated=False
    def visit(hwnd,_):
        nonlocal visible,rejected,truncated
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            visible+=1
            if len(windows)>=256:
                truncated=True
                return True
            identity=inspect_window(hwnd)
            if identity is None:
                rejected+=1
                return True
            proc=psutil.Process(identity['pid'])
            if proc.create_time()!=identity['started']:
                rejected+=1
                return True
            # A missing placement property must not discard an otherwise valid window.
            try:
                placement=win32gui.GetWindowPlacement(hwnd)
                show=placement[1]
                minimized=show in (2,6,7)
                maximized=show==3
            except Exception as exc:
                errors['placement:'+type(exc).__name__]+=1
                minimized=None
                maximized=None
            windows.append({**identity,'app':proc.name(),
                'minimized':minimized,'maximized':maximized,
                'owned':identity['pid']==os.getpid(),
                'z_index':len(windows)})
        except Exception as exc:
            errors['window:'+type(exc).__name__]+=1
        return True
    win32gui.EnumWindows(visit,None)
    return {'windows':windows,'errors':dict(errors),'visible_candidates':visible,
            'rejected':rejected,'truncated':truncated,
            'status':'PARTIAL' if windows and (errors or truncated) else 'OBSERVED' if windows else 'UNAVAILABLE'}


class PerceptualPresent:
    """Latest evidence per channel; timestamps describe acquisition intervals, not simultaneity."""
    def __init__(self, eye, *, spatial=read_spatial, windows=read_windows, clock=time.monotonic):
        self.eye=eye
        self.clock=clock
        self.readers={'spatial':spatial,'windows':windows,'uia':self._read_uia}
        self.intervals={'spatial':.12,'windows':.65,'uia':1.5}
        self.max_age={'spatial':.6,'windows':2.0,'uia':4.0}
        self._lock=threading.RLock()
        self._stop=threading.Event()
        self._threads=[]
        self._channels={}
        self._version=0
        self._last_external=None

    def _read_uia(self):
        # Peripheral UIA reads geometry/types only, not names, document contents or values.
        from collections import Counter
        import win32gui
        from uia_chat_readonly import inspect_window
        hwnd=win32gui.GetForegroundWindow()
        if not hwnd:
            return {'status':'FOCUS_TRANSITION'}
        before=inspect_window(hwnd)
        if not before or before['pid']==os.getpid():
            return {'status':'NO_EXTERNAL_FOREGROUND'}
        rows=self.eye.scan_uia_properties(hwnd,max_controls=300,max_depth=16,include_sensitive=False)
        after=inspect_window(hwnd)
        if before!=after or win32gui.GetForegroundWindow()!=hwnd:
            return {'status':'CONTEXT_CHANGED'}
        types=Counter(str(row.get('control_type') or 'unknown') for row in rows)
        return {'status':'OBSERVED' if rows else 'UNAVAILABLE','window':before,
                'count':len(rows),'types':dict(types),'truncated':len(rows)>=300}

    def publish(self, name, value, started, ended, *, status='OBSERVED'):
        if name not in self.intervals or ended<started:
            raise ValueError('invalid sensor sample')
        with self._lock:
            previous=self._channels.get(name)
            if previous and ended<previous['ended']:
                return False
            self._version+=1
            self._channels[name]={'status':status,'started':started,'ended':ended,
                                  'version':self._version,'value':deepcopy(value)}
            spatial=self._channels.get('spatial',{})
            windows=self._channels.get('windows',{})
            if (spatial.get('status')=='OBSERVED' and windows.get('status') in ('OBSERVED','PARTIAL')
                    and 0<=self.clock()-spatial.get('ended',0)<=self.max_age['spatial']
                    and 0<=self.clock()-windows.get('ended',0)<=self.max_age['windows']):
                focus=spatial['value'].get('foreground')
                match=[w for w in windows['value'].get('windows',[]) if w['hwnd']==focus and not w['owned']]
                if len(match)==1:
                    self._last_external=deepcopy(match[0])
            return True

    def _loop(self,name):
        while not self._stop.is_set():
            started=self.clock()
            try:
                value=self.readers[name]()
                self.publish(name,value,started,self.clock(),status=value.get('status','OBSERVED') if name=='windows' else 'OBSERVED')
            except Exception as exc:
                self.publish(name,{'error':type(exc).__name__},started,self.clock(),status='UNAVAILABLE')
            self._stop.wait(self.intervals[name])

    def start(self):
        if any(t.is_alive() for t in self._threads):
            return
        self._stop.clear()
        self._threads=[threading.Thread(target=self._loop,args=(name,),name='brainnet-present-'+name,daemon=True)
                       for name in self.readers]
        for worker in self._threads:
            worker.start()

    def stop(self, timeout=2):
        self._stop.set()
        end=time.monotonic()+timeout
        for worker in self._threads:
            worker.join(max(0,end-time.monotonic()))
        return not any(worker.is_alive() for worker in self._threads)

    def snapshot(self):
        now=self.clock()
        with self._lock:
            channels=deepcopy(self._channels)
            last=deepcopy(self._last_external)
            version=self._version
        for name in self.intervals:
            channel=channels.get(name)
            if channel is None:
                channels[name]={'status':'UNAVAILABLE','age_ms':None,'value':None}
                continue
            age=now-channel['ended']
            channel['age_ms']=round(max(0,age)*1000,1)
            if age<0 or age>self.max_age[name]:
                channel['status']='STALE'
        spatial=channels['spatial']
        window_sample=channels['windows']
        foreground=spatial['value'].get('foreground') if spatial['status']=='OBSERVED' else None
        windows=window_sample['value'].get('windows',[]) if window_sample['status'] in ('OBSERVED','PARTIAL') else []
        live_external=next((w for w in windows if w['hwnd']==foreground and not w['owned']),None)
        # Last external is context only and must still be in the live inventory.
        if last is not None:
            last=next((w for w in windows if (w['hwnd'],w['pid'],w['started'])==
                       (last['hwnd'],last['pid'],last['started']) and not w['minimized']),None)
        uia=channels['uia']
        if uia['status']=='OBSERVED':
            uia_window=uia['value'].get('window')
            if not uia_window:
                uia['status']=uia['value'].get('status','UNAVAILABLE')
            elif uia_window.get('hwnd')!=foreground or not any((w['hwnd'],w['pid'],w['started'])==(uia_window['hwnd'],uia_window['pid'],uia_window['started']) for w in windows):
                uia['status']='CONTEXT_CHANGED'
        return {'version':version,'at':now,'foreground':foreground,
                'focus_state':'TRANSITION' if foreground==0 else 'UNKNOWN' if foreground is None else 'OBSERVED',
                'windows':windows,'external_foreground':live_external,'last_external':last,
                'channels':channels,'action_authorized':False}
