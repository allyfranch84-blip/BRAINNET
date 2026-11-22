
## 2026-11-10 16:21:39 -0300 — Estabilização do motor e parser visual

- BRAINNET.py: removida a segunda instanciação de ErrorBlackBoxEngine; mantida a primeira e a ligação existente do motor à mesma instância.
- ui_tars_protocol.py: acrescentado tratamento de ValueError de ast.literal_eval para reportar coordenadas inválidas em start_box.
- Validação: sintaxe dos dois arquivos verificada com ast.parse. Pytest não executado por instrução do usuário.
- Limitação: validação de sintaxe não demonstra que a execução visual ou a inicialização do Kernel funcionam.

## 2026-11-10 16:34:01 -0300 — Execução visual pelo terminal

- BRAINNET.py: inicia e encerra os workers da ponte no caminho síncrono do UI-TARS; resultado inclui trace e motivo de falha e usa ícone de sucesso somente quando confirmado.
- Sintaxe validada com ast.parse; verificação simulada não concluiu e foi interrompida; pytest não executado. O protocolo ainda não implementa arrastar e a execução visual real não foi validada.

## 2026-11-10 16:37:02 -0300 — Coordenadas inválidas no UI-TARS

- vision_eye.py: exemplo numérico explícito no prompt; proíbe placeholders x/y.
- ui_tars_protocol.py: rejeita propostas inválidas, reobserva e informa o erro ao modelo; interrompe após três propostas inválidas.
- BRAINNET.py: apresenta o motivo de proposta inválida.
- Validação: ast.parse e teste direto do parser para coordenadas numéricas e (x,y). Pytest não executado. Arrasto ainda não implementado.

## 2026-11-10 16:45:42 -0300 — Coordenadas e repetição visual

- ui_tars_protocol.py: aceita tuplas numéricas literais e strings de coordenadas, preservando validação; limita repetição do mesmo ponto.
- vision_eye.py: remove exemplo numérico que o VLM estava repetindo e instrução contraditória para arrastar; esclarece o histórico.
- Validação: sintaxe e parser exercitado com entradas válidas e inválidas; pytest não executado. Arrastar ainda não implementado.

## 2026-11-10 16:51:02 -0300 — Arrasto no UI-TARS

- effector.py: gesto de arrastar com LEFTDOWN e liberação em finally.
- actuator_bridge.py: roteamento mouse_drag sob bloqueio de entrada.
- ui_tars_protocol.py: validação de start_box/end_box e conversão para pontos de tela; contrato DRAG.
- vision_eye.py: drag permitido e orientação para formas no Paint.
- causal_trajectory.py e cybernetic_verifier.py: DRAG reconhecido na captura e verificação.
- Validação: sintaxe, parser, conversão de coordenadas e liberação simulada após exceção; pytest não executado. Não houve teste real no Paint nem validação da escolha de ferramenta.

## 2026-11-10 17:36:27 -0300 — Parser visual após regressão

- ui_tars_protocol.py: restaurados contratos JSON e Thought/Action, clique direito, drag, entrada posicional e validação de atalhos e coordenadas. Erros agora mostram a proposta de ação inválida, sem inferir cliques de texto livre.
- Validação direta do parser para JSON válido, arrasto, clique direito, atalho e rejeição de coordenadas ou texto livre inválidos. Pytest não executado; Paint não foi acionado.

## 2026-11-10 18:36:06 -0300 — Missão 002.1: scroll e verificação do círculo

- vision_eye.py: prompt permite scroll com argumentos aceitos pelo parser.
- visual_goal_verifier.py: comparação determinística conservadora de novos pixels vermelhos e geometria, com canvas explícito.
- ui_tars_protocol.py: verifica círculo somente com canvas identificado, janela e geometria consistentes; caso contrário mantém GOAL_UNVERIFIED.
- test_ui_tars_protocol.py: imagens sintéticas e testes de integração simulada.
- Validação: unittest, 23 aprovados; pytest não executado, sem mouse real ou Ollama. Git indisponível no diretório; suítes pytest específicas não executadas.

## 2026-11-10 18:46:52 -0300 — Missão 003A: adaptadores de inferência

- inference_backend.py: contrato, seleção ollama/llamacpp, respostas completas e streaming, erros tipados e supervisor opt-in de processo próprio.
- test_inference_backend.py: testes simulados de seleção, rede, cancelamento, timeout, falha e recuperação limitada, sem servidores/modelos reais.
- Validação: unittest 17 aprovados; sintaxe validada. Primeira execução teve uma falha de acesso a diretório temporário, removida por simulação; execução final passou. Pytest não executado. Nenhum cliente existente foi migrado e o backend novo não foi validado com modelo real.

- Complemento 003A: adaptador llama.cpp rejeita modelo diferente do configurado; execução final: 18 testes simulados aprovados.

## 2026-11-10 18:51:59 -0300 — Adendo 003A: isolamento e supervisão

- inference_backend.py: exige porta distinta do Ollama e executável fora da instalação, observa portas ocupadas, registra eventos e limita recuperações com intervalo. Checagem separada de assinatura GGUF do modelo/projetor e leitura de template sem afirmar compatibilidade.
- test_inference_backend.py: simulações de falhas repetidas, porta ocupada, modelo ausente, Vulkan, recuperação, artefatos e encerramento.
- Resultado: 26 testes unittest aprovados; uma execução intermediária falhou devido a objeto BytesIO simulado reutilizado, corrigido antes da execução final. Nenhum llama.cpp real foi instalado ou iniciado; pytest não executado.
