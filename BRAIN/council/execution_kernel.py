# =============================================================================
# council/execution_kernel.py — Infraestrutura de execução de Tasks
# =============================================================================

from __future__ import annotations

import asyncio
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from .provider_registry import ProviderRegistry

logger = logging.getLogger("Council.Kernel")

@dataclass
class Task:
    """A menor unidade de execução. Totalmente independente."""
    id: str
    provider: str                 # "chatgpt" | "deepseek" | "local_llm"
    role: str                     # "architect" | "implementer" | "reviewer" | "tester"
    prompt: str
    port_type: str = "chat"       # "chat" | "browser" | "test"
    timeout: float = 120.0
    retry: int = 0
    depends_on: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class TaskResult:
    task_id: str
    status: str                   # "success" | "failed" | "timeout"
    output: Any = None
    error: Optional[str] = None
    duration: float = 0.0
    artifacts: dict[str, Any] = field(default_factory=dict)

class ExecutionKernel:
    """
    Executa uma Task isolada, aplicando timeout, retry e telemetria.
    Não sabe o que é uma Missão, apenas o que é uma Task.
    """
    
    def __init__(self, registry: ProviderRegistry):
        self.registry = registry
        self.metrics: dict[str, Any] = {}

    async def execute_task(self, task: Task) -> TaskResult:
        start_time = time.time()
        attempts = 0
        last_error = None

        while attempts <= task.retry:
            try:
                logger.info(f"Kernel executando: {task.id} (Tentativa {attempts+1})")
                
                # Roteamento baseado no port_type
                if task.port_type == "chat":
                    if not self.registry.exists(task.provider):
                        raise ValueError(f"Provider não encontrado: {task.provider}")
                    port = self.registry.get(task.provider)
                    result = await asyncio.wait_for(
                        self._run_chat(port, task), 
                        timeout=task.timeout
                    )
                
                elif task.port_type == "test":
                    if not self.registry.exists("test"):
                        raise ValueError("TestRunnerPort não configurado")
                    port = self.registry.get("test")
                    result = await asyncio.wait_for(
                        port.run(task.prompt), # prompt = path do teste
                        timeout=task.timeout
                    )
                
                else:
                    raise ValueError(f"port_type desconhecido: {task.port_type}")

                duration = time.time() - start_time
                return TaskResult(
                    task_id=task.id, status="success", 
                    output=result, duration=duration
                )

            except asyncio.TimeoutError:
                last_error = f"Timeout após {task.timeout}s"
                logger.warning(f"{task.id} falhou: {last_error}")
            except Exception as e:
                last_error = str(e)
                logger.error(f"{task.id} erro: {last_error}")
            
            attempts += 1
            if attempts <= task.retry:
                await asyncio.sleep(2 ** attempts) # Backoff exponencial

        duration = time.time() - start_time
        return TaskResult(
            task_id=task.id, status="failed", 
            error=last_error, duration=duration
        )

    async def _run_chat(self, port: Any, task: Task) -> Any:
        """Wrapper para ChatPort, pois a interface pode variar."""
        # Assume que a porta tem send_prompt e wait_generation
        await port.send_prompt(task.prompt)
        await port.wait_generation(timeout=task.timeout)
        return await port.read_response()