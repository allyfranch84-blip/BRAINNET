# -*- coding: utf-8 -*-
"""
ArchitectureReasoner — Grafo Unificado + Impacto + Planejamento
================================================================

Complementa o ArchitectureIndexer (Parte 1) e adiciona:
    1.  ArchitectureGraph unificado e tipado (substitui call_graph isolado)
    2.  Impact Analysis (find_impacted)
    3.  Confidence Layer (confidence / reason / distance / references)
    4.  Histórico de snapshots (architecture_history/)
    5.  Patch Planner (plan_patch)
    6.  Test Index (símbolo -> testes)
    7.  Ownership Registry
    8.  Workspace Knowledge (namespaces separados)
    9.  Memória Semântica (embeddings plugáveis)
    10. Mission Log
    11. ArchitectureReasoner (fachada de alto nível)

Uso:
    from architecture_reasoner import ArchitectureReasoner
    r = ArchitectureReasoner("/caminho/brainnet")
    r.initialize()

    # Respondendo ao MissionExecutor
    r.where_to_change("onde alterar DeepThink?")
    r.what_breaks("semantic_move")
    r.which_tests("motor_intent.execute")
    r.plan_patch("adicionar validação no DeepThink")

CLI:
    python architecture_reasoner.py --init
    python architecture_reasoner.py --where "DeepThink"
    python architecture_reasoner.py --breaks semantic_move
    python architecture_reasoner.py --plan "adicionar validação no DeepThink"
    python architecture_reasoner.py --similar "gerenciamento de intenções"
    python architecture_reasoner.py --snapshot --tag "pos-refactor"
    python architecture_reasoner.py --history
    python architecture_reasoner.py --diff 1:2
    python architecture_reasoner.py --stats
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol, Set, Tuple

# Importa a Parte 1
try:
    from architecture_indexer import (
        ArchitectureIndexer,
        FileInfo,
        FunctionInfo,
        ClassInfo,
        GlobalVariable,
        ImportInfo,
        CallEdge,
        DependencyEdge,
        VERSION,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from architecture_indexer import (  # type: ignore
        ArchitectureIndexer,
        FileInfo,
        FunctionInfo,
        ClassInfo,
        GlobalVariable,
        ImportInfo,
        CallEdge,
        DependencyEdge,
        VERSION,
    )

logger = logging.getLogger("ArchitectureReasoner")

REASONER_VERSION = f"{VERSION}+reasoner.1.0"
HISTORY_DIR = "architecture_history"
WORKSPACE_DIR = "workspace_knowledge"
OWNERSHIP_FILE = "ownership.json"
TEST_INDEX_FILE = "test_index.json"
MISSIONS_FILE = "missions.jsonl"


# =============================================================================
# PARTE 1 — GRAFO UNIFICADO
# =============================================================================


class NodeKind(str, Enum):
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    CONSTANT = "constant"
    TEST = "test"
    FILE = "file"


class EdgeKind(str, Enum):
    IMPORTS = "imports"
    CALLS = "calls"
    USES = "uses"
    INHERITS = "inherits"
    OVERRIDES = "overrides"
    CONTAINS = "contains"
    DEPENDS_ON = "depends_on"
    TESTS = "tests"
    OWNED_BY = "owned_by"


def node_id(kind: NodeKind, qualname: str) -> str:
    return f"{kind.value}:{qualname}"


@dataclass
class GraphNode:
    id: str
    kind: NodeKind
    name: str
    module: Optional[str] = None
    file: Optional[str] = None
    lineno: int = 0
    qualname: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "name": self.name,
            "module": self.module,
            "file": self.file,
            "lineno": self.lineno,
            "qualname": self.qualname,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GraphNode":
        return cls(
            id=d["id"],
            kind=NodeKind(d["kind"]),
            name=d["name"],
            module=d.get("module"),
            file=d.get("file"),
            lineno=d.get("lineno", 0),
            qualname=d.get("qualname"),
            metadata=d.get("metadata", {}),
        )


@dataclass
class GraphEdge:
    source: str
    target: str
    kind: EdgeKind
    weight: float = 1.0
    lineno: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind.value,
            "weight": self.weight,
            "lineno": self.lineno,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GraphEdge":
        return cls(
            source=d["source"],
            target=d["target"],
            kind=EdgeKind(d["kind"]),
            weight=d.get("weight", 1.0),
            lineno=d.get("lineno", 0),
            metadata=d.get("metadata", {}),
        )


class ArchitectureGraph:
    """
    Grafo único e tipado. Qualquer algoritmo (impacto, planejamento,
    raciocínio) navega por aqui — não pelo call_graph isolado.
    """

    def __init__(self) -> None:
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: List[GraphEdge] = []
        self._out: Dict[str, List[GraphEdge]] = defaultdict(list)
        self._in: Dict[str, List[GraphEdge]] = defaultdict(list)

    # ---------- mutação ----------

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        # dedupe: soma peso em vez de duplicar
        for e in self._out[edge.source]:
            if e.target == edge.target and e.kind == edge.kind:
                e.weight += edge.weight
                return
        self.edges.append(edge)
        self._out[edge.source].append(edge)
        self._in[edge.target].append(edge)

    # ---------- navegação ----------

    def get_node(self, nid: str) -> Optional[GraphNode]:
        return self.nodes.get(nid)

    def neighbors(
        self,
        nid: str,
        kinds: Optional[Set[EdgeKind]] = None,
        direction: str = "out",
    ) -> List[Tuple[GraphNode, GraphEdge]]:
        edges = self._out[nid] if direction == "out" else self._in[nid]
        result = []
        for e in edges:
            if kinds and e.kind not in kinds:
                continue
            other_id = e.target if direction == "out" else e.source
            other = self.nodes.get(other_id)
            if other is not None:
                result.append((other, e))
        return result

    def bfs(
        self,
        start: str,
        max_depth: int = 5,
        kinds: Optional[Set[EdgeKind]] = None,
        direction: str = "out",
    ) -> List[Tuple[GraphNode, int]]:
        visited: Dict[str, int] = {start: 0}
        queue: deque = deque([(start, 0)])
        result: List[Tuple[GraphNode, int]] = []
        while queue:
            cur, depth = queue.popleft()
            if depth > 0:
                n = self.nodes.get(cur)
                if n:
                    result.append((n, depth))
            if depth >= max_depth:
                continue
            dirs = ["out", "in"] if direction == "both" else [direction]
            for d in dirs:
                for neighbor, _edge in self.neighbors(cur, kinds, d):
                    if neighbor.id in visited and visited[neighbor.id] <= depth + 1:
                        continue
                    visited[neighbor.id] = depth + 1
                    queue.append((neighbor.id, depth + 1))
        return result

    def find_nodes(
        self,
        kind: Optional[NodeKind] = None,
        name: Optional[str] = None,
        qualname: Optional[str] = None,
        module: Optional[str] = None,
        file: Optional[str] = None,
    ) -> List[GraphNode]:
        out = []
        for n in self.nodes.values():
            if kind is not None and n.kind != kind:
                continue
            if name is not None and n.name != name:
                continue
            if qualname is not None and n.qualname != qualname:
                continue
            if module is not None and n.module != module:
                continue
            if file is not None and n.file != file:
                continue
            out.append(n)
        return out

    # ---------- serialização ----------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ArchitectureGraph":
        g = cls()
        for nd in d.get("nodes", []):
            g.add_node(GraphNode.from_dict(nd))
        for ed in d.get("edges", []):
            g.add_edge(GraphEdge.from_dict(ed))
        return g

    def stats(self) -> Dict[str, Any]:
        nodes_by_kind: Dict[str, int] = defaultdict(int)
        for n in self.nodes.values():
            nodes_by_kind[n.kind.value] += 1
        edges_by_kind: Dict[str, int] = defaultdict(int)
        for e in self.edges:
            edges_by_kind[e.kind.value] += 1
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "nodes_by_kind": dict(nodes_by_kind),
            "edges_by_kind": dict(edges_by_kind),
        }


def build_graph_from_indexer(indexer: ArchitectureIndexer) -> ArchitectureGraph:
    """Materializa o ArchitectureGraph a partir do ArchitectureIndexer."""
    g = ArchitectureGraph()

    # ---- módulos, classes, funções, variáveis ----
    for fi in indexer.files.values():
        mid = node_id(NodeKind.MODULE, fi.module)
        g.add_node(GraphNode(
            id=mid,
            kind=NodeKind.MODULE,
            name=fi.module,
            module=fi.module,
            file=fi.path,
            qualname=fi.module,
            metadata={
                "line_count": fi.line_count,
                "docstring": fi.docstring,
            },
        ))

        # classes
        for cqn in fi.classes:
            c = indexer.classes.get(cqn)
            if not c:
                continue
            cid = node_id(NodeKind.CLASS, cqn)
            g.add_node(GraphNode(
                id=cid,
                kind=NodeKind.CLASS,
                name=c.name,
                module=c.module,
                file=c.file,
                lineno=c.lineno,
                qualname=c.qualname,
                metadata={
                    "bases": c.bases,
                    "decorators": c.decorators,
                    "docstring": c.docstring,
                },
            ))
            g.add_edge(GraphEdge(source=mid, target=cid, kind=EdgeKind.CONTAINS))

        # funções e métodos
        for fqn in fi.functions:
            f = indexer.functions.get(fqn)
            if not f:
                continue
            fkind = NodeKind.METHOD if f.is_method else NodeKind.FUNCTION
            fid = node_id(fkind, fqn)
            g.add_node(GraphNode(
                id=fid,
                kind=fkind,
                name=f.name,
                module=f.module,
                file=f.file,
                lineno=f.lineno,
                qualname=f.qualname,
                metadata={
                    "signature": f.signature,
                    "complexity": f.complexity,
                    "is_async": f.is_async,
                    "docstring": f.docstring,
                    "num_params": f.num_params,
                },
            ))
            if f.is_method and f.qualname.count(".") >= 2:
                parent_class_qn = ".".join(f.qualname.split(".")[:-1])
                pcid = node_id(NodeKind.CLASS, parent_class_qn)
                if pcid in g.nodes:
                    g.add_edge(GraphEdge(source=pcid, target=fid,
                                         kind=EdgeKind.CONTAINS))
                # override?
                for base_node, _e in g.neighbors(pcid, {EdgeKind.INHERITS}):
                    for sub, _e2 in g.neighbors(base_node.id, {EdgeKind.CONTAINS}):
                        if sub.name == f.name:
                            g.add_edge(GraphEdge(
                                source=fid, target=sub.id,
                                kind=EdgeKind.OVERRIDES,
                            ))
            else:
                g.add_edge(GraphEdge(source=mid, target=fid,
                                     kind=EdgeKind.CONTAINS))

        # variáveis/constantes
        for gqn in fi.globals:
            gv = indexer.globals.get(gqn)
            if not gv:
                continue
            gkind = NodeKind.CONSTANT if gv.is_constant else NodeKind.VARIABLE
            gid = node_id(gkind, gqn)
            g.add_node(GraphNode(
                id=gid,
                kind=gkind,
                name=gv.name,
                module=gv.module,
                file=gv.file,
                lineno=gv.lineno,
                qualname=gv.qualname,
                metadata={"value": gv.value_repr},
            ))
            g.add_edge(GraphEdge(source=mid, target=gid,
                                 kind=EdgeKind.CONTAINS))

    # ---- imports / dependências ----
    for d in indexer.dependencies:
        src = node_id(NodeKind.MODULE, d.source_module)
        tgt = node_id(NodeKind.MODULE, d.target_module)
        if src in g.nodes and tgt in g.nodes:
            ek = EdgeKind.IMPORTS if d.kind == "import" else EdgeKind.DEPENDS_ON
            g.add_edge(GraphEdge(source=src, target=tgt, kind=ek,
                                 lineno=d.lineno))

    # ---- herança entre classes ----
    for qn, c in indexer.classes.items():
        cid = node_id(NodeKind.CLASS, qn)
        if cid not in g.nodes:
            continue
        for base_name in c.bases:
            # tenta resolver base -> qualname real
            for other_qn in indexer.classes:
                if other_qn.split(".")[-1] == base_name.split(".")[-1]:
                    bid = node_id(NodeKind.CLASS, other_qn)
                    if bid in g.nodes and bid != cid:
                        g.add_edge(GraphEdge(source=cid, target=bid,
                                             kind=EdgeKind.INHERITS))
                        break

    # ---- chamadas ----
    for caller, callees in indexer.call_graph.items():
        caller_node = None
        for kind in (NodeKind.FUNCTION, NodeKind.METHOD):
            nid = node_id(kind, caller)
            if nid in g.nodes:
                caller_node = nid
                break
        if not caller_node:
            continue
        for callee in callees:
            callee_node = None
            for kind in (NodeKind.FUNCTION, NodeKind.METHOD):
                nid = node_id(kind, callee)
                if nid in g.nodes:
                    callee_node = nid
                    break
            if callee_node:
                g.add_edge(GraphEdge(source=caller_node, target=callee_node,
                                     kind=EdgeKind.CALLS))

    return g


# =============================================================================
# PARTE 2 — IMPACT ANALYSIS
# =============================================================================


@dataclass
class ImpactResult:
    target: str
    direction: str
    impacted: List[Dict[str, Any]]
    total: int
    max_depth: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ImpactAnalyzer:
    """Responde 'o que quebra se eu alterar Y?'."""

    def __init__(self, graph: ArchitectureGraph, indexer: ArchitectureIndexer):
        self.graph = graph
        self.indexer = indexer

    def find_impacted(
        self,
        symbol: str,
        depth: int = 3,
        direction: str = "callers",
        include_tests: bool = True,
    ) -> ImpactResult:
        target_nodes = self._resolve_symbol(symbol)
        if not target_nodes:
            return ImpactResult(symbol, direction, [], 0, depth)

        if direction == "callers":
            kinds, dirs = {EdgeKind.CALLS}, ["in"]
        elif direction == "callees":
            kinds, dirs = {EdgeKind.CALLS}, ["out"]
        elif direction == "importers":
            kinds, dirs = {EdgeKind.IMPORTS, EdgeKind.DEPENDS_ON}, ["in"]
        elif direction == "imports":
            kinds, dirs = {EdgeKind.IMPORTS, EdgeKind.DEPENDS_ON}, ["out"]
        elif direction == "both":
            kinds = {EdgeKind.CALLS, EdgeKind.IMPORTS, EdgeKind.DEPENDS_ON,
                     EdgeKind.INHERITS, EdgeKind.OVERRIDES}
            dirs = ["in", "out"]
        else:
            raise ValueError(f"direction inválido: {direction}")

        seen: Dict[str, int] = {nid: 0 for nid in target_nodes}
        q: deque = deque((nid, 0) for nid in target_nodes)
        impacted: List[Dict[str, Any]] = []

        while q:
            cur, d = q.popleft()
            if d >= depth:
                continue
            for direction_i in dirs:
                for neighbor, edge in self.graph.neighbors(cur, kinds, direction_i):
                    if neighbor.id in seen and seen[neighbor.id] <= d + 1:
                        continue
                    seen[neighbor.id] = d + 1
                    q.append((neighbor.id, d + 1))
                    if not include_tests and self._is_test(neighbor):
                        continue
                    impacted.append({
                        "id": neighbor.id,
                        "kind": neighbor.kind.value,
                        "qualname": neighbor.qualname,
                        "name": neighbor.name,
                        "module": neighbor.module,
                        "file": neighbor.file,
                        "lineno": neighbor.lineno,
                        "distance": d + 1,
                        "via": edge.kind.value,
                    })

        dedup: Dict[str, Dict[str, Any]] = {}
        for item in impacted:
            prev = dedup.get(item["id"])
            if prev is None or prev["distance"] > item["distance"]:
                dedup[item["id"]] = item
        final = sorted(dedup.values(),
                       key=lambda x: (x["distance"], x["file"] or ""))
        return ImpactResult(
            target=symbol, direction=direction,
            impacted=final, total=len(final), max_depth=depth,
        )

    def _resolve_symbol(self, symbol: str) -> List[str]:
        hits: List[str] = []
        for kind in NodeKind:
            nid = node_id(kind, symbol)
            if nid in self.graph.nodes:
                hits.append(nid)
        if hits:
            return hits
        for kind in NodeKind:
            for n in self.graph.find_nodes(kind=kind, name=symbol):
                hits.append(n.id)
        if hits:
            return hits
        for n in self.graph.nodes.values():
            if n.qualname and symbol in n.qualname:
                hits.append(n.id)
        return hits

    def _is_test(self, node: GraphNode) -> bool:
        if not node.file:
            return False
        f = node.file.replace("\\", "/")
        return "test" in Path(f).name.lower() or "/tests/" in f


# =============================================================================
# PARTE 3 — CONFIDENCE
# =============================================================================


@dataclass
class ConfidenceResult:
    file: str
    confidence: float
    reason: str
    distance: int
    references: int
    module: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ConfidenceScorer:
    """
    Atribui {confidence, reason, distance, references} a cada arquivo
    candidato — no formato exato esperado pelo MissionExecutor.
    """

    def __init__(self, graph: ArchitectureGraph, indexer: ArchitectureIndexer):
        self.graph = graph
        self.indexer = indexer

    def score_file(
        self,
        file_path: str,
        reason: str,
        distance: int = 1,
        exact_match: bool = False,
    ) -> ConfidenceResult:
        refs = 0
        module = None
        fi = self.indexer.files.get(file_path)
        if fi:
            module = fi.module
            for fqn in fi.functions:
                refs += len(self.indexer.reverse_call_graph.get(fqn, []))
            for d in self.indexer.dependencies:
                if d.target_module == fi.module:
                    refs += 1

        base = 0.4
        if exact_match:
            base = 0.9
        elif reason.startswith("imports"):
            base = 0.7
        elif reason.startswith("calls"):
            base = 0.8

        dist_penalty = min(0.3, 0.05 * max(0, distance - 1))
        ref_bonus = min(0.10, 0.01 * refs)

        conf = max(0.0, min(1.0, base - dist_penalty + ref_bonus))
        return ConfidenceResult(
            file=file_path,
            confidence=round(conf, 3),
            reason=reason,
            distance=distance,
            references=refs,
            module=module,
        )


# =============================================================================
# PARTE 4 — HISTÓRICO
# =============================================================================


class ArchitectureHistory:
    """Guarda snapshots numerados em architecture_history/."""

    def __init__(self, root: str | Path):
        self.dir = Path(root) / HISTORY_DIR
        self.dir.mkdir(parents=True, exist_ok=True)

    def _next_index(self) -> int:
        idxs: List[int] = []
        for p in self.dir.glob("snapshot_*.json"):
            m = re.search(r"snapshot_(\d+)\.json", p.name)
            if m:
                idxs.append(int(m.group(1)))
        return max(idxs, default=0) + 1

    def save(
        self,
        graph: ArchitectureGraph,
        indexer: ArchitectureIndexer,
        tag: Optional[str] = None,
    ) -> Path:
        idx = self._next_index()
        path = self.dir / f"snapshot_{idx:04d}.json"
        payload = {
            "index": idx,
            "tag": tag,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": REASONER_VERSION,
            "statistics": indexer.statistics,
            "graph": graph.to_dict(),
        }
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def list_snapshots(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for p in sorted(self.dir.glob("snapshot_*.json")):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                out.append({
                    "file": str(p),
                    "index": d.get("index"),
                    "timestamp": d.get("timestamp"),
                    "tag": d.get("tag"),
                    "nodes": len(d.get("graph", {}).get("nodes", [])),
                    "edges": len(d.get("graph", {}).get("edges", [])),
                })
            except Exception:
                continue
        return out

    def diff(self, idx_a: int, idx_b: int) -> Dict[str, Any]:
        a = json.loads(
            (self.dir / f"snapshot_{idx_a:04d}.json").read_text(encoding="utf-8")
        )
        b = json.loads(
            (self.dir / f"snapshot_{idx_b:04d}.json").read_text(encoding="utf-8")
        )
        a_nodes = {n["id"] for n in a["graph"]["nodes"]}
        b_nodes = {n["id"] for n in b["graph"]["nodes"]}
        a_edges = {(e["source"], e["target"], e["kind"])
                   for e in a["graph"]["edges"]}
        b_edges = {(e["source"], e["target"], e["kind"])
                   for e in b["graph"]["edges"]}
        return {
            "from": idx_a,
            "to": idx_b,
            "nodes_added": sorted(b_nodes - a_nodes),
            "nodes_removed": sorted(a_nodes - b_nodes),
            "edges_added": [list(e) for e in sorted(b_edges - a_edges)],
            "edges_removed": [list(e) for e in sorted(a_edges - b_edges)],
        }


# =============================================================================
# PARTE 5 — TEST INDEX
# =============================================================================


@dataclass
class TestInfo:
    test_id: str
    name: str
    file: str
    target_symbol: Optional[str] = None
    last_status: Optional[str] = None
    last_duration: Optional[float] = None
    last_commit: Optional[str] = None
    last_run: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TestIndex:
    """Mapeia símbolos ↔ testes por convenção de nome e imports."""

    def __init__(self, indexer: ArchitectureIndexer):
        self.indexer = indexer
        self.tests: Dict[str, TestInfo] = {}
        self.symbol_to_tests: Dict[str, List[str]] = defaultdict(list)

    def build(self) -> Dict[str, int]:
        self.tests.clear()
        self.symbol_to_tests.clear()
        for fi in self.indexer.files.values():
            is_test_file = (
                Path(fi.path).name.startswith("test_")
                or "/tests/" in fi.path.replace("\\", "/")
            )
            if not is_test_file:
                continue

            target_mod = None
            base = Path(fi.path).stem
            if base.startswith("test_"):
                target_mod = base[5:]

            # mapear por import
            for imp in fi.imports:
                for name in imp.names:
                    for fqn in self.indexer.functions:
                        if fqn.split(".")[-1] == name:
                            if fi.path not in self.symbol_to_tests[fqn]:
                                self.symbol_to_tests[fqn].append(fi.path)
                    for cqn in self.indexer.classes:
                        if cqn.split(".")[-1] == name:
                            if fi.path not in self.symbol_to_tests[cqn]:
                                self.symbol_to_tests[cqn].append(fi.path)
                if imp.module and target_mod and target_mod in imp.module:
                    for fqn in self.indexer.functions:
                        if fqn.startswith(imp.module + "."):
                            if fi.path not in self.symbol_to_tests[fqn]:
                                self.symbol_to_tests[fqn].append(fi.path)

            # cada test_* vira TestInfo
            for fqn in fi.functions:
                f = self.indexer.functions.get(fqn)
                if not f or not f.name.startswith("test_"):
                    continue
                self.tests[fqn] = TestInfo(
                    test_id=fqn, name=f.name, file=fi.path,
                    target_symbol=target_mod,
                )
        return {"tests": len(self.tests),
                "symbols_mapped": len(self.symbol_to_tests)}

    def tests_for(self, symbol: str) -> List[TestInfo]:
        out: List[TestInfo] = []
        seen: Set[str] = set()

        # 1) match exato
        for fpath in self.symbol_to_tests.get(symbol, []):
            for t in self.tests.values():
                if t.file == fpath and t.test_id not in seen:
                    seen.add(t.test_id)
                    out.append(t)

        # 2) match por sufixo
        for fqn, paths in self.symbol_to_tests.items():
            if fqn.endswith("." + symbol) or fqn.split(".")[-1] == symbol:
                for fpath in paths:
                    for t in self.tests.values():
                        if t.file == fpath and t.test_id not in seen:
                            seen.add(t.test_id)
                            out.append(t)
        return out

    def record_run(self, test_id: str, status: str, duration: float,
                   commit: Optional[str] = None) -> None:
        if test_id not in self.tests:
            return
        t = self.tests[test_id]
        t.last_status = status
        t.last_duration = duration
        t.last_commit = commit
        t.last_run = datetime.now(timezone.utc).isoformat()

    def save(self, path: Path) -> None:
        path.write_text(json.dumps({
            "tests": {k: v.to_dict() for k, v in self.tests.items()},
            "symbol_to_tests": dict(self.symbol_to_tests),
        }, indent=2, ensure_ascii=False), encoding="utf-8")

    def load(self, path: Path) -> bool:
        if not path.exists():
            return False
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            self.tests = {k: TestInfo(**v) for k, v in d.get("tests", {}).items()}
            self.symbol_to_tests = defaultdict(
                list, d.get("symbol_to_tests", {})
            )
            return True
        except Exception:
            return False


# =============================================================================
# PARTE 6 — OWNERSHIP
# =============================================================================


@dataclass
class OwnershipInfo:
    file: str
    owner: Optional[str] = None
    status: str = "active"
    coverage: Optional[float] = None
    last_modified: Optional[str] = None
    last_mission: Optional[str] = None
    last_agent: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OwnershipRegistry:
    def __init__(self, root: str | Path):
        self.path = Path(root) / OWNERSHIP_FILE
        self.entries: Dict[str, OwnershipInfo] = {}

    def load(self) -> bool:
        if not self.path.exists():
            return False
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            self.entries = {k: OwnershipInfo(**v) for k, v in d.items()}
            return True
        except Exception:
            return False

    def save(self) -> None:
        self.path.write_text(json.dumps(
            {k: v.to_dict() for k, v in self.entries.items()},
            indent=2, ensure_ascii=False,
        ), encoding="utf-8")

    def get(self, file: str) -> Optional[OwnershipInfo]:
        return self.entries.get(file)

    def set(self, file: str, **kwargs) -> OwnershipInfo:
        e = self.entries.get(file) or OwnershipInfo(file=file)
        for k, v in kwargs.items():
            if hasattr(e, k):
                setattr(e, k, v)
        self.entries[file] = e
        return e

    def compute_from_filesystem(self, indexer: ArchitectureIndexer) -> int:
        count = 0
        for fi in indexer.files.values():
            if fi.path not in self.entries:
                self.entries[fi.path] = OwnershipInfo(file=fi.path)
                count += 1
            self.entries[fi.path].last_modified = datetime.fromtimestamp(
                fi.mtime, tz=timezone.utc
            ).isoformat()
        return count


# =============================================================================
# PARTE 7 — WORKSPACE KNOWLEDGE
# =============================================================================


class WorkspaceStore:
    """Namespaces separados para não misturar arquitetura/chat/notas."""

    NAMESPACES = ("architecture", "workspace", "missions", "chats", "notes")

    def __init__(self, root: str | Path):
        self.base = Path(root) / WORKSPACE_DIR
        for ns in self.NAMESPACES:
            (self.base / ns).mkdir(parents=True, exist_ok=True)

    def put(self, namespace: str, key: str, value: Any) -> Path:
        if namespace not in self.NAMESPACES:
            raise ValueError(f"namespace inválido: {namespace}")
        path = self.base / namespace / f"{key}.json"
        path.write_text(
            json.dumps(value, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def get(self, namespace: str, key: str) -> Optional[Any]:
        if namespace not in self.NAMESPACES:
            return None
        path = self.base / namespace / f"{key}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list(self, namespace: str) -> List[str]:
        if namespace not in self.NAMESPACES:
            return []
        return sorted(p.stem for p in (self.base / namespace).glob("*.json"))


# =============================================================================
# PARTE 8 — MEMÓRIA SEMÂNTICA
# =============================================================================


class EmbeddingBackend(Protocol):
    def embed(self, text: str) -> List[float]:
        ...


class HashEmbeddingBackend:
    """
    Backend determinístico offline (hash de tokens).
    Pode ser trocado por sentence-transformers / OpenAI / etc.
    """

    DIM = 256

    def embed(self, text: str) -> List[float]:
        vec = [0.0] * self.DIM
        for tok in re.findall(r"\w+", text.lower()):
            h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
            vec[h % self.DIM] += 1.0 if (h >> 8) & 1 else -1.0
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


@dataclass
class SemanticEntry:
    id: str
    text: str
    embedding: List[float]
    metadata: Dict[str, Any] = field(default_factory=dict)


class SemanticMemory:
    """Busca vetorial por significado (com backend plugável)."""

    def __init__(self, backend: Optional[EmbeddingBackend] = None):
        self.backend = backend or HashEmbeddingBackend()
        self.entries: Dict[str, SemanticEntry] = {}

    def index(self, entry_id: str, text: str,
              metadata: Optional[Dict[str, Any]] = None) -> None:
        self.entries[entry_id] = SemanticEntry(
            id=entry_id, text=text, embedding=self.backend.embed(text),
            metadata=metadata or {},
        )

    def _cosine(self, a: List[float], b: List[float]) -> float:
        return sum(x * y for x, y in zip(a, b))

    def search(self, query: str, top_k: int = 10,
               threshold: float = 0.0) -> List[Dict[str, Any]]:
        qvec = self.backend.embed(query)
        scored: List[Tuple[float, SemanticEntry]] = []
        for e in self.entries.values():
            s = self._cosine(qvec, e.embedding)
            if s >= threshold:
                scored.append((s, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [{
            "id": e.id, "score": round(s, 4), "text": e.text,
            "metadata": e.metadata,
        } for s, e in scored[:top_k]]

    def index_indexer(self, indexer: ArchitectureIndexer) -> int:
        count = 0
        for qn, f in indexer.functions.items():
            text = " ".join(filter(None, [qn, f.signature, f.docstring or ""]))
            self.index(f"function:{qn}", text,
                       {"kind": "function", "file": f.file})
            count += 1
        for qn, c in indexer.classes.items():
            text = " ".join(filter(None, [qn, c.docstring or ""] + list(c.bases)))
            self.index(f"class:{qn}", text,
                       {"kind": "class", "file": c.file})
            count += 1
        return count


# =============================================================================
# PARTE 9 — MISSÕES
# =============================================================================


@dataclass
class MissionRecord:
    id: str
    objective: str
    status: str = "running"
    created_at: str = ""
    finished_at: Optional[str] = None
    files_changed: List[str] = field(default_factory=list)
    duration_seconds: Optional[float] = None
    tests_run: List[Dict[str, Any]] = field(default_factory=list)
    result: Optional[str] = None
    commit: Optional[str] = None
    rollback: Optional[str] = None
    agent: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MissionLog:
    """Histórico permanente (JSONL append-only)."""

    def __init__(self, root: str | Path):
        self.path = Path(root) / MISSIONS_FILE
        self.missions: Dict[str, MissionRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                self.missions[d["id"]] = MissionRecord(**d)
            except Exception:
                continue

    def _append(self, record: MissionRecord) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict(),
                               ensure_ascii=False) + "\n")

    def start(self, objective: str,
              agent: Optional[str] = None, **metadata) -> MissionRecord:
        mid = f"m_{int(time.time() * 1000)}_" \
              f"{hashlib.md5(objective.encode()).hexdigest()[:6]}"
        rec = MissionRecord(
            id=mid, objective=objective, status="running",
            created_at=datetime.now(timezone.utc).isoformat(),
            agent=agent, metadata=metadata,
        )
        self.missions[mid] = rec
        self._append(rec)
        return rec

    def finish(self, mid: str, status: str, **kwargs) -> None:
        if mid not in self.missions:
            return
        r = self.missions[mid]
        r.status = status
        r.finished_at = datetime.now(timezone.utc).isoformat()
        for k, v in kwargs.items():
            if hasattr(r, k):
                setattr(r, k, v)
        try:
            created = datetime.fromisoformat(r.created_at)
            finished = datetime.fromisoformat(r.finished_at)
            r.duration_seconds = (finished - created).total_seconds()
        except Exception:
            pass
        self._append(r)


# =============================================================================
# PARTE 10 — PATCH PLANNER
# =============================================================================


@dataclass
class PatchStep:
    order: int
    action: str  # modify | create | delete | test | rollback
    file: str
    symbol: Optional[str] = None
    reason: str = ""
    dependencies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PatchPlan:
    mission: str
    steps: List[PatchStep]
    files: List[str]
    tests: List[str]
    rollback: List[str]
    estimated_risk: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mission": self.mission,
            "steps": [s.to_dict() for s in self.steps],
            "files": self.files,
            "tests": self.tests,
            "rollback": self.rollback,
            "estimated_risk": self.estimated_risk,
        }


class PatchPlanner:
    """Planeja modificações ordenadas por dependência, com testes e rollback."""

    def __init__(self, indexer: ArchitectureIndexer,
                 graph: ArchitectureGraph,
                 impact: ImpactAnalyzer,
                 tests: TestIndex):
        self.indexer = indexer
        self.graph = graph
        self.impact = impact
        self.tests = tests

    def plan_patch(self, mission: str, max_files: int = 10) -> PatchPlan:
        candidates = self.indexer.find_where_to_change(
            mission, limit=max_files
        )
        files: List[str] = []
        for c in candidates:
            if c["file"] not in files:
                files.append(c["file"])

        ordered = self._topo_sort(files)

        steps: List[PatchStep] = []
        tests_set: Set[str] = set()
        order = 1

        for fpath in ordered:
            fi = self.indexer.files.get(fpath)
            if not fi:
                continue
            steps.append(PatchStep(
                order=order,
                action="modify",
                file=fpath,
                reason="Score de relevância para a missão",
                dependencies=self.indexer.get_dependencies(fi.module),
            ))
            order += 1
            for fqn in fi.functions:
                for t in self.tests.tests_for(fqn):
                    tests_set.add(t.test_id)

        for tid in sorted(tests_set):
            t = self.tests.tests.get(tid)
            if not t:
                continue
            steps.append(PatchStep(
                order=order, action="test", file=t.file,
                reason=f"Validar {tid}",
            ))
            order += 1

        rollback = [f"git checkout HEAD -- {f}" for f in ordered]
        risk = self._estimate_risk(ordered)

        return PatchPlan(
            mission=mission, steps=steps, files=ordered,
            tests=sorted(tests_set), rollback=rollback,
            estimated_risk=risk,
        )

    def _topo_sort(self, files: List[str]) -> List[str]:
        """Dependências primeiro (Kahn adaptado / DFS)."""
        mod_to_file = {
            self.indexer.files[f].module: f
            for f in files if f in self.indexer.files
        }
        deps: Dict[str, Set[str]] = {f: set() for f in files}
        for f in files:
            fi = self.indexer.files.get(f)
            if not fi:
                continue
            for dep_mod in self.indexer.get_dependencies(fi.module):
                if dep_mod in mod_to_file:
                    deps[f].add(mod_to_file[dep_mod])

        result: List[str] = []
        temp: Set[str] = set()
        perm: Set[str] = set()

        def visit(n: str) -> None:
            if n in perm or n in temp:
                return
            temp.add(n)
            for d in deps.get(n, ()):
                visit(d)
            temp.discard(n)
            perm.add(n)
            result.append(n)

        for f in files:
            visit(f)
        return result

    def _estimate_risk(self, files: List[str]) -> str:
        total_complexity = 0
        total_impact = 0
        for f in files:
            fi = self.indexer.files.get(f)
            if not fi:
                continue
            for fqn in fi.functions:
                func = self.indexer.functions.get(fqn)
                if func:
                    total_complexity += func.complexity
                    total_impact += len(
                        self.indexer.reverse_call_graph.get(fqn, [])
                    )
        score = total_complexity + total_impact * 2
        if score > 200:
            return "high"
        if score > 80:
            return "medium"
        return "low"


# =============================================================================
# PARTE 11 — ARCHITECTURE REASONER (FACHADA)
# =============================================================================


class ArchitectureReasoner:
    """
    Fachada de alto nível consumida pelo MissionExecutor.
    Fluxo: MissionExecutor → ArchitectureReasoner → ArchitectureIndexer.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.indexer = ArchitectureIndexer(self.root)
        self.graph: ArchitectureGraph = ArchitectureGraph()
        self.impact: Optional[ImpactAnalyzer] = None
        self.confidence: Optional[ConfidenceScorer] = None
        self.history = ArchitectureHistory(self.root)
        self.tests = TestIndex(self.indexer)
        self.ownership = OwnershipRegistry(self.root)
        self.workspace = WorkspaceStore(self.root)
        self.semantic = SemanticMemory()
        self.missions = MissionLog(self.root)
        self.planner: Optional[PatchPlanner] = None
        self._ready = False

    def initialize(self, force: bool = False) -> Dict[str, Any]:
        if self.indexer.load() and not force:
            logger.info("Snapshot carregado do disco")
        else:
            logger.info("Construindo índice completo...")
            self.indexer.build_index(force=force)
            self.indexer.save()

        self.graph = build_graph_from_indexer(self.indexer)
        self.impact = ImpactAnalyzer(self.graph, self.indexer)
        self.confidence = ConfidenceScorer(self.graph, self.indexer)
        self.planner = PatchPlanner(
            self.indexer, self.graph, self.impact, self.tests
        )

        test_path = self.root / TEST_INDEX_FILE
        if not self.tests.load(test_path):
            self.tests.build()
            self.tests.save(test_path)

        self.semantic.index_indexer(self.indexer)

        if not self.ownership.load():
            self.ownership.compute_from_filesystem(self.indexer)
            self.ownership.save()

        self._ready = True
        return {
            "files": len(self.indexer.files),
            "functions": len(self.indexer.functions),
            "classes": len(self.indexer.classes),
            "graph_nodes": len(self.graph.nodes),
            "graph_edges": len(self.graph.edges),
            "tests": len(self.tests.tests),
            "version": REASONER_VERSION,
        }

    # ---------- perguntas do MissionExecutor ----------

    def where_to_change(
        self, description: str, limit: int = 10
    ) -> List[ConfidenceResult]:
        raw = self.indexer.find_where_to_change(description, limit=limit)
        results: List[ConfidenceResult] = []
        for r in raw:
            assert self.confidence is not None
            cr = self.confidence.score_file(
                file_path=r["file"],
                reason=", ".join(r["reasons"][:2]),
                distance=1,
                exact_match=r["score"] > 0.8,
            )
            cr.confidence = round((cr.confidence + r["score"]) / 2, 3)
            results.append(cr)
        return sorted(results, key=lambda c: c.confidence, reverse=True)

    def what_breaks(self, symbol: str, depth: int = 3) -> ImpactResult:
        assert self.impact is not None
        return self.impact.find_impacted(symbol, depth=depth,
                                          direction="both")

    def which_tests(self, symbol: str) -> List[TestInfo]:
        return self.tests.tests_for(symbol)

    def find_similar(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        return self.semantic.search(query, top_k=top_k)

    def which_module(self, symbol: str) -> Optional[Dict[str, Any]]:
        for kind in (NodeKind.FUNCTION, NodeKind.METHOD,
                     NodeKind.CLASS, NodeKind.MODULE):
            n = self.graph.get_node(node_id(kind, symbol))
            if n:
                return {
                    "qualname": n.qualname,
                    "module": n.module,
                    "file": n.file,
                    "kind": n.kind.value,
                }
        for n in self.graph.nodes.values():
            if n.name == symbol:
                return {
                    "qualname": n.qualname,
                    "module": n.module,
                    "file": n.file,
                    "kind": n.kind.value,
                }
        return None

    def which_commits(self, file: str, limit: int = 5) -> List[Dict[str, str]]:
        try:
            out = subprocess.run(
                ["git", "log", "--oneline", f"-{limit}", "--", file],
                cwd=str(self.root), capture_output=True, text=True,
                timeout=10,
            )
            if out.returncode != 0:
                return []
            commits = []
            for line in out.stdout.strip().splitlines():
                if not line.strip():
                    continue
                parts = line.split(" ", 1)
                if len(parts) == 2:
                    commits.append({"hash": parts[0], "message": parts[1]})
            return commits
        except Exception:
            return []

    def has_mission_conflict(
        self, mission_files: List[str]
    ) -> List[Dict[str, Any]]:
        conflicts = []
        for rec in self.missions.missions.values():
            if rec.status != "running":
                continue
            overlap = set(rec.files_changed) & set(mission_files)
            if overlap:
                conflicts.append({
                    "mission_id": rec.id,
                    "objective": rec.objective,
                    "conflicting_files": sorted(overlap),
                })
        return conflicts

    def plan_patch(self, mission: str,
                   max_files: int = 10) -> PatchPlan:
        assert self.planner is not None
        return self.planner.plan_patch(mission, max_files=max_files)

    # ---------- missões ----------

    def start_mission(self, objective: str,
                      agent: Optional[str] = None) -> MissionRecord:
        return self.missions.start(objective, agent=agent)

    def finish_mission(self, mid: str, status: str, **kwargs) -> None:
        self.missions.finish(mid, status, **kwargs)

    # ---------- snapshot ----------

    def snapshot(self, tag: Optional[str] = None) -> Path:
        return self.history.save(self.graph, self.indexer, tag=tag)


# =============================================================================
# PARTE 12 — CLI
# =============================================================================


def _cli_init(args: argparse.Namespace) -> int:
    r = ArchitectureReasoner(args.root)
    print(json.dumps(r.initialize(force=args.force), indent=2))
    return 0


def _cli_where(args: argparse.Namespace) -> int:
    r = ArchitectureReasoner(args.root)
    r.initialize()
    results = r.where_to_change(args.where, limit=args.limit)
    print(json.dumps([c.to_dict() for c in results],
                     indent=2, ensure_ascii=False))
    return 0


def _cli_breaks(args: argparse.Namespace) -> int:
    r = ArchitectureReasoner(args.root)
    r.initialize()
    print(json.dumps(r.what_breaks(args.breaks, depth=args.depth).to_dict(),
                     indent=2, ensure_ascii=False))
    return 0


def _cli_plan(args: argparse.Namespace) -> int:
    r = ArchitectureReasoner(args.root)
    r.initialize()
    print(json.dumps(r.plan_patch(args.plan).to_dict(),
                     indent=2, ensure_ascii=False))
    return 0


def _cli_similar(args: argparse.Namespace) -> int:
    r = ArchitectureReasoner(args.root)
    r.initialize()
    print(json.dumps(r.find_similar(args.similar, top_k=args.limit),
                     indent=2, ensure_ascii=False))
    return 0


def _cli_snapshot(args: argparse.Namespace) -> int:
    r = ArchitectureReasoner(args.root)
    r.initialize()
    path = r.snapshot(tag=args.tag)
    print(f"Snapshot salvo: {path}")
    return 0


def _cli_history(args: argparse.Namespace) -> int:
    r = ArchitectureReasoner(args.root)
    if args.diff:
        a, b = map(int, args.diff.split(":"))
        print(json.dumps(r.history.diff(a, b),
                         indent=2, ensure_ascii=False))
    else:
        print(json.dumps(r.history.list_snapshots(),
                         indent=2, ensure_ascii=False))
    return 0


def _cli_stats(args: argparse.Namespace) -> int:
    r = ArchitectureReasoner(args.root)
    r.initialize()
    print(json.dumps({
        "graph": r.graph.stats(),
        "indexer": r.indexer.statistics,
        "tests": len(r.tests.tests),
        "ownership": len(r.ownership.entries),
        "missions": len(r.missions.missions),
        "version": REASONER_VERSION,
    }, indent=2, ensure_ascii=False))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="ArchitectureReasoner — Grafo, Impacto, Plano, Histórico"
    )
    p.add_argument("--root", default=os.environ.get("BRAINNET_ROOT", os.getcwd()))
    p.add_argument("--force", action="store_true")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--depth", type=int, default=3)
    p.add_argument("--tag", default=None)

    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--init", action="store_true")
    g.add_argument("--where", metavar="QUERY")
    g.add_argument("--breaks", metavar="SYMBOL")
    g.add_argument("--plan", metavar="MISSION")
    g.add_argument("--similar", metavar="QUERY")
    g.add_argument("--snapshot", action="store_true")
    g.add_argument("--history", action="store_true")
    g.add_argument("--diff", metavar="A:B",
                   help="ex: 1:2 — compara snapshots")
    g.add_argument("--stats", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    args = build_arg_parser().parse_args(argv)

    if args.init:
        return _cli_init(args)
    if args.where:
        return _cli_where(args)
    if args.breaks:
        return _cli_breaks(args)
    if args.plan:
        return _cli_plan(args)
    if args.similar:
        return _cli_similar(args)
    if args.snapshot:
        return _cli_snapshot(args)
    if args.history or args.diff:
        return _cli_history(args)
    if args.stats:
        return _cli_stats(args)
    return 1


# =============================================================================
# ENTRYPOINT
# =============================================================================

if __name__ == "__main__":
    sys.exit(main())