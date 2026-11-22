import time
import threading
from effector import Effector
from causal_trajectory import WindowsAppResolver
from execution_authority import authorization_scope, require_action_allowed

print("=== TESTE DE CORPO BRUTO (SEM MATEMÁTICA) ===")
eff = Effector()
resolver = WindowsAppResolver(eff)
token = threading.Event()

print("Solicitando abertura do Notepad via Menu Iniciar...")
with authorization_scope(token):
    require_action_allowed("OPEN_APP")
    # Isso vai digitar "notepad" no menu iniciar e apertar Enter
    resolver._open_via_start_menu("notepad")

time.sleep(2)
if resolver.is_process_running("notepad"):
    print("✅ SUCESSO: O Notepad abriu. O corpo (motor) está funcionando!")
else:
    print("❌ FALHA: O Notepad não abriu. O motor está quebrado.")
