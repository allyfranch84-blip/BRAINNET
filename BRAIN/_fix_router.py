from pathlib import Path
import ast

p = Path(r'A:\BRAINNET\BRAIN\router.py')
src = p.read_text(encoding='utf-8')

# 1. __slots__
if '"_semantic_layer"' not in src:
    src = src.replace('"attractor_direct"\n    )', '"attractor_direct",\n        "_semantic_layer",\n    )')

# 2. __init__
if 'self._semantic_layer = None' not in src:
    src = src.replace('self._qwen_deep = qwen_deep', 'self._qwen_deep = qwen_deep\n        self._semantic_layer = None')

# 3. _get_semantic_layer
if 'def _get_semantic_layer' not in src:
    helper = '''    def _get_semantic_layer(self):
        if self._semantic_layer is None:
            try:
                from semantic_layer import SemanticLayer
                self._semantic_layer = SemanticLayer()
            except Exception as ex:
                logger.debug(f"[ROUTER] semantic_layer init falhou: {ex}")
        return self._semantic_layer

    def decompose_pipeline(self, prompt: str) -> List[str]:'''
    src = src.replace('def decompose_pipeline(self, prompt: str) -> List[str]:', helper)

# 4. evaluate_route replacement
start_marker = '# 1. Projeção Contrafactual da Intenção no Espaço Hiperdimensional'
end_marker = '        # Rota Causal / Ação Operacional (Padrão Invariante)'

start_idx = src.find(start_marker)
end_idx = src.find(end_marker)

if start_idx != -1 and end_idx != -1:
    new_block = '''# 1. Classificação Semântica (PV11-1b)
        _layer = self._get_semantic_layer()
        _category = "TEORICO"
        _confidence = 0.0
        if _layer is not None:
            try:
                _r = _layer.classify(prompt_raw, ["FISICO", "OPERACIONAL", "AFETO", "SOCIAL", "TEORICO"])
                _category = _r.get("category", "TEORICO")
                _confidence = float(_r.get("confidence", 0.0))
            except Exception as ex:
                logger.debug(f"[ROUTER] semantic_layer falhou: {ex}")

        # 2. Decomposição de Etapas Sequenciais
        etapas = self.decompose_pipeline(prompt_raw)
        if len(etapas) > 1:
            elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000.0
            return RouteDecision(
                mode="COMPOUND_PIPELINE",
                target_model=None,
                direct_reply=None,
                mentor_data={"steps": etapas},
                complexity_score=0.5,
                rationale=f"Pipeline não-linear encadeado com {len(etapas)} portais conceituais",
                budget_ms=elapsed_ms,
            )

        # 3. Rota Direta (Fast-Path)
        if _category == "OPERACIONAL" and _confidence >= 0.60:
            _target = self._qwen_deep
            if self.homeostasis is not None:
                complexity = min(1.0, len(prompt_raw) / 100.0)
                if not self.homeostasis.should_use_deep_brain(complexity):
                    _target = self._qwen_fast
            elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000.0
            return RouteDecision(
                mode="DETERMINISTIC_ACTION",
                target_model=_target,
                direct_reply=None,
                mentor_data={"raw_intent": prompt_raw},
                complexity_score=round(_confidence, 3),
                rationale=f"Comando direto (semantic OPERACIONAL conf={_confidence:.2f})",
                budget_ms=elapsed_ms,
            )

        # Viés contextual de tela ativa
        _has_deictic = any(w in prompt_raw.lower() for w in ["esse", "essa", "aqui", "isso", "tela", "olhe", "veja"])
        if context and context.get("title") and _has_deictic:
            _has_deictic = True

        elapsed_ms = (time.perf_counter_ns() - t0) / 1_000_000.0

        # Rota Visual
        if _has_deictic:
            return RouteDecision(
                mode="INSPECT_SCREEN",
                target_model=None,
                direct_reply=None,
                mentor_data={"query": prompt_raw},
                complexity_score=round(_confidence, 3),
                rationale="Ativação do canal visual por sinal dêitico",
                budget_ms=elapsed_ms,
            )

'''
    src = src[:start_idx] + new_block + src[end_idx:]

# 5. Fix sim_deep in DEEP_PATH (if it still exists)
if 'complexity_score=round(sim_deep, 3),' in src:
    src = src.replace('complexity_score=round(sim_deep, 3),', 'complexity_score=round(_confidence, 3),')

# Verify syntax before writing
try:
    ast.parse(src)
    p.write_text(src, encoding='utf-8')
    print("OK: router.py corrigido totalmente com sintaxe validada.")
except SyntaxError as e:
    print(f"ERRO DE SINTAXE: {e}")