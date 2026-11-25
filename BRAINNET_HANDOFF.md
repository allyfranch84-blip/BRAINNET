# Continuidade operacional · 25/11/2026

Comece em `A:\BRAINNET`. A branch de revisão desta sessão é `codex/p51-operacao-segura`. A base do canal conferida diretamente no GitHub foi `7d718c1`. O primeiro marco de código validado é `c6ff506`.

P47, P48, P49 e P51.1 têm testes e componentes na raiz e diretórios de backup de instalação datados. Os testes das quatro fases passaram. Esses arquivos incluem mudanças locais anteriores, algumas fora do índice Git. Um checkout da branch isoladamente não reproduz toda a instalação. Preserve o gerador de destilação, as configurações e as diferenças locais. A continuidade histórica está em `BRAINNET/docs/BRAINNET_CONTINUIDADE.md`.

Leia `BRAINNET_TEST_REPORT.md`, `BRAINNET_NEXT_TASKS.md` e o último registro de `BRAINNET_SESSION_LOG.jsonl`. Use o Python de `VENV/Scripts`, que nesta instalação é 3.10.6. O launcher inicia serviços e não é um comando de diagnóstico.

O sincronizador novo usa `updates/release.json` no mesmo commit do payload e confere o hash de `updates/current.py`. Para verificar o canal, execute `VENV\Scripts\python.exe -B sincronizar_brainnet.py` na raiz. A prévia lê objetos Git e os três destinos P0. Para instalar em uma base compatível, revise os arquivos e use `--apply` seguido do SHA completo dessa prévia. Uma nova ponta exige nova revisão. O cliente anterior só conhece o instalador legado P51.1. A primeira adoção do novo cliente em outra instalação exige obter o arquivo do commit revisado. Cursos futuros devem declarar os arquivos e hashes e ampliar a lista local de destinos somente após revisão.

## Retomada remota ChatGPT (P55.1)
Nesta branch de revisão apenas, leia `BRAINNET_P55_REVIEW.md` antes de integrar. O canal `updates/local` não foi alterado nesta rodada. Não substituir as mudanças locais do Codex. Protocolo e pesquisa de fundo passaram em testes isolados; integração Windows pendente.
