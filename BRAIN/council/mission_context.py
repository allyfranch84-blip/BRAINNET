# =============================================================================
# council/mission_context.py — O ambiente unificado de execução
# =============================================================================

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .mission_contract import Mission, Contract
from .mission_state import MissionState
from .mission_planner import MissionPlan

@dataclass
class MissionContext:
    """
    Agrupa todo o estado da missão, do ambiente e das permissões.
    É passado de mão em mão entre o Reasoning, Planner, Executor e Adapters.
    """
    # Entidades do Council
    mission: Mission
    contract: Contract
    state: MissionState
    
    # O plano gerado (opcional até o Planner rodar)
    plan: Optional[MissionPlan] = None

    # Ambiente (Workspace)
    workspace_root: str = field(default_factory=os.getcwd)
    current_branch: str = "main"
    git_status: str = "clean"
    opened_files: list[str] = field(default_factory=list)

    # Modelos / Providers
    active_models: list[str] = field(default_factory=lambda: ["chatgpt", "deepseek"])
    
    # Telemetria
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metrics: dict[str, Any] = field(default_factory=dict)

    def is_valid(self) -> bool:
        """Verifica se o contexto básico está íntegro."""
        return self.contract.state.value == "active" and bool(self.workspace_root)