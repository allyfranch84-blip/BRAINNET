# V9.1.3 — fechamento de gaps

## 1. GHRR / P-DAG — parcial

Antes: `unbind_left`/`unbind_right` já existem; `unbind` preserva lado direito legado. `syntactic_pdag` é inicializado como None. Se injetado, o planejador antigo recuperava chave legada e convertia passos diretamente em pipeline. Alteração: o mesmo ponto de `decompor_trajetoria_cognitiva` agora usa `propose_route` e devolve proposta com pipeline e passos vazios. A execução posterior encerra por ausência de passos. A proposta mantém autorização falsa; não há ativação automática ou novo banco. O teste focado injeta mock no planejador real e valida ausência de passos. Limites: Kernel não injeta P-DAG sintático; não foram implementadas busca aproximada, comparação por contexto ou revalidação de alvo. A mudança afeta somente quando a dependência for injetada. ReLU/resonator não ativado.

## 2. Inferência e modelos — parcial

Antes: `describe_ui_with_protocol` já usa `BRAINNET_VISION_KEEP_ALIVE` (padrão 5m), mas `_consultar_visual_json` usava zero. Alteração: ambos respeitam a mesma variável, incluindo override explícito zero. Teste inspeciona payload HTTP simulado; não demonstra residência, concorrência ou desempenho real. Manager de residência já recusa evicção com `active`, mas não está integrado às requisições visuais, portanto proteção ativa ponta a ponta permanece pendente.

Em consulta read-only, 127.0.0.1:11435/api/tags retornou all-minilm e nomic-embed-text; 11434 expirou após 2s. Há manifests adicionais em A:\OLLAMA_MODELS conforme inventário anterior. Os processos `ollama app.exe` e `ollama.exe serve` estavam presentes, mas seu ambiente efetivo e diretório não foram comprovados; causa da divergência é desconhecida. Nenhum serviço foi iniciado ou encerrado. Não foi feito benchmark Ollama/llama.cpp nem aferição de RAM/VRAM ou tokens/s; o mesmo modelo e recursos não foram validados para comparação.

## 3. Orquestrador ativo — bloqueado

`cognitive_orchestrator.py` não foi encontrado na árvore inspecionada; apenas bytecode antigo foi localizado, não carregado. `model_residency_manager.py` possui drivers/admissão injetáveis, mas decisões não estão conectadas a um orquestrador ativo. Nenhum novo substituto ou controlador de carga/descarga foi ativado. Faltam identidade, contrato, testes de ciclo de vida e orçamento de RAM/VRAM confiável. Não há suporte de Sleep Mode presumido.

## 4. Memória antes da decisão — pendente

A flag de memória cria índice e registra eventos, porém `router.read_situation` não é chamado pelo ciclo principal; H-Mem e P-DAG não foram conectados ao planejamento ou metacognição nesta missão. Não há comparação ligada/desligada. A consolidação H-Mem legada continua destrutiva; a alternativa preservadora existe, mas não foi ativada. Nenhum dado foi consolidado. Lembrança não autoriza atuação.

## 5. Atenção visual / ROI — parcial

O mapeamento existente `protocol_point_to_screen` foi testado com imagem redimensionada, offset negativo de monitor e coordenadas inválidas, sem clique. O controle de foco/geometria existente não foi modificado. Testes não comprovam DPI de Windows, várias telas reais, fallback de região, ausência de alvo ou integração UIA-OCR-VLM. Nenhuma alteração de estratégia ROI foi feita.

## Verificação e riscos

Checkpoint antes das alterações: `development_logs/checkpoints/v913_20261111/` contém cópias prévias de `vision_eye.py`, `causal_trajectory.py`, `BRAINNET.py`. Sintaxe AST dos dois arquivos e teste novo passou. Testes iniciais: `test_v909_foundation.py test_v908_long_context.py test_v911_prepared.py`: 12 aprovados em 1,20s. Testes focados `test_v913_gaps.py test_v911_prepared.py`: 8 aprovados em 1,20s. Regressão auditada: `python -m pytest -q --tb=short -p no:cacheprovider test_v913_gaps.py test_v911_prepared.py test_v91_comprehension.py test_v91_hdc.py test_ghrr_pdag.py test_v909_foundation.py test_v908_journal.py test_v908_long_context.py test_v9_safety.py test_paint_app_context.py test_ui_scene_graph.py test_passive_attention.py test_adaptive_resource_controller.py test_model_residency_manager.py test_inference_capability.py test_inference_backend.py test_canvas_goal_simulated.py test_uia_property_read.py test_contextual_grounder.py`: 164 aprovados, 46 subtestes, zero falhas ou ignorados, 4,68s. Plugins automáticos desativados; logs separados na pasta BRAIN. A suíte completa não foi executada. Não se observou processo de Kernel/inspector no instante da verificação; isso não impede inicialização concorrente posterior.

Sem medições de latência de inferência, RAM, VRAM ou benchmark de recuperação neste lote. Próximo passo: recuperar contrato de orquestração verificável, integrar leases de residência às requisições reais e testes de concorrência, validar orçamento, e integrar memória apenas como evidência contextual sob autorização independente.
