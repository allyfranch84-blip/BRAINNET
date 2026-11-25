"""Single-owner inference startup and bounded recovery for the desktop launcher."""
import os
import json
import shutil
import subprocess
import threading
import time
import logging
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlsplit
import psutil

LOG=logging.getLogger(__name__)
NAMES=frozenset(('ollama.exe','ollama app.exe','ollama_llama_server.exe','llama-server.exe'))

def reset_inference_processes():
    """Explicit launcher reset only. Never terminate Python, Node or other apps."""
    targets=[]
    for proc in psutil.process_iter(['name','username']):
        try:
            if (proc.info.get('name') or '').casefold() in NAMES and proc.info.get('username')==psutil.Process().username():
                targets.append(proc)
        except (psutil.NoSuchProcess,psutil.AccessDenied):
            continue
    for proc in targets:
        try:
            LOG.warning('inference reset pid=%s name=%s',proc.pid,proc.name())
            proc.terminate()
        except psutil.NoSuchProcess:
            pass
    _,alive=psutil.wait_procs(targets,timeout=4)
    for proc in alive:
        try: proc.kill()
        except psutil.NoSuchProcess: pass
    _,alive=psutil.wait_procs(alive,timeout=3)
    if alive:
        raise RuntimeError('Inference processes did not exit')
    return len(targets)

