"""In-memory long-task contracts, with explicit serialization only."""
import copy
import json
from urllib.parse import urlsplit

class BookDraft:
    def __init__(self, goal, chapters):
        if not goal or not chapters:raise ValueError('goal and chapters required')
        self.goal=goal;self.chapters=[{'title':x,'status':'PENDING','text':''} for x in chapters]
        self.continuity=[];self.status='PENDING';self.attempts={};self.events=[];self.max_attempts=2
    def record(self,index,*,status,text=''):
        if status not in ('PENDING','DRAFT','REVIEWED','FAILED','CANCELLED'):raise ValueError('invalid status')
        self.chapters[index].update(status=status,text=text)
        self.status='VERIFYING' if all(c['status']=='REVIEWED' and c['text'] for c in self.chapters) else 'IN_PROGRESS'
    def generate_sections(self, generate, checkpoint, *, cancelled=lambda: False, emit=lambda index, text: None):
        """Generate draft blocks with explicit completion evidence; no auto-verification."""
        if not callable(generate) or not callable(checkpoint): raise ValueError('callbacks required')
        for index, chapter in enumerate(self.chapters):
            if chapter['status'] == 'DRAFT' and chapter['text']:
                continue
            if chapter['text']:
                self.status='PARTIAL_UNCONFIRMED'; checkpoint(self); return self.status
            if cancelled():
                self.status='CANCELLED'; checkpoint(self); return self.status
            previous='\n\n'.join(c['text'] for c in self.chapters[:index] if c['text'])[-2400:]
            prompt=(f'Objetivo: {self.goal}\nEstrutura: '+', '.join(c['title'] for c in self.chapters)
                    +f'\nEscreva apenas a seção {index+1}: {chapter["title"]}. '
                    +'Continue coerentemente sem repetir seções anteriores. '
                    +'Trate fatos não verificados como incertos.\nTexto anterior (trecho):\n'+previous)
            try:
                result=generate(prompt)
                text=result.text.strip()
                if not text: raise ValueError('empty section')
                if any(text == c['text'] for c in self.chapters[:index] if c['text']):
                    self.status='PARTIAL_DUPLICATE'; checkpoint(self); return self.status
                chapter['text']=text
                if getattr(result,'finish_reason',None) not in ('stop','end_turn'):
                    chapter['status']='PENDING'; self.status='PARTIAL_UNCONFIRMED'
                    checkpoint(self); emit(index,text); return self.status
                chapter['status']='DRAFT'
                checkpoint(self); emit(index,text)
            except Exception as exc:
                self.status='PARTIAL_ERROR'; self.events.append({'chapter':index,'state':'FAILED','error':type(exc).__name__})
                checkpoint(self); return self.status
        self.status='DRAFT_COMPLETE'; checkpoint(self); return self.status
    def record_attempt(self,index,*,succeeded,evidence=None,text=''):
        """Record an explicitly supplied observation; never invokes an actuator."""
        if not isinstance(index,int) or isinstance(index,bool) or not 0<=index<len(self.chapters):raise ValueError('invalid chapter')
        count=self.attempts.get(index,0)
        if count>=self.max_attempts:
            self.status='BLOCKED';return False
        self.attempts[index]=count+1
        if succeeded is True and isinstance(evidence,str) and evidence.strip() and text.strip():
            self.record(index,status='REVIEWED',text=text)
            self.events.append({'chapter':index,'state':'VERIFIED','evidence':evidence})
            return True
        self.record(index,status='FAILED')
        self.events.append({'chapter':index,'state':'FAILED','evidence':evidence})
        self.status='REPLANNING' if self.attempts[index]<self.max_attempts else 'BLOCKED'
        return False
    def verify_completion(self, verifier):
        if self.status!='VERIFYING' or not callable(verifier):return False
        try:verified=verifier(copy.deepcopy(self.chapters)) is True
        except Exception:verified=False
        self.status='COMPLETE' if verified else 'PARTIAL'
        self.events.append({'state':'GOAL_VERIFIED' if verified else 'GOAL_UNVERIFIED'})
        return verified
    def causal_map(self):
        lines=['flowchart TD','    START["Objetivo registrado"]']
        for i, chapter in enumerate(self.chapters):
            state='VERIFIED' if chapter['status']=='REVIEWED' else ('FAILED' if chapter['status']=='FAILED' else 'PLANNED')
            lines.append(f'    C{i}["Capítulo {i+1}: {state}"]')
            lines.append(f'    {"START" if i==0 else "C"+str(i-1)} --> C{i}')
        for i, event in enumerate(self.events):
            state=event.get('state','UNKNOWN')
            if state not in ('VERIFIED','FAILED','GOAL_VERIFIED','GOAL_UNVERIFIED'):continue
            lines.append(f'    E{i}["Evento {i+1}: {state}"]')
            if isinstance(event.get('chapter'),int):lines.append(f'    C{event["chapter"]} -.-> E{i}')
        return '\n'.join(lines)+'\n'
    def serialize(self):return json.dumps({'version':1,'goal':self.goal,'chapters':self.chapters,'continuity':self.continuity,'attempts':self.attempts,'events':self.events,'max_attempts':self.max_attempts,'status':self.status},ensure_ascii=False)
    @classmethod
    def restore(cls,data):
        value=json.loads(data)
        if value.get('version')!=1:raise ValueError('unsupported version')
        obj=cls(value['goal'],[c['title'] for c in value['chapters']]);obj.chapters=copy.deepcopy(value['chapters']);obj.continuity=value['continuity']
        obj.attempts={int(k):v for k,v in value.get('attempts',{}).items()};obj.events=value.get('events',[])
        obj.max_attempts=value.get('max_attempts',2)
        # Restored artifacts must revalidate the final state before claiming completion.
        obj.status='VERIFYING' if all(c['status']=='REVIEWED' and c['text'] for c in obj.chapters) else 'IN_PROGRESS'
        return obj

def inspect_video(url, fetch_metadata, fetch_captions):
    parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname not in ('youtube.com','www.youtube.com','youtu.be','m.youtube.com') or parsed.username or parsed.password:
        return {'status':'INVALID_URL','visual_analyzed':False}
    try:meta=fetch_metadata(url)
    except Exception:return {'status':'UNAVAILABLE','visual_analyzed':False}
    try:captions=fetch_captions(url)
    except Exception:return {'status':'CAPTIONS_UNAVAILABLE','source':url,'visual_analyzed':False}
    if not captions:return {'status':'CAPTIONS_UNAVAILABLE','source':url,'visual_analyzed':False}
    return {'status':'CAPTIONS_AVAILABLE','source':url,'metadata':meta,'segments':captions,'visual_analyzed':False}
