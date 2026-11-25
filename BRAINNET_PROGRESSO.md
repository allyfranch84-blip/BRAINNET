# BRAINNET — registro de desenvolvimento

## 24/11/2026 — primeiro fluxo de projeto verificável

- Branch de revisão `codex/brainnet-capabilities`, a partir da base GitHub `7119d7ab6c861c211a14507ad0196afafdaeda9c` com o patch anterior de intenção reaplicado em `bbe0ae2`.

## Marco verificado — Chat, projeto, código e pesquisa

- O Chat do kernel mínimo esclareceu “Faz um jogo d corida” em duas respostas e criou `index.html`, `game.js` e `README.md` numa pasta descartável. O motor passou em estado inicial, aceleração/direção, chegada e reinício no Node.js. A extensão do fluxo atual é o protótipo auditado 2D de navegador.
- Num teste de integração independente, o Edge headless carregou o protótipo com perfil descartável e verificou Canvas, eventos de teclado enviados pelo teste, chegada e reinício. Um erro de asserção real no Node.js também acionou uma correção explícita e passou na segunda tentativa, em diretório novo.
- Timeout de verificação agora retorna `INCONCLUSIVE`. A API antiga exige verificador explícito. A bancada executa somente código de teste ou do protótipo auditado.
- `/codigo mapa` devolve resumos AST dos módulos selecionados, com dependências, referências por linha e SHA-256. `/pesquisa Wikipédia Alan Turing` consultou a API pública a partir do Chat e retornou links com IDs de páginas. Google, WhatsApp, Excel, YouTube, Paint, AutoCAD e Photoshop seguem na fila de integração real.
- Abertura de aplicativos aceita erro limitado em nomes conhecidos e pede esclarecimento diante de alternativas. Ao usar inventário dinâmico, a verificação compara o caminho do executável e a identidade do processo, como atestado em teste simulado. O ensaio não usou cursor físico.
- WMI passou a ser carregado sob demanda pelo módulo de governança. O kernel mínimo foi instanciado pelo teste de contrato em Windows.
- Modelo local 1,5B real em CPU via llama.cpp e servidor temporário de propriedade do ensaio. O modo de resposta JSON passou de 1/4 para 2/4 casos, com prazo por caso ampliado de 20 s para 30 s. O pedido com erro de grafia passou em 20,375 s e a sequência em 2,391 s. Negação e pergunta ainda foram mal classificadas pelo modelo e barradas pelo parser/validador, antes de qualquer despacho. Prontidão em 5,094 s e encerramento do processo temporário confirmado. Repetir com `BRAIN/probe_real_motor_pipeline.py` e caminhos locais elegíveis.
- Primeira bateria após integração: **130 passaram, 1 ignorado** (modo de rede desativado). A consulta Wikipedia passou separadamente com modo de rede ativado. O pytest terminou com código zero e emitiu o aviso de limpeza conhecido do `pyreadline3`.
- Regressão final: **199 testes e 20 subtestes aprovados em 7,93 s**, com Edge e Wikipédia ativos. Um benchmark opcional de GPU ficou fora da seleção por depender de um arquivo ausente na cópia. `/checkup` conferiu PID e RAM reais do Windows sem exigir WMI.

### Reprodução e próximos passos

1. No worktree, entre em `BRAIN` e execute `python -B -m pytest -p no:cacheprovider -q test_capabilities_chat_e2e.py test_engineering_project_loop.py test_code_summary.py test_intent_grounding.py test_dynamic_app_inventory_route.py`. Use `BRAINNET_TEST_HEADLESS_EDGE=1` e `BRAINNET_TEST_WIKIPEDIA=1` para as provas opt-in.
2. Concluir benchmark do parser local e distinguir sintaxe JSON, interpretação, aterramento e verificação. Medir latência antes de ampliar escopo.
3. Ligar um executor isolado para requisitos fora do protótipo, com resultados verificáveis e continuidade em disco. Depois medir transferência de habilidades entre dois aplicativos e comparar recuperação lexical com FHRR/GHRR.
4. Testar canais de pesquisa e automação independentes antes de paralelizar interfaces gráficas. Atribuir cursor, sessão ou contexto de navegador explicitamente e medir custo por tarefa concluída.

### Retomada para outro modelo

1. Execute `git status --short --branch` e `git log -3 --oneline` no worktree da branch de revisão. Use o registro abaixo para distinguir o estado validado da instalação em `A:\BRAINNET`.
2. Comece pelos casos falhos do parser real já registrados acima. O alvo imediato é devolver `none` em perguntas e negações e reduzir a latência a frio com um prompt menor e contrato estruturado, mantendo o validador e medindo os mesmos quatro casos. O probe reproduz a bancada com um GGUF pequeno já instalado. Nenhum estudo de desempenho dá autorização a ações físicas.
3. Preserve o caminho curto de Paint, Bloco de Notas e Calculadora para pedidos únicos e inequívocos. O teste garante zero chamadas ao modelo e passagem pelo executor existente. Nomes dinâmicos ainda precisam de inventário e verificação de processo.
4. Depois do parser, conectar execução isolada para projetos fora do protótipo 2D e provar a retomada de uma tarefa interrompida. Testar busca em fontes e transferência de uma habilidade em dois aplicativos antes de ampliar memória ou interface.
5. Em testes longos, verificar a cada 3 s inicialmente. A partir da décima checagem, aumentar gradualmente até 30 s. Anotar primeiro erro, correção, comando, resultado e commit. Publicar somente arquivos revisados.

## Aprendizado motor — abstração de experiência

- `/memory concept <ID>` converte um recibo histórico em etapas conceituais e requisitos de revalidação, sem parâmetros de replay. Testes usaram SQLite real descartável com observações simuladas. Seleção inicial: 25 passaram, 1 ignorado (rede opt-in).
- Próximo ensaio: obter recibo de um efeito motor observado, recuperar o conceito e aplicá-lo a uma segunda interface com nova autorização e verificação. Paralelismo de pesquisa e cursores requer ensaios distintos.
