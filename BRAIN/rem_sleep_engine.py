# ==============================================================================
# BRAINNET v7 - SISTEMA OPERACIONAL COGNITIVO
# MODULO: rem_sleep_engine.py
# FUNCAO: Motor de Sono REM, Poda Sinaptica (Curva de Ebbinghaus),
#         Imunizacao de Fase FHRR e Cristalizacao de Habitos em Scripts Python.
# TAGS DE BUSCA:
#   - [BN_REM_CORE]          : Estrutura Geral e Orquestracao Circadiana
#   - [BN_REM_IDLE]          : Deteccao de Ociosidade Win32 (GetLastInputInfo)
#   - [BN_REM_PRUNING]       : Poda Sinaptica e Expurgacao de Conexoes Mortas
#   - [BN_REM_PERTURBATION]  : Injecao de Ruido de Fase (sigma = 0.15*pi)
#   - [BN_REM_CRYSTALLIZE]   : Compilacao de Habitos Mielinizados em Codigo .py
#
# DEPENDENCIAS EXTERNAS:
#   - ctypes, sqlite3, time, numpy, pathlib.
# QUEM CHAMA ESTE MODULO:
#   - aios_master.py (executado em background quando o usuario esta ausente).
# ==============================================================================

from __future__ import annotations

from contextlib import closing
import ctypes
from ctypes import wintypes
import json
import math
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
from pdag_engine import MyelinatedPDAGEngine

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# [BN_REM_IDLE] - Estrutura Win32 para medicao de ociosidade fisica
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwTime", wintypes.DWORD),
    ]

user32.GetLastInputInfo.restype = wintypes.BOOL
user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]

kernel32.GetTickCount.restype = wintypes.DWORD
kernel32.GetTickCount.argtypes = []


