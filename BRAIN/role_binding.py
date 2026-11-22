"""JSON-safe role slots; substitution never evaluates text or mutates templates."""
from copy import deepcopy
import re

SLOT = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")


def encode_open_concept(vsa):
    return vsa.bind(vsa.role_action, vsa.text_to_hypervector("ABRIR_APP"))


def substitute_slots(pipeline, bindings):
    if not isinstance(bindings, dict):
        raise ValueError("Bindings devem ser um dicionario")
    def replace(match):
        name = match.group(1)
        if name not in bindings or not isinstance(bindings[name], str) or not bindings[name].strip():
            raise ValueError(f"Slot {name} sem valor explicito")
        return bindings[name]
    def visit(value):
        if isinstance(value, str):
            return SLOT.sub(replace, value)
        if isinstance(value, list):
            return [visit(item) for item in value]
        if isinstance(value, dict):
            return {key: visit(item) for key, item in value.items()}
        return deepcopy(value)
    return visit(pipeline)


def abstract_app_demonstration(steps, app):
    if not isinstance(app, str) or not app.strip():
        raise ValueError("Informe o nome do aplicativo digitado")
    core = [step for step in steps if step.get("acao") != "WAIT"]
    if len(core) != 3 or [step.get("acao") for step in core] != ["HOTKEY", "TYPE", "HOTKEY"]:
        raise ValueError("A meta-primitiva abrir app exige Win -> digite o app -> Enter; coordenadas nao sao generalizadas automaticamente")
    if core[0].get("keys") != ["win"] or core[2].get("keys") != ["enter"]:
        raise ValueError("A demonstracao de abertura deve usar Win e Enter")
    if core[1].get("text", "").strip().casefold() != app.strip().casefold():
        raise ValueError("O nome informado nao corresponde ao aplicativo digitado na demonstracao")
    result = deepcopy(steps)
    for step in result:
        if step.get("acao") == "TYPE":
            step["text"] = "{APP_ALVO}"
    return {"passos": result, "professor_verified": True, "meta_primitive": "OPEN_APP",
            "slot_roles": {"APP_ALVO": "application"}, "concept_encoding": "FHRR_ACTION_V1",
            "meta_pipeline": [{"acao": "OPEN_APP", "app": "{SLOT_APP}"}]}
