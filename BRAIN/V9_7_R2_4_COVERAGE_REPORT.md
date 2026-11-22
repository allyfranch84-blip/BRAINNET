# V9.7 R2.4 — cobertura do orçamento

## Alterações
Busca DuckDuckGo do handler real registra operação de ferramenta, respeita prazo no transporte, não reserva tokens e descarta resultado tardio após cancelamento. Quando há orçamento, usa uma única chamada urllib, sem repetição após falha; não acessa GUI. InferenceResult aceita contagens opcionais de entrada/saída reportadas pelo Ollama e llama.cpp; a conversa principal registra tokens de saída reportados no orçamento. Estimativa reservada permanece conservadora, inclusive após resposta; não há política de expiração nem liberação de reserva. A dupla contabilização de uma mesma operação concluída é impedida pelo estado da operação.

## Cobertura por cliente
- Conversa de perguntas: reserva de inferência, timeout, tokens de saída reportados quando disponíveis e rejeição de resposta após cancelamento. Transporte bloqueante não é interrompido pelo evento.
- Busca DuckDuckGo: operação de ferramenta e prazo; conteúdo apenas de resultados e links, não verificação factual; sem retries no caminho contabilizado.
- UI-TARS/VLM: contagem parcial existente de iterações e chamadas; sem tokens reportados nem timeout efetivo ligado ao prazo na thread bloqueante.
- Gerador de código: reserva parcial e cancelamento após resposta; sem conciliação de tokens.
- Thorium/extensão Chromium: fora do orçamento; não foi acionado ou modificado. O ramo legado de pesquisa interativa existe, mas acessibilidade efetiva e autorização específica não foram comprovadas; não presumir que a pesquisa background acione o navegador.
- Outras chamadas visuais (descrição de tela/ROI), gerador criativo causal, pesquisa/resumos legados: cobertura parcial ou ausente; ver V9_7_R2_3_BUDGET_COVERAGE_REPORT.md. LongContextEngine existe, mas sua chamada pelo caminho atual do Kernel não foi demonstrada. Memória local e FHRR não são chamadas de inferência e não tiveram medição de custo.
- llama.cpp: adaptador extrai tokens quando servidor retorna usage, mas sua utilização no caminho conversacional atual e integração ao TaskContext não foram comprovadas.

## Limitações
Tokens reservados e estimados seguem no mesmo campo `estimated`; tokens de entrada são expostos no resultado do adaptador mas não somados ao orçamento. Sem retorno válido, consumo continua desconhecido e reserva conservada. Não há política explícita de expiração, conciliação de operação remota desconhecida, cancelamento comprovado de thread/socket ou impedir duplicação entre tarefas distintas. Não há teste integrado completo pesquisa→recuperação→inferência→verificação, nem testes de Thorium simulado, VLM e contexto longo nesta etapa. Não declarar orçamento global concluído.

## Testes
Focados: 38 testes e 6 subtestes passaram em 2,01 s; regressão segura: 233 testes e 50 subtestes em 6,86 s, exit 0. Logs V9_7_R2_4_FOCUSED.log e V9_7_R2_4_REGRESSION_FINAL.log. Testes novos cobrem pesquisa sem GUI com transporte simulado, tokens reportados e descarte de resposta após cancelamento. Sem rede real, modelos ou ações físicas. Checkpoints development_logs/checkpoints/r24; diffs V9_7_R2_4_*.diff.
