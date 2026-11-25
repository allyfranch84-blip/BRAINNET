from dataclasses import dataclass

@dataclass
class Strategy:

    summary: str

    confidence: float

    estimated_steps: int