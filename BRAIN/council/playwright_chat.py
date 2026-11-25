# =============================================================================
# council/playwright_chat.py — Adaptador Universal com LocatorStrategy
# =============================================================================

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional, List

from .ports import ChatPort, ChatTurn
from .playwright_browser import PlaywrightBrowserAdapter
from .locator import LocatorTarget

logger = logging.getLogger("Council.WebChat")

@dataclass
class SiteProfile:
    name: str
    url: str
    textarea: LocatorTarget
    send_button: LocatorTarget
    response_area: LocatorTarget

# PERFIS DE SITES (Fáceis de dar manutenção)
CHATGPT_PROFILE = SiteProfile(
    name="ChatGPT",
    url="https://chatgpt.com",
    textarea=LocatorTarget(
        name="caixa de texto", 
        css="#prompt-textarea", 
        role="textbox", 
        placeholder="Message ChatGPT"
    ),
    send_button=LocatorTarget(
        name="botão enviar", 
        css='button[data-testid="send-button"]', 
        aria_label="Send"
    ),
    response_area=LocatorTarget(
        name="resposta", 
        css='[data-message-author-role="assistant"]', 
        role="article"
    )
)

DEEPSEEK_PROFILE = SiteProfile(
    name="DeepSeek",
    url="https://chat.deepseek.com",
    textarea=LocatorTarget(name="input", css="textarea#chat-input", placeholder="Send a message"),
    send_button=LocatorTarget(name="botão", css='div[role="button"]', aria_label="Send"),
    response_area=LocatorTarget(name="resposta", css=".ds-markdown", role="article")
)

class WebConversationProvider(ChatPort):
    def __init__(self, profile: SiteProfile, browser: PlaywrightBrowserAdapter):
        self.profile = profile
        self.browser = browser
        self.is_open = False
        self.last_response = ""

    async def _ensure_open(self):
        if not self.is_open:
            await self.browser.open(self.profile.url)
            self.is_open = True
            
            # Auto-detecção de Login
            print(f"\nVerificando login no {self.profile.name}...")
            is_logged_in = False
            for _ in range(10):
                if await self.browser.find(self.profile.textarea, timeout=2000):
                    is_logged_in = True
                    break
                await asyncio.sleep(1)
                
            if is_logged_in:
                print("✅ Login detectado!")
            else:
                print(f"\n⚠️ ATENÇÃO: Faça o login no {self.profile.name} e aperte ENTER no terminal.")
                input("Pressione ENTER para continuar...")

    async def send_prompt(self, prompt: str) -> None:
        await self._ensure_open()
        
        # 1. Achar Caixa de Texto
        textarea = await self.browser.find(self.profile.textarea)
        if not textarea:
            raise RuntimeError(f"Caixa de texto não encontrada no {self.profile.name}")

        await textarea.fill(prompt)
        
        # 2. Estratégia de Envio (Cascata)
        logger.info("Tentando enviar mensagem...")
        
        # Prioridade 1: Botão Enviar (via LocatorStrategy)
        btn = await self.browser.find(self.profile.send_button, timeout=3000)
        if btn:
            await btn.click()
            logger.info("Enviado via botão.")
            return

        # Prioridade 2: Mouse Virtual (Bounding Box da Textarea)
        logger.info("Botão não encontrado. Calculando posição por Visão...")
        box = await textarea.bounding_box()
        if box:
            btn_x = box["x"] + box["width"] - 25
            btn_y = box["y"] + (box["height"] / 2)
            await self.browser.click_at(btn_x, btn_y)
            logger.info("Enviado via mouse virtual.")
            return
            
        # Prioridade 3: Enter (Fallback Final)
        logger.warning("Visão falhou. Usando ENTER.")
        await self.browser.page.keyboard.press("Enter")

    async def _get_last_response_text(self) -> str:
        """Lê a última resposta usando LocatorStrategy."""
        element = await self.browser.find(self.profile.response_area, timeout=2000)
        if element:
            try:
                return await element.inner_text()
            except:
                pass
        return ""

    async def wait_generation(self, timeout: float = 180.0) -> bool:
        """Usa Estabilidade de Texto (Text Polling)."""
        logger.info("Aguardando resposta (Estabilidade de Texto)...")
        start_time = time.time()
        last_text = ""
        stable_count = 0
        
        while (time.time() - start_time) < timeout:
            current_text = await self._get_last_response_text()
            
            if current_text and current_text == last_text:
                stable_count += 1
                if stable_count >= 4: # 4 * 0.5s = 2 segundos estável
                    logger.info("Resposta estabilizada.")
                    self.last_response = current_text
                    return True
            else:
                stable_count = 0
                last_text = current_text
            
            await asyncio.sleep(0.5)
            
        logger.warning("Timeout aguardando resposta.")
        self.last_response = last_text
        return False

    async def read_response(self) -> ChatTurn:
        if not self.last_response:
            self.last_response = await self._get_last_response_text()
        return ChatTurn(role="assistant", content=self.last_response, model=self.profile.name)

    def extract_code(self, turn: ChatTurn) -> list[dict[str, str]]:
        import re
        blocks = re.findall(r"```(?:python)?\n(.*?)```", turn.content, re.DOTALL)
        return [{"language": "python", "code": b.strip()} for b in blocks]

    def extract_markdown(self, turn: ChatTurn) -> str:
        return turn.content

    def detect_error(self, turn: ChatTurn) -> Optional[str]:
        if "usage limit" in turn.content.lower() or "too many requests" in turn.content.lower():
            return "Rate limit atingido no " + self.profile.name
        return None

    async def new_chat(self) -> None:
        await self.browser.open(self.profile.url)
        self.last_response = ""

    async def continue_chat(self, chat_id: str) -> None:
        pass