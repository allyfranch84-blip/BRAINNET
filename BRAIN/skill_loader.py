# ==============================================================================
# BRAINNET v7 - SISTEMA OPERACIONAL COGNITIVO
# MODULO: skill_loader.py
# FUNCAO: Carregador Dinamico de Habilidades em Tempo Real com Inspecao Defensiva.
# TAGS DE BUSCA:
#   - [BN_SKILL_DECORATOR] : Decorador @skill para funcoes e classes
#   - [BN_SKILL_LOADER]    : Varredura da pasta HABILIDADES e importacao segura
#   - [BN_SKILL_EXEC]      : Executor assincrono de habilidades
#
# DEPENDENCIAS EXTERNAS:
#   - asyncio, functools, importlib, inspect, os, sys, pathlib.
# QUEM CHAMA ESTE MODULO:
#   - BRAINNET.PY (para listar e executar ferramentas na UI e no Kernel).
# ==============================================================================

from __future__ import annotations

import asyncio
import functools
import importlib.util
import inspect
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger("BRAINNET_SkillLoader")

SKILL_REGISTRY_ATTR = "__aios_skill_meta__"

def normalize_skill_result(result):
    """Legacy crystallized scripts only return a payload; they do not run it."""
    if isinstance(result, dict) and result.get('mode') == 'CRYSTALLIZED_ZERO_LLM' and result.get('status') == 'COMPLETED':
        return {**result, 'status':'PROPOSAL_ONLY', 'executed':False, 'verified':False}
    return result

# ------------------------------------------------------------------------------
# [BN_SKILL_DECORATOR] - DECORADOR OFICIAL @skill
# ------------------------------------------------------------------------------

def skill(
    name: Optional[str] = None,
    description: str = "",
    tags: Optional[List[str]] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorador para marcar funcoes ou classes como Habilidades do BRAINNET.
    """
    def decorator(target: Callable[..., Any]) -> Callable[..., Any]:
        target_name = name or getattr(target, "__name__", "habilidade_anonima")
        
        try:
            sig = str(inspect.signature(target))
        except Exception:
            sig = "(*args, **kwargs)"

        meta = {
            "name": target_name,
            "description": description or (inspect.getdoc(target) or "").strip(),
            "tags": tags or [],
            "is_async": inspect.iscoroutinefunction(target),
            "signature": sig,
        }
        setattr(target, SKILL_REGISTRY_ATTR, meta)
        return target

    return decorator


# ------------------------------------------------------------------------------
# [BN_SKILL_LOADER] - CARREGADOR DINAMICO E REATIVO
# ------------------------------------------------------------------------------

class DynamicSkillLoader:
    """
    [BN_SKILL_LOADER]
    Monitora a pasta HABILIDADES e carrega plugins .py em runtime sem reiniciar.
    """

    __slots__ = ("skills_dir", "_registry", "_file_mtimes", "_modules")

    def __init__(self, skills_dir: Union[str, Path] = "HABILIDADES") -> None:
        self.skills_dir = Path(skills_dir).resolve()
        self._registry: Dict[str, Callable[..., Any]] = {}
        self._file_mtimes: Dict[str, float] = {}
        self._modules: Dict[str, Any] = {}
        self.ensure_skills_dir()
        self.scan_and_load(force=True)

    def ensure_skills_dir(self) -> None:
        """Garante que a pasta HABILIDADES existe no disco."""
        if not self.skills_dir.exists():
            try:
                self.skills_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error(f"Erro ao criar pasta HABILIDADES: {e}")

    def _import_file(self, file_path: Path) -> Optional[Any]:
        """Importa um script Python isoladamente no sys.modules."""
        mod_key = f"bn_skill_{file_path.stem}_{abs(hash(str(file_path)))}"
        try:
            spec = importlib.util.spec_from_file_location(mod_key, file_path)
            if spec is None or spec.loader is None:
                return None
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_key] = module
            spec.loader.exec_module(module)
            self._modules[str(file_path)] = module
            return module
        except Exception as err:
            logger.error(f"Falha ao carregar arquivo de habilidade '{file_path.name}': {err}")
            return None

    def _inspect_and_register(self, module: Any, file_path: Path) -> int:
        """
        Inspeciona o modulo e registra funcoes ou classes decoradas.
        Totalmente imune a ausencias de chaves no dicionario de metadados.
        """
        count = 0
        for attr_name in dir(module):
            if attr_name.startswith("_"):
                continue
            attr = getattr(module, attr_name)

            # Registra estritamente funções ou classes decoradas com @skill
            if hasattr(attr, SKILL_REGISTRY_ATTR):
                meta_dict = getattr(attr, SKILL_REGISTRY_ATTR)
                skill_name = meta_dict.get("name", attr_name)
                self._registry[skill_name] = attr
                count += 1
        return count

    def scan_and_load(self, force: bool = False) -> Dict[str, Callable[..., Any]]:
        """Varre o diretorio e sincroniza os modulos novos ou modificados."""
        if not self.skills_dir.exists():
            return self._registry

        current_files: Dict[str, float] = {}
        for root, _, files in os.walk(self.skills_dir):
            for file in files:
                if file.endswith(".py") and not file.startswith("__"):
                    fpath = Path(root) / file
                    try:
                        current_files[str(fpath)] = fpath.stat().st_mtime
                    except OSError:
                        continue

        # Remove modulos de arquivos deletados
        deleted = set(self._file_mtimes.keys()) - set(current_files.keys())
        for del_path in deleted:
            del self._file_mtimes[del_path]
            if del_path in self._modules:
                del self._modules[del_path]

        # Carrega arquivos novos ou modificados
        for fpath_str, mtime in current_files.items():
            if force or fpath_str not in self._file_mtimes or self._file_mtimes[fpath_str] < mtime:
                fpath = Path(fpath_str)
                mod = self._import_file(fpath)
                if mod:
                    self._file_mtimes[fpath_str] = mtime
                    self._inspect_and_register(mod, fpath)

        return self._registry

    # Alias de compatibilidade com o kernel
    def sync_skills(self, force: bool = False) -> Dict[str, Callable[..., Any]]:
        return self.scan_and_load(force=force)

    @property
    def registry(self) -> Dict[str, Callable[..., Any]]:
        return self._registry

    # --------------------------------------------------------------------------
    # [BN_SKILL_EXEC] - DISPARO ESTRUTURADO (SYNC OU ASYNC)
    # --------------------------------------------------------------------------

    async def execute_skill(self, skill_name: str, *args: Any, **kwargs: Any) -> Any:
        """Executa uma habilidade de forma nao-bloqueante no event loop."""
        self.scan_and_load(force=False)
        if skill_name not in self._registry:
            raise KeyError(f"Habilidade '{skill_name}' nao encontrada no registro.")

        target = self._registry[skill_name]
        is_async = inspect.iscoroutinefunction(target) or (
            hasattr(target, "__call__") and inspect.iscoroutinefunction(target.__call__)
        )

        if is_async:
            return normalize_skill_result(await target(*args, **kwargs))
        else:
            loop = asyncio.get_running_loop()
            return normalize_skill_result(await loop.run_in_executor(None, functools.partial(target, *args, **kwargs)))
