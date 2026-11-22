"""Semicolons separate teacher steps; punctuation in TYPE remains literal."""
import pytest

from professor_mode import parse_complete_lesson
from test_professor_mode import bridge, send
from test_professor_complete import mock_batch


@pytest.mark.parametrize("raw,expected", [
    ("digite olá, como vai?; tecla enter", "olá, como vai?"),
    ('digite "olá, como vai?"; tecla enter', "olá, como vai?"),
    ('digite "olá; como vai?"; tecla enter', "olá; como vai?"),
    ("digite 'olá; como vai?'; tecla enter", "olá; como vai?"),
    ("digite “olá; como vai?”; tecla enter", "olá; como vai?"),
    ("digite d'água, tudo bem?; tecla enter", "d'água, tudo bem?"),
    ("aguarde 0,5 segundos; digite olá, como vai?; tecla enter", "olá, como vai?"),
])
def test_punctuation_and_quotes_are_preserved(raw, expected):
    lesson = parse_complete_lesson("/professor teste | escrever | " + raw)
    typed = [step for step in lesson[3] if step["acao"] == "TYPE"]
    assert typed == [{"passo": len(lesson[3]) - 1, "acao": "TYPE", "text": expected}]
    assert lesson[3][-1]["keys"] == ["enter"]


@pytest.mark.parametrize("raw", ['tecla win; digite "sem fechar; enter', "tecla win;; enter", "tecla win;", "tecla win, enter"])
def test_invalid_lesson_never_executes_a_prefix(bridge, raw):
    mock_batch(bridge)
    send(bridge, "/professor teste | escrever | " + raw)
    bridge._kernel.trajectory_engine.execute_professor_batch.assert_not_awaited()


def test_batch_keeps_message_comma_intact(bridge):
    mock_batch(bridge)
    send(bridge, "/professor mensagem | enviar_mensagem | tecla win; digite whatsapp; tecla enter; digite davi; tecla enter; digite olá, como vai?; tecla enter")
    steps = bridge._professor_mode["passos_executados"]
    assert len(steps) == 7
    assert steps[5]["text"] == "olá, como vai?"
    bridge._tom.evaluate_intent.assert_not_called()


def test_interactive_help_and_step_use_same_delimiter(bridge):
    mock_batch(bridge)
    send(bridge, "/professor")
    send(bridge, "escrever")
    assert "PONTO E VÍRGULA (;)" in send(bridge, "escrever")["reply"]
    send(bridge, 'digite "Olá; mundo, tudo bem?"; tecla enter')
    assert bridge._professor_mode["passos_executados"][0]["text"] == "Olá; mundo, tudo bem?"
    assert len(bridge._professor_mode["passos_executados"]) == 2
