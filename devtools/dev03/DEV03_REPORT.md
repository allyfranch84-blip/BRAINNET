# DEV-03 — resultado da implementação

Implementação na cópia Git, separada dos arquivos operacionais e da issue #2. Não houve instalação na raiz operacional, sincronização de árvores, alteração de arquivos operacionais, reinício de serviço, execução de launcher ou ação física.

A ferramenta valida manifestos explícitos contra base e commit Git, fonte limpa e hashes dos blobs, limita caminhos e cria prévia reproduzível. A aplicação exige `-Apply`, hash da prévia e confirmação interativa; bloqueia processos relevantes, guarda backups e manifesto antes de alterar, verifica SHA-256 e registra falhas parciais. O rollback confirma o destino, verifica backups e recusa sobrepor alterações posteriores.

Teste em árvores temporárias: `python -m unittest -v test_patch_control`: **15 aprovados e 1 ignorado, 0 falhas**, em 53,725 s. Cobertos prévia PowerShell, confirmação negada, inclusão e modificação, nomes Unicode, conflitos, hash, proteções, divergência de caixa, processos simulados, falha parcial, rollback e corrupção de backup. A criação de junction real foi ignorada por indisponibilidade de permissão; a detecção do atributo de reanálise foi testada simuladamente. O fluxo PowerShell `-Apply` completo com confirmação positiva e o detector real de processos não foram executados no ambiente operacional.

O teste motor virtual da issue #2 não prova movimento real nem foi implantado por esta tarefa. Nenhum resultado deste relatório demonstra funcionamento operacional real. Ver instruções e advertência sobre `taskkill` no README; a primeira implantação depende de revisão de manifesto/prévia e consentimento explícito.

## Revisão de segurança posterior

Uma tentativa adicional de criar junction em diretório temporário falhou com `Acesso negado`. O comportamento de junction real continua não verificado e permanece o risco de substituição concorrente entre verificações de caminho e escrita. Por isso, aplicação e rollback fora do diretório temporário estão explicitamente desativados no código, independentemente de confirmação. Esse bloqueio não deve ser removido sem validação Windows apropriada e revisão de segurança.

Reexecução após o bloqueio: 16 testes aprovados, 1 ignorado e 0 falhas (59,632 s). O bloqueio do caminho operacional também foi testado com o diretório temporário adulterado.

## Revisão do PR #5 — resolução de executáveis

O wrapper procura o Git independente embutido no GitHub Desktop, valida o executável e transmite seu caminho absoluto ao controlador. Python tenta `py -3.12`, a instalação padrão Python 3.12 e o PATH, com opções explícitas `-GitPath` e `-PythonPath`. Um teste Windows em árvores temporárias removeu Git e Python do PATH e isolou LOCALAPPDATA: Preview conseguiu usar o Git do Desktop 3.7.0 e o Python 3.12 sem iniciar serviços. Caminho explícito inexistente falhou de modo fechado. `py -3.12` não encontrou instalação registrada neste ambiente; o fallback foi usado. A suíte executou 20 testes: 19 aprovados, 1 ignorado (junction real indisponível), 0 falhas. Os quatro testes focados do wrapper foram repetidos com aprovação; o caminho explícito válido também foi retestado. O bloqueio de implantação/rollback operacional permanece.
