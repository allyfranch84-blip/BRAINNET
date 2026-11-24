"""Ground model-produced application references in the current utterance.
This is a fail-closed validator, not a command parser or an execution path.
Historical actions are never a source of authority.
"""
import unicodedata
from copy import deepcopy

APP_ALIASES={
    'paint':('paint','mspaint'),
    'notepad':('notepad','bloco de notas','bloco notas'),
    'calculator':('calculator','calculadora','calc','calculatorapp'),
    'thorium':('thorium',), 'whatsapp':('whatsapp',), 'telegram':('telegram',),
    'chatgpt':('chatgpt','chat gpt'), 'chrome':('chrome',), 'firefox':('firefox',),
    'msedge':('msedge','edge'), 'krita':('krita',), 'vlc':('vlc',),
    'discord':('discord',), 'signal':('signal',),
}

def words(text):
    folded=''.join(c for c in unicodedata.normalize('NFKD',str(text).casefold()) if not unicodedata.combining(c))
    return tuple(''.join(c if c.isalnum() else ' ' for c in folded).split())

def contains(haystack,needle):
    return bool(needle) and any(haystack[i:i+len(needle)]==needle for i in range(len(haystack)-len(needle)+1))

def canonical_app(name):
    value=words(str(name).casefold().removesuffix('.exe'))
    return next((key for key,aliases in APP_ALIASES.items() if any(value==words(a) for a in aliases)),None)

def mentioned_apps(text):
    tokens=words(text)
    return {key for key,aliases in APP_ALIASES.items() if any(contains(tokens,words(a)) for a in aliases)}

def has_reference(text):
    tokens=words(text)
    return any(t in tokens for t in ('nele','nela','nesse','nessa','neste','nesta','esse','essa','este','esta','isso','anterior','mesmo','mesma'))

# Lexical evidence is only a veto on an unexpected side effect; the semantic
# model still chooses every action, order, quantity and target.
OPEN_CUES=frozenset(('abra','abrir','abre','inicie','iniciar','execute','executar','lance','lancar','rode','rodar','carregue','carregar'))
CLICK_CUES=frozenset(('clique','clicar','clica','aperte','apertar','pressione','pressionar','toque','tocar','acione','acionar','selecione','selecionar'))
MOVE_CUES=frozenset(('mova','mover','move','desloque','deslocar','posicione','posicionar','leve','levar','va','ir','suba','subir','desca','descer','aponte','apontar','coloque','colocar','arraste','arrastar'))
SCROLL_CUES=frozenset(('role','rolar','scroll','rolagem','deslize','deslizar'))

def ground_plan(text,plan,*,reference=None):
    from motor_intent import validate_plan
    validate_plan(plan)
    if plan['status']!='execute':
        return deepcopy(plan)
    tokens=words(text)
    token_set=set(tokens)
    apps=mentioned_apps(text)
    bound=deepcopy(plan)
    active=None
    target=None
    for step in bound['steps']:
        action=step['action']
        if action=='open_app':
            if step['target'] not in apps or not token_set & OPEN_CUES:
                raise ValueError('OPEN_APP_NOT_GROUNDED')
            active=step['target']
            target=None
        elif action in ('move_to','click_target'):
            if not token_set & (MOVE_CUES if action=='move_to' else CLICK_CUES):
                raise ValueError('NAMED_ACTION_NOT_GROUNDED')
            explicit=canonical_app(step.get('app',''))
            if step.get('app') and (explicit is None or explicit not in apps):
                # Permit a verified antecedent only when the user actually refers to it.
                if not (reference and has_reference(text) and explicit==canonical_app(reference.get('app',''))):
                    raise ValueError('APPLICATION_NOT_GROUNDED')
            if explicit is None and len(apps)==1:
                explicit=next(iter(apps))
            if explicit is None and len(apps)>1 and active is None:
                raise ValueError('APPLICATION_AMBIGUOUS')
            requested=step['target']
            if not contains(tokens,words(requested)):
                previous=target or (reference if has_reference(text) else None)
                if not previous or not has_reference(text) or words(previous['target'])!=words(requested):
                    raise ValueError('TARGET_NOT_GROUNDED')
                previous_app=canonical_app(previous.get('app',''))
                if explicit and previous_app and explicit!=previous_app:
                    raise ValueError('REFERENCE_APPLICATION_MISMATCH')
                explicit=explicit or previous_app
            if explicit:
                step['app']=explicit
            target={'target':requested,'app':explicit or active}
        elif action=='click' and not token_set & CLICK_CUES:
            raise ValueError('CLICK_NOT_GROUNDED')
        elif action=='scroll' and not token_set & SCROLL_CUES:
            raise ValueError('SCROLL_NOT_GROUNDED')
        elif action=='move' and any(s['action']=='open_app' for s in bound['steps']) and not token_set & MOVE_CUES:
            raise ValueError('MOVE_NOT_GROUNDED')
    return validate_plan(bound)
