# ==============================================================================
# BRAINNET v7 - SISTEMA OPERACIONAL COGNITIVO
# MODULO: world_model_engine.py
# FUNCAO: Motor de Modelo de Mundo, Autoconsciencia de Hardware (Win11 LTSC),
#         Inspecao Semantica de Aplicativos e Projecao Passado/Futuro.
# ==============================================================================

from __future__ import annotations

import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

BRAIN_DIR = Path(__file__).resolve().parent
if str(BRAIN_DIR) not in sys.path:
    sys.path.insert(0, str(BRAIN_DIR))

from context_capture import ContextCapture
from governance import SystemGovernance
from perception_eye import PerceptionEye, UIControlElement
from hyperdimensional import FHRRHyperdimensionalEngine
from pdag_engine import MyelinatedPDAGEngine


class WorldModelEngine:
    """
    O Córtex de Autoconsciência do BRAINNET.
    Mapeia em tempo real:
    1. O Corpo: CPU Xeon, RAM, VRAM da RX 580.
    2. O Ambiente: O que é o aplicativo em foco e para que servem seus controles.
    3. A Linha do Tempo: Memória episódica (Passado) e Hipótese causal (Futuro).
    """

    __slots__ = (
        "ctx_engine",
        "governance",
        "eye",
        "vsa",
        "pdag",
        "historico_episodico",
        "hipotese_futura_ativa"
    )

    def __init__(
        self,
        ctx_engine: ContextCapture,
        governance: SystemGovernance,
        eye: PerceptionEye,
        vsa: FHRRHyperdimensionalEngine,
        pdag: MyelinatedPDAGEngine
    ) -> None:
        self.ctx_engine = ctx_engine
        self.governance = governance
        self.eye = eye
        self.vsa = vsa
        self.pdag = pdag
        self.historico_episodico: List[Dict[str, Any]] = []
        self.hipotese_futura_ativa: Optional[Dict[str, Any]] = None

    def capturar_estado_consciente(self) -> Dict[str, Any]:
        """
        Retorna a fotografia completa da autoconsciência do organismo:
        [Hardware + Identidade do App + Controles Semânticos + Linha do Tempo]
        """
        t0 = time.perf_counter_ns()

        # 1. ESTADO DO CORPO (Propriocepção no Windows 11 LTSC)
        cpu = self.governance.get_cpu_metrics()
        ram = self.governance.get_ram_metrics()
        vram = self.governance.get_vram_metrics()
        
        estado_hardware = {
            "cpu_total_pct": cpu.total_usage_pct,
            "cpu_threads_ativas": cpu.thread_count,
            "ram_usada_mb": ram.used_mb,
            "ram_livre_mb": ram.available_mb,
            "vram_rx580_usada_mb": vram.used_mb,
            "vram_rx580_livre_mb": vram.free_mb,
        }

        # 2. ESTADO DO AMBIENTE (Janela e Identidade do Aplicativo)
        ctx = self.ctx_engine.capture_foreground_context()
        hwnd = ctx.get("hwnd", 0)

        # 3. SEMIÓTICA DA INTERFACE (Descoberta automática de botões e caixas de texto)
        controles_nativos = self.eye.scan_window_controls(hwnd) if hwnd else []
        mapa_affordances = []
        for c in controles_nativos[:25]:  # Top elementos estruturais mais relevantes
            if c.name or c.class_name in ("Edit", "Button", "RichEdit20W"):
                tipo_funcional = "ACAO" if "Button" in c.class_name else ("DIGITACAO" if "Edit" in c.class_name else "INFORMATIVO")
                mapa_affordances.append({
                    "nome": c.name or "[Sem Rótulo]",
                    "classe": c.class_name,
                    "tipo": tipo_funcional,
                    "posicao_rel_pct": c.rel_center_pct
                })

        # 4. LINHA DO TEMPO (Passado Recente e Próximo Passo Previsto)
        ultimo_passo = self.historico_episodico[-1] if self.historico_episodico else {"acao": "NENHUMA", "delta": "INICIO"}
        
        latencia_ms = (time.perf_counter_ns() - t0) / 1_000_000.0

        return {
            "timestamp": time.time(),
            "hardware": estado_hardware,
            "janela_ativa": {
                "titulo": ctx.get("title", ""),
                "processo": ctx.get("process_name", ""),
                "menu_iniciar_aberto": ctx.get("start_menu_open", False)
            },
            "affordances_detectadas": mapa_affordances,
            "linha_do_tempo": {
                "o_que_fez_passado": ultimo_passo,
                "o_que_vai_fazer_futuro": self.hipotese_futura_ativa or "AGUARDANDO_INTENCAO"
            },
            "latencia_introspeccao_ms": round(latencia_ms, 2)
        }

    def projetar_acao_futura(self, intencao_geral: str, estado_atual: Dict[str, Any]) -> Dict[str, Any]:
        """
        [CÓRTEX PREDITIVO CAUSAL]:
        Analisa a intenção e os botões reais da janela ativa.
        Deduz o que o aplicativo faz e projeta a hipótese do próximo passo.
        """
        app_nome = estado_atual["janela_ativa"]["processo"]
        titulo = estado_atual["janela_ativa"]["titulo"]
        affordances = estado_atual["affordances_detectadas"]

        # Procura pistas semânticas universais nos controles descobertos
        alvo_candidato = None
        for item in affordances:
            rotulo = item["nome"].lower()
            # Se a intenção for pesquisar/buscar e o controle tiver pistas de busca
            if any(k in intencao_geral.lower() for k in ["busque", "pesquise", "procure", "ache"]):
                if any(k in rotulo for k in ["pesquisar", "buscar", "search", "localizar", "encontrar"]):
                    alvo_candidato = item
                    break

        if alvo_candidato:
            hipotese = {
                "hipotese_causal": f"Eu clicarei no controle '{alvo_candidato['nome']}' ({alvo_candidato['tipo']}) para habilitar a busca no aplicativo {app_nome}.",
                "acao_planejada": {
                    "tipo": "CLIQUE_AFFORDANCE",
                    "rotulo": alvo_candidato["nome"],
                    "coords_pct": alvo_candidato["posicao_rel_pct"]
                },
                "expectativa_de_mudanca": "O campo de texto deve receber foco e o cursor deve ficar ativo."
            }
        else:
            hipotese = {
                "hipotese_causal": f"Como o alvo não tem botão explícito visível, dispararei o atalho universal de navegação do Windows para {app_nome}.",
                "acao_planejada": {"tipo": "TECLADO_EXPLORACAO", "comando": "tab_ou_atalho"},
                "expectativa_de_mudanca": "A janela deve alterar o elemento focado."
            }

        self.hipotese_futura_ativa = hipotese
        return hipotese

    def registrar_desfecho_episodico(self, acao_executada: Dict[str, Any], houve_delta: bool) -> None:
        """Registra no Passado o resultado real, aplicando valência afetiva em 10.000D."""
        desfecho = {
            "acao": acao_executada,
            "delta_confirmado": houve_delta,
            "valencia_somatica": "ALIVIO" if houve_delta else "FRUSTRACAO",
            "tempo": time.time()
        }
        self.historico_episodico.append(desfecho)
        if len(self.historico_episodico) > 50:
            self.historico_episodico.pop(0)

        # Grava hipervetor na memória FHRR
        v_estado = self.vsa.generate_vector(f"EPISODIO_{len(self.historico_episodico)}")
        v_resultado = self.vsa.somatic_alivio if houve_delta else self.vsa.somatic_frustracao
        v_final = self.vsa.bind(v_estado, v_resultado)
        self.vsa.register_cleanup(f"MEM_{int(time.time())}", v_final)


