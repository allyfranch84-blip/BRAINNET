# BRAINNET — Linha de base de regressão

## Entrega

`regression_runner.py` executa apenas seleções explícitas em `GROUPS`; não usa descoberta geral de testes. `regression_baseline_v2.json` contém versão, seleção e resultados JUnit efetivamente medidos; v1 foi preservada. Comparação sinaliza falha ou erro novo, alteração de assinatura de falha, teste anteriormente aprovado agora ignorado e caso ausente quando a seleção coincide com a baseline. Falhas conhecidas continuam no resumo. Não sobrescreve a baseline existente automaticamente. Não foi possível verificar rastreamento Git da baseline nesta pasta; versionamento aqui significa esquema/arquivo versionado, não confirmação de commit.

Comandos, em `A:\BRAINNET\BRAIN`:

- Rápido: `python regression_runner.py --suite fast`
- Integração segura: `python regression_runner.py --suite integration`
- Toda a seleção segura auditada: `python regression_runner.py --suite safe-full`
- Arquivo modificado: `python regression_runner.py --changed BRAIN\capability_lab.py` (repetir `--changed` conforme necessário). Arquivos desconhecidos acionam a seleção segura inteira, não descoberta arbitrária.
- GUI oficial: `python regression_runner.py --suite gui`; alterações devem ser passadas por `--changed` com caminho contendo `INTERFACE DE USUARIO`. Executa build e, quando definidos em package.json, scripts test e typecheck. Atualmente não há script `test`; isso é informado como `NOT_CONFIGURED`, não considerado teste aprovado. Não executa GUI real.
- E2E supervisionado: `python regression_runner.py --suite e2e-supervised` recusa execução por ausência de seleção auditada; testes de atuação real não estão na allowlist.

Gerados por execução: JUnit XML, log completo e resumo JSON em `development_logs/REGRESSION_<timestamp>*`. A execução segura final produziu 73 aprovados, 0 falhas, 0 erros e 0 ignorados; XML `development_logs/REGRESSION_20261112_181741_220162.xml`, resumo `development_logs/REGRESSION_V2_VERIFIED_SUMMARY.json`. A baseline v2 foi criada em execução separada e a comparação subsequente terminou com código 0. Dois testes do próprio executor verificam identificação sintética de falha nova e recusa de E2E.

A seleção contém testes de autorização e propostas, TaskContext, memória situacional, roteamento/intenção, inferência simulada e controle motor simulado. Não prova operação física, nem equivale à suíte total ou aos 233 testes do relatório histórico anterior.

## Seis falhas visuais históricas

Fonte `V9_7_E1_R1_REPORT.md`, que as comparou com checkpoint limitado. Os seis IDs são registrados em todo resumo, sem xfail nem alteração de permissões:

1. `test_ui_tars_protocol.py::test_bridge_click_moves_then_clicks_under_lock` — autorização ausente.
2. `test_ui_tars_protocol.py::test_vision_sends_image_schema_and_unloads_model` — política keep_alive diferente.
3. `test_ui_tars_protocol.py::test_kernel_bridge_passes_direct_instruction_without_browser_url` — fixture sem atributo.
4. `test_ui_tars_protocol.py::test_failed_ncd_stops_before_next_action` — autorização ausente.
5. `test_ui_tars_protocol.py::test_finished_without_verified_action_never_claims_success` — autorização ausente.
6. `test_ui_tars_protocol.py::test_focus_change_blocks_input_before_actuation` — autorização ausente.

São referências históricas, não falhas atuais comprovadas. Uma seleção que incluía `test_v98a_capability_lab.py::test_move_requires_authorization_and_independent_observation` ficou bloqueada neste ambiente; a execução foi interrompida e não gerou resultado JUnit final. Por isso os seis testes visuais e esse teste assíncrono não são executados automaticamente até investigação adicional. A baseline v2 não monitora suas mudanças; não afirmar que foram corrigidos ou que passaram.

## Limitações

A seleção e o mapa de dependências são manuais e incompletos; informar arquivos alterados é responsabilidade do chamador, não há integração automática de CI/Git nem proteção contra alterações de código nos testes selecionados. Arquivos fora da allowlist nunca são executados automaticamente. Não existem testes GUI específicos no package.json; build/GUI não foram executados nesta missão porque nenhum arquivo GUI foi alterado. `--suite gui` não demonstra conexão com Kernel ou interface em execução. A proteção baseia-se em revisão estática da lista e mocks, não em isolamento de hardware no sistema operacional. Prazo dos testes é 300 s; um bloqueio interrompido pode não produzir JUnit e é informado como erro de execução. A baseline compara somente casos efetivamente selecionados. Não foi demonstrada cobertura para toda alteração futura ou suíte completa.
