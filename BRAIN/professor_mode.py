"""Restricted literal grammar for user-authorized demonstrations; no LLM/eval."""
import re


def normalize_professor_voice(text):
    aliases = {"win": "win", "windows": "win", "enter": "enter", "tecla enter": "enter", "apertar enter": "enter",
               "espaço": "space", "espaco": "space", "tecla espaço": "space",
               "seta para baixo": "down", "seta para cima": "up",
               "seta para esquerda": "left", "seta para direita": "right"}
    key = aliases.get(" ".join(text.casefold().strip().split()))
    return f"tecla {key}" if key else text


def parse_professor_step(text):
    raw = text.strip()
    raw = normalize_professor_voice(raw)
    wait = re.fullmatch(r"aguarde\s+(\d+(?:[.,]\d+)?)\s+segundos?", raw, re.I)
    if wait:
        seconds = float(wait.group(1).replace(",", "."))
        if not 0 <= seconds <= 300:
            raise ValueError("Espera deve ser de 0 a 300 segundos")
        return {"acao": "WAIT", "seconds": seconds}
    typing = re.fullmatch(r"digite\s+(.+)", raw, re.I | re.S)
    if typing:
        content = typing.group(1)
        quotes = {'"': '"', "'": "'", '“': '”'}
        if len(content) > 1 and content[0] in quotes and content[-1] == quotes[content[0]]:
            content = content[1:-1]
        if not content or len(content) > 10000:
            raise ValueError("Texto de demonstracao deve ter de 1 a 10000 caracteres")
        return {"acao": "TYPE", "text": content}
    key = re.fullmatch(r"(?:tecla|aperte|pressione|apertar)\s+(.+)", raw, re.I)
    if key:
        aliases = {"windows": "win", "control": "ctrl", "escape": "esc", "retorno": "enter"}
        keys = [aliases.get(part, part) for part in re.split(r"\s*\+\s*", key.group(1).casefold().strip())]
        if not keys or len(keys) > 4 or any(not re.fullmatch(r"win|ctrl|alt|shift|enter|tab|esc|backspace|space|up|down|left|right|[a-z0-9]", part) for part in keys):
            raise ValueError("Teclas nao suportadas; exemplos: tecla Win, tecla Enter, tecla ctrl+s")
        return {"acao": "HOTKEY", "keys": keys}
    click = re.fullmatch(r"clique(?:\s+em)?\s+(-?\d+)\s*(?:,\s*|\s+)(-?\d+)", raw, re.I)
    if click:
        x, y = int(click.group(1)), int(click.group(2))
        if not all(-(2**31) <= value < 2**31 for value in (x, y)):
            raise ValueError("Coordenadas fora do limite Win32")
        return {"acao": "CLICK", "x": x, "y": y}
    raise ValueError("Use tecla Win, tecla Enter, digite <texto> ou clique em <x> <y>. Nenhum LLM foi chamado.")


def _split_professor_steps(raw):
    phrases, start, quote = [], 0, None
    pairs = {'"': '"', "'": "'", '“': '”'}
    for index, char in enumerate(raw):
        if quote:
            if char == quote:
                quote = None
        elif char in pairs and (index == 0 or raw[index - 1].isspace()):
            quote = pairs[char]
        elif char == ";":
            phrases.append(raw[start:index].strip())
            start = index + 1
    if quote:
        raise ValueError("Feche as aspas do texto antes de executar os passos")
    phrases.append(raw[start:].strip())
    return phrases


def parse_complete_lesson(text):
    parts = re.sub(r"^/professor\s+", "", text, flags=re.I).split("|", 2)
    if len(parts) != 3 or "|" in parts[2] or not re.fullmatch(r"[\w-]{1,64}", parts[1].strip()):
        return None  # Legacy interactive syntax.
    concept, purpose, raw = (part.strip() for part in parts)
    if not re.fullmatch(r"[\w-]{1,40}", concept):
        raise ValueError("Nome de conceito invalido")
    phrases = _split_professor_steps(raw)
    if not 1 <= len(phrases) <= 100 or any(not part for part in phrases):
        raise ValueError("Informe de 1 a 100 passos, separados por PONTO E VÍRGULA (;)")
    steps = [{"passo":i, **parse_professor_step(part)} for i,part in enumerate(phrases,1)]
    return concept.casefold(), purpose, phrases, steps
