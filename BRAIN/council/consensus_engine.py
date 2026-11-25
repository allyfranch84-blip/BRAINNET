# =============================================================================
# council/consensus_engine.py — SupervisorCouncil (convergência + supervisão)
# =============================================================================

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, Protocol

from .mission_contract import Action, ActionKind, Contract
from .ports import TestResult

logger = logging.getLogger("Council.Consensus")


# -----------------------------------------------------------------------------
# Tipos
# -----------------------------------------------------------------------------

class ConsensusStrategy(str, Enum):
    MAJORITY    = "majority"       # voto majoritário (2+ concordam)
    EVIDENCE    = "evidence"       # baseado em evidências coletadas
    TEST        = "test"           # decide executando os testes propostos
    UNANIMOUS   = "unanimous"      # exige concordância total
    HUMAN       = "human"          # sempre escala para humano


class Verdict(str, Enum):
    CONVERGE        = "converge"           # consenso, pode prosseguir
    DIVERGE         = "diverge"            # modelos discordam
    INSUFFICIENT    = "insufficient"       # evidência insuficiente
    OVERCONFIDENT   = "overconfident"      # um modelo alega mais do que pode provar
    NEEDS_HUMAN     = "needs_human"        # escalar para humano


@dataclass
class ModelResponse:
    """Resposta de um modelo em um turno."""
    model: str                          # "chatgpt" | "deepseek" | "claude"
    role: str                           # "architect" | "implementer" | "reviewer"
    content: str
    claims: list[str] = field(default_factory=list)      # o que o modelo AFIRMA
    proposed_actions: list[Action] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)  # hashes de evidência
    confidence: Optional[float] = None
    timestamp: str = ""


@dataclass
class ConsensusResult:
    verdict: Verdict
    strategy: ConsensusStrategy
    winner: Optional[ModelResponse] = None
    reason: str = ""
    agreement_score: float = 0.0        # 0.0 = discórdia total, 1.0 = unânime
    evidence_used: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "strategy": self.strategy.value,
            "winner_model": self.winner.model if self.winner else None,
            "winner_role": self.winner.role if self.winner else None,
            "reason": self.reason,
            "agreement_score": round(self.agreement_score, 3),
            "evidence_used": self.evidence_used,
            "details": self.details,
        }


# -----------------------------------------------------------------------------
# Test runner adapter (o ConsensusEngine chama testes reais se disponível)
# -----------------------------------------------------------------------------

class TestRunnerProtocol(Protocol):
    async def run(self, test_path: str, timeout: float = 300.0) -> TestResult: ...


# -----------------------------------------------------------------------------
# ConsensusEngine
# -----------------------------------------------------------------------------

