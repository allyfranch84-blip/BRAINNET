# V9.8-A2.9.1 — Transições de operações pendentes

**Resultado: INCOMPLETO.** Não foi implementada aprovação confiável na interface, nem retomada pelo handler real, nem despacho simulado de ponta a ponta. Não existe autorização motora física nesta alteração.

## Alterações

`adaptive_resource_controller.py`: `bind_motor_observation` associa geometria e identidade somente a uma proposta pendente; `expire_pending_motor` marca como expirada sob o lock quando consultado após o prazo; `cancel_pending_motor` também cancela antes do consumo de uma autorização simulada. `transition_motor_simulation` implementa, exclusivamente em simulação, transições WAITING_AUTHORIZATION→AUTHORIZED→EXECUTING→VERIFYING→SUCCEEDED/FAILED/INCONCLUSIVE, com conferência de geometria na autorização e no início. Estados terminais não admitem essas transições. Os nomes dos estados de simulação não constituem autorização real.

`test_v98a2_9_1_atomic.py`: testes de estados simulados, prazo expirado e disputa de cancelamento com autorização. A disputa permite que autorização ocorra primeiro e seja imediatamente cancelada; caso cancelada, não pode executar. O código não efetua despacho.

## Validação

`python -m pytest -q --tb=short -p no:cacheprovider test_v98a2_9_1_atomic.py test_v98a2_9_pending.py test_v98a2_8_motor_path.py test_v97r22_production.py`: 11 aprovados. Testes usam o handler real para criar proposta; transições são chamadas diretamente no orçamento e NÃO demonstram retomada real do Chat ou despacho simulado. Sem ações físicas.

## Pendências

Não há evento de aprovação com identidade confiável vindo da GUI, credencial limitada e de uso único integrada a `execution_authority`, consumo atômico de autorização real, ligação ao handler de retomada e atuador simulado, limpeza periódica ou arquivamento de propostas expiradas. A expiração é avaliada apenas quando as funções relevantes são chamadas. A transição de cancelamento entre token genérico e sinal de espera continua precisando de revisão. Não foram comprovados rejeição de token de outra tarefa, reinício, revalidação ao despacho ou exatamente um despacho. Não ativar execução real com base nestas estruturas.

Não foram iniciados processos, abertas janelas ou alterado atuador Bézier.
