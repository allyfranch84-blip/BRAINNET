# ==============================================================================
# HABILIDADE CRISTALIZADA AUTOMATICAMENTE PELO SONO REM DO BRAINNET
# INTENCAO: abra o whatsapp
# SUCESSOS CONSOLIDADOS: 3
# HASH SINAPTICO: b1ea1065080b6e184325b69b48c59420
# ==============================================================================
from skill_loader import skill

PIPELINE_PAYLOAD = {"status":"AUTO_CURADO","causa_original":"O WhatsApp n\u00e3o foi encontrado ou n\u00e3o abriu corretamente.","passos_corretivos":[{"passo":1,"acao":"LAUNCH","cmd":"start","keys":["whatsapp"],"text":"Tente abrir o WhatsApp diretamente pelo comando de linha de comando."},{"passo":2,"acao":"WAIT","cmd":"timeout","keys":[5],"text":"Aguarde 5 segundos para ver se o WhatsApp abre."},{"passo":3,"acao":"LAUNCH","cmd":"start","keys":["chrome"],"text":"Se o WhatsApp n\u00e3o abrir, tente abrir o navegador Chrome."},{"passo":4,"acao":"TYPE","cmd":"https://web.whatsapp.com","keys":["https://web.whatsapp.com"],"text":"No Chrome, digite a URL do WhatsApp Web."},{"passo":5,"acao":"WAIT","cmd":"timeout","keys":[5],"text":"Aguarde 5 segundos para ver se o WhatsApp Web abre."}]}

@skill(name="abra_o_whatsapp", description="Rotina automatica cristalizada para: abra o whatsapp")
def execute_skill(*args, **kwargs):
    """Execucao determinista estatica com custo 0 de IA."""
    return {
        "status": "COMPLETED",
        "mode": "CRYSTALLIZED_ZERO_LLM",
        "intent": "abra o whatsapp",
        "payload": PIPELINE_PAYLOAD
    }
