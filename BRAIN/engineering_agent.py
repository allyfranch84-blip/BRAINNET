import json
import logging
import re
import subprocess
import urllib.request
import sys
from pathlib import Path
from typing import Dict, Any, List
from assistant_prompts import MODELO_DEEP

logger = logging.getLogger("BRAINNET_Engineer")

def assess_change(evidence):
    """Review-only gate; never applies a patch or executes untrusted code."""
    if not isinstance(evidence,dict): raise ValueError('evidence must be a mapping')
    if evidence.get('rejected') is True:return 'REJECTED'
    stages=(('static_valid','STATIC_VALID'),('safe_tests_passed','TESTED_SAFE'),
            ('integration_validated','INTEGRATION_VALIDATED'),('stability_validated','STABILITY_VALIDATED'))
    state='PROPOSED'
    for key,label in stages:
        if evidence.get(key) is not True:return state
        state=label
    if evidence.get('human_approved') is not True:return state
    return 'APPROVED'

def classify_error(error):
    """Classifica sem executar codigo nem propor correcao automatica."""
    if isinstance(error, BaseException):
        if isinstance(error, IndentationError): return 'IndentationError'
        if isinstance(error, SyntaxError): return 'SyntaxError'
        if isinstance(error, ModuleNotFoundError): return 'ModuleNotFoundError'
        if isinstance(error, ImportError): return 'ImportError'
        if isinstance(error, TypeError): return 'TypeError'
        if isinstance(error, NameError): return 'NameError'
        return 'UNKNOWN'
    if not isinstance(error, str): return 'UNKNOWN'
    matches = re.findall(r'(?m)^\s*(IndentationError|SyntaxError|ModuleNotFoundError|ImportError|TypeError|NameError)\s*:', error)
    return matches[-1] if matches else 'UNKNOWN'

class EngineeringAgent:
    def __init__(self, kernel, bridge):
        self.kernel = kernel
        self.bridge = bridge
        self.projects_dir = Path(r"A:\BRAINNET\PROJETOS")
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    def _call_llm(self, prompt: str, model: str = MODELO_DEEP, is_json: bool = True) -> str:
        payload = {
            "model": model, "prompt": prompt, "stream": False,
            "keep_alive": "5m",
            "options": {"temperature": 0.2, "num_ctx": 8192, "num_predict": 2048}
        }
        if is_json:
            payload["format"] = "json"

        try:
            req = urllib.request.Request("http://localhost:11434/api/generate", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read().decode("utf-8")).get("response", "").strip()
        except Exception as e:
            logger.error(f"[ENGINEER]: Falha no LLM: {e}")
            return ""

    def plan_project(self, goal: str) -> Dict[str, Any]:
        """Fase 1: Pesquisa e Planejamento da estrutura do projeto."""
        self.bridge._push_event("aios:message", {"role": "ai", "text": f"📐 Planejando a arquitetura do projeto: *{goal}*..."})

        prompt = (
            "Você é o Engenheiro de Software Chefe da BRAINNET.\n"
            f"OBJETIVO DO USUÁRIO: {goal}\n"
            "Crie um plano de arquivos para este projeto. Assuma que o ambiente é Windows 11 e Python 3.12.\n"
            "Se precisar de bibliotecas externas (ex: pygame, requests), liste-as.\n"
            "Retorne APENAS um JSON válido com o seguinte formato:\n"
            '{"project_name": "nome_da_pasta", "dependencies": ["lib1", "lib2"], '
            '"files": [{"path": "main.py", "content": "# codigo completo aqui"}, {"path": "modulo.py", "content": "..."}]}'
        )

        response = self._call_llm(prompt)
        try:
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            plan = json.loads(response)
            logger.info(f"[ENGINEER]: Plano gerado para '{plan.get('project_name')}' com {len(plan.get('files', []))} arquivos.")
            return plan
        except Exception as e:
            logger.error(f"[ENGINEER]: Falha ao fazer parse do plano: {e}. Resposta: {response[:200]}")
            return None

    def create_files(self, project_name: str, files: List[Dict[str, str]]) -> Path:
        """Fase 3: Criação dos arquivos em disco."""
        project_path = self.projects_dir / project_name
        project_path.mkdir(parents=True, exist_ok=True)

        for file_info in files:
            file_path = project_path / file_info["path"]
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(file_info["content"], encoding="utf-8")
            logger.info(f"[ENGINEER]: Arquivo criado: {file_path.name}")

        return project_path

    def test_project(self, project_path: Path, entry_file: str = "main.py") -> bool:
        """Fase 4: Teste, Detecção de Falha e Auto-Cura (Active Inference)."""
        max_retries = 3
        
        for attempt in range(1, max_retries + 1):
            self.bridge._push_event("aios:message", {"role": "ai", "text": f"⚙️ Testando o código (Tentativa {attempt}/{max_retries})..."})
            try:
                process = subprocess.Popen(
                    [sys.executable, entry_file],
                    cwd=str(project_path),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )

                try:
                    outs, errs = process.communicate(timeout=5)
                    if process.returncode != 0:
                        erro = errs.strip() or outs.strip()
                        logger.warning(f"[ENGINEER]: Erro na execução:\n{erro}")
                        
                        if attempt < max_retries:
                            self.bridge._push_event("aios:message", {"role": "ai", "text": f"⚠️ Erro detectado ({classify_error(erro)}). Correção automática desativada; revisão necessária."})
                            return False
                        else:
                            self.bridge._push_event("aios:message", {"role": "ai", "text": f"❌ O código falhou após {max_retries} tentativas de auto-cura.\n```\n{erro[:500]}\n```"})
                            return False
                    else:
                        logger.info("[ENGINEER]: Script executou e finalizou com sucesso.")
                        return True
                except subprocess.TimeoutExpired:
                    logger.info("[ENGINEER]: Projeto rodando em background. Janela deve estar aberta.")
                    self.bridge._push_event("aios:message", {"role": "ai", "text": f"✅ **Projeto criado e aberto!** O jogo/app deve estar rodando agora."})
                    return True

            except Exception as e:
                logger.error(f"[ENGINEER]: Falha ao testar projeto: {e}")
                return False
        
        return False

    def _apply_auto_fix(self, project_path: Path, erro: str):
        """Aplicação automática de código gerado exige fluxo isolado e revisão."""
        raise PermissionError("Correção automática desativada; revisão explícita necessária")
