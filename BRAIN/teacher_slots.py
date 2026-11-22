"""Literal teacher bindings and deterministic message-route instantiation."""
from copy import deepcopy
import re
from role_binding import substitute_slots

SLOTS = {"app": "APP_ALVO", "contato": "CONTATO", "msg": "MENSAGEM"}


def parse_variables(text):
    pattern = r'''\s*(app|contato|msg)\s*=\s*("[^"]*"|'[^']*'|.*?)(?=\s*,\s*(?:app|contato|msg)\s*=|$)'''
    bindings, cursor = {}, 0
    for match in re.finditer(pattern, text, re.I):
        if text[cursor:match.start()].strip(" ,"):
            raise ValueError("Use app=..., contato=..., msg=...")
        key, value = match.group(1).lower(), match.group(2).strip()
        if len(value) > 1 and value[0] in "\"'" and value[-1] == value[0]:
            value = value[1:-1]
        if key in bindings or not value or len(value) > 10000 or re.search(r"\{[A-Z][A-Z0-9_]*\}", value):
            raise ValueError("Variável repetida, vazia ou inválida")
        bindings[key] = value
        cursor = match.end()
    if text[cursor:].strip() or not bindings:
        raise ValueError("Use app=..., contato=..., msg=...")
    return bindings


def abstract_message(steps, variables):
    if set(variables) != set(SLOTS) or len({v.casefold() for v in variables.values()}) != 3:
        raise ValueError("Informe app, contato e msg com valores distintos")
    result, found = deepcopy(steps), set()
    for step in result:
        if step.get("acao") == "TYPE":
            for key, value in variables.items():
                if step.get("text", "").strip().casefold() == value.strip().casefold():
                    step["text"] = "{" + SLOTS[key] + "}"
                    found.add(key)
                    break
    if found != set(SLOTS):
        raise ValueError("Cada variável deve corresponder a um passo TYPE demonstrado")
    return {"passos": result, "meta_primitive": "SEND_MESSAGE",
            "slot_roles": {"APP_ALVO": "application", "CONTATO": "recipient", "MENSAGEM": "message"},
            "slot_defaults": {"APP_ALVO": variables["app"]}}


def instantiate_message(pdag, text):
    match = re.fullmatch(r"(?:no\s+(.+?)\s*[,;]?\s+)?(?:envie|enviar)\s+(?:uma\s+)?mensagem\s+para\s+(.+?)\s+dizendo\s+(.+)", text.strip(), re.I | re.S)
    if not match or pdag is None or pdag.is_verified_demonstration("enviar_mensagem_generico") is not True:
        return None
    route = pdag.find_myelinated_path("trajectory:enviar_mensagem_generico", exact_only=True)
    if not isinstance(route, dict) or route.get("meta_primitive") != "SEND_MESSAGE":
        return None
    app = match.group(1) or route.get("slot_defaults", {}).get("APP_ALVO")
    bindings = {"APP_ALVO": app, "CONTATO": match.group(2).strip(), "MENSAGEM": match.group(3).strip()}
    template = deepcopy(route["passos"])
    message_indexes = [i for i, step in enumerate(template) if step.get("acao") == "TYPE" and step.get("text") == "{MENSAGEM}"]
    if not message_indexes:
        raise ValueError("Rota de mensagem sem slot MENSAGEM")
    for i, step in enumerate(template):
        if i in message_indexes or (i > min(message_indexes) and step.get("acao") == "HOTKEY" and step.get("keys") == ["enter"]):
            step["target_contact"] = "{CONTATO}"
    result = substitute_slots({"passos": template}, bindings)
    return {"passos": result["passos"], "pipeline": [dict(p=step["acao"], **{k: v for k, v in step.items() if k not in ("acao", "passo", "feedback")}) for step in result["passos"]],
            "monologo_socratico": ["Rota de mensagem instanciada por slots sem LLM."]}
