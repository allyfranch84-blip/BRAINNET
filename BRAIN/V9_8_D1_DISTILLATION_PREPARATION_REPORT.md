# V9.8-D1 — Preparação de destilação

**Estado: preparação parcial; não pronto para treinamento ou gasto.** Nenhuma requisição paga foi enviada, nenhum peso foi modificado e nenhum modelo foi iniciado. Gasto nesta missão: US$ 0,00.

## Modelos e hardware

O caminho conversacional de `BRAINNET.py` seleciona `qwen2.5:1.5b`; geração de código e `assistant_prompts.MODELO_DEEP` referenciam `qwen2.5-coder:7b`. Manifests em `A:\OLLAMA_MODELS\manifests\registry.ollama.ai\library` e arquivos de configuração indicam formato GGUF Q4_K_M, família qwen2; modelo 1.5B com blob de 986.048.512 bytes e Coder indicado como 7.6B, blob de 4.683.074.048 bytes. Os blobs e demais camadas foram encontrados e os blobs de modelo começam por GGUF. Não foram recalculados SHA-256 nem comprovado carregamento no Ollama; manifests não comprovam identidade dos pesos originais ou disponibilidade no endpoint ativo.

As fichas oficiais de [Qwen2.5-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct) e [Qwen2.5-Coder-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct) indicam Apache-2.0; a correspondência exata entre os blobs locais e essas revisões não foi estabelecida. Verificar licença, revisão e proveniência antes do uso ou redistribuição.

O relatório H3 identificou RX 580 2048SP mas não validou capacidade de VRAM utilizável; não presumir 8 GB. [PEFT/QLoRA](https://huggingface.co/docs/peft/main/en/developer_guides/quantization) exige backend de treino compatível e pesos/quantização suportados; um GGUF de inferência existente não comprova capacidade de treinar. CPU, RAM, stack e backend Windows/AMD precisam ser medidos e validados; Ollama ou Vulkan por si sós não comprovam LoRA/QLoRA. Não foi inspecionada uma instalação independente dos pesos originais em safetensors nem executado treinamento.

## Dataset

`distillation_d1/candidates.jsonl`: 3 candidatos mínimos, sem credenciais ou dados pessoais conhecidos, com entrada, resposta local quando evidenciada, resultado, critério, categoria, fonte e professor ainda não selecionado. Um representa diagnóstico de componente determinístico (não saída LLM), um é relato do usuário com data não confirmada e um é falha de fixture/teste (não defeito do modelo). Todos exigem revisão; o terceiro está marcado NOT_TRAINING_EVIDENCE. Não se deve treiná-los diretamente. Seleção de ferramentas, planejamento, falsa confirmação, factualidade e recursos não têm exemplos completos e verificáveis extraídos nesta missão; não foram preenchidos com saídas inventadas.

A divisão por hash de grupo atribuiu os três ao treino e zero à validação/teste. Entradas normalizadas idênticas em grupos diferentes são rejeitadas, mas paráfrases e vazamento semântico não são detectados automaticamente: agrupar casos relacionados manualmente e obter evidências suficientes antes de definir splits imutáveis. Dataset insuficiente para avaliar generalização.

## Preparação de cliente e orçamento

Foram auditados `distill_data_generator_72b.py` e `local_distiller.py`: o primeiro contém cliente OpenRouter com requests reais e não foi chamado; o segundo usa Ollama. `distillation_preparation.py` prepara payload no formato messages/choices OpenAI-compatible e utiliza transporte explicitamente injetado, sem cliente HTTP remoto instalado ou habilitado por padrão. `OfflineTeacherBudget` é simulação em memória, com teto configurável até US$ 0,70, reserva por tokens/rates informados, deduplicação, resposta estruturada, custo por uso informado e bloqueio diante de resultado/custo desconhecido. Não há retry automático; isso evita repetição com cobrança não confirmada. Ele não é um limite financeiro robusto para produção: estado não persiste, input_tokens e preços são fornecidos pelo chamador, custos extras e arredondamento de faturamento não foram validados, e transporte injetado precisa de isolamento. Não habilitar chamadas pagas até implementar ledger transacional persistente, reconciliação de uso/custos, limites no provedor, autenticação segura, preços vigentes e aprovação específica.

Nenhum professor foi selecionado, nenhuma revisão de termos específica foi concluída e nenhum preço foi configurado; custo futuro é **indeterminado**, não US$ 0,70 por previsão. Fórmula de orçamento: `(tokens_entrada × preço_entrada + tokens_saída × preço_saída)/1.000.000`, mais taxas aplicáveis. O limite de US$ 0,70 é teto solicitado, não estimativa de gasto.

O [OpenAI Services Agreement](https://openai.com/policies/services-agreement/) contém restrição ao uso de outputs para desenvolver modelos concorrentes, sujeita a exceções e contrato aplicável; não presumir que um professor OpenAI seja autorizado para esta finalidade. Avaliar individualmente os termos atuais do provedor e seu contrato antes de selecionar qualquer professor. Outros provedores e eventuais restrições de dados de terceiros permanecem pendentes.

## Avaliação e testes

`summarize_evaluations` agrega taxas apenas quando os resultados são explicitamente verificados; métricas ausentes ficam desconhecidas e promoção permanece desabilitada. Ainda não há comparação real original versus adaptado, medição de latência, memória ou regressões de modelo. É necessário reservar conjunto de teste independente e avaliação humana/automática comprovada antes de treinamento.

`python -m unittest test_v98d1_distillation -v`: 7 aprovados, cobrindo ausência de transporte por padrão, deduplicação, teto, custo desconhecido, concorrência e splits idênticos. `python regression_runner.py --suite safe-full`: 73 aprovados, 0 falhas, JUnit `development_logs/REGRESSION_20261117_202516_702938.xml`. Sem API paga e sem alteração de modelos.

**Critério integral não atingido:** não existe dataset de treino validado e dividido, nem adaptador remoto pago seguro e auditado, nem benchmark de modelos. A execução está restrita a preparação e simulação.
