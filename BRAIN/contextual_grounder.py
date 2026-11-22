"""Contextual UI target recognition. Read-only until execution safeguards exist."""
from dataclasses import dataclass, asdict
import re
import time
import unicodedata
from difflib import get_close_matches


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(text).casefold()) if not unicodedata.combining(c)).strip()


def parse_click(text):
    """Accept explicit standalone action forms only; never interpret free prose."""
    s=normalize(' '.join(str(text).strip().split()))
    m=re.fullmatch(r'(?:clique|clicar|click|selecione|selecionar|abra)\s+(?:(?:em|no|na)\s+)?(?:(?:o|a)\s+)?(?:(?:menu|ferramenta)\s+)?([\w -]{1,80})[.!]?',s)
    if not m:return None
    target=m.group(1).strip()
    if not target or re.search(r'\b(?:e|depois|entao)\b',target):return None
    if s.startswith('abra ') and 'menu ' not in s:return None
    return {'action':'CLICK','target':target}

def suggest_apps(name, inventory):
    """Offer similar inventory names without launching or asserting installation."""
    if not isinstance(inventory,dict): return []
    names=[str(k) for k in inventory if isinstance(k,str) and k.strip()]
    return get_close_matches(str(name).casefold(),names,n=3,cutoff=.6)

@dataclass
class TaskContext:
    app: str
    hwnd: int
    pid: int
    process_name: str
    process_started: float
    previous_intent: str
    validated_at: float
    last_result: str
    pending_target: str | None = None
    authorization_state: str = 'NOT_RETAINED'

class ContextualGrounder:
    def __init__(self, context_engine, eye, process_started, *, clock=time.monotonic, max_age=300):
        self.context_engine=context_engine;self.eye=eye;self.process_started=process_started;self.clock=clock;self.max_age=max_age;self.context=None
    def remember(self, app, intent, result):
        current=self.context_engine.capture_foreground_context() or {}
        hwnd=current.get('hwnd');pid=current.get('pid');process=str(current.get('process_name',''))
        expected=normalize(app).removesuffix('.exe');actual=normalize(process).removesuffix('.exe')
        aliases={'paint':'mspaint','bloco de notas':'notepad','calculadora':'calc'}
        if not hwnd or not pid or actual!=aliases.get(expected,expected):return False
        try: started=self.process_started(pid)
        except Exception:return False
        if not isinstance(started,(int,float)) or started<=0:return False
        self.context=TaskContext(app,int(hwnd),int(pid),process,float(started),intent,self.clock(),result)
        return True
    def resolve(self, intent):
        c=self.context
        if c is None or self.clock()-c.validated_at>self.max_age:return {'status':'CONTEXT_UNAVAILABLE','reason':'Aplicativo recente nao foi verificado ou expirou.'}
        try:now=self.context_engine.capture_foreground_context() or {}; started=self.process_started(c.pid)
        except Exception:return {'status':'CONTEXT_UNAVAILABLE','reason':'Nao foi possivel verificar janela e processo.'}
        if now.get('hwnd')!=c.hwnd or now.get('pid')!=c.pid or started!=c.process_started or normalize(now.get('process_name',''))!=normalize(c.process_name):
            return {'status':'CONTEXT_UNAVAILABLE','reason':'Janela perdeu foco ou identidade do processo mudou.'}
        target=intent['target']
        if target in ('nesse botao','neste botao','esse botao','este botao','isso'):
            if not c.pending_target:return {'status':'CONTEXT_UNAVAILABLE','reason':'Nenhum alvo anterior validado.'}
            target=c.pending_target
        try:controls=self.eye.scan_window_controls(c.hwnd)
        except Exception:return {'status':'TARGET_NOT_FOUND','reason':'Controles UIA indisponiveis.'}
        matches=[x for x in controls if normalize(getattr(x,'name',''))==target]
        if not matches:return {'status':'TARGET_NOT_FOUND','reason':'Controle nao encontrado por nome exato.'}
        if len(matches)!=1:return {'status':'TARGET_AMBIGUOUS','reason':'Mais de um controle corresponde ao alvo.'}
        candidate=matches[0]
        # Fresh UIA properties are informative only. Execution is still blocked:
        # there is no serialised identity revalidation or user-takeover check.
        details=None
        reader=getattr(self.eye,'scan_uia_properties',None)
        if callable(reader):
            try:
                fresh=[item for item in reader(c.hwnd)
                       if normalize(item.get('name',''))==target and item.get('process_id')==c.pid]
                if len(fresh)>1:return {'status':'TARGET_AMBIGUOUS','reason':'Mais de um controle UIA atual corresponde ao alvo.'}
                if len(fresh)==1:
                    details={key:fresh[0].get(key) for key in ('automation_id','control_type','runtime_id',
                             'is_enabled','is_offscreen','invoke_supported','expand_collapse_supported')}
            except Exception:pass
        c.pending_target=None
        if (details and details['is_enabled'] is True and details['is_offscreen'] is False
            and details['runtime_id'] and (details['invoke_supported'] is True or details['expand_collapse_supported'] is True)):
            ready={'status':'READY_FOR_UIA','reason':'Alvo requer revalidacao serializada.',
                'target_descriptor':{'name':str(getattr(candidate,'name','')),'hwnd':c.hwnd,'pid':c.pid,
                    'process_started':c.process_started,'runtime_id':details['runtime_id'],
                    'automation_id':details['automation_id'],'control_type':details['control_type']}}
            if normalize(c.process_name) in ('mspaint.exe','mspaint'):
                from paint_app_context import paint_context, ExecutionEvidence
                ready['app_context']=asdict(paint_context(c,(details,)))
                ready['learning_candidate']=ExecutionEvidence(intent='CLICK',app='paint',semantic_targets=[target],strategy='UIA').as_learning_candidate()
            return ready
        if details and details['is_enabled'] is False: reason='Controle desabilitado.'
        elif details and details['is_offscreen'] is True: reason='Controle fora da tela.'
        else: reason='Controle identificado; revalidacao atomica e verificacao de intervencao humana indisponiveis.'
        result={'status':'ACTION_BLOCKED','reason':reason,
                'candidate_name':str(getattr(candidate,'name','')), 'uia_properties':details}
        if normalize(c.process_name) in ('mspaint.exe','mspaint'):
            from paint_app_context import paint_context, ExecutionEvidence
            app=paint_context(c, (details,) if details else ())
            result['app_context']=asdict(app)
            result['learning_candidate']=ExecutionEvidence(
                intent='CLICK',app='paint',semantic_targets=[target],strategy='UIA').as_learning_candidate()
        return result
