# V9.5 — integração funcional e inferência gerenciada

## Habilidades

A busca estática localizou `DynamicSkillLoader.execute_skill` e `BrainnetBridge.run_skill`; ambos normalizam o retorno legado `CRYSTALLIZED_ZERO_LLM` com `COMPLETED` para `PROPOSAL_ONLY`, e o template REM novo já retorna proposta. Testes anteriores cobrem ambos. Não foram encontradas garantias para chamada direta de funções importadas por outros consumidores ou para habilidades arbitrárias que aleguem COMPLETED: a missão não corrigiu todas as habilidades existentes. `PROPOSED/VALIDATED/AUTHORIZED/EXECUTED/VERIFIED/FAILED` ainda não formam máquina de estados integrada. Importação dinâmica executa código Python do arquivo e não é sandbox; não foram carregadas habilidades reais. Nenhuma experiência foi consolidada.

## Proposta procedural

`MyelinatedPDAGEngine.propose_verified_procedure` consulta chave exata já existente, exige `teacher_verified` e contexto com hwnd/pid e retorna passos copiados com `status=PROPOSED`, `execution_authorized=False`, `context_revalidation_required=True`. Sob `BRAINNET_PROCEDURAL_PROPOSALS=1`, `BrainnetBridge` anexa proposta ao contexto do roteador; padrão desativado. Isso conecta consulta ao ponto de decisão após reinício, mas o roteador atual não consome a proposta para construir plano e não confirma que contexto corresponda ao histórico. A chave legada usa os primeiros 40 caracteres e pode colidir. A proposta não autoriza nem executa.

Testes simulam recuperação P-DAG, contexto ausente, rota não verificada e checagem de autorização separada. Não há teste de resultado factual efetivo ponta a ponta. O caminho legado em `CausalTrajectoryEngine.executar_trajetoria_completa` ainda consulta rotas aproximadas e pode executá-las após verificações próprias; não foi modificado ou comprovado seguro nesta missão. H-Mem/REM legados continuam com operações destrutivas possíveis, não foram acionados.

## Inferência

O backend atual já usa `LlamaProcessManager`/`HTTPInferenceBackend`: processo próprio sob demanda, limite de reinícios, porta própria, CPU/Vulkan configuráveis, timeouts e cancelamento por requisição; `ModelResidencyManager` gerencia leases em interfaces simuladas. Não há integração completa automática entre leases e todos os clientes, descarregamento efetivo por ociosidade, nem fallback automático comprovado. Padrão Ollama preservado. `validate_model_artifacts` e `LlamaProcessManager` agora aceitam `expected_model_sha256` opcional e verificam hash completo antes de iniciar processo próprio; mismatch bloqueia Popen. Sem hash, comportamento anterior permanece (assinatura GGUF apenas). O hash valida integridade contra valor fornecido, não estrutura completa ou compatibilidade.

Sem carregar pesos, inventário anterior identificou GGUF locais e a instância Ollama em 11435 oferecia all-minilm e nomic; ambiente do processo apontava diretório C:, enquanto A: contém mais manifests. Nenhum modelo foi iniciado ou verificado nesta etapa. Para comparação posterior: usar mesmo GGUF/quantização e prompt com endpoints isolados, medir startup, primeiro token, throughput e RAM/VRAM; apenas após autorização explícita. `llama-cpp-2` permanece alternativa Rust documentada na V9.4, não instalada.

## Benchmarks e limites

`V9_5_SYNTHETIC_BENCHMARK.json`: 50 iterações, FHRR 256D, GHRR 128D, rota simulada, zero inferências e zero objetivos verificados. p50/p95: FHRR 0,2372/0,2831ms; proposta P-DAG com mock 0,0345/0,0464; GHRR 0,584/0,6411; montagem 0,0023/0,0027; verificação simulada 0,001/0,0012; total com recuperação 0,8669/0,9437; sem recuperação simplificado 0,0009/0,001. Caminhos não são equivalentes e não demonstram ganho; RSS total 45.592.576 bytes não é custo incremental. Não foram medidas seleção real de habilidade, chamada LLM, tempo de carga ou VRAM.

## Validação

`ast.parse` dos arquivos Python alterados passou. Seleção auditada de 24 arquivos + testes novos: `V9_5_REGRESSION_TESTS.log` registra 184 testes e 46 subtestes aprovados, zero falhas/ignorados, 5,03 s. `V9_5_FOCUSED_TESTS.log` registra execução anterior de 10 testes, 1,49 s. Suíte completa não executada. Checkpoints em `development_logs/checkpoints/v95_20261111/`.

Instância `BRAINNET.py` já estava em execução durante a missão; pesquisa estática não encontrou chamador de SelfInspector na produção examinada. Não foi interrompida nem recarregada, logo as alterações não estão ativas nela. Nenhum modelo, GUI, teclado ou mouse foi iniciado por este trabalho; não foram alterados bancos ou dados pessoais. Risco residual de inicialização concorrente de inspeção e caminhos dinâmicos não auditados permanece.

**Critério de conclusão não atingido:** ainda não foi demonstrado fluxo real intenção → experiência → autorização → execução → resultado factual verificado. Antes de ativar, implementar revalidação de contexto/identidade no plano efetivo, auditar o fast-path legado e simular ciclo com verificador independente; somente depois considerar teste supervisionado real.
