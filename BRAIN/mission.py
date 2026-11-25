from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Mission:

    id: str

    objective: str

    created: datetime

    finished: datetime | None = None

    status: str = "CREATED"

    strategy = None

    executor = None

    notes: list = field(default_factory=list)

    history: list = field(default_factory=list)