# V9.5.2 — confiabilidade e continuidade

## Escopo e referência

A mensagem solicitou referência a histórico real V9, mas nenhum histórico específico foi anexado nesta solicitação; não foi possível atribuir as falhas de Dom Pedro, status ou monitores a uma execução específica. Os logs de triângulo do histórico da conversa mostram proposta inválida e repetição, mas não incluem a proposta completa necessária para identificar sua forma exata nesta versão.

## Continuidade — parcial

`send_command` não sobrescreve mais `_last_executed_task` em toda mensagem não slash; passa a registrar comandos operacionais reconhecidos. Para falha visual, `_last_task_event` mantém task_id, tarefa, status, motivo e última etapa; perguntas sobre erro consultam esse evento e, se não houver motivo, a Caixa Preta em RAM, informando dados não disponíveis. Pedido de retomada retorna necessidade de revalidação, sem agir automaticamente. Testes simulam falha e pergunta subsequente.

Limitações: o reconhecimento operacional é conservador e não cobre todas as formulações; dados ficam em memória e não sobrevivem à reinicialização. Não há IDs de todos os eventos ou vínculo persistente com Caixa Preta; a última entrada da Caixa Preta pode não corresponder à tarefa atual e é descrita como não confirmada. Exceções e retornos sem `visual_result` não têm diagnóstico completo. Não foi implementado replanejamento/retomada automática.

## Propostas visuais — parcial

Parser existente mantém AST restrito; `Somente chamada de funcao simples e permitida` ocorre quando a expressão não é chamada a nome simples, inclusive atributos ou outras estruturas. Não se sabe qual foi a expressão real do caso. `run_task` permite no máximo uma repetição para erros reconhecidos de formato; erros de estrutura proibida, coordenadas e alvos inválidos param sem despachar. Em erro do parser dentro de `vision_eye`, a exceção transporta estágio, modelo, endpoint, esquema, comprimento e SHA-256 da proposta; trace já contém task_id no resultado. Não gravamos proposta original ou captura: não há ainda armazenamento protegido de dados sensíveis nem ID do snapshot. O texto de exceção legado permanece limitado em trace. Não foram implementadas etapas semânticas de triângulo ou verificação da figura nesta missão.

## Monitores — parcial

`obter_geometria_monitores` agora enumera retângulos reais fornecidos por MSS, incluindo origem negativa e múltiplos monitores; índice inexistente é rejeitado. `descrever_tela` não chama índice MSS de número/principal do Windows. Pedido de duas telas chama duas descrições independentes e informa hora e índices MSS; falha é reportada por tela. Pedidos numerados e acompanhamento informam que a correspondência com o Windows ainda é desconhecida, em vez de inventar uma posição. Ainda faltam identificação de dispositivo Windows↔MSS e validação de DPI em monitores reais; não se deve interpretar os índices MSS como rótulos Windows. Testes usam geometria e visão simuladas.

## Factualidade / intenção flexível — pendente

Não foi alterado o canal de respostas históricas, pesquisa de fontes, modelo, fallback ou tratamento de Dom Pedro I / Dom Pedro 54. Não há evidência nesta missão de que alucinações factuais estejam corrigidas. O pedido final sobre reconhecimento flexível terminou truncado após “abrir, restaur”; esse item não foi implementado. Não há base para declarar os casos históricos, status de inferência ou replanejamento resolvidos.

## Validação

`ast.parse` passou nos arquivos alterados. `test_v952_reliability.py`: 7 passaram em 1,05s. Regressão auditada + cenários novos: 198 testes e 46 subtestes passaram em 5,55s; zero falhas ou ignorados. Logs `V9_5_2_FOCUSED_TESTS.log`, `V9_5_2_REGRESSION_TESTS.log`; suíte completa não executada. Checkpoints em `development_logs/checkpoints/v952_20261111`. Nenhuma captura real, GUI, mouse, teclado, modelo ou serviço foi acionado; não se modificou banco. Uma verificação de processos não encontrou instância Python BRAINNET/pytest/inspector no momento consultado, sem garantia contra inicialização posterior. O teste simulado não comprova funcionamento físico.
