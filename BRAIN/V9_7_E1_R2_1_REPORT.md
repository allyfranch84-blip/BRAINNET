# V9.7-E1-R2.1 — auditoria inicial

Não implementado. A tarefa ainda não possui orçamento compartilhado fim a fim: `send_command` define apenas modo em ContextVar; `_send_command_impl` cria outro task_id depois de retornos antecipados; UI-TARS cria novo task_id e usa limite local; `run_in_executor` não propaga ContextVar automaticamente; diversos clientes Ollama usam urllib diretamente e contornam `inference_backend`; o planejamento pode ocorrer em thread e exige propagação explícita. Cancelamento de autorização e cancelamento de inferência têm contratos distintos.

A estrutura existente `TaskContinuity` registra estado da tarefa, mas não fornece contadores atômicos, prazo monotônico ou contabilização de tokens. A implementação precisa preservar autorização e garantir que esgotamento no worker impeça etapas posteriores antes de se declarar um orçamento global. AUTO atual considera comprimento, não risco, evidência ou custo.

Nenhuma implementação, teste ou diff foi produzido nesta etapa; o critério de integração entre módulos não foi comprovado. Os testes e limitações anteriores estão em V9_7_E1_R1_REPORT.md e V9_7_E1_R2_REPORT.md.
