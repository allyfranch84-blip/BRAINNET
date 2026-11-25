from dataclasses import dataclass

@dataclass
class Report:

    success: bool

    tests_passed: int

    tests_failed: int

    observations: str
    