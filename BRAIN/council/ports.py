# =============================================================================
# council/ports.py — Interfaces abstratas (Ports & Adapters)
# =============================================================================

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


# -----------------------------------------------------------------------------
# Tipos auxiliares de valor
# -----------------------------------------------------------------------------

@dataclass
class ElementRef:
    """Referência a um elemento de UI — agnóstica de tecnologia."""
    id: str
    text: str = ""
    role: str = ""           # button, textbox, link, etc.
    bbox: Optional[tuple[int, int, int, int]] = None   # (x, y, w, h)
    attributes: dict[str, str] = field(default_factory=dict)
    source: str = ""         # "dom" | "accessibility" | "ocr" | "vision"


@dataclass
class ChatTurn:
    """Um turno de conversa extraído de um chat."""
    role: str                # "user" | "assistant" | "system"
    content: str
    timestamp: str = ""
    model: str = ""
    raw_html: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TestResult:
    """Resultado de um teste real."""
    test_id: str
    status: str              # "PASS" | "FAIL" | "ERROR" | "SKIP"
    duration_seconds: float = 0.0
    stdout: str = ""
    stderr: str = ""
    traceback: Optional[str] = None
    screenshots: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)


@dataclass
class Evidence:
    """Evidência coletada durante uma missão."""
    kind: str                # "screenshot" | "log" | "test_output" | "diff" | "chat_turn"
    path: Optional[str] = None
    content: Optional[str] = None
    hash: str = ""           # sha256 do conteúdo
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


# -----------------------------------------------------------------------------
# Portas (interfaces abstratas)
# -----------------------------------------------------------------------------

class BrowserPort(ABC):
    """
    Interface abstrata para navegar e interagir com páginas web.
    Implementações concretas: PlaywrightBrowserAdapter, VisionBrowserAdapter,
    PyAutoGUIBrowserAdapter. O resto do sistema só conhece esta porta.
    """

    @abstractmethod
    async def open(self, url: str) -> None: ...

    @abstractmethod
    async def focus(self) -> None: ...

    @abstractmethod
    async def click(self, target: ElementRef | str) -> None: ...

    @abstractmethod
    async def scroll(self, direction: str, amount: int = 500) -> None:
        """direction: 'up' | 'down' | 'left' | 'right'"""

    @abstractmethod
    async def paste(self, text: str) -> None: ...

    @abstractmethod
    async def copy(self) -> str: ...

    @abstractmethod
    async def capture(self, path: Optional[str] = None) -> Evidence:
        """Screenshot do estado atual. Retorna Evidence com hash."""

    @abstractmethod
    async def wait_element(
        self, target: ElementRef | str, timeout: float = 30.0,
        state: str = "visible"
    ) -> ElementRef: ...

    @abstractmethod
    async def find_text(self, text: str) -> list[ElementRef]:
        """Encontra elementos por texto (via DOM, a11y ou OCR)."""

    @abstractmethod
    async def send_enter(self) -> None: ...

    @abstractmethod
    async def upload_file(self, path: str, target: ElementRef | str) -> None: ...

    @abstractmethod
    async def download(self, url: str, dest: str) -> str: ...

    @abstractmethod
    async def accessibility_tree(self) -> dict[str, Any]:
        """Árvore semântica do que está na tela (quando disponível)."""

    @abstractmethod
    async def close(self) -> None: ...


class ChatPort(ABC):
    """
    Interface abstrata para interagir com um chat de IA.
    Implementações: ChatGPTAdapter, DeepSeekAdapter, ClaudeAdapter...
    """

    @abstractmethod
    async def send_prompt(self, prompt: str) -> None: ...

    @abstractmethod
    async def wait_generation(self, timeout: float = 180.0) -> bool:
        """Aguarda resposta completa. Retorna True se completou, False se timeout."""

    @abstractmethod
    async def read_response(self) -> ChatTurn:
        """Lê o último turno do assistente."""

    @abstractmethod
    def extract_code(self, turn: ChatTurn) -> list[dict[str, str]]:
        """Extrai blocos de código. Retorna [{language, code}]."""

    @abstractmethod
    def extract_markdown(self, turn: ChatTurn) -> str: ...

    @abstractmethod
    def detect_error(self, turn: ChatTurn) -> Optional[str]:
        """Detecta se o chat retornou erro (rate limit, recusa, etc.)."""

    @abstractmethod
    async def new_chat(self) -> None: ...

    @abstractmethod
    async def continue_chat(self, chat_id: str) -> None: ...


class TestRunnerPort(ABC):
    """Interface para executar testes reais."""

    @abstractmethod
    async def run(self, test_path: str, timeout: float = 300.0) -> TestResult: ...

    @abstractmethod
    async def run_suite(self, paths: list[str], parallel: bool = True) -> list[TestResult]: ...


class EvidencePort(ABC):
    """Interface para persistir evidências e consultar histórico."""

    @abstractmethod
    async def save(self, evidence: Evidence) -> str: ...

    @abstractmethod
    async def load(self, hash_or_path: str) -> Optional[Evidence]: ...

    @abstractmethod
    async def list_for_mission(self, mission_id: str) -> list[Evidence]: ...