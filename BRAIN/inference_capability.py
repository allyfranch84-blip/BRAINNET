"""Read-only capability discovery and conservative inference planning.

Importing this module never starts a server or loads model weights.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import os
import platform
import re
import shutil
import struct
import subprocess

UNKNOWN = 'UNKNOWN'
INSUFFICIENT_EVIDENCE = 'INSUFFICIENT_EVIDENCE'


def measurement(value, source, confidence='observed'):
    return {'value': value, 'source': source, 'confidence': confidence,
            'timestamp': datetime.now(timezone.utc).isoformat()}


def _run(args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, errors='replace', timeout=12,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return (p.stdout + p.stderr) if p.returncode == 0 else ''
    except (OSError, subprocess.TimeoutExpired):
        return ''


def discover_hardware(executable=None, disk_path='.'):
    """Collect optional observations; GPU discovery never starts inference."""
    result = {}
    try:
        import psutil
        m = psutil.virtual_memory()
        result['ram_total'] = measurement(m.total, 'psutil.virtual_memory', 'high')
        result['ram_available'] = measurement(m.available, 'psutil.virtual_memory', 'high')
        result['cpu_cores'] = measurement(psutil.cpu_count(logical=False) or UNKNOWN, 'psutil.cpu_count')
        result['cpu_threads'] = measurement(psutil.cpu_count(logical=True) or UNKNOWN, 'psutil.cpu_count')
    except (ImportError, OSError):
        for k in ('ram_total','ram_available','cpu_cores','cpu_threads'):
            result[k] = measurement(UNKNOWN, 'psutil unavailable', 'unknown')
    result['cpu'] = measurement(platform.processor() or UNKNOWN, 'platform.processor')
    try: free = shutil.disk_usage(disk_path).free
    except OSError: free = UNKNOWN
    result['disk_free'] = measurement(free, 'shutil.disk_usage')
    gpus = []
    if os.name == 'nt':
        import json
        out = _run(['powershell','-NoProfile','-Command',
                    'Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM | ConvertTo-Json -Compress'])
        try:
            data = json.loads(out); gpus = data if isinstance(data, list) else [data]
        except (ValueError, TypeError): pass
    result['gpus'] = measurement(gpus if gpus else UNKNOWN, 'Win32_VideoController' if os.name == 'nt' else 'unavailable', 'reported' if gpus else 'unknown')
    result['vram_usable'] = measurement(UNKNOWN, 'unverified: OS and Vulkan values may differ', 'unknown')
    result['shared_memory'] = measurement(UNKNOWN, 'not independently measured', 'unknown')
    result['vulkan_devices'] = measurement(UNKNOWN, 'not queried', 'unknown')
    result['llama'] = measurement(UNKNOWN, 'not configured', 'unknown')
    if executable:
        version = _run([str(executable),'--version'])
        help_text = _run([str(executable),'--help'])
        devices = _run([str(executable),'--list-devices'])
        flags = sorted(set(re.findall(r'--[a-z][a-z0-9-]+', help_text)))
        result['llama'] = measurement({'version':version.strip() or UNKNOWN, 'flags':flags,
            'executable':str(Path(executable).resolve())} if help_text else UNKNOWN, 'llama-server --version/--help', 'reported' if help_text else 'unknown')
        result['vulkan_devices'] = measurement(devices.strip() or UNKNOWN, 'llama-server --list-devices', 'reported' if devices else 'unknown')
    return result


# GGUF v2/v3 values. Large arrays are traversed without retaining their contents.
_FORMATS={0:'B',1:'b',2:'H',3:'h',4:'I',5:'i',6:'f',7:'?',10:'Q',11:'q',12:'d'}
_MAX_ITEMS=20_000_000

def _read_exact(f, n):
    b=f.read(n)
    if len(b)!=n: raise ValueError('GGUF truncado')
    return b

def _num(f, fmt): return struct.unpack('<'+fmt,_read_exact(f,struct.calcsize(fmt)))[0]
def _string(f, keep=True):
    n=_num(f,'Q')
    if n>100_000_000: raise ValueError('string GGUF excede limite')
    if keep: return _read_exact(f,n).decode('utf-8')
    if f.tell()+n>os.fstat(f.fileno()).st_size: raise ValueError('GGUF truncado')
    f.seek(n,1); return None

def _value(f, typ, keep=True):
    if typ in _FORMATS: return _num(f,_FORMATS[typ])
    if typ==8: return _string(f,keep)
    if typ==9:
        etype=_num(f,'I'); count=_num(f,'Q')
        if count>_MAX_ITEMS or etype==9: raise ValueError('array GGUF invalido')
        if etype in _FORMATS:
            n=struct.calcsize(_FORMATS[etype])*count
            if f.tell()+n>os.fstat(f.fileno()).st_size: raise ValueError('GGUF truncado')
            f.seek(n,1)
        elif etype==8:
            for _ in range(count): _string(f,False)
        else: raise ValueError('tipo GGUF desconhecido')
        return None
    raise ValueError('tipo GGUF desconhecido')

def inspect_gguf(path, *, sha256=False):
    """Read metadata only; optional SHA-256 streams file bytes without modifying it."""
    p=Path(path); meta={}
    with p.open('rb') as f:
        if _read_exact(f,4)!=b'GGUF': raise ValueError('assinatura GGUF invalida')
        version=_num(f,'I')
        if version not in (2,3): raise ValueError('versao GGUF nao suportada')
        tensors=_num(f,'Q'); count=_num(f,'Q')
        if count>100_000 or tensors>10_000_000: raise ValueError('cabecalho GGUF invalido')
        for _ in range(count):
            key=_string(f); typ=_num(f,'I')
            keep=(key.startswith('general.') or any(key.endswith('.'+x) for x in (
                'block_count','context_length','embedding_length','feed_forward_length',
                'attention.head_count','attention.head_count_kv','expert_count','expert_used_count')))
            value=_value(f,typ,keep)
            if keep and value is not None: meta[key]=value
    digest=UNKNOWN
    if sha256:
        h=hashlib.sha256()
        with p.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
        digest=h.hexdigest()
    return {'path':str(p.resolve()), 'size_bytes':p.stat().st_size, 'version':version,
            'tensor_count':tensors, 'architecture':meta.get('general.architecture',UNKNOWN),
            'quantization_code':meta.get('general.file_type',UNKNOWN), 'metadata':meta,
            'sha256':digest, 'inspected_at':datetime.now(timezone.utc).isoformat()}


PROFILE_NAMES=('CPU_ONLY','HYBRID_CONSERVATIVE','HYBRID_BALANCED','GPU_MAX_STABLE','MOE_HYBRID')
@dataclass
class ExecutionProfile:
    name: str
    requested: dict
    observed: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    estimates: dict = field(default_factory=dict)
    status: str = 'NOT_TESTED'
    def __post_init__(self):
        if self.name not in PROFILE_NAMES: raise ValueError('perfil desconhecido')
        if self.status not in ('NOT_TESTED','TESTED','FAILED','UNKNOWN'): raise ValueError('estado invalido')


def plan_execution(inventory, model, profile, *, ram_budget=None, vram_budget=None,
                   ram_margin=0, vram_margin=0, max_gpu_layers=None, max_age_seconds=60):
    """Conservative admission: budgets are externally measured evidence, not GGUF size."""
    reasons=[]; req=profile.requested
    if any(isinstance(x,bool) or not isinstance(x,int) or x<0 for x in (ram_margin,vram_margin)):
        raise ValueError('margens devem ser inteiros nao negativos')
    if profile.status != 'TESTED': reasons.append('perfil sem teste de estabilidade')
    arch=model.get('architecture',UNKNOWN); quant=model.get('quantization_code',UNKNOWN)
    if arch==UNKNOWN or quant==UNKNOWN: reasons.append('metadados do modelo incompletos')
    metadata=model.get('metadata',{})
    blocks=metadata.get(str(arch)+'.block_count')
    declared_context=metadata.get(str(arch)+'.context_length')
    if not isinstance(blocks,int) or blocks<=0 or not isinstance(declared_context,int) or declared_context<=0:
        reasons.append('camadas ou contexto do modelo desconhecidos')
    if isinstance(declared_context,int) and isinstance(req.get('context_size'),int) and req['context_size']>declared_context:
        reasons.append('contexto solicitado excede contexto declarado')
    digest=model.get('sha256',UNKNOWN)
    if not isinstance(digest,str) or not re.fullmatch(r'[0-9a-fA-F]{64}',digest): reasons.append('identidade do modelo nao comprovada')
    if profile.observed.get('model_sha256') != digest or profile.observed.get('requested') != req:
        reasons.append('evidencia nao corresponde ao modelo e configuracao')
    peak=profile.metrics.get('ram_peak_bytes')
    if not isinstance(peak,int) or isinstance(peak,bool) or peak<=0 or not isinstance(ram_budget,int) or ram_budget<peak:
        reasons.append('orcamento de RAM sem pico medido compativel')
    ram=inventory.get('ram_available',{}); available=ram.get('value',UNKNOWN)
    try:
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(ram['timestamp'])).total_seconds()
        if age<0 or age>max_age_seconds: reasons.append('medicao de RAM desatualizada')
    except (KeyError,ValueError,TypeError): reasons.append('data de RAM desconhecida')
    if not isinstance(available,int) or available<0: reasons.append('RAM disponivel desconhecida')
    if not isinstance(ram_budget,int) or isinstance(ram_budget,bool) or ram_budget<=0: reasons.append('orcamento de RAM nao comprovado')
    elif isinstance(available,int) and available < ram_budget+ram_margin: reasons.append('RAM insuficiente')
    device=req.get('device','cpu'); layers=req.get('gpu_layers',0)
    if device not in ('cpu','vulkan'): reasons.append('dispositivo invalido')
    if isinstance(layers,bool) or not isinstance(layers,int) or layers<0: reasons.append('camadas invalidas')
    elif device=='cpu' and layers!=0: reasons.append('CPU nao suporta offload')
    elif layers and (not isinstance(max_gpu_layers,int) or layers>max_gpu_layers): reasons.append('offload excede limite comprovado ou desconhecido')
    if isinstance(layers,int) and not isinstance(layers,bool) and isinstance(blocks,int) and layers>blocks+1:
        reasons.append('offload excede camadas do modelo')
    if device=='vulkan':
        vm=inventory.get('vram_usable',{}); vram=vm.get('value',UNKNOWN)
        if not isinstance(vram,int): reasons.append('VRAM utilizavel desconhecida')
        else:
            try:
                age=(datetime.now(timezone.utc)-datetime.fromisoformat(vm['timestamp'])).total_seconds()
                if age<0 or age>max_age_seconds: reasons.append('medicao de VRAM desatualizada')
            except (KeyError,ValueError,TypeError): reasons.append('data de VRAM desconhecida')
        peak_gpu=profile.metrics.get('vram_peak_bytes')
        if not isinstance(peak_gpu,int) or isinstance(peak_gpu,bool) or peak_gpu<=0 or not isinstance(vram_budget,int) or vram_budget<peak_gpu:
            reasons.append('orcamento de VRAM sem pico medido compativel')
        if not isinstance(vram_budget,int) or isinstance(vram_budget,bool) or vram_budget<=0: reasons.append('orcamento de VRAM nao comprovado')
        elif isinstance(vram,int) and vram < vram_budget+vram_margin: reasons.append('VRAM insuficiente')
    if not isinstance(req.get('context_size'),int) or isinstance(req.get('context_size'),bool) or req['context_size']<=0: reasons.append('contexto invalido')
    if req.get('concurrency') is not None and (isinstance(req['concurrency'],bool) or not isinstance(req['concurrency'],int) or req['concurrency']<1): reasons.append('concorrencia invalida')
    if req.get('load_mode') not in (None,'auto','none','mmap','mlock','mmap+mlock','dio'): reasons.append('modo de carregamento invalido')
    flags=inventory.get('llama',{}).get('value',{})
    current_version=flags.get('version') if isinstance(flags,dict) else None
    if not current_version or profile.observed.get('llama_version') != current_version:
        reasons.append('versao da build nao corresponde ao teste')
    flags=flags.get('flags',[]) if isinstance(flags,dict) else []
    needed=['--device','--n-gpu-layers','--ctx-size']
    if req.get('concurrency') is not None: needed.append('--parallel')
    if req.get('load_mode') is not None: needed.append('--load-mode')
    if any(f not in flags for f in needed): reasons.append('argumentos nao verificados na build')
    return {'decision':INSUFFICIENT_EVIDENCE if reasons else 'APPROVED', 'reasons':reasons,
            'requested':dict(req), 'profile_status':profile.status}
