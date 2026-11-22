# V9.7 GUI FIX — Master Shell e telemetria

## Interface utilizada e causa
`iniciar/iniciar_aios.bat` inicia `npm run dev` em `A:\BRAINNET\INTERFACE DE USUARIO\BRAINDET IU\project`; `BRAINNET.py` abre `http://localhost:5173` por PyWebView. O `src/App.tsx` dessa pasta importa `src/components/MasterShell_(1).jsx`. A implementação V9.7-A alterou o projeto aninhado `project\project`, portanto não era a fonte apontada por esse launcher. O servidor Vite ativo e o processo aberto não foram inspecionados, logo outro launcher/porta ocupada pode mudar o resultado. O launcher usa servidor dev, não `dist`; build sozinho não atualiza processo Python já iniciado.

Widgets anteriores consultam get_world_model_status, get_metacognition_status, get_diagnostics e get_usage_report, ausentes de BrainnetBridge no arquivo atual; a ponte pywebview existir não prova que esses métodos ou métricas existam. O hook agora distingue método ausente de espera por conexão. Métricas cognitivas não foram inventadas ou sintetizadas.

## Alterações
MasterShell da pasta externa: quatro botões na conversa e no split, consultando `get_effort_mode` e salvando `set_effort_mode`; só muda seleção após confirmação e alterações atingem comandos seguintes. Método ausente no backend não cai silenciosamente no mock se a ponte está ativa. Kernel publica `aios:task` por evaluate_js com fase, modos e snapshot real; dashboard exibe último evento de tarefa recebido, IDs, limites e valores disponíveis. Eventos finais de tarefa antiga não substituem tarefa mais recente. Evento de cancelamento solicitado ou operações pendentes não aparece FINISHED. Uma atualização de tela/ponte limpa os dados locais, sem inventar estado de reconexão.

Limites: eventos somente no início e retorno/falha de send_command; não há fluxo de progresso no meio da inferência, registro persistente ou confirmação real do término de operação remota. Última falha verificada não está ligada; é exibida como indisponível. Um retorno normal não comprova objetivo. Orçamento não cobre todos os clientes, conforme R2.4. Nenhum evento possui texto de raciocínio interno.

## Evidência
16 testes Python passaram (test_v97_gui_events.py, test_v97r22_production.py, test_v97a_effort.py, test_v961_cognitive_reliability.py), desenvolvimento simulado, log development_logs/V9_7_GUI_FIX_TESTS_FINAL2.log. Captura de evaluate_js comprova formação de eventos start/final com mesmo task_id e os quatro modos, incluindo cancelamento solicitado; não comprova entrega no navegador. Build da pasta externa passou, log V9_7_GUI_FIX_BUILD_FINAL.log; `dist/assets/index-D-RI12VM.js` contém `aios:task` e seletor. Build gerou dist; launcher usa Vite dev. Não foram executados testes de navegador/DOM, reconexão real ou aplicativo Windows. O aplicativo aberto não foi reiniciado; não se declara sucesso em produção.

## Atualização supervisionada
Preservar trabalho e logs, encerrar a janela e o processo Python da BRAINNET pelo procedimento habitual do usuário, sem encerrar processos de terceiros. Confirmar que porta 5173 é servida pelo projeto externo indicado; se necessário iniciar `npm run dev` nessa pasta em terminal separado e executar `py -3.12 BRAINNET.py` em `A:\BRAINNET\BRAIN`. O launcher fornecido executa taskkill em Ollama; não foi executado nesta missão. Reabrir a conversa, conferir os botões, selecionar modo e enviar pergunta leve; abrir painel Telemetria e confirmar mesmo ID e valores. Não reiniciar automaticamente ou executar ações físicas.

Arquivos: BRAINNET.py, src/components/MasterShell_(1).jsx, src/components/TelemetryDashboard.jsx, src/components/useKernelTelemetry.js e test_v97_gui_events.py; checkpoints em development_logs/checkpoints/gui_fix (hook não alterado no checkpoint). GUI em produção não verificada.
