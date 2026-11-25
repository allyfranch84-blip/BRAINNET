# =============================================================================
# council/playwright_browser.py — Adaptador Real com Mouse Virtual
# =============================================================================

import asyncio
import base64
import logging
from pathlib import Path
from typing import Optional
from playwright.async_api import async_playwright, Browser, Page

from .ports import BrowserPort, ElementRef, Evidence

logger = logging.getLogger("Council.Browser")

class PlaywrightBrowserAdapter(BrowserPort):
    def __init__(self, headless: bool = False, profile_name: str = "default", executable_path: Optional[str] = None):
        self.headless = headless
        self.executable_path = executable_path
        self.user_data_dir = Path(f"./profiles/{profile_name}").resolve()
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        
        self.pw = None
        self.browser = None
        self.page: Optional[Page] = None

    async def open(self, url: str) -> None:
        if not self.pw:
            self.pw = await async_playwright().start()
            
            launch_args = {
                "user_data_dir": str(self.user_data_dir),
                "headless": self.headless,
                "args": ["--disable-blink-features=AutomationControlled"]
            }

            if self.executable_path:
                logger.info(f"Usando navegador customizado: {self.executable_path}")
                launch_args["executable_path"] = self.executable_path
            
            try:
                self.browser = await self.pw.chromium.launch_persistent_context(**launch_args)
            except Exception as e:
                logger.warning(f"Falha ao abrir navegador customizado ({e}). Usando Chromium padrão...")
                launch_args.pop("executable_path", None)
                self.browser = await self.pw.chromium.launch_persistent_context(**launch_args)
            
            self.page = self.browser.pages[0] if self.browser.pages else await self.browser.new_page()
        
        await self.page.goto(url, wait_until="domcontentloaded")

    async def focus(self) -> None:
        if self.page:
            await self.page.bring_to_front()

    async def click(self, target: ElementRef | str) -> None:
        if not self.page: return
        selector = target if isinstance(target, str) else f"[id='{target.id}']"
        await self.page.click(selector)

    # --- MÉTODOS DE VISÃO E MOUSE VIRTUAL ---
    async def click_at(self, x: float, y: float) -> None:
        """Clica em coordenadas absolutas da tela (mouse virtual)."""
        if not self.page: return
        logger.info(f"Mouse virtual clicando em X:{x}, Y:{y}")
        await self.page.mouse.click(x, y)

    async def get_bounding_box(self, selector: str) -> Optional[dict]:
        """Retorna a posição e tamanho de um elemento na tela."""
        if not self.page: return None
        try:
            element = self.page.locator(selector).first
            return await element.bounding_box()
        except Exception:
            return None
    # ---------------------------------------

    async def scroll(self, direction: str, amount: int = 500) -> None:
        if not self.page: return
        if direction == "down":
            await self.page.mouse.wheel(0, amount)
        elif direction == "up":
            await self.page.mouse.wheel(0, -amount)

    async def paste(self, text: str) -> None:
        if not self.page: return
        await self.page.keyboard.insert_text(text)

    async def copy(self) -> str:
        return "" 

    async def capture(self, path: Optional[str] = None) -> Evidence:
        if not self.page: raise RuntimeError("Navegador não aberto")
        screenshot_bytes = await self.page.screenshot(full_page=False)
        
        if path:
            Path(path).write_bytes(screenshot_bytes)
            
        return Evidence(
            kind="screenshot",
            path=path,
            content=base64.b64encode(screenshot_bytes).decode("utf-8")
        )

    async def wait_element(self, target: ElementRef | str, timeout: float = 30.0, state: str = "visible") -> ElementRef:
        if not self.page: raise RuntimeError("Navegador não aberto")
        selector = target if isinstance(target, str) else f"[id='{target.id}']"
        
        await self.page.wait_for_selector(selector, timeout=timeout*1000, state=state)
        return ElementRef(id=selector)

    async def find_text(self, text: str) -> list[ElementRef]:
        if not self.page: return []
        locator = self.page.get_by_text(text, exact=False)
        count = await locator.count()
        return [ElementRef(id=f"text_locator_{i}", text=text) for i in range(count)]

    async def send_enter(self) -> None:
        if self.page:
            await self.page.keyboard.press("Enter")

    async def upload_file(self, path: str, target: ElementRef | str) -> None:
        pass 

    async def download(self, url: str, dest: str) -> str:
        return dest

    async def accessibility_tree(self) -> dict:
        return {}

    async def close(self) -> None:
        if self.browser:
            await self.browser.close()
        if self.pw:
            await self.pw.stop()