class InferenceSupervisor:
    def __init__(self):
        self.kind=os.getenv('BRAINNET_INFERENCE_BACKEND','ollama').casefold()
        if self.kind not in ('ollama','llamacpp'):
            raise ValueError('unknown inference backend')
        self.model=os.getenv('BRAINNET_MOTOR_MODEL','qwen2.5:1.5b')
        self.endpoint=('http://127.0.0.1:11435' if self.kind=='ollama' else 'http://127.0.0.1:8080')
        self.proc=None
        self.manager=None
        self.stop_event=threading.Event()
        self.lock=threading.RLock()
        self.state='STOPPED'
        self.error=None
        self.attempts=0
        self.worker=None
        self.reset_done=False

    def _json(self,path,data=None,timeout=3):
        req=Request(self.endpoint+path,data=json.dumps(data).encode() if data is not None else None,
                    headers={'Content-Type':'application/json'})
        with urlopen(req,timeout=timeout) as response:
            return json.load(response)

    def _port_free(self):
        port=urlsplit(self.endpoint).port
        return not any(c.status=='LISTEN' and c.laddr and c.laddr.port==port for c in psutil.net_connections(kind='tcp'))

    def _spawn(self):
        if not self._port_free():
            raise RuntimeError('Configured port occupied; refusing to kill unknown owner')
        if self.kind=='ollama':
            executable=shutil.which('ollama.exe') or shutil.which('ollama')
            if not executable:
                raise RuntimeError('ollama.exe not found')
            env=os.environ.copy()
            env.update(OLLAMA_HOST='127.0.0.1:11435',OLLAMA_NUM_PARALLEL='1',OLLAMA_MAX_LOADED_MODELS='1')
            env.setdefault('OLLAMA_VULKAN','1')
            # Preserve configured model directory; never substitute an invented path.
            log=Path(__file__).resolve().parent/'development_logs'/'ollama_supervisor.log'
            log.parent.mkdir(exist_ok=True)
            with log.open('a',encoding='utf-8') as out:
                self.proc=subprocess.Popen([executable,'serve'],env=env,stdout=out,stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        else:
            from inference_backend import LlamaProcessManager
            executable=os.getenv('BRAINNET_LLAMA_EXE') or shutil.which('llama-server.exe')
            gguf=os.getenv('BRAINNET_LLAMA_GGUF')
            if not executable or not gguf:
                raise RuntimeError('Configure BRAINNET_LLAMA_EXE and BRAINNET_LLAMA_GGUF')
            self.manager=LlamaProcessManager(executable,gguf,endpoint=self.endpoint,
                device=os.getenv('BRAINNET_LLAMA_DEVICE','vulkan'),
                gpu_layers=int(os.getenv('BRAINNET_LLAMA_GPU_LAYERS','20')),
                context_size=4096,concurrency=1,load_mode=os.getenv('BRAINNET_LLAMA_LOAD_MODE') or None)
            if self.manager.start()!='started':
                raise RuntimeError('llama-server not owned by supervisor')

    def _alive(self):
        if self.kind=='ollama':
            return self.proc is not None and self.proc.poll() is None
        return self.manager is not None and self.manager.status()['state'] not in ('crashed','degraded','stopped','blocked','external')

    def _warmup(self):
        deadline=time.monotonic()+45
        while not self.stop_event.is_set() and time.monotonic()<deadline:
            if not self._alive():
                raise RuntimeError('Inference process exited during startup')
            try:
                self._json('/api/version' if self.kind=='ollama' else '/health')
                break
            except (OSError,ValueError):
                self.stop_event.wait(.5)
        else:
            raise RuntimeError('Server readiness timeout')
        if self.kind=='ollama':
            models=self._json('/api/tags').get('models',[])
            names={m.get('name') for m in models}
            if self.model not in names and self.model+':latest' not in names:
                raise RuntimeError('Configured local model not installed')
            result=self._json('/api/generate',{'model':self.model,'prompt':'Responda apenas OK',
                'stream':False,'options':{'num_ctx':4096,'num_predict':8,'temperature':0}},timeout=60)
            if result.get('done') is not True or not str(result.get('response','')).strip():
                raise RuntimeError('Generation not confirmed')
        else:
            result=self._json('/v1/chat/completions',{'model':self.model,'messages':[{'role':'user','content':'Responda apenas OK'}],
                'stream':False,'max_tokens':8,'temperature':0},timeout=60)
            if not str(result['choices'][0]['message'].get('content','')).strip():
                raise RuntimeError('Generation not confirmed')
        self.state='READY'
        self.error=None

    def _stop_owned(self):
        if self.manager is not None:
            self.manager.stop()
            self.manager=None
        if self.proc is not None:
            try:
                parent=psutil.Process(self.proc.pid)
                # Check Popen handle first; do not act on a recycled PID.
                children=parent.children(recursive=True) if self.proc.poll() is None else []
                for child in children:
                    try: child.terminate()
                    except psutil.NoSuchProcess: pass
                if self.proc.poll() is None:
                    self.proc.terminate()
                    try: self.proc.wait(timeout=4)
                    except subprocess.TimeoutExpired:
                        self.proc.kill()
                        self.proc.wait(timeout=3)
                _,alive=psutil.wait_procs(children,timeout=3)
                for child in alive:
                    try: child.kill()
                    except psutil.NoSuchProcess: pass
            except psutil.NoSuchProcess:
                pass
            self.proc=None

    def start(self,*,reset=False):
        with self.lock:
            if self.stop_event.is_set():
                return False
            self.state='STARTING'
            try:
                if reset and not self.reset_done:
                    self.reset_done=True
                    reset_inference_processes()
                self._spawn()
                self._warmup()
                LOG.info('Inference READY backend=%s model=%s endpoint=%s',self.kind,self.model,self.endpoint)
                return True
            except Exception as exc:
                self.error=f'{type(exc).__name__}: {exc}'
                self.state='UNAVAILABLE'
                LOG.error('Inference unavailable: %s',self.error)
                # A startup failure is not a reason to kill external processes.
                return False

    def monitor(self):
        while not self.stop_event.wait(5):
            with self.lock:
                if self._alive():
                    # Do not restart a live server merely because it is busy.
                    continue
                if self.attempts>=2:
                    self.state='RESTART_LIMIT'
                    return
                self.attempts+=1
            if self.stop_event.wait(5*self.attempts):
                return
            self.start()

    def launch(self,*,reset=False):
        # Called once from the actual main entrypoint, never on import.
        self.start(reset=reset)
        self.worker=threading.Thread(target=self.monitor,daemon=True,name='inference-supervisor')
        self.worker.start()

    def backend(self,model):
        from inference_backend import HTTPInferenceBackend,ModelUnavailable,BackendUnavailable
        if self.state!='READY' or not self._alive():
            raise BackendUnavailable(self.error or self.state)
        if self.kind=='llamacpp' and model!=self.model:
            raise ModelUnavailable('Independent server has only the configured model loaded')
        return HTTPInferenceBackend(self.endpoint,model,self.kind,supervisor=self.manager)

    def status(self):
        return {'backend':self.kind,'endpoint':self.endpoint,'model':self.model,
                'state':self.state if self._alive() else 'STOPPED' if self.state=='READY' else self.state,
                'error':self.error,'restarts':self.attempts}

    def stop(self):
        self.stop_event.set()
        with self.lock:
            self._stop_owned()
            self.state='STOPPED'
