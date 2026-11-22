# V9.8-K1 — Kiwix e consulta ZIM offline

**Resultado: instalação portátil e consulta documental inicial implementadas; integração completa com síntese e memória permanente ainda parcial.**

## Instalação e fontes

[Kiwix Desktop](https://github.com/kiwix/kiwix-desktop), distribuição oficial Windows x64 2.5.1, foi baixado para `A:\BRAINNET\tools\kiwix-desktop` e extraído como aplicação portátil; executável `kiwix-desktop.exe`. O arquivo ZIP tem 157.265.310 bytes e SHA-256 `56ad5b3a86010c2c74db63a717d087cfbdcdbe71a0d7fca0655f90ef1d80593f`, calculado localmente; não foi comparado a checksum assinado do fornecedor. Não foi instalado no registro do Windows nem iniciado, e não se afirma validação visual do aplicativo.

[python-libzim](https://github.com/openzim/python-libzim) 3.13.1 wheel CPython 3.12 Windows x64 foi instalado isoladamente em `A:\BRAINNET\vendor\kiwix`; o Kernel não precisa alterar o ambiente global. Não foi encontrado ZIM previamente no workspace. A amostra oficial do [openzim/zim-testing-suite](https://github.com/openzim/zim-testing-suite) `testdata/kiwix/small.zim` tem 78.970 bytes e SHA-256 `64e67613388b0fc7d86c289d55f8d2f3a378d7e8ac107297325d1370cebfb478`. É fixture sintética, não enciclopédia útil. Nenhum ZIM grande foi baixado.

## Caminho implementado

`kiwix_knowledge.py` usa libzim nativo, sem implementar leitor nem abrir rede: catálogo de ZIM de um diretório, sugestões por título, busca textual quando o arquivo dispõe de índice, leitura por caminho, extração limitada de texto HTML/plain, UUID e data do arquivo, e LRU em memória para até 32 consultas (padrão 16). O limite por artigo padrão é 1 MiB e o trecho 4000 caracteres. O tamanho é checado antes de obter conteúdo, mas libzim pode alocar buffers de descompressão adicionais: não foi demonstrado teto rígido de RSS para arquivos arbitrários. Arquivos ausentes/corrompidos são tratados; texto recuperado é dado não confiável, não instrução.

`BrainnetBridge._executar_comando_interno` aceita `/offline <consulta>` quando existe exatamente um ZIM em `A:\BRAINNET\knowledge\zim`; retorna trecho e referência, sem modelo ou acesso à internet. Se não houver arquivo ou houver vários, informa a limitação. A pasta de conhecimento está vazia por padrão; a fixture de testes não é adicionada automaticamente ao catálogo de usuário. A referência (arquivo, UUID, data, artigo, título, horário e rótulo UNVERIFIED_SOURCE_TEXT) é registrada no journal existente `development_logs/missions.jsonl`; se memória situacional estiver habilitada, uma observação não verificada é adicionada em RAM. Não foram modificados P-DAG, FHRR/GHRR ou SQLite. O journal é persistência de proveniência, não integração a H-Mem nem fatos verificados; não há síntese pelo modelo ou recuperação semântica conectada ao fluxo nesta etapa.

O Kernel e UI existentes não foram reiniciados; o código alterado será carregado quando o usuário decidir reiniciar de forma apropriada. Não há prova do comportamento na instância atualmente em execução.

## Validação

`python -m unittest test_v98k1_kiwix -v`: 5 aprovados; catálogo, buscas título e texto, leitura, persistência de referência em journal temporário, observação não verificada, erro de arquivo ausente/corrompido, limite de artigo, cache limitado e handler real do Chat com ZIM real de teste e transporte de rede bloqueado por mock. A resposta obtida incluiu `Test ZIM file` e referência `small.zim | A/main.html | 2020-11-15`. O mock de urllib não comprova bloqueio de todas as APIs de rede do sistema; a implementação de leitura não chama rede.

Regressão `python regression_runner.py --suite safe-full`: 73 aprovados, 0 falhas, JUnit `development_logs/REGRESSION_20261117_203617_575861.xml`. Um processo de leitura mediu catálogo inicial 98,60 ms; 50 consultas à fixture, p50 2,79 ms e p95 4,65 ms; RSS antes/depois 24.694.784 / 33.918.976 bytes. Não são pico de memória nem estimativa para ZIM grande. Dados `development_logs/V9_8_K1_BENCHMARK.json`.

## Pendências

Adicionar seleção de arquivo no Chat e teste com corpus real licenciado; conectar recuperação e síntese com citações e budget existente sem iniciar modelos; integrar referências à memória persistente de experiências existente sem qualificá-las como fatos; validar limites de descompressão e comportamento em arquivos grandes; build/distribuição que inclua opcionalmente libzim; verificar checksum do pacote com fonte independente; validação real do Kiwix Desktop. Não foi demonstrada síntese semântica nem consulta de conhecimento real ao vivo.
