# ==============================================================================
# BRAINNET v7 - HABILIDADE MODULAR: habilidade_code_vault_coder.py
# FUNCAO: Cofre de Codigo (Vault), Rollback de Seguranca, Fatiamento VSA 
#         e Auto-Aperfeicoamento orientado ao Qwen-Coder 7B.
# ==============================================================================

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.request

# Garante acesso aos modulos do nucleo em A:\BRAINNET\BRAIN
skills_dir = Path(__file__).resolve().parent
brain_dir = skills_dir.parent / "BRAIN"
BRAIN_DIR = brain_dir  # Alias universal para maiúsculo e minúsculo
if str(brain_dir) not in sys.path:
    sys.path.insert(0, str(brain_dir))

VAULT_DIR = brain_dir / "code_vault"

from skill_loader import skill  # type: ignore
from hyperdimensional import FHRRHyperdimensionalEngine  # type: ignore


class _CodeVaultManager:
    """Gerencia o cofre de seguranca, backups e reversao de codigo."""
    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path
        self.vault_path.mkdir(parents=True, exist_ok=True)

    def create_backup(self, file_path: Path) -> Optional[str]:
        if not file_path.exists():
            return None
        
        timestamp = int(time.time() * 1000)
        file_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()[:10]
        backup_name = f"{file_path.stem}_{timestamp}_{file_hash}{file_path.suffix}"
        backup_path = self.vault_path / backup_name

        shutil.copy2(file_path, backup_path)
        return str(backup_path)

    def rollback(self, backup_path: str, target_file: Path) -> bool:
        b_path = Path(backup_path)
        if b_path.exists():
            shutil.copy2(b_path, target_file)
            return True
        return False


@skill(name="code_vault_patch", description="Aplica alteracao cirurgica em arquivo com backup automatico e validacao AST.", tags=["coder", "vault", "self-healing"])
def code_vault_patch(
    file_relative_path: str = "BRAIN/teste_vault.txt",
    target_block_name: str = "teste",
    new_code_snippet: str = "# Teste de seguranca do Vault executado via UI"
) -> Dict[str, Any]:
    project_root = skills_dir.parent
    VAULT_DIR = BRAIN_DIR / "code_vault"
    target_file = (project_root / file_relative_path).resolve()
    
    if not target_file.exists():
        return {"ok": False, "log": f"Arquivo alvo nao encontrado: {target_file}"}

    vault = _CodeVaultManager(VAULT_DIR)
    backup_file = vault.create_backup(target_file)

    try:
        ast.parse(new_code_snippet)
    except SyntaxError as e:
        return {
            "ok": False,
            "error_type": "SYNTAX_ERROR_PRE_CHECK",
            "log": f"Rejeitado por erro de sintaxe AST: linha {e.lineno} - {e.msg}",
            "backup_restored": True
        }

    try:
        content = target_file.read_text(encoding="utf-8")
        
        if target_file.suffix == ".py":
            tree = ast.parse(content)
            target_node = None
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == target_block_name:
                    target_node = node
                    break
            
            if target_node:
                lines = content.splitlines()
                start_idx = target_node.lineno - 1
                end_idx = getattr(target_node, "end_lineno", start_idx + len(new_code_snippet.splitlines()))
                
                new_lines = new_code_snippet.splitlines()
                lines[start_idx:end_idx] = new_lines
                updated_content = "\n".join(lines)
            else:
                updated_content = content + "\n\n" + new_code_snippet
        else:
            updated_content = content + "\n" + new_code_snippet

        target_file.write_text(updated_content, encoding="utf-8")

        if target_file.suffix == ".py":
            compile(updated_content, str(target_file), 'exec')

        return {
            "ok": True,
            "backup_used": backup_file,
            "log": f"Bloco '{target_block_name}' atualizado e validado com sucesso em '{file_relative_path}'."
        }

    except Exception as ex:
        if backup_file:
            vault.rollback(backup_file, target_file)
        return {
            "ok": False,
            "error_type": "RUNTIME_OR_COMPILE_EXCEPTION",
            "log": f"Falha ao aplicar patch. Rollback executado. Erro: {ex}",
            "backup_restored": True
        }


@skill(name="query_coder_7b", description="Envia prompt cirurgico otimizado para o Qwen-Coder 7B local via Ollama (Modo Desenvolvedor Oculto).", tags=["coder", "ollama", "qwen"])
def query_coder_7b(
    prompt_context: str = "# Arquitetura Micro-Kernel BRAINNET v7\n# Motor de Execucao Oculto via Qwen-Coder 7B",
    instruction: str = "Realize varredura e analise de integridade dos modulos locais."
) -> Dict[str, Any]:
    url = "http://localhost:11434/api/generate"
    system_instruction = (
        "Você é o sub-kernel de engenharia de software do BRAINNET v7.\n"
        "Restrições absolutas:\n"
        "1. Retorne APENAS o código puro em bloco markdown (```python ... ```).\n"
        "2. Não adicione saudações ou explicações textuais."
    )
    
    full_prompt = f"{system_instruction}\n\nCONTEXTO:\n{prompt_context}\n\nINSTRUCAO:\n{instruction}"

    payload = {
        "model": "qwen2.5-coder:7b",
        "prompt": full_prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_thread": 14,
            "num_predict": 400
        }
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            response_text = data.get("response", "").strip()
            
            if "```" in response_text:
                parts = response_text.split("```")
                for i in range(1, len(parts), 2):
                    code_candidate = parts[i].strip()
                    if code_candidate.startswith("python"):
                        code_candidate = code_candidate[6:].strip()
                    return {"ok": True, "code": code_candidate, "raw": response_text}

            return {"ok": True, "code": response_text, "raw": response_text}
    except Exception as e:
        return {"ok": False, "error": str(e), "log": "Falha de comunicacao com o Ollama local (Qwen-Coder 7B)."}