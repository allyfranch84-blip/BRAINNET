import logging
import numpy as np
from typing import Dict, List, Tuple, Optional
from qfhrr_core import QFHRRHyperdimensionalEngine

logger = logging.getLogger("BRAINNET_Polysemy")

class PolysemyResolver:
    """
    Resolve a ambiguidade de palavras (polissemia) usando o contexto real.
    Usa o QFHRR em Z_8 para colapsar a superposição de significados.
    """
    
    def __init__(self, vsa: QFHRRHyperdimensionalEngine):
        self.vsa = vsa
        # Papel canônico que rotula o significado de uma palavra
        self.role_significado = self.vsa.generate_vector("__ROLE_SIGNIFICADO__")
        self.role_palavra = self.vsa.generate_vector("__ROLE_PALAVRA__")

    def create_multivector(self, palavra: str, significados: List[str]) -> np.ndarray:
        """
        Cria um vetor superposto da palavra com todos os seus significados.
        V_palavra = Palavra + (Significado1 * Role) + (Significado2 * Role) ...
        """
        v_palavra = self.vsa.text_to_hypervector(palavra)
        components = [self.vsa.bind(self.role_palavra, v_palavra)]
        
        for sig in significados:
            v_sig = self.vsa.text_to_hypervector(sig)
            # Liga o significado ao papel
            bound = self.vsa.bind(self.role_significado, v_sig)
            components.append(bound)
            
        # Superposição (Bundle)
        return self.vsa.bundle(components)

    def resolve_context(self, multivector: np.ndarray, codebook_significados: Dict[str, np.ndarray], contexto: str) -> Tuple[Optional[str], float]:
        """
        Dado o vetor da palavra (com N significados) e o contexto real,
        descobre qual é o significado correto.
        """
        v_contexto = self.vsa.text_to_hypervector(contexto)
        
        # Faz o unbind de cada significado usando o contexto (O Colapso)
        # O contexto atua como um filtro de fase
        v_filtrado = self.vsa.unbind(multivector, v_contexto)
        
        best_label = None
        best_sim = -1.0
        
        for label, v_sig in codebook_significados.items():
            # Testa qual significado ressoa melhor com o resultado filtrado
            sim = self.vsa.similarity(v_filtrado, v_sig)
            if sim > best_sim:
                best_sim = sim
                best_label = label
                
        if best_sim >= 0.35:
            logger.info(f"[POLYSEMY]: Significado resolvido para '{best_label}' no contexto '{contexto[:20]}...' (sim={best_sim:.2f})")
            return best_label, best_sim
            
        logger.warning(f"[POLYSEMY]: Ambiguidade não resolvida (melhor sim={best_sim:.2f})")
        return None, best_sim
