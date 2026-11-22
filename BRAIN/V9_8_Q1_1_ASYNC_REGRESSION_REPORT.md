# V9.8-Q1.1 — Regressão visual e asyncio no Windows

**Resultado: TIMEOUT classificado e limitado; causa raiz ainda em investigação.** O executor central não fica preso indefinidamente no teste visual auditado. O teste em si não passou neste ambiente.

## Reprodução

`development_logs/V9_8_Q1_1_minimal.py` executa apenas importações da biblioteca padrão, registra threads e chama `asyncio.run(asyncio.sleep(0))`, em processo próprio com timeout de 8 s e faulthandler de 3 s. Política efetiva `WindowsProactorEventLoopPolicy`; `socket.socketpair` era `_fallback_socketpair`; somente MainThread existia antes de construir o loop. O processo foi interrompido pelo seu supervisor após TIMEOUT. A pilha `development_logs/V9_8_Q1_1_minimal.log` mostra `socket.accept` dentro de `_fallback_socketpair` chamado por `asyncio` Proactor ao construir o loop. Assim o bloqueio reproduz sem carregar protocolo visual, fixtures pytest ou o regression_runner. Não houve oportunidade de verificar o fechamento normal do loop nesta execução.

O teste `test_v98a_capability_lab.py::test_move_requires_authorization_and_independent_observation` trava na mesma pilha em `asyncio.run`, antes de executar sua coroutine. O trace direto anterior está em `development_logs/V9_8_Q1_visual_timeout.log`. O executor central agora registra o mesmo comportamento em `development_logs/REGRESSION_VISUAL_20261112_183054_674384.log`. Os dois caminhos classificam como TIMEOUT, não PASS. Não há evidência de que o protocolo visual cause o bloqueio. É plausível que a política de rede local do ambiente interfira com a conexão de socketpair, mas a causa de o accept não retornar não foi demonstrada; nenhuma regra de rede foi alterada.

## Alteração

`regression_runner.py`: novo modo `--suite visual-diagnostic` executa unicamente o teste mockado previamente auditado, em subprocesso próprio, com faulthandler após 4 segundos, prazo de 12 segundos e log/sumário persistentes. `subprocess.run` termina e aguarda seu próprio processo após o timeout; não visa serviços existentes. Status é PASS, FAIL, ERROR ou TIMEOUT. Não modifica socket, política asyncio global, autorização ou comunicação externa. Nenhum JUnit é fabricado após timeout.

`test_v98q1_1_diagnostic.py`: três testes simulados passaram, cobrindo classificação PASS/FAIL/ERROR, TIMEOUT com stack preservada e recusa de teste não auditado. Estes mocks não demonstram que uma rede externa foi bloqueada no sistema operacional.

## Resultados

- Antes: seleção direta e reprodução mínima travaram; pilha e encerramento limitado registrados.
- Depois: `python regression_runner.py --suite visual-diagnostic` retornou TIMEOUT com código de processo executor 1, log e JSON; subprocesso terminou sob o limite configurado. Não foi corrigida a criação real do loop neste ambiente.
- `python regression_runner.py --suite safe-full`: 73 aprovados, 0 falhas, 0 erros, 0 ignorados; JUnit `development_logs/REGRESSION_20261112_183111_633123.xml`; baseline não atualizada.
- Seis falhas visuais históricas permanecem referências não reexecutadas, não são declaradas corrigidas. Não foi demonstrado encerramento normal do loop real; testes de classificação são simulados. Nenhum desktop ou serviço foi manipulado; nenhum teste desta execução exige comunicação externa. Não foi realizada medição de tráfego de rede do sistema.

## Próximo discriminante

Investigar em processo isolado e ambiente controlado com conectividade loopback autorizada, sem abrir acesso externo: reproduzir somente `_fallback_socketpair`, confirmar connect/accept e limpar sockets, comparar com política restrita. Modificar infraestrutura de teste somente após identificar a restrição. Não substituir a política do Kernel nem desativar controles de rede preventivamente.
