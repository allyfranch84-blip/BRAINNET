# =============================================================================
# council/mission_state.py — A única fonte da verdade sobre a missão
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from .mission_contract import Contract

@dataclass
class MissionState:
    mission_id: str
    contract: Contract
    status: str = "initializing"  # initializing | running | paused | finished | failed
    current_step: str = ""
    current_provider: str = ""
    
    # Histórico de artefatos gerados (respostas dos modelos, diffs, testes)
    artifacts: dict[str, Any] = field(default_factory=dict)
    
    # Falhas e retentativas
    failures: list[dict[str, Any]] = field(default_factory=list)
    retries: int = 0
    
    # Métricas
    start_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    end_time: Optional[str] = None
    
    def record_artifact(self, key: str, value: Any) -> None:
        self.artifacts[key] = value

    def record_failure(self, reason: str, context: dict[str, Any] = None) -> None:
        self.failures.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "context": context or {}
        })
        self.retries += 1

    def finish(self, status: str = "finished") -> None:
        self.status = status
        self.end_time = datetime.now(timezone.utc).isoformat()