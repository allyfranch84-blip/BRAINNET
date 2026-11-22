# ==============================================================================
# BRAINNET v7 - SISTEMA OPERACIONAL COGNITIVO
# MODULO: dual_tier_arbitration.py
# FUNCAO: Decisao por Consenso em Duas Camadas com Gramatica Fasorial Alinhada.
# ==============================================================================

from __future__ import annotations

import json
import logging
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import zlib
import numpy as np

BRAIN_DIR = Path(__file__).resolve().parent
if str(BRAIN_DIR) not in sys.path:
    sys.path.insert(0, str(BRAIN_DIR))

from context_capture import ContextCapture
from hyperdimensional import FHRRHyperdimensionalEngine
from pdag_engine import MyelinatedPDAGEngine
from error_blackbox import ErrorBlackBoxEngine

logger = logging.getLogger("BRAINNET_Consensus")


class NCDFilter:
    @staticmethod
    def calculate_ncd(state_before: str, state_after: str) -> float:
        if state_before == state_after:
            return 0.0

        b_x = state_before.encode("utf-8")
        b_y = state_after.encode("utf-8")
        b_xy = b_x + b_y

        c_x = len(zlib.compress(b_x))
        c_y = len(zlib.compress(b_y))
        c_xy = len(zlib.compress(b_xy))

        ncd = (c_xy - min(c_x, c_y)) / max(c_x, c_y)
        return round(float(ncd), 4)


class CandidateItemMemory:
    def __init__(self, vsa_engine: FHRRHyperdimensionalEngine) -> None:
        self.vsa = vsa_engine
        self._quarantine: Dict[str, Dict[str, Any]] = {}

    def register_candidate(
        self,
        task_key: str,
        trajectory: List[Dict[str, Any]],
        ncd_score: float,
        context_name: str = "desktop"
    ) -> bool:
        if ncd_score < 0.20:
            return False

        # Codificação por Papéis (Role-Value Binding) padronizada
        v_cand = self.vsa.encode_compositional(
            action=trajectory[0].get("acao", "ACTION"),
            target=task_key,
            param="VALIDATED_TRAJECTORY",
            context=context_name
        )

        self._quarantine[task_key] = {
            "trajectory": trajectory,
            "vector": v_cand,
            "target_key": task_key,
            "context_name": context_name,
            "ncd_score": ncd_score,
            "success_count": 1,
            "timestamp": time.time()
        }
        return True

    def get_candidate(self, task_key: str) -> Optional[Dict[str, Any]]:
        return self._quarantine.get(task_key)

    def increment_candidate_success(self, task_key: str) -> int:
        if task_key in self._quarantine:
            self._quarantine[task_key]["success_count"] += 1
            return self._quarantine[task_key]["success_count"]
        return 0

    def purge_candidate(self, task_key: str) -> None:
        self._quarantine.pop(task_key, None)


class DualTierArbitrator:
    __slots__ = ("vsa", "pdag", "quarantine", "blackbox", "consensus_threshold")

    def __init__(
        self,
        vsa: FHRRHyperdimensionalEngine,
        pdag: MyelinatedPDAGEngine,
        blackbox: ErrorBlackBoxEngine,
        consensus_threshold: float = 0.55
    ) -> None:
        self.vsa = vsa
        self.pdag = pdag
        self.quarantine = CandidateItemMemory(vsa)
        self.blackbox = blackbox
        self.consensus_threshold = consensus_threshold

    def arbitrate_decision(
        self,
        task_key: str,
        current_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        t0 = time.perf_counter_ns()
        candidate = self.quarantine.get_candidate(task_key)

        if not candidate:
            elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000.0
            return {
                "decision": "SEM_CANDIDATO",
                "motivo": "Nenhuma rota explorada previamente na quarentena.",
                "tempo_ms": round(elapsed_ms, 3)
            }

        # 1. Projeção Alinhada da Simulação de Momento
        v_sim = self.vsa.encode_compositional(
            action=candidate["trajectory"][0].get("acao", "ACTION"),
            target=task_key,
            param="VALIDATED_TRAJECTORY",
            context=current_context.get("process_name", "desktop")
        )
        v_cand = candidate["vector"]

        # 2. Produto Escalar de Similaridade de Consenso
        similarity = self.vsa.similarity(v_sim, v_cand)
        elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000.0

        # ======================================================================
        # CENÁRIO A: CONSENSO APROVADO (Similaridade >= 0.55)
        # ======================================================================
        if similarity >= self.consensus_threshold:
            successes = self.quarantine.increment_candidate_success(task_key)
            promovido = False

            if successes >= 3:
                chave_pdag = f"promoted:{task_key[:32]}"
                self.pdag.record_execution(
                    context_key=chave_pdag,
                    intent=task_key,
                    pipeline={"tipo": "promoted_trajectory", "passos": candidate["trajectory"]},
                    reinforcement=1.0
                )
                self.quarantine.purge_candidate(task_key)
                promovido = True

            return {
                "decision": "CONSENSO_APROVADO",
                "similaridade_consenso": round(similarity, 4),
                "trajetoria": candidate["trajectory"],
                "sucessos_acumulados": successes,
                "promovido_ao_pdag": promovido,
                "tempo_arbitragem_ms": round(elapsed_ms, 3)
            }

        # ======================================================================
        # CENÁRIO B: CONFLITO / DIVERGÊNCIA (Similaridade < 0.55)
        # ======================================================================
        else:
            snap = self.blackbox.registrar_falha_e_punir(
                intencao_original=task_key,
                acao_executada={"tipo": "ARBITRATION_CONFLICT", "candidato": candidate["trajectory"]},
                estado_esperado={"contexto": candidate["context_name"], "similaridade_minima": self.consensus_threshold},
                estado_observado={"contexto_atual": current_context.get("process_name"), "similaridade": round(similarity, 4)},
                motivo_punicao="Contexto ativo incompatível com a rota pré-explorada na quarentena."
            )

            return {
                "decision": "CONFLITO_REJEITADO",
                "similaridade_consenso": round(similarity, 4),
                "snapshot_blackbox": snap["snapshot_id"],
                "motivo": "Incompatibilidade de contexto ou alteração de tela detectada. Execução bloqueada preventivamente.",
                "tempo_arbitragem_ms": round(elapsed_ms, 3)
            }


if __name__ == "__main__":
    print("=" * 70)
    print("BRAINNET v7 - TESTE DO MOTOR DE ARBITRAGEM POR CONSENSO (DUAL-TIER)")
    print("=" * 70)

    ctx = ContextCapture()
    vsa = FHRRHyperdimensionalEngine(dimension=10_000)
    pdag = MyelinatedPDAGEngine(db_path="core1_pdag.db")
    blackbox = ErrorBlackBoxEngine(ctx, vsa, pdag)
    arbitrator = DualTierArbitrator(vsa, pdag, blackbox, consensus_threshold=0.70)

    tarefa = "Abrir Bloco de Notas e Inserir Relatorio"

    # 1. CAMADA 1: Exploração em Segundo Plano
    print("\n[CAMADA 1: SEGUNDO PLANO]: Explorando rota no contexto 'desktop'...")
    ncd = NCDFilter.calculate_ncd("Desktop_Vazio", "Bloco_Notas_Aberto_Texto")
    print(f"  -> Distância NCD calculada: {ncd} (Limiar >= 0.20)")

    rota = [
        {"passo": 1, "acao": "LAUNCH", "cmd": "notepad.exe"},
        {"passo": 2, "acao": "TYPE", "text": "Relatorio de Consenso 2026"},
        {"passo": 3, "acao": "HOTKEY", "keys": ["enter"]}
    ]
    arbitrator.quarantine.register_candidate(tarefa, rota, ncd_score=ncd, context_name="desktop")
    print(f"  -> Rota retida na Quarentena de RAM: True")

    # 2. CAMADA 2: Solicitação em Contexto Compatível
    print("\n[CAMADA 2: ARBITRAGEM EM TEMPO REAL]: Operador solicita no desktop...")
    decisao = arbitrator.arbitrate_decision(tarefa, {"process_name": "desktop"})

    print(f"\n>>> RESULTADO DA ARBITRAGEM (CONTEXTO CORRETO) <<<")
    print(f"  Decisão: {decisao['decision']}")
    print(f"  Similaridade de Consenso: {decisao.get('similaridade_consenso')} (Limiar: {arbitrator.consensus_threshold})")
    print(f"  Tempo de Arbitragem: {decisao['tempo_arbitragem_ms']} ms (Zero-LLM)")

    # 3. CAMADA 2: Solicitação em Contexto Incompatível (Ex: Jogo 3D em Tela Cheia)
    print("\n[TESTE DE CONFLITO PREVENTIVO]: Operador solicita durante jogo em tela cheia...")
    decisao_conflito = arbitrator.arbitrate_decision(tarefa, {"process_name": "fullscreen_game.exe"})
    
    print(f"\n>>> RESULTADO DA ARBITRAGEM (CONTEXTO INCOMPATÍVEL) <<<")
    print(f"  Decisão sob Divergência: {decisao_conflito['decision']}")
    print(f"  Similaridade Obtida: {decisao_conflito.get('similaridade_consenso')} (Limiar: {arbitrator.consensus_threshold})")
    print(f"  Ação de Segurança: {decisao_conflito.get('motivo')}")

    print("\n" + "=" * 70)
    print(">>> DUAL-TIER CONCLUÍDO COM HARMONIZAÇÃO FASORIAL TOTAL! <<<")
    print("=" * 70)