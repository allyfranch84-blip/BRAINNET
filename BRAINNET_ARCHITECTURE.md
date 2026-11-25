# Caminhos conferidos na instalação

| Componente | Caminho efetivo e contrato |
|---|---|
| Interface | `INTERFACE DE USUARIO/BRAINDET IU/project/src/main.tsx` carrega a aplicação React. A MasterShell usa `window.pywebview.api` e o Chat envia comandos por `BrainnetBridge`. A cópia em `project/project` é independente. |
| Kernel mínimo | `BRAIN/BRAINNET.py` constrói o Kernel e a ponte. O perfil mínimo deixa o P-DAG persistente e o REM desativados. O processo de interface escolhe a URL pelo ambiente. |
| Inferência | O supervisor do Kernel usa a porta 11435 para Ollama. Um serviço externo com versão e catálogo válidos pode atender ao adaptador HTTP. A disponibilidade do serviço e uma geração concluída são observações distintas. |
| Conversas e notas | `workspace_chat_archive.py` e `workspace_notes.py` usam arquivos SQLite distintos sob LOCALAPPDATA. Os testes criam armazenamentos descartáveis. |
| Extensão | Manifest V3 e worker em `EXTENSAO_NAVEGADOR`. Há rotas que usam a aba ativa e abrem outra com foco. A ativação e a leitura de DOM em segundo plano ainda precisam de ensaio. |
| Motor | Entrada física passa pelo ActuatorBridge. O indicador de um comando na fila não demonstra uma ação física ou múltiplos cursores independentes. |
| Atualização | O cliente baixa a referência literal do canal. Um manifesto de versão 1 identifica os destinos e SHA-256 do texto com LF normalizado. Backups e verificação final usam os bytes reais. Cada tentativa de instalação cria um registro em `.git/brainnet-updates`. |
