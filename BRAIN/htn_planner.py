"""Ordered goal parsing and table-driven meta-primitives, independent of LLMs."""
import ast
import re
from urllib.parse import quote_plus
from role_binding import substitute_slots
from system_intent import system_launch_target

META_PRIMITIVES = {
    "SCROLL": [{"acao": "SCROLL", "direction": "{DIRECTION}", "clicks": 1}],
    "OPEN_APP": [{"acao": "ENSURE_APP", "app": "{APP_ALVO}"}],
    "TYPE_TEXT": [{"acao": "TYPE", "text": "{TEXTO}"}],
    "CLICK_TEXT": [{"acao": "LOCATE", "target": "{TARGET}"}, {"acao": "CLICK", "target": "{TARGET}"}],
    "SEARCH_APP": [{"acao": "HOTKEY", "keys": ["ctrl", "f"]}, {"acao": "TYPE", "text": "{QUERY}"}, {"acao": "HOTKEY", "keys": ["enter"]}],
    "SEARCH_WEB": [{"acao": "HOTKEY", "keys": ["ctrl", "l"]}, {"acao": "TYPE", "text": "{URL_BUSCA}"}, {"acao": "HOTKEY", "keys": ["enter"]}],
    "SEND_MESSAGE": [
        {"acao": "HOTKEY", "keys": ["ctrl", "f"]}, {"acao": "TYPE", "text": "{DESTINATARIO}"},
        {"acao": "WAIT", "seconds": 0.5}, {"acao": "HOTKEY", "keys": ["enter"]},
        {"acao": "WAIT", "seconds": 0.5}, {"acao": "TYPE", "text": "{MENSAGEM}", "target_contact": "{DESTINATARIO}"},
        {"acao": "HOTKEY", "keys": ["enter"], "target_contact": "{DESTINATARIO}"},
    ],
}


def _unquote(text):
    text = text.strip()
    pairs = {'"': '"', "'": "'", '“': '”'}
    return text[1:-1] if len(text) > 1 and text[0] in pairs and text[-1] == pairs[text[0]] else text


def parse_objectives(text):
    if re.search(r"menu iniciar|start menu", text, re.I):
        return []  # Explicit native-search instructions keep their existing parser.
    context = re.fullmatch(r"no\s+(.+?)\s+((?:mande|envie|diga|digite|escreva|pesquise|busque)\s+.+)", text.strip(), re.I | re.S)
    browser = re.fullmatch(r"(?:pesquise|busque)\s+no\s+(.+?)\s+(?:sobre|por)\s+(.+)", text.strip(), re.I | re.S)
    if context:
        text = f"abra o {context.group(1)} e {context.group(2)}"
    elif browser:
        text = f"abra o {browser.group(1)} e pesquise sobre {browser.group(2)}"
    quoted = [match.span() for match in re.finditer(r'''"[^"]*"|'[^']*'|“[^”]*”''', text)]
    cuts = [match for match in re.finditer(r"(?:\s+e\s+|,\s*)(?=(?:abra|abre|abrir|inicie|pesquise|busque|diga|envie|mande|escreva|digite|redija|componha|crie|role|clique)\b)", text, re.I)
            if not any(start <= match.start() < end for start, end in quoted)]
    parts, cursor = [], 0
    for match in cuts:
        parts.append(text[cursor:match.start()].strip())
        cursor = match.end()
    parts.append(text[cursor:].strip())
    goals = []
    for part in parts:
        opening = re.match(r"^(?:abra|abre|abrir|inicie|execute)\s", part, re.I)
        message = re.fullmatch(r"(?:diga|envie|mande)\s+(.+)\s+(?:para|pra|pro)\s+(.+)", part, re.I | re.S)
        search = re.fullmatch(r"(?:pesquise|busque)\s+(?:(?:por|sobre|na internet|no google)\s+)?(.+)", part, re.I | re.S)
        typing = re.fullmatch(r"(?:escreva|digite|redija|componha|crie)\s+(.+)", part, re.I | re.S)
        click = re.fullmatch(r"clique\s+n[oa]\s+(?:bot[aã]o\s+)?(.+)", part, re.I | re.S)
        if opening:
            target = system_launch_target(part)
            if not target:
                return []
            goals.append({"kind": "OPEN_APP", "roles": {"APP_ALVO": target}})
        elif message:
            recipient = re.sub(r"^[oa]\s+", "", message.group(2), flags=re.I)
            goals.append({"kind": "SEND_MESSAGE", "roles": {"MENSAGEM": _unquote(message.group(1)), "DESTINATARIO": _unquote(recipient)}})
        elif search:
            goals.append({"kind": "SEARCH", "roles": {"QUERY": _unquote(search.group(1))}})
        elif typing:
            raw = typing.group(1).strip()
            goals.append({"kind": "TYPE_TEXT", "roles": {"TEXTO": _unquote(raw)}, "literal": raw != _unquote(raw)})
        elif re.fullmatch(r"role (?:a tela )?para (?:baixo|cima)", part, re.I):
            goals.append({"kind": "SCROLL", "roles": {"DIRECTION": "up" if part.casefold().endswith("cima") else "down"}})
        elif click:
            goals.append({"kind": "CLICK_TEXT", "roles": {"TARGET": _unquote(click.group(1))}})
        else:
            return []
    return goals if goals and goals[0]["kind"] in ("OPEN_APP", "CLICK_TEXT") else []


