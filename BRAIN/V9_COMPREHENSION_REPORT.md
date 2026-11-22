# V9.1-COMPREHENSION — relatório

## Inventário de modelos e runtimes

A sessão informa OLLAMA_HOST=127.0.0.1:11435 e OLLAMA_MODELS=A:\OLLAMA_MODELS. `ollama list` consultado sem carregar modelos retornou somente `all-minilm:latest` (45 MB, ID 1b226e2802db) e `nomic-embed-text:latest` (274 MB, ID 0a109f422b47). Ambas são listagens, não testes de embedding. Há processos Ollama vivos; não foi verificado o ambiente herdado pelo servidor, portanto a discrepância a seguir não tem causa comprovada.

Os 13 manifests sob A:\OLLAMA_MODELS incluem brainnet-parser, brainnet7b, qwen2.5 0.5b/1.5b, qwen2.5-coder 7b/14b, qwen2.5vl 3b, qwen3-vl 2b/4b/8b, qwen2.5-abliterate 7b, all-minilm e nomic. Presença de manifest não prova integridade de blobs nem disponibilidade no servidor. `portable_manifest.json` registra identificadores e soma dos tamanhos declarados, sem inventar licença, revisão ou compatibilidade.

Arquivos GGUF encontrados sob A:\BRAINNET: brainnet-parser-v2.gguf (3.093.669.184 bytes), brainnet-7b-q4_k_m.gguf (4.683.073.504), brainnet-parser-1.5b-q4_k_m.gguf (986.048.160), Qwen2.5-0.5B-Instruct-ollama.gguf (397.807.936). Não foram inspecionados metadados ou carregados. Cache Hugging Face observado contém clip-vit-large-patch14 e llama-3-tokenizer; conteúdo e revisão não foram validados. Parakeet Redux, EmbeddingGemma 2, Pocket TTS, Timestral, MAI-UI-2B, Moondream 2 e Qwen3-ASR não foram identificados nas fontes verificadas; não se comprova ausência em outros diretórios.

Runtimes Python `whisper`, `faster_whisper`, `piper`, `TTS`, `sentence_transformers` e `yt_dlp` não foram encontrados pelo interpretador usado; `yt-dlp.exe` e `ffmpeg.exe` existem no PATH. `speech_voice.py` referencia edge-tts; disponibilidade funcional não foi testada. Ruff e Pyright não foram encontrados como comandos/módulos. Para instalação opcional em Core/Edge/Desktop, primeiro identificar fonte oficial, licença, arquitetura, revisão e hash de cada componente e verificar capacidade e espaço; não foram validados comandos específicos nem baixados pesos. Core permanece sem dependência nova; Edge CPU e Desktop exigem escolhas e medição próprias.

## Código e interpretação

`code_mapper.index_symbols` indexa AST sem modelos e informa arquivo, linhas, imports, classes, funções síncronas e assíncronas, argumentos, anotações, chamadas estáticas e raises. BRAINNET.py: 1388 linhas, 36 símbolos; causal_trajectory.py: 1532 linhas, 45 símbolos. Referências estáticas não comprovam execução, dependências de serviço e efeitos ainda não são classificados, testes associados não são inferidos, e chamadas dentro de funções aninhadas podem aparecer no símbolo pai. O `generate_guide` legado não foi alterado: ainda pode duplicar blocos e enviar blocos completos ao LLM. O novo índice não está conectado ao Kernel nem produz automaticamente respostas às perguntas.

`natural_comprehension.py` preserva texto e detecta marcadores de URL/caminho/código/números; sugere correções limitadas, classifica algumas intenções e nunca autoriza execução. A correspondência é conservadora e isolada, não está integrada ao planejador ou ao sistema de habilidades. Não identifica todos os nomes próprios, ironia contextual ou caminhos com espaços; correções são apenas sugestões e correspondências aproximadas perigosas exigem esclarecimento. O registro tipado de capacidades é parcial, com disponibilidade falsa para funcionalidades não integradas; não implementa todos os contratos de /help nem executa atalhos.

## Tarefas longas

`long_workflows.py` contém protótipos isolados: BookDraft mantém capítulos e não declara conclusão até todos marcados revisados com texto; serializa/restaura string JSON, mas ainda não salva/exporta arquivos, verifica fatos, gera capítulos ou usa memória contextual. `inspect_video` valida domínios YouTube e utiliza callbacks injetados; distingue falha de metadados, ausência/falha de legendas e dados fornecidos, marcando visão não analisada. Não baixa vídeos, não transcreve, não suporta quadros, não responde perguntas, não extrai conceitos e não está integrado ao Kernel. Casos de transcrição parcial e retomada persistida real ainda não foram implementados. Não afirmar estudo de vídeo ou livro concluído a partir desses protótipos.

## Validação

Com plugins automáticos desativados: `python -m pytest -q -p no:cacheprovider test_v91_comprehension.py test_v91_hdc.py test_ghrr_pdag.py test_v909_foundation.py test_v908_journal.py test_v908_long_context.py test_v9_safety.py test_paint_app_context.py test_ui_scene_graph.py test_passive_attention.py test_adaptive_resource_controller.py test_model_residency_manager.py test_inference_capability.py test_inference_backend.py test_canvas_goal_simulated.py test_uia_property_read.py test_contextual_grounder.py`: 156 testes e 46 subtestes aprovados, nenhum ignorado ou falho, 4,28 s. Nenhuma suíte completa foi executada. SelfInspector pode rodar pytest e restaurar arquivos, mas não foi chamado ou alterado; inspeção de processos não oferece garantia contra uma inicialização concorrente posterior.

Medição sintética de interpretação, 1000 chamadas sobre três strings: p50 0,0411 ms, p95 0,0622 ms, RSS do processo 23.556.096 bytes; não é medição de memória incremental ou de recuperação de contexto. Nenhuma inferência real, download, GUI ou ação física foi realizada.

## Próximos bloqueadores

Integrar capacidades existentes ao planejador sem construir comandos arbitrários, adicionar autorização e testes negativos reais, implementar persistência/retomada e verificação de livros, adaptadores de mídia com proveniência e acesso autorizado, ampliar análise de referências e efeitos e medir num corpus independente. Investigar configuração efetiva do servidor Ollama antes de declarar modelos ausentes. Os critérios completos da missão ainda não foram alcançados.
