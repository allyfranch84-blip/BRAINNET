# =============================================================================
# council/fake_ports.py — Implementações de Simulação (Modo P52)
# =============================================================================

import asyncio
from typing import Optional
from .ports import BrowserPort, ChatPort, ElementRef, ChatTurn, Evidence

class FakeBrowserAdapter(BrowserPort):
    """Simula um navegador. Retorna o que pedirmos."""
    def __init__(self):
        self.current_url = ""

    async def open(self, url: str) -> None:
        self.current_url = url
        print(f"  [FakeBrowser] Abrindo URL: {url}")

    async def focus(self) -> None:
        print("  [FakeBrowser] Focando janela")

    async def click(self, target: ElementRef | str) -> None:
        print(f"  [FakeBrowser] Clicando em: {target}")

    async def scroll(self, direction: str, amount: int = 500) -> None:
        pass

    async def paste(self, text: str) -> None:
        print(f"  [FakeBrowser] Colando texto ({len(text)} chars)")

    async def copy(self) -> str:
        return "Texto copiado simulado"

    async def capture(self, path: Optional[str] = None) -> Evidence:
        return Evidence(kind="screenshot", content="fake_screenshot_bytes")

    async def wait_element(self, target: ElementRef | str, timeout: float = 30.0, state: str = "visible") -> ElementRef:
        return ElementRef(id=str(target), text=str(target))

    async def find_text(self, text: str) -> list[ElementRef]:
        return [ElementRef(id="fake_element", text=text)]

    async def send_enter(self) -> None:
        print("  [FakeBrowser] Enviando ENTER")

    async def upload_file(self, path: str, target: ElementRef | str) -> None:
        pass

    async def download(self, url: str, dest: str) -> str:
        return dest

    async def accessibility_tree(self) -> dict:
        return {"role": "document", "text": "Simulated UI"}

    async def close(self) -> None:
        print("  [FakeBrowser] Fechando navegador")


class FakeConversationProvider(ChatPort):
    """Simula um LLM (ChatGPT ou DeepSeek)."""
    def __init__(self, name: str):
        self.name = name
        self.last_prompt = ""
        self.mock_response = f"Olá! Eu sou o {self.name}. A capital do Brasil é Brasília."

    async def send_prompt(self, prompt: str) -> None:
        self.last_prompt = prompt
        print(f"  [FakeChat:{self.name}] Prompt enviado: {prompt[:50]}...")

    async def wait_generation(self, timeout: float = 180.0) -> bool:
        print(f"  [FakeChat:{self.name}] Gerando resposta...")
        await asyncio.sleep(0.5) # Simula o tempo de geração
        return True

    async def read_response(self) -> ChatTurn:
        print(f"  [FakeChat:{self.name}] Resposta lida.")
        return ChatTurn(
            role="assistant",
            content=self.mock_response,
            model=self.name
        )

    def extract_code(self, turn: ChatTurn) -> list[dict[str, str]]:
        return []

    def extract_markdown(self, turn: ChatTurn) -> str:
        return turn.content

    def detect_error(self, turn: ChatTurn) -> Optional[str]:
        return None

    async def new_chat(self) -> None:
        pass

    async def continue_chat(self, chat_id: str) -> None:
        pass