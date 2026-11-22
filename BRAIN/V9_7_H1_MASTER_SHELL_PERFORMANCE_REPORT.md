# V9.7-H1 — desempenho do Master Shell externo

## Alterações
Em `project/src/components/MasterShell_(1).jsx`, removida a montagem global de WorldModelWidget e MetacognitionGauge que aparecia em todas as páginas exceto Telemetria; os coletores continuam na página dedicada. TelemetryDashboard é importado sob demanda com fallback. Chat mantém o seletor e a cópia do histórico completo; renderiza inicialmente as últimas 100 mensagens e permite carregar blocos anteriores de 100. Texto para copiar é memoizado apenas quando as mensagens mudam. A lista inicial de logs agora respeita limite de 200, igual ao fluxo posterior. DotTerrain suspende o requestAnimationFrame quando document.hidden e remove o listener ao desmontar. Não houve alteração de backend, launcher ou cópia aninhada.

Arquivos adicionais: src/components/chatHistory.mjs e scripts/test-chat-history.mjs. Checkpoint development_logs/checkpoints/v97h1/MasterShell.jsx, hash anterior V9_7_H1_BEFORE_HASH.log e diff V9_7_H1_DIFF.log.

## Medições
Bundle de referência do build externo anterior: JS inicial 379.335 bytes, CSS 30.561 bytes. Novo build: JS inicial 371.709 bytes, chunk de TelemetryDashboard 9.335 bytes e CSS 30.592 bytes. O JS inicial é 7.626 bytes menor sem compressão; soma do JS quando telemetria é carregada é 381.044 bytes, portanto não se afirma redução do total. Arquivos gerados em node_modules/.cache/v97h1-build-final; log V9_7_H1_BUILD_FINAL.log. Não foram medidos tempo de render, número de renders, memória do renderer ou CPU em repouso, nem executado profiler em janela real. Não é possível concluir ganho de desempenho global.

## Testes e limites
Build externo exit 0. Teste Node com 1.000 mensagens passou: mostra as últimas 100, expande para 200 e preserva texto integral para cópia; log V9_7_H1_CHAT_TEST.log. Dez testes Python simulados de eventos/modos/backend passaram; log V9_7_H1_TESTS.log. Não foram executados testes DOM, testes de navegação e duplicação de listeners, nem medição real de temporizadores ou identidade visual. A inspeção de código confirma cleanup do listener visibilitychange e do requestAnimationFrame e a página dedicada continua no roteamento, mas não comprova comportamento visual em produção. Histórico em memória continua ilimitado para não descartar mensagens; a paginação controla apenas nós renderizados. Outras animações e timers não foram medidos nem alterados.
