"""Conservative, non-executing interpretation of natural requests."""
from dataclasses import dataclass
import math
import re
import unicodedata
from parser_contract import analyze_literal_intent

@dataclass(frozen=True)
class Capability:
    identifier: str
    shortcut: str | None
    side_effect: str
    authorization: str
    available: bool
    verification: str
    timeout: str = 'caller-controlled'
    cancellation: str = 'caller-controlled'

CAPABILITIES={
    'help':Capability('help','/help','read','none',True,'response'),
    'research':Capability('research','/pesquisa','network','explicit',True,'source references'),
    'code_audit':Capability('code_audit',None,'read','none',False,'static evidence'),
    'book':Capability('book',None,'file_write','explicit',False,'chapter review'),
    'video':Capability('video',None,'network','explicit',False,'timestamped sources'),
}

# Seed identities are stable source records, not learned or verified episodes.
CONCEPT_SEEDS = {
    'aplicativo': ('entidade digital', 'janela programa execução'),
    'janela': ('interface', 'aplicativo visível minimizado foco'),
    'abrir': ('operação', 'iniciar aplicativo criar janela'),
    'mostrar': ('objetivo', 'tornar visível janela restaurar'),
    'focar': ('operação', 'selecionar janela primeiro plano'),
    'botão': ('controle', 'elemento interface clicar'),
    'clicar': ('operação', 'acionar controle botão'),
    'desenho': ('atividade', 'criar imagem aplicativo'),
    'paint': ('aplicativo', 'editor desenho imagem janela'),
    'movimento': ('operação', 'deslocamento posição direção'),
    'mouse': ('dispositivo', 'cursor ponteiro movimento clique'),
}


def retrieve_concept_candidates(engine, text, *, limit=3):
    """FHRR candidate retrieval only: similarity is not meaning or authority."""
    if not isinstance(text, str) or not text.strip() or not 1 <= limit <= 11:
        raise ValueError('invalid request')
    query = engine.text_to_hypervector(text)
    ranked = []
    for key, (category, relations) in CONCEPT_SEEDS.items():
        vector = engine.text_to_hypervector(f'{key} {relations}')
        score = float(engine.similarity(query, vector))
        if not math.isfinite(score):
            continue
        ranked.append({'concept_id': f'brainnet:concept:v1:{key}', 'label': key,
                       'category': category, 'relations_text': relations, 'similarity': score,
                       'source': 'curated_seed', 'verified': False, 'execution_authorized': False})
    return sorted(ranked, key=lambda item: item['similarity'], reverse=True)[:limit]

def _fold(text):
    return ''.join(c for c in unicodedata.normalize('NFD',text.casefold()) if unicodedata.category(c)!='Mn')

def conceptual_hypotheses(text):
    """Bounded advisory hypotheses; no planner or authority is invoked."""
    if not isinstance(text,str) or not text.strip():raise ValueError('empty request')
    # Exclude quoted material, URLs and paths from keyword evidence.
    stripped=re.sub(r'https?://\S+|[A-Za-z]:\\[^\s]+|`[^`]*`|"[^"]*"|\'[^\']*\'',' ',text)
    normalized=_fold(stripped)
    hypotheses=[];missing=[];preferences=[];constraints=[]
    if re.search(r'\b(?:astronomia|astronomico)\b',normalized) and re.search(r'\b(?:ensinar|ensine|aprender|aprenda)\b',normalized):
        hypotheses.append({'goal':'ensinar_astronomia','evidence':['astronomia','ensinar/aprender'],'status':'HYPOTHESIS'})
        if not re.search(r'\b(?:video|livro|jogo|aula)\b',normalized):missing.append('formato do material')
    if re.search(r'\b(?:livro|livo)\b',normalized) and re.search(r'\b(?:faca|crie|escreva|produza)\b',normalized):
        hypotheses.append({'goal':'criar_livro','evidence':['livro','pedido de criação'],'status':'HYPOTHESIS'})
        if not re.search(r'\b(?:sobre|astronomia|fisica|historia)\b',normalized):missing.append('assunto do livro')
    if re.search(r'\b(?:analise|analize|examine)\b',normalized) and re.search(r'\b(?:codigo|projeto)\b',normalized):
        hypotheses.append({'goal':'auditar_codigo','evidence':['análise','código/projeto'],'status':'HYPOTHESIS'})
    if re.search(r'\b(?:aplicativo|app)\b',normalized) and re.search(r'\b(?:ruim|problema|melhore)\b',normalized):
        hypotheses.append({'goal':'investigar_aplicativo','evidence':['aplicativo','problema/melhoria'],'status':'HYPOTHESIS'})
        missing.append('aplicativo e problema observado')
    if re.search(r'\b(?:divertida|divertido|ludica|ludico)\b',normalized):preferences.append({'value':'abordagem divertida','certainty':'EXPRESSED'})
    if re.search(r'\b(?:iniciante|iniciantes)\b',normalized):preferences.append({'value':'público iniciante','certainty':'EXPRESSED'})
    if re.search(r'\bnao\s+(?:muito\s+)?infantil\b',normalized):constraints.append('evitar estilo excessivamente infantil')
    return {'original':text,'hypotheses':hypotheses,'alternatives':[], 'context_used':[],
            'constraints':constraints,'preferences':preferences,'missing_information':missing,
            'verified_facts':[], 'execution_authorized':False}

def interpret(text):
    if not isinstance(text,str) or not text.strip():raise ValueError('empty request')
    protected=[m.group() for m in re.finditer(r'https?://\S+|[A-Za-z]:\\[^\s]+|`[^`]*`|\b\d+\b',text)]
    folded=_fold(text);literal=analyze_literal_intent(text)
    negated=bool(re.search(r'\b(nao|nunca|jamais)\b',folded))
    candidates=[]
    for wrong,right in [('livo','livro'),('vidio','video'),('analize','analise'),('peint','paint')]:
        if re.search(r'\b'+wrong+r'\b',folded):candidates.append({'original':wrong,'suggestion':right})
    proposed=folded
    for c in candidates:proposed=re.sub(r'\b'+c['original']+r'\b',c['suggestion'],proposed)
    cap=None
    if re.search(r'\b(mostre|mostrar)\b.*\b(comandos|ajuda)\b',proposed) or proposed.strip() in ('/help','/ajuda','/?'):cap='help'
    elif re.match(r'^\s*(?:pesquise|pesquisar)\s+sobre\b',proposed) or proposed.startswith('/pesquisa '):cap='research'
    elif re.search(r'\b(?:analise|analisar)\b.*\b(?:seu|proprio)\s+codigo\b',proposed):cap='code_audit'
    elif re.search(r'\b(?:escreva|faca|escrever)\b.*\blivro\b',proposed):cap='book'
    elif re.search(r'\b(?:analise|veja|assistir)\b.*\bvideo\b',proposed):cap='video'
    risky=bool(re.search(r'\b(apague|apagar|delete|exclua|excluir|edite|editar|clique|abra|abre|execute)\b',proposed))
    ambiguous=negated or risky or bool(re.search(r'\b(?:ironia|sarcasmo)\b',proposed))
    return {'original':text,'protected':protected,'corrections':candidates,'negated':negated,
            'capability':cap if not ambiguous else None,'needs_clarification':ambiguous,
            'literal_intent':literal,'execution_authorized':False}
