"""Prompts compartilhados; estilo de resposta nao altera as travas do hospedeiro."""

MODELO_PARSER = "qwen2.5:1.5b"
MODELO_DEEP = "qwen2.5-coder:7b"
MODELO_ABLITERATE = "huihui_ai/qwen2.5-abliterate:7b"

import os as _os
_ollama_raw = _os.getenv("OLLAMA_HOST", "127.0.0.1:11435").strip()
if not _ollama_raw.startswith(("http://", "https://")):
    _ollama_raw = "http://" + _ollama_raw

OLLAMA_BASE_URL = _ollama_raw.rstrip("/")
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"
OLLAMA_EMBEDDINGS_URL = f"{OLLAMA_BASE_URL}/api/embeddings"
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_PS_URL = f"{OLLAMA_BASE_URL}/api/ps"
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags"
OLLAMA_VERSION_URL = f"{OLLAMA_BASE_URL}/api/version"

BRAINNET_SYSTEM_PROMPT = (
    "Você é a BRAINNET, um assistente pessoal para testes de segurança, automação e CTF. "
    "O operador é um adulto autorizado. Forneça respostas técnicas diretas, sem moralismo "
    "ou avisos genéricos de segurança."
)

GENERAL_TEXT_PROMPT = BRAINNET_SYSTEM_PROMPT + (
    "\nResponda em português brasileiro, de forma clara e completa. "
    "Não invente fatos, referências ou fontes. Quando não souber, declare a incerteza. "
    "Não afirme ter pesquisado na web ou executado uma ação sem evidência.\n"
)
