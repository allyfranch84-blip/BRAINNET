# V9.4 — Rust seletivo e inferência

## Medições e decisão

Benchmark local sintético, Windows 11/Python 3.12, dimensão FHRR/QFHRR 10.000, GHRR 256; tempos em ms. JSON completo: `V9_4_BENCHMARK.json`. FHRR inicialização 37,44; NumPy bind p50/p95 0,02165/0,0232; bundle de 4 1,0566/1,094; similarity 0,0072/0,0079. Numba indisponível neste interpretador, portanto não há comparação Numba. GHRR bind 0,0315/0,0322 e remoção esquerda 0,0393/0,0459 em dimensão 256. QFHRR bind 0,0149/0,0153; similarity 0,11365/0,147.

QFHRR pack anterior p50/p95 3,605/3,7441 (10 medições); implementação vetorizada final 0,0749/0,0974 (100 medições), cerca de 48x na mediana neste ensaio. Amostras e quantidades diferentes; não é medição de tarefa real. Teste reproduz o algoritmo antigo para comprimentos 0–32, 127, 256 e 10.000, valores 0–31, compara bytes e round-trip. Formato de três bits permanece o mesmo; máscara v2 usa o mesmo pack. Memória RSS processo 50.606.080 antes e 53.768.192 após benchmark geral; processo final separado reportou 38.830.080 bytes. Não se mede alocação incremental por operação ou VRAM.

Índice FHRR com um item p50/p95 1,7885/1,7996; situação update 0,0278/0,0398 e snapshot 0,0143/0,0271; loader vazio inicial 1,02 e scan 0,081/0,1004. P-DAG foi medido apenas vazio: busca exata ausente 0,0005/0,001 e aproximada vazia 0,0006/0,0007; esses números não medem uma busca aproximada com nós reais. Não foram medidos custo por tarefa, carga de modelos, primeiro token ou tokens/s.

Não foi criada extensão Rust: cargo, rustc e maturin não foram encontrados no PATH, e o gargalo observado de pack teve uma alternativa NumPy mais rápida que preserva bytes nas amostras. Não se demonstrou ganho de Rust nem se avaliou busca FHRR em lote em carga representativa; recomenda-se manter Python/NumPy/Numba existente até obter benchmark representativo e binários verificáveis. GHRR e demais operações não foram portados.

## Habilidades e memória

`rem_sleep_engine.py` gerava scripts que apenas devolviam payload com `status=COMPLETED` sem executar. Novo template informa `PROPOSAL_ONLY`, `executed=False`, `verified=False`. `skill_loader.normalize_skill_result` corrige esse estado para scripts legados consumidos por `DynamicSkillLoader.execute_skill`; `BrainnetBridge.run_skill` aplica a mesma normalização e não reporta `ok=True` para proposta. Testes usam script sintético em diretório temporário e mock. Arquivos de habilidades existentes não foram reescritos; chamadas diretas a funções antigas fora desses dois consumidores ainda podem retornar COMPLETED. Não se executam passos automaticamente. REM e H-Mem legados ainda podem excluir dados se chamados; não foram acionados, nem foi conectada recuperação adicional ao roteador.

## Backend sem Ollama e portabilidade

`inference_backend.py` já possui `LlamaCppAdapter` por HTTP e `LlamaProcessManager` opcional que inicia/encerra seus processos próprios; não depende do Ollama. Não foi implementada nova ligação em processo, porque o caminho direto e os requisitos de cancelamento, memória e offload não foram verificados neste ambiente. Nenhuma inferência foi executada; compatibilidade funcional dos GGUF e Vulkan RX 580 não foi reconfirmada. Há GGUF locais inventariados no relatório V9 de compreensão, mas presença de arquivo não prova compatibilidade.

O projeto [llama-cpp-rs](https://github.com/utilityai/llama-cpp-rs) fornece bindings Rust `llama-cpp-2`; é alternativa experimental, não instalada. A [documentação oficial do llama.cpp](https://github.com/ggml-org/llama.cpp/blob/master/docs/install.md) descreve builds Vulkan para Windows, sem comprovar suporte à GPU específica deste computador. Comparação CPU/Ollama/Vulkan requer autorização e mesmo modelo, quantização e prompt.

`portable_manifest.json` adiciona componente Rust opcional marcado PENDENTE, sem download, hash ou binário inventados; fallback é NumPy/Python. Não há instalador de wheels, download com consentimento, verificação nova de hash ou binário Windows compilado. O Kernel não exige Rust.

## Validação

Sintaxe de `BRAINNET.py`, `skill_loader.py`, `rem_sleep_engine.py` e testes validada por AST; QFHRR foi importado e testado. `test_v94_skill_contract.py`: 3 testes focados passaram antes do quarto teste de pack ser acrescentado; a seleção final inclui os quatro. Regressão auditada com 23 arquivos: 180 testes e 46 subtestes aprovados em 4,79s, zero falhas/ignorados; `V9_4_REGRESSION_TESTS.log`. A suíte completa não foi executada. Checkpoints pré-alteração em `development_logs/checkpoints/v94_20261111/`. Não se detectou autoinspeção ativa no instante consultado. Nenhum modelo, serviço, mouse, teclado ou GUI foi iniciado.