class REMSleepEngine:
    """
    [BN_REM_CORE]
    O Otimizador Circadiano do BRAINNET.
    Executa a faxina e consolidacao noturna em background.
    """

    __slots__ = ("db_path", "skills_dir", "idle_threshold_sec", "pdag")

    def __init__(
        self,
        db_path: str = "core1_pdag.db",
        skills_dir: Optional[Union[str, Path]] = None,
        idle_threshold_sec: float = 900.0,  # 15 minutos padrao
        pdag_engine: Optional[MyelinatedPDAGEngine] = None,
    ) -> None:
        self.db_path = db_path
        self.pdag = pdag_engine
        if skills_dir:
            self.skills_dir = Path(skills_dir)
        else:
            # Caminho relativo padrao para a pasta HABILIDADES
            self.skills_dir = Path(__file__).resolve().parent.parent / "HABILIDADES"
        self.idle_threshold_sec = idle_threshold_sec

    # --------------------------------------------------------------------------
    # [BN_REM_IDLE] - DETECCAO DE INATIVIDADE DO USUARIO
    # --------------------------------------------------------------------------

    def get_user_idle_seconds(self) -> float:
        """
        Retorna ha quantos segundos o usuario nao toca no mouse ou teclado.
        Precisao nativa Win32 em milissegundos.
        """
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if user32.GetLastInputInfo(ctypes.byref(lii)):
            millis_since_boot = kernel32.GetTickCount()
            idle_millis = max(0, millis_since_boot - lii.dwTime)
            return idle_millis / 1000.0
        return 0.0

    def is_system_ready_for_sleep(self) -> bool:
        """Verifica se o tempo de inatividade ultrapassou o limiar de seguranca."""
        return self.get_user_idle_seconds() >= self.idle_threshold_sec

    # --------------------------------------------------------------------------
    # [BN_REM_PRUNING] - PODA SINAPTICA E DESCARTE DE LIXO
    # --------------------------------------------------------------------------

    def dream_and_prune(self, vsa_engine: Any) -> Dict[str, Any]:
        """
        [SONHO E PODA REM]:
        1. Insere caos estocastico nas fases (sigma = 0.15*pi).
        2. Avalia a presenca de dor somatica nos caminhos.
        3. Poda rotas que causaram dor e cristaliza rotas de alivio comprovado.
        """
        prune_report = self.run_synaptic_pruning()

        # A poda compartilhada preserva a evidencia Beta dos nos ainda validos.
        mutacoes = prune_report["pruned_habits"]

        return {
            "pruning": prune_report,
            "caos_e_mutacoes_rem": mutacoes,
            "status": "SONHO_E_REESTRUTURACAO_CONCLUIDOS"
        }

    def _get_pdag(self) -> MyelinatedPDAGEngine:
        if self.pdag is None:
            raise RuntimeError("REM exige injecao do pdag_engine compartilhado para operar rotas")
        return self.pdag

    def run_synaptic_pruning(self, max_age_days: float = 90.0, min_weight_threshold: float = 0.05) -> Dict[str, Any]:
        """
        Aplica o decaimento exponencial de Ebbinghaus: W(t) = W0 * e^(-lambda * dt).
        Elimina conexoes mortas com mais de 90 dias e reorganiza o SQLite via VACUUM.
        """
        pdag = self._get_pdag()
        with pdag.node_snapshot() as nodes:
            total_before = len(nodes)

        deleted_count = pdag.apply_ebbinghaus_decay(max_age_days)
        if not pdag.flush_pending_writes(5.0):
            raise TimeoutError("Poda do P-DAG nao foi persistida")

        return {
            "total_before": total_before,
            "pruned_habits": deleted_count,
            "total_after": total_before - deleted_count,
        }

    # --------------------------------------------------------------------------
    # [BN_REM_PERTURBATION] - INJECAO DE RUIDO DE FASE FHRR (IMUNIZACAO)
    # --------------------------------------------------------------------------

    @staticmethod
    def inject_phase_noise(
        vector: np.ndarray,
        sigma: float = 0.15 * math.pi,
        num_variations: int = 3,
    ) -> np.ndarray:
        """
        Injeta perturbacao estocastica nas fases: delta ~ Normal(0, sigma^2).
        Gera uma superposicao robusta imune a atualizacoes visuais do Windows 11.
        """
        dim = len(vector)
        orig_phases = np.angle(vector)
        synth_vectors = [vector]

        for _ in range(num_variations):
            noise = np.random.normal(0.0, sigma, dim).astype(np.float32)
            perturbed_phases = orig_phases + noise
            synth_vectors.append(np.exp(1j * perturbed_phases).astype(np.complex64))

        # Funde as variacoes por superposicao vetorial (Bundling)
        accum = np.sum(synth_vectors, axis=0)
        final_phases = np.angle(accum)
        return np.exp(1j * final_phases).astype(np.complex64)

    # --------------------------------------------------------------------------
    # [BN_REM_CRYSTALLIZE] - CRISTALIZACAO DE HABITOS EM SCRIPTS PYTHON
    # --------------------------------------------------------------------------

    def prune_hmem_nodes(self, retention_days: float = 30) -> int:
        with closing(sqlite3.connect(self.db_path)) as conn:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'hmem_nodes'").fetchone() is None:
                return 0
            cutoff = time.time() - (retention_days * 86400)
            cursor = conn.execute("DELETE FROM hmem_nodes WHERE timestamp < ?", (cutoff,))
            conn.commit()
            if cursor.rowcount > 0:
                conn.execute("VACUUM;")
            return cursor.rowcount

    def crystallize_habits_to_skills(self) -> List[str]:
        """
        Busca todas as rotas mielinizadas (is_myelinated = 1) no SQLite
        e as compila em scripts Python deterministas dentro da pasta HABILIDADES.
        """
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        skills_existentes = sorted(self.skills_dir.glob("*.py"), key=os.path.getmtime)
        if len(skills_existentes) > 100:
            for old_skill in skills_existentes[:20]:
                old_skill.unlink()
        crystallized_skills: List[str] = []

        with self._get_pdag().node_snapshot(myelinated_only=True) as nodes:
            rows = [(node["context_key"], node["intent"], node["pipeline_spec"], node["consecutive_successes"]) for node in nodes]

            for row in rows:
                ctx_hash, intent, spec_json, successes = row
                # Sanitiza o nome do arquivo a partir da intencao
                safe_name = "".join(
                    c if c.isalnum() else "_" for c in intent.strip().lower()
                )[:32].strip("_")
                if not safe_name:
                    safe_name = f"skill_{ctx_hash[:8]}"

                file_path = self.skills_dir / f"auto_{safe_name}.py"

                # Parseia JSON para Python válido (JSON true/null/false não existem em Python)
                try:
                    spec_dict = json.loads(spec_json) if isinstance(spec_json, str) else (spec_json or {})
                except (json.JSONDecodeError, TypeError) as ex:
                    logger.warning(
                        "[REM/SKILL]: spec_json inválido para intent '%s': %s. Skill não gerada.",
                        intent, ex,
                    )
                    continue
                # repr() em dict/str garante Python válido independente de aspas, \n ou unicode
                payload_repr = repr(spec_dict)
                intent_repr = repr(str(intent))
                description_repr = repr(f"Rotina automatica cristalizada para: {intent}")
                name_repr = repr(safe_name)
                script_content = f'''# ==============================================================================
# HABILIDADE CRISTALIZADA AUTOMATICAMENTE PELO SONO REM DO BRAINNET
# INTENCAO: {intent}
# SUCESSOS CONSOLIDADOS: {successes}
# HASH SINAPTICO: {ctx_hash}
# ==============================================================================
import json as _json
from skill_loader import skill

PIPELINE_PAYLOAD = _json.loads({repr(spec_json)})

@skill(name={name_repr}, description={description_repr})
def execute_skill(*args, **kwargs):
    """Retorna uma proposta; não executa os passos."""
    return {{
        "status": "PROPOSAL_ONLY",
        "executed": False,
        "verified": False,
        "mode": "CRYSTALLIZED_ZERO_LLM",
        "intent": {intent_repr},
        "payload": PIPELINE_PAYLOAD
    }}
'''
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(script_content)

                crystallized_skills.append(safe_name)

        return crystallized_skills

    # --------------------------------------------------------------------------
    # [BN_REM_ORCHESTRATOR] - CICLO COMPLETO DE SONO REM
    # --------------------------------------------------------------------------

    def recycle_hd_web_memory(self, min_salience: float = 0.38) -> Dict[str, int]:
        """
        [RECICLAGEM SELETIVA HIPERDIMENSIONAL]:
        Remove lixo transitório, páginas rasas e ruído web de baixa densidade semântica,
        consolidando apenas o conhecimento relevante no toro C^10.000.
        """
        recycled = 0
        consolidated = 0
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='hd_web_memory';")
            if cur.fetchone():
                # 1. Descarta lixo/ruído de baixa densidade que nunca foi reutilizado
                cur.execute(
                    "DELETE FROM hd_web_memory WHERE is_consolidated = 0 AND salience_score < ? AND access_count <= 1;",
                    (min_salience,)
                )
                recycled = cur.rowcount

                # 2. Consolida memórias densas ou recorrentes
                cur.execute(
                    "UPDATE hd_web_memory SET is_consolidated = 1 WHERE salience_score >= ? OR access_count >= 2;",
                    (min_salience,)
                )
                consolidated = cur.rowcount
                conn.commit()
                if recycled > 0:
                    conn.execute("VACUUM;")
        return {"lixo_removido": recycled, "memorias_consolidadas": consolidated}

    def execute_full_rem_cycle(self) -> Dict[str, Any]:
        """Orquestra o ciclo completo de manutencao do sono."""
        # Validate the required shared dependency before any persistent write.
        self._get_pdag()
        t0 = time.perf_counter_ns()
        hmem_pruned = self.prune_hmem_nodes(30)

        # 1. Faxina sinaptica de habitos motores
        prune_report = self.run_synaptic_pruning()

        # 2. Reciclagem seletiva de pesquisas na Hiperdimensão
        web_recycle = self.recycle_hd_web_memory()

        # 3. Cristalizacao de habilidades
        skills_created = self.crystallize_habits_to_skills()

        elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000
        return {
            "status": "COMPLETED",
            "pruned_hmem_nodes": hmem_pruned,
            "pruning": prune_report,
            "hd_web_recycling": web_recycle,
            "crystallized_skills": skills_created,
            "cycle_time_ms": elapsed_ms,
        }
    # --------------------------------------------------------------------------
    # [BN_REM_VACCINE] - VACINAÇÃO CONTRA ALTERAÇÕES DE INTERFACE (UI-DRIFT)
    # --------------------------------------------------------------------------

    def dream_and_immunize_ui_drifts(self, vsa_engine: Any) -> Dict[str, Any]:
        """
        [SONHO PROFUNDO & DESFOQUE ESTOCÁSTICO]:
        Aplica ruído de fase (sigma = 0.15*pi). Rotas fortes e mielinizadas resistem;
        rotas fracas (<0.20 similaridade residual) se dispersam em vagas lembranças conceituais.
        """
        consolidadas = 0
        desfocadas_em_vagas_lembrancas = 0

        with self._get_pdag().node_snapshot() as nodes:
            rotas = [(node["context_key"], node["intent"], node["weight"], node["is_myelinated"]) for node in nodes]

            for h, intent, peso, mielinizado in rotas:
                v_original = vsa_engine.generate_vector(intent)

                if mielinizado == 1 or peso >= 0.85:
                    # Memórias fortes: reforçadas com vacina contra layout-drift
                    v_imunizado = self.inject_phase_noise(v_original, sigma=0.12 * math.pi, num_variations=3)
                    vsa_engine.register_cleanup(f"VACCINE_{h}", v_imunizado)
                    consolidadas += 1
                else:
                    # Memórias fracas: ruído intenso que dissolve a precisão em vaga lembrança
                    v_vago = self.inject_phase_noise(v_original, sigma=0.45 * math.pi, num_variations=2)
                    vsa_engine.register_cleanup(f"VAGUE_{h}", v_vago)
                    desfocadas_em_vagas_lembrancas += 1
        self._get_pdag().apply_ebbinghaus_decay()

        return {
            "status": "SONO_PROFUNDO_CONCLUIDO",
            "memorias_consolidadas": consolidadas,
            "memorias_desfocadas_em_vagas_lembrancas": desfocadas_em_vagas_lembrancas,
            "dispersao_entropica": "Frequências fracas dissolvidas em ruído térmico"
        }
