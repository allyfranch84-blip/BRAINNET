# V9.1-HDC — relatório de integração

## Situação real

Integração **parcial**: o Kernel não utiliza o novo índice nem recupera trajetórias GHRR por este trabalho. Não se demonstrou atuação, uso de modelos ou integração funcional ponta a ponta. Nenhum banco persistente foi alterado; testes de P-DAG usaram bancos temporários.

## Ordem 1 — álgebra

`ghrr_core.py`: `unbind` mantém o comportamento legado (remove fator direito); foram acrescentados `unbind_right` e `unbind_left` com ordem explícita. `generate_vector(None)` usa gerador persistente inicializado com a mesma seed: a primeira amostra permanece compatível e chamadas seguintes deixam de ser idênticas. Vetores com rótulo continuam determinados pelo mesmo SHA-256; nenhuma representação persistida foi convertida. A busca de chamadores não encontrou uso de GHRR `unbind` fora do motor; outras chamadas `.unbind` inspecionadas utilizam FHRR. Testes verificam inversões, ordem, não comutatividade, unitariedade, finitude, determinismo e diversidade.

`pdag_ghrr_extension.py` valida tamanho e finitude do blob antes de reconstruir o formato legado. Não existe checksum armazenado: alterações finitas do tamanho correto podem passar; integridade criptográfica não foi comprovada. `qfhrr_core.py` não foi alterado: zero é simultaneamente fase e marcador esparso, portanto a representação antiga perde a distinção. O round-trip de bits para valores Z8 e similaridade idêntica foram testados; não foi medida perda de similaridade frente a FHRR contínuo. Uma correção exige representação versionada com máscara explícita e migração, ainda não implementada.

## Ordem 2 — índice FHRR experimental

`situation_fhrr_index.py` recebe motor existente por injeção e mantém texto estruturado, metadados e vetor derivado em memória; usa `text_to_hypervector`, que é a API disponível nesta versão. Há limites em bytes dos vetores, escopo por tarefa, filtro de validade, versões e finitude e fallback exato quando geração de consulta falha. Similaridade não autoriza ações nem comprova fatos. O índice é separado de `SituationMemory`, não está ligado a `BrainnetKernel`, não preserva automaticamente todas as observações nem possui sincronização concorrente ou armazenamento persistente. Não é seguro usá-lo como fonte única de decisão. O orçamento cobre apenas vetores, não objetos Python.

## Ordem 3 — GHRR/P-DAG

`CausalTrajectoryEngine` inicia `syntactic_pdag = None`; o caminho existente consulta e grava rotas usando prefixo de 40 caracteres e não comprova todas as pré-condições exigidas nesta missão. Por isso não foi ativado nem conectado. Falta injeção segura, chave versionada por intenção e contexto, validação de aplicação, autorização e resultado histórico. Nenhuma habilidade foi executada ou treinada.

## Ordem 4 — H-Mem e recursos

A consolidação existente em `hmem_engine.py` agrega episódios e executa DELETE dos episódios antigos; não foi chamada nem modificada. Ela não satisfaz a exigência de preservação de referências e bloqueia a integração experimental segura. Não foram implementados orçamentos conjuntos de FHRR/GHRR/QFHRR/modelos, cache GHRR nem testes completos de portabilidade e reinicialização. O índice FHRR limita sua própria alocação vetorial. Não houve inferência nem execução de aplicativos ou mouse/teclado.

## Testes e medição

Seleção: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q -p no:cacheprovider test_v91_hdc.py test_ghrr_pdag.py test_v909_foundation.py test_v908_journal.py test_v908_long_context.py test_v9_safety.py test_paint_app_context.py test_ui_scene_graph.py test_passive_attention.py test_adaptive_resource_controller.py test_model_residency_manager.py test_inference_capability.py test_inference_backend.py test_canvas_goal_simulated.py test_uia_property_read.py test_contextual_grounder.py`: 150 testes e 32 subtestes aprovados, 4,07 s, zero falhas ou ignorados. Sintaxe dos arquivos novos/alterados validada com AST. Suíte completa não executada.

Ensaio sintético separado: 20 registros, dimensão 256, 20 consultas com o texto praticamente idêntico ao dos registros, NumPy sem JIT: top-1 20/20, mediana 0,3064 ms, p95 observado 0,3673 ms, 40.960 bytes de vetores, RSS do processo 38.510.592 bytes. O conjunto é trivial e não mede generalização, recall real, RAM incremental ou desempenho do Kernel. Testes iniciais falharam por uso de `semantic_bag` inexistente, conexão SQLite temporária aberta e orçamento/expectativa inadequados; corrigidos e repetidos. Uma tentativa de medição com módulo `resource` falhou porque ele não existe no Windows; a medição final usou psutil.

## Próximos passos

Definir consentimento e verificação de rota antes de qualquer leitura com possível atuação; preservar episódios H-Mem e suas referências; projetar formato versionado e checksum com leitura legada; integrar índices opt-in ao Kernel com testes simulados de autorização, contexto e validade; avaliar recuperação em conjunto sintético independente e medir memória incremental. Não ativar o caminho sintático atual enquanto suas verificações não estiverem completas.
