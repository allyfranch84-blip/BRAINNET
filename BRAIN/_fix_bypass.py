from pathlib import Path
import ast

p = Path(r'A:\BRAINNET\BRAIN\BRAINNET.py')
src = p.read_text(encoding='utf-8')

# Marcadores para achar o bloco da ToM
start_marker = '# 1. TEORIA DA MENTE (mPFC) & GÂNGLIOS DA BASE (GO / NO-GO)'
end_marker = 'if julgamento.gate == MotorGateState.NO_GO and julgamento.is_physical_world:'

start_idx = src.find(start_marker)
end_idx = src.find(end_marker, start_idx)

if start_idx != -1 and end_idx != -1:
    old_block = src[start_idx:end_idx]
    
    # O novo bloco remove o dicionário (literal_app) e usa o Router Semântico
    new_block = '''# 1. TEORIA DA MENTE (mPFC) & GÂNGLIOS DA BASE (GO / NO-GO)
        # V9.5-FIX DEFINITIVO: Fim do dicionário de bypass. A classificação é semântica.
        _is_operational = False
        try:
            _route = self._kernel.router.evaluate_route(prompt_raw, ctx_agora)
            if _route.mode == "DETERMINISTIC_ACTION":
                _is_operational = True
        except Exception as e:
            logger.debug(f"[ROUTER] Falha ao classificar intencao: {e}")

        if _is_operational:
            julgamento = MentalizingJudgment(
                gate=MotorGateState.GO, intended_goal=prompt_raw,
                underlying_meaning="Comando classificado como OPERACIONAL pelo Semantic Router.",
                is_physical_world=False, requires_social_dialogue=False, confidence_evidence=1.0,
                explanation_to_user="Acionando motor."
            )
        else:
            julgamento = self._tom.evaluate_intent(prompt_raw, ctx_agora)

        '''
    
    # Substitui o bloco antigo (que continha o literal_app) pelo novo
    if 'literal_app = system_launch_target' in old_block:
        src = src[:start_idx] + new_block + src[end_idx:]
        
        try:
            ast.parse(src)
            p.write_text(src, encoding='utf-8')
            print('OK: Dicionario de bypass removido. O Router Semantico assume o controle.')
        except SyntaxError as e:
            print(f'ERRO DE SINTAXE: {e}')
    else:
        print('AVISO: O bloco atual nao contem o dicionario bypass antigo.')
else:
    print('FALHOU: Marcadores da ToM nao encontrados.')
