import argparse
import hashlib
import json
import os
import random
import time
import requests
from pathlib import Path

ROLES_PROMPT = (
    "Você é um parser estrito. Extraia as entidades do texto do usuário. "
    "Não explique, não converse. Retorne APENAS um JSON válido. "
    "Se houver negação, action deve ser null. "
    "Se houver ambiguidade, target deve ser null. "
    'Campos: {"action":"OPEN|TYPE|CLICK|SEARCH|WAIT|null",'
    '"target":"texto|null",'
    '"domain":"DIGITAL_UI|PHYSICAL_WORLD|LOGICAL_MATH|null"}.'
)

PIPELINE_PROMPT = (
    "Compile o comando em um pipeline Windows. Retorne APENAS JSON "
    'no formato {"passos":[...]}. '
    "Primitivas: OPEN_APP(app), TYPE(text), HOTKEY(keys), WAIT(seconds). "
    "Não invente coordenadas ou passos adicionais. "
    "Pesquisar no navegador: OPEN_APP, Ctrl+L, TYPE, Enter. "
    "Salvar no editor: Ctrl+Shift+S, TYPE(caminho), Enter."
)

SCHEMA_STR = """
{
  "roles": {
    "action": "OPEN|TYPE|CLICK|SEARCH|WAIT|null",
    "target": "texto|null",
    "domain": "DIGITAL_UI|PHYSICAL_WORLD|LOGICAL_MATH|null"
  },
  "json_perfeito": {
    "passos": [
      {"acao": "OPEN_APP", "app": "nome"},
      {"acao": "TYPE", "text": "texto"},
      {"acao": "HOTKEY", "keys": ["ctrl", "c"]},
      {"acao": "WAIT", "seconds": 1.0}
    ]
  }
}
"""

def step(action, **kwargs):
    return {"acao": action, **kwargs}

# NOVO GERADOR DINÂMICO (Cria até 500 comandos únicos)
def cases(count=500):
    apps = ["brave", "whatsapp", "notepad", "code", "calc", "explorer", "terminal", "word", "excel"]
    verbs = ["Abra", "Inicie", "Feche", "Maximize", "Minimize", "Foque"]
    items = ["documento", "arquivo", "planilha", "código", "texto", "imagem"]
    folders = ["Área de Trabalho", "Documentos", "Downloads", "C:", "D:"]
    
    random.seed(42) # Garante que os comandos sejam sempre os mesmos
    
    generated = 0
    i = 0
    while generated < count:
        app = random.choice(apps)
        verb = random.choice(verbs)
        text = f"Registro {i}: {random.choice(items)} teste, pontuação! Tudo certo?"
        folder = random.choice(folders)
        path = rf"C:\Users\Public\{folder}\brainnet_{i}.txt"
        query = f"documentação {random.choice(items)} exemplo {i}"
        delay = float(random.randint(1, 10))
        
        yield (
            f"{verb} o {app} e aguarde {int(delay)} segundos.",
            {"action": "OPEN", "target": app, "domain": "DIGITAL_UI"},
            [step("OPEN_APP", app=app), step("WAIT", seconds=delay)],
        )
        generated += 1
        if generated >= count: break
        
        yield (
            f"No {random.choice(['notepad', 'code'])} já aberto, digite {json.dumps(text, ensure_ascii=False)} e salve como {path}.",
            {"action": "TYPE", "target": text, "domain": "DIGITAL_UI"},
            [step("TYPE", text=text), step("HOTKEY", keys=["ctrl", "shift", "s"]), step("TYPE", text=path), step("HOTKEY", keys=["enter"])],
        )
        generated += 1
        if generated >= count: break
        
        yield (
            f"Pesquise no {random.choice(['brave', 'chrome', 'edge'])} sobre {query}.",
            {"action": "SEARCH", "target": query, "domain": "DIGITAL_UI"},
            [step("OPEN_APP", app="brave"), step("HOTKEY", keys=["ctrl", "l"]), step("TYPE", text=query), step("HOTKEY", keys=["enter"])],
        )
        generated += 1
        if generated >= count: break
        
        yield (
            f"Aguarde {int(delay)} segundos, abra {app} e aguarde {int(delay)} segundos.",
            {"action": "WAIT", "target": None, "domain": "DIGITAL_UI"},
            [step("WAIT", seconds=delay), step("OPEN_APP", app=app), step("WAIT", seconds=delay)],
        )
        generated += 1
        if generated >= count: break
        
        yield (
            f"Abra notepad, digite {json.dumps(text, ensure_ascii=False)} e salve como {path}.",
            {"action": "OPEN", "target": "notepad", "domain": "DIGITAL_UI"},
            [step("OPEN_APP", app="notepad"), step("TYPE", text=text), step("HOTKEY", keys=["ctrl", "shift", "s"]), step("TYPE", text=path), step("HOTKEY", keys=["enter"])],
        )
        generated += 1
        i += 1

def request_openrouter(api_key, command, model_name):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost",
        "X-Title": "BRAINNET-Distill"
    }
    prompt = (
        ROLES_PROMPT + "\n" + PIPELINE_PROMPT + 
        f"\n\nRetorne o JSON estritamente neste formato:\n{SCHEMA_STR}" +
        f"\n\nComando do usuário: {json.dumps(command, ensure_ascii=False)}"
    )
    
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.0
    }

    response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    return json.loads(response.json()["choices"][0]["message"]["content"])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api_key", required=True, help="Sua chave sk-or-v1-...")
    parser.add_argument("--model", default="anthropic/claude-sonnet-5.5", help="Modelo da OpenRouter")
    parser.add_argument("--output", default="dataset_distill_claude.jsonl")
    args = parser.parse_args()

    output = Path(args.output)
    accepted = set()

    if output.exists():
        for line in output.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            accepted.add(row["id"])

    failures = 0
    print(f"Iniciando colheita com {args.model}. Arquivo: {output}")

    with output.open("a", encoding="utf-8") as stream:
        for command, roles_expected, steps_expected in cases(count=500):
            identifier = hashlib.sha256(command.encode()).hexdigest()
            if identifier in accepted:
                continue

            try:
                generated = request_openrouter(args.api_key, command, args.model)
                
                if "roles" not in generated or "json_perfeito" not in generated:
                    raise ValueError("JSON faltando chaves principais")
                
                row = {
                    "id": identifier,
                    "comando": command,
                    **generated,
                    "teacher": args.model,
                    "source": "synthetic_claude",
                    "physically_validated": False,
                }
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                stream.flush()
                accepted.add(identifier)
                print(f"{len(accepted)}/500", flush=True)
                
                time.sleep(2.0) # Pausa segura para não estourar o Rate Limit

            except Exception as error:
                print(f"Erro no comando: {command[:30]}... -> {error}", flush=True)
                failures += 1
                time.sleep(5) 

    print(f"Concluído! Aceitos: {len(accepted)}; rejeitados nesta rodada: {failures}")

if __name__ == "__main__":
    main()