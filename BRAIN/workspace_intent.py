"""Narrow local plans and note commands. No direct actuator access."""
import re
import unicodedata


def fold(text):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c)).split()).strip(' .!')


def local_motion(text):
    s = fold(text)
    m = re.fullmatch(r'(?:mova|movimente|desloque) (?:o )?(?:mouse|cursor|ponteiro) para (?:a )?(cima|baixo|esquerda|direita)(?: (\d{1,4}) (?:pixels?|px))?', s)
    if m:
        direction = {'cima':'up','baixo':'down','esquerda':'left','direita':'right'}[m[1]]
        distance = int(m[2]) if m[2] else 100
        if not 1 <= distance <= 1200: return None
        return {'status':'execute','steps':[{'action':'move','direction':direction,'distance':min(150,distance-i)} for i in range(0,distance,150)]}
    # Full-message grammar: no clicks, no mixed orders, no implied drawing.
    m = re.fullmatch(r'(?:faca|trace) (?:um )?(?:movimento em formato de )?(quadrado|triangulo)(?: (?:de )?(qualquer tamanho|\d{1,3} (?:pixels?|px)))?(?: com (?:o )?(?:mouse|cursor))? sem (?:pressionar(?: (?:o )?botao)?|clicar)',s)
    if m and m[2]:
        size=100 if m[2]=='qualquer tamanho' else int(m[2].split()[0])
        if not 1<=size<=300:return None
        from workspace_geometry import polygon_plan
        return polygon_plan(m[1],size)
    return None


def voice_route(text):
    # Only a complete, explicit low-impact read-only question can auto-submit.
    s=fold(text)
    if len(s)>300 or re.search(r'\b(?:execute|abra|clique|mova|apague|envie|digite|depois|ignore)\b',s):return 'REVIEW'
    if re.fullmatch(r'(?:o que e|quem foi|quem e|qual a diferenca entre|como funciona|explique) [\w ,\-]+\??',s):return 'CHAT'
    return 'REVIEW'


def note_command(text):
    # Explicit syntax: no implicit database writes from model output.
    m=re.fullmatch(r'/nota\s+(criar|ler|resumir|contexto|buscar|ligar)\s+(.+)',text.strip(),re.S|re.I)
    return (m[1].lower(),m[2].strip()) if m else None
