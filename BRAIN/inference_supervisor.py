"""Single-owner inference startup and bounded recovery for the desktop launcher."""
import os
import json
import shutil
import stat
import subprocess
import threading
import time
import logging
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlsplit
import psutil

LOG=logging.getLogger(__name__)

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
        self.external=False
        self.recovery_requested=threading.Event()

    def _json(self,path,data=None,timeout=3):
        req=Request(self.endpoint+path,data=json.dumps(data).encode() if data is not None else None,
                    headers={'Content-Type':'application/json'})
        with urlopen(req,timeout=timeout) as response:
            return json.load(response)

    def _port_free(self):
        port=urlsplit(self.endpoint).port
        return not any(c.status=='LISTEN' and c.laddr and c.laddr.port==port for c in psutil.net_connections(kind='tcp'))

    def _ollama_catalog(self):
        version = self._json('/api/version').get('version')
        rows = self._json('/api/tags').get('models')
        if not isinstance(version, str) or not version.strip() or not isinstance(rows, list):
            raise ValueError('Resposta incompatível com a API Ollama')
        names = [row['name'] for row in rows if isinstance(row, dict) and isinstance(row.get('name'), str)]
        if len(names) != len(rows):
            raise ValueError('Catálogo Ollama inválido')
        return version, names

    def _attach_ollama(self):
        _, names = self._ollama_catalog()
        if self.model not in names and self.model + ':latest' not in names:
            raise RuntimeError('Configured local model not installed')
        self.state = 'AVAILABLE'
        self.error = None

    def preflight(self, *, probe=False):
        """On-demand observation. Only an explicit probe may load the selected model."""
        if self.kind != 'ollama':
            raise ValueError('O preflight de catálogo requer o backend ollama')
        expected = Path('A:/OLLAMA_MODELS')
        default = Path.home() / '.ollama' / 'models'
        store = Path(os.environ.get('OLLAMA_MODELS') or default)
        report = {'endpoint': self.endpoint, 'selected_model': self.model, 'version': None,
                  'models': None, 'selected_installed': None, 'resident': None,
                  'inference': 'NOT_TESTED', 'vulkan': 'UNVERIFIED', 'errors': {},
                  'expected_store_exists': expected.is_dir(), 'disk_free_bytes': {}}
        try:
            report['junction_to_expected'] = (getattr(default.lstat(), 'st_reparse_tag', None) ==
                stat.IO_REPARSE_TAG_MOUNT_POINT and default.samefile(expected))
            report['client_store_matches_expected'] = store.samefile(expected)
        except OSError as exc:
            report['errors']['storage'] = type(exc).__name__
        for drive in ('A:/', 'C:/'):
            try:
                report['disk_free_bytes'][drive] = shutil.disk_usage(drive).free
            except OSError as exc:
                report['errors'][drive] = type(exc).__name__
        try:
            report['version'], names = self._ollama_catalog()
            report['models'] = names
            report['selected_installed'] = self.model in names or self.model + ':latest' in names
        except (OSError, ValueError, AttributeError) as exc:
            report['errors']['server'] = str(exc)
            return report
        try:
            rows = self._json('/api/ps')['models']
            if not isinstance(rows, list):
                raise ValueError('Resposta /api/ps inválida')
            report['resident'] = [{k: row.get(k) for k in ('name','size','size_vram','expires_at')} for row in rows]
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            report['errors']['resident'] = str(exc)
        if probe and report['selected_installed']:
            started = time.monotonic()
            try:
                reply = self._json('/api/generate', {'model': self.model, 'prompt': 'Responda OK',
                    'stream': False, 'options': {'num_ctx': 1024, 'num_predict': 8, 'temperature': 0}}, timeout=60)
                report['inference'] = 'PASS_REAL' if reply.get('done') is True and str(reply.get('response') or '').strip() else 'INCONCLUSIVE'
                report['usage'] = {k: reply.get(k) for k in ('load_duration','eval_count','eval_duration','prompt_eval_count')}
            except (OSError, ValueError, AttributeError) as exc:
                report['inference'] = 'FAIL'
                report['errors']['generation'] = str(exc)
            report['elapsed_ms'] = round((time.monotonic() - started) * 1000, 2)
        return report

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
            device=os.getenv('BRAINNET_LLAMA_DEVICE','vulkan')
            self.manager=LlamaProcessManager(executable,gguf,endpoint=self.endpoint,
                device=device,
                gpu_layers=int(os.getenv('BRAINNET_LLAMA_GPU_LAYERS','0' if device=='cpu' else '20')),
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
                # The legacy reset flag never grants ownership of other sessions.
                if self.proc is not None or self.manager is not None:
                    if self._alive() and not reset and not self.recovery_requested.is_set():
                        self.state = 'READY'
                        return True
                    self._stop_owned()
                if self.kind == 'ollama' and (self.external or not self._port_free()):
                    self.external = True
                    self._attach_ollama()
                    return True
                self._spawn()
                self._warmup()
                self.recovery_requested.clear()
                LOG.info('Inference READY backend=%s model=%s endpoint=%s',self.kind,self.model,self.endpoint)
                return True
            except Exception as exc:
                self.error=f'{type(exc).__name__}: {exc}'
                self.state='UNAVAILABLE'
                LOG.error('Inference unavailable: %s',self.error)
                # Only clean up children created by this supervisor.
                try: self._stop_owned()
                except Exception: LOG.exception('Owned startup cleanup failed')
                return False

    def monitor(self):
        while not self.stop_event.wait(5):
            with self.lock:
                if self.external:
                    if self.state == 'UNAVAILABLE':
                        try:
                            self._attach_ollama()
                        except (OSError, ValueError, RuntimeError, AttributeError) as exc:
                            self.error = str(exc)
                    continue
                if self._alive() and not self.recovery_requested.is_set():
                    # Do not restart a live server merely because it is busy.
                    continue
                if self.attempts>=2:
                    self.state='RESTART_LIMIT'
                    return
                self.attempts+=1
                if self.recovery_requested.is_set():
                    try: self._stop_owned()
                    except Exception:
                        LOG.exception('Owned recovery cleanup failed')
                        self.state='UNAVAILABLE'
                        return
                    self.recovery_requested.clear()
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
        if self.external and self.state=='AVAILABLE':
            return HTTPInferenceBackend(self.endpoint,model,self.kind)
        if self.state!='READY' or not self._alive():
            raise BackendUnavailable(self.error or self.state)
        if self.kind=='llamacpp' and model!=self.model:
            raise ModelUnavailable('Independent server has only the configured model loaded')
        return HTTPInferenceBackend(self.endpoint,model,self.kind,supervisor=self.manager)

    def report_failure(self,exc):
        # Do not treat a slow inference, invalid JSON or missing model as crash.
        # Only request recovery after the server health probe also fails.
        from inference_backend import BackendUnavailable,ProcessFailed
        if not isinstance(exc,(BackendUnavailable,ProcessFailed)):
            return
        with self.lock:
            if self.state not in ('READY', 'AVAILABLE'):
                return
            try:
                self._json('/api/version' if self.kind=='ollama' else '/health',timeout=3)
            except Exception:
                self.error=f'{type(exc).__name__}: {exc}'
                self.state='UNAVAILABLE'
                if not self.external:
                    self.recovery_requested.set()

    def status(self):
        return {'backend':self.kind,'endpoint':self.endpoint,'model':self.model,
                'state':self.state if self._alive() else 'STOPPED' if self.state=='READY' else self.state,
                'ownership':'external' if self.external else ('owned' if self.proc or self.manager else 'none'),
                'error':self.error,'restarts':self.attempts}

    def stop(self):
        self.stop_event.set()
        with self.lock:
            self._stop_owned()
            self.state='STOPPED'


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Pré-voo do Ollama na porta oficial')
    parser.add_argument('--probe', action='store_true', help='Testar geração curta com modelo já instalado')
    args = parser.parse_args()
    result = InferenceSupervisor().preflight(probe=args.probe)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    raise SystemExit(0 if result['selected_installed'] and (not args.probe or result['inference'] == 'PASS_REAL') else 1)
