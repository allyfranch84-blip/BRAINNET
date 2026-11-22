# V9.8-A2.1 — Trajetória segura

**Estado: NOT_READY.** Nenhum movimento, clique, digitação ou reinício foi realizado. O laboratório existente permaneceu aberto; a versão WinForms ainda não foi iniciada nesta missão.

## Observações reais

- Task ID de diagnóstico: `V9_8_A2_1_OBSERVE` (não autoriza atuação).
- HWND do laboratório: 1573244, PID 5244; retângulo observado `(527, 241, 887, 552)` na coordenada devolvida pelo observador.
- Última leitura de cursor: `(376, 396)`; timestamp Unix `1794510521.3966007`, sessão 1, desktop e input desktop `Default`, fonte `GetCursorPos`. Essa posição é instantânea e precisa ser lida novamente antes de qualquer proposta.
- DISPLAY1: `(0, 0, 1920, 1080)`; área útil `(0, 0, 1920, 1048)`. DISPLAY2: `(1920, 0, 3520, 900)`; área útil `(1920, 0, 3520, 868)`. Enumeração MSS correspondente por retângulo não comprova identidade estável entre índices.
- Observador: `GetAwarenessFromDpiAwarenessContext` retornou 0 (DPI unaware). A janela do laboratório também retornou 0 e `GetDpiForWindow` retornou 96; isso pode ser DPI virtualizado, não prova o DPI físico. `LogicalToPhysicalPointForPerMonitorDPI` retornou falha para a chamada experimental. Contexto DPI do executor efetivo não foi identificado. Não foi comprovado que UIA, observador e executor compartilham espaço físico.
- A varredura atual de UIA retornou apenas um `TitleBarControl`, sem Name e AutomationId, retângulo `(557, 249, 879, 272)`; padrões não informados. Não há evidência atual dos dois botões nem verificação de TESTE A/B. A versão WinForms no disco declara nomes acessíveis, mas não foi executada ou validada aqui.

## Preparação implementada

`capability_lab.prepare_safe_trajectory` valida identificação da janela, confirmação de DPI, retângulo de segurança observado, inventário de controles, desktop, posição atual, área útil do monitor e interseção de todo o segmento com controles. Calcula +30 apenas depois dessas pré-condições; seu estado pronto é `AWAITING_AUTHORIZATION`, sem qualquer despacho de entrada. Resultado real permanece `NOT_READY`: não há região segura identificada na janela atual, controles e espaço de coordenadas não estão verificados. Não foi criada região fictícia nem proposta de movimento acionável.

Executor previsto após autorização separada: `ActuatorBridge.dispatch('mouse_move', ...)` e `Effector.mouse_move`, respeitando autoridade existente. Verificação independente prevista: nova leitura Win32 `GetCursorPos`, após confirmar equivalência física dos espaços. Autorização atual: **não concedida**.

## Testes

`python -m unittest test_v98a2_1_safe_trajectory test_v98a2_proprioception -v`: 8 testes executados, 8 aprovados, 0 falhas. Cobrem geometria, exclusão de controles, DPI indisponível, limites, coordenadas negativas, desktop e autorização. Não provam comportamento físico nem acessibilidade da versão WinForms.

## Bloqueios para a próxima etapa

A instância atual não expõe dados necessários para confirmar botões nem uma área segura. É necessária inspeção de uma instância atualizada do laboratório, com autorização separada para abri-la, sem fechar a atual, além de comprovar DPI e coordenadas do executor. Somente após identificar uma região vazia observada poderá ser solicitado que o operador posicione o cursor nela; uma nova leitura então permitirá calcular o destino +30. Qualquer execução requer autorização separada.

Evidência bruta: `development_logs/V9_8_A2_1_observation.json` e script de leitura `development_logs/V9_8_A2_1_observe.py`.
