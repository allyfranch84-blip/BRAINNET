"""Ground model-produced application references in the current utterance.
This is a fail-closed validator, not a command parser or an execution path.
Historical actions are never a source of authority.
"""
import re
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

def _fold(text):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(text).casefold()) if not unicodedata.combining(c))

def words(text):
    return tuple(''.join(c if c.isalnum() else ' ' for c in _fold(text)).split())

def contains(haystack,needle):
    return bool(needle) and any(haystack[i:i+len(needle)]==needle for i in range(len(haystack)-len(needle)+1))

def canonical_app(name):
    value=' '.join(_fold(name).split()).removesuffix('.exe')
    return next((key for key,aliases in APP_ALIASES.items() if value in aliases),None)

def mentioned_apps(text):
    # Preserve punctuation inside a name (Notepad++, Paint.NET).
    tokens=tuple(t.removesuffix('.exe') for t in re.findall(r'[^\W_]+(?:[.+#_-]+[^\W_]+)*(?:[+#]+)?', _fold(text)))
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

_CLAUSE_SPLIT = re.compile(r'([,;\n]|[.!?](?=\s|$)|\b(?:e\s+depois|em\s+seguida|(?:e\s+)?nem(?:\s+depois)?|depois|entao|mas|e)\b)')
_NEGATIONS = frozenset(('nao', 'nunca', 'jamais', 'nem', 'sem', 'evite'))
_ARTICLES = frozenset(('o', 'a', 'os', 'as', 'um', 'uma'))
_APP_QUALIFIERS = frozenset(('app', 'aplicativo', 'programa'))
_SENTENCE_ENDS = frozenset(('', '.', '!', '?', ';', '\n'))
_COORDINATION = frozenset((',', 'e', 'e depois', 'depois', 'entao', 'em seguida'))
_BUILTIN_OPEN_APPS = frozenset(('paint', 'notepad', 'calculator'))


def _one_edit(value, expected, *, allow_replacement):
    """One deletion, insertion, adjacent swap or permitted substitution."""
    if abs(len(value) - len(expected)) > 1:
        return False
    if len(value) == len(expected):
        differences = [i for i, (a, b) in enumerate(zip(value, expected)) if a != b]
        if len(differences) == 1:
            return allow_replacement
        if len(differences) == 2:
            left, right = differences
            return right == left + 1 and value[left:right + 1] == expected[left:right + 1][::-1]
        return False
    shorter, longer = sorted((value, expected), key=len)
    index = next((i for i, (a, b) in enumerate(zip(shorter, longer)) if a != b), len(shorter))
    return shorter[index:] == longer[index + 1:]


def _app_identity(phrase):
    """Approximate known aliases only when the full name gives one answer."""
    exact = canonical_app(phrase)
    if exact:
        return exact, False
    tokens = tuple(phrase.split())
    if not tokens or not all(t.isalnum() for t in tokens):
        return None, False
    candidates = set()
    for key, aliases in APP_ALIASES.items():
        for alias in aliases:
            expected = alias.split()
            if len(tokens) != len(expected):
                continue
            edits = [(a, b) for a, b in zip(tokens, expected) if a != b]
            if len(edits) != 1:
                continue
            value, correct = edits[0]
            if min(len(value), len(correct)) >= 4 and _one_edit(
                    value, correct, allow_replacement=len(tokens) > 1):
                candidates.add(key)
    if len(candidates) > 1:
        return None, True
    return next(iter(candidates), None), False


def _open_evidence(text, opens):
    """Extract bounded lexical evidence for ordered, positive app requests."""
    parts = _CLAUSE_SPLIT.split(_fold(text))
    proposed = {' '.join(_fold(step['target']).split()) for step in opens}
    questions = set()
    interrogative = False
    for i in range(len(parts) - 1, -1, -2):
        after = parts[i + 1] if i + 1 < len(parts) else ''
        if after in _SENTENCE_ENDS:
            interrogative = after == '?'
        if interrogative:
            questions.add(i)
    evidence = []
    continuing = False
    for i in range(0, len(parts), 2):
        clause = ' '.join(parts[i].split())
        before = ' '.join(parts[i - 1].split()) if i else ''
        if not clause or clause in ('por favor', 'por gentileza'):
            continue
        if set(words(clause)) & _NEGATIONS or 'nem' in before.split() or i in questions:
            continuing = False
            continue
        if continuing and clause.startswith('ou '):
            return evidence, 'APPLICATION_AMBIGUOUS'
        for prefix in ('por favor ', 'por gentileza ', 'quero que voce ', 'quero que '):
            if clause.startswith(prefix):
                clause = clause[len(prefix):]
                break
        first, _, rest = clause.partition(' ')
        explicit = first in OPEN_CUES
        if not explicit and not (continuing and before in _COORDINATION):
            continuing = False
            continue
        phrase = rest if explicit else clause
        if not explicit and first in CLICK_CUES | MOVE_CUES | SCROLL_CUES:
            continuing = False
            continue
        if 'ou' in words(phrase):
            return evidence, 'APPLICATION_AMBIGUOUS'
        if phrase.split(' ', 1)[0] in _ARTICLES:
            phrase = phrase.partition(' ')[2]
        if phrase.split(' ', 1)[0] in _APP_QUALIFIERS:
            phrase = phrase.partition(' ')[2]
        for suffix in (' por favor', ' por gentileza', ' para mim', ' pra mim', ' agora'):
            if phrase.endswith(suffix):
                phrase = phrase[:-len(suffix)]
                break
        phrase = phrase.strip(' \"\'“”‘’')
        identity, ambiguous = _app_identity(phrase)
        if ambiguous:
            return evidence, 'APPLICATION_AMBIGUOUS'
        continuing = explicit or identity is not None or phrase in proposed
        if continuing and phrase:
            evidence.append((phrase, identity))
    return evidence, None


