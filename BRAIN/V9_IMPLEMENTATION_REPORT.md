# BRAINNET V9 — relatório de implementação

## Escopo e evidências

Trabalho parcial de estabilização realizado sem executar pytest, movimentos reais, modelos, serviços ou o inicializador. O diretório não é um repositório Git detectável; portanto não há diff histórico confiável para atribuir alterações anteriores. A baseline e a saída dos testes estão em `V9_BASELINE.md` e `V9_BASELINE_TEST_OUTPUT.txt`.

## Alterações

- `execution_authority.py`: trajetórias exigem autorização explícita ou herdada válida; revogação e execução em background são respeitadas. O limite de comando cria autorização apenas na entrada apropriada.
- `BRAINNET.py`: a entrada `send_command` estabelece o escopo de autorização; negação explícita de abertura é reconhecida; inicialização de alvo literal corrigida; etapas compostas não avançam diante de estados inconclusivos e cancelam a espera em timeout; sete URLs de geração passam a usar a configuração central.
- `system_intent.py`: variante “abre” para abertura literal, mantendo recusa de prefixos negados.
- `ui_tars_protocol.py`: texto livre inválido não é convertido automaticamente em clique por OCR.
- `actuator_bridge.py`: exclusividade do cursor permanece até o trabalho físico terminar mesmo quando a tarefa assíncrona é cancelada. Uma operação nativa que nunca retorna pode manter o bloqueio indefinidamente.
- `vision_eye.py`: URL padrão centralizada, com override específico preservado; retenção configurável por `BRAINNET_VISION_KEEP_ALIVE`, padrão `5m`, e `0` para descarregamento imediato.
- `engineering_agent.py`: classificação determinística de erros e aplicação automática de correções desativada; falhas exigem revisão. Outros métodos antigos que criam arquivos ou executam processos não foram isolados ou acionados.
- `parser_contract.py`: função isolada `analyze_literal_intent` produz intenção estruturada conservadora, incluindo negação, ambiguidade e contexto necessário; nunca concede autorização. Ainda não foi ligada ao Kernel.
- `test_v9_safety.py`: testes simulados das alterações, sem ações reais.

## Testes

- `python -m unittest test_v9_safety test_homeostasis -q`: 21 aprovados, nenhuma falha. O loop assíncrono do Windows exigiu execução fora da restrição de rede local; não foi utilizado pytest.
- Baseline selecionada de regressão: 141 testes, 136 aprovados, 1 falha e 4 erros. A falha preexistente compara `READY_FOR_UIA` com `ACTION_BLOCKED`; os quatro erros são chamadas diretas sem token.
- Comparação de regressão antes do último teste adicional: 152 testes, 141 aprovados, 1 falha e 10 erros. Os seis erros adicionais são testes antigos que chamam o controlador visual diretamente sem autorização, agora recusados. Eles exigem revisão dos cenários e configuração explícita de autoridade; não foram alterados para mascarar resultados. Consulte `V9_FINAL_TEST_OUTPUT.txt`. A suíte inteira do projeto não foi executada.
- O teste antigo baseado em pytest `test_vision_sends_image_schema_and_unloads_model` espera descarregamento por padrão; a nova retenção padrão de 5 minutos é incompatível com essa expectativa. Não executado; configurar `BRAINNET_VISION_KEEP_ALIVE=0` preserva o comportamento anterior.
- A verificação AST inicial encontrou zero erros de sintaxe entre 172 arquivos Python na raiz; `_fix_ui_tars.py` emitiu aviso de escape inválido.

## Medição local limitada

Medição sintética após alterações, 1000 iterações: parsing visual mediana 0,0211 ms, p95 0,037 ms; alvo literal mediana 0,0069 ms, p95 0,0079 ms; classificação de erros mediana 0,0011 ms, p95 0,0012 ms. RSS do processo de medição: 30,79 MiB. Não há comparação anterior equivalente nem medição de VLM, carregamento de modelo, VRAM, UIA ou desempenho final; estes números não demonstram aceleração em produção.

## Pendências e limites

