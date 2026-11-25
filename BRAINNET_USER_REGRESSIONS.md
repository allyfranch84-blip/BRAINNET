# Relato de regressão funcional do usuário — 2026-11-25

Origem: teste manual do usuário na instalação operacional A:\BRAINNET. Os resultados individuais do questionário anterior não foram transmitidos integralmente; não inventar detalhes ou contagens. Os dez domínios abaixo foram explicitamente marcados como falhos. Não exigir repetição integral da bateria. Não confundir PASS_UNIT/PASS_INTEGRATION com PASS_REAL.

| ID | Domínio | Evidência / requisito | Estado |
|---|---|---|---|
| U01 | Conversação e compreensão | Domínio marcado como falho; qualidade DeepThink fraca | USER_FAIL |
| U02 | Negação e perguntas | Domínio marcado como falho; casos individuais ausentes | USER_FAIL |
| U03 | Notas e links | Links em texto não clicáveis; Markdown automático na visualização e salvamento requerido | USER_FAIL |
| U04 | Memória entre chats | Mais de um chat; memória permanente ao menos abstrata | USER_FAIL |
| U05 | Movimentos e geometria | Domínio marcado como falho; trajetórias individuais ausentes | USER_FAIL |
| U06 | Abertura de aplicativos | Domínio marcado como falho | USER_FAIL |
| U07 | Continuidade contextual | Domínio marcado como falho | USER_FAIL |
| U08 | Planejamento e DeepThink | Fraco; conteúdo aparece no topo e desaparece | USER_FAIL |
| U09 | Pesquisa internet | Domínio marcado como falho | USER_FAIL |
| U10 | Aprendizagem persistente | Domínio marcado como falho | USER_FAIL |
| U11 | Layout | Menu expansível, microfone e profundidade devem ficar no compositor; remover barra superior redundante | USER_REPORTED |
| U12 | Voz | Modo direto com interpretação/correção contextual e modo revisão editável; submenu > junto ao Mic ligado; ícone com cor de estado real | USER_REQUIREMENT |
| U13 | Latência | Não havia informação no chat durante teste de aprendizagem | USER_FAIL |
| U14 | Consumo | Não foi possível medir; operação sem engasgos relatada | UNMEASURED; USER_OBSERVATION_POSITIVE |

Recursos adicionais podem ser baixados com instruções claras e explicação de aplicação. Preferir recursos já disponíveis e armazenamento A:, preservar C: e junction Ollama. Não baixar modelos indiscriminadamente.

O relato pode preceder as mudanças locais do Codex de 25/11: a versão efetivamente executada no momento dos testes não foi registrada. Codex relatou prova real de /kernel status e criação/leitura de nota, timeout ao retornar à primeira conversa e teste de esclarecimento com despacho substituído. Essas evidências posteriores não anulam o relato nem comprovam resolução global.

Próximo passo: recuperar alterações locais inéditas por inventário de hashes e diff direcionado; não sobrescrever nem publicar bancos, conversas, configurações ou segredos. Priorizar falhas funcionais e reexecutar somente casos corrigidos. A P52.1 de seleção de modelos e a P55.2 de navegador são candidatas independentes, não correções instaladas.

## Evidências históricas recuperadas de conversa anterior
- Criação de nota em linguagem natural falhou; leitura de `[[teste 1]]` falhou.
- Movimento para cima funcionou na segunda tentativa.
- Quadrado de 100 px por lado, sem pressionar botão, teve quatro segmentos executados e verificados em um ensaio P48. Triângulo estava indisponível naquele ponto histórico (P49 posterior não comprova regressão ou aprovação atual).
- A bateria manual completa e suas marcações não foram recuperadas. Essas observações não representam a versão atual instalada; usá-las como casos históricos de regressão.
