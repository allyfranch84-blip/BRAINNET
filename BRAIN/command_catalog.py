"""Command descriptions only; existing bridge remains the sole dispatcher."""
COMMANDS = (
 ('Chat','/escreva <tema>','Rascunho por seções; conclusão e retomada são parciais.','experimental','modelo conversacional','não'),
 ('Chat','/continue <id>','Retoma seções elegíveis de um rascunho.','experimental','checkpoint e modelo','não'),
 ('Chat','/copy | /copie | /copy all | /copie all | /copy tudo | /copie tudo | /copy-all | /copietudo','Copia mensagens recentes ou histórico.','experimental','área de transferência','sim: escrita'),
 ('Modelos','/modelo listar','Consulta modelos instalados no endpoint Ollama configurado.','experimental','Ollama acessível','não'),
 ('Modelos','/modelo usar <nome>','Seleciona modelo encontrado no catálogo para próximas inferências conversacionais.','experimental','Ollama e modelo instalado','não'),
 ('Modelos','/modo auto | fast | balanced | deep','Define orçamento cognitivo das próximas tarefas.','disponível','configuração gravável','não'),
 ('Modelos','/modo livre | padrao | status','Seleciona ou consulta estilo conversacional; não altera pesos nem permissões.','experimental','configuração gravável','não'),
 ('Visão','/visao agora','Solicita descrição da tela pelo caminho visual existente.','experimental','visão, captura e modelo visual','não para leitura'),
 ('Visão','/uia scan','Lista controles UIA da janela ativa.','experimental','janela ativa e UIA','não para leitura'),
 ('Controle','clique / pinte / desenhe ...','Solicita interação visual em linguagem natural; execução e verificação seguem contratos existentes.','experimental','UI-TARS e atuador','sim'),
 ('Memória','/offline <termo>','Consulta um ZIM local; com vários use /offline arquivo.zim :: termo. Fontes não verificadas.','experimental','libzim e ZIM local','não'),
 ('Memória','/offline-ref <id>','Reabre uma fonte registrada no H-Mem.','experimental','H-Mem e ZIM original','não'),
 ('Memória','/esquecer | /purge | /limpar <termo>','Remove hábitos; vazio/tudo pode apagar todos.','experimental','P-DAG','sim: escrita'),
 ('Aprendizado','/treino on | /treino start | /treinar | /iniciar treino | /treino off | /treino stop | /parar treino | /treino status | /status treino | /treinamento','Controla ou consulta o coletor existente.','experimental','harvester','sim para iniciar'),
 ('Aprendizado','/rem | /rem parar | /rem stop | /acordar | /rem status | /sono status','Solicita ciclo REM, parada ou status; ciclo pode podar dados.','experimental','REM','sim para iniciar'),
 ('Aprendizado','/certo | /correto | /perfeito','Registra reforço para tarefa anterior no P-DAG.','experimental','P-DAG e tarefa identificada','sim: escrita'),
 ('Diagnóstico','/report | /repot | /repor | /falha <motivo>','Registra relato de falha e pode alterar P-DAG.','experimental','P-DAG e caixa preta','sim: escrita'),
 ('Diagnóstico','/logs web | /log web | /historico web | /historico-web','Consulta histórico web do P-DAG.','experimental','P-DAG','não'),
 ('Diagnóstico','/help | /ajuda | /?','Mostra este catálogo de handlers.','disponível','nenhuma','não'),
 ('Sistema','/code | /code on | /code exit | /code off','Ativa ou desativa modo de código legado.','experimental','Coder 7B para geração','sim para escrita'),
 ('Sistema','/switch mode | /modo','Alterna modo legado Trajetória/Consenso.','experimental','Kernel','não'),
 ('Chat','/pesquisa | /pesquisar | /pesquise | /busque | /buscar | /search <assunto>','Busca fontes em segundo plano; não confirma as afirmações.','experimental','rede DuckDuckGo','não para pesquisa'),
)

def render_help(kernel=None):
    lines=['Comandos registrados (disponibilidade externa não verificada):']
    for category in ('Chat','Modelos','Visão','Controle','Memória','Aprendizado','Sistema','Diagnóstico'):
        lines.append('\n**'+category+'**')
        for cat,syntax,desc,state,deps,auth in COMMANDS:
            if cat==category:
                required = {'/visao agora':'vision', '/uia scan':'eye',
                            'clique / pinte / desenhe ...':'ui_protocol'}.get(syntax)
                if syntax.startswith('/treino '): required = 'harvester'
                if syntax.startswith('/rem '): required = 'rem_engine'
                if syntax.startswith(('/certo ', '/esquecer ', '/logs web ')): required = 'pdag'
                if syntax.startswith('/report '): required = 'blackbox'
                if required and (kernel is None or getattr(kernel, required, None) is None):
                    state = 'indisponível'
                    deps = deps + f' (módulo {required} ausente)'
                lines.append(f'• `{syntax}` — {desc} Estado: {state}; dependências: {deps}; autorização: {auth}; uso manual.')
    return '\n'.join(lines)
