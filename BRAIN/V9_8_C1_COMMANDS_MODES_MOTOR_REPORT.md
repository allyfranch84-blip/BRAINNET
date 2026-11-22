# V9.8-C1 — Comandos, modos e diagnóstico motor

**Resultado: integração parcial.** Os comandos novos e o catálogo foram conectados ao handler real; a sequência motora completa até verificação factual ainda não existe. A instância ativa não foi reiniciada nem observada.

## Arquivos e contratos

- `command_catalog.py`: catálogo de apresentação por categoria, sintaxe/aliases, descrição, dependências, estado, uso manual e autorização. `/help`, `/ajuda` e `/?` usam o catálogo; verificações de módulos locais marcam certas dependências ausentes. Não consulta modelos ou rede ao mostrar ajuda.
- `BRAINNET.py`: `_manual_capability_command` acrescenta os comandos explícitos ao dispatcher existente. `/modo auto|fast|balanced|deep` usa `set_effort_mode` e afeta próximas tarefas; `/modo livre|padrao|status` altera perfil de estilo independente. LIVRE acrescenta instrução de resposta direta ao caminho conversacional existente e não troca pesos, autorizações ou verificações. `MODELO_ABLITERATE` existe como constante em `assistant_prompts.py`, mas não foi encontrado integrado ao perfil; não se alega modelo destreinado.
- `/modelo listar` consulta `/api/tags` no endpoint configurado; `/modelo usar <nome>` apenas aceita nome retornado e salva preferência para próximas inferências conversacionais. A seleção não comprova que o modelo esteja carregado ou suporte geração; outros clientes legados não foram migrados. Modelo e perfil são capturados por tarefa via ContextVar, evitando mudança no meio do caminho conversacional.
- `/visao agora` usa `vision.descrever_tela`; resultado é OBSERVATION_UNVERIFIED. `/uia scan` usa `capture_foreground_context` e `scan_uia_properties`; não despacha ações. Dependências ausentes retornam UNAVAILABLE. A chamada visual existente pode acionar modelo e é bloqueante; só ocorrerá por comando futuro do usuário, não foi executada nesta missão.
- GUI externa `MasterShell_(1).jsx`: mostra perfil e modelo configurados, marcando disponibilidade não verificada; atualiza a exibição após comandos de modo/modelo. Build passou, mas GUI real não foi observada.

## Tabela de comandos e evidências

| Categoria / comandos | Estado neste código | Dependências | Testes nesta missão |
|---|---|---|---|
| `/help`, `/ajuda`, `/?` | disponível; catálogo declarativo | handler e catálogo | `test_help_includes_catalog_and_missing_module` |
| `/modo auto/fast/balanced/deep` | disponível para próximas tarefas | arquivo de configuração; backend para inferir | `test_modes_independent_and_apply_next_inference` |
| `/modo livre/padrao/status` | experimental, estilo conversacional | configuração e caminho `_budgeted_conversation` | mesmo teste; não cobre clientes legados |
| `/modelo listar/usar` | experimental | Ollama `/api/tags`, modelo listado | `test_model_selects_only_installed`, `test_model_endpoint_unavailable_is_explicit` |
| `/visao agora`, `/uia scan` | experimental | captura, visão/modelo ou UIA | `test_manual_uia_and_vision_use_existing_methods`, mocks |
| `/escreva`, `/continue` | experimental; checkpoints e retomada limitados | modelo, orçamento, disco | regressão segura; detalhes em V9_8_T1_LONG_CHAT_REPORT.md |
| `/offline`, `/offline-ref` | experimental | libzim, ZIM; H-Mem para referências | testes K1.1 anteriores; não reexecutados nesta missão |
| `/pesquisa` e aliases | experimental, busca em segundo plano | DuckDuckGo/rede | seleção segura `test_v97r24_coverage.py` |
| `/code` e aliases | legado experimental; modo não garante execução nem modelo disponível | Coder/arquivo | não exercitado diretamente nesta missão |
| `/switch mode`, `/modo` | alternância legada distinta do esforço | estado do Kernel | `test_unknown_and_legacy_mode` |
| `/treino` e aliases | legado experimental; pode iniciar atividade | harvester | não acionado nesta missão |
| `/rem` e aliases | legado experimental; pode podar | REM | não acionado nesta missão |
| `/certo`, `/report`, `/esquecer` e aliases | legado com escrita/alteração de dados | P-DAG e caixa preta | não acionados nesta missão |
| `/copy`, `/logs web` e aliases | legado | clipboard ou P-DAG | não acionados nesta missão |
| linguagem natural `clique/pinte/desenhe...` | UI-TARS experimental | visão, autorização, executor | não houve ação física |

O catálogo é inventário declarativo associado ao dispatcher, não registro gerador do roteamento: pode divergir quando handlers mudarem. Verifica existência de alguns módulos, mas não confirma backend, modelo, UIA ou arquivo efetivamente disponíveis. Aliases não exaustivos em alguns ramos prefixados e comandos internos sem representação pública permanecem para auditoria futura.

## Motor e histórico

Não há registro suficiente nesta missão para atribuir `ACTION_NOT_CONFIRMED` do histórico antigo a uma etapa concreta. No código atual, “mova o mouse em qualquer direção” é reconhecido e retorna `CLARIFICATION_REQUIRED`, etapa `INTENT_RECOGNIZED`, pois não define direção nem distância; nenhum despacho. Uma proposta explícita de 30 pixels sem clicar retorna `AUTHORIZATION_REQUIRED`, também sem despacho. Isso não significa ação realizada.

A retomada autorizada da mesma tarefa não está integrada ao Chat; portanto `DISPATCHED`, `EXECUTION_FAILED`, `VERIFICATION_FAILED` e `SUCCEEDED` não foram implementados como resultados motores de ponta a ponta nem testados. Não se atribui falha de execução à ausência de aplicativo. O comando desconhecido retorna mensagem curta, sem anexar a lista completa. O `/ui` anunciado em versões antigas não tem handler slash encontrado e não é anunciado como disponível; `/pesquisa` possui ramo legado posterior que é precedido pela busca normal e pode estar inacessível nesse caminho.

## Validação

`python -m unittest test_v98c1_commands -v`: 7 aprovados; testes de handler real com configuração temporária e mocks para Ollama, UIA, visão e atuador. Cobrem help, dependência ausente, DEEP enviado com limite 800, perfil independente, modelo listado e aplicado em payload simulado, falha de endpoint, comandos manuais, motor não despachado, comando desconhecido e modo legado. Não comprovam operação GUI real, captura de tela, modelo instalado, qualidade do perfil ou motor físico.

`python regression_runner.py --suite safe-full`: 73 aprovados, 0 falhas/erros/ignorados; JUnit `development_logs/REGRESSION_20261122_174503_365652.xml`. Após a última alteração de texto, os 7 testes focados foram repetidos e passaram. `npm run build` no projeto externo: aprovado, 1935 módulos, 7,36 s. Não houve teste de comunicação PyWebView ou janela real. Nenhum modelo ou serviço foi iniciado, e nenhum mouse/teclado foi atuado.

**Critério integral não atingido:** o catálogo não é fonte única dos handlers, testes não cobrem todos os aliases e o fluxo motor autorizado/verificado permanece incompleto. A integração em produção requer reinício supervisionado posteriormente e validação separada, sem presumir que a instância ativa esteja atualizada.