class ConsensusEngine:
    """
    Decide entre múltiplas respostas de modelos.
    NÃO escolhe "o mais confiante" — escolhe o que tem mais evidência.
    """

    def __init__(
        self,
        strategy: ConsensusStrategy = ConsensusStrategy.EVIDENCE,
        test_runner: Optional[TestRunnerProtocol] = None,
        human_callback: Optional[Callable[[ConsensusResult], bool]] = None,
        confidence_penalty: float = 0.15,
    ):
        self.strategy = strategy
        self.test_runner = test_runner
        self.human_callback = human_callback
        # Penalidade aplicada quando um modelo alega confiança sem evidência
        self.confidence_penalty = confidence_penalty

    async def evaluate(
        self,
        responses: list[ModelResponse],
        context: Optional[dict[str, Any]] = None,
    ) -> ConsensusResult:
        if not responses:
            return ConsensusResult(
                verdict=Verdict.INSUFFICIENT,
                strategy=self.strategy,
                reason="nenhuma resposta recebida",
            )

        # 1. Detecção de overconfidence primeiro (aplicada a TODOS)
        suspicious = self._detect_overconfidence(responses)
        if suspicious:
            logger.warning(
                "Modelos com possível overconfidence: %s",
                [r.model for r in suspicious],
            )

        # 2. Despacha para a estratégia
        if self.strategy == ConsensusStrategy.MAJORITY:
            return self._majority(responses)
        if self.strategy == ConsensusStrategy.UNANIMOUS:
            return self._unanimous(responses)
        if self.strategy == ConsensusStrategy.TEST:
            return await self._test_based(responses, context or {})
        if self.strategy == ConsensusStrategy.HUMAN:
            return self._escalate_human(responses, "estratégia HUMAN explícita")
        return self._evidence_based(responses, context or {})

    # ---------- estratégias ----------

    def _majority(self, responses: list[ModelResponse]) -> ConsensusResult:
        if len(responses) < 2:
            return ConsensusResult(
                verdict=Verdict.INSUFFICIENT,
                strategy=self.strategy,
                reason="maioria exige >= 2 respostas",
            )
        # Agrupa por "claim principal" — simplificação: hash do conteúdo normalizado
        buckets: dict[str, list[ModelResponse]] = {}
        for r in responses:
            key = self._claim_key(r)
            buckets.setdefault(key, []).append(r)

        largest = max(buckets.values(), key=len)
        if len(largest) > len(responses) / 2:
            return ConsensusResult(
                verdict=Verdict.CONVERGE,
                strategy=self.strategy,
                winner=largest[0],
                reason=f"{len(largest)}/{len(responses)} concordam",
                agreement_score=len(largest) / len(responses),
            )
        return ConsensusResult(
            verdict=Verdict.DIVERGE,
            strategy=self.strategy,
            reason="nenhuma maioria clara",
            agreement_score=max(len(v) for v in buckets.values()) / len(responses),
        )

    def _unanimous(self, responses: list[ModelResponse]) -> ConsensusResult:
        keys = {self._claim_key(r) for r in responses}
        if len(keys) == 1:
            return ConsensusResult(
                verdict=Verdict.CONVERGE,
                strategy=self.strategy,
                winner=responses[0],
                reason="unanimidade",
                agreement_score=1.0,
            )
        return ConsensusResult(
            verdict=Verdict.DIVERGE,
            strategy=self.strategy,
            reason=f"{len(keys)} claims distintos",
            agreement_score=1.0 / len(keys),
        )

    def _evidence_based(
        self,
        responses: list[ModelResponse],
        context: dict[str, Any],
    ) -> ConsensusResult:
        """
        Rankeia por evidência referenciada. O modelo que cita mais
        evidências (e tem claims mais específicos) vence.
        """
        scored: list[tuple[float, ModelResponse]] = []
        for r in responses:
            score = (
                len(r.evidence_refs) * 2.0
                + len(self._specific_claims(r)) * 1.0
                + (r.confidence or 0.0) * 0.5
                - (self.confidence_penalty if r in self._detect_overconfidence(responses) else 0.0)
            )
            scored.append((score, r))
        scored.sort(key=lambda x: x[0], reverse=True)

        top_score, winner = scored[0]
        runner_score = scored[1][0] if len(scored) > 1 else 0.0

        if top_score <= 0:
            return ConsensusResult(
                verdict=Verdict.INSUFFICIENT,
                strategy=self.strategy,
                reason="nenhuma resposta tem evidência",
            )

        # Se o segundo colocado está próximo, é divergência
        if runner_score > 0 and top_score / runner_score < 1.3:
            return ConsensusResult(
                verdict=Verdict.DIVERGE,
                strategy=self.strategy,
                winner=winner,
                reason=f"evidências próximas (top={top_score:.1f}, runner={runner_score:.1f})",
                agreement_score=runner_score / top_score,
                evidence_used=winner.evidence_refs,
            )

        return ConsensusResult(
            verdict=Verdict.CONVERGE,
            strategy=self.strategy,
            winner=winner,
            reason=f"melhor score de evidência ({top_score:.1f})",
            agreement_score=min(1.0, top_score / max(runner_score, 1.0) / 2),
            evidence_used=winner.evidence_refs,
        )

    async def _test_based(
        self,
        responses: list[ModelResponse],
        context: dict[str, Any],
    ) -> ConsensusResult:
        """
        Decisão por execução: cada resposta propõe ações; a que resultar em
        testes PASS vence. Requer test_runner no construtor.
        """
        if not self.test_runner:
            return ConsensusResult(
                verdict=Verdict.NEEDS_HUMAN,
                strategy=self.strategy,
                reason="test_based sem test_runner configurado",
            )

        test_paths = context.get("test_paths", [])
        if not test_paths:
            return ConsensusResult(
                verdict=Verdict.NEEDS_HUMAN,
                strategy=self.strategy,
                reason="test_based sem test_paths no contexto",
            )

        scores: list[tuple[float, ModelResponse, list[TestResult]]] = []
        for r in responses:
            results: list[TestResult] = []
            passed = 0
            for tp in test_paths:
                try:
                    res = await self.test_runner.run(tp)
                    results.append(res)
                    if res.status == "PASS":
                        passed += 1
                except Exception as e:
                    logger.exception("Teste falhou durante consensus: %s", e)
            scores.append((passed / len(test_paths), r, results))

        scores.sort(key=lambda x: x[0], reverse=True)
        top_score, winner, results = scores[0]
        runner_score = scores[1][0] if len(scores) > 1 else 0.0

        if top_score == 1.0 and runner_score < 1.0:
            return ConsensusResult(
                verdict=Verdict.CONVERGE,
                strategy=self.strategy,
                winner=winner,
                reason=f"todos os testes PASS ({len(test_paths)})",
                agreement_score=1.0,
                details={"test_results": [r.__dict__ for r in results]},
            )

        if abs(top_score - runner_score) < 0.1:
            return ConsensusResult(
                verdict=Verdict.DIVERGE,
                strategy=self.strategy,
                winner=winner,
                reason=f"testes inconclusivos (top={top_score:.2f}, runner={runner_score:.2f})",
                agreement_score=top_score,
                details={"test_results": [r.__dict__ for r in results]},
            )

        return ConsensusResult(
            verdict=Verdict.CONVERGE,
            strategy=self.strategy,
            winner=winner,
            reason=f"mais testes PASS ({top_score:.0%})",
            agreement_score=top_score,
            details={"test_results": [r.__dict__ for r in results]},
        )

    def _escalate_human(
        self,
        responses: list[ModelResponse],
        reason: str,
    ) -> ConsensusResult:
        result = ConsensusResult(
            verdict=Verdict.NEEDS_HUMAN,
            strategy=self.strategy,
            reason=reason,
            details={
                "responses": [
                    {"model": r.model, "role": r.role, "claims": r.claims}
                    for r in responses
                ],
            },
        )
        if self.human_callback:
            approved = self.human_callback(result)
            if approved:
                result.verdict = Verdict.CONVERGE
        return result

    # ---------- heurísticas ----------

    def _claim_key(self, r: ModelResponse) -> str:
        """Chave normalizada do claim principal — para agrupar 'iguais'."""
        text = (r.claims[0] if r.claims else r.content[:200]).lower()
        return re.sub(r"\s+", " ", text).strip()

    def _specific_claims(self, r: ModelResponse) -> list[str]:
        """Claims que citam algo concreto (arquivo, linha, símbolo)."""
        concrete = re.compile(
            r"(\b\w+\.(?:py|js|jsx|ts|tsx|go|rs)\b)|"      # arquivo
            r"(\bline\s+\d+\b)|"                             # linha
            r"(\b[A-Z][a-zA-Z0-9]+(?:Manager|Service|Adapter|Engine)\b)"  # classe
        )
        return [c for c in r.claims if concrete.search(c)]

    def _detect_overconfidence(
        self, responses: list[ModelResponse]
    ) -> list[ModelResponse]:
        """
        Detecta modelos que afirmam com confiança alta mas sem evidência.
        Regra: confidence >= 0.8 e evidence_refs == 0 e claims específicos == 0.
        """
        suspicious: list[ModelResponse] = []
        for r in responses:
            if (
                (r.confidence or 0.0) >= 0.8
                and not r.evidence_refs
                and not self._specific_claims(r)
            ):
                suspicious.append(r)
        return suspicious


