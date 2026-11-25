# =============================================================================
# council/reasoning_engine.py — O Cérebro (Decision Maker)
# =============================================================================

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any, TYPE_CHECKING

from .mission_contract import Mission, ActionKind, Contract
from .supervisor_council import SupervisorCouncil
from .mission_state import MissionState

if TYPE_CHECKING:
    from architecture_reasoner import ArchitectureReasoner

logger = logging.getLogger("Council.Reasoning")

# =============================================================================
# O NOVO CONTRATO DE PLANEJAMENTO
# =============================================================================

class TaskRole(str, Enum):
    ARCHITECT   = "architect"
    IMPLEMENTER = "implementer"
    REVIEWER    = "reviewer"

@dataclass
class MissionPlan:
    """
    O que o ReasoningEngine produz. O Dispatcher apenas lê isso e executa.
    """
    objective: str
    context_files: list[str] = field(default_factory=list)
    architect: str = "chatgpt"
    implementer: str = "deepseek"
    reviewers: list[str] = field(default_factory=lambda: ["chatgpt", "deepseek"])
    required_tests: list[str] = field(default_factory=list)
    confidence: float = 0.0
    reasoning_log: list[str] = field(default_factory=list)

# =============================================================================
# REASONING ENGINE
# =============================================================================

class ReasoningEngine:
    def __init__(self, architecture_reasoner: "ArchitectureReasoner", history_db: Any = None):
        self.arch = architecture_reasoner
        self.history = history_db
        self.supervisor = SupervisorCouncil()
        
        self.DEFAULT_ARCHITECT = "chatgpt"
        self.DEFAULT_IMPLEMENTER = "deepseek"

    def plan_mission(self, mission: Mission, state: MissionState) -> MissionPlan:
        """
        Ponto de entrada. Recebe a missão, consulta o conhecimento,
        e cospe um MissionPlan executável.
        """
        logger.info(f"ReasoningEngine planejando missão: {mission.objective}")
        state.current_step = "reasoning"
        log: list[str] = []

        # 1. Análise de Impacto (ArchitectureReasoner)
        log.append("Consultando ArchitectureReasoner para mapear contexto...")
        impacted_files = []
        required_tests = []
        
        if hasattr(self.arch, "where_to_change"):
            candidates = self.arch.where_to_change(mission.objective)
            impacted_files = [c.file for c in candidates[:5]]
            log.append(f"Arquivos prováveis: {', '.join(impacted_files) or 'Nenhum'}")
            
            # Extrai os testes sugeridos (se o Reasoner suportar)
            if hasattr(self.arch, "which_tests"):
                for f in impacted_files:
                    # Simulação de busca de testes
                    pass

        # 2. Definição de Estratégia (Heurística)
        is_complex = any(w in mission.objective.lower() for w in ["criar", "corrigir", "refatorar"])
        
        arch = self.DEFAULT_ARCHITECT if is_complex else None
        impl = self.DEFAULT_IMPLEMENTER
        
        if is_complex:
            log.append("Missão complexa. Gerando pipeline Architect -> Implementer.")
        else:
            log.append("Missão simples. Apenas Implementer será usado.")

        plan = MissionPlan(
            objective=mission.objective,
            context_files=impacted_files,
            architect=arch,
            implementer=impl,
            required_tests=required_tests,
            confidence=0.85 if impacted_files else 0.5,
            reasoning_log=log
        )
        
        state.record_artifact("mission_plan", plan)
        return plan