def direct_app_request(text):
    """Return a local plan for one complete, unambiguous built-in app request.

    Alternative targets raise APPLICATION_AMBIGUOUS. Everything outside the
    narrow local grammar remains eligible for the regular semantic route.
    """
    if not isinstance(text, str):
        return None
    evidence, error = _open_evidence(text, ())
    if error:
        raise ValueError(error)
    if len(evidence) != 1 or evidence[0][1] not in _BUILTIN_OPEN_APPS:
        return None
    parts = _CLAUSE_SPLIT.split(_fold(text).strip())
    clauses = [' '.join(part.split()) for part in parts[::2] if part.strip()]
    content = [clause for clause in clauses if clause not in ('por favor', 'por gentileza')]
    # Commas may separate polite phrases, and a final period or exclamation
    # mark may end the command. Connectors and additional content defer.
    if len(content) != 1 or any(separator not in (',', '.', '!') for separator in parts[1::2]):
        return None
    return {'status': 'execute', 'steps': [{'action': 'open_app', 'target': evidence[0][1]}]}


def explicit_app_choices(text):
    """Carry forward only an explicit opening verb with known, alternative targets."""
    if not isinstance(text, str) or len(text) > 320 or '?' in text:
        return ()
    alternatives = re.split(r'\s+ou\s+', _fold(text.strip().rstrip('.!')))
    if not 2 <= len(alternatives) <= 4:
        return ()
    targets = []
    for i, phrase in enumerate(alternatives):
        # Later noun phrases inherit the opening verb only within this sentence.
        plan = direct_app_request(phrase)
        if i and plan is None:
            plan = direct_app_request('abra ' + phrase)
        if plan is None:
            return ()
        target = plan['steps'][0]['target']
        if target in targets:
            return ()
        targets.append(target)
    return tuple(targets)


def _negated_action_cues(text):
    parts = _CLAUSE_SPLIT.split(_fold(text))
    prohibited = set()
    for i in range(0, len(parts), 2):
        clause = set(words(parts[i]))
        before = parts[i - 1].split() if i else ()
        if clause & _NEGATIONS or 'nem' in before:
            prohibited.update(clause)
    return prohibited

def ground_plan(text,plan,*,reference=None):
    from motor_intent import validate_plan
    validate_plan(plan)
    if plan['status']!='execute':
        return deepcopy(plan)
    tokens=words(text)
    token_set=set(tokens)
    apps=mentioned_apps(text)
    bound=deepcopy(plan)
    opened=[step for step in bound['steps'] if step['action']=='open_app']
    open_evidence, open_error = _open_evidence(text, opened)
    prohibited = _negated_action_cues(text)
    apps.update(identity for _, identity in open_evidence if identity)
    active=None
    target=None
    for step in bound['steps']:
        action=step['action']
        if action=='open_app':
            active=canonical_app(step['target']) or step['target']
            target=None
        elif action in ('move_to','click_target'):
            cues = MOVE_CUES if action == 'move_to' else CLICK_CUES
            if not token_set & cues or prohibited & cues:
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
        elif action=='click':
            if not token_set & CLICK_CUES or prohibited & CLICK_CUES:
                raise ValueError('CLICK_NOT_GROUNDED')
            if has_reference(text):
                previous=target or reference
                if not previous:
                    raise ValueError('REFERENCE_UNRESOLVED')
                previous_app=canonical_app(previous.get('app',''))
                if apps and previous_app and previous_app not in apps:
                    raise ValueError('REFERENCE_APPLICATION_MISMATCH')
                step.update(action='click_target',target=previous['target'])
                if previous_app:
                    step['app']=previous_app
        elif action=='inspect_context':
            # Disambiguate an explicitly named category only within a read-only
            # query. This never turns words into an executable motor action.
            if contains(tokens,words('inteligência artificial')) or contains(tokens,words('chat de ia')):
                step['purpose']='ai_chat'
        elif action=='scroll' and (not token_set & SCROLL_CUES or prohibited & SCROLL_CUES):
            raise ValueError('SCROLL_NOT_GROUNDED')
        elif action=='move' and (prohibited & MOVE_CUES or (opened and not token_set & MOVE_CUES)):
            raise ValueError('MOVE_NOT_GROUNDED')
    if open_error:
        raise ValueError(open_error)
    if len(opened) != len(open_evidence):
        raise ValueError('OPEN_APP_NOT_GROUNDED')
    for step, (phrase, identity) in zip(opened, open_evidence):
        name = ' '.join(_fold(step['target']).split())
        if name != phrase and (identity is None or canonical_app(name) != identity):
            raise ValueError('OPEN_APP_NOT_GROUNDED')
        if identity and canonical_app(phrase) is None:
            step['target'] = identity
    return validate_plan(bound)
