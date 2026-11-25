# Retomada ChatGPT · P55.1 (revisão, não instalada)

Base remota do Codex: 115c92ccaa0c1178d2d302abb6c5401dcb8d3e3e. A branch updates/local permanece nessa base; não foi promovido nenhum instalador. A última atividade local relatada inclui probes de GUI/Ollama, esclarecimento de aplicativo, ajustes de sincronização e conversation_router.py ainda não confirmados no GitHub. Não sobrescrever essas mudanças.

## Entrega
- BRAIN/browser_bridge_protocol.py: token obrigatório (64 caracteres hexadecimais minúsculos), comparação de tempo constante, resultado JSON limitado a 256 KiB, validação de envelope e ID.
- BRAIN/browser_bridge.py: servidor loopback falha fechado se BRAINNET_BROWSER_TOKEN não configurado, autentica antes de servir fila/heartbeat/resultado, remove CORS genérico, rejeita respostas desconhecidas ou expiradas, cria rota research_background sem abrir/focar navegador como fallback.
- EXTENSAO_NAVEGADOR: configuração manual do token em options, polling autenticado, rota RESEARCH_BACKGROUND somente leitura em aba inativa já pertencente à tarefa. Usa Google, não injeta em redirecionamento inesperado, não usa hitboxes nem mouse físico; preserva aba ativada ou movida pelo usuário quando detectado. Não contorna CAPTCHA.
- BRAIN/probe_browser_background.py: ensaio explícito Windows, banco descartável, não encerra processos existentes, compara aba ativa, cursor e foreground (amostras ~50 ms).

## Evidências
PASS_UNIT: python -m unittest -v test_browser_bridge_protocol, 4 casos; ambiente Linux isolado.
PASS_UNIT: node --test test_background_research.js, 5 casos, API Chromium simulada; node --check background_research.js passou.
Os Git blob SHAs dos quatro arquivos testados foram comparados com os blobs remotos e coincidiram: 6a9345787698ced6b4390462a8be4e652d60db46, 79742dd9e3583894ce0eec4413f44bd9b9fb2d27, 5d6e688fabeb7580f2cc33738c7503c5013e0375, 510250463b8b0689f478c6b1351ef0b0b3e0cb95.
NOT_TESTED: integração HTTP completa, Chrome/Thorium reais, Windows, inicialização pelo kernel, regressão completa. Não há prova de execução em background no computador do usuário nem de paralelismo. A nova rota ainda não está ligada ao planejador/chat. As rotas legadas que usam foco continuam distintas. Autenticação do token compartilhado não isola vários clientes autorizados; configurar apenas uma instância da extensão para o ensaio. Não há cancelamento remoto de ação já despachada.

## Continuação
1. Publicar checkpoints locais do Codex antes de integrar, sem reset ou sobrescrita de diferenças.
2. Revisar diff desta branch. Atualizar ponte Python e extensão conjuntamente, com backup; não instalar somente uma metade. O sincronizador atual autoriza apenas três destinos P0, não estes arquivos. Promover somente após ampliar política local revisada e manifesto com hashes de origem/destino.
3. Testes locais: python -B -m pytest -q BRAIN/test_browser_bridge_protocol.py; node --test EXTENSAO_NAVEGADOR/test_background_research.js; node --check EXTENSAO_NAVEGADOR/background.js; regressão safe-full.
4. Para prova real, fechar kernel/ponte atual, abrir navegador com extensão atualizada, configurar localmente um token aleatório com secrets.token_hex(32) no ambiente BRAINNET_BROWSER_TOKEN do PowerShell e na página de opções da extensão. Não compartilhar o token, não versionar nem imprimir em logs públicos. Rodar VENV/Scripts/python.exe -B BRAIN/probe_browser_background.py --run, sem mover o mouse ou trocar o foco durante a amostra. Se a porta 9876 estiver ocupada, não matar o processo automaticamente.
5. Verificar desconexão sem token, token errado, resultado rejeitado, pesquisa real com janela minimizada e preservação de aba. Se válido, integrar ao catálogo de capacidades e eventos de missão; tratar resultados de sites como dados e não instruções.
6. Retomar falha de alternância de conversas e esclarecimento somente a partir da versão local mais recente do Codex.
