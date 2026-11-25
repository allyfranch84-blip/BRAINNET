# =============================================================================
# council/approval_gateway.py — Aprovação por missão (não por ação)
# =============================================================================

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from .mission_contract import (
    Contract, ContractState, Mission, Action, ScopeViolation,
)

logger = logging.getLogger("Council.Approval")


# -----------------------------------------------------------------------------
# UI abstrata (o "humano no loop")
# -----------------------------------------------------------------------------

class ApprovalUI(ABC):
    """Interface que a UI concreta precisa implementar."""

    @abstractmethod
    def show_mission_proposal(self, mission: Mission) -> dict[str, Any]:
        """Mostra o escopo e retorna o que o humano respondeu."""

    @abstractmethod
    def ask_confirm(self, message: str, default: bool = False) -> bool:
        """Pergunta sim/não. Usado em saídas de escopo."""


class TerminalApprovalUI(ApprovalUI):
    """UI simples para CLI/TUI."""

    def show_mission_proposal(self, mission: Mission) -> dict[str, Any]:
        scope = mission.scope
        print("\n" + "=" * 70)
        print(f"  MISSÃO PROPOSTA: {mission.objective}")
        print(f"  ID: {mission.mission_id}")
        print("=" * 70)
        print(f"\n  Arquivos permitidos ({len(scope.allowed_files)}):")
        for f in scope.allowed_files[:10]:
            print(f"    ✓ {f}")
        if len(scope.allowed_files) > 10:
            print(f"    ... e mais {len(scope.allowed_files) - 10}")
        print(f"\n  Diretórios permitidos: {scope.allowed_dirs or '(nenhum)'}")
        print(f"  Ações permitidas: {sorted(a.value for a in scope.allowed_actions)}")
        print(f"  Ações PROIBIDAS: {sorted(a.value for a in scope.forbidden)}")
        print(f"\n  Limites:")
        print(f"    - max arquivos alterados: {scope.max_files_changed}")
        print(f"    - max linhas alteradas:   {scope.max_lines_changed}")
        print(f"    - max duração:            {scope.max_duration_seconds}s")
        print(f"    - max chamadas de modelo: {scope.max_model_calls}")
        print(f"    - max testes:             {scope.max_test_runs}")
        print()
        resp = input("  Autoriza esta missão? [s/N] ").strip().lower()
        return {"approved": resp in ("s", "sim", "y", "yes"), "by": "human"}

    def ask_confirm(self, message: str, default: bool = False) -> bool:
        suffix = "[S/n]" if default else "[s/N]"
        resp = input(f"{message} {suffix} ").strip().lower()
        if not resp:
            return default
        return resp in ("s", "sim", "y", "yes")


class AutoDenyUI(ApprovalUI):
    """Para testes — nega tudo."""

    def show_mission_proposal(self, mission: Mission) -> dict[str, Any]:
        return {"approved": False, "by": "auto-deny"}

    def ask_confirm(self, message: str, default: bool = False) -> bool:
        return False


class AutoApproveUI(ApprovalUI):
    """Para testes controlados — aprova tudo. NUNCA use em produção."""

    def __init__(self, scope_override: Optional[Mission] = None):
        self.scope_override = scope_override

    def show_mission_proposal(self, mission: Mission) -> dict[str, Any]:
        logger.warning("AutoApproveUI: aprovando missão sem revisão humana")
        return {"approved": True, "by": "auto-approve-test"}

    def ask_confirm(self, message: str, default: bool = False) -> bool:
        return True


# -----------------------------------------------------------------------------
# Approval Gateway
# -----------------------------------------------------------------------------

@dataclass
class ApprovalDecision:
    approved: bool
    contract: Optional[Contract]
    reason: str = ""