- Persistem as falhas e erros acima: a integração ponta a ponta não está validada. Não foi demonstrado desenho no Paint nem sucesso factual visual.
- O classificador compacto aprendido, sua avaliação com dados rotulados confiáveis, consolidação de conceitos estruturados, integração de aprendizado e demais lotes da missão não foram implementados. `hd_web_memory` contém 768 registros, mas não foram identificados rótulos confiáveis de utilidade. Nenhum esquema SQLite foi alterado.
- `semantic_layer.py`, `cognitive_orchestrator.py` e `signal_collector.py` não foram encontrados; não foram recriados. O gerenciador de residência existente não foi conectado automaticamente.
- A inicialização real, o roteamento entre modelos, o controle de processos e o custo de VRAM não foram testados. O inicializador foi apenas inspecionado: ele reinicia o Ollama, logo não foi executado.
- Recomenda-se primeiro revisar os testes de autorização e os chamadores diretos, sem enfraquecer o default-deny; depois confirmar UIA e objetivo visual em testes simulados, avaliar um classificador com rótulos confiáveis e integrar novos contratos progressivamente. Qualquer teste de desktop ou modelo real requer etapa própria supervisionada.

## Missão V9.0.6 — integração de autorização

### Diagnóstico individual

Os seis erros adicionais eram chamadas diretas a `UIProtocolController.run_task`, protegida por `authorized_trajectory`, sem `authorization_scope` no teste chamador. O token deveria estar ativo no contexto antes de `asyncio.run`, para propagação à tarefa e aos simuladores:

1. `test_controller_verifies_explicit_canvas`: execução autorizada de verificação do canvas.
2. `test_controller_without_identified_canvas_is_unverified`: mesma entrada, com canvas desconhecido.
3. `test_confirmed_goal_requires_callback_and_observed_action`: mesma entrada, com confirmação simulada.
4. `test_finished_without_goal_check`: mesma entrada, sem callback de confirmação.
5. `test_high_ncd_does_not_confirm_goal`: mesma entrada, evidência NCD isolada.
6. `test_scroll_dispatch_in_controller`: mesma entrada, envio simulado de scroll.

Os cinco problemas anteriores eram a falha `test_host_context_and_grounded_but_blocked` (espera `ACTION_BLOCKED`, recebe `READY_FOR_UIA`) e quatro erros nos testes `test_drag_releases_button_on_failure`, `test_drag_routes_to_effector`, `test_trajectory_drag_primitive_alias` e `test_trajectory_drag_validates_window_before_dispatch`: eles também simulavam execução autorizada sem token. Nenhuma asserção foi alterada. Os dois grupos de testes receberam escopo e token explícitos de teste; há testes negativos separados que mantêm bloqueio sem autorização ou com token revogado.

### Fluxo e correções

`send_command` estabelece escopo no limite de comando; tarefas asyncio herdam contexto, `dispatch` armazena o token com o item, o worker o reinstala e `asyncio.to_thread` transmite o contexto à thread física. UIA revalida o token antes da operação. O decorador da trajetória não cria token: agora revoga também o token herdado quando a tarefa é cancelada. A ponte revoga o token ao cancelar um envio e no instante do prazo de execução, antes de aguardar o término da operação nativa; ações pendentes são recusadas ao verificar novamente o token após a fila e o bloqueio do cursor. Ao sair do escopo de ociosidade o token também é revogado. Caminhos de timeout no Kernel revogam o token e solicitam cancelamento; a resposta informa que a conclusão ainda não está comprovada.

Arquivos alterados nesta etapa: `execution_authority.py`, `actuator_bridge.py`, `BRAINNET.py`, `test_ui_tars_protocol.py`, `test_v9_safety.py`, este relatório e `V9_0_6_TEST_OUTPUT.txt`. `uia_control_executor.py` foi inspecionado, sem alterações.

### Validação

- Testes focados `python -m unittest test_v9_safety test_ui_tars_protocol -q`: 38 aprovados.
- Seleção comparável em `V9_0_6_TEST_OUTPUT.txt`: 156 testes, 155 aprovados, uma falha e nenhum erro. Baseline original: 141 testes, uma falha e quatro erros; primeiro lote: 152 testes, uma falha e dez erros. As quantidades diferem porque novos testes foram acrescentados.
- Testes novos simulam cancelamento com operação nativa já em curso e outra aguardando o bloqueio, timeout com operação ainda ativa, revogação de trajetória herdada e manutenção da exclusividade até encerramento do worker. Sintaxe dos arquivos alterados verificada via AST. Nenhum pytest, mouse, teclado, aplicativo ou modelo real foi iniciado.

### Limitações restantes

A falha preexistente `READY_FOR_UIA` versus `ACTION_BLOCKED` permanece sem alteração. Revogar impede novos despachos após a próxima checagem, mas não desfaz uma chamada nativa ou COM já iniciada; a ponte preserva o lock até ela retornar e pode permanecer bloqueada se não retornar. A confirmação de cancelamento não é inferida apenas de `Future.cancel()`. A seleção não cobre toda a suíte, nem demonstra comportamento real de dispositivos ou todo chamador externo. O comportamento do escopo de ociosidade existente, que autoriza após inatividade, não foi ampliado; a política de sua utilização permanece assunto separado.

