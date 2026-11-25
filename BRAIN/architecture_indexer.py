# -*- coding: utf-8 -*-
"""
ArchitectureIndexer — Mapa Cerebral Permanente da Brainnet
===========================================================

Serviço permanente que indexa, mantém e consulta a arquitetura do projeto.

Uso:
    python architecture_indexer.py --build
    python architecture_indexer.py --refresh
    python architecture_indexer.py --search "DeepThink"
    python architecture_indexer.py --stats
    python architecture_indexer.py --graph
    python architecture_indexer.py --watch

Uso como biblioteca:
    from architecture_indexer import ArchitectureIndexer
    idx = ArchitectureIndexer.singleton()
    idx.build_index()
    results = idx.search_function("semantic_move")
    info = idx.find_function("semantic_move")
    dependents = idx.find_dependents("motor_intent")
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import logging
import os
import sys
import threading
import time
import traceback
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

# =============================================================================
# CONSTANTES
# =============================================================================

VERSION = "2.0.0"
SNAPSHOT_FILE = "architecture_snapshot.json"
REPORT_FILE = "architecture_report.md"
ARCH_GRAPH_FILE = "architecture_graph.json"
DEP_GRAPH_FILE = "dependency_graph.json"
CALL_GRAPH_FILE = "call_graph.json"

DEFAULT_IGNORE_DIRS: Set[str] = {
    "venv", ".venv", "env", "__pycache__", ".git", ".hg", ".svn",
    "build", "dist", "logs", "models", "cache", "tmp", "temp",
    ".pytest_cache", "node_modules", ".mypy_cache", ".ruff_cache",
    ".idea", ".vscode", ".tox", ".eggs", "*.egg-info",
}

DEFAULT_IGNORE_FILES: Set[str] = {
    ".DS_Store", "Thumbs.db", ".gitignore", ".gitkeep",
}

IGNORE_EXTENSIONS: Set[str] = {
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe",
    ".zip", ".tar", ".gz", ".rar", ".7z",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".ico",
    ".mp3", ".mp4", ".avi", ".mov", ".wav",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
}

# Palavras que NÃO são chamadas de função (builtins e keywords)
NON_CALL_NAMES: Set[str] = {
    "print", "len", "str", "int", "float", "bool", "list", "dict",
    "tuple", "set", "frozenset", "bytes", "bytearray", "range",
    "enumerate", "zip", "map", "filter", "sorted", "reversed",
    "sum", "min", "max", "abs", "all", "any", "iter", "next",
    "isinstance", "issubclass", "type", "hasattr", "getattr",
    "setattr", "delattr", "callable", "id", "hash", "repr",
    "format", "input", "open", "super", "object", "property",
    "staticmethod", "classmethod", "classmethod", "staticmethod",
    "Exception", "ValueError", "TypeError", "KeyError",
    "IndexError", "AttributeError", "RuntimeError", "StopIteration",
    "NotImplementedError", "AssertionError", "OSError", "IOError",
}

COMPLEXITY_NODES = (
    ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp,
    ast.With, ast.AsyncWith, ast.Try, ast.BoolOp,
    ast.comprehension, ast.ExceptHandler,
)

logger = logging.getLogger("ArchitectureIndexer")


# =============================================================================
# DATACLASSES
# =============================================================================


@dataclass
class ImportInfo:
    """Representa uma importação (import X, from X import Y, etc.)."""

    module: str
    names: List[str] = field(default_factory=list)
    alias: Optional[str] = None
    lineno: int = 0
    is_relative: bool = False
    level: int = 0
    raw: str = ""
    resolved_module: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CallEdge:
    """Representa uma aresta de chamada: caller -> callee."""

    caller: str
    callee: str
    lineno: int = 0
    is_method: bool = False
    raw: str = ""
    resolved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DependencyEdge:
    """Dependência entre módulos."""

    source_module: str
    target_module: str
    kind: str = "import"  # import | from_import | dynamic
    lineno: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FunctionInfo:
    qualname: str
    name: str
    module: str
    file: str
    lineno: int = 0
    end_lineno: int = 0
    args: List[str] = field(default_factory=list)
    kwargs: List[str] = field(default_factory=list)
    annotations: Dict[str, str] = field(default_factory=dict)
    returns: Optional[str] = None
    decorators: List[str] = field(default_factory=list)
    docstring: Optional[str] = None
    is_async: bool = False
    is_method: bool = False
    complexity: int = 1
    num_params: int = 0
    signature: str = ""
    calls: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ClassInfo:
    qualname: str
    name: str
    module: str
    file: str
    lineno: int = 0
    end_lineno: int = 0
    bases: List[str] = field(default_factory=list)
    decorators: List[str] = field(default_factory=list)
    methods: List[str] = field(default_factory=list)
    docstring: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GlobalVariable:
    qualname: str
    name: str
    module: str
    file: str
    lineno: int = 0
    value_repr: Optional[str] = None
    is_constant: bool = False
    annotation: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FileInfo:
    path: str
    module: str
    sha256: str = ""
    size: int = 0
    mtime: float = 0.0
    imports: List[ImportInfo] = field(default_factory=list)
    classes: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)
    globals: List[str] = field(default_factory=list)
    constants: List[str] = field(default_factory=list)
    docstring: Optional[str] = None
    line_count: int = 0
    dependencies: List[str] = field(default_factory=list)
    call_edges: List[CallEdge] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "module": self.module,
            "sha256": self.sha256,
            "size": self.size,
            "mtime": self.mtime,
            "imports": [i.to_dict() for i in self.imports],
            "classes": self.classes,
            "functions": self.functions,
            "globals": self.globals,
            "constants": self.constants,
            "docstring": self.docstring,
            "line_count": self.line_count,
            "dependencies": self.dependencies,
            "call_edges": [c.to_dict() for c in self.call_edges],
            "exports": self.exports,
        }


@dataclass
class ArchitectureSnapshot:
    timestamp: str
    version: str
    hash: str
    root: str
    statistics: Dict[str, Any] = field(default_factory=dict)
    files: Dict[str, Any] = field(default_factory=dict)
    functions: Dict[str, Any] = field(default_factory=dict)
    classes: Dict[str, Any] = field(default_factory=dict)
    globals: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[Any] = field(default_factory=list)
    call_graph: Dict[str, List[str]] = field(default_factory=dict)
    reverse_call_graph: Dict[str, List[str]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# UTILITÁRIOS
# =============================================================================


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _path_to_module(root: Path, path: Path) -> str:
    """Converte caminho absoluto em nome de módulo python."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        return path.stem
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) if parts else path.stem


