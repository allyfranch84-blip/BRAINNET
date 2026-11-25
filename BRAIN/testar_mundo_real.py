# =============================================================================
# testar_mundo_real.py
# =============================================================================

import asyncio
from council.playwright_browser import PlaywrightBrowserAdapter
from council.playwright_chat import WebConversationProvider, CHATGPT_PROFILE

async def main():
    print("🤖 Iniciando Brainnet (Arquitetura SiteProfile)...")
    
    THORIUM_PATH = r"A:\Thorium\Application\thorium.exe"
    
    browser = PlaywrightBrowserAdapter(
        headless=False, 
        profile_name="chatgpt",
        executable_path=THORIUM_PATH
    )
    
    # Usa o WebConversationProvider passando o Perfil do ChatGPT
    chatgpt = WebConversationProvider(CHATGPT_PROFILE, browser)
    
    try:
        print("\nEnviando prompt para o ChatGPT...")
        await chatgpt.send_prompt("Qual é a capital do Brasil? Responda em uma frase curta.")
        
        print("\nAguardando a resposta (Estabilidade de Texto)...")
        success = await chatgpt.wait_generation(timeout=60)
        
        if success:
            response = await chatgpt.read_response()
            print("\n" + "="*50)
            print("🗣️  RESPOSTA EXTRAÍDA:")
            print(response.content)
            print("="*50 + "\n")
        else:
            print("❌ Timeout ao esperar a geração da resposta.")
        
    except Exception as e:
        print(f"\n❌ Ocorreu um erro: {e}")
    finally:
        print("Fechando navegador...")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())