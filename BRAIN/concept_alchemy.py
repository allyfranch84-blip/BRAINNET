"""Alquimia de Conceitos e Frases usando QFHRR (Z_8)."""
import logging
import numpy as np
from typing import Dict, Any, List, Optional
from qfhrr_core import QFHRRHyperdimensionalEngine

logger = logging.getLogger("BRAINNET_Alchemy")

class ConceptAlchemy:
    def __init__(self, vsa: QFHRRHyperdimensionalEngine, hmem_engine, llm_callback=None):
        self.vsa = vsa
        self.hmem = hmem_engine
        self.llm_callback = llm_callback # Função para verbalizar a ideia via Ollama
        
        # Papéis estruturais fixos (Roles)
        self.role_sujeito = self.vsa.generate_vector("__ROLE_SUJEITO__")
        self.role_estado = self.vsa.generate_vector("__ROLE_ESTADO__")
        self.role_acao = self.vsa.generate_vector("__ROLE_ACAO__")
        self.role_conceito_a = self.vsa.generate_vector("__ROLE_CONCEITO_A__")
        self.role_conceito_b = self.vsa.generate_vector("__ROLE_CONCEITO_B__")

    def encode_frase(self, sujeito: str, estado: str, acao: str) -> np.ndarray:
        """Cria um vetor único que representa a estrutura da frase."""
        v_suj = self.vsa.text_to_hypervector(sujeito)
        v_est = self.vsa.text_to_hypervector(estado)
        v_act = self.vsa.text_to_hypervector(acao)
        
        # Binding (Associação Estrutural)
        v_frase = self.vsa.bind(self.role_sujeito, v_suj)
        v_frase = self.vsa.bind(v_frase, self.vsa.bind(self.role_estado, v_est))
        v_frase = self.vsa.bind(v_frase, self.vsa.bind(self.role_acao, v_act))
        return v_frase

    def decode_frase(self, v_frase: np.ndarray, codebook_sujeitos: Dict, codebook_estados: Dict, codebook_acoes: Dict):
        """Faz o unbinding para tentar ler a frase de volta (sem tokens)."""
        res = {}
        for nome_papel, v_papel, cb in [
            ("sujeito", self.role_sujeito, codebook_sujeitos),
            ("estado", self.role_estado, codebook_estados),
            ("acao", self.role_acao, codebook_acoes)
        ]:
            v_recuperado = self.vsa.unbind(v_frase, v_papel)
            # Encontra a palavra mais próxima no codebook
            best_label, best_sim = None, -1.0
            for label, v_cb in cb.items():
                sim = self.vsa.similarity(v_recuperado, v_cb)
                if sim > best_sim:
                    best_sim = sim
                    best_label = label
            res[nome_papel] = (best_label, round(best_sim, 2))
        return res

    def alquimia_conceitual(self, conceito_a: str, operacao: str, conceito_b: str) -> str:
        """Subtrai ou soma dois conceitos e verbaliza via LLM."""
        v_a = self.vsa.text_to_hypervector(conceito_a)
        v_b = self.vsa.text_to_hypervector(conceito_b)
        
        if operacao == "subtracao":
            # Subtração: A - B (remove a semântica de B de A)
            v_result = self.vsa.unbind(v_a, v_b)
        elif operacao == "soma":
            # Soma: A + B (superposição)
            v_result = self.vsa.bundle([v_a, v_b])
        else:
            raise ValueError("Operação inválida. Use 'subtracao' ou 'soma'.")

        # Para verbalizar, encontramos a palavra mais próxima do resultado no código semântico
        # ou passamos para o LLM.
        if self.llm_callback:
            # O LLM recebe o vetor resultante codificado em base64/string e tenta traduzir
            # (Na prática, buscamos via cleanup no hmem).
            return self.llm_callback(v_result, f"Alquimia: {conceito_a} {operacao} {conceito_b}")
        return "Verbalização indisponível."
