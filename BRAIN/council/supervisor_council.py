# =============================================================================
# council/supervisor_council.py — Observador contínuo da missão
# =============================================================================

from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Any

logger = logging.getLogger("Council.Supervisor")

class AlertType(str, Enum):
    STAGNATION = "stagnation"
    CONTRADICTION = "contradiction"
    LOOP = "loop"
    HALLUCINATION = "hallucination"
    SCOPE_VIOLATION = "scope_violation"

class ModelResponse:
    def __init__(self, model: str, role: str, content: str, claims: list[str], evidence_refs: list[str], confidence: float = 0.0):
        self.model = model
        self.role = role
        self.content = content
        self.claims = claims
        self.evidence_refs = evidence_refs
        self.confidence = confidence

class SupervisorCouncil:
    def __init__(self, window: int = 5, stagnation_threshold: int = 3):
        self.window = window
        self.stagnation_threshold = stagnation_threshold
        self.history: list[ModelResponse] = []
        self.alerts: list[dict[str, Any]] = []

    def observe(self, response: ModelResponse) -> dict[str, Any]:
        self.history.append(response)
        if len(self.history) > self.window * 10:
            self.history = self.history[-self.window * 10:]

        alerts = []
        recent = self.history[-self.window:]
        
        # 1. LOOP ou STAGNATION
        if len(recent) >= self.stagnation_threshold:
            keys = [
                re.sub(r"\s+", " ", (r.claims[0] if r.claims else r.content[:200]).lower())
                for r in recent[-self.stagnation_threshold:]
            ]
            if len(set(keys)) == 1:
                alerts.append({
                    "type": AlertType.STAGNATION if len(recent) < 10 else AlertType.LOOP,
                    "models": [r.model for r in recent[-self.stagnation_threshold:]],
                    "message": f"mesmo claim repetido {self.stagnation_threshold}x",
                })

        # 2. CONTRADICTION
        if len(recent) >= 2:
            prev, cur = recent[-2], recent[-1]
            if prev.model == cur.model and prev.role == cur.role:
                if self._contradicts(prev, cur):
                    alerts.append({
                        "type": AlertType.CONTRADICTION,
                        "model": cur.model,
                        "message": "modelo contradiz o próprio turno anterior",
                    })

        # 3. HALLUCINATION (Heurística: confiança alta sem evidência)
        if len(recent) >= 3:
            avg_conf = sum(r.confidence for r in recent) / len(recent)
            zero_evidence = sum(1 for r in recent if not r.evidence_refs)
            if avg_conf >= 0.85 and zero_evidence >= 2:
                alerts.append({
                    "type": AlertType.HALLUCINATION,
                    "message": f"possível alucinação: confiança média {avg_conf:.2f} sem evidência",
                })

        self.alerts.extend(alerts)
        return {"alerts": alerts, "history_size": len(self.history)}

    def _contradicts(self, a: ModelResponse, b: ModelResponse) -> bool:
        if not a.claims or not b.claims:
            return False
        ka = re.sub(r"\s+", " ", a.claims[0].lower()).strip()
        kb = re.sub(r"\s+", " ", b.claims[0].lower()).strip()
        neg_a = ka.startswith("não ") or " não " in ka
        neg_b = kb.startswith("não ") or " não " in kb
        if neg_a != neg_b:
            return ka.replace("não ", "") == kb.replace("não ", "")
        return False