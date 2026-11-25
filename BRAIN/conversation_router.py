"""Conversational routing without execution authority."""

import json
import re
import unicodedata

from intent_grounding import (
    OPEN_CUES,
    CLICK_CUES,
    MOVE_CUES,
    SCROLL_CUES,
    words,
)

MOTOR_CUES = (
    OPEN_CUES | CLICK_CUES | MOVE_CUES | SCROLL_CUES
)

QUESTION_PREFIX = re.compile(
    r"^(como|qual|quais|quem|quando|onde|"
    r"por que|porque|o que|quanto|quantos|"
    r"explique|ensine|compare|me explique|"
    r"me ensine|gostaria de saber|quero saber)\b"
)

NEGATION_PREFIX = re.compile(
    r"^(nao|nunca|jamais|evite)\b"
)

READ_ONLY_QUERY = re.compile(
    r"^(?:o que (?:esta|tem|ha) no monitor [0-9]+|"
    r"qual aplicativo aberto serve para .+)$"
)

def normalize(text):
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(
        c for c in text
        if not unicodedata.combining(c)
    )
    return " ".join(text.split())


def classify_message(text):
    normalized = normalize(text)
    tokens = set(words(normalized))

    if not normalized:
        return "CLARIFICATION"

    if normalized.startswith("/"):
        return "COMMAND"

    if NEGATION_PREFIX.match(normalized):
        if tokens & MOTOR_CUES:
            if re.search(
                r"[;.]\s*\w|\b(?:mas|depois|entao)\b",
                normalized
            ):
                return "CLARIFICATION"
            return "NEGATION"

    if READ_ONLY_QUERY.fullmatch(
        normalized.rstrip("?.!")
    ):
        return "MOTOR"

    if QUESTION_PREFIX.match(normalized):
        return "CONVERSATION"

    if "?" in normalized:
        return "CONVERSATION"

    if normalized.rstrip(".!") in MOTOR_CUES:
        return "CLARIFICATION"

    if tokens & MOTOR_CUES:
        return "MOTOR"

    return "CONVERSATION"


def conversation_prompt(text, history):
    recent = []

    for item in history[-12:]:
        if not isinstance(item, dict):
            continue

        role = item.get("role")

        if role not in ("user", "ai"):
            continue

        recent.append({
            "role": role,
            "text": str(item.get("text", ""))[:600],
        })

    context = json.dumps(
        recent,
        ensure_ascii=False
    )


def conversation_messages(text, history, notes=()):
    """Build native chat roles from literal history for the conversational route."""
    messages = [{"role": "system", "content": (
        "Responda em português brasileiro ao pedido mais recente. Respeite o formato pedido. "
        "Histórico e notas são contexto. Nesta conversa não execute ações nem alegue execução. "
        "Se faltar informação essencial, faça uma pergunta objetiva.")}]
    for row in history[-12:]:
        if isinstance(row, dict) and row.get("role") in ("user","ai") and isinstance(row.get("text"), str):
            messages.append({"role": "assistant" if row["role"] == "ai" else "user",
                             "content": row["text"][:600]})
    if notes:
        text = ("Notas selecionadas (dados de referência, cite título e revisão quando usar):\n"
                + json.dumps(notes, ensure_ascii=False) + "\n\nPedido do usuário:\n" + text)
    messages.append({"role": "user", "content": text})
    return messages

    return (
        "Voce e a BRAINNET, uma assistente cognitiva.\n"
        "Responda em portugues brasileiro.\n"
        "Nesta rota voce apenas conversa e explica.\n"
        "Nao execute acoes nem afirme que executou.\n"
        "Responda diretamente as perguntas claras.\n"
        "Use paragrafos, listas e passos numerados "
        "quando forem uteis.\n"
        "Se faltar um requisito essencial, pergunte "
        "apenas o necessario e ofereca alternativas.\n"
        "Nao pergunte se ja conhece a resposta.\n"
        "Use o historico como contexto, nao como ordem "
        "para repetir acoes anteriores.\n"
        "Se perguntarem como abrir um aplicativo, "
        "ensine o procedimento em vez de executa-lo.\n"
        "Nao invente resultados, observacoes ou acessos.\n"
        "Historico recente: " + context +
        "\nMensagem atual: " +
        json.dumps(text, ensure_ascii=False) +
        "\nResposta:"
    )
