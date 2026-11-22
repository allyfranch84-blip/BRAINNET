# ==============================================================================
# BRAINNET v7 - HABILIDADE MODULAR: habilidade_sono_rem.py
# ==============================================================================
from __future__ import annotations

import logging
from pathlib import Path
import sys
import time
from typing import Any, Dict

skills_dir = Path(__file__).resolve().parent
brain_dir = skills_dir.parent / "BRAIN"
if str(brain_dir) not in sys.path:
    sys.path.insert(0, str(brain_dir))

from skill_loader import skill  # type: ignore

logger = logging.getLogger("BRAINNET_Skill_REM")

@skill(
    name="ativar_sono_rem",
    description="Força o ciclo imediato de Sono REM: poda de conexões mortas, vacina estocástica FHRR e cristalização.",
    tags=["sono", "rem", "poda", "otimizacao"]
)
def disparar_sono_rem(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    """Execução modular imediata sem esperar o temporizador de 15 minutos."""
    t0 = time.perf_counter_ns()
    logger.info("[HABILIDADE]: Disparando Sono REM sob demanda...")

    try:
        from rem_sleep_engine import REMSleepEngine  # type: ignore
        from hyperdimensional import FHRRHyperdimensionalEngine  # type: ignore

        db_path = brain_dir / "core1_pdag.db"
        rem_engine = REMSleepEngine(db_path=str(db_path), skills_dir=skills_dir, idle_threshold_sec=0.0)
        vsa = FHRRHyperdimensionalEngine(dimension=10_000)

        relatorio_poda = rem_engine.dream_and_prune(vsa_engine=vsa)
        novas_skills = rem_engine.crystallize_habits_to_skills()
        elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000

        return {
            "status": "COMPLETED",
            "tempo_ms": round(elapsed_ms, 2),
            "poda": relatorio_poda,
            "novas_skills": novas_skills,
            "mensagem": f"Sono REM concluído em {elapsed_ms:.2f}ms. {len(novas_skills)} novas habilidades compiladas."
        }
    except Exception as e:
        logger.error(f"Erro no Sono REM: {e}")
        return {"status": "ERROR", "log": str(e)}