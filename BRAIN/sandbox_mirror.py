# ==============================================================================
# BRAINNET v7 - SISTEMA OPERACIONAL COGNITIVO
# MODULO: sandbox_mirror.py
# FUNCAO: Confinamento Seguro de Codigo Dinamico (AST Sanitizer + Win32 Job Objects).
# TAGS DE BUSCA:
#   - [BN_SANDBOX_CORE]    : Gerenciamento do Ambiente de Teste
#   - [BN_SANDBOX_AST]     : Inspecao Sintatica e Bloqueio de Comandos Perigosos
#   - [BN_SANDBOX_JOB]     : Limitador de Hardware Nativo Win32 (RAM e CPU)
#   - [BN_SANDBOX_RUNNER]  : Execucao Isolada e Kill-Switch de 5 segundos
#
# DEPENDENCIAS EXTERNAS:
#   - ast, subprocess, sys, tempfile (Bibliotecas padrao do Python).
#   - ctypes / wintypes (Integracao nativa com Kernel32 Job Objects).
# QUEM CHAMA ESTE MODULO:
#   - aios_master.py (quando a IA gera uma habilidade nova ou script de automacao).
# ==============================================================================

from __future__ import annotations

import ast
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Set, Tuple

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# [BN_SANDBOX_JOB] - Estruturas Win32 Job Object via ctypes puro (Zero Dependencias Externas)
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x0100

class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]

class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
        ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]

class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]

JobObjectExtendedLimitInformation = 9

kernel32.CreateJobObjectW.restype = wintypes.HANDLE
kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]

kernel32.SetInformationJobObject.restype = wintypes.BOOL
kernel32.SetInformationJobObject.argtypes = [
    wintypes.HANDLE,
    ctypes.c_int,
    ctypes.c_void_p,
    wintypes.DWORD,
]

kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]

kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


@dataclass(slots=True, frozen=True)
class SandboxReport:
    """Relatorio estruturado da execucao no Espelho."""
    status: str                 # 'PASSED', 'SECURITY_BLOCKED', 'TIMEOUT', 'RUNTIME_ERROR'
    output: str                 # Saida padrao (stdout)
    error_trace: str            # Rastro de erro se houver (stderr)
    execution_time_ms: float    # Tempo total gasto no teste
    details: str                # Justificativa estruturada


