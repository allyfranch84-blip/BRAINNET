# =============================================================================
# council/playwright_chat.py — Adaptador Universal Baseado em SiteProfile
# =============================================================================

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional, List

from .ports import ChatPort, ChatTurn
from .playwright_browser import PlaywrightBrowserAdapter

logger = logging.getLogger("Council.WebChat")

# =============================================================================
# SITE PROFILES (Configuração pura, sem lógica)
# =============================================================================

@dataclass
class SiteProfile:
    name: str
    url: str
    textarea_selectors: List[str]
    send_button_selectors: List[str]
    response_selectors: List[str]

# Perfis prontos. Fáceis de manter.
CHATGPT_PROFILE = SiteProfile(
    name="ChatGPT",
    url="https://chatgpt.com",
    textarea_selectors=['#prompt-textarea', 'textarea[data-id]', 'textarea'],
    send_button_selectors=['button[data-testid="send-button"]', 'button[aria-label*="Send"]', 'button[aria-label*="Enviar"]'],
    response_selectors=['[data-message-author-role="assistant"]', 'article[data-testid]', '.markdown']
)

DEEPSEEK_PROFILE = SiteProfile(
    name="DeepSeek",
    url="https://chat.deepseek.com",
    textarea_selectors=['textarea#chat-input', 'textarea'],
    send_button_selectors=['button[aria-label*="Send"]', 'div[role="button"][aria-label*="Send"]'],
    response_selectors=['.ds-markdown', '.markdown', '[class*="message"]']
)

# =============================================================================
# PROVIDER UNIVERSAL
# =============================================================================

class WebConversationProvider(ChatPort):
    def __init__(self, profile: SiteProfile, browser: PlaywrightBrowserAdapter):
        self.profile = profile
        self.browser = browser
        self.is_open = False
        self.last_response = ""

    async def _find_element(self, selectors: List[str]):
        """Tenta cada seletor da lista até achar um visível."""
        if not self.browser.page: return None
        for sel in selectors:
            try:
                locator = self.browser.page.locator(sel).first
                if await locator.is_visible():
                    return locator
            except Exception:
                continue
        return None

    async def _ensure_open(self):
        if not self.is_open:
            await self.browser.open(self.profile.url)
            self.is_open = True
            
            # AUTO-DETECÇÃO DE LOGIN
            print(f"\nVerificando login no {self.profile.name}...")
            is_logged_in = False
            for _ in range(10): # Tenta por 10 segundos
                if await self._find_element(self.profile.textarea_selectors):
                    is_logged_in = True
                    break
                await asyncio.sleep(1)
                
            if is_logged_in:
                print("✅ Login detectado com sucesso!")
            else:
                print(f"\n⚠️ ATENÇÃO: A caixa de texto do {self.profile.name} não foi encontrada.")
                print("Faça o login na janela que abriu e aperte ENTER no terminal.")
                input("Pressione ENTER para continuar...")

    async def send_prompt(self, prompt: str) -> None:
        await self._ensure_open()
        
        # 1. Encontra a caixa de texto
        textarea = await self._find_element(self.profile.textarea_selectors)
        if not textarea:
            raise RuntimeError(f"Caixa de texto não encontrada no {self.profile.name}")

        await textarea.fill(prompt)
        
        # 2. Estratégia de Envio em Cascata
        logger.info("Tentando enviar mensagem...")
        
        # Nível 1: Botão aria-label
        btn = await self._find_element(self.profile.send_button_selectors)
        if btn:
            await btn.click()
            logger.info("Enviado via botão aria-label.")
            return

        # Nível 2: Enter
        logger.info("Botão não encontrado. Tentando Enter...")
        await self.browser.page.keyboard.press("Enter")

    async def _get_last_response_text(self) -> str:
        """Usa a cascata de seletores para pegar o texto da última resposta."""
        if not self.browser.page: return ""
        
        for sel in self.profile.response_selectors:
            try:
                locator = self.browser.page.locator(sel)
                if await locator.count() > 0:
                    # Pega a última mensagem visível
                    text = await locator.last.inner_text()
                    if text.strip():
                        return text
            except Exception:
                continue
        return ""

    async def wait_generation(self, timeout: float = 180.0) -> bool:
        """
        Usa Estabilidade de Texto em vez de depender do botão 'Stop'.
        Fica lendo a última mensagem até ela parar de mudar por 2 segundos.
        """
        if not self.browser.page: return False
        
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