# V9.8-A2.7 — Integração motora

**Estado: INCOMPLETO / NOT_READY.** Nenhum movimento, clique ou digitação real foi realizado. O laboratório existente HWND 8389610 permanecia visível na última leitura; ele executa a versão anterior em memória e não possui a nova área inserida no código. Não foi reaberto.

## Alterações

- `capability_lab.py`: adicionada à versão WinForms em disco uma área não interativa `lab_motor_area`, com rótulo “ÁREA DE TESTE MOTOR — SEM CLIQUES”, abaixo dos controles e do registro; seus limites físicos e acessibilidade real ainda não foram verificados. Adicionada função pura `bounded_linear_points`, que gera pontos determinísticos e rejeita trajetos fora do retângulo fornecido. Essa função não é perfil acionado pelo Effector.
- `parser_contract.py`: a formulação solicitada sem a palavra “lentamente” passa a gerar proposta; permanece sem autorização. Não é compreensão geral de linguagem.
- `test_v98a2_7_motor_preparation.py`: testes sintéticos de geometria, negação e proposta. Nenhuma integração com atuação real.

## Testes

`python -m unittest test_v98a2_7_motor_preparation test_v98a2_1_safe_trajectory -v`: 12 aprovados, 0 falhas. Sintaxe validada. Esses testes não comprovam área real, DPI do executor, Chat→executor nem operação física.

## Bloqueios remanescentes

1. A área nova ainda não existe na janela em execução; é necessária abertura supervisionada separadamente autorizada e confirmação de seu HWND e retângulo físico via UIA. Não há coordenadas seguras para solicitar posicionamento do cursor.
2. `Effector.mouse_move` permanece com Bézier e jitter; não usa `bounded_linear_points`. Coordenadas e DPI da thread do executor não foram comprovados. Não existe perfil determinístico conectado ao atuador.
3. `BrainnetBridge._send_command_impl` reconhece o movimento como proposta e retorna `AUTHORIZATION_REQUIRED`; não despacha `verify_relative_move`. O fluxo não preserva ainda autorização explícita específica para a prova do Chat até o executor. A autorização genérica de comando não comprova consentimento para esta ação. Conectar a execução sem um contrato explícito de autorização e revalidação enfraqueceria o bloqueio existente, portanto não foi feito.
4. A verificação factual existente não foi integrada ao Chat. Não foi demonstrado o trajeto completo com simuladores nem TaskContext e cancelamento. O critério principal da missão não foi cumprido.

## Próxima prova

Primeiro integrar e testar autorização explícita específica, revalidação de HWND/área/DPI imediatamente antes da execução, perfil linear com cancelamento sob exclusividade do atuador e verificação independente. Depois, abrir a versão atualizada somente sob autorização, identificar área e solicitar posicionamento manual. Fazer nova leitura, calcular +30 e pedir autorização específica separada para uma única execução. Não se deve executar a função isolada para contornar o Chat.
