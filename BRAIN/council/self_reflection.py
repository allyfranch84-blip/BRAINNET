# =============================================================================
# council/self_reflection.py — Aprendizado Pós-Missão
# =============================================================================

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .mission_context import MissionContext
from .knowledge_indexer import KnowledgeIndexer

logger = logging.getLogger("Council.SelfReflection")

class BrainSelfReflection:
    """
    Analisa o resultado da missão e escreve um relatório permanente.
    Alimenta o KnowledgeIndexer para que missões futuras aprendam com esta.
    """
    
    def __init__(self, knowledge_indexer: KnowledgeIndexer, reports_dir: str | Path):
        self.knowledge = knowledge_indexer
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def reflect(self, ctx: MissionContext, outcome: str, test_results: list[dict], git_diff: str) -> Path:
        """
        Gera o relatório e atualiza o KnowledgeIndexer.
        outcome: 'success' | 'failed' | 'aborted'
        """
        logger.info(f"Iniciando SelfReflection para missão {ctx.mission.mission_id}")
        
        report_md = self._build_report_md(ctx, outcome, test_results, git_diff)
        
        # Salva o relatório em disco
        report_file = self.reports_dir / f"mission_{ctx.mission.mission_id}.md"
        report_file.write_text(report_md, encoding="utf-8")
        
        # Alimenta o Knowledge Indexer com este novo relatório
        self.knowledge.ingest_file(report_file)
        self.knowledge.save()
        
        # Aqui o ReasoningEngine poderia atualizar o reasoning_memory.db
        # (mencionado no texto anterior) para calibrar heurísticas.
        
        return report_file

    def _build_report_md(self, ctx: MissionContext, outcome: str, test_results: list[dict], git_diff: str) -> str:
        lines = []
        lines.append(f"# Mission Report: {ctx.mission.mission_id}")
        lines.append(f"**Data:** {datetime.now(timezone.utc).isoformat()}")
        lines.append(f"**Objetivo:** {ctx.mission.objective}")
        lines.append(f"**Resultado:** {outcome.upper()}")
        lines.append("")
        
        lines.append("## Plano Executado")
        if ctx.plan:
            lines.append(f"- **Estratégia:** {ctx.plan.strategy}")
            lines.append(f"- **Arquivos alterados:** {', '.join(ctx.plan.ordered_files)}")
            lines.append(f"- **Testes executados:** {', '.join(ctx.plan.required_tests)}")
            lines.append(f"- **Nível de risco:** {ctx.plan.risk_level}")
        lines.append("")

        lines.append("## Resultados dos Testes")
        for t in test_results:
            status = "✅ PASS" if t.get("status") == "PASS" else "❌ FAIL"
            lines.append(f"- {t.get('test_id')}: {status}")
            if t.get("status") != "PASS" and t.get("stderr"):
                lines.append(f"  ```\n  {t.get('stderr')[:500]}\n  ```")
        lines.append("")

        lines.append("## Lições Aprendidas (Self-Reflection)")
        if outcome == "failed":
            lines.append("- **O que falhou:** A execução não passou nos testes.")
            lines.append("- **Ação futura:** Na próxima tentativa, incluir mais evidências no prompt ou revisar a ordem das dependências.")
        else:
            lines.append("- A estratégia utilizada foi eficiente e pode ser repetida para missões similares.")
        lines.append("")

        if git_diff:
            lines.append("## Git Diff (Amostra)")
            lines.append(f"```diff\n{git_diff[:2000]}\n```")

        return "\n".join(lines)