def _validate_python_artifact(source, require_gui=False):
    """Validate a generated artifact structurally, without executing it."""
    if not isinstance(source, str) or not source.strip():
        raise ValueError("Gerador nao produziu codigo Python")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError("Codigo Python gerado possui sintaxe invalida") from exc
    if require_gui:
        modules, constructors = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "tkinter":
                        modules.add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module == "tkinter":
                constructors.update(alias.asname or alias.name for alias in node.names if alias.name == "Tk")
        found = any(
            isinstance(node, ast.Call) and (
                isinstance(node.func, ast.Name) and node.func.id in constructors or
                isinstance(node.func, ast.Attribute) and node.func.attr == "Tk" and
                isinstance(node.func.value, ast.Name) and node.func.value.id in modules
            ) for node in ast.walk(tree)
        )
        if not found:
            raise ValueError("Codigo gerado nao comprova estrutura de interface tkinter")
    return source.strip()


def compile_objectives(goals, generate_text=None, web_search=False):
    steps, app = [], None
    for goal in goals:
        kind, roles = goal["kind"], dict(goal["roles"])
        if kind == "OPEN_APP":
            app = roles["APP_ALVO"]
            roles["APP_ALVO"] = "notepad" if app in ("bloco de notas", "um bloco de notas", "editor de texto") else app
        code_request = kind == "TYPE_TEXT" and not goal.get("literal") and re.match(r"^(?:(?:um|uma|o|a)\s+)?(?:c[oó]digo|programa|script)\b.*\bpython\b", roles["TEXTO"], re.I | re.S)
        if code_request:
            if generate_text is None:
                raise ValueError("Geracao de codigo nao disponivel")
            instruction = roles["TEXTO"]
            require_gui = bool(re.search(r"\b(?:interface|janela|gr[aá]fica|gui)\b", instruction, re.I))
            roles["TEXTO"] = _validate_python_artifact(generate_text(instruction), require_gui)
        elif kind == "TYPE_TEXT" and not goal.get("literal") and re.match(r"^(?:um[a]?\s+)?(?:poema|poesia|soneto|haicai|conto|hist[oó]ria|reda[cç][aã]o|texto\s+sobre)\b", roles["TEXTO"], re.I):
            if generate_text is None:
                raise ValueError("Geracao criativa nao disponivel")
            roles["TEXTO"] = generate_text(roles["TEXTO"])
        if kind == "SEARCH":
            kind = "SEARCH_WEB" if web_search else "SEARCH_APP"
            roles["URL_BUSCA"] = "https://www.google.com/search?q=" + quote_plus(roles["QUERY"])
        if kind == "SEND_MESSAGE" and not app:
            raise ValueError("Mensagem exige aplicativo explicito")
        template = META_PRIMITIVES.get(kind)
        if template is None:
            raise ValueError("Meta-primitiva nao suportada")
        steps.extend(substitute_slots(template, roles))
    for index, step in enumerate(steps, 1):
        step["passo"] = index
    return {"monologo_socratico": ["Metas decompostas em ordem e instanciadas por papeis explicitos."],
            "passos": steps, "goals": goals}


def compile_primitives(goals, generate_text=None, web_search=False):
    """Native primitive catalog plus legacy step projection for stored routes."""
    plan = compile_objectives(goals, generate_text, web_search)
    names = {"ENSURE_APP": "OPEN_APP", "LOCATE": "LOCATE_VISUAL"}
    plan["pipeline"] = [dict(p=names.get(step["acao"], step["acao"]),
                             **{key: value for key, value in step.items() if key not in ("acao", "passo")})
                        for step in plan["passos"] if step["acao"] != "WAIT"]
    return plan
