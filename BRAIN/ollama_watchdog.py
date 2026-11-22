import os
import subprocess
import time
import urllib.request
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [OLLAMA_WD] %(message)s")
logger = logging.getLogger("Watchdog")

OLLAMA_HOST = "127.0.0.1:11435"
OLLAMA_URL = f"http://{OLLAMA_HOST}/api/version"

def is_ollama_alive():
    try:
        with urllib.request.urlopen(OLLAMA_URL, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False

def start_ollama():
    logger.info("Iniciando Ollama...")
    env = os.environ.copy()
    env["OLLAMA_HOST"] = OLLAMA_HOST
    env["OLLAMA_MODELS"] = r"A:\OLLAMA_MODELS"
    env["OLLAMA_VULKAN"] = "1"
    # Inicia em background sem abrir janela
    subprocess.Popen(["ollama", "serve"], env=env, creationflags=subprocess.CREATE_NO_WINDOW)
    time.sleep(5) # Espera inicialização

if __name__ == "__main__":
    logger.info("Watchdog iniciado. Monitorando Ollama na porta 11435.")
    while True:
        if not is_ollama_alive():
            logger.warning("Ollama caiu! Reiniciando...")
            subprocess.run(["taskkill", "/IM", "ollama.exe", "/F"], capture_output=True)
            start_ollama()
        time.sleep(10) # Checa a cada 10 segundos
