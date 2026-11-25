"""
mission_executor.py

Executor principal de missões da BRAINNET.

Fluxo:

Mission
   ↓
Planejamento
   ↓
Execução
   ↓
Testes
   ↓
Rollback (se necessário)
   ↓
Relatório
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Callable, List, Dict, Optional
import traceback
import time

from mission import Mission
from report import MissionReport
from telemetry import Telemetry
from strategy import StrategyEngine


# =====================================================
# ACTION
# =====================================================

@dataclass
class Action:

    name: str
    callback: Callable[[Mission], bool]
    rollback: Optional[Callable[[Mission], None]] = None


# =====================================================
# EXECUTOR
# =====================================================

class MissionExecutor:

    def __init__(self):

        self.strategy = StrategyEngine()

        self.telemetry = Telemetry()

        self.actions: Dict[str, Action] = {}

        self.rollback_stack: List[Action] = []

    # -------------------------------------------------

    def register(self, action: Action):

        self.actions[action.name] = action

    # -------------------------------------------------

    def execute(self, mission: Mission) -> MissionReport:

        report = MissionReport()

        report.start_time = datetime.now()

        report.objective = mission.objective

        self.telemetry.start(mission.id)

        try:

            strategy = self.strategy.plan(mission)

            report.strategy = strategy

            for step in strategy.steps:

                self._run_step(step, mission, report)

            report.success = True

        except Exception as exc:

            report.success = False

            report.error = str(exc)

            report.traceback = traceback.format_exc()

            self.rollback(mission)

        finally:

            report.finish_time = datetime.now()

            self.telemetry.finish(mission.id)

        return report

    # -------------------------------------------------

    def _run_step(self, step, mission, report):

        if step.action not in self.actions:

            raise RuntimeError(
                f"Ação não registrada: {step.action}"
            )

        action = self.actions[step.action]

        start = time.perf_counter()

        ok = action.callback(mission)

        elapsed = time.perf_counter() - start

        report.steps.append({

            "action": step.action,

            "success": ok,

            "time": elapsed

        })

        if not ok:

            raise RuntimeError(
                f"Falha na ação {step.action}"
            )

        self.rollback_stack.append(action)

    # -------------------------------------------------

    def rollback(self, mission):

        while self.rollback_stack:

            action = self.rollback_stack.pop()

            if action.rollback:

                try:

                    action.rollback(mission)

                except Exception:

                    pass

    # -------------------------------------------------

    def execute_named(self, name: str, mission: Mission):

        if name not in self.actions:

            raise KeyError(name)

        return self.actions[name].callback(mission)

    # -------------------------------------------------

    def list_actions(self):

        return sorted(self.actions.keys())