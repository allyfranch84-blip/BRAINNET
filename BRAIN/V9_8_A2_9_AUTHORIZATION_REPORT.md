# V9.8-A2.9 — Autorização e tarefa pendente

**Estado: INCOMPLETO.** O critério de transição por aprovação explícita no Chat até operação autorizada não foi alcançado. Não foram realizadas ações físicas.

## Alterações

- `adaptive_resource_controller.py`: `SharedTaskBudget.begin_pending_motor` registra operação única e seus dx/dy, prazo monotônico da tarefa, estado pendente e campos de HWND/PID/região desconhecidos; `cancel_pending_motor` cancela uma vez sob o lock da tarefa. Não cria autorização.
- `BRAINNET.py`: o handler real registra a proposta na tarefa e mantém o orçamento no registro de tarefas ativas ao retornar `AUTHORIZATION_REQUIRED`; emite fase `WAITING_AUTHORIZATION`. A espera utiliza sinal de cancelamento próprio porque o token genérico `command_authority` é revogado ao fim da chamada; não transfere nem concede autorização motora. Sem registro de tarefas disponível, o resultado informa a indisponibilidade.
- `test_v98a2_9_pending.py`: testes simulados do handler real para preservação de task_id/operação e cancelamento.

## Testes

`python -m pytest -q --tb=short -p no:cacheprovider test_v98a2_9_pending.py test_v98a2_8_motor_path.py test_v97r22_production.py`: 8 aprovados, 0 falhas. Exercitam proposta, espera e cancelamento em memória e regressão conversacional; não comprovam aprovação nem execução.

## Pendências decisivas

Não existe ainda canal de aprovação explícita no Master Shell, contrato de permissão vinculada de uso único no mecanismo existente, validação atômica de aprovação, revalidação de janela/região ou retomada da mesma tarefa até o executor. Portanto não há aprovação válida, execução simulada de ponta a ponta, teste de aprovação repetida/expirada/concorrente, teste de alteração de contexto nem retorno final ao Chat. O prazo está armazenado, mas não existe expiração automática ou limpeza das tarefas pendentes; elas podem permanecer no registro até gerenciamento futuro. `cancel_pending_motor` ainda não está exposto ao usuário nem remove o registro. A troca de sinal de cancelamento para preservar a espera também ainda exige revisão de corridas entre cancelamento e transição; não usar para atuação. Não apresentar estas estruturas como prontas para execução real.

Nenhum atuador foi modificado, processo iniciado, janela aberta ou movimento realizado.
