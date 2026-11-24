"""Fail-closed input and output contract for the intent parser; no execution."""
import re


def parse_supervised_mouse_move(text):
    """Parse a small relative move as a proposal, never as authorization."""
    if not isinstance(text, str):
        return None
    if re.fullmatch(r'\s*(?:mova|mover|movimente)\s+o\s+mouse\s+em\s+qualquer\s+dire[cç][aã]o\s*[.!]?\s*', text, re.I):
        return {'action': 'MOUSE_MOVE', 'direction_delegated': True,
                'distance_delegated': True, 'maximum_distance': 20,
                'click': False, 'execution_authorized': False, 'status': 'NEEDS_OBSERVATION'}
    match = re.fullmatch(r'\s*(?:mova|mover|movimente)\s+o\s+mouse\s+(?:lentamente\s+)?(\d{1,3})\s+p[ií]xels?\s+para\s+(?:a\s+)?(direita|esquerda|cima|baixo)\s*,?\s*sem\s+clicar\s*[.!]?\s*', text, re.I)
    if not match:
        return None
    distance = int(match.group(1))
    if not 1 <= distance <= 100:
        return None
    direction = match.group(2).casefold()
    dx, dy = {'direita': (distance, 0), 'esquerda': (-distance, 0),
              'cima': (0, -distance), 'baixo': (0, distance)}[direction]
    return {'action': 'MOUSE_MOVE', 'dx': dx, 'dy': dy, 'click': False,
            'speed': 'slow_requested', 'execution_authorized': False, 'status': 'PROPOSED'}


def normalize_input(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 16000:
        return "", True
    unquoted = re.sub(r'''"[^"]*"|'[^']*'|“[^”]*”''', "", text)
    if re.search(r"\b(?:não|nao|nunca|jamais)\b", unquoted, re.I):
        return text, True
    text = re.sub(r"\bzap\s+zap\b", "whatsapp", text, flags=re.I)
    text = re.sub(r"^abre\b", "abra", text, flags=re.I)
    return text.strip(), False


def validate_roles(parsed):
    if not isinstance(parsed, dict) or set(parsed) != {"action", "target", "domain"}:
        raise ValueError("Resposta fora do schema de papéis")
    action, target, domain = (parsed[key] for key in ("action", "target", "domain"))
    if action not in ("OPEN", "TYPE", "CLICK", "SEARCH", "WAIT", None):
        raise ValueError("Ação fora do schema")
    if domain not in ("DIGITAL_UI", "PHYSICAL_WORLD", "LOGICAL_MATH", "SOCIAL_AFFECT", None):
        raise ValueError("Domínio fora do schema")
    if target is not None and (not isinstance(target, str) or len(target) > 16000):
        raise ValueError("Alvo fora do schema")
    if isinstance(target, str) and target.strip().casefold() in ("", "null", "isso", "aquilo", "algo", "alguma coisa"):
        target = None
    return {"action": action, "target": target, "domain": domain}


def analyze_literal_intent(text):
    """Taxonomia conservadora: descreve a intenção; nunca autoriza execução."""
    from system_intent import PHYSICAL, system_launch_target, is_unqualified_physical_door
    normalized, negated = normalize_input(text)
    result = {'action': None, 'domain': None, 'target': None, 'negated': negated,
              'ambiguous': True, 'needs_context': True, 'execution_authorized': False,
              'intent_kind': None, 'canonical_target': None}
    if not normalized or negated:
        if normalized and negated:
            result['intent_kind'] = 'NEGATED'
        return result
    # A multi-step request cannot be reduced to one application target.
    if re.search(r'\s+e\s+(?:abra|abre|abrir|inicie|desenhe|pinte|clique|pesquise|digite)\b', normalized, re.I):
        result['intent_kind'] = 'COMPOUND'
        return result
    if re.match(r'^\s*(?:como|qual|quem|quando|onde|por que|o que)\b', normalized, re.I):
        result['intent_kind'] = 'QUESTION'
        return result
    if re.match(r'^\s*(?:abra|abre|abrir|inicie)\s+(?:seu|seu\s+pr[oó]prio)\s+cora[cç][aã]o\b', normalized, re.I):
        result.update(domain='SOCIAL_AFFECT', needs_context=False)
        return result
    if re.match(r'^\s*(?:abra|abre|abrir|inicie)\b', normalized, re.I):
        if re.search(PHYSICAL, normalized, re.I) or is_unqualified_physical_door(normalized):
            result.update(action='OPEN', domain='PHYSICAL_WORLD', ambiguous=False, needs_context=False)
            return result
        target=system_launch_target(normalized)
        if target:
            canonical = {'paint':'Paint', 'bloco de notas':'Notepad', 'editor de texto':'Notepad', 'notepad':'Notepad'}.get(target, target)
            result.update(action='OPEN', domain='DIGITAL_UI', target=target,
                          intent_kind='OPEN_APP', canonical_target=canonical,
                          ambiguous=False, needs_context=False)
        return result
    if re.match(r'^\s*(?:clique|clicar|click)\b', normalized, re.I):
        result.update(action='CLICK',domain='DIGITAL_UI')
        return result
    return result
