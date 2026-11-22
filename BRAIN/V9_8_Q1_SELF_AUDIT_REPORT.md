# V9.8-Q1 — Autoauditoria e regressão

**Resultado: integração parcial.** A inspeção executou inventário estático e a regressão segura a partir de `SelfInspector.audit_read_only`; a análise motora e registro persistente foram produzidos. Não comprova autoaperfeiçoamento nem cobre todas as interfaces do Kernel.

## Implementação e evidências

- `self_inspector.py`: `audit_read_only` usa `code_mapper.index_symbols` para classes, funções, imports e chamadas; calcula SHA-256; tenta Git e, quando indisponível, compara manifesto explícito, sem alterá-lo. Seleciona referências do mapa do executor e pode executar sua seleção segura completa. Gera JSON detalhado e registra evento no journal existente `development_logs/missions.jsonl`. Não chama `check_for_changes`, `_run_tests` ou rollback.
- `diagnose_audited_timeout` executa somente um teste explicitamente permitido em subprocesso próprio, com faulthandler, prazo de 12 segundos e log. O subprocesso é terminado por `subprocess.run` quando excede o prazo; serviços não são alvo.
- `test_v98q1_self_audit.py`: três testes aprovados de leitura, preservação do arquivo, journal, bloqueio de caminho externo e recusa de testes não auditados.
- Auditoria real: `development_logs/SELF_AUDIT_eef3c21b38c947a6aca53c82a342e5fa.json`; identificou `self_inspector.py` alterado em relação a `development_logs/V9_8_Q1_HASH_MANIFEST.json`. Manifesto foi criado nesta missão, não é baseline histórica. Git indisponível no diretório auditado. 73 testes seguros passaram, 0 falharam, 0 ignorados; JUnit `development_logs/REGRESSION_20261112_182521_609492.xml`.
- Uso explícito: `SelfInspector(brain_dir).audit_read_only([...], run_tests=True, hash_baseline=...)`; recuperação de eventos do journal: `development_logs.mission_log.read_events(directory, 'mission')`. Não invoca modelo nem altera código automaticamente.

## Mapa de dependências e capacidades

`BrainnetBridge.send_command` cria `SharedTaskBudget` → `_send_command_impl` analisa `parse_supervised_mouse_move` → `begin_pending_motor` armazena operação → `WAITING_AUTHORIZATION`. `execution_authority.command_authority` cria escopo genérico; não representa aprovação específica. `transition_motor_simulation` e `bind_motor_observation` operam no orçamento; não foram conectados a despacho pelo Chat. `capability_lab.verify_relative_move` usa ActuatorBridge, mas não é caminho real de retomada do Chat. Esta descrição decorre de inspeção dos arquivos, não de execução física. `engineering_agent.assess_change` é gate de revisão; `code_mapper.index_symbols` é AST estático. Não se infere inatividade de módulos por ausência de imports estáticos; carregamento dinâmico permanece a investigar.

| Comportamento | Responsável / evidência | Classificação | Lacuna / prioridade |
|---|---|---|---|
| Proposta e identidade | BRAINNET.py; test_v98a2_8_motor_path.py | INTEGRADA EM SIMULAÇÃO | Continuação não demonstrada; P0 |
| Estado pendente e cancelamento | SharedTaskBudget; test_v98a2_9_pending.py | INTEGRADA EM SIMULAÇÃO | expiração e limpeza automática ausentes; P0 |
| Transições sob lock | transition_motor_simulation; test_v98a2_9_1_atomic.py | TESTADA ISOLADAMENTE | não é concessão de autorização real; P0 |
| Evento confiável de aprovação | interface e autoridade | DECLARADA / NÃO COMPROVADA | nenhum canal de consentimento específico demonstrado; P0 |
| Retomada e despacho | handler real | DECLARADA / NÃO COMPROVADA | teste real com transporte simulado e um despacho ausente; P0 |
| Trajeto e verificador | capability_lab e Effector | TESTADA ISOLADAMENTE | não comprovados via Chat; DPI e perfil determinístico ausentes; P0 |
| Resultado físico | sistema real | NÃO COMPROVADA | sem prova real ou reprodutibilidade; P1 |

## Travamento e hipóteses

`test_v98a_capability_lab.py::test_move_requires_authorization_and_independent_observation` terminou TIMEOUT. A pilha capturada em `development_logs/SELF_AUDIT_TIMEOUT_8a2c5261d83a428a853de6d8ff4f75aa.log` mostra `socket.accept` → `_fallback_socketpair` → `asyncio` Proactor → `asyncio.run` na linha 22, antes da coroutine; não há evidência de impasse no atuador. Hipótese principal: restrição ou comportamento de socketpair neste ambiente; não é causa comprovada. Teste discriminante: executar diagnóstico de criação de loop em ambiente controlado que permita sockets locais, sem modelos e sem atuadores. Correção sugerida somente após confirmação: adaptar fixture/event loop ou executar testes isolados num ambiente compatível. Alterar o loop pode afetar outros testes assíncronos; não enfraquecer autorização para corrigi-los.

## Limitações e pendências

O journal é infraestrutura persistente de desenvolvimento consultável por leitura, mas não foi integrado a H-Mem/FHRR nem há recuperação semântica de experiências. O inspetor não foi conectado a um comando ativo do Kernel/GUI; foi chamado diretamente por API. O método gera inventário e revisão específica com heurísticas, não investigação causal geral, diffs função a função, proposta automática de patch ou diagnóstico genérico de todas as regressões. A seleção efetivamente executada é a segura completa, não apenas os testes potencialmente afetados. O manifesto cobre apenas módulos explicitamente informados e não detecta remoções ou renomeações fora desse escopo. O mecanismo legado `check_for_changes` continua capaz de chamar pytest completo e rollback; não foi executado, nem permanentemente desativado. As seis falhas visuais históricas continuam sem verificação atual. A base v2 não foi atualizada.

Critério completo não atendido: ainda falta integração do novo método ao mecanismo ativo do Kernel, conexão à memória de experiências, análise automatizada geral de hipóteses e execução de ponta a ponta da retomada motora. Nenhuma atuação física, autoedição ou reinício de serviço foi realizado.
