"""Semantic motor vocabulary. No native input, regex commands or model-generated code."""
import json
import math
import random

DIRECTIONS = {
    'right': (1, 0), 'left': (-1, 0), 'up': (0, -1), 'down': (0, 1),
    'up_right': (1, -1), 'up_left': (-1, -1),
    'down_right': (1, 1), 'down_left': (-1, 1),
}
MAX_DISTANCE = 150
MAX_STEPS = 8

SYSTEM_PROMPT = """Interprete a intenção motora explícita do usuário em português.
Você apenas descreve um plano; não executa nada. Responda exclusivamente JSON.
Formato: {"status":"execute","steps":[...]} ou {"status":"none","steps":[]} ou
{"status":"unsupported","steps":[]}.
Vocabulário:
{"action":"move","direction":"right|left|up|down|up_right|up_left|down_right|down_left|any","distance":150}
{"action":"click","button":"left|right|middle","count":1}
{"action":"scroll","direction":"up|down","count":1}
Movimentos usam pixels relativos (1 a 150 por passo); distância não especificada: 150.
Para deslocamentos maiores, decomponha em passos de até 150 pixels, no máximo 8 passos.
Use any somente quando a direção for delegada.
Clique ou role na posição atual somente quando essa intenção for explícita; clique simples
sem alvo pode usar o cursor atual se o pedido for claramente uma ordem de clique.
Nunca transforme perguntas, exemplos, citações, negações, instruções para explicar,
pedidos de implementação ou descrições de código em ações. Retorne none.
Alvos nomeados (botão, objeto, aplicativo), coordenadas absolutas, arrasto,
digitação e tarefas que misturam ações não suportadas: unsupported para o plano inteiro.
Não invente passos, alvos ou cliques. Use no máximo 8 passos.
Exemplos:
"desloque o ponteiro para cima" -> {"status":"execute","steps":[{"action":"move","direction":"up","distance":150}]}
"vá 100 pixels à esquerda e depois 50 para baixo" -> {"status":"execute","steps":[{"action":"move","direction":"left","distance":100},{"action":"move","direction":"down","distance":50}]}
"clique com o botão direito na posição atual" -> {"status":"execute","steps":[{"action":"click","button":"right","count":1}]}
"como mover o mouse?" -> {"status":"none","steps":[]}
"mova o mouse até o botão salvar" -> {"status":"unsupported","steps":[]}
"""


def validate_plan(value):
    if not isinstance(value, dict) or set(value) != {'status', 'steps'}:
        raise ValueError('invalid motor plan')
    status, steps = value['status'], value['steps']
    if status not in ('execute', 'none', 'unsupported') or not isinstance(steps, list):
        raise ValueError('invalid motor status')
    if status != 'execute':
        if steps:
            raise ValueError('non-executable plan has steps')
        return value
    if not 1 <= len(steps) <= MAX_STEPS:
        raise ValueError('invalid step count')
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError('invalid step')
        action = step.get('action')
        if action == 'move':
            if (set(step) != {'action', 'direction', 'distance'}
                    or step['direction'] not in (*DIRECTIONS, 'any')
                    or type(step['distance']) is not int
                    or not 1 <= step['distance'] <= MAX_DISTANCE):
                raise ValueError('invalid relative movement')
        elif action == 'click':
            if (set(step) != {'action', 'button', 'count'}
                    or step['button'] not in ('left', 'right', 'middle')
                    or type(step['count']) is not int or not 1 <= step['count'] <= 2):
                raise ValueError('invalid click')
        elif action == 'scroll':
            if (set(step) != {'action', 'direction', 'count'}
                    or step['direction'] not in ('up', 'down')
                    or type(step['count']) is not int or not 1 <= step['count'] <= 10):
                raise ValueError('invalid scroll')
        else:
            raise ValueError('unknown motor action')
    return value


def parse_response(text):
    return validate_plan(json.loads(text))


def resolve_move(start, rect, direction, distance, *, previous=None, choose=random.choice):
    """Use observed monitor geometry, never model-invented absolute coordinates."""
    if (len(start) != 2 or len(rect) != 4 or
            any(type(v) is not int for v in (*start, *rect))):
        raise ValueError('invalid geometry')
    left, top, right, bottom = rect
    if not (left <= start[0] < right and top <= start[1] < bottom):
        raise ValueError('cursor outside monitor')
    if type(distance) is not int or not 1 <= distance <= MAX_DISTANCE:
        raise ValueError('invalid distance')
    candidates = {}
    for name, (dx, dy) in DIRECTIONS.items():
        scale = distance / math.hypot(dx, dy)
        delta = (math.trunc(dx * scale), math.trunc(dy * scale))
        if delta == (0, 0):
            continue
        point = (start[0] + delta[0], start[1] + delta[1])
        if left <= point[0] < right and top <= point[1] < bottom:
            candidates[name] = point
    if direction == 'any':
        options = [name for name in candidates if name != previous] or list(candidates)
        if not options:
            raise ValueError('no movement inside monitor')
        direction = choose(options)
    if direction not in candidates:
        raise ValueError('movement outside monitor')
    return candidates[direction], direction
