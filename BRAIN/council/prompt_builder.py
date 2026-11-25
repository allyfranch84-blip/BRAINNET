# =============================================================================
# council/prompt_builder.py — Transforma plano em blocos de texto
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from .mission_planner import MissionPlan

@dataclass
class PromptPackage:
    """Pacote de prompts prontos, mas sem dono (provider)."""
    architect_prompt: str = ""
    implementer_prompt: str = ""
    review_prompt: str = ""
    repair_prompt: str = ""
    summary_prompt: str = ""

class PromptBuilder:
    """Serializa um MissionPlan em texto. Não toma decisões."""
    
    def build(self, plan: MissionPlan) -> PromptPackage:
        ctx_files = "\n".join(f"- {f}" for f in plan.context_files)
        ordered_files = "\n".join(f"- {f}" for f in plan.ordered_files)
        tests = "\n".join(f"- {t}" for t in plan.required_tests)

        base_context = f"""
### MISSÃO
{plan.objective}

### ARQUIVOS DE CONTEXTO
{ctx_files or 'Nenhum'}

### ORDEM DE MODIFICAÇÃO SUGERIDA
{ordered_files or 'Nenhuma'}

### TESTES OBRIGATÓRIOS
{tests or 'Nenhum'}

### RISCO ESTIMADO
{plan.risk_level.upper()}
"""

        return PromptPackage(
            architect_prompt=f"""
Você é o ARQUITETO. Analise o contexto e produza uma especificação técnica
detalhada de como implementar a missão abaixo. Não escreva o código final.
{base_context}
""",
            implementer_prompt=f"""
Você é o IMPLEMENTADOR. Escreva o código completo para os arquivos listados,
seguindo a especificação do arquiteto e as regras do projeto.
{base_context}
""",
            review_prompt=f"""
Você é o REVISOR. Avalie a implementação proposta.
Procure bugs, falhas de segurança e falta de testes.
{base_context}
""",
            summary_prompt=f"""
Resuma as ações tomadas para a missão abaixo.
{base_context}
"""
        )