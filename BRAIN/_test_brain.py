import urllib.request
import json
from assistant_prompts import OLLAMA_BASE_URL, MODELO_DEEP

print(f"=== TESTE DE CÉREBRO (OLLAMA EM {OLLAMA_BASE_URL}) ===")
payload = {
    "model": MODELO_DEEP,
    "prompt": "Responda apenas: Cérebro online.",
    "stream": False,
    "options": {"temperature": 0.1}
}
req = urllib.request.Request(
    f"{OLLAMA_BASE_URL}/api/generate",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        print(f"✅ SUCESSO: Resposta do LLM: '{data.get('response', '').strip()}'")
except Exception as e:
    print(f"❌ FALHA: O Ollama não respondeu. Erro: {e}")
