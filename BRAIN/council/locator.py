# =============================================================================
# council/locator.py — Estratégia de Localização de Elementos
# =============================================================================

from dataclasses import dataclass
from typing import Optional, Any
from playwright.async_api import Page, Locator

@dataclass
class LocatorTarget:
    """Define como encontrar um elemento usando múltiplas estratégias."""
    name: str
    css: Optional[str] = None
    role: Optional[str] = None
    aria_label: Optional[str] = None
    placeholder: Optional[str] = None
    text: Optional[str] = None

async def find_robust_locator(page: Page, target: LocatorTarget, timeout: int = 5000) -> Optional[Locator]:
    """
    Tenta encontrar um elemento na página testando as estratégias em ordem.
    """
    strategies = []
    
    if target.css: strategies.append(page.locator(target.css))
    if target.role: strategies.append(page.get_by_role(target.role)) # type: ignore
    if target.aria_label: strategies.append(page.locator(f'[aria-label*="{target.aria_label}"]'))
    if target.placeholder: strategies.append(page.locator(f'[placeholder*="{target.placeholder}"]'))
    if target.text: strategies.append(page.get_by_text(target.text, exact=False))

    for i, locator in enumerate(strategies):
        try:
            first = locator.first
            await first.wait_for(state="visible", timeout=timeout)
            return first
        except Exception:
            continue # Se falhar, tenta a próxima estratégia

    return None # Falhou em todas