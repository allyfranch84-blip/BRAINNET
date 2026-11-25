"""
mission_manager.py

Camada central de gerenciamento de missões da BRAINNET.

Fluxo:

Chat
 ↓
MissionManager.start()
 ↓
Mission
 ↓
Planner / Strategy
 ↓
Executor
 ↓
Tests
 ↓
Report
 ↓
Telemetry
 ↓
MissionManager.finish()

"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
import uuid

from mission import Mission
from workspace_manager import WorkspaceManager
from strategy import StrategyEngine
from telemetry import Telemetry
from report import Report


class MissionManager:

    def __init__(self):

        self.workspace = WorkspaceManager()
        self.strategy = StrategyEngine()
        self.telemetry = Telemetry()
        self.report = Report()

        self.current_mission = None

    def start(self, objective: str) -> Mission:

        mission = Mission(
            id=str(uuid.uuid4()),
            objective=objective,
            created=datetime.utcnow(),
            status="RUNNING",
        )

        self.current_mission = mission

        self.workspace.prepare(mission)

        self.telemetry.event(
            mission.id,
            "MISSION_STARTED",
            {
                "objective": objective
            },
        )

        return mission

    def save_checkpoint(self):

        if self.current_mission is None:
            return

        self.workspace.save(self.current_mission)

    def plan(self):

        if self.current_mission is None:
            raise RuntimeError("Nenhuma missão ativa.")

        self.current_mission.strategy = self.strategy.create(
            self.current_mission
        )

        self.telemetry.event(
            self.current_mission.id,
            "PLAN_CREATED",
            {},
        )

    def execute(self):

        if self.current_mission is None:
            raise RuntimeError("Nenhuma missão ativa.")

        if self.current_mission.executor is None:
            return

        self.current_mission.executor.run()

    def finish(
        self,
        success: bool,
        message: str = "",
    ):

        if self.current_mission is None:
            return

        self.current_mission.finished = datetime.utcnow()

        self.current_mission.status = (
            "SUCCESS"
            if success
            else "FAILED"
        )

        self.report.generate(
            self.current_mission,
            message,
        )

        self.telemetry.event(
            self.current_mission.id,
            "MISSION_FINISHED",
            {
                "success": success,
                "message": message,
            },
        )

        self.workspace.save(
            self.current_mission
        )

        self.current_mission = None