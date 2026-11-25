# =============================================================================
# council/mission_executor.py — O Orquestrador Cego
# =============================================================================

from __future__ import annotations

import logging
from typing import Any

from .mission_context import MissionContext
from .mission_planner import MissionPlan
from .prompt_builder import PromptBuilder
from .execution_kernel import ExecutionKernel, Task, TaskResult
from .self_reflection import BrainSelfReflection
from .plan_validator import PlanValidator # <-- IMPORTANTE: Adicionado

logger = logging.getLogger("Council.Executor")

class MissionExecutor:
    """
    Orquestra o pipeline de execução. Não pensa, apenas obedece ao plano.
    """
    
    def __init__(
        self, 
        kernel: ExecutionKernel, 
        prompt_builder: PromptBuilder,
        self_reflection: BrainSelfReflection,
        validator: PlanValidator # <-- IMPORTANTE: Adicionado aqui
    ):
        self.kernel = kernel
        self.prompt_builder = prompt_builder
        self.self_reflection = self_reflection
        self.validator = validator

    async def execute(self, ctx: MissionContext) -> str:
        """
        Executa o plano contido no Contexto. Retorna o status final.
        """
        if not ctx.plan:
            raise ValueError("MissionContext não possui um MissionPlan")
        
        # 1. VALIDAÇÃO (O Porteiro)
        val_result = self.validator.validate(ctx)
        if not val_result.is_valid:
            logger.error("Plano inválido. Abortando antes da execução.")
            for err in val_result.errors:
                logger.error(f"  - {err}")
            ctx.state.record_failure("validation_failed", {"errors": val_result.errors})
            return "failed"

        # 2. Preparação
        plan = ctx.plan
        ctx.state.status = "running"
        ctx.state.current_step = "execution_started"
        
        # Gera os prompts
        prompts = self.prompt_builder.build(plan)
        
        # Monta as Tasks baseadas no plano
        tasks = self._build_tasks_from_plan(plan, prompts)
        
        # 3. Executa o pipeline
        task_results: dict[str, TaskResult] = {}
        
        for task in tasks:
            # Checkpoint antes de cada task
            ctx.state.current_step = f"task_{task.id}"
            
            # Verifica dependência
            if task.depends_on and task.depends_on not in task_results:
                logger.error(f"Dependência {task.depends_on} não satisfeita para {task.id}")
                return await self._handle_failure(ctx, task_results, "dependency_failed")

            # Executa via Kernel
            result = await self.kernel.execute_task(task)
            task_results[task.id] = result
            
            # Salva artefato no estado
            ctx.state.record_artifact(f"task_{task.id}", result.output)
            
            if result.status != "success":
                logger.error(f"Task {task.id} falhou: {result.error}")
                return await self._handle_failure(ctx, task_results, result.error or "task_failed")

        # 4. Executa os testes finais (se houver)
        test_failures = await self._run_tests(ctx, plan)
        
        if test_failures:
            return await self._handle_failure(ctx, task_results, "test_failures")

        # 5. Sucesso! Roda o SelfReflection
        ctx.state.status = "finished"
        self._reflect(ctx, "success", task_results, git_diff="")
        
        return "success"

    def _build_tasks_from_plan(self, plan: MissionPlan, prompts: Any) -> list[Task]:
        """Converte a lógica abstrata do plano em Tasks concretas para o Kernel."""
        tasks = []

        # Task 1: Architect (se aplicável)
        if plan.architect_model:
            tasks.append(Task(
                id="task_arch",
                provider=plan.architect_model,
                role="architect",
                prompt=prompts.architect_prompt,
                port_type="chat"
            ))

        # Task 2: Implementer
        impl_task = Task(
            id="task_impl",
            provider=plan.implementer_model,
            role="implementer",
            prompt=prompts.implementer_prompt,
            port_type="chat",
            depends_on="task_arch" if plan.architect_model else None
        )
        tasks.append(impl_task)

        # Task 3: Reviewer (opcional, apenas se o risco for alto ou se houver revisores)
        if plan.reviewers:
            tasks.append(Task(
                id="task_review",
                provider=plan.reviewers[0],
                role="reviewer",
                prompt=prompts.review_prompt,
                port_type="chat",
                depends_on="task_impl"
            ))

        return tasks

    async def _run_tests(self, ctx: MissionContext, plan: MissionPlan) -> bool:
        """Executa os testes obrigatórios no final."""
        has_failures = False
        for test_path in plan.required_tests:
            task = Task(
                id=f"test_{test_path.replace('/', '_')}",
                provider="pytest",
                role="tester",
                prompt=test_path,
                port_type="test",
                timeout=300.0
            )
            result = await self.kernel.execute_task(task)
            ctx.state.record_artifact(f"test_{test_path}", result.output)
            
            if result.status != "success" or (hasattr(result.output, 'status') and result.output.status == "FAIL"):
                has_failures = True
                
        return has_failures

    async def _handle_failure(self, ctx: MissionContext, results: dict, error: str) -> str:
        """Executa o plano de rollback e finaliza a missão."""
        logger.warning(f"Iniciando rollback para missão {ctx.mission.mission_id}")
        ctx.state.status = "failed"
        
        # Aqui executaríamos os comandos de rollback do ctx.plan.rollback_plan
        # Ex: git checkout...
        
        self._reflect(ctx, "failed", results, git_diff="")
        return "failed"

    def _reflect(self, ctx: MissionContext, outcome: str, results: dict, git_diff: str) -> None:
        """Gera o relatório final de aprendizado."""
        test_results = []
        # Converte TaskResults em dicionários para o SelfReflection
        for t_id, res in results.items():
            if t_id.startswith("test_"):
                test_results.append({"test_id": t_id, "status": res.status})
                
        self.self_reflection.reflect(ctx, outcome, test_results, git_diff)