## Missão V9.0.7 — regressão e intenção

`ContextualGrounder.resolve` devolve `READY_FOR_UIA` ao identificar alvo com propriedades UIA suficientes; isso ainda não executa nem autoriza atuação. `BrainnetBridge` encaminha ao `ActuatorBridge`, que exige token e exclusividade; `uia_control_executor` revalida janela, processo, atividade humana, alvo e autorização antes da operação, e o efeito é verificado separadamente. A asserção antiga que exigia `ACTION_BLOCKED` na descoberta foi corrigida: o teste continua exigindo nenhuma ação executada e nenhuma experiência elegível para consolidação. Não se trata de comprovação de atuação real.

`SelfInspector.check_for_changes` chama pytest quando detecta mudanças Python e, se falhar, restaura modificados e remove adicionados; na primeira execução grava apenas histórico. Não foi encontrado processo Python ativo no levantamento de processos e nenhum Kernel foi iniciado. O inspetor, seu histórico e sua configuração não foram alterados. Não há garantia contra outra pessoa iniciar o programa concorrentemente depois da verificação.

`BrainnetBridge.send_command` chama `analyze_literal_intent`, expõe `intent_contract` no resultado normal e usa sua sinalização de negação junto à verificação preexistente de comando inicial; a classificação jamais concede autoridade. O roteamento anterior permanece responsável pela execução, leitura, UIA e esclarecimento. Pedidos compostos conhecidos são marcados ambíguos em vez de atribuir a frase inteira ao nome de um aplicativo. Os seis pedidos solicitados foram testados no ponto de entrada com o despachante simulado; isso não comprova a execução final em aplicativos reais.

Arquivos modificados: `BRAINNET.py`, `parser_contract.py`, `test_paint_app_context.py`, `test_v9_safety.py`, este relatório e os registros `V9_0_7_PYTEST_OUTPUT.txt` e `V9_0_7_UNITTEST_OUTPUT.txt`.

Pytest real, plugins automáticos desativados e cache desativado: `python -m pytest -q -p no:cacheprovider test_v9_safety.py test_paint_app_context.py test_ui_scene_graph.py test_passive_attention.py test_adaptive_resource_controller.py test_model_residency_manager.py test_inference_capability.py test_inference_backend.py test_canvas_goal_simulated.py test_uia_property_read.py test_contextual_grounder.py`: 135 aprovados, 32 subtestes aprovados, 0 falhas, 0 erros, 0 ignorados, duração pytest 3,26 s. A seleção anterior de unittest foi repetida: 158 aprovados, 0 falhas, 0 erros, duração 1,611 s; a seleção anterior tinha 155 aprovados e uma falha em 156 testes, com dois testes acrescentados agora.

A suíte pytest completa NÃO foi executada: por exemplo, `test_causal_trajectory.py` contém testes pytest assíncronos que iniciam subprocessos Tkinter (linhas 102 e 170); unittest não coleta essas funções. Outros arquivos usam subprocessos, rede e interfaces e ainda não foram totalmente auditados ou isolados. Desativar plugins também impede presumir que testes assíncronos seriam executados corretamente numa suíte completa. Próximo bloqueador: isolar e revisar esses testes, configurar suporte assíncrono controlado e então validar a suíte restante sem atuação ou efeitos externos. Não foram executados aplicativos reais, modelos, mouse ou teclado.

## Missão V9.0.8

Registro de desenvolvimento e auditoria parcial criados em `development_logs/`; detalhes, medições, riscos e resultados em `V9_0_8_MULTIMISSION_REPORT.md`. Seleção pytest: 138 aprovados e 32 subtestes, 3,89 s; suíte completa não executada. Falha silenciosa de resumo longo foi corrigida; ledger de proveniência é experimental em memória, sem integração automática. Residência e NCM foram apenas auditados, sem testes reais de modelos ou treinamento.

## V9.0.9 / V9.1

Fundação experimental de memória situacional, leitura opt-in no roteador e manifesto/plano de instalação simulada criados. Seleção segura: 145 aprovados, 32 subtestes, 3,69 s. A memória não está ligada ao ciclo do Kernel; não há persistência automática nem medição real de RAM. Kernel sem modelos opcionais e instalação portátil ainda não foram comprovados. Inventário e limites em `V9_ARCHITECTURE_AND_PORTABILITY_PLAN.md`.

## V9.1-HDC

