# =============================================================================
# council/mission_planner.py — Transforma intenção em plano executável
# =============================================================================

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from .mission_contract import Mission, ActionKind
from .mission_state import MissionState

if TYPE_CHECKING:
    from architecture_reasoner import ArchitectureReasoner

logger = logging.getLogger("Council.Planner")


@dataclass
class MissionPlan:
    """
    A representação final e imutável do que será executado.
    Nenhum módulo abaixo deste nível (PromptBuilder, Dispatcher) 
    tem permissão para alterar este plano.
    """
    objective: str
    strategy: str                 # Ex: "architect_first", "direct_impl"
    context_files: list[str]      # Arquivos que devem ser lidos
    ordered_files: list[str]      # Arquivos na ordem exata de modificação (Topological sort)
    required_tests: list[str]     # Testes que devem ser executados ao final
    architect_model: Optional[str] = None
    implementer_model: str = "deepseek"
    reviewers: list[str] = field(default_factory=list)
    
    # Metadados de segurança
    risk_level: str = "low"       # low | medium | high
    rollback_plan: list[str] = field(default_factory=list)
    
    # Contexto extra
    reasoning_log: list[str] = field(default_factory=list)


class MissionPlanner:
    """
    O maestro da Fase 1. Pega a decisão do ReasoningEngine e cruza com 
    o grafo de arquitetura real da Brainnet.
    """

    def __init__(self, reasoner: "ArchitectureReasoner"):
        self.reasoner = reasoner

    def plan(self, mission: Mission, state: MissionState, strategy: str = "architect_first") -> MissionPlan:
        """
        Recebe a missão crua e cospe o plano de execução detalhado.
        """
        logger.info(f"MissionPlanner gerando plano para: {mission.objective}")
        state.current_step = "planning"
        log: list[str] = []

        # ---------------------------------------------------------
        # 1. Análise de Contexto (via ArchitectureReasoner)
        # ---------------------------------------------------------
        context_files: list[str] = []
        ordered_files: list[str] = []
        required_tests: list[str] = []

        log.append("Buscando arquivos-alvo no ArchitectureReasoner...")
        
        # O Reasoner (que criamos na Parte 2) tem o método find_where_to_change
        if hasattr(self.reasoner, "where_to_change"):
            # Pega os top 5 arquivos mais prováveis
            candidates = self.reasoner.where_to_change(mission.objective, limit=5)
            context_files = [c.file for c in candidates if c.file]
            log.append(f"Candidatos encontrados: {', '.join(context_files)}")
        else:
            log.append("Aviso: ArchitectureReasoner não possui where_to_change(). Usando lista vazia.")
            context_files = mission.scope.allowed_files[:3] # fallback

        # ---------------------------------------------------------
        # 2. Ordenação Topológica (Dependências primeiro)
        # ---------------------------------------------------------
        if context_files and hasattr(self.reasoner, "get_dependencies"):
            log.append("Calculando ordem topológica de modificação...")
            # Aqui o MissionPlanner delega para a inteligência do Reasoner
            # Lógica simplificada: dependências primeiro.
            ordered_files = self._topological_sort(context_files)
            log.append(f"Ordem de execução: {' -> '.join(ordered_files)}")
        else:
            ordered_files = context_files

        # ---------------------------------------------------------
        # 3. Seleção de Testes (TestIndex)
        # ---------------------------------------------------------
        log.append("Buscando testes relacionados...")
        if hasattr(self.reasoner, "which_tests"):
            for f in ordered_files:
                # Pede os testes para cada arquivo que será alterado
                tests = self.reasoner.which_tests(f)
                for t in tests:
                    if t.file not in required_tests:
                        required_tests.append(t.file)
        
        # Se não achou testes específicos, coloca um genérico ou vazio
        log.append(f"Testes obrigatórios: {', '.join(required_tests) or 'Nenhum mapeado'}")

        # ---------------------------------------------------------
        # 4. Avaliação de Risco e Rollback
        # ---------------------------------------------------------
        risk = self._estimate_risk(ordered_files, required_tests)
        rollback = [f"git checkout HEAD -- {f}" for f in ordered_files]
        log.append(f"Risco estimado: {risk.upper()}")

        # ---------------------------------------------------------
        # 5. Definição de Modelos baseada na Estratégia
        # ---------------------------------------------------------
        if strategy == "architect_first":
            arch = "chatgpt"
            impl = "deepseek"
            reviewers = ["chatgpt", "deepseek"]
        elif strategy == "direct_impl":
            arch = None
            impl = "deepseek"
            reviewers = ["chatgpt"]
        else: # consensus
            arch = "chatgpt"
            impl = "chatgpt"
            reviewers = ["deepseek"]

        # ---------------------------------------------------------
        # 6. Monta o Plano Final
        # ---------------------------------------------------------
        plan = MissionPlan(
            objective=mission.objective,
            strategy=strategy,
            context_files=context_files,
            ordered_files=ordered_files,
            required_tests=required_tests,
            architect_model=arch,
            implementer_model=impl,
            reviewers=reviewers,
            risk_level=risk,
            rollback_plan=rollback,
            reasoning_log=log
        )

        # Grava no estado da missão para auditoria
        state.record_artifact("mission_plan", plan)
        log.append("MissionPlan gerado com sucesso.")
        
        return plan

    # -------------------------------------------------------------------------
    # Métodos Auxiliares
    # -------------------------------------------------------------------------

    def _topological_sort(self, files: list[str]) -> list[str]:
        """
        Ordena os arquivos para que dependências sejam alteradas antes dos dependentes.
        Usa o grafo do ArchitectureReasoner (se disponível).
        """
        if not hasattr(self.reasoner, "graph"):
            return files # fallback: mantém a ordem original

        graph = self.reasoner.graph
        # Mapeia path -> module
        path_to_mod = {f.path: f.module for f in self.reasoner.indexer.files.values()}
        
        mods_to_change = [path_to_mod[f] for f in files if f in path_to_mod]
        
        # DFS simples para ordenar
        visited = set()
        order = []
        
        def visit(node):
            if node in visited: return
            visited.add(node)
            # Visita dependências primeiro
            for dep in graph.get_dependencies(node):
                if dep in mods_to_change:
                    visit(dep)
            order.append(node)

        for mod in mods_to_change:
            visit(mod)

        # Mapeia de volta para path, mantendo a ordem
        mod_to_path = {v: k for k, v in path_to_mod.items()}
        return [mod_to_path[m] for m in order if m in mod_to_path]

    def _estimate_risk(self, files: list[str], tests: list[str]) -> str:
        """Heurística simples de risco baseada no volume e testes."""
        if not files:
            return "low"
        if len(files) > 5:
            return "high"
        if not tests:
            return "high" # Sem testes = risco alto
        if len(files) > 2:
            return "medium"
        return "low"