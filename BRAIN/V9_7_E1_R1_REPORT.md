# V9.7-E1-R1 — diagnóstico e integração parcial

Cada teste foi executado individualmente no estado original da missão R1 e em cópia isolada dos arquivos Python atuais com BRAINNET.py do checkpoint anterior à E1. Os 12 logs individuais em development_logs/V9_7_E1_R1_{atual,checkpoint}_<nome>.log contêm entrada, stack completo e saída. Ambas versões produziram as mesmas seis falhas; nesse recorte nenhuma é regressão demonstrada da E1. A cópia usa os demais arquivos atuais, portanto não é snapshot integral histórico.

1. test_bridge_click_moves_then_clicks_under_lock: entrada click (10,20), mock effector; esperava completed, obteve PermissionError porque não forneceu token. Contrato de autorização exige escopo ativo.
2. test_vision_sends_image_schema_and_unloads_model: entrada screenshot sintético; esperava keep_alive=0, recebeu '5m'; divergência de política de residência.
3. test_kernel_bridge_passes_direct_instruction_without_browser_url: entrada /ui no Brave; esperava despacho de instrução, obteve AttributeError _modo_coder_ativo em objeto construído sem inicialização; contrato do fixture/handler incompleto.
4. test_failed_ncd_stops_before_next_action: entrada type simulado; esperava FAILED_FACTUAL, obteve PermissionError antes da ação porque token não foi fornecido.
5. test_finished_without_verified_action_never_claims_success: entrada finished simulado; esperava AWAITING_GOAL_VERIFICATION, obteve PermissionError por ausência de token.
6. test_focus_change_blocks_input_before_actuation: entrada type com foco alterado; esperava FAILED_FACTUAL, obteve PermissionError por ausência de token.

Não foram enfraquecidos autorização, parser ou verificações. As falhas não foram corrigidas; políticas e contratos dos testes precisam ser reconciliados sem ocultar regressões.

Integração: antes do despacho de clique contextual READY_FOR_UIA, BrainnetBridge chama observe_ui_scene com alvo e required=True, compara hwnd, pid, nascimento do processo, idade da cena, geometria, identificador UIA e avaliação assess_target. Se falhar, observa novamente uma vez; se persistir, bloqueia antes do atuador. observe_ui_scene rejeita alteração de retângulo durante a captura. A autorização permanece separada no atuador. Isso não cobre protocolo visual por coordenadas, monitor Windows/MSS, nem revalidação de cena dentro da fila do atuador; o executor UIA conserva suas próprias verificações de identidade e foco.

Testes finais focados: 32 testes e 7 subtestes aprovados após último ajuste, development_logs/V9_7_E1_R1_SCENE_FINAL.log. Seleção auditada anterior ao último ajuste: 220 testes e 50 subtestes aprovados, V9_7_E1_R1_REGRESSION.log. Seleção visual completa: 42 passaram e 6 falharam, V9_7_E1_R1_VISUAL_FULL_FINAL.log. Sem GUI ou atuação física. Checkpoint e diff: development_logs/checkpoints/e1r1 e V9_7_E1_R1_DIFF.log. Critério completo não atingido.