GHRR recebeu desassociação explícita à esquerda/direita e geração aleatória sem repetição, preservando `unbind` e rótulos legados. Incluído índice FHRR isolado e validação estrutural de blob GHRR. Seleção simulada: 150 testes e 32 subtestes aprovados, 4,07 s. A integração ao Kernel e ao P-DAG permanece incompleta; detalhes e riscos em `V9_FHRR_GHRR_INTEGRATION_REPORT.md`.

## V9.1-COMPREHENSION

Inventário parcial de modelos, índice AST read-only, intérprete conservador e protótipos isolados de livro/vídeo criados. A seleção segura teve 156 testes e 46 subtestes aprovados, 4,28 s. Os protótipos não estão integrados ao Kernel nem demonstram execução real. Detalhes e bloqueios em `V9_COMPREHENSION_REPORT.md`.

## V9.1.1

Arqueologia do extrator de legendas concluída parcialmente; QFHRR v2 com máscara, consolidação H-Mem não destrutiva opt-in, proposta GHRR e flag experimental de memória adicionados. Nenhum teste foi executado, por instrução expressa; apenas sintaxe AST. A integração ao Kernel é parcial e não validada. Detalhes em `V9_1_1_INTEGRATION_REPORT.md` e `V9_YTDLP_RECOVERY_REPORT.md`.

## V9.1.3

A rota sintática quando injetada agora produz apenas proposta sem passos motores e a consulta visual JSON respeita keep_alive configurável. Regressão auditada: 164 testes e 46 subtestes aprovados em 4,68s; suíte completa não executada. Orquestrador, integração da memória e residência ativa continuam pendentes. Evidências e limitações em `V9_1_3_GAP_REPORT.md`.

## V9.1.4

Leitura situacional opt-in alimenta contexto do roteador e resultado visual verificado gera evento; proposta GHRR aproximada permanece isolada e nunca autoriza. Servidor Ollama usa modelos em C: apesar da variável da sessão apontar A:. Testes seguros: 167 aprovados e 46 subtestes em 4,35s. Integração completa, orquestrador e visão ROI ainda pendentes; detalhes em `V9_1_4_INTEGRATION_REPORT.md`.

## V9.2

Protótipo BookDraft registrou falha, retomada e verificação estrutural simulada; gate consultivo de revisão adicionado sem aplicação de patches. Seleção segura: 170 testes e 46 subtestes, 4,86s. Planejamento contínuo no Kernel e isolamento de código não confiável continuam pendentes. Detalhes em `V9_2_ADAPTIVE_AUTONOMY_REPORT.md`.

## V9.3

Hipóteses conceituais limitadas foram conectadas ao `send_command` em modo observacional desativado por padrão. Seleção segura: 176 testes e 46 subtestes aprovados, 4,91s. Planejamento contínuo, composição e aprendizagem de estratégias não foram integrados. Ver `V9_3_COGNITIVE_EVOLUTION_REPORT.md`.

## V9.4

Pack QFHRR vetorizado com preservação de bytes em testes; mediana sintética 3,605 → 0,0749 ms. Habilidades cristalizadas passam a reportar proposta sem execução nos consumidores existentes. Seleção segura: 180 testes e 46 subtestes, 4,79 s. Rust e inferência direta em processo não foram implementados; detalhes em `V9_4_RUST_INFERENCE_REPORT.md`.

## V9.5

Consulta P-DAG de proposta verificada sob flag, sem autorização de execução; verificação opcional SHA-256 antes de iniciar llama-server. Seleção segura: 184 testes e 46 subtestes aprovados, 5,03s. O critério ponta a ponta não foi alcançado; a instância existente não foi reiniciada. Ver `V9_5_FUNCTIONAL_INTEGRATION_REPORT.md`.

## V9.5.1

Diagnóstico reproduziu esclarecimento de `abra o paint` no ToM, que ignorava o alvo preservado pelo contrato. Contrato estruturado passou a informar OPEN_APP e evidência alimenta a distribuição ToM; porta física e variante `abre` tratadas. Seleção segura: 191 testes e 46 subtestes aprovados, 5,41s. Nenhuma instância BRAINNET identificada nas consultas; produção ainda não validada. Ver `V9_5_1_INTENT_REPAIR_REPORT.md`.

## V9.5.2

Preservação parcial da última tarefa operacional, diagnóstico de falha em RAM, limite de repetição para formato e enumeração MSS foram implementados. Regressão simulada: 198 testes e 46 subtestes aprovados, 5,55s. Persistência, numeração Windows e factualidade histórica permanecem pendentes. Ver `V9_5_2_RELIABILITY_REPORT.md`.
