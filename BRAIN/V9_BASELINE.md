# BRAINNET V9 — baseline

Data: 2026-11-11. Não há repositório Git detectável em A:\BRAINNET\BRAIN ou em seus diretórios pais; alterações preexistentes não podem ser diferenciadas por diff Git. A inspeção não iniciou o Kernel. O inicializador iniciar\iniciar_aios.bat chama BRAIN\BRAINNET.py e contém taskkill do Ollama; não foi executado.

172 arquivos Python analisados por ast.parse: nenhum erro de sintaxe; aviso de escape em _fix_ui_tars.py. Foram localizados: eh_pergunta em BRAINNET.py; evaluate_intent em theory_of_mind.py; _avaliar_resultado em autonomous_harvester.py; _apply_auto_fix em engineering_agent.py; parse_ui_action em ui_tars_protocol.py; describe_ui_with_protocol e descrever_tela em vision_eye.py. Não foram encontrados os arquivos-fonte semantic_layer.py, cognitive_orchestrator.py, signal_collector.py nem as implementações concept_from_click e _orchestrator_tick. model_residency_manager.py existe sem integração automática comprovada. Há 72 arquivos test*.py; nem todos foram classificados como seguros para execução.

Baseline selecionada: 141 testes unittest simulados; 1 falha e 4 erros. test_host_context_and_grounded_but_blocked espera ACTION_BLOCKED mas o código retorna READY_FOR_UIA. Quatro testes drag de test_ui_tars_protocol não fornecem o token exigido por execution_authority. Detalhes em V9_BASELINE_TEST_OUTPUT.txt. Não foi executada a suíte completa, pois pode executar GUI, banco ou serviços. Não foi executado pytest.

Endpoints: assistant_prompts.py usa OLLAMA_HOST com padrão 127.0.0.1:11435; vision_eye.py usa OLLAMA_CHAT_URL com padrão 127.0.0.1:11435; BRAINNET.py contém chamadas fixas 11434. inference_backend.py preserva Ollama como padrão e aceita llamacpp explícito em porta própria. Nenhum serviço foi iniciado nesta auditoria.

Estado prévio: modificações UIA iniciadas na conversa e não validadas; o decorador authorized_trajectory cria token na ausência de autorização. Parser visual contém fallback por linguagem natural ao OCR. Esses comportamentos são riscos a investigar, não resultados de teste real.
