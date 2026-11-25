# =============================================================================
# council/mission_contract.py — Missão, Escopo e Contrato
# =============================================================================

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class ContractState(str, Enum):
    PROPOSED    = "proposed"      # aguardando aprovação humana
    ACTIVE      = "active"        # aprovada, executando
    PAUSED      = "paused"        # pausada por saída de escopo
    COMPLETED   = "completed"     # concluída com sucesso
    FAILED      = "failed"        # concluída com falha
    CANCELLED   = "cancelled"     # cancelada pelo humano
    EXPIRED     = "expired"       # expirou (timeout/max_duration)


class ActionKind(str, Enum):
    NAVIGATE        = "navigate"
    SEND_PROMPT     = "send_prompt"
    READ_RESPONSE   = "read_response"
    SCREENSHOT      = "screenshot"
    MODIFY_FILE     = "modify_file"
    CREATE_FILE     = "create_file"
    DELETE_FILE     = "delete_file"
    RUN_TEST        = "run_test"
    GIT_COMMIT      = "git_commit"
    GIT_PUSH        = "git_push"
    INSTALL_PACKAGE = "install_package"
    EXECUTE_SHELL   = "execute_shell"


# Ações que são seguras por natureza (leitura, navegação, captura)
READ_ONLY_ACTIONS: set[ActionKind] = {
    ActionKind.NAVIGATE,
    ActionKind.SCREENSHOT,
    ActionKind.READ_RESPONSE,
}


@dataclass
class Scope:
    """
    O que a Brainnet pode fazer durante a missão. Definido ANTES da aprovação,
    verificado durante a execução, auditado ao final.
    """
    # Arquivos que podem ser tocados
    allowed_files: list[str] = field(default_factory=list)
    allowed_dirs: list[str] = field(default_factory=list)

    # Ações permitidas (além das read-only, que são sempre permitidas)
    allowed_actions: set[ActionKind] = field(default_factory=set)

    # Domínios permitidos (para navegação)
    allowed_domains: list[str] = field(default_factory=list)

    # Limites de segurança
    max_files_changed: int = 20
    max_lines_changed: int = 5_000
    max_duration_seconds: int = 3_600      # 1h
    max_model_calls: int = 50
    max_test_runs: int = 30

    # Travas explícitas (o que NUNCA pode acontecer)
    forbidden: set[ActionKind] = field(default_factory=lambda: {
        ActionKind.GIT_PUSH,
        ActionKind.INSTALL_PACKAGE,
        ActionKind.DELETE_FILE,
    })

    def permits(self, action: Action) -> tuple[bool, str]:
        """
        Retorna (permitido, motivo). O motivo é vazio se permitido.
        """
        # 1. Leitura é sempre permitida
        if action.kind in READ_ONLY_ACTIONS:
            return True, ""

        # 2. Forbidden tem prioridade absoluta
        if action.kind in self.forbidden:
            return False, f"ação proibida pelo escopo: {action.kind.value}"

        # 3. Ações de modificação exigem permissão explícita
        if action.kind in (ActionKind.MODIFY_FILE, ActionKind.CREATE_FILE):
            if action.kind not in self.allowed_actions:
                return False, f"ação não autorizada: {action.kind.value}"
            target = action.target or ""
            in_files = any(target == f or target.startswith(f) for f in self.allowed_files)
            in_dirs  = any(target.startswith(d) for d in self.allowed_dirs)
            if not (in_files or in_dirs):
                return False, f"arquivo fora do escopo: {target}"

        # 4. Navegação exige domínio permitido
        if action.kind == ActionKind.NAVIGATE:
            target = action.target or ""
            if self.allowed_domains and not any(d in target for d in self.allowed_domains):
                return False, f"domínio fora do escopo: {target}"

        # 5. Ações genéricas (test, shell, commit) verificam allowed_actions
        if action.kind not in self.allowed_actions:
            return False, f"ação não autorizada: {action.kind.value}"

        return True, ""


