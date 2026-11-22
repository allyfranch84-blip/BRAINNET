import json
import logging
import urllib.request
import zipfile
import io
import shutil
from pathlib import Path

logger = logging.getLogger("BRAINNET_Update")

class UpdateManager:
    def __init__(self, brain_dir, manifest_url=None):
        self.brain_dir = Path(brain_dir)
        self.manifest_url = manifest_url or "https://raw.githubusercontent.com/henrique/brainnet/main/manifest.json"
        self.current_version = self._read_local_version()

    def _read_local_version(self):
        v_file = self.brain_dir / "VERSION"
        if v_file.exists():
            return v_file.read_text(encoding="utf-8").strip()
        return "8.9.0"

    def check_updates(self):
        try:
            req = urllib.request.Request(self.manifest_url, headers={"User-Agent": "BRAINNET-Update"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                latest = data.get("version", "0.0.0")
                changelog = data.get("changelog", "Sem notas.")
                download_url = data.get("download_url", "")
                
                available = latest > self.current_version
                
                return {
                    "available": available,
                    "current": self.current_version,
                    "latest": latest,
                    "changelog": changelog,
                    "download_url": download_url,
                }
        except Exception as e:
            logger.error(f"[UPDATE]: Falha ao checar atualizações: {e}")
            return {"available": False, "error": str(e)}

    def download_and_stage_update(self, download_url):
        staging = self.brain_dir.parent / "UPDATE_STAGING"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        
        req = urllib.request.Request(download_url, headers={"User-Agent": "BRAINNET-Update"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            zip_data = resp.read()
            
        with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
            z.extractall(staging)
            
        logger.info(f"[UPDATE]: Nova versão baixada e extraída em {staging}")
        return staging

    def apply_staged_update(self, staging):
        try:
            for item in staging.rglob("*"):
                if item.is_file():
                    rel_path = item.relative_to(staging)
                    target = self.brain_dir / rel_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, target)
                    
            logger.info("[UPDATE]: Arquivos substituídos com sucesso.")
            return True
        except Exception as e:
            logger.error(f"[UPDATE]: Falha ao aplicar a atualização: {e}")
            return False