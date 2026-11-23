# DEV-03 — implantação controlada de patches

O projeto operacional fica em `A:\BRAINNET`. A cópia Git fica em `A:\BRAINNET\BRAINNET`; atualizar a cópia Git não instala nada na pasta operacional. A ferramenta é opt-in. O modo padrão é prévia, sem alterações no destino e sem início/encerramento de serviços. **Aplicação e rollback em destinos reais estão desativados no código** até que a proteção contra junctions/reparse points seja validada em ambiente Windows apropriado e revisada; só são permitidos destinos temporários de teste.

## Três estágios

1. Desenvolver numa branch e revisar o patch; executar testes automatizados na cópia Git. O trabalho motor virtual da issue #2 é separado e não prova movimento real.
2. Após revisão, obter consentimento explícito para a implantação, atualizar a cópia Git e executar a prévia. Só depois de revisar caminhos, conflitos, hashes, riscos e local dos backups e aprovar o hash da prévia usar `-Apply`.
3. O usuário realiza o teste funcional manualmente, após conferir o aviso do launcher abaixo. Registrar evidências reais; usar rollback se necessário.

## Manifesto revisado

Salve o arquivo JSON **fora da cópia Git**. `base_commit` e `target_commit` são hashes Git completos de 40 dígitos; os arquivos devem corresponder exatamente ao `git diff --name-status --no-renames base target`, aceitando somente inclusões e modificações. Os SHA-256 referem-se aos bytes dos blobs Git da base e do alvo. Para uma inclusão use `null` em `before_sha256`. Conteúdo excluído, renomeações, divergências intencionais e arquivos não rastreados não são implantados.

```json
{
  "base_commit": "<40 dígitos hexadecimais da base>",
  "target_commit": "<40 dígitos hexadecimais do commit aprovado>",
  "files": [
    {"path": "BRAIN/exemplo.py", "before_sha256": "<SHA-256 da base>", "after_sha256": "<SHA-256 do alvo>"}
  ]
}
```

A ferramenta exige HEAD no commit aprovado, árvore Git limpa inclusive arquivos não rastreados e a base ancestral do alvo. Arquivos protegidos, extensões não permitidas, travessia, links/junctions e conflitos são recusados. Não faz `pull`, `reset`, remoção de arquivos extras, cópia integral nem ações motoras.

## Prévia, aplicação e rollback

No PowerShell, somente após revisão do manifesto:

```powershell
$tool = 'A:\BRAINNET\BRAINNET\devtools\dev03\Deploy-BrainnetPatch.ps1'
& $tool -Preview -Manifest 'A:\BRAINNET\BRAIN\development_logs\manifesto_aprovado.json'
```

A prévia informa arquivos, hashes atuais e novos, conflitos e hash da prévia. O seguinte comando está documentado para o futuro, mas será recusado para o destino real enquanto o bloqueio de segurança estiver ativo. Depois da validação de junctions e de **nova aprovação explícita do usuário** para aqueles arquivos e aquele hash:

```powershell
& $tool -Apply -Manifest 'A:\BRAINNET\BRAIN\development_logs\manifesto_aprovado.json' -PlanHash '<hash integral da prévia>'
```

O comando exige confirmação interativa digitando `APLICAR <hash>`; verifica processos relevantes e aborta se houver algum ativo ou se a consulta falhar. Não os encerra. Faz backups e registra manifesto antes de alterar arquivos; confirma os hashes finais. Uma falha parcial deixa um manifesto com estado explícito e identificador de implantação para inspeção e eventual rollback.

```powershell
& $tool -Rollback '<deployment_id>'
```

Rollback exige confirmação `ROLLBACK <deployment_id>`, ausência de processos relevantes, backups íntegros e ausência de modificações posteriores. Não force rollback de arquivos alterados depois; revise o conflito. Diretórios vazios criados durante a aplicação podem permanecer após rollback.

## Aviso antes do teste manual

O `A:\BRAINNET\iniciar\iniciar_aios.bat` atual contém `taskkill /F /IM ollama.exe` e `taskkill /F /IM "ollama app.exe"`, inicia `ollama serve` e abre Vites e Kernel. Ele pode interromper sessões Ollama existentes. A ferramenta não o executa; o usuário deve decidir quando iniciá-lo manualmente.

## Limites

O detector de processos usa `Get-CimInstance` e é conservador: bloqueia também Python/Node com linha de comando inacessível e qualquer Ollama/llama-server. Não garante exclusividade contra um processo iniciado depois da verificação; a instalação deve ocorrer numa janela supervisionada sem reinícios concorrentes. A fonte deve ser byte a byte igual ao blob Git: conversões automáticas LF/CRLF podem provocar recusa, sem conversão silenciosa. O manifesto e os backups exigem proteção do próprio sistema de arquivos contra alteração por terceiros. Os testes de aplicação e rollback usam somente árvores temporárias, com a verificação de processos simulada. A criação de junction real pode depender das permissões do Windows; não considerar uma simulação equivalente a validação real de junction. Sem implantação ou teste funcional real até aprovação explícita.
