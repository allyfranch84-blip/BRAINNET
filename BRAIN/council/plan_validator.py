# =============================================================================
# council/plan_validator.py — Verificação de Sanidade do Plano
# =============================================================================

import os
from dataclasses import dataclass
from typing import Any
from .mission_context import MissionContext
from .mission_planner import MissionPlan
from .provider_registry import ProviderRegistry

@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str]

class PlanValidator:
    """Verifica se o plano é executável antes de acionar o Kernel."""

    def __init__(self, registry: ProviderRegistry):
        self.registry = registry

    def validate(self, ctx: MissionContext) -> ValidationResult:
        errors = []
        
        if not ctx.plan:
            return ValidationResult(False, ["MissionPlan está vazio."])

        plan = ctx.plan

        # 1. Verifica se os Providers necessários existem
        if plan.architect_model and not self.registry.exists(plan.architect_model):
            errors.append(f"Provider ausente: {plan.architect_model}")
        
        if not self.registry.exists(plan.implementer_model):
            errors.append(f"Provider ausente: {plan.implementer_model}")
            
        for reviewer in plan.reviewers:
            if not self.registry.exists(reviewer):
                errors.append(f"Provider ausente (Reviewer): {reviewer}")

        # 2. Verifica se os arquivos existem no disco (apenas leitura)
        for f in plan.ordered_files:
            if not os.path.exists(f) and not os.path.exists(os.path.join(ctx.workspace_root, f)):
                # Alguns arquivos podem ser novos, então isso é apenas um aviso rigoroso
                errors.append(f"Arquivo não encontrado no workspace: {f}")

        # 3. Verifica se há rollback definido se o risco for alto
        if plan.risk_level == "high" and not plan.rollback_plan:
            errors.append("Risco alto, mas não há plano de rollback definido.")

        return ValidationResult(len(errors) == 0, errors)