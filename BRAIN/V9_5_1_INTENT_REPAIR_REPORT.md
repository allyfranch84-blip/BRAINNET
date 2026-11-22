# V9.5.1 — diagnóstico e correção de intenção

## Diagnóstico anterior à alteração

Consulta local direta, sem Kernel, modelo, mouse ou GUI: texto `abra o paint`; `analyze_literal_intent` retornou action OPEN, domínio DIGITAL_UI, target `paint`, sem autorização; `system_launch_target` retornou `paint`. Primeiro ponto que perdeu o sinal: `TheoryOfMindEngine.evaluate_intent` ignorou o contrato, atribuiu confiança 0,208 e retornou `NEED_MORE_DATA`, alegando ausência de elemento/aplicativo. `AdaptiveInferenceRouter` retornou `DEEP_PATH`, portanto não corrigiu a perda; `DigitalProprioceptionGate` isolado retornou AFFORDANCE_VALIDA. A execução real antiga não foi observada nesta missão, mas a decisão defeituosa é reproduzível nos componentes atuais.

Hashes dos arquivos em disco no diagnóstico anterior: BRAINNET.py `b5a8ae903bc1c8d7eb75933381b97bbc509a697705333b670d7381b880157b63`; theory_of_mind.py `00dd3dbf1345d1d078f1b09015376e8cbc05f2598729d95c894313de7631a270`; router.py `526c9a6fd887cf3998f4a4a72a4ea09df38111d89917dd7608948292fa76174e`; parser_contract.py `529edcc67cfde6fd5f19a067812b26f2626ae2636b8111a1efd82f49c5879d`; system_intent.py `9eba1029710322a2cfe0814e5a5277ee643faaa2ab908a53ea3542b42f48584e`. São hashes de disco, não prova do código carregado por outro processo.

## Correção

`parser_contract.py` preserva os campos legados `action=OPEN` e `target` e acrescenta `intent_kind=OPEN_APP` e `canonical_target=Paint` ou `Notepad`; negação, pergunta e objetivo composto são identificados separadamente e `execution_authorized` permanece falso. `system_intent.py` e o contrato reconhecem a expressão não qualificada `abra a porta` como física, não como nome de aplicativo. `TheoryOfMindEngine` usa a intenção estruturada explícita como evidência para ponderar e renormalizar a distribuição, mantendo as decisões subsequentes, os bloqueios físicos e a autoridade independente; não foi inserido retorno direto forçado de GO. `htn_planner.py` passa a reconhecer a variante `abre`. Isso é uma regra determinística para pedidos inequívocos, não prova de compreensão semântica geral; aplicações e objetos desconhecidos ainda podem ser ambíguos.

No diagnóstico após a alteração, `abra o paint` preservou o alvo e ToM retornou `GO_AUTHORIZED` com probabilidade operacional 0,5125; esse enum é uma decisão do ToM, não substitui o token exigido por `execution_authority`. O caminho de pergunta `como abrir o paint?` continua usando o canal conversacional existente no Kernel; ToM isolado, por si só, pode retornar GO para perguntas ou negações, portanto consumidores que o chamem fora do fluxo do Kernel não devem assumir proteção completa. A frase composta é identificada como COMPOUND; execução composta real não foi validada.

## Versão e reinicialização

Em duas consultas CIM não foi encontrado processo Python com linha de comando BRAINNET.py. A instância observada em missão anterior não estava identificável nestas consultas. Portanto não se pode calcular hash dos módulos carregados nem concluir que uma instância atual use versão antiga; outros tipos de inicialização não foram excluídos. A string BRAINNET v7 existe no cabeçalho/prompts atuais e, isoladamente, não identifica a versão do código. Não foi reiniciado ou encerrado processo.

Para reiniciar supervisionadamente: salvar trabalhos e estado na interface, confirmar com o usuário que nenhuma tarefa está em andamento, registrar logs e hashes atuais, encerrar pela interface de forma controlada, confirmar saída do processo e iniciar pelo procedimento habitual. Somente então repetir o comando acompanhado de monitoramento visual; não executar automaticamente nesta missão. O inicializador deve ser revisado antes, pois anteriormente continha reinício do Ollama.

## Testes

Sintaxe AST de system_intent.py, parser_contract.py, theory_of_mind.py, htn_planner.py e teste novo: OK. `test_v951_intent.py`: 7 passaram em 0,63s, incluindo oito entradas por parametrização, distribuição uniforme e teste simulado intenção → ToM/rota → proposta HTN → token simulado → executor/verificador mocks. Esse teste não executa o ciclo completo de `BrainnetBridge` nem comprova UI ou resultado factual em Paint. Seleção auditada anterior + teste novo: 191 testes e 46 subtestes aprovados, zero falhas/ignorados, 5,41s. Logs `V9_5_1_FOCUSED_TESTS.log` e `V9_5_1_REGRESSION_TESTS.log`; suíte completa não foi executada. Teste com distribuição uniforme não demonstra recuperação após exceção interna do motor FHRR.

Checkpoints pré-alteração: `development_logs/checkpoints/v951_20261111/`. Não houve alterações em bancos, nem teste de GUI, mouse, teclado, modelo ou serviço. Correção em produção permanece não confirmada até teste supervisionado após reinicialização.
