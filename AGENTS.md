# BRAINNET — orientações para Codex

## Diretórios e fontes de verdade
- Projeto executado pelo usuário: `A:\BRAINNET`.
- Cópia versionada: `A:\BRAINNET\BRAINNET`; não presumir que editar uma cópia altera a outra.
- Kernel: `BRAIN/BRAINNET.py`; GUI real: `INTERFACE DE USUARIO/BRAINDET IU/project/src/components/MasterShell_(1).jsx` (não `project/project`).
- Nunca sincronizar árvores inteiras nem sobrescrever arquivos operacionais sem inventário, backup e aprovação específica.

## Mudanças seguras e verificáveis
- Preferir correções mínimas nos contratos existentes em vez de novos orquestradores ou bibliotecas pesadas.
- UIA/Win32 antes de VLM; medir latência; leitura de tela não concede autorização para clicar ou digitar.
- `OBSERVED` exige evidência real. `EMPTY`, `UNAVAILABLE`, `INCONCLUSIVE`, `SIMULATED` e `GOAL_VERIFIED` são estados diferentes.
- Separar testes mockados, atuador virtual, observação real e execução física. Nunca relatar teste simulado como funcionamento físico.
- Não executar `iniciar/iniciar_aios.bat` automaticamente: ele encerra processos Ollama e inicia serviços.
- Não executar clique, teclado, drag, `taskkill`, restart de Ollama/Kernel/Vite ou captura de conteúdo privado sem autorização contextual específica.
- Não modificar `BRAIN/brainnet_config.json`, `.env`, bancos, modelos, ZIM, credenciais, logs pessoais nem dados fora do versionamento.
- Alterar apenas o necessário em branch de revisão, rodar testes focalizados e regressão segura quando possível; registrar testes ignorados e falhas de ambiente sem escondê-los.
- Não fazer push, merge na main, force push ou instalar arquivos em `A:\BRAINNET` sem autorização explícita.
- Ao concluir: indicar arquivos/linhas alterados, comandos e resultados de testes, evidência factual, limitações, risco e próximos testes manuais.

## P1 — leitura UIA
- Comando seguro `/uia scan <HWND> <PID>`: janela externa explicitamente indicada, identidade revalidada antes/depois, contagem/tipos/retângulos limitados; não exibir nomes/textos de controles por padrão.
- `/uia scan` sem alvo não deve inferir que a MasterShell ou foreground corresponde à intenção do usuário.
- A primeira leitura pode levar mais tempo por inicialização de Python; separar latência do provedor da duração total do processo.
