"""Offline-first distillation preparation; no network transport is installed."""
import hashlib,json,threading
from decimal import Decimal, InvalidOperation

MAX_USD=Decimal('0.70')

def estimate_cost(input_tokens,output_tokens,input_usd_per_million,output_usd_per_million):
    if any(type(v) is not int or v < 0 for v in (input_tokens,output_tokens)):
        raise ValueError('token counts must be nonnegative integers')
    try: rates=[Decimal(str(x)) for x in (input_usd_per_million,output_usd_per_million)]
    except (InvalidOperation,ValueError): raise ValueError('invalid price')
    if any(not x.is_finite() or x<0 for x in rates): raise ValueError('invalid price')
    return (Decimal(input_tokens)*rates[0]+Decimal(output_tokens)*rates[1])/Decimal(1000000)

def group_split(group_id):
    if not isinstance(group_id,str) or not group_id.strip(): raise ValueError('group id required')
    v=int.from_bytes(hashlib.sha256(group_id.encode('utf-8')).digest()[:4],'big')%100
    return 'train' if v<70 else 'validation' if v<85 else 'test'

def validate_record(row):
    required=('input','local_response','verified_outcome','category','criterion','evidence_id','teacher_model','group_id')
    if not isinstance(row,dict) or any(k not in row for k in required): raise ValueError('missing fields')
    if any(not isinstance(row[k],str) or not row[k].strip() for k in ('input','category','criterion','evidence_id','group_id')): raise ValueError('invalid record')
    if row['local_response'] is not None and not isinstance(row['local_response'],str): raise ValueError('invalid local response')
    if row['teacher_model'] is not None and not isinstance(row['teacher_model'],str): raise ValueError('invalid teacher')
    return {**row,'split':group_split(row['group_id'])}

def validate_dataset(rows):
    seen = {}
    result = []
    for item in rows:
        row = validate_record(item)
        normalized = ' '.join(row['input'].casefold().split())
        group = seen.setdefault(normalized, row['group_id'])
        if group != row['group_id']:
            raise ValueError('identical inputs must share a group')
        result.append(row)
    return result

def summarize_evaluations(rows):
    """Aggregate human-verified outcomes; unknown metrics stay unknown."""
    if not isinstance(rows, list): raise ValueError('rows must be a list')
    checked = [r for r in rows if r.get('verified') is True and type(r.get('correct')) is bool]
    hallucinations = [r for r in rows if r.get('verified') is True and type(r.get('hallucination')) is bool]
    return {'cases':len(rows), 'verified_cases':len(checked),
            'error_rate':sum(not r['correct'] for r in checked)/len(checked) if checked else None,
            'hallucination_rate':sum(r['hallucination'] for r in hallucinations)/len(hallucinations) if hallucinations else None,
            'latency_ms':'NOT_MEASURED','memory_bytes':'NOT_MEASURED','promotion':'DISABLED'}

class OfflineTeacherBudget:
    """Simulated transport only: no provider adapter or paid calls enabled."""
    def __init__(self, limit='0.70'):
        self.limit=Decimal(str(limit))
        if not self.limit.is_finite() or not Decimal('0')<self.limit<=MAX_USD: raise ValueError('limit must be <= $0.70')
        self._lock=threading.Lock();self.spent=Decimal(0);self.reserved=Decimal(0);self.completed={};self.unknown=set()
    def request(self,record,*,input_tokens,max_output_tokens,input_rate,output_rate,transport=None,simulation=False,license_reviewed=False):
        row=validate_record(record)
        if simulation is not True or transport is None: raise RuntimeError('remote transport disabled; explicit future implementation required')
        if license_reviewed is not True or not row['teacher_model']: raise ValueError('teacher and licensing review required')
        request_id=hashlib.sha256(json.dumps([row['group_id'],row['input'],row['teacher_model']],ensure_ascii=False).encode()).hexdigest()
        estimate=estimate_cost(input_tokens,max_output_tokens,input_rate,output_rate)
        with self._lock:
            if request_id in self.completed:return self.completed[request_id]
            if self.unknown or request_id in getattr(self,'_active',set()): raise RuntimeError('pending or unknown cost: reconcile before retry')
            if self.spent+self.reserved+estimate>self.limit:raise RuntimeError('budget exceeded')
            if not hasattr(self,'_active'):self._active=set()
            self._active.add(request_id);self.reserved+=estimate
        try:
            result=transport({'model':row['teacher_model'],'messages':[{'role':'user','content':row['input']}], 'max_tokens':max_output_tokens})
            usage=result.get('usage',{}) if isinstance(result,dict) else {}
            it,ot=usage.get('prompt_tokens'),usage.get('completion_tokens')
            cost=estimate_cost(it,ot,input_rate,output_rate)
            if it>input_tokens or ot>max_output_tokens or cost>estimate: raise ValueError('reported use exceeds reservation')
            choices=result.get('choices')
            text=choices[0].get('message',{}).get('content') if isinstance(choices,list) and choices and isinstance(choices[0],dict) else None
            if not isinstance(text,str) or not text.strip(): raise ValueError('invalid teacher response')
            with self._lock:
                self.reserved-=estimate;self.spent+=cost;self._active.remove(request_id)
                final={'request_id':request_id,'content':text,'usage':{'input':it,'output':ot},'cost_usd':str(cost),'simulated':True}
                self.completed[request_id]=final
            return final
        except Exception:
            with self._lock:self.unknown.add(request_id);self._active.discard(request_id)
            raise
