# V9.6.1 — confiabilidade cognitiva

## Causas e correções
O ponto send_command descartava registros de respostas que retornavam antes do trecho final; agora registra mensagens de usuário e respostas com identificadores e timestamp após os retornos normais, inclusive ajuda e perguntas de histórico. A primeira/última mensagem anterior é recuperada dos eventos de usuário disponíveis; não inclui o turno corrente. O histórico permanece limitado a 120 eventos e não é persistido: ausência de dados é comunicada; cópia de histórico não é armazenada.

Relatos explícitos com "não conseguiu", "não consegui" ou "não funcionou" recebem resposta sem iniciar operação. Não é um classificador geral: outras formas, citações, correções e comentários requerem mais trabalho. O alvo "note pad" é normalizado para notepad unicamente depois da análise de um comando de abertura reconhecido. Isso não representa autorização.

Ajuda natural e /help chegam ao mesmo bloco, antecipado antes da coleta de contexto. Pesquisa natural simples e slash agora compartilham web_search_autonomous, que encontra títulos, URLs e trechos, sem abrir navegador ou gravar memória; retorno diferencia SEARCH_STARTED de SOURCES_FOUND e deixa explícito que conteúdo e afirmações não foram verificados. É uma mudança de comportamento de /pesquise: deixa de abrir abas e resumir por modelo. Chamadas diretas a deep_multi_tab_research e outros fluxos legados não foram alterados. Não foram implementados CONTENT_EXTRACTED, CLAIMS_VERIFIED ou MEMORY_COMMITTED, verificação independente de fatos, nem prevenção global de escrita de dados contraditórios. O resultado não prova a veracidade das fontes.

## Testes
Sintaxe por ast.parse. Focados com testes da V9.5.2: 12 aprovados (antes do sexto teste novo). Regressão segura final: 209 testes e 50 subtestes aprovados em 5,28 s, exit 0, development_logs/V9_6_1_REGRESSION_FINAL2.log. Uma repetição anterior mostrou 1 falha no acesso à ajuda; o bloco foi movido antes da captura do contexto e o teste passou na repetição. A primeira coleta restrita foi interrompida por demora; logs preservados. A suíte completa não foi executada. Testes usam mocks; não executam pesquisa web, modelos, GUI ou atuadores reais.

## Pendências
Não foi anexado histórico completo V9.6 para testes de sequência além dos exemplos da missão. Perguntas de arquitetura, inventário de modelos, estado de mielinização e auditoria do próprio código não foram conectados a evidências. Dom Pedro I e afirmações falsas não foram verificados contra fontes reais; perguntas históricas fora da busca podem continuar suscetíveis a alucinações. Equivalência geral de intenções, retomada persistente e identificação confiável de falhas e eventos históricos permanecem incompletas. Correspondência Windows/MSS, DPI, ações de mouse e diagnóstico de backend seguem pendentes. A V9.6 validou estruturalmente uma proposta simulada de código, sem comprovar geração real, inserção ou execução. O reconhecimento não dispensa autorização; não houve alteração no mecanismo de autorização.

## Operação supervisionada futura
Após revisão e reinicialização manual, testar conversa e busca sem atuação; confirmar fontes e comparar histórico exibido. Para abrir Notepad ou escrever conteúdo, autorizar a ação separadamente e verificar resultado. Não declarar conclusão de tarefa ou fato apenas por fonte encontrada.

Checkpoint: development_logs/checkpoints/v961. Não foram alterados bancos nem executadas ações físicas.