def _truncate(text: Optional[str], max_len: int = 500) -> Optional[str]:
    if text is None:
        return None
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _safe_repr(node: ast.AST, max_len: int = 120) -> str:
    try:
        s = ast.unparse(node)
    except Exception:
        s = type(node).__name__
    return _truncate(s, max_len) or ""


def _annot_to_str(node: Optional[ast.AST]) -> Optional[str]:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


def _signature_of(func: ast.AST) -> str:
    try:
        return ast.unparse(func)  # inclui decorators se for o FunctionDef inteiro
    except Exception:
        return ""


def _extract_signature(node: ast.AST) -> str:
    """Retorna apenas o cabeçalho 'def nome(...) -> tipo'."""
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return ""
    try:
        args = ast.unparse(node.args)
    except Exception:
        args = "?"
    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    kw = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
    return f"{kw}{node.name}({args}){ret}"


# =============================================================================
# PARSER AST — EXTRAÇÃO COMPLETA
# =============================================================================


class _ASTExtractor(ast.NodeVisitor):
    """
    Percorre o AST e extrai toda a informação estrutural do arquivo.

    Produz:
        self.imports, self.functions, self.classes, self.globals
        self.calls, self.docstring, self._import_aliases, self._from_imports
    """

    def __init__(self, module_name: str, file_path: str):
        self.module = module_name
        self.file = file_path
        self.imports: List[ImportInfo] = []
        self.functions: List[FunctionInfo] = []
        self.classes: List[ClassInfo] = []
        self.globals: List[GlobalVariable] = []
        self.calls: List[CallEdge] = []
        self.docstring: Optional[str] = None

        # Resolução de nomes
        self._import_aliases: Dict[str, str] = {}       # alias local -> module
        self._from_imports: Dict[str, Tuple[str, str]] = {}  # local -> (module, orig)

        # Contexto de escopo
        self._class_stack: List[str] = []
        self._function_stack: List[str] = []

    # ---------- helpers de escopo ----------

    def _current_qual(self, name: str) -> str:
        parts = list(self._class_stack) + list(self._function_stack)
        if parts:
            return ".".join(parts + [name])
        return name

    def _current_caller(self) -> Optional[str]:
        if not self._function_stack:
            return None
        parts = list(self._class_stack) + list(self._function_stack)
        return f"{self.module}.{'.'.join(parts)}"

    # ---------- módulo ----------

    def visit_Module(self, node: ast.Module) -> None:
        self.docstring = ast.get_docstring(node, clean=True)
        for child in node.body:
            self.visit(child)

    # ---------- imports ----------

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            self._import_aliases[local] = alias.name
            self.imports.append(
                ImportInfo(
                    module=alias.name,
                    names=[alias.name],
                    alias=alias.asname,
                    lineno=node.lineno,
                    is_relative=False,
                    raw=_safe_repr(node),
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        level = node.level or 0
        for alias in node.names:
            local = alias.asname or alias.name
            self._from_imports[local] = (module, alias.name)
            self.imports.append(
                ImportInfo(
                    module=module,
                    names=[alias.name],
                    alias=alias.asname,
                    lineno=node.lineno,
                    is_relative=level > 0,
                    level=level,
                    raw=_safe_repr(node),
                )
            )

    # ---------- classes ----------

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qual = self._current_qual(node.name)
        base_names: List[str] = []
        for base in node.bases:
            base_names.append(_annot_to_str(base) or "")
        decorators = [_annot_to_str(d) or "" for d in node.decorator_list]
        docstring = ast.get_docstring(node, clean=True)

        info = ClassInfo(
            qualname=f"{self.module}.{qual}",
            name=node.name,
            module=self.module,
            file=self.file,
            lineno=node.lineno,
            end_lineno=getattr(node, "end_lineno", node.lineno),
            bases=base_names,
            decorators=decorators,
            docstring=_truncate(docstring),
        )

        self._class_stack.append(node.name)
        # percorre corpo para capturar métodos e anotações
        for child in node.body:
            self.visit(child)
        self._class_stack.pop()

        # depois de visitar, coleta métodos (estão em self.functions com qualname)
        prefix = f"{self.module}.{qual}."
        info.methods = [
            f.qualname for f in self.functions if f.qualname.startswith(prefix)
        ]
        self.classes.append(info)

    # ---------- funções ----------

    def _handle_function(self, node: ast.AST, is_async: bool) -> None:
        assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        qual = self._current_qual(node.name)

        # argumentos
        args_list: List[str] = []
        kwargs_list: List[str] = []
        annotations: Dict[str, str] = {}

        a = node.args
        pos = list(a.posonlyargs) + list(a.args)
        for arg in pos:
            args_list.append(arg.arg)
            if arg.annotation is not None:
                annotations[arg.arg] = _annot_to_str(arg.annotation) or ""
        if a.vararg:
            args_list.append(f"*{a.vararg.arg}")
        for arg in a.kwonlyargs:
            kwargs_list.append(arg.arg)
            if arg.annotation is not None:
                annotations[arg.arg] = _annot_to_str(arg.annotation) or ""
        if a.kwarg:
            kwargs_list.append(f"**{a.kwarg.arg}")

        decorators = [_annot_to_str(d) or "" for d in node.decorator_list]
        docstring = ast.get_docstring(node, clean=True)

        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, COMPLEXITY_NODES):
                complexity += 1

        info = FunctionInfo(
            qualname=f"{self.module}.{qual}",
            name=node.name,
            module=self.module,
            file=self.file,
            lineno=node.lineno,
            end_lineno=getattr(node, "end_lineno", node.lineno),
            args=args_list,
            kwargs=kwargs_list,
            annotations=annotations,
            returns=_annot_to_str(node.returns),
            decorators=decorators,
            docstring=_truncate(docstring),
            is_async=is_async,
            is_method=bool(self._class_stack),
            complexity=complexity,
            num_params=len(args_list) + len(kwargs_list),
            signature=_extract_signature(node),
        )

        self.functions.append(info)
        self._function_stack.append(node.name)
        for child in node.body:
            self.visit(child)
        self._function_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._handle_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._handle_function(node, is_async=True)

    # ---------- variáveis globais e constantes ----------

    def visit_Assign(self, node: ast.Assign) -> None:
        # Só capturamos assignments no nível do módulo (fora de funções)
        if not self._function_stack and not self._class_stack:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    is_const = name.isupper()
                    value_repr = _safe_repr(node.value)
                    self.globals.append(
                        GlobalVariable(
                            qualname=f"{self.module}.{name}",
                            name=name,
                            module=self.module,
                            file=self.file,
                            lineno=node.lineno,
                            value_repr=value_repr,
                            is_constant=is_const,
                        )
                    )
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if not self._function_stack and not self._class_stack:
            if isinstance(node.target, ast.Name):
                name = node.target.id
                self.globals.append(
                    GlobalVariable(
                        qualname=f"{self.module}.{name}",
                        name=name,
                        module=self.module,
                        file=self.file,
                        lineno=node.lineno,
                        value_repr=_safe_repr(node.value) if node.value else None,
                        is_constant=name.isupper(),
                        annotation=_annot_to_str(node.annotation),
                    )
                )
        self.generic_visit(node)

    # ---------- chamadas ----------

    def visit_Call(self, node: ast.Call) -> None:
        caller = self._current_caller()
        if caller:
            callee_repr = self._describe_call(node)
            if callee_repr and callee_repr.split(".")[0] not in NON_CALL_NAMES:
                is_method = "." in callee_repr
                edge = CallEdge(
                    caller=caller,
                    callee=callee_repr,
                    lineno=node.lineno,
                    is_method=is_method,
                    raw=_safe_repr(node.func),
                )
                self.calls.append(edge)
                # registra também no FunctionInfo do caller
                for f in self.functions:
                    if f.qualname == caller:
                        f.calls.append(callee_repr)
                        break
        self.generic_visit(node)

    def _describe_call(self, node: ast.Call) -> Optional[str]:
        """Retorna 'obj.metodo' ou 'funcao' ou 'modulo.funcao'."""
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            parts: List[str] = [func.attr]
            cur = func.value
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                parts.append(cur.id)
            return ".".join(reversed(parts))
        return None


# =============================================================================
# PARSER — wrappers públicos
# =============================================================================


def parse_source(
    source: str, module: str, file_path: str
) -> Tuple[
    List[ImportInfo],
    List[FunctionInfo],
    List[ClassInfo],
    List[GlobalVariable],
    List[CallEdge],
    Optional[str],
]:
    """Faz o parse de um código-fonte e retorna todas as estruturas extraídas."""
    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as e:
        logger.warning(f"SyntaxError em {file_path}: {e}")
        return [], [], [], [], [], None

    ex = _ASTExtractor(module_name=module, file_path=file_path)
    ex.visit(tree)
    return (
        ex.imports,
        ex.functions,
        ex.classes,
        ex.globals,
        ex.calls,
        ex.docstring,
    )


# =============================================================================
# RESOLUÇÃO DE NOMES E IMPORTS
# =============================================================================


class NameResolver:
    """
    Resolve imports relativos e nomes de chamadas para o grafo de chamadas final.
    Não é 100% um type-checker — apenas heurística de alta cobertura.
    """

    def __init__(self, module_to_file: Dict[str, str]):
        self.module_to_file = module_to_file

    def resolve_import_module(
        self, imp: ImportInfo, current_module: str
    ) -> Optional[str]:
        """Resolve o módulo alvo de uma importação."""
        if imp.is_relative:
            base = current_module.rsplit(".", imp.level)[0] if imp.level else current_module
            if imp.module:
                return f"{base}.{imp.module}" if base else imp.module
            return base or None
        return imp.module or None

    def resolve_call(
        self,
        callee_raw: str,
        current_module: str,
        file_imports: List[ImportInfo],
        all_modules: Set[str],
        all_functions_by_name: Dict[str, List[str]],
    ) -> Tuple[Optional[str], bool]:
        """
        Tenta resolver uma chamada para o qualname real.
        Retorna (qualname_resolvido, é_chamada_interna).
        """
        parts = callee_raw.split(".")
        head = parts[0]

        # 1) chamada a método / atributo direto: pode ser self.metodo()
        if len(parts) >= 2 and parts[1] in ("metodo",) or len(parts) >= 2:
            # tentativa: módulo_atual.Classe.metodo
            for imp in file_imports:
                # ex: from module import Class -> Class.method()
                for orig in imp.names:
                    if orig == head:
                        target_mod = self.resolve_import_module(imp, current_module)
                        if target_mod:
                            candidate = f"{target_mod}.{'.'.join(parts[1:])}"
                            if candidate in all_modules or True:
                                # validar via lookup de função por qualname
                                for qn in all_functions_by_name.get(parts[-1], []):
                                    if qn == candidate:
                                        return candidate, False
            # fallback: módulo_atual.<resto>
            local_candidate = f"{current_module}.{'.'.join(parts[1:])}"
            for qn in all_functions_by_name.get(parts[-1], []):
                if qn == local_candidate:
                    return local_candidate, True

        # 2) chamada simples: funcao() — tentar resolver dentro do módulo
        if len(parts) == 1:
            local = f"{current_module}.{callee_raw}"
            if callee_raw in all_functions_by_name:
                candidates = all_functions_by_name[callee_raw]
                if local in candidates:
                    return local, True
                return candidates[0], False

        # 3) chamada qualificada: modulo.funcao()
        if len(parts) >= 2:
            head_mod = parts[0]
            for imp in file_imports:
                local_name = imp.alias or (imp.names[0] if imp.names else imp.module.split(".")[-1])
                if local_name == head_mod:
                    target_mod = self.resolve_import_module(imp, current_module)
                    if target_mod:
                        candidate = f"{target_mod}.{'.'.join(parts[1:])}"
                        return candidate, False

        # fallback: não resolvido
        return None, False


# =============================================================================
# ARCHITECTURE INDEXER
# =============================================================================


class ArchitectureIndexer:
    """
    Serviço permanente de indexação arquitetural.

    Métodos principais:
        build_index()      — reindexa o projeto inteiro (incremental por hash).
        refresh()          — alias de build_index (revalida hashes).
        update_file(path)  — reindexar apenas um arquivo.
        remove_file(path)  — remover da indexação.
        save() / load()    — persistência JSON.
        search(...)        — buscas inteligentes.
        find_*(...)        — wrappers específicos.
        get_stats()        — estatísticas agregadas.
        export_graphs()    — gera arquivos de grafo/report.
    """

    _singleton: Optional["ArchitectureIndexer"] = None
    _singleton_lock = threading.Lock()

    # ------------------- construção -------------------

    def __init__(self, root: str | Path, snapshot_dir: Optional[str | Path] = None):
        self.root = Path(root).resolve()
        self.snapshot_dir = Path(snapshot_dir).resolve() if snapshot_dir else self.root
        self.snapshot_path = self.snapshot_dir / SNAPSHOT_FILE

        # Bancos internos
        self.files: Dict[str, FileInfo] = {}          # path -> FileInfo
        self.functions: Dict[str, FunctionInfo] = {}  # qualname -> FunctionInfo
        self.classes: Dict[str, ClassInfo] = {}       # qualname -> ClassInfo
        self.globals: Dict[str, GlobalVariable] = {}  # qualname -> GlobalVariable
        self.dependencies: List[DependencyEdge] = []  # lista de arestas
        self.call_graph: Dict[str, List[str]] = defaultdict(list)
        self.reverse_call_graph: Dict[str, List[str]] = defaultdict(list)
        self.statistics: Dict[str, Any] = {}

        # Índices auxiliares (recomputados em _rebuild_indexes)
        self._module_to_file: Dict[str, str] = {}
        self._functions_by_name: Dict[str, List[str]] = defaultdict(list)
        self._classes_by_name: Dict[str, List[str]] = defaultdict(list)

        self._lock = threading.RLock()
        self._last_build: float = 0.0

    # ------------------- singleton -------------------

    @classmethod
    def singleton(cls, root: Optional[str | Path] = None) -> "ArchitectureIndexer":
        with cls._singleton_lock:
            if cls._singleton is None:
                if root is None:
                    root = os.environ.get("BRAINNET_ROOT", os.getcwd())
                cls._singleton = ArchitectureIndexer(root)
            return cls._singleton

    # ------------------- varredura de arquivos -------------------

    def _should_ignore_dir(self, name: str) -> bool:
        return name in DEFAULT_IGNORE_DIRS or name.startswith(".")

    def _should_ignore_file(self, path: Path) -> bool:
        if path.name in DEFAULT_IGNORE_FILES:
            return True
        if path.suffix.lower() in IGNORE_EXTENSIONS:
            return True
        return False

    def _iter_python_files(self) -> Iterable[Path]:
        for dirpath, dirnames, filenames in os.walk(self.root):
            # poda diretórios ignorados in-place
            dirnames[:] = [d for d in dirnames if not self._should_ignore_dir(d)]
            for fname in filenames:
                if not fname.endswith(".py"):
                    continue
                p = Path(dirpath) / fname
                if self._should_ignore_file(p):
                    continue
                yield p

    # ------------------- parse de um arquivo -------------------

    def _index_file(self, path: Path) -> Optional[FileInfo]:
        try:
            stat = path.stat()
            sha = _sha256_file(path)
            module = _path_to_module(self.root, path)

            with open(path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()

            imports, functions, classes, globals_, calls, docstring = parse_source(
                source, module=module, file_path=str(path)
            )

            file_info = FileInfo(
                path=str(path),
                module=module,
                sha256=sha,
                size=stat.st_size,
                mtime=stat.st_mtime,
                imports=imports,
                classes=[c.qualname for c in classes],
                functions=[f.qualname for f in functions],
                globals=[g.qualname for g in globals_],
                constants=[g.qualname for g in globals_ if g.is_constant],
                docstring=_truncate(docstring),
                line_count=source.count("\n") + 1,
                call_edges=calls,
                dependencies=sorted(
                    {imp.module for imp in imports if imp.module}
                ),
                exports=[f.name for f in functions],
            )

            # Atualiza bancos
            with self._lock:
                self.files[file_info.path] = file_info

                # Limpa entradas antigas deste arquivo
                for qn in list(self.functions.keys()):
                    if self.functions[qn].file == file_info.path:
                        del self.functions[qn]
                for qn in list(self.classes.keys()):
                    if self.classes[qn].file == file_info.path:
                        del self.classes[qn]
                for qn in list(self.globals.keys()):
                    if self.globals[qn].file == file_info.path:
                        del self.globals[qn]

                for f in functions:
                    self.functions[f.qualname] = f
                for c in classes:
                    self.classes[c.qualname] = c
                for g in globals_:
                    self.globals[g.qualname] = g

            return file_info

        except Exception as e:
            logger.error(f"Erro indexando {path}: {e}\n{traceback.format_exc()}")
            return None

    # ------------------- build / refresh -------------------

    def build_index(self, max_workers: int = 8, force: bool = False) -> Dict[str, Any]:
        """
        Reindexa o projeto inteiro.
        Se force=False, usa hash para pular arquivos não alterados.
        """
        start = time.time()
        with self._lock:
            seen_paths: Set[str] = set()
            to_parse: List[Path] = []

            for path in self._iter_python_files():
                spath = str(path)
                seen_paths.add(spath)
                existing = self.files.get(spath)
                if existing is not None and not force:
                    # checagem rápida por mtime
                    try:
                        if abs(path.stat().st_mtime - existing.mtime) < 1e-6:
                            continue
                    except OSError:
                        continue
                to_parse.append(path)

            # remove arquivos que sumiram
            removed = [p for p in self.files.keys() if p not in seen_paths]
            for p in removed:
                self._remove_file_internal(p)

            # parse paralelo dos arquivos alterados/novos
            parsed_count = 0
            if to_parse:
                with ThreadPoolExecutor(max_workers=max_workers) as pool:
                    futures = {pool.submit(self._index_file, p): p for p in to_parse}
                    for fut in as_completed(futures):
                        try:
                            info = fut.result()
                            if info is not None:
                                parsed_count += 1
                        except Exception as e:
                            logger.error(f"Falha no worker: {e}")

        self._rebuild_indexes()
        self._recompute_statistics()
        self._last_build = time.time()

        elapsed = round(time.time() - start, 3)
        logger.info(
            f"build_index: {parsed_count} arquivos parseados, "
            f"{len(removed)} removidos, {len(self.files)} total em {elapsed}s"
        )
        return {
            "parsed": parsed_count,
            "removed": len(removed),
            "total": len(self.files),
            "elapsed_seconds": elapsed,
        }

    def refresh(self, max_workers: int = 8) -> Dict[str, Any]:
        """Revalida hashes e reindexar somente o que mudou."""
        return self.build_index(max_workers=max_workers, force=False)

    # ------------------- update / remove -------------------

    def update_file(self, path: str | Path) -> Optional[FileInfo]:
        p = Path(path)
        if not p.is_absolute():
            p = self.root / p
        if not p.exists():
            self.remove_file(p)
            return None
        info = self._index_file(p)
        self._rebuild_indexes()
        self._recompute_statistics()
        return info

    def remove_file(self, path: str | Path) -> None:
        p = Path(path)
        if not p.is_absolute():
            p = self.root / p
        self._remove_file_internal(str(p))
        self._rebuild_indexes()
        self._recompute_statistics()

    def _remove_file_internal(self, spath: str) -> None:
        with self._lock:
            self.files.pop(spath, None)
            for qn in list(self.functions.keys()):
                if self.functions[qn].file == spath:
                    del self.functions[qn]
            for qn in list(self.classes.keys()):
                if self.classes[qn].file == spath:
                    del self.classes[qn]
            for qn in list(self.globals.keys()):
                if self.globals[qn].file == spath:
                    del self.globals[qn]

    # ------------------- reconstrução de índices -------------------

    def _rebuild_indexes(self) -> None:
        """Reconstrói call_graph, reverse_call_graph, dependencies e índices."""
        with self._lock:
            self._module_to_file = {fi.module: fi.path for fi in self.files.values()}

            self._functions_by_name = defaultdict(list)
            for qn in self.functions:
                self._functions_by_name[self.functions[qn].name].append(qn)

            self._classes_by_name = defaultdict(list)
            for qn in self.classes:
                self._classes_by_name[self.classes[qn].name].append(qn)

            # --- dependências entre módulos ---
            self.dependencies = []
            all_modules = set(self._module_to_file.keys())
            resolver = NameResolver(self._module_to_file)

            for fi in self.files.values():
                for imp in fi.imports:
                    target = resolver.resolve_import_module(imp, fi.module)
                    if target:
                        self.dependencies.append(
                            DependencyEdge(
                                source_module=fi.module,
                                target_module=target,
                                kind="from_import" if imp.names else "import",
                                lineno=imp.lineno,
                            )
                        )

            # --- call graph ---
            self.call_graph = defaultdict(list)
            self.reverse_call_graph = defaultdict(list)

            for fi in self.files.values():
                for edge in fi.call_edges:
                    resolved, _internal = resolver.resolve_call(
                        edge.callee,
                        current_module=fi.module,
                        file_imports=fi.imports,
                        all_modules=all_modules,
                        all_functions_by_name=self._functions_by_name,
                    )
                    callee_final = resolved or f"{fi.module}.{edge.callee}"
                    if callee_final not in self.call_graph[edge.caller]:
                        self.call_graph[edge.caller].append(callee_final)
                    if edge.caller not in self.reverse_call_graph[callee_final]:
                        self.reverse_call_graph[callee_final].append(edge.caller)

    # ------------------- estatísticas -------------------

    def _recompute_statistics(self) -> None:
        with self._lock:
            num_edges = sum(len(v) for v in self.call_graph.values())
            dep_edges = len(self.dependencies)

            # arquivos órfãos = sem dependências de entrada/saída
            all_mods = set(self._module_to_file.keys())
            dep_out = {d.source_module for d in self.dependencies}
            dep_in = {d.target_module for d in self.dependencies}
            orphan_files = sorted(all_mods - dep_out - dep_in)

            # funções órfãs = sem chamadores e que não são __init__/main
            orphan_funcs = []
            for qn, f in self.functions.items():
                if f.name.startswith("__"):
                    continue
                if not self.reverse_call_graph.get(qn):
                    orphan_funcs.append(qn)

            # componentes conectados (grafo não-direcionado)
            comps = self._count_components()

            # ciclos
            cycles = self._detect_cycles()

            self.statistics = {
                "files": len(self.files),
                "classes": len(self.classes),
                "functions": len(self.functions),
                "globals": len(self.globals),
                "imports": sum(len(fi.imports) for fi in self.files.values()),
                "call_edges": num_edges,
                "dependency_edges": dep_edges,
                "components": comps,
                "cycles": len(cycles),
                "cycle_examples": cycles[:5],
                "orphan_files": len(orphan_files),
                "orphan_file_list": orphan_files[:30],
                "orphan_functions": len(orphan_funcs),
                "orphan_function_list": orphan_funcs[:50],
                "last_build": datetime.fromtimestamp(
                    self._last_build or time.time(), tz=timezone.utc
                ).isoformat(),
            }

    def _count_components(self) -> int:
        """Componentes fracamente conectados do grafo de dependências."""
        adj: Dict[str, Set[str]] = defaultdict(set)
        for d in self.dependencies:
            adj[d.source_module].add(d.target_module)
            adj[d.target_module].add(d.source_module)
        seen: Set[str] = set()
        comps = 0
        for node in set(adj.keys()) | set(self._module_to_file.keys()):
            if node in seen:
                continue
            comps += 1
            q = deque([node])
            seen.add(node)
            while q:
                cur = q.popleft()
                for nb in adj.get(cur, ()):
                    if nb not in seen:
                        seen.add(nb)
                        q.append(nb)
        return comps

    def _detect_cycles(self) -> List[List[str]]:
        """Detecta ciclos no grafo de dependências (limite de 100 ciclos)."""
        adj: Dict[str, List[str]] = defaultdict(list)
        for d in self.dependencies:
            adj[d.source_module].append(d.target_module)

        cycles: List[List[str]] = []
        visiting: Set[str] = set()
        visited: Set[str] = set()
        stack: List[str] = []

        def dfs(node: str) -> None:
            if len(cycles) >= 100:
                return
            if node in visiting:
                try:
                    idx = stack.index(node)
                    cycles.append(stack[idx:] + [node])
                except ValueError:
                    pass
                return
            if node in visited:
                return
            visiting.add(node)
            stack.append(node)
            for nb in adj.get(node, ()):
                dfs(nb)
            stack.pop()
            visiting.discard(node)
            visited.add(node)

        for node in list(adj.keys()):
            if node not in visited:
                dfs(node)
        return cycles

    # ------------------- persistência -------------------

    def _snapshot_hash(self) -> str:
        h = hashlib.sha256()
        h.update(VERSION.encode())
        for spath in sorted(self.files.keys()):
            h.update(spath.encode())
            h.update(self.files[spath].sha256.encode())
        return h.hexdigest()

    def save(self, path: Optional[str | Path] = None) -> Path:
        target = Path(path) if path else self.snapshot_path
        target.parent.mkdir(parents=True, exist_ok=True)

        snap = ArchitectureSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            version=VERSION,
            hash=self._snapshot_hash(),
            root=str(self.root),
            statistics=self.statistics,
            files={p: fi.to_dict() for p, fi in self.files.items()},
            functions={qn: f.to_dict() for qn, f in self.functions.items()},
            classes={qn: c.to_dict() for qn, c in self.classes.items()},
            globals={qn: g.to_dict() for qn, g in self.globals.items()},
            dependencies=[d.to_dict() for d in self.dependencies],
            call_graph=dict(self.call_graph),
            reverse_call_graph=dict(self.reverse_call_graph),
        )
        with open(target, "w", encoding="utf-8") as f:
            json.dump(snap.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Snapshot salvo em {target}")
        return target

    def load(self, path: Optional[str | Path] = None) -> bool:
        target = Path(path) if path else self.snapshot_path
        if not target.exists():
            logger.warning(f"Snapshot não encontrado: {target}")
            return False
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.files = {}
            for p, fd in data.get("files", {}).items():
                fi = FileInfo(**{k: v for k, v in fd.items() if k != "imports"
                                 and k != "call_edges"})
                fi.imports = [ImportInfo(**i) for i in fd.get("imports", [])]
                fi.call_edges = [CallEdge(**c) for c in fd.get("call_edges", [])]
                self.files[p] = fi

            self.functions = {
                qn: FunctionInfo(**fd) for qn, fd in data.get("functions", {}).items()
            }
            self.classes = {
                qn: ClassInfo(**cd) for qn, cd in data.get("classes", {}).items()
            }
            self.globals = {
                qn: GlobalVariable(**gd) for qn, gd in data.get("globals", {}).items()
            }
            self.dependencies = [
                DependencyEdge(**d) for d in data.get("dependencies", [])
            ]
            self.call_graph = defaultdict(
                list, data.get("call_graph", {})
            )
            self.reverse_call_graph = defaultdict(
                list, data.get("reverse_call_graph", {})
            )
            self.statistics = data.get("statistics", {})
            self._last_build = time.time()
            self._rebuild_indexes()
            logger.info(f"Snapshot carregado: {len(self.files)} arquivos")
            return True
        except Exception as e:
            logger.error(f"Falha carregando snapshot: {e}\n{traceback.format_exc()}")
            return False

    def clear(self) -> None:
        with self._lock:
            self.files.clear()
            self.functions.clear()
            self.classes.clear()
            self.globals.clear()
            self.dependencies.clear()
            self.call_graph.clear()
            self.reverse_call_graph.clear()
            self.statistics = {}
            self._module_to_file.clear()
            self._functions_by_name.clear()
            self._classes_by_name.clear()

    # ------------------- getters -------------------

    def get_file(self, path_or_module: str) -> Optional[FileInfo]:
        if path_or_module in self.files:
            return self.files[path_or_module]
        if path_or_module in self._module_to_file:
            return self.files.get(self._module_to_file[path_or_module])
        return None

    def get_function(self, qualname_or_name: str) -> Optional[FunctionInfo]:
        if qualname_or_name in self.functions:
            return self.functions[qualname_or_name]
        for qn, f in self.functions.items():
            if f.name == qualname_or_name:
                return f
        return None

    def get_class(self, qualname_or_name: str) -> Optional[ClassInfo]:
        if qualname_or_name in self.classes:
            return self.classes[qualname_or_name]
        for qn, c in self.classes.items():
            if c.name == qualname_or_name:
                return c
        return None

    # ------------------- dependências e call graph -------------------

    def get_dependencies(self, module: str) -> List[str]:
        return sorted({
            d.target_module for d in self.dependencies if d.source_module == module
        })

    def find_dependencies(self, module: str) -> List[str]:
        return self.get_dependencies(module)

    def find_dependents(self, module: str) -> List[str]:
        return sorted({
            d.source_module for d in self.dependencies if d.target_module == module
        })

    def get_callers(self, function_qualname: str) -> List[str]:
        return list(self.reverse_call_graph.get(function_qualname, []))

    def get_callees(self, function_qualname: str) -> List[str]:
        return list(self.call_graph.get(function_qualname, []))

    def find_callers(self, function_name: str) -> List[str]:
        target = self.find_function(function_name)
        if not target:
            return []
        return self.get_callers(target.qualname)

    def find_callees(self, function_name: str) -> List[str]:
        target = self.find_function(function_name)
        if not target:
            return []
        return self.get_callees(target.qualname)

    def find_files_using(self, symbol: str) -> List[str]:
        """Retorna arquivos que importam ou chamam o símbolo."""
        results: List[str] = []
        # arquivos que importam
        for fi in self.files.values():
            for imp in fi.imports:
                if symbol in imp.names or imp.module == symbol or imp.module.endswith(f".{symbol}"):
                    results.append(fi.path)
                    break
        # arquivos que contêm chamadas
        for qn, callers in self.reverse_call_graph.items():
            if qn.split(".")[-1] == symbol or qn == symbol:
                for c in callers:
                    f = self.functions.get(c)
                    if f and f.file not in results:
                        results.append(f.file)
        return sorted(set(results))

    # =================================================================
    # CAMADA DE CONSULTA INTELIGENTE (PARTE 3)
    # =================================================================

    def _rank_results(
        self,
        results: List[Dict[str, Any]],
        reference_module: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Aplica ranking: mesmo módulo > mesmo pacote > frequência > distância."""
        if reference_module is None:
            return results

        ref_pkg = reference_module.rsplit(".", 1)[0] if "." in reference_module else ""

        def score(r: Dict[str, Any]) -> float:
            s = 0.0
            mod = r.get("module", "")
            if mod == reference_module:
                s += 100.0
            elif ref_pkg and mod.startswith(ref_pkg + "."):
                s += 50.0
            s += r.get("frequency", 0) * 0.5
            return s

        return sorted(results, key=score, reverse=True)

    def search_symbol(
        self,
        query: str,
        kind: Optional[str] = None,
        reference_module: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Busca por símbolo (função/classe/global/módulo).
        kind: 'function' | 'class' | 'global' | 'module' | None
        """
        q = query.lower().strip()
        results: List[Dict[str, Any]] = []

        if kind in (None, "function"):
            for qn, f in self.functions.items():
                if q.lower() in qn.lower() or q.lower() in f.name.lower():
                    results.append({
                        "kind": "function",
                        "qualname": qn,
                        "module": f.module,
                        "file": f.file,
                        "lineno": f.lineno,
                        "signature": f.signature,
                        "docstring": f.docstring,
                        "frequency": len(self.reverse_call_graph.get(qn, [])),
                    })

        if kind in (None, "class"):
            for qn, c in self.classes.items():
                if q.lower() in qn.lower() or q.lower() in c.name.lower():
                    results.append({
                        "kind": "class",
                        "qualname": qn,
                        "module": c.module,
                        "file": c.file,
                        "lineno": c.lineno,
                        "bases": c.bases,
                        "docstring": c.docstring,
                        "frequency": 0,
                    })

        if kind in (None, "global"):
            for qn, g in self.globals.items():
                if q.lower() in qn.lower() or q.lower() in g.name.lower():
                    results.append({
                        "kind": "global",
                        "qualname": qn,
                        "module": g.module,
                        "file": g.file,
                        "lineno": g.lineno,
                        "value": g.value_repr,
                        "frequency": 0,
                    })

        if kind in (None, "module"):
            for mod, path in self._module_to_file.items():
                if q in mod.lower():
                    results.append({
                        "kind": "module",
                        "module": mod,
                        "file": path,
                        "frequency": 0,
                    })

        results = self._rank_results(results, reference_module)
        return results[:limit]

    def search_text(
        self, query: str, reference_module: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Busca textual bruta em docstrings, nomes e assinaturas."""
        q = query.lower().strip()
        hits: List[Dict[str, Any]] = []
        for qn, f in self.functions.items():
            hay = " ".join(filter(None, [qn, f.name, f.signature, f.docstring]))
            if q in hay.lower():
                hits.append({
                    "kind": "function",
                    "qualname": qn,
                    "module": f.module,
                    "file": f.file,
                    "lineno": f.lineno,
                    "snippet": _truncate(hay, 200),
                    "frequency": len(self.reverse_call_graph.get(qn, [])),
                })
        for qn, c in self.classes.items():
            hay = " ".join(filter(None, [qn, c.name, c.docstring, *c.bases]))
            if q in hay.lower():
                hits.append({
                    "kind": "class",
                    "qualname": qn,
                    "module": c.module,
                    "file": c.file,
                    "lineno": c.lineno,
                    "snippet": _truncate(hay, 200),
                    "frequency": 0,
                })
        hits = self._rank_results(hits, reference_module)
        return hits[:limit]

    def search_import(self, module_name: str) -> List[Dict[str, Any]]:
        """Retorna arquivos que importam o módulo informado."""
        q = module_name.strip()
        hits: List[Dict[str, Any]] = []
        for fi in self.files.values():
            for imp in fi.imports:
                if imp.module == q or q in imp.names or imp.module.startswith(q + "."):
                    hits.append({
                        "file": fi.path,
                        "module": fi.module,
                        "lineno": imp.lineno,
                        "raw": imp.raw,
                    })
                    break
        return hits

    # --- wrappers requisitados ---

    def search_function(self, name: str) -> List[Dict[str, Any]]:
        return self.search_symbol(name, kind="function")

    def search_class(self, name: str) -> List[Dict[str, Any]]:
        return self.search_symbol(name, kind="class")

    def search_module(self, name: str) -> List[Dict[str, Any]]:
        return self.search_symbol(name, kind="module")

    def find_function(self, name: str) -> Optional[FunctionInfo]:
        return self.get_function(name)

    def find_class(self, name: str) -> Optional[ClassInfo]:
        return self.get_class(name)

    def find_module(self, name: str) -> Optional[FileInfo]:
        return self.get_file(name)

    def find_where_to_change(
        self, description: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        API de alto nível para MissionExecutor.
        Recebe uma descrição ('onde alterar DeepThink?') e retorna arquivos
        candidatos com score de confiança.

        Estratégia:
            1. extrai tokens significativos da descrição;
            2. busca símbolos e texto;
            3. agrupa por arquivo, soma scores, ranqueia.
        """
        import re
        tokens = [
            t for t in re.split(r"\W+", description.lower())
            if t and len(t) > 2 and t not in {"onde", "para", "the", "and", "que", "com"}
        ]
        scores: Dict[str, float] = defaultdict(float)
        reasons: Dict[str, List[str]] = defaultdict(list)

        for tok in tokens:
            for r in self.search_text(tok, limit=30):
                scores[r["file"]] += 10 + r.get("frequency", 0)
                reasons[r["file"]].append(f"text:{tok}")
            for r in self.search_symbol(tok, limit=30):
                if "file" in r:
                    scores[r["file"]] += 20
                    reasons[r["file"]].append(f"symbol:{r['qualname']}")

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        max_score = ranked[0][1] if ranked else 1.0
        return [
            {
                "file": fpath,
                "score": round(score / max_score, 3),
                "reasons": sorted(set(reasons[fpath]))[:10],
                "module": self.files[fpath].module if fpath in self.files else None,
            }
            for fpath, score in ranked
        ]

    # ------------------- export de grafos / relatórios -------------------

    def export_graphs(self, out_dir: Optional[str | Path] = None) -> Dict[str, str]:
        out = Path(out_dir) if out_dir else self.snapshot_dir
        out.mkdir(parents=True, exist_ok=True)

        # architecture_graph.json (visão consolidada)
        arch_path = out / ARCH_GRAPH_FILE
        arch_data = {
            "version": VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "root": str(self.root),
            "statistics": self.statistics,
            "nodes": [
                {
                    "id": fi.module,
                    "path": fi.path,
                    "line_count": fi.line_count,
                    "classes": len(fi.classes),
                    "functions": len(fi.functions),
                }
                for fi in self.files.values()
            ],
            "edges": [d.to_dict() for d in self.dependencies],
        }
        arch_path.write_text(
            json.dumps(arch_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # dependency_graph.json
        dep_path = out / DEP_GRAPH_FILE
        dep_graph = {
            "nodes": list(self._module_to_file.keys()),
            "edges": [d.to_dict() for d in self.dependencies],
        }
        dep_path.write_text(
            json.dumps(dep_graph, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # call_graph.json
        call_path = out / CALL_GRAPH_FILE
        call_data = {
            "call_graph": {k: list(v) for k, v in self.call_graph.items()},
            "reverse_call_graph": {
                k: list(v) for k, v in self.reverse_call_graph.items()
            },
        }
        call_path.write_text(
            json.dumps(call_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # architecture_report.md
        report_path = out / REPORT_FILE
        report_path.write_text(self._build_report(), encoding="utf-8")

        logger.info(f"Grafos exportados em {out}")
        return {
            "architecture": str(arch_path),
            "dependencies": str(dep_path),
            "calls": str(call_path),
            "report": str(report_path),
        }

    def _build_report(self) -> str:
        s = self.statistics
        lines: List[str] = []
        lines.append("# Architecture Report — Brainnet")
        lines.append("")
        lines.append(f"- **Gerado em:** {datetime.now(timezone.utc).isoformat()}")
        lines.append(f"- **Root:** `{self.root}`")
        lines.append(f"- **Versão:** {VERSION}")
        lines.append("")
        lines.append("## Estatísticas")
        lines.append("")
        lines.append(f"- Arquivos: **{s.get('files', 0)}**")
        lines.append(f"- Classes: **{s.get('classes', 0)}**")
        lines.append(f"- Funções: **{s.get('functions', 0)}**")
        lines.append(f"- Globals: **{s.get('globals', 0)}**")
        lines.append(f"- Imports: **{s.get('imports', 0)}**")
        lines.append(f"- Arestas de chamada: **{s.get('call_edges', 0)}**")
        lines.append(f"- Arestas de dependência: **{s.get('dependency_edges', 0)}**")
        lines.append(f"- Componentes: **{s.get('components', 0)}**")
        lines.append(f"- Ciclos detectados: **{s.get('cycles', 0)}**")
        lines.append(f"- Arquivos órfãos: **{s.get('orphan_files', 0)}**")
        lines.append(f"- Funções órfãs: **{s.get('orphan_functions', 0)}**")
        lines.append("")

        if s.get("cycle_examples"):
            lines.append("## Ciclos (amostra)")
            for cyc in s["cycle_examples"]:
                lines.append(f"- {' → '.join(cyc)}")
            lines.append("")

        # Top 20 funções mais chamadas
        top = sorted(
            ((qn, len(callers)) for qn, callers in self.reverse_call_graph.items()),
            key=lambda kv: kv[1],
            reverse=True,
        )[:20]
        if top:
            lines.append("## Top 20 funções mais chamadas")
            for qn, cnt in top:
                lines.append(f"- `{qn}` — **{cnt}** chamadores")
            lines.append("")

        # Top 20 módulos com mais dependências
        dep_count: Dict[str, int] = defaultdict(int)
        for d in self.dependencies:
            dep_count[d.source_module] += 1
        top_mods = sorted(dep_count.items(), key=lambda kv: kv[1], reverse=True)[:20]
        if top_mods:
            lines.append("## Top 20 módulos com mais dependências")
            for mod, cnt in top_mods:
                lines.append(f"- `{mod}` — **{cnt}** dependências")
            lines.append("")

        return "\n".join(lines)

    # ------------------- watcher (reindexação automática) -------------------

    def watch(self, interval: float = 2.0, once: bool = False) -> None:
        """
        Monitora o diretório e reindexar apenas arquivos alterados.
        Bloqueia até Ctrl+C (ou uma passada se once=True).
        """
        seen_mtimes: Dict[str, float] = {}
        for path in self._iter_python_files():
            try:
                seen_mtimes[str(path)] = path.stat().st_mtime
            except OSError:
                pass

        logger.info(f"Watching {self.root} (interval={interval}s)")
        try:
            while True:
                changed: List[Path] = []
                current: Set[str] = set()
                for path in self._iter_python_files():
                    spath = str(path)
                    current.add(spath)
                    try:
                        mt = path.stat().st_mtime
                    except OSError:
                        continue
                    if spath not in seen_mtimes or abs(mt - seen_mtimes[spath]) > 1e-6:
                        changed.append(path)
                        seen_mtimes[spath] = mt
                # removidos
                for spath in list(seen_mtimes.keys()):
                    if spath not in current:
                        self.remove_file(spath)
                        del seen_mtimes[spath]

                if changed:
                    logger.info(f"Alterações detectadas: {len(changed)} arquivo(s)")
                    for p in changed:
                        self.update_file(p)
                    self.save()

                if once:
                    return
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("Watcher encerrado.")
            self.save()


# =============================================================================
# CLI
# =============================================================================


def _cli_build(args: argparse.Namespace) -> int:
    idx = ArchitectureIndexer(args.root)
    result = idx.build_index(max_workers=args.workers, force=args.force)
    idx.save()
    idx.export_graphs()
    print(json.dumps(result, indent=2))
    return 0


def _cli_refresh(args: argparse.Namespace) -> int:
    idx = ArchitectureIndexer(args.root)
    if not idx.load():
        print("Sem snapshot existente. Rodando --build primeiro...")
        return _cli_build(args)
    result = idx.refresh(max_workers=args.workers)
    idx.save()
    print(json.dumps(result, indent=2))
    return 0


def _cli_search(args: argparse.Namespace) -> int:
    idx = ArchitectureIndexer(args.root)
    if not idx.load():
        print("Sem snapshot. Execute --build primeiro.", file=sys.stderr)
        return 1
    results = idx.search_text(args.query, limit=args.limit)
    if not results:
        print(f"Nenhum resultado para: {args.query}")
        return 0
    for r in results:
        print(f"[{r['kind']:8}] {r['qualname']}")
        print(f"           → {r['file']}:{r['lineno']}")
        if r.get("snippet"):
            print(f"           {r['snippet']}")
        print()
    return 0


def _cli_stats(args: argparse.Namespace) -> int:
    idx = ArchitectureIndexer(args.root)
    if not idx.load():
        print("Sem snapshot. Execute --build primeiro.", file=sys.stderr)
        return 1
    print(json.dumps(idx.statistics, indent=2, ensure_ascii=False))
    return 0


def _cli_graph(args: argparse.Namespace) -> int:
    idx = ArchitectureIndexer(args.root)
    if not idx.load():
        print("Sem snapshot. Execute --build primeiro.", file=sys.stderr)
        return 1
    paths = idx.export_graphs(args.out)
    print(json.dumps(paths, indent=2))
    return 0


def _cli_watch(args: argparse.Namespace) -> int:
    idx = ArchitectureIndexer(args.root)
    if args.rebuild and not idx.load():
        idx.build_index()
        idx.save()
    idx.watch(interval=args.interval, once=args.once)
    return 0


def _cli_where(args: argparse.Namespace) -> int:
    idx = ArchitectureIndexer(args.root)
    if not idx.load():
        print("Sem snapshot. Execute --build primeiro.", file=sys.stderr)
        return 1
    results = idx.find_where_to_change(args.query, limit=args.limit)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="ArchitectureIndexer — Mapa Cerebral da Brainnet"
    )
    p.add_argument("--root", default=os.environ.get("BRAINNET_ROOT", os.getcwd()),
                   help="Raiz do projeto (default: cwd)")
    p.add_argument("--workers", type=int, default=8,
                   help="Threads de parsing paralelo")
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--build", action="store_true", help="Reindexar tudo")
    group.add_argument("--refresh", action="store_true", help="Reindexar só alterados")
    group.add_argument("--search", metavar="QUERY", help="Busca textual")
    group.add_argument("--stats", action="store_true", help="Mostrar estatísticas")
    group.add_argument("--graph", action="store_true", help="Exportar grafos e report")
    group.add_argument("--watch", action="store_true", help="Monitorar mudanças")
    group.add_argument("--where", metavar="DESC",
                       help="'Onde alterar X?' — API de alto nível para MissionExecutor")

    p.add_argument("--force", action="store_true",
                   help="Com --build: reparar tudo mesmo se hash igual")
    p.add_argument("--limit", type=int, default=20, help="Máx. resultados")
    p.add_argument("--out", default=None, help="Diretório de saída (--graph)")
    p.add_argument("--interval", type=float, default=2.0,
                   help="Intervalo em segundos (--watch)")
    p.add_argument("--once", action="store_true",
                   help="Com --watch: apenas uma passada")
    p.add_argument("--rebuild", action="store_true",
                   help="Com --watch: força build inicial se sem snapshot")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.build:
        return _cli_build(args)
    if args.refresh:
        return _cli_refresh(args)
    if args.search:
        return _cli_search(args)
    if args.stats:
        return _cli_stats(args)
    if args.graph:
        return _cli_graph(args)
    if args.watch:
        return _cli_watch(args)
    if args.where:
        return _cli_where(args)
    parser.print_help()
    return 1


# =============================================================================
# ENTRYPOINT
# =============================================================================

if __name__ == "__main__":
    sys.exit(main())