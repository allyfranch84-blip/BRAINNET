# V9.8-T2.1 — Streaming de pensamento e resposta

**Estado: integração parcial, NÃO VERIFICADA com modelo real ou janela real.** Não foram confirmadas capacidades nativas nem garantida recuperação de fluxo após reconexão.

## Implementação

- `inference_backend.py`: `HTTPInferenceBackend.stream_events` acrescenta eventos estruturados THINKING, CONTENT e OPERATIONAL, preservando `stream` textual antigo. Para Ollama extrai `message.thinking` / `message.content` em chat e `thinking` / `response` em geração; para llama.cpp chat extrai `delta.reasoning_content` / `delta.content`. O evento final carrega fim/tokens quando reportados. Não ativa `think` nem presume que um modelo o suporte. Frames inválidos e fluxo sem conclusão produzem erro.
- `BRAINNET.py`: no caminho conversacional DEEP, o handler real consome `stream_events` do adaptador existente e publica `aios:stream` por `_push_event`, com task_id, message_id, sequência, canal, fonte, timestamp e estado. Somente CONTENT compõe resposta e histórico; THINKING não é inserido em memória factual. Reserva, orçamento e prazo existentes são verificados entre fragmentos. O caminho de seções usa ainda resposta completa. Exceção é comunicada como ERROR ou CANCEL_REQUESTED; não comprova interrupção de operação HTTP bloqueante.
- `MasterShell_(1).jsx` do projeto externo: durante execução mostra conteúdo parcial em componente separado; pensamento aparece dentro de painel recolhido e apenas quando o usuário marca “Mostrar pensamento recebido”. Armazena dados em estado por task_id/message_id, ignora duplicatas e detecta lacuna de sequência sem completar artificialmente. Eventos operacionais continuam em painel separado do texto de pensamento e resposta final. Limite de 50 tarefas no estado; não há persistência de thinking.

## Capacidades e limites

Consulta local a 11435 foi bloqueada neste ambiente com WinError 10013; em T2 consultas de metadados em ambas as portas expiraram fora do ambiente restrito. Nenhum modelo compatível foi identificado nem iniciado. O handler usa streaming de geração Ollama em DEEP; o parser llama.cpp e Ollama chat foram exercitados apenas por fixture e não conectam automaticamente outro backend ao Chat. Não há descoberta `/api/show` bem-sucedida nem validação de template em servidor real.

Não existe replay após reconexão: duplicatas dentro da sessão são ignoradas e uma lacuna é sinalizada, mas fragmentos perdidos não são recuperados. O transporte por `evaluate_js` não é transacional. Atualizações são por fragmento e ainda não há batching; respostas muito extensas podem causar renders excessivos. Cancelamento é cooperativo entre leituras; um readline bloqueante pode continuar até o timeout de transporte. Não é comprovado teste de cancelamento real durante I/O bloqueante. Não há teste integrado do transporte PyWebView até DOM ou teste de interface de reconexão/múltiplas tarefas; portanto não se declara cumprimento do critério completo.

## Validação

`python -m unittest test_v98t21_stream test_v98t2_reasoning_events test_v98t1_long_chat -q`: 15 testes aprovados. Incluem Ollama thinking/content intercalados, ausência de thinking, llama.cpp reasoning_content, cancelamento simulado em ambos canais, fluxo sem marcador e handler real com `_push_event` capturado e backend simulado. Isso não executa transporte JavaScript real e não prova reconexão. `python regression_runner.py --suite safe-full`: 73 aprovados, 0 falhas/erros/ignorados; JUnit `development_logs/REGRESSION_20261112_211154_290119.xml`. `npm run build` projeto externo: aprovado, 1935 módulos, 7,32 s, JS 376,30 kB. Nenhum modelo ou atuador real foi iniciado; execução da janela não foi observada.

Pendente: teste automatizado ponta a ponta PyWebView/React com eventos simulados, replay sequenciado e recuperação após reconexão, batching, cancelamento confirmado de I/O, descoberta de capacidade e validação supervisionada com modelo compatível já disponível. Não declarar comportamento real até essa validação.
