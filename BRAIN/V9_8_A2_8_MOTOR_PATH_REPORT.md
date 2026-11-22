# V9.8-A2.8 — Caminho motor

**Resultado: INCOMPLETO.** O critério Chat→autorização específica→atuador determinístico→verificador não foi atingido. Nenhuma atuação real foi executada.

## Alterações

- `BRAINNET.py`: a proposta gerada por `_send_command_impl`, dentro do handler real `send_command`, inclui o `task_id` do `SharedTaskBudget` corrente. Sem contexto, o ID é `None`; nenhuma autorização é criada pela proposta.
- `test_v98a2_8_motor_path.py`: teste do handler real com dependências controladas, comprovando correspondência entre ID da proposta e ID do orçamento, estado `AUTHORIZATION_REQUIRED` e ausência de despacho ao atuador.

## Contrato e ponto exato de interrupção

O decorador `command_authority` cria automaticamente um `threading.Event` genérico para o comando e o invalida ao terminar. Ele não vincula permissão a task_id, operação, janela, retângulo, expiração e uso único. `_send_command_impl` retorna imediatamente `AUTHORIZATION_REQUIRED` para a proposta; nenhuma interface de aprovação específica e nenhuma continuação da mesma tarefa foram conectadas. A transformação do evento genérico em aprovação específica enfraqueceria a segurança e não foi realizada.

`ActuatorBridge` possui exclusividade e `Effector.mouse_move` usa Bézier com jitter; não foi implementado nem conectado perfil determinístico. `bounded_linear_points` preexistente é somente cálculo geométrico. Não há comprovação de equivalência das coordenadas físicas do observador e da thread do executor. A função `verify_relative_move` permanece fora do fluxo de Chat e não foi usada como atalho. Consequentemente, ainda faltam a aprovação vinculada e de uso único no mecanismo existente, transferência segura do contexto para a continuação, perfil linear com revalidação e cancelamento, inspeção de DPI e integração do verificador.

## Testes

`python -m pytest -q --tb=short -p no:cacheprovider test_v98a2_8_motor_path.py`: 1 aprovado. Teste demonstra apenas produção segura da proposta, não um movimento simulado de ponta a ponta. Uma tentativa da seleção maior não retornou resultado final registrado nesta execução e não é contabilizada como aprovação. Os requisitos sobre autorização válida, executor e verificador integrado ainda não foram testados e continuam pendentes.

Sem mouse, teclado, nova janela ou reinício de serviços. Não se solicitou nem se inferiu autorização para movimento.
