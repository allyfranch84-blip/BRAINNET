# P55.2 · Transporte autenticado e ciclo de vida da pesquisa

Base Codex: 115c92ccaa0c1178d2d302abb6c5401dcb8d3e3e. Base P55.1: 5b41453b15c840507e247b8e92b26cfd9553572f. Código desta rodada até c8a0414d245007ffb7d43bd43ffb06894f2ac656. Branch de revisão; updates/local não promovido.

## Hipótese e alterações
A P55.1 aceitava resultados correlacionados a um ID pendente mesmo antes de seu despacho e não diferenciava timeout antes/depois de despacho. Servidor sem ciclo de vida explícito dificultava testes. A P55.2 introduz BrowserTransport em módulo independente e conecta BrowserDeepBridge ao transporte. Fila de no máximo 32 pedidos pendentes, prazos monotônicos, relógio de parede para validade no worker, rejeição de resultado antecipado, duplicado, desconhecido ou vencido, autenticação antes de poll/heartbeat/result, encerramento explícito, erro de bind sem matar processo. O timeout depois de despacho significa efeito desconhecido, não ausência de ação. Não repetir automaticamente.

O worker verifica prazo antes de iniciar a ação; a pesquisa read-only revalida prazo entre estágios e registra aba ativada pelo usuário mesmo antes de receber o ID da criação. A revisão dos fixtures do fallback semântico adapta a disponibilidade ao novo transporte. O probe Windows fecha a ponte que possui em finally.

## Evidência desta sessão
- PASS_UNIT + PASS_INTEGRATION_LOOPBACK: python -m pytest -q -p no:cacheprovider test_browser_bridge_protocol.py test_browser_bridge_transport.py: 14 passaram, 9 subtestes, 1,17 s; Linux isolado, conexões HTTP reais para os 10 testes de transporte, porta aleatória, sem navegador.
- PASS_UNIT: node --test test_background_research.js: 6 passaram, API Chrome simulada, 53,4 ms.
- node --check background_research.js e py_compile do novo transporte passaram.
- Dois pedidos concorrentes receberam resultados corretamente mesmo com envio reverso. Resultado antes do despacho foi rejeitado por HTTP 409. Sem token ou token errado recebeu HTTP 403. Testes verificaram colisão de porta, fechamento, fila limitada, timeout antes/depois de despacho e mensagem inválida.
- Blobs testados e publicados coincidem: browser_bridge_protocol.py 6a9345787698ced6b4390462a8be4e652d60db46; test_browser_bridge_protocol.py 79742dd9e3583894ce0eec4413f44bd9b9fb2d27; browser_bridge_transport.py ca1dbf6b43b4ebed1d830fc4ca9aa1bf8b718a92; test_browser_bridge_transport.py 19af92e310fee9674a45e218ac2f38ba76819f44; background_research.js 92445a63bc69b9d7d35be54042c03e5e02449c7f; test_background_research.js b9e67b75f0420bcef7aa6761f494f0f34727e98a.
- Primeira falha desta rodada: nenhuma nos testes executados; nenhum teste de kernel completo realizado.
- NOT_TESTED: adaptação do BrowserDeepBridge no kernel real, fallback semântico, service worker real, navegação Google, foco e cursor Windows, cancelamento remoto de ação já despachada, regressão safe-full. Autenticação ainda pressupõe um único cliente de extensão confiável. Worker legado é serial. O transporte não comprova independência física nem paralelismo de navegação.

## Próximo ciclo
1. Preservar/publicar as últimas alterações operacionais Codex (probes, router, sincronizador) sem checkout destrutivo. O GitHub não recebeu o checkpoint posterior a 115c92c.
2. Verificar o diff P55.1/2 e a política de destinos do sincronizador. O cliente atualmente aceita só três arquivos P0 e não deve executar patches legados. Integrar seletivamente o conjunto completo Python/extensão, com hashes de base e backup; não alterar a main.
3. Rodar em A:\BRAINNET: VENV\Scripts\python.exe -B -m pytest -q -p no:cacheprovider BRAIN/test_browser_bridge_protocol.py BRAIN/test_browser_bridge_transport.py BRAIN/test_browser_concept_fallback.py; node --test EXTENSAO_NAVEGADOR/test_background_research.js; node --check EXTENSAO_NAVEGADOR/background.js; safe-full.
4. Configurar um único worker e token local aleatório (ver P55.1); probe real opt-in Windows, sem matar serviços, observar foco/cursor/aba e fonte. Não armazenar token em repo.
5. Só após prova real ligar pesquisa read-only ao catálogo e DeepThink; depois provar concorrência de pesquisa + notas, não cursor decorativo.
6. Retomar timeout de alternância de chat e esclarecimento a partir do checkpoint Codex atualizado.
