"""Bounded multicontext working memory, with derived FHRR indices.

The original receipts remain authoritative. Vectors and application-purpose
hypotheses are retrieval aids only; nothing here authorizes physical actions.
No filesystem, native input, LLM, or background thread.
"""
from collections import deque
from copy import deepcopy
import threading
import time
import numpy as np

PURPOSES=frozenset(('communication','browser','graphics','text_editing','video','ai_chat'))
# Initial semantic priors, not observations of the active UI or learned skills.
APP_PRIORS={
    'whatsapp':('communication',), 'telegram':('communication',),
    'signal':('communication',), 'discord':('communication',),
    'thorium':('browser',), 'chrome':('browser',), 'msedge':('browser',),
    'firefox':('browser',), 'mspaint':('graphics',), 'notepad':('text_editing',),
    'krita':('graphics',), 'vlc':('video',), 'chatgpt':('ai_chat',),
}


def identity(window):
    try:
        hwnd,pid,birth=window['hwnd'],window['pid'],window['started']
        if type(hwnd) is not int or type(pid) is not int or hwnd<=0 or pid<=0 or type(birth) not in (float,int) or not np.isfinite(birth) or birth<=0:
            return None
        return (hwnd,pid,birth)
    except (TypeError,KeyError):
        return None


def app_name(window):
    return str(window.get('app','')).casefold().removesuffix('.exe')


def live_windows(snapshot):
    if snapshot.get('channels',{}).get('windows',{}).get('status') not in ('OBSERVED','PARTIAL'):
        return []
    return [w for w in snapshot.get('windows',[]) if not w.get('owned') and identity(w) is not None]


class CognitiveContext:
    def __init__(self, engine, *, capacity=50):
        if type(capacity) is not int or not 1<=capacity<=50:
            raise ValueError('invalid working-memory capacity')
        self.engine=engine
        self.capacity=capacity
        self._events=deque()
        self._lock=threading.RLock()
        self._sequence=0

    def _vector(self, fields):
        # Role binding keeps an action label distinct from a target label.
        # Direct vector generation avoids filling the global token/cleanup cache.
        parts=[]
        for role,value in fields.items():
            if value:
                parts.append(self.engine.generate_vector('context-role:'+role) *
                             self.engine.generate_vector('context-value:'+str(value)))
        return self.engine.bundle(parts)

    def record(self, task_id, steps, result, window=None):
        # Do not store chat text, reply text, native handles in the prompt, or
        # full images. Preserve only typed actions and observed result status.
        from motor_intent import validate_plan
        validate_plan({'status':'execute','steps':steps})
        status=result.get('status','UNKNOWN')
        key=identity(window)
        app=app_name(window) if key else ''
        record={'task_id':str(task_id),'window':key,'app':app,
                'steps':deepcopy(steps),'status':status,'at':time.monotonic(),
                'effect_verified':status=='EFFECT_VERIFIED',
                'goal_verified':False}
        # Each record is an operation receipt, not an assertion of task success.
        fields={'app':app,'actions':','.join(s['action'] for s in steps),
                'target':','.join(s.get('target','') for s in steps),
                'status':status}
        vector=self._vector(fields)
        with self._lock:
            self._sequence+=1
            record['sequence']=self._sequence
            self._events.append((record,vector))
            if len(self._events)>self.capacity:
                self._events.popleft()
        return record['sequence']

    def tree(self):
        """Root -> per-application-instance bundles -> exact receipt leaves."""
        with self._lock:
            grouped={}
            for record,vector in self._events:
                grouped.setdefault(record['window'],[]).append((record,vector))
            nodes=[]
            for key,items in grouped.items():
                vectors=[v for _,v in items]
                weights=[1.0+0.5*i/max(1,len(items)-1) for i in range(len(items))]
                summary=self.engine.bundle_weighted(vectors,weights)
                nodes.append({'window':key,'app':items[-1][0]['app'],
                              'count':len(items),'vector':summary})
            root=self.engine.bundle([n['vector']*self.engine.generate_vector('context-node:'+str(n['window'])) for n in nodes]) if nodes else None
            return {'root':root,'nodes':nodes}

    def prompt_context(self,snapshot):
        windows=live_windows(snapshot)
        live={identity(w):w for w in windows}
        with self._lock:
            recent=[]
            for record,_ in reversed(self._events):
                if record['window'] not in live:
                    continue
                # Do not revive targets from a prior failed or unconfirmed operation.
                # Include result status explicitly, never imply authorization.
                recent.append({'app':record['app'],'steps':deepcopy(record['steps']),
                               'status':record['status'],'effect_verified':record['effect_verified']})
                if len(recent)>=6:
                    break
        return {'recent_operations':recent,
                'purpose_hypotheses':{app_name(w):list(APP_PRIORS[app_name(w)]) for w in windows if app_name(w) in APP_PRIORS}}

    def resolve_purpose(self,snapshot,purpose):
        if purpose not in PURPOSES:
            raise ValueError('unknown purpose')
        matches=[w for w in live_windows(snapshot) if purpose in APP_PRIORS.get(app_name(w),())]
        # A browser may host arbitrary web apps, so a process prior is never
        # sufficient evidence to send messages, submit forms, or play media.
        return {'status':'CANDIDATE' if len(matches)==1 else 'AMBIGUOUS' if matches else 'UNKNOWN',
                'purpose':purpose,'candidates':[{'app':app_name(w),'hwnd':w['hwnd'],
                    'pid':w['pid'],'source':'APP_PRIOR','ui_verified':False} for w in matches],
                'action_authorized':False}

    def describe(self,snapshot):
        live={identity(w) for w in live_windows(snapshot)}
        with self._lock:
            records=[deepcopy(r) for r,_ in self._events]
        stats=self.stats()
        lines=[f"Memória rápida: {stats['events']}/{self.capacity} recibos; {stats['contexts']} nós; {stats['dimensions']}D.",
               f"FHRR folhas: {stats['leaf_bytes']} bytes; persistência: não; autoridade: nenhuma."]
        for record in records[-12:]:
            state='janela atual' if record['window'] in live else 'histórico/sem vínculo atual'
            lines.append(f"{record['sequence']}. {record['app'] or 'global'} | {', '.join(s['action'] for s in record['steps'])} | {record['status']} | {state}")
        return '\n'.join(lines)

    def stats(self):
        with self._lock:
            return {'events':len(self._events),'contexts':len({r['window'] for r,_ in self._events}),
                    'dimensions':self.engine.dim,'leaf_bytes':sum(v.nbytes for _,v in self._events),
                    'capacity':self.capacity}
