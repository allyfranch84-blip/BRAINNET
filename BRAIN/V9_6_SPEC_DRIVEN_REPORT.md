# V9.6 — especificações e convergência funcional

## Resultado e escopo
Implementação parcial: no planejador HTN, pedidos não citados de código Python são gerados pelo callback existente e validados estruturalmente antes de virar uma proposta TYPE. Para interface, exige importação tkinter e chamada Tk. Não executa o código, não autoriza atuação e não declara objetivo concluído. Pedido citado mantém tratamento literal. O callback existente depende do modelo iaos-qwen:latest em localhost:11434; sua indisponibilidade ou falha bloqueia a proposta.

## Evidência
Especificação versionada: development_logs/specs/V9_6_calculator_v1.md. Checkpoint: development_logs/htn_planner_v96_checkpoint.py. Sintaxe AST aprovada. Teste focado: 5 testes e 4 subtestes. Regressão auditada ampliada: 203 testes e 50 subtestes aprovados em 4,92 s; pytest exit 0, log development_logs/V9_6_REGRESSION_FINAL.log. Comparação com V9.5.2: seleção anterior registrou 198 testes e 46 subtestes, ampliada por cinco testes e quatro subtestes. Primeira execução interrompida durante coleta; outra execução atingiu 100% mas terminou com PermissionError na limpeza da pasta temporária padrão. Repetição com --basetemp próprio concluiu com exit 0. Não foi executada a suíte completa.

## Divergências e limitações
O artefato de teste é um exemplo gráfico sintético, não comprova calculadora funcional. A validação AST comprova apenas sintaxe e indício estrutural de Tk, não comportamento nem segurança; outras bibliotecas GUI ainda não são aceitas. O editor falso é simulado e não prova integração física ou leitura real de conteúdo; a confirmação factual da inserção e salvamento permanece pendente. Não houve inferência real. Não foi demonstrado o caminho completo pela interface do Kernel.

Os demais objetivos não concluídos incluem evidências de fontes históricas, tratamento de memória contaminada, distinção de pesquisa/extração/verificação, monitor Windows↔MSS e DPI, continuidade persistente, cancelamento comprovado, diagnóstico de CPU, comparação integral de tarefas e indicadores reais. Consultar V9_5_2_RELIABILITY_REPORT.md para limitações anteriores. Não se alteraram os caminhos desses componentes nesta missão.

## Processo de especificação e revisão
Especificação e filosofia registradas. Estados SPECIFIED, PLANNED, IMPLEMENTED e TESTED aplicam-se somente ao escopo do contrato HTN descrito; VERIFIED, APPROVED e ACTIVE não foram declarados para a missão. A referência oficial google/elephant-goldfish-model foi consultada; plugin EGM não está disponível no ambiente desta sessão. Não foi instalado, nem houve revisão independente Goldfish; os documentos são registros locais e não substituem tal revisão.

Pydantic, Ruff, uv, Polars, LanceDB e Maturin não foram encontrados no Python consultado; cargo/rustc também indisponíveis no PATH. Não houve instalação, lockfile uv, revisão Ruff, integração Pydantic, benchmark Polars/LanceDB ou migração. Detalhes em V9_6_NATIVE_BENCHMARK.md. Não se pode afirmar desempenho ou compatibilidade de extensão nativa.

## Próximo teste supervisionado
Após revisão das alterações e reinicialização supervisionada pelo usuário, verificar modelo disponível, autorizar explicitamente abertura/escrita, pedir a calculadora, conferir o conteúdo no editor e, separadamente, validar o funcionamento em ambiente apropriado. Não considerar sucesso com base apenas no plano ou no teste simulado.
