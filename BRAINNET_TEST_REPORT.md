# Resultados · 25/11/2026

| Verificação | Classe | Evidência |
|---|---|---|
| Base P47/48/49/51 e supervisor anterior | PASS_INTEGRATION | 56 testes em 2,50 s. Inclui persistência SQLite temporária, telemetria e contratos simulados. |
| Build React oficial | PASS_REAL | Vite 7.3.7, 2.201 módulos, 11,12 s, saída temporária. JS principal de 529,24 kB, aviso de chunk grande. |
| Regressão auditada | PASS_INTEGRATION | `VENV/Scripts/python.exe -B BRAIN/regression_runner.py --suite safe-full`: 74 passaram, sem regressão detectada. Relatório local com identificador 20261125_021207_055911. |
| Supervisor corrigido | PASS_UNIT | `VENV/Scripts/python.exe -B -m pytest -q -p no:cacheprovider BRAIN/test_inference_supervisor.py`: 7 passaram em 0,44 s. |
| Descoberta do Ollama antes de iniciar serviços | BLOCKED | GET real de versão em 11435 retornou WinError 10061. Junction apontava para o armazenamento esperado. Inventário em disco com 16 manifestos. O catálogo da API e o Vulkan estavam indeterminados. |
| Extensão | PARTIAL | `node --check EXTENSAO_NAVEGADOR/background.js` passou. Uso de aba ativa encontrado por inspeção. |

O aviso de finalização do pyreadline3 apareceu em processos de pytest que retornaram código zero. Os seis testes visuais históricos ficam fora de safe-full. Não houve atualização de baseline.

O sincronizador passou em 10 testes em 2,15 s, com arquivos temporários, um repositório Git descartável, conflito, reentrada, rollback e reexecução. Na primeira execução, quatro casos encontraram WinError 206 no caminho temporário longo. Repetição na unidade A usou `--basetemp .pytest_runs/<novo-id-curto>`. A aplicação efetiva desse pacote na instalação não é necessária: seus três destinos já correspondem aos hashes de chegada.

## P55.1 — revisão remota
| Verificação | Classe | Evidência |
|---|---|---|
| Protocolo autenticado | PASS_UNIT | 4 casos Python, Linux isolado, blobs remotos iguais |
| Pesquisa de fundo | PASS_UNIT | 5 casos Node, Chromium simulado, blobs remotos iguais |
| Extensão/ponte e foco Windows | NOT_TESTED | Probe opt-in publicado; ver BRAINNET_P55_REVIEW.md |

## P55.2 — transporte e prazos
| Verificação | Classe | Evidência |
|---|---|---|
| Protocolo e transporte | PASS_UNIT / PASS_INTEGRATION_LOOPBACK | 14 testes Python, 9 subtestes, 1,17 s; 10 casos com HTTP real local |
| Pesquisa e validade de comando | PASS_UNIT | 6 casos Node, API Chromium simulada |
| Integração do kernel / extensão real | NOT_TESTED | Probe opt-in atualizado; ver BRAINNET_P55_2_REVIEW.md |
