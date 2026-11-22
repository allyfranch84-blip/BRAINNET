# V9.8-A2.2 — Validação do laboratório atualizado

**Estado: NOT_READY.** Uma única tentativa de iniciar a instância atualizada foi realizada. O comando retornou PID 14432, mas a consulta posterior não encontrou esse processo e a enumeração de janelas encontrou apenas a instância anterior (PID 5244, HWND 1573244). A saída de erro do novo processo não foi capturada; a causa do encerramento ou da indisponibilidade não está comprovada. A consulta CIM foi negada pelo ambiente. Não foi iniciada uma segunda tentativa.

A instância anterior permanece identificável; nenhum processo foi encerrado por esta tarefa. `import clr` funcionou em verificação separada, o que não comprova que a janela WinForms iniciou corretamente. Não é possível registrar HWND, controles UIA, região segura ou DPI da nova instância sem observá-la. Não se pode confirmar Name, AutomationId ou padrões de TESTE A/B.

Leitura de observação subsequente, referente à instância antiga e não à nova: cursor `(596, 234)` no instante Unix 1794510901.990047; monitor DISPLAY1 `(0, 0, 1920, 1080)`, área útil `(0, 0, 1920, 1048)`; sessão 1, desktop Default. A janela antiga tinha retângulo `(422, 223, 782, 534)`, HWND 1573244. O observador e a janela antiga relataram DPI awareness 0; `GetDpiForWindow` informou 96, sujeito a virtualização. Uma conversão pontual retornou valores iguais, mas não comprova equivalência física do observador e do atuador. A posição é passageira e não deve ser usada para atuação.

Nenhuma região sem controles foi comprovada; portanto não há ponto para o operador posicionar o cursor e não há proposta de movimento pronta. O método proposto de verificação, após revalidação e autorização separada, é comparar uma nova leitura independente `GetCursorPos` antes e depois do movimento com destino exato `x + 30, y`, sem tratar a mera aceitação do executor como prova.

Não houve movimento, clique ou digitação; não foi executado o launcher, nem reiniciados serviços. O executor não foi acionado. Para tentar novamente é necessária autorização para outra instância, desta vez com captura de erro e identificação explícita da janela, preservando a instância anterior.