# ==============================================================================
# DEMONSTRAÇÃO PRÁTICA: O AGENTE ENXERGANDO O PRÓPRIO CORPO E A TELA
# ==============================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("BRAINNET v7 - TESTE DO MOTOR DE AUTOCONSCIÊNCIA (WORLD MODEL ENGINE)")
    print("=" * 70)

    ctx = ContextCapture()
    gov = SystemGovernance()
    eye = PerceptionEye()
    vsa = FHRRHyperdimensionalEngine(dimension=10_000)
    pdag = MyelinatedPDAGEngine(db_path="core1_pdag.db")

    motor_mundo = WorldModelEngine(ctx, gov, eye, vsa, pdag)

    print("\n[1. INTROSPECÇÃO DO CORPO E AMBIENTE]: Mapeando estado do sistema...")
    estado = motor_mundo.capturar_estado_consciente()

    print("\n>>> CORPO (WINDOWS 11 LTSC + XEON + RX 580) <<<")
    print(f"  CPU Total: {estado['hardware']['cpu_total_pct']}% | Threads: {estado['hardware']['cpu_threads_ativas']}")
    print(f"  RAM em Uso: {estado['hardware']['ram_usada_mb']} MB (Livre: {estado['hardware']['ram_livre_mb']} MB)")
    print(f"  VRAM RX 580: {estado['hardware']['vram_rx580_usada_mb']} MB (Livre: {estado['hardware']['vram_rx580_livre_mb']} MB)")

    print("\n>>> AMBIENTE ATIVO (JANELA EM PRIMEIRO PLANO) <<<")
    print(f"  Título: '{estado['janela_ativa']['titulo']}'")
    print(f"  Processo: '{estado['janela_ativa']['processo']}'")
    print(f"  Controles Semânticos Descobertos na Tela: {len(estado['affordances_detectadas'])} elementos")
    for idx, aff in enumerate(estado['affordances_detectadas'][:5]):
        print(f"    [{idx+1}] {aff['tipo']} -> '{aff['nome']}' ({aff['classe']}) em {aff['posicao_rel_pct']}%")

    print("\n>>> LINHA DO TEMPO (PASSADO & FUTURO) <<<")
    intencao = "Pesquisar contato ou documento"
    futuro = motor_mundo.projetar_acao_futura(intencao, estado)
    print(f"  O que ele fez (Passado): {estado['linha_do_tempo']['o_que_fez_passado']}")
    print(f"  O que ele vai fazer (Hipótese de Futuro):")
    print(f"    -> {futuro['hipotese_causal']}")
    print(f"    -> Ação Prevista: {futuro['acao_planejada']}")
    print(f"    -> Expectativa: {futuro['expectativa_de_mudanca']}")
    print(f"\n  Latência da Introspecção: {estado['latencia_introspeccao_ms']} ms (Zero-LLM)")
    print("=" * 70)