# V9.8-T2 — Deep Think visível

**Estado: integração parcial; critério de pensamento nativo não atingido.** O painel mostra eventos operacionais reais, não conteúdo interno do modelo. Nenhum texto de pensamento foi inventado.

## Modelos e backends

Foram consultados `/api/tags` nas portas Ollama 11434 e 11435 em leitura. No ambiente restrito as conexões retornaram WinError 10013; a consulta local fora desse ambiente expirou em ambas. Não foi possível obter lista de modelos e, consequentemente, `/api/show` por modelo nem confirmar capacidades `think`, níveis ou compatibilidade. Não se afirma que Ollama esteja parado; não foi iniciado ou reiniciado. O caminho conversacional efetivo usa `qwen2.5:1.5b` / Ollama conforme código, mas a instalação do modelo e suporte a pensamento não foram confirmados. `inference_backend.py` tem adaptador llama.cpp HTTP e valida template opcional como arquivo, mas não há extração de `reasoning_content` nem prova da configuração efetiva de servidor. Não foi iniciado llama-server.

O modo DEEP existente altera limites de geração e tempo; não foi conectado a thinking nativo porque suporte de modelo e servidor não foi demonstrado. Não se afirma aumento de inteligência ou raciocínio autônomo por aumentar limites.

## Alterações

- `BRAINNET.py`: eventos `aios:reasoning` com task_id, fonte, timestamp, estado e tipo em início/fim de tarefa, seleção efetiva de modelo no caminho conversacional, conclusão de inferência com duração e falha por tipo. O evento final contém snapshot de orçamento já existente. Não inclui prompt ou pensamento fabricado. Não altera autorização.
- `MasterShell_(1).jsx` do projeto externo: painel `<details>` inicialmente recolhido “PENSAMENTO PROFUNDO · etapas operacionais”, separado da resposta, com origem, horário, estado, modelo/backend e métricas disponíveis. Não exibe raw thinking. Dados ficam limitados a 50 tarefas e 20 eventos por tarefa; não são persistidos. Exibe indisponibilidade de conteúdo de pensamento. O seletor existente permanece.
- `test_v98t2_reasoning_events.py`: testa caminho real do Chat com transporte simulado, mesmos IDs, origem, falha e ausência de conteúdo de pensamento fabricado.

## Testes

`python -m unittest test_v98t2_reasoning_events -v`: 2 aprovados. `python regression_runner.py --suite safe-full`: 73 aprovados, 0 falhas, JUnit `development_logs/REGRESSION_20261112_204656_325632.xml`. `npm run build` no projeto externo passou: 1935 módulos, 7,33 s, JS principal 374,86 kB (118,89 kB gzip). Build não demonstra janela real, render, reconexão ou transporte PyWebView. Sem modelos reais, mouse ou teclado.

## Limitações

Não foram implementados seleção de capacidade via `/api/show`, `think`, níveis, coleta e exibição de thinking, separação de streaming misto, toggle de exibição de pensamento, nem testes desses contratos. Eventos de interpretação, recuperação, plano, hipóteses ou verificação não são emitidos por esta alteração e não devem ser inferidos do painel. Sucesso de inferência não significa verificação factual. Os eventos não são recuperados após reconexão; a janela real não foi observada e não há teste automatizado React para múltiplas tarefas ou reconexão. A interface registra apenas eventos recebidos, sem garantia de entrega. Próximo passo: consultar metadados de modelos quando endpoints estiverem acessíveis e testar política de compatibilidade com transportes simulados antes de habilitar thinking nativo, com limites e consentimento de exibição.
