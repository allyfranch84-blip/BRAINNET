"""Bounded on-demand telemetry and conservative motor clarification."""
import os
import re
import time
import unicodedata


def shape_clarification(text):
    normalized = ''.join(c for c in unicodedata.normalize('NFKD',text.casefold()) if not unicodedata.combining(c))
    if '?' in normalized or normalized.startswith(('nao ','nunca ','jamais ')):
        return None
    if not re.match(r'^\s*(?:mova|movimente|desenhe|faca|trace|crie|quero que voce (?:faca|desenhe|mova))\b',normalized):
        return None
    if re.search(r'\b(?:mouse|cursor|ponteiro)\b',normalized) and re.search(r'\b(?:quadrado|circulo|triangulo|retangulo|espiral)\b',normalized):
        size = bool(re.search(r'\b(?:\d+\s*(?:px|pixels?)|qualquer tamanho)\b',normalized))
        mode = bool(re.search(r'\b(?:sem (?:pressionar|clicar)|com (?:o )?botao pressionado)\b',normalized))
        questions = []
        if not mode: questions.append('Você quer percorrer o contorno ou desenhar com o botão pressionado?')
        if not size: questions.append('Qual tamanho em pixels? Pode delegar o tamanho.')
        if questions:
            return {'status':'CLARIFICATION_REQUIRED','reply':' '.join(questions)+' Nenhuma ação executada.','dispatched':False,'logs':[]}
        return {'status':'UNAVAILABLE','reply':'Entendi os parâmetros. Este tipo de trajetória ainda não está disponível. O executor local aceita quadrados e triângulos retângulos isósceles sem clicar, com lado ou cateto de 1 a 300 pixels. Outras figuras e desenhos com botão pressionado ainda não são suportados.','dispatched':False,'logs':[]}
    if re.search(r'\b(?:e|depois|para|ate)\s*[.!]?\s*$',normalized):
        return {'status':'CLARIFICATION_REQUIRED','reply':'O pedido parece incompleto. Qual é a ação ou o destino que falta? Nenhuma ação foi executada.','dispatched':False,'logs':[]}
    return None


def on_demand_telemetry(kernel):
    import psutil
    hw = {}
    try:
        mem=psutil.virtual_memory(); proc=psutil.Process(os.getpid())
        hw.update(ram_total_bytes=mem.total,ram_used_bytes=mem.total-mem.available,ram_available_bytes=mem.available,process_rss_bytes=proc.memory_info().rss)
        hw['cpu_total_pct']=psutil.cpu_percent(interval=.10)
        hw['cpu_process_pct']=proc.cpu_percent(interval=.10)
    except (OSError,psutil.Error):
        pass
    lock=getattr(kernel,'_runtime_task_lock',None)
    active=[]; recent=[]
    if lock is not None:
        with lock:
            active=[v.snapshot() for v in getattr(kernel,'_runtime_tasks',{}).values()]
            recent=[v.snapshot() for v in getattr(kernel,'_runtime_recent_tasks',())]
    return {'available':True,'source':'psutil · sob demanda','timestamp':time.time(),'stale':False,'hardware':hw,'inference':{},'kernel':{'running':bool(getattr(kernel,'is_running',False)),'active_tasks':active,'recent_tasks':recent}}
