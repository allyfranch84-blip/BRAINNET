# P52.1 — política adaptativa e bancada local de modelos

Base: 115c92ccaa0c1178d2d302abb6c5401dcb8d3e3e. Código e testes: 50a87079f8bfce8a795c4a4d9bea0a0bea0affef. Branch de revisão, não instalada; updates/local permanece intacto.

## Entrega
BRAIN/adaptive_model_policy.py consulta apenas loopback 11435; valida versão e catálogo, escolhe entre tags explicitamente instaladas, aplica limites iniciais por perfil (FAST 2048/256/30s; BALANCED 4096/768/90s; DEEP 4096/2048/180s). A ordem de alternativas ainda é hipótese, não ranking medido. Não chama CLI nem /api/pull. A seleção isolada não altera o kernel nem a configuração de modelo.

O CLI sem argumentos faz somente consultas GET à API. --run FAST, BALANCED ou DEEP autoriza três gerações sequenciais com prompts públicos sintéticos: negação, esclarecimento e ordenação de missão. Registra modelo, resultado comparado com JSON esperado, tempo total, motivo de término, tokens e velocidade quando reportada. Não controla o desktop nem grava notas. O parâmetro keep_alive 30s pode alterar a residência do modelo; executar sem outras inferências em andamento. O timeout HTTP não comprova interrupção de inferência no servidor. Os três prompts são uma triagem pequena, não um benchmark psicométrico nem validação de planejamento/execução reais.

## Evidência
PASS_UNIT: python -m pytest -q -p no:cacheprovider em diretório isolado: 8 passaram em 0,03s (catálogo/API simulados). Hashes Git comparados com o conteúdo publicado: adaptive_model_policy.py d3abf0bb5d9a23d6ba61f6aeab0ebb6bc531fff6; test_adaptive_model_policy.py 219460d71615b67d9fcb2d8fff27d92f47dcb264.
NOT_TESTED: inferência Ollama real, GPU, modelo Thinking, integração com BrainnetBridge, comparação qualitativa geral.
Primeira falha: nenhuma nos oito testes executados.

## Continuação
O usuário relatou várias falhas na bateria anterior, sem resultados individuais nesta rodada. Solicitar o relatório de A–F e a saída da bancada FAST/DEEP (não repetir a bateria completa). Priorizar falhas comprovadas. O último checkpoint Codex continua ausente do remoto após 115c92c. Preservar os arquivos locais modificados (principalmente BRAINNET.py, conversation_router.py, probes e sincronizador). O sincronizador P0 tem lista fixa de destinos e não deve ser substituído sem comparar a versão operacional. Obter a bancada pelo commit fixo e criar somente arquivos novos (ou aceitar conteúdo idêntico), sem checkout nem aplicação de instalador remoto. Depois dos dados reais, revisar política, incluir eventos de modelo selecionado e conectar à versão local mais recente do kernel. A revisão P55.2 segue em review/p55-browser-bridge.