class ASTSecurityInspector(ast.NodeVisitor):
    """
    [BN_SANDBOX_AST]
    Inspeciona a arvore sintatica do codigo antes de autorizar a execucao.
    Bloqueia chamadas evasivas e imports de sistema nao autorizados.
    """

    BANNED_MODULES: Set[str] = {
        "socket", "winreg", "ctypes", "shutil", "subprocess",
        "msvcrt", "pty", "posix", "_winapi",
        "os", "sys", "pathlib", "importlib", "urllib", "requests",
        "httpx", "aiohttp", "http", "ftplib",
        "telnetlib", "smtplib", "pickle", "marshal",
        "shelve", "dbm", "sqlite3", "threading",
        "multiprocessing", "concurrent",
    }

    BANNED_FUNCTIONS: Set[str] = {
        "eval", "exec", "globals", "locals", "__import__", "compile",
        "open", "input", "breakpoint",
        "memoryview", "vars", "dir",
    }

    BANNED_ATTRS: Set[str] = {
        "__globals__", "__subclasses__", "__builtins__", "__class__",
        "__code__", "__closure__", "__dict__", "__mro__",
        "__bases__", "__getattribute__", "__setattr__", "__delattr__",
        "gi_frame", "gi_code", "cr_frame", "cr_code",
        "f_globals", "f_locals", "func_globals", "func_code",
    }

    def __init__(self) -> None:
        self.violations: List[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            base_mod = alias.name.split(".")[0]
            if base_mod in self.BANNED_MODULES:
                self.violations.append(f"Importacao proibida do modulo: '{alias.name}'")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            base_mod = node.module.split(".")[0]
            if base_mod in self.BANNED_MODULES:
                self.violations.append(f"Importacao proibida a partir de: '{node.module}'")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Detecta chamadas de funcoes perigosas
        if isinstance(node.func, ast.Name) and node.func.id in self.BANNED_FUNCTIONS:
            self.violations.append(f"Chamada de funcao perigosa proibida: '{node.func.id}()'")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # Detecta tentativas de introspeccao para quebrar a sandbox
        if node.attr in self.BANNED_ATTRS:
            self.violations.append(f"Acesso a atributo restrito proibido: '{node.attr}'")
        self.generic_visit(node)


class SandboxMirror:
    """
    [BN_SANDBOX_CORE]
    O Espelho: Executor e Validador de Codigo Dinamico em Confinamento Win32.
    """

    __slots__ = ("max_ram_bytes", "timeout_sec")

    def __init__(self, max_ram_mb: int = 256, timeout_sec: float = 5.0) -> None:
        self.max_ram_bytes = max_ram_mb * 1024 * 1024
        self.timeout_sec = timeout_sec

    def sanitize_code(self, code_str: str) -> Tuple[bool, List[str]]:
        """Verifica a integridade sintatica e a politica de seguranca via AST."""
        try:
            tree = ast.parse(code_str)
        except SyntaxError as e:
            return False, [f"Erro de sintaxe no codigo: linha {e.lineno} ({e.msg})"]

        inspector = ASTSecurityInspector()
        inspector.visit(tree)

        if inspector.violations:
            return False, inspector.violations
        return True, []

    def execute_in_sandbox(self, code_str: str) -> SandboxReport:
        """
        [BN_SANDBOX_RUNNER]
        Executa o codigo em um subprocesso encapsulado em um Job Object do Windows.
        Aplica limite de memoria de 256MB e encerramento forcado no tempo limite.
        """
        t0 = time.perf_counter_ns()

        # 1. Checagem Sintatica e de Seguranca
        is_safe, issues = self.sanitize_code(code_str)
        if not is_safe:
            elapsed = (time.perf_counter_ns() - t0) / 1_000_000
            return SandboxReport(
                status="SECURITY_BLOCKED",
                output="",
                error_trace="\n".join(issues),
                execution_time_ms=elapsed,
                details="Codigo rejeitado pela analise estatica AST."
            )

        # 2. Criacao do arquivo temporario isolado
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as temp_file:
            temp_path = temp_file.name
            temp_file.write(code_str)

        h_job = None
        try:
            # 3. Configuracao do Job Object com limite de 256MB e auto-kill ao fechar
            h_job = kernel32.CreateJobObjectW(None, None)
            if h_job:
                info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
                info.BasicLimitInformation.LimitFlags = (
                    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_PROCESS_MEMORY
                )
                info.ProcessMemoryLimit = self.max_ram_bytes
                kernel32.SetInformationJobObject(
                    h_job,
                    JobObjectExtendedLimitInformation,
                    ctypes.byref(info),
                    ctypes.sizeof(info)
                )

            # 4. Inicia o subprocesso em modo isolado (-I -S ignora configuracoes do usuario)
            cmd = [sys.executable, "-I", "-S", temp_path]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            # Conecta o processo ao Job Object do Windows
            if h_job and hasattr(proc, "_handle"):
                kernel32.AssignProcessToJobObject(h_job, int(proc._handle))

            try:
                stdout, stderr = proc.communicate(timeout=self.timeout_sec)
                elapsed = (time.perf_counter_ns() - t0) / 1_000_000

                if proc.returncode == 0:
                    return SandboxReport(
                        status="PASSED",
                        output=stdout.strip(),
                        error_trace="",
                        execution_time_ms=elapsed,
                        details="Execucao segura finalizada com sucesso."
                    )
                else:
                    return SandboxReport(
                        status="RUNTIME_ERROR",
                        output=stdout.strip(),
                        error_trace=stderr.strip(),
                        execution_time_ms=elapsed,
                        details=f"Falha de execucao (Codigo de saida: {proc.returncode})."
                    )

            except subprocess.TimeoutExpired:
                # Dispara o kill-switch imediatamente
                proc.kill()
                proc.communicate()
                elapsed = (time.perf_counter_ns() - t0) / 1_000_000
                return SandboxReport(
                    status="TIMEOUT",
                    output="",
                    error_trace=f"Tempo limite de {self.timeout_sec}s ultrapassado.",
                    execution_time_ms=elapsed,
                    details="Kill-switch acionado para evitar congelamento."
                )

        finally:
            # Limpeza do Job Object e do arquivo temporario
            if h_job:
                kernel32.CloseHandle(h_job)
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass