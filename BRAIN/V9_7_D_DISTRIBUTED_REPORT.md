# V9.7-D — multi-brain experimental

## Auditoria
ModelResidencyManager possui fila e proteção de modelos ativos, porém gerencia processos locais e não dispositivos. execution_authority controla autorização local de ações. browser_bridge mantém HTTP em loopback para extensão Chromium; não constitui pareamento seguro de dispositivos. Não houve verificação abrangente de todos os módulos de rede.

## Protótipo
simulated_multibrain.py define Node, NodeRole, Task, Result e SimulatedCoordinator em memória. O executor simulado precisa estar online, pareado, não revogado, ter capacidade e permissão para pesquisa, crítica, análise de código ou verificação; coordenadores e observadores não são executores. Quando não há executor disponível antes do despacho, pode ser usado worker local injetado. Depois do despacho não há repetição automática; timeout é TIMEOUT_UNCONFIRMED, pois não prova encerramento. IDs duplicados são rejeitados na instância. Resultados agregam origem e registram conflitos literais, sem declarar fatos verificados.

O pareamento, permissões e revogação são apenas campos simulados, não autenticação real. Asyncio usa cancelamento cooperativo: um worker que ignore cancelamento pode atrasar timeout. Não há fila distribuída, persistência de IDs, isolamento de processo, transporte, criptografia nem execução distribuída em dispositivos reais. Funções injetadas precisam ser confiáveis: o contrato de tarefas analíticas não constitui sandbox. Nenhum serviço é iniciado.

## Segurança para integração futura
Definir identidade criptográfica de dispositivo, pareamento aprovado pelo usuário, transporte autenticado e cifrado, escopo mínimo por tarefa, revogação persistente, política de retenção e acesso, limitação de tamanho, isolamento do executor e cancelamento comprovado. Mouse, teclado, arquivos e rede externa exigem controles próprios e autorização explícita; conexão de rede jamais deve concedê-los. Idempotência persistente e registro de execução devem preceder retries ou efeitos externos.

## Painel Master Shell — especificação
Listar dispositivos conhecidos com identidade verificada, online/offline e horário da última confirmação, papel, capacidades, modelos, carga e latência medidas ou UNKNOWN, permissões e tarefa atual. Oferecer pareamento e revogação somente após implementação do fluxo autenticado; distinguir claramente dados simulados. Sem UI ativa nesta fase.

## Testes
18 testes passaram em 0,23 s: test_v97d_simulated_multibrain.py e test_model_residency_manager.py; log development_logs/V9_7_D_TESTS_FINAL.log. Testam conflito, duplicação local, dispositivo revogado/offline/observador, fallback pré-despacho e timeout simulado. Não demonstram rede, segurança criptográfica ou execução em outro computador. Não foram iniciados serviços de rede.
