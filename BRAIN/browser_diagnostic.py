# =============================================================================
# browser_diagnostic.py — Verificador de Ambiente
# =============================================================================

import asyncio
from playwright.async_api import async_playwright
import sys

async def main():
    print("=== BRAINNET BROWSER DIAGNOSTIC ===\n")
    print(f"✓ Python: {sys.version.split()[0]}")
    
    async with async_playwright() as p:
        print("✓ Playwright: OK")
        
        # 1. Testa Chrome do sistema
        try:
            browser = await p.chromium.launch(channel="chrome", headless=True)
            version = browser.version
            await browser.close()
            print(f"✓ Chrome (Sistema): OK (v{version})")
        except Exception:
            print("✗ Chrome (Sistema): NÃO ENCONTRADO")

        # 2. Testa Chromium do Playwright
        try:
            browser = await p.chromium.launch(headless=True)
            version = browser.version
            await browser.close()
            print(f"✓ Chromium (Playwright): OK (v{version})")
        except Exception as e:
            print(f"✗ Chromium (Playwright): FALTANDO - Rode 'playwright install chromium'")
            
    print("\nRecomendação: O Brainnet tentará usar o Chrome primeiro, depois o Chromium.")

if __name__ == "__main__":
    asyncio.run(main())