# V9.8-K1.1 — Memória de fontes offline

**Resultado:** persistência e recuperação por referência demonstradas com fixture ZIM real em processos de teste separados. A biblioteca de usuário `A:\BRAINNET\knowledge\zim` não continha arquivos `.zim`; consulta documental com corpus real de usuário e instância ativa do Kernel permanecem pendentes.

## Integração

- `kiwix_knowledge.py`: a referência inclui arquivo, UUID e data do ZIM, tamanho e mtime, caminho e título do artigo, horário e estado `SOURCE_UNVERIFIED`. Relação conceitual registrada é apenas `ARTICLE_TITLE`, não uma afirmação semântica verificada. O texto continua marcado `UNTRUSTED` e não é armazenado integralmente no H-Mem.
- `record_reference` reutiliza `HMemEngine.record_episodic_node` para gravar episódio `kiwix_reference` com task_id como session_id; preserva o journal já existente e, quando habilitada, observação situacional não verificada. Não cria outro banco ou esquema cognitivo.
- `hmem_engine.py`: `get_episodic_node` recupera pelo node_id exato, usando a chave primária SQLite, sem busca semântica por similaridade. O método não promove o conteúdo a fato.
- `recall_reference` localiza episódio por ID e reabre diretamente o artigo no ZIM, sem executar nova busca por título ou texto. Verifica UUID, data, tamanho e mtime; ausências geram `SOURCE_MISSING`, alterações detectadas `SOURCE_CHANGED` e leituras falhas `SOURCE_UNAVAILABLE`.
- `BRAINNET.py`: H-Mem é instanciado sob demanda com o VSA existente, no primeiro uso; a seção crítica usa o lock situacional existente. `/offline termo` funciona para um único ZIM; `/offline arquivo.zim :: termo` seleciona um entre vários; a resposta inclui ID `HND_...` se o episódio foi gravado. `/offline-ref HND_...` recupera a mesma referência sem nova busca. Sem VSA/H-Mem, retorna fonte com aviso explícito de indisponibilidade de retomada por ID. Nenhum Ollama é necessário.

## Validação

`python -m unittest test_v98k1_1_memory test_v98k1_kiwix -v`: 11 testes aprovados. Todos os acessos ZIM usaram a fixture real de formato, sintética, `testdata/kiwix/small.zim`; nenhum usou enciclopédia de usuário. Um subprocesso independente escreveu o episódio e terminou; outro processo abriu o mesmo banco SQLite temporário e recuperou o artigo. Outros testes usaram o handler real de Chat com H-Mem temporário, confirmaram ausência/alteração do arquivo, rejeição de episódio alheio e texto não confiável; extração ignora conteúdo de tag script. Os testes bloquearam `urllib.request.urlopen` no caminho do Chat, mas isso não é um firewall para todas as APIs de rede; a leitura implementada não contém chamada de rede.

Regressão auditada `python regression_runner.py --suite safe-full`: 73 aprovados, zero falhas/erros/ignorados; JUnit `development_logs/REGRESSION_20261117_204322_920995.xml`. Sintaxe verificada. Testes não modificaram banco de produção; o processo Kernel atual não foi iniciado, encerrado ou reiniciado.

## Limitações

- Não há corpus real na biblioteca nem verificação em instância ativa; os comandos só ficarão disponíveis no processo que carregar o código alterado.
- UUID/data e atributos do arquivo são sinais de versão, não hash de integridade: uma modificação com tamanho e timestamp preservados pode não ser detectada. Não se afirmou verificação criptográfica do arquivo.
- O conteúdo não é checado contra a realidade nem transformado em fato verificado. Apenas o título é usado como rótulo conceitual; não existe extração de relações conceituais gerais ou síntese por modelo.
- H-Mem persiste em SQLite, mas políticas legadas de retenção/REM podem podar episódios; persistência após reinício de teste não comprova retenção permanente. Referências legadas gravadas apenas no journal K1 não foram migradas automaticamente.
- Identificação do arquivo é pelo nome no diretório configurado; mover/renomear o ZIM exige nova consulta. Não há seleção automática entre vários arquivos, somente sintaxe explícita. Cache e memória do libzim não têm teto rígido de processo para ZIMs arbitrários.
- O fluxo foi demonstrado com fixture sintética real e dependências de Kernel simuladas; não é prova de interação com GUI nem de consulta de conteúdo de usuário em produção.