class ApprovalGateway:
    """
    Interlock central. Aprova MISSÕES (não ações), monitora durante a execução,
    e exige re-aprovação apenas quando o escopo é violado.

    Fluxo:
        mission = Mission(objective=..., scope=...)
        contract = gateway.request_mission_approval(mission)
        # ... execução ...
        gateway.check_action(contract, action)   # levanta ScopeViolation se fora
        # ... fim ...
        gateway.close_mission(contract, "completed")
    """

    def __init__(
        self,
        ui: ApprovalUI,
        audit_dir: str | Path = "council_audit",
        on_violation: Optional[Callable[[Contract, Action, str], None]] = None,
    ):
        self.ui = ui
        self.audit_dir = Path(audit_dir)
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.on_violation = on_violation
        self._active: dict[str, Contract] = {}

    # ---------- ciclo de vida ----------

    def request_mission_approval(self, mission: Mission) -> Contract:
        """
        Apresenta a missão ao humano. Se aprovada, retorna um Contract ativo.
        Se negada, levanta PermissionError.
        """
        proposal_path = self._save_proposal(mission)

        response = self.ui.show_mission_proposal(mission)
        approved = response.get("approved", False)
        approved_by = response.get("by", "unknown")

        if not approved:
            self._log_event(mission.mission_id, "mission_denied", {
                "proposal_file": str(proposal_path),
            })
            raise PermissionError(
                f"Missão {mission.mission_id} negada por {approved_by}"
            )

        contract = Contract(
            mission=mission,
            approved_by=approved_by,
        )
        contract.activate()
        self._active[mission.mission_id] = contract

        self._log_event(mission.mission_id, "mission_approved", {
            "proposal_file": str(proposal_path),
            "fingerprint": mission.fingerprint(),
            "approved_by": approved_by,
            "expires_at": contract.expires_at,
        })
        return contract

    def check_action(self, contract: Contract, action: Action) -> None:
        """
        Verifica uma ação. Se fora do escopo, dispara on_violation,
        pausa o contrato e levanta ScopeViolation.
        Se dentro do escopo, registra e retorna silenciosamente.
        """
        ok, reason = contract.check_and_record(action)
        if ok:
            return

        # Fora do escopo
        if contract.state == ContractState.ACTIVE:
            contract.state = ContractState.PAUSED

        self._log_event(contract.mission.mission_id, "scope_violation", {
            "action": action.kind.value,
            "target": action.target,
            "reason": reason,
        })

        if self.on_violation:
            try:
                self.on_violation(contract, action, reason)
            except Exception as e:
                logger.exception("on_violation callback falhou: %s", e)

        # Pergunta ao humano se autoriza estender o escopo
        extended = self.ui.ask_confirm(
            f"\n  AÇÃO FORA DO ESCOPO DETECTADA:\n"
            f"  {action.kind.value} em {action.target!r}\n"
            f"  Motivo: {reason}\n\n"
            f"  Deseja autorizar esta ação (fora do escopo original)?",
            default=False,
        )

        if not extended:
            self._log_event(contract.mission.mission_id, "violation_denied", {
                "action": action.kind.value,
                "target": action.target,
            })
            raise ScopeViolation(action, reason)

        # Humano autorizou a extensão
        contract.state = ContractState.ACTIVE
        contract.mission.scope.forbidden.discard(action.kind)
        contract.mission.scope.allowed_actions.add(action.kind)
        if action.target and action.kind.value in ("modify_file", "create_file"):
            contract.mission.scope.allowed_files.append(action.target)

        contract.check_and_record(action)  # agora deve passar
        self._log_event(contract.mission.mission_id, "scope_extended", {
            "action": action.kind.value,
            "target": action.target,
        })

    def close_mission(self, contract: Contract, outcome: str) -> dict[str, Any]:
        """Finaliza a missão e grava o resumo de auditoria."""
        contract.close(outcome)
        summary = contract.audit_summary()
        self._save_audit(contract.mission.mission_id, summary)
        self._active.pop(contract.mission.mission_id, None)
        return summary

    def resume(self, mission_id: str) -> Optional[Contract]:
        """Retoma um contrato pausado (após autorização humana)."""
        c = self._active.get(mission_id)
        if c and c.state == ContractState.PAUSED:
            c.state = ContractState.ACTIVE
            return c
        return None

    # ---------- persistência ----------

    def _save_proposal(self, mission: Mission) -> Path:
        path = self.audit_dir / f"{mission.mission_id}_proposal.json"
        path.write_text(
            json.dumps(mission.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def _save_audit(self, mission_id: str, summary: dict[str, Any]) -> Path:
        path = self.audit_dir / f"{mission_id}_audit.json"
        path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def _log_event(self, mission_id: str, event: str, data: dict[str, Any]) -> None:
        path = self.audit_dir / f"{mission_id}_events.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": time.time(),
                "event": event,
                **data,
            }, ensure_ascii=False) + "\n")