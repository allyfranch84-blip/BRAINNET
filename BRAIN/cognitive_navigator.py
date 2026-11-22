import logging
import json
import urllib.request
import urllib.error
from assistant_prompts import MODELO_PARSER
from typing import Dict, Any, List, Optional

logger = logging.getLogger("BRAINNET_Navigator")

class CognitiveMapNavigator:
    """
    Navegador Cognitivo: Mapeia intenções em um P-DAG e executa a escrita/leitura
    capítulo por capítulo, mantendo o contexto vivo via H-Mem (Schemas).
    """
    def __init__(self, vsa, pdag, hmem, long_context, ollama_url="http://localhost:11434/api/generate"):
        self.vsa = vsa
        self.pdag = pdag
        self.hmem = hmem
        self.long_context = long_context
        self.ollama_url = ollama_url
        self.bridge = None # Será injetado pelo BrainnetBridge depois

    def _call_llm(self, prompt: str, model: str = MODELO_PARSER) -> str:
        payload = {
            "model": model, "prompt": prompt, "stream": False, 
            "options": {"temperature": 0.7, "num_predict": 4096} # Permite textos de até ~12.000 caracteres por capítulo
        }
        try:
            req = urllib.request.Request(self.ollama_url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
            # Timeout aumentado para 300s (5 min) para dar tempo do Xeon carregar o modelo
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read().decode("utf-8")).get("response", "").strip()
        except urllib.error.HTTPError as http_err:
            try:
                error_body = http_err.read().decode("utf-8")
            except Exception:
                error_body = "Não foi possível ler o corpo do erro."
            logger.critical("\n" + "="*50)
            logger.critical(f"🚨 [FALHA HTTP NO NAVEGADOR] Status {http_err.code}: {error_body}")
            logger.critical("="*50 + "\n")
            return f"[ERRO NA GERAÇÃO: Ollama recusou a requisição ({http_err.code}). Detalhe: {error_body}]"
        except Exception as ex:
            logger.critical("\n" + "="*50)
            logger.critical(f"🚨 [FALHA CRÍTICA NO NAVEGADOR] O Ollama não respondeu: {ex}")
            logger.critical("="*50 + "\n")
            return f"[ERRO NA GERAÇÃO: O modelo Ollama falhou ou demorou mais de 5 minutos. Detalhe: {ex}]"

    def plan_journey(self, objective: str, num_steps: int = 5) -> str:
        """Cria o mapa (esqueleto) de um projeto longo e salva no P-DAG."""
        prompt = (
            f"Você é o Arquiteto da BRAINNET. Crie um mapa de {num_steps} etapas/capítulos para a seguinte intenção: '{objective}'.\n"
            "Retorne APENAS um JSON no formato: {\"etapas\": [{\"id\": 1, \"titulo\": \"...\", \"objetivo\": \"...\"}]}"
        )
        response = self._call_llm(prompt)
        
        # Extrai o JSON da resposta
        try:
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            data = json.loads(response)
            etapas = data.get("etapas", [])
        except Exception:
            logger.warning("[NAVEGADOR]: Falha ao fazer parse do mapa. Criando mapa linear simples.")
            etapas = [{"id": i, "titulo": f"Parte {i}", "objetivo": f"Continuar escrevendo sobre {objective}"} for i in range(1, num_steps + 1)]

        route_key = f"trajectory:mapa_{objective.casefold().replace(' ', '_')[:20]}"
        
        # Salva o mapa no P-DAG como uma rota (usando o sistema de banco de dados existente)
        if self.pdag:
            self.pdag.record_execution(
                context_key=route_key, intent=objective, 
                pipeline={"passos": etapas, "type": "cognitive_map"}, reinforcement=1.0
            )
            
        logger.info(f"[NAVEGADOR]: Mapa '{route_key}' criado com {len(etapas)} etapas.")
        return route_key, etapas

    def execute_journey(self, etapas: list, doc_id: str) -> str:
        """Navega pelo mapa (lista de etapas) passada diretamente."""
        if not etapas:
            return "Mapa vazio."

        accumulated_text = ""
        world_state_context = "Início da jornada."

        for step in etapas:
            logger.info(f"[NAVEGADOR]: Escrevendo capítulo {step['id']}: {step['titulo']}")
            
            # Puxa o texto do último documento ingerido (O Manifesto Comunista)
            contexto_documento = ""
            try:
                # O Drag & Drop salva os arquivos na tabela long_context_state
                # Tenta pegar o texto que foi extraído (usando o summary se não houver texto bruto)
                row = self.long_context._conn.execute(
                    "SELECT cumulative_summary, source_path FROM long_context_state ORDER BY updated_at DESC LIMIT 1"
                ).fetchone()
                if row and row[0]:
                    # O Drag & Drop salvou o texto inicial aqui
                    texto_puro = row[0]
                    contexto_documento = f"\n[CONTEÚDO DO DOCUMENTO '{row[1]}']:\n{texto_puro[:4000]}\n"
                    logger.info(f"[NAVEGADOR]: Documento carregado ({len(texto_puro)} chars).")
                else:
                    logger.warning("[NAVEGADOR]: Nenhum documento encontrado na tabela para consulta.")
            except Exception as e:
                logger.error(f"[NAVEGADOR]: Falha ao buscar documento: {e}")

            prompt = (
                f"Você é o Escritor da BRAINNET. Você está escrevendo uma obra contínua baseada nos documentos fornecidos.\n"
                f"ESTADO ATUAL DA NARRATIVA: {world_state_context}\n"
                f"{contexto_documento}"
                f"OBJETIVO DO CAPÍTULO ATUAL: {step['objetivo']} (Título: {step['titulo']})\n"
                "INSTRUÇÃO OBRIGATÓRIA: Escreva um capítulo MUITO LONGO e detalhado (mínimo de 2.500 palavras). "
                "Explore profundamente os conceitos, use exemplos, detalhes técnicos e mantenha a coesão com o que já aconteceu. "
                "NÃO termine o capítulo antes de esgotar o assunto."
            )
            
            # Gera o texto do capítulo
            chapter_text = self._call_llm(prompt)
            
            # Telemetria de Contexto
            chars_prompt = len(prompt)
            chars_doc = len(contexto_documento)
            chars_output = len(chapter_text)
            logger.info(f"[NAVEGADOR] Capítulo {step['id']}: Prompt={chars_prompt} chars | Doc={chars_doc} chars | Output={chars_output} chars")
            
            accumulated_text += f"\n\n=== {step['titulo'].upper()} ===\n[Gerado: {chars_output} caracteres | Contexto do Doc: {chars_doc} caracteres]\n{chapter_text}"
            
            # Atualiza o estado do mundo (resumo para o próximo capítulo) usando o H-Mem
            summary_prompt = f"Resuma em 2 frases o que aconteceu neste texto e qual é o novo estado do mundo:\n{chapter_text}"
            new_state = self._call_llm(summary_prompt)
            if new_state:
                world_state_context = new_state
                
            # Salva o texto bruto no LongContext (SQLite) para não perder nada
            if self.long_context:
                self.long_context._conn.execute(
                    "INSERT INTO long_context_state (doc_id, source_type, source_path, total_chunks, current_chunk, cumulative_summary, status, created_at, updated_at) "
                    "VALUES (?, 'cognitive_map', ?, 1, 1, ?, 'DONE', strftime('%s','now'), strftime('%s','now'))",
                    (f"{doc_id}_cap{step['id']}", "cognitive_navigator", chapter_text)
                )
            
            # Avisa o frontend que o capítulo terminou
            if self.bridge:
                try:
                    payload = json.dumps({"role": "ai", "text": f"📝 Capítulo {step['id']} concluído ({len(chapter_text)} chars). Iniciando próximo..."}, ensure_ascii=False)
                    if getattr(self.bridge, "_window", None):
                        self.bridge._window.evaluate_js(f"window.dispatchEvent(new CustomEvent('aios:message', {{ detail: {payload} }}));")
                except Exception as e:
                    logger.debug(f"[NAVEGADOR]: Falha ao enviar evento para UI: {e}")

        # Consolida a memória final no H-Mem (Cria um Schema do livro inteiro)
        if self.hmem:
            self.hmem.record_episodic_node(
                concept=f"projeto_{doc_id}", payload={"resumo_final": world_state_context, "texto_total": len(accumulated_text)},
                context_tuple="cognitive_navigation", session_id=doc_id
            )

        return accumulated_text