# -----------------------------------------------------------------------------
# SupervisorCouncil
# -----------------------------------------------------------------------------

class SupervisorCouncil:
    """
    Observa continuamente a execução e detecta:
        - estagnação (modelos repetindo)
        - overconfidence acumulada
        - contradições entre turnos
        - violação de escopo iminente
    Não substitui o ConsensusEngine — complementa, observando o histórico.
    """

    def __init__(self, window: int = 5, stagnation_threshold: int = 3):
        self.window = window
        self.stagnation_threshold = stagnation_threshold
        self.history: list[ModelResponse] = []
        self.alerts: list[dict[str, Any]] = []

    def observe(self, response: ModelResponse) -> dict[str, Any]:
        """Registra uma resposta e retorna alertas gerados."""
        self.history.append(response)
        if len(self.history) > self.window * 10:
            self.history = self.history[-self.window * 10:]

        alerts = []

        # 1. Estagnação: mesmo claim repetido N vezes seguidas
        recent = self.history[-self.window:]
        if len(recent) >= self.stagnation_threshold:
            keys = [
                re.sub(r"\s+", " ", (r.claims[0] if r.claims else r.content[:200]).lower())
                for r in recent[-self.stagnation_threshold:]
            ]
            if len(set(keys)) == 1:
                alerts.append({
                    "kind": "stagnation",
                    "models": [r.model for r in recent[-self.stagnation_threshold:]],
                    "message": f"mesmo claim repetido {self.stagnation_threshold}x",
                })

        # 2. Contradição: modelo afirma X agora, ~X antes
        if len(recent) >= 2:
            prev, cur = recent[-2], recent[-1]
            if prev.model == cur.model and prev.role == cur.role:
                if self._contradicts(prev, cur):
                    alerts.append({
                        "kind": "contradiction",
                        "model": cur.model,
                        "message": "modelo contradiz o próprio turno anterior",
                    })

        # 3. Overconfidence acumulada
        if len(recent) >= 3:
            avg_conf = sum(r.confidence or 0.0 for r in recent) / len(recent)
            zero_evidence = sum(1 for r in recent if not r.evidence_refs)
            if avg_conf >= 0.8 and zero_evidence >= 2:
                alerts.append({
                    "kind": "overconfidence",
                    "message": f"confiança média {avg_conf:.2f} sem evidência",
                })

        self.alerts.extend(alerts)
        return {"alerts": alerts, "history_size": len(self.history)}

    def _contradicts(self, a: ModelResponse, b: ModelResponse) -> bool:
        """Heurística simples: 'não X' vs 'X' em claims curtos."""
        if not a.claims or not b.claims:
            return False
        ka = re.sub(r"\s+", " ", a.claims[0].lower()).strip()
        kb = re.sub(r"\s+", " ", b.claims[0].lower()).strip()
        neg_a = ka.startswith("não ") or " não " in ka
        neg_b = kb.startswith("não ") or " não " in kb
        if neg_a != neg_b:
            core_a = ka.replace("não ", "").strip()
            core_b = kb.replace("não ", "").strip()
            return core_a == core_b
        return False

    def summary(self) -> dict[str, Any]:
        by_kind: dict[str, int] = {}
        for a in self.alerts:
            by_kind[a["kind"]] = by_kind.get(a["kind"], 0) + 1
        return {
            "total_alerts": len(self.alerts),
            "alerts_by_kind": by_kind,
            "history_size": len(self.history),
        }