from pathlib import Path
import json
from datetime import datetime


class WorkspaceManager:
    def __init__(self, root: Path):
        self.root = Path(root)

    def create(self, mission_id: str):
        ws = self.root / mission_id
        ws.mkdir(parents=True, exist_ok=True)

        for name in (
            "mission.json",
            "strategy.md",
            "report.md",
            "telemetry.json",
            "architecture_snapshot.json",
        ):
            path = ws / name
            if not path.exists():
                if path.suffix == ".json":
                    path.write_text("{}", encoding="utf8")
                else:
                    path.write_text("", encoding="utf8")

        return ws

    def append_log(self, mission_id: str, text: str):
        log = self.root / mission_id / "report.md"

        with log.open("a", encoding="utf8") as f:
            f.write(f"\n[{datetime.now()}]\n")
            f.write(text)
            f.write("\n")
            