@dataclass
class Action:
    """Uma ação concreta proposta durante a execução."""
    kind: ActionKind
    target: Optional[str] = None       # path, URL, seletor, comando
    payload: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""                # por que essa ação?
    requested_by: str = ""             # qual modelo/papel pediu
    requested_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class Mission:
    """
    O que o usuário pediu. Vira um Contract depois da aprovação.
    """
    objective: str
    scope: Scope
    mission_id: str = field(default_factory=lambda: f"m_{uuid.uuid4().hex[:10]}")
    requested_by: str = "human"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "objective": self.objective,
            "scope": _scope_to_dict(self.scope),
            "requested_by": self.requested_by,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    def fingerprint(self) -> str:
        """Hash determinístico do escopo — para auditoria."""
        payload = json.dumps(
            {
                "objective": self.objective,
                "scope": _scope_to_dict(self.scope),
            },
            sort_keys=True, ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass
class Contract:
    """
    Missão aprovada. Contrato entre humano e Brainnet.
    Durante a execução, toda ação é verificada contra este contrato.
    """
    mission: Mission
    state: ContractState = ContractState.PROPOSED
    approved_by: str = "human"
    approved_at: str = ""
    expires_at: float = 0.0           # time.time() + max_duration_seconds

    # Contadores de uso (para enforcement dos limites)
    files_changed: set[str] = field(default_factory=set)
    lines_changed: int = 0
    model_calls: int = 0
    test_runs: int = 0
    started_at: float = 0.0

    # Log de ações (para auditoria e rollback)
    actions_log: list[dict[str, Any]] = field(default_factory=list)

    # ------------------------------------------------------------------

    def activate(self) -> None:
        now = time.time()
        self.state = ContractState.ACTIVE
        self.approved_at = datetime.now(timezone.utc).isoformat()
        self.started_at = now
        self.expires_at = now + self.mission.scope.max_duration_seconds

    def check_and_record(self, action: Action) -> tuple[bool, str]:
        """
        Verifica a ação contra o escopo E os limites de uso.
        Se permitida, incrementa contadores. Se não, não incrementa.
        """
        if self.state != ContractState.ACTIVE:
            return False, f"contrato não está ativo (estado: {self.state.value})"

        if time.time() > self.expires_at:
            self.state = ContractState.EXPIRED
            return False, "contrato expirado"

        # 1. Checagem de escopo
        ok, reason = self.mission.scope.permits(action)
        if not ok:
            self.actions_log.append({
                "ts": datetime.now(timezone.utc).isoformat(),
                "action": action.kind.value,
                "target": action.target,
                "result": "DENIED",
                "reason": reason,
            })
            return False, reason

        # 2. Checagem de limites
        if action.kind == ActionKind.MODIFY_FILE and action.target:
            if len(self.files_changed) >= self.mission.scope.max_files_changed:
                if action.target not in self.files_changed:
                    reason = f"max_files_changed ({self.mission.scope.max_files_changed}) atingido"
                    self.actions_log.append({
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "action": action.kind.value,
                        "target": action.target,
                        "result": "DENIED",
                        "reason": reason,
                    })
                    return False, reason
            self.files_changed.add(action.target)

        if action.kind == ActionKind.SEND_PROMPT:
            self.model_calls += 1
            if self.model_calls > self.mission.scope.max_model_calls:
                reason = f"max_model_calls ({self.mission.scope.max_model_calls}) atingido"
                return False, reason

        if action.kind == ActionKind.RUN_TEST:
            self.test_runs += 1
            if self.test_runs > self.mission.scope.max_test_runs:
                reason = f"max_test_runs ({self.mission.scope.max_test_runs}) atingido"
                return False, reason

        # 3. Registro de aprovação
        self.actions_log.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": action.kind.value,
            "target": action.target,
            "result": "ALLOWED",
            "rationale": action.rationale,
        })
        return True, ""

    def close(self, outcome: str) -> None:
        """outcome: 'completed' | 'failed' | 'cancelled'"""
        self.state = ContractState(outcome)
        self.actions_log.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": "contract_closed",
            "outcome": outcome,
        })

    def audit_summary(self) -> dict[str, Any]:
        """Resumo da execução para o relatório final."""
        denied = [a for a in self.actions_log if a.get("result") == "DENIED"]
        return {
            "mission_id": self.mission.mission_id,
            "objective": self.mission.objective,
            "state": self.state.value,
            "fingerprint": self.mission.fingerprint(),
            "approved_at": self.approved_at,
            "files_changed": sorted(self.files_changed),
            "model_calls": self.model_calls,
            "test_runs": self.test_runs,
            "total_actions": len(self.actions_log),
            "denied_actions": len(denied),
            "denied_details": denied,
            "duration_seconds": (
                time.time() - self.started_at if self.started_at else 0
            ),
        }


class ScopeViolation(RuntimeError):
    """Levantada quando uma ação sai do escopo do contrato."""
    def __init__(self, action: Action, reason: str):
        self.action = action
        self.reason = reason
        super().__init__(
            f"ScopeViolation: {action.kind.value} em {action.target!r} — {reason}"
        )


# -----------------------------------------------------------------------------
# Serialização
# -----------------------------------------------------------------------------

def _scope_to_dict(scope: Scope) -> dict[str, Any]:
    return {
        "allowed_files": scope.allowed_files,
        "allowed_dirs": scope.allowed_dirs,
        "allowed_actions": [a.value for a in scope.allowed_actions],
        "allowed_domains": scope.allowed_domains,
        "max_files_changed": scope.max_files_changed,
        "max_lines_changed": scope.max_lines_changed,
        "max_duration_seconds": scope.max_duration_seconds,
        "max_model_calls": scope.max_model_calls,
        "max_test_runs": scope.max_test_runs,
        "forbidden": [a.value for a in scope.forbidden],
    }