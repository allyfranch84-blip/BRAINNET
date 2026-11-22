# V9.8-A2.5 — Ciclo de vida do Capability Lab

**Resultado: janela e controles observados durante execução supervisionada.** Um observador independente em thread foi iniciado antes da única instância autorizada. Processo iniciado PID 13676, HWND 8389610, janela visível; retângulo observado `(234, 234, 640, 563)`. Não se deve reutilizar retângulos antigos sem reobservação.

O código utiliza `Application.Run(form)`. A busca na implementação não encontrou `Close`, `Dispose`, `Application.Exit` ou saída explícita antes desse loop. A instrumentação opcional via variável `BRAINNET_LAB_LIFECYCLE_LOG` registra Load, Shown, FormClosing, FormClosed, entrada/retorno de Application.Run e batimentos de um timer do loop. stdout e stderr foram capturados separadamente.

Eventos observados: APPLICATION_RUN_BEGIN 17:23:15.113, LOAD 17:23:15.150, SHOWN 17:23:15.175 e batimentos MESSAGE_LOOP_TICK entre 17:23:16 e 17:23:26. Na primeira verificação `Popen.poll()` retornou None, sem código de saída; consulta posterior confirmou HWND existente e visível. Os batimentos mostram processamento de mensagens durante o intervalo observado. stdout e stderr vazios no instante da verificação; não foi observada exceção ou encerramento voluntário.

UIA somente de leitura, 17:23:15.434:

| Controle | Name | AutomationId | ControlType | BoundingRectangle |
|---|---|---|---|---|
| A | TESTE A | lab_button_a | ButtonControl | (262, 285, 412, 330) |
| B | TESTE B | lab_button_b | ButtonControl | (442, 285, 592, 330) |

Ambos foram identificados como habilitados, visíveis e com padrão Invoke disponível. Esses dados não autorizam execução.

O supervisor anterior A2.4 usava `Popen` e terminava imediatamente após observação; seu código não chamava terminate ou kill. A janela desapareceu depois que esse processo supervisor terminou, enquanto a nova permaneceu enquanto o supervisor continuou ativo: isso sugere uma associação ao ciclo de vida do ambiente iniciador, mas não comprova que ele encerrou diretamente o filho ou qual mecanismo do ambiente atuou. O código de saída anterior não foi capturado; causa precisa continua desconhecida.

O supervisor desta tentativa continua aguardando a janela, sem encerrá-la. Se a sessão de execução ou o ambiente que hospeda o processo for encerrado, a permanência posterior não foi demonstrada. Nenhuma atuação física, fechamento da instância anterior, reinício de serviço ou nova tentativa foi realizada. A segurança de uma região para movimento e a equivalência DPI do executor permanecem não verificadas.

Arquivos: `capability_lab.py` (instrumentação opcional), `development_logs/V9_8_A2_5_supervisor.py`, `V9_8_A2_5_observer.log`, `V9_8_A2_5_lifecycle.log`, `V9_8_A2_5_stdout.log` e `V9_8_A2_5_stderr.log`.
