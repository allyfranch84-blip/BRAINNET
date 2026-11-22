# V9.8-T1 — Chat extenso

**Estado: implementação parcial, não aceita como geração longa completa em produção.** Há geração segmentada inicial e checkpoints; não foram comprovados coerência de livro, limites reais dos modelos, streaming por token ou retomada integral após qualquer interrupção.

## Auditoria anterior

`BrainnetBridge.send_command` cria SharedTaskBudget e chama `_send_command_impl`; caminho conversacional `_budgeted_conversation` usa Ollama HTTP com limites FAST 200 tokens/2048 contexto, BALANCED 450/4096, DEEP 800/8192, prazos 15/30/60 s; AUTO seleciona um deles. Esses são limites solicitados, não confirmação da capacidade do modelo. Chat armazena até 120 mensagens no histórico Python, em memória; React mantém mensagens em estado e renderiza janela de histórico. Não foi localizado handler `/escreva` ativo no Kernel, embora exista `long_workflows.BookDraft` com capítulos serializáveis. `LongContextEngine` contém resumo/SQLite separado, sem ligação efetiva comprovada a esta geração. O adaptador oferece streaming, mas o caminho conversacional usa resposta completa; a GUI não fazia streaming textual. Não há medição real indicando em qual camada ocorreu eventual truncamento relatado.

## Alterações

- `inference_backend.py`: `InferenceResult.finish_reason` opcional expõe a causa de conclusão informada pelo backend sem mudar parâmetros de clientes antigos.
- `long_workflows.py`: `BookDraft.generate_sections` reutiliza capítulos, gera sequencialmente, inclui até 2400 caracteres anteriores como contexto literal, salva checkpoint e bloqueia repetição textual exata. Conteúdo com motivo de parada ausente ou limite é preservado e marcado `PARTIAL_UNCONFIRMED`; não é refeito automaticamente. Não há prova de continuidade semântica ou deduplicação aproximada.
- `BRAINNET.py`: `/escreva <tema>` e formas explícitas “escreva um texto longo sobre ...” usam três seções, `_budgeted_conversation` e seus limites por chamada/tarefa. Salva JSON por ID em `BRAIN/long_drafts` após seção e em falha. Retorna marca explícita de resultado incompleto; se backend informar `length`, a resposta curta comum também informa interrupção. `/continue <id>` retoma capítulos ainda vazios após erro/cancelamento, preservando ID do documento; a nova chamada cria novo task_id e orçamento, não retoma o mesmo SharedTaskBudget. Se texto parcial existir na seção interrompida, o sistema o preserva e não prossegue automaticamente. Não há controle de concorrência para duas continuações do mesmo documento; evitar uso simultâneo.
- Master Shell externo `src/components/MasterShell_(1).jsx`: escuta `aios:long_section`, atualiza uma mensagem por ID e índice, evita duplicar eventos no estado atual, conclui com a resposta do Kernel e oferece continuar após erro/cancelamento. Os eventos são por seção, não por token. Mensagens locais não são persistidas após reinício/reconexão; não há recuperação automática de checkpoints pela GUI. Cancelamento pelo botão existente pode descartar a resposta final na UI mesmo com checkpoint em disco.

## Validação

`python -m unittest test_v98t1_long_chat -v`: 7 aprovados; cenários sintéticos de três seções curtas, contexto anterior, igualdade exata, preservação de parcial, cancelamento entre seções, motivo length, handler real com transporte substituído e retomada com novo orçamento. Não há demonstração de extensão de livro, geração real, coerência, memória factual ou interrupção durante streaming.

`python regression_runner.py --suite safe-full`: 73 aprovados, zero falhas/erros/ignorados; JUnit `development_logs/REGRESSION_20261112_204211_680423.xml`. `npm run build` no projeto externo: concluído, 1935 módulos, 7,32 s, bundle JS principal 372,99 kB (118,26 kB gzip). Build não comprova interface executada ou comunicação real; não houve teste automatizado de eventos React nem benchmark de render/memória. Não foram iniciados modelos, serviços ou atuadores.

## Pendências para aceite

- Retomar trecho truncado de forma segura sem perda/repetição e expor recuperação do checkpoint após reinício.
- Preservar identidade e orçamento da mesma tarefa ou definir e testar formalmente tarefa de continuação; sincronizar concorrência/cancelamento.
- Recuperar memória e fontes com proveniência; separar fatos verificados, hipóteses, síntese e histórico literal. Não implementar como fatos as respostas geradas.
- Implementar streaming incremental verificável do adaptador, reconexão idempotente, cancelamento durante transporte bloqueante e limite de tokens/contexto realmente informado pelo modelo.
- Testes GUI↔Kernel simulados, textos extensos, performance, fatos e limites reais; observar interface real antes de declarar produção. Controles de autorização não foram alterados.
