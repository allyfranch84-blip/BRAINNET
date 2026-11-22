"""Pure installation planning; never downloads or executes components."""
import json
from pathlib import Path
import platform
import shutil

def discover_local(root=None):
    """Inventory local files/tools without starting services or loading models."""
    root = Path(root).resolve() if root else Path(__file__).resolve().parent
    try:
        import psutil
        ram = psutil.virtual_memory().available
    except (ImportError, OSError):
        ram = None
    try:
        disk = shutil.disk_usage(root).free
    except OSError:
        disk = None
    models = []
    for directory in (root, root / 'models'):
        if directory.is_dir():
            for path in directory.glob('*.gguf'):
                if path.is_file(): models.append(str(path.relative_to(root)))
    return {'root':str(root), 'os':platform.system(), 'architecture':platform.machine(),
            'cpu':platform.processor() or None, 'ram_available':ram, 'disk_free':disk,
            'gpu':'UNKNOWN', 'vulkan':'UNKNOWN', 'ollama_executable':shutil.which('ollama'),
            'llama_server_executable':shutil.which('llama-server'), 'gguf_files':models,
            'model_functionality':'NOT_TESTED'}

def simulate(profile, capabilities, manifest_path=None):
    path = Path(manifest_path) if manifest_path else Path(__file__).with_name('portable_manifest.json')
    manifest=json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('schema_version') != 1 or profile not in manifest['profiles']:
        raise ValueError('unsupported manifest or profile')
    result=[]
    for component in manifest['components']:
        if profile not in component['profiles']: continue
        pending=any(component.get(k) in (None, 'PENDENTE') for k in ('revision','license','minimum','download_bytes','sha256'))
        gpu_unknown=profile == 'Desktop GPU' and capabilities.get('vulkan_verified') is not True
        result.append({'name':component['name'],'decision':'PENDING_EVIDENCE' if pending or gpu_unknown else 'ELIGIBLE',
                       'fallback':component['fallback']})
    return {'profile':profile,'components':result,'execution':'SIMULATION_ONLY'}
