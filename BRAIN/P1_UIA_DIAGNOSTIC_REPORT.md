# P1 — diagnóstico do /uia scan (somente leitura)

## Caminho atual

No Master Shell externo, `src/App.tsx` importa `src/components/MasterShell_(1).jsx`. O componente chama `kernel.call('send_command', text)`; `useKernel` encaminha a `window.pywebview.api` quando disponível e, caso contrário, usa uma API mock. A resposta é exibida a partir de `res.reply`; `res.controls` não é renderizado no Chat.

No Kernel, `BrainnetBridge.send_command` chama `_send_command_impl`, que consulta `_manual_capability_command`. Para `/uia scan`, este chama `capture_foreground_context()` **uma vez**, extrai `hwnd`, chama `eye.scan_uia_properties(hwnd, max_controls=100)` e devolve contagem, lista e `status=OBSERVED`. Não utiliza `BrainnetKernel.observe_ui_scene`, que faz revalidação distinta de janela, PID e início do processo. A rota `/uia scan` não informa ao usuário o HWND/PID nem revalida foco após a leitura.

`capture_foreground_context()` usa `GetForegroundWindow` e `GetWindowThreadProcessId`. Ao digitar na MasterShell, o foco **pode** passar para PyWebView; assim o comando pode inspecionar a própria BRAINNET. Essa hipótese não foi comprovada na GUI real nesta sessão. A seleção de um HWND anterior não deve ser tratada como alvo autorizado: uma solução futura precisa de seleção explícita, confirmação da identidade e revalidação antes/depois da leitura.

`scan_uia_properties` retorna `[]` tanto quando a biblioteca está indisponível quanto quando o handle/root não produz elementos. O handler atual marca `OBSERVED` também para `[]`; isso não é evidência de percepção. Falhas de campos individuais viram `None`. Um resultado com controles não garante visibilidade do conteúdo real, nem leitura por VLM.

## Observações reais separadas

Na consulta Win32 somente leitura, a janela em foco foi HWND `198274`, PID `8500`; a verificação fora da sessão isolada identificou `thorium.exe`. Três tempos das chamadas Win32 foram **0,051; 0,012; 0,008 ms**. São tempos de identificação da janela, não de UIA. Na sessão isolada, `psutil` retornou `NoSuchProcess` para o mesmo PID; portanto a sessão de diagnóstico e seus privilégios afetam a capacidade de associar janela e processo.

Nenhuma janela Notepad ou `BRAINNET — Laboratório seguro` foi encontrada na enumeração limitada. Não foi realizada varredura UIA de controles reais, não há contagem real nem latência real de UIA e não se observou a GUI operacional. A consulta ao HWND zero pelo diagnóstico retornou `TARGET_INVALID`, biblioteca UIA disponível e provedor `UNKNOWN`; não representa observação de controles. Python 3.12.10, Windows 11 build 26100 e `uiautomation` 2.0.29 estavam disponíveis na sessão de diagnóstico. Foram vistos processos Ollama; a busca heurística não identificou Kernel/Vite, o que não prova sua ausência em outras sessões. Nenhum processo foi encerrado ou iniciado.

## Testes e limites

`python -m pytest -q --tb=short -p no:cacheprovider test_p1_uia_diagnostic.py test_uia_property_read.py test_ui_scene_graph.py test_v98c1_commands.py` com plugins automáticos e bytecode desativados: **34 aprovados, 3 subtestes aprovados**. Os testes usam mocks; caracterizam explicitamente a falsa classificação de lista vazia e não demonstram UIA real.

`python regression_runner.py --suite safe-full`: **72 aprovados, 1 falha**. `test_inference_backend.TestSupervisorAddendum::test_absent_gpu_counter_is_unknown` depende de `llama_cpp_independent/b12255/benchmark_003c1.py`, ausente na cópia Git; falha antes da verificação de GPU, já reproduzida e documentada no PR #4. Os seis testes visuais históricos não fazem parte dessa seleção.

## Diagnóstico manual seguro posterior

Sem iniciar aplicações por este script, o usuário pode abrir manualmente uma janela de teste Notepad sem dados privados e obter HWND/PID em seu PowerShell interativo:

```powershell
Get-Process -Name notepad | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object Id, MainWindowHandle
Set-Location 'A:\BRAINNET\BRAINNET\BRAIN'
python .\p1_uia_diagnostic.py --hwnd <HWND> --pid <PID>
```

O diagnóstico exige explicitamente ambos os identificadores, valida janela controlada e identidade de processo antes e depois, não muda foco, não captura imagem e não atua. Por padrão não exibe títulos nem nomes de controles; `--include-control-names` só deve ser usado em uma janela sem conteúdo sensível. `control_count` inclui elementos UIA, possivelmente a raiz. A API atual não permite distinguir com segurança lista vazia de provedor sem evidência, por isso o estado é `EMPTY_OR_PROVIDER_UNAVAILABLE`. Algumas chamadas de provedores podem bloquear; o diagnóstico não oferece timeout interno garantido. Execute-o somente em janela de teste e em processo supervisionado.

## Patch mínimo proposto — não aplicado ao Kernel

Após evidência local de UIA real, separar no contrato do scanner `PROVIDER_UNAVAILABLE`, `EMPTY` e `OBSERVED` com evidência; transmitir ao Chat HWND/PID, resumo limitado e tempo, sem persistir conteúdo privado; selecionar explicitamente janela externa e revalidar PID/criação/contexto. Preservar autorização e nunca iniciar VLM por essa leitura. A implementação proposta precisa de revisão, testes e aprovação antes de ser instalada. Não alterar a instância ativa nesta missão.
