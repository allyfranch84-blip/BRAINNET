# V9.0.9 — arquitetura e portabilidade

## Inventário e contratos

- O estado de comando está distribuído: `BrainnetBridge._last_executed_task`, `AdaptiveResourceController.tasks` com `TaskContinuity`, contexto de janela em `ContextualGrounder` e etapas no `UIProtocolController`. São cópias ou projeções com ciclos de vida distintos; não foi demonstrada sincronização entre elas.
- `HMemEngine` persiste episódios/esquemas em SQLite; `LongContextEngine` persiste resumo e andamento; `ContextualGrounder` guarda alvo em memória. `ExecutionEvidence` descreve possível aprendizado; o estado de execução UIA é separado da verificação de objetivo. A análise não provou que todas as decisões são persistidas.
- `router.py` escolhe rota e nome de modelo; `inference_backend.py` oferece seleção explícita Ollama/llama.cpp; `ModelResidencyManager` é coordenador optativo de carga/descarga, não integrado globalmente. `execution_authority.py` continua sendo a fonte de autorização. Nenhum mecanismo de autorização foi alterado.
- Caminhos rígidos incluem `BRAINNET.py` (raiz A:\\BRAINNET), `code_mapper.py`, `engineering_agent.py` e `ollama_watchdog.py` (A:\\OLLAMA_MODELS). Há endpoints fixos 11434 em clientes antigos. Portabilidade integral ainda não existe.
- `situation_memory.py` fornece `Observation`, `SituationSnapshot`, `VerifiedOutcome` e `ResourceBudget` tipados; reutiliza `TaskContinuity`, `InferenceRequest`, `InferenceResult` e `ExecutionProfile` por aliases. Esses contratos antigos não possuem todos os campos de versão, validade e proveniência solicitados; `ExecutionProfile` é perfil de execução, não inventário completo de capacidades. Evolução de contrato e interoperabilidade permanecem pendentes.

## Memória situacional experimental

`SituationMemory(enabled=True)` mantém observações globais e por tarefa em RAM, com lock, limite por tamanho serializado JSON, prioridade, origem, timestamps, expiração e invalidação por mudança explícita de janela. Snapshots são cópias e podem ser filtrados por chaves. `export_eligible` apenas devolve registros marcados como verificados e elegíveis; não grava dados. `restore_historical` devolve os registros como REVALIDATION_REQUIRED e não os reinsere no estado atual. A verificação do registro é responsabilidade do chamador; a estrutura não comprova evidência por si. Não existe aprendizagem ou autorização a partir da memória.

`AdaptiveInferenceRouter.read_situation` é consumidor explícito de leitura; a instância da memória não é criada pelo Kernel e `evaluate_route` não a utiliza. Isto demonstra leitura opt-in isolada, não integração de runtime completa. O limite mede bytes de JSON, não RAM efetiva do processo; expiração é filtrada na leitura e não é coletada automaticamente. Não há persistência durável nem monitoramento automático de foco. Não foram medidos custo ou RAM reais.

## Instalação portátil

`portable_manifest.json` lista Core, Edge CPU, Desktop GPU e Servidor opcional; versões, licenças não verificadas, requisitos, tamanhos e hashes ficam PENDENTE/null. `portable_planner.simulate` não instala, baixa ou inicia processos e retorna PENDING_EVIDENCE para informações incompletas. Não presume Vulkan por fabricante. `inference_capability.discover_hardware` já fornece CPU, RAM, disco e relatórios GPU, com VRAM/Vulkan desconhecidos quando não verificáveis; não foi conectado automaticamente ao planejador.

O Kernel ainda não foi validado sem modelos opcionais e há caminhos e clientes acoplados. O manifesto não é instalador executável e faltam revisão de dependências, licenças, fontes, tamanhos e hashes. Não executar downloads a partir de campos pendentes.

## Validação

`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p no:cacheprovider test_v909_foundation.py test_v908_journal.py test_v908_long_context.py test_v9_safety.py test_paint_app_context.py test_ui_scene_graph.py test_passive_attention.py test_adaptive_resource_controller.py test_model_residency_manager.py test_inference_capability.py test_inference_backend.py test_canvas_goal_simulated.py test_uia_property_read.py test_contextual_grounder.py`: 145 aprovados, 32 subtestes aprovados, 0 falhas, 0 ignorados, 3,69 s. Inclui concorrência, prazo, mudança de janela, falha simulada, limite serializado e revalidação após reinício simulado. Não mede RAM nem estabelece estabilidade de produção. Suíte completa não executada.

## Próximos passos

Definir uma interface de persistência explícita com verificação de evidências e testes de reinício real isolado; conectar leitura ao ciclo de vida do Kernel atrás de configuração e observar sem influência no roteamento; validar inicialização com backends ausentes usando simulação; completar manifesto com fontes verificadas. Não iniciar modelos, dispositivos ou download até validação separada.
