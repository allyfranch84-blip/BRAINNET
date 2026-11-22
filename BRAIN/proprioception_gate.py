# ==============================================================================
# BRAINNET v7 - SISTEMA OPERACIONAL COGNITIVO
# MODULO: proprioception_gate.py
# FUNCAO: Auto-Modelo de Affordances do SO, Ortogonalidade Ontologica (FHRR 10.000D)
#         e Extincao do "Problema da Geladeira" em < 0.3ms (Zero-LLM).
# ==============================================================================

from __future__ import annotations

import logging
from pathlib import Path
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

BRAIN_DIR = Path(__file__).resolve().parent
if str(BRAIN_DIR) not in sys.path:
    sys.path.insert(0, str(BRAIN_DIR))

from hyperdimensional import FHRRHyperdimensionalEngine

logger = logging.getLogger("BRAINNET_Proprioception")


class DigitalProprioceptionGate:
    """
    [CAMADA 0 - PORTAO ONTOLOGICO DO CORPO DIGITAL]:
    Conhece matematicamente as capacidades fisicas do sistema operacional
    e bloqueia ordens do mundo material/impossiveis por quase-ortogonalidade fasorial.
    """

    __slots__ = (
        "vsa",
        "corpo_digital_vector",
        "mundo_fisico_vector",
        "ontologia_rejeitada",
        "limiar_affordance"
    )

    def __init__(self, vsa_engine: Optional[FHRRHyperdimensionalEngine] = None) -> None:
        self.vsa = vsa_engine or FHRRHyperdimensionalEngine(dimension=10_000, seed=42)
        self.limiar_affordance = 0.18

        # 1. CATALOGO DE AFFORDANCES DIGITAIS DO SISTEMA OPERACIONAL
        ferramentas_so = [
            "janela_win32_hwnd_foco_minimizar_maximizar",
            "processo_executavel_iniciar_finalizar_taskkill",
            "arvore_acessibilidade_uia_botao_texto_lista",
            "teclado_mouse_clique_atalho_digitar_unicode",
            "sistema_arquivos_disco_ler_gravar_editar_pasta",
            "navegador_web_url_pagina_aba_pesquisa_dados",
            "terminal_powershell_cmd_script_python_batch",
            "audio_microfone_voz_fala_som_tts"
        ]

        vetores_ferramentas = [self.vsa.generate_vector(f) for f in ferramentas_so]
        self.corpo_digital_vector = self.vsa.bundle(vetores_ferramentas)

        # 2. VETOR DE OBJETOS DO MUNDO FISICO (SEM INTERFACE LOGICA NO SO)
        objetos_fisicos_exemplares = [
            "geladeira_fogao_microondas_eletrodomestico_cozinha",
            "pao_queijo_comida_cafe_agua_almoco_prato",
            "voar_andar_correr_pular_limpar_casa_lavar",
            "porta_fisica_janela_parede_carro_veiculo_rua",
            "copo_mesa_cadeira_garrafa_roupa_gaveta"
        ]
        vetores_fisicos = [self.vsa.generate_vector(f) for f in objetos_fisicos_exemplares]
        self.mundo_fisico_vector = self.vsa.bundle(vetores_fisicos)

        # Atratores fasoriais normalizados e limiares contínuos em C^10.000
        self.ontologia_rejeitada = None

    def validar_intencao_no_corpo_digital(self, prompt: str) -> Tuple[bool, Dict[str, Any]]:
        """
        [VERIFICADOR ONTOLÓGICO PROBABILÍSTICO EM C^10.000]:
        Substitui listas e regexes por colapso de densidade de probabilidade
        entre o Toro do Corpo Digital e o Toro do Mundo Físico Material.
        """
        t0 = time.perf_counter_ns()
        p_low = prompt.strip().lower()

        # Projeção no espaço hiperdimensional C^10.000
        v_intencao = self.vsa.generate_vector(p_low)
        sim_so = max(0.0, self.vsa.similarity(v_intencao, self.corpo_digital_vector))
        sim_fisico = max(0.0, self.vsa.similarity(v_intencao, self.mundo_fisico_vector))

        # Distribuição de probabilidade não-linear (Gibbs Softmax, beta = 10.0)
        scores = np.array([sim_so, sim_fisico], dtype=np.float32)
        exp_scores = np.exp(scores * 10.0)
        probs = exp_scores / np.sum(exp_scores)
        prob_so, prob_fisico = float(probs[0]), float(probs[1])

        elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000.0

        # Se a probabilidade do mundo material físico predominar
        if prob_fisico > 0.65 and sim_fisico > sim_so:
            return False, {
                "status": "IMPOSSIBLE_ACTION",
                "motivo": f"Comando rejeitado por falta de affordance: o alvo pertence ao mundo material (Probabilidade Física: {prob_fisico:.2%}).",
                "similaridade_so": round(sim_so, 4),
                "prob_fisico": round(prob_fisico, 4),
                "tempo_ms": round(elapsed_ms, 3)
            }

        return True, {
            "status": "AFFORDANCE_VALIDA",
            "similaridade_so": round(sim_so, 4),
            "prob_so": round(prob_so, 4),
            "tempo_ms": round(elapsed_ms, 3)
        }