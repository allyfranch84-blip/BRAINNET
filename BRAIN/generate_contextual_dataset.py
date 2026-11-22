import json
import time
import urllib.request
import urllib.error
import os

import os, sys
API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
if not API_KEY:
    print("ERRO: defina a variável de ambiente OPENROUTER_API_KEY antes de rodar.")
    sys.exit(1)
URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "anthropic/claude-sonnet-4.6" 

PROMPT_SISTEMA = """Você é o Gerador de Dataset Contextual da BRAINNET.
Sua tarefa é gerar exemplos de comandos ambíguos no Windows, acompanhados do contexto, para treinar um modelo de linguagem a inferir a INTENÇÃO correta.

Formato de saída obrigatório (JSONL, um por linha):
{"texto": "abra isso", "contexto": {"janela": "Bloco de Notas", "processo": "notepad.exe"}, "roles": {"action": "CLICK", "target": "janela", "domain": "DIGITAL_UI"}}

Regras de Geração:
1. DÊIXIS: "abra isso", "clique aí", "fecha essa janela". O contexto dita o alvo (ex: janela do Brave, botão Salvar).
2. METÁFORA/SOCIAL: "abra a mente", "abra o coração". O action deve ser null, domain SOCIAL_AFFECT.
3. FÍSICO NO PC: "abra a geladeira", "abre a porta". action null, domain PHYSICAL_WORLD.
4. COMPOSTO: "abra o brave e pesquise X", "abra o notepad e digite Y".
5. SLANG/ERROS: "abre o zap", "abrir a rede". Mapeie "zap" para "whatsapp" e domain DIGITAL_UI.

Retorne EXATAMENTE o JSON por linha, sem markdown, sem explicações."""

def gerar_exemplos():
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": PROMPT_SISTEMA}, 
            {"role": "user", "content": "Gere 10 exemplos em JSONL."}
        ],
        "temperature": 0.7
    }

    req = urllib.request.Request(URL, data=json.dumps(payload).encode("utf-8"), headers=headers)
    
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print("Limite de requisições atingido. Dormindo 15 segundos...")
            time.sleep(15)
            return "" # Retorna vazio para tentar de novo
        else:
            print(f"Erro HTTP: {e.code} - {e.reason}")
            raise
    except Exception as e:
        print(f"Erro: {e}")
        raise

if __name__ == "__main__":
    os.makedirs("dataset", exist_ok=True)
    arquivo = open("dataset/dataset_contextual.jsonl", "w", encoding="utf-8")
    
    total_linhas = 0
    while total_linhas < 1000:
        try:
            print(f"Gerando lote... Total atual: {total_linhas}")
            texto = gerar_exemplos()
            
            if not texto:
                continue # Se deu erro 429, pula para o próximo loop
                
            for linha in texto.splitlines():
                linha = linha.strip()
                # Filtro de segurança para garantir que só entra JSON puro
                if linha.startswith("{") and "texto" in linha and "roles" in linha:
                    try:
                        json.loads(linha) # Valida o JSON antes de salvar
                        arquivo.write(linha + "\n")
                        total_linhas += 1
                    except json.JSONDecodeError:
                        pass # Ignora se o Claude gerou uma linha pela metade
            
            time.sleep(4) # Pausa entre lotes para não estourar o limite
        except KeyboardInterrupt:
            print("\nInterrompido pelo usuário.")
            break
        except Exception as e:
            print(f"Erro no lote: {e}. Tentando novamente em 10s...")
            time.sleep(10)
            
    arquivo.close()
    print(f"Concluído! {total_linhas} exemplos salvos em dataset_contextual.jsonl")