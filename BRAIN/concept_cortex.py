# ==============================================================================
# BRAINNET v7 - SISTEMA OPERACIONAL COGNITIVO
# MODULO: concept_cortex.py
# FUNCAO: Cortéx de Conceitos. Resonator 3-fatores (multiplicativo com permutação)
#         Grounding via Resolver.probe, Z-score determinístico, SQLite WAL.
# Tag: [BN_CONCEPT_CORTEX]
# ==============================================================================

from __future__ import annotations

import ast
import logging
import math
import operator
import os
import re
import sqlite3
import time
from threading import RLock
import uuid
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import psutil
from system_intent import is_web_navigation, system_launch_target
from role_binding import abstract_app_demonstration, substitute_slots
from htn_planner import parse_objectives

try:
    import win32gui
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

from hyperdimensional import FHRRHyperdimensionalEngine
from causal_trajectory import WindowsAppResolver

logger = logging.getLogger("BRAINNET_ConceptCortex")

ACTIONS: List[str] = ["OPEN", "TYPE", "CLICK", "WAIT"]
TARGET_INVARIANTS: List[str] = [
    "PORTA_DE_TRANSICAO", "BUSCA", "ENVIO", "RECEPCAO",
    "CONFIRMACAO", "NAVEGACAO", "CANCELAMENTO",
]
DOMAINS: List[str] = ["DIGITAL_UI", "PHYSICAL_WORLD", "LOGICAL_MATH", "SOCIAL_AFFECT", "TELEMETRY"]

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS concept_invariants (
    concept_key TEXT PRIMARY KEY,
    phases_blob BLOB NOT NULL,
    exemplar_count INTEGER NOT NULL DEFAULT 1,
    last_updated REAL NOT NULL,
    negative_phases_blob BLOB,
    failure_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS click_audit (
    event_id TEXT PRIMARY KEY, timestamp REAL NOT NULL,
    intent_hash TEXT NOT NULL, element TEXT NOT NULL, app_name TEXT NOT NULL,
    change_type TEXT NOT NULL, pid_before INTEGER, pid_after INTEGER,
    hwnd_before INTEGER, hwnd_after INTEGER, ncd_real REAL NOT NULL,
    expected_ncd REAL NOT NULL, verified INTEGER NOT NULL,
    prototype_success INTEGER
);
CREATE INDEX IF NOT EXISTS idx_click_audit_time ON click_audit(timestamp);
"""


class ConceptCortex:
    __slots__ = (
        "hdc", "resolver", "db_path", "dim", "tau_affordance",
        "role_action", "role_target", "role_domain",
        "actions_cb", "targets_cb", "domains_cb", "a_so_tensor",
        "invariants_cache", "_conn", "mu_noise", "sigma_noise", "negative_cache", "_learning_lock"
    )

    def __init__(
        self,
        hdc: FHRRHyperdimensionalEngine,
        resolver: WindowsAppResolver,
        db_path: str = "core1_pdag.db",
        dim: int = 10_000,
        tau_affordance: float = 0.20,
    ) -> None:
        self.hdc = hdc
        self.resolver = resolver
        self.db_path = db_path
        self.dim = dim
        self.tau_affordance = tau_affordance

        self.role_action = hdc.generate_vector("CANONICAL_ROLE_ACTION")
        self.role_target = hdc.generate_vector("CANONICAL_ROLE_TARGET")
        self.role_domain = hdc.generate_vector("CANONICAL_ROLE_DOMAIN")

        self.actions_cb = self._init_codebook(ACTIONS, "ACTION")
        self.targets_cb = self._init_codebook(TARGET_INVARIANTS, "TARGET")
        self.domains_cb = self._init_domains_codebook()
        self.a_so_tensor = self._init_codebook(
            ["win32_process", "win32_hwnd", "uia_invoke", "uia_value", "fs_io", "net_socket"],
            "AFFORDANCE"
        )

        cal_vectors = np.stack([self.hdc.generate_vector(f"CALIBRATION_{i}") for i in range(100)])
        dots = np.dot(self.a_so_tensor, np.conj(cal_vectors.T))
        sims = np.real(dots) / self.dim
        self.mu_noise = float(np.mean(sims))
        self.sigma_noise = float(np.std(sims))

        self._conn = sqlite3.connect(
            self.db_path, check_same_thread=False, isolation_level=None
        )
        self._conn.executescript(SCHEMA)
        self._learning_lock = RLock()
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(concept_invariants)")}
        if "negative_phases_blob" not in columns:
            self._conn.execute("ALTER TABLE concept_invariants ADD COLUMN negative_phases_blob BLOB")
        if "failure_count" not in columns:
            self._conn.execute("ALTER TABLE concept_invariants ADD COLUMN failure_count INTEGER NOT NULL DEFAULT 0")
        self.invariants_cache = self._hydrate_invariants()
        self._conn.execute("""CREATE TABLE IF NOT EXISTS grounding_cleanup (
            exemplar_id TEXT PRIMARY KEY, cleanup_key TEXT NOT NULL,
            phases_blob BLOB NOT NULL, metadata_json TEXT NOT NULL, timestamp REAL NOT NULL)""")
        for key, blob in self._conn.execute(
                "SELECT cleanup_key, phases_blob FROM grounding_cleanup ORDER BY timestamp DESC LIMIT 1000"):
            vector = np.frombuffer(blob, dtype=np.complex64)
            if vector.shape == (self.dim,) and np.all(np.isfinite(vector)):
                self.hdc.register_cleanup(key, vector)
        self.negative_cache = {key: np.frombuffer(blob, dtype=np.complex64).copy()
                               for key, blob in self._conn.execute("SELECT concept_key, negative_phases_blob FROM concept_invariants WHERE negative_phases_blob IS NOT NULL")}

    def close(self) -> None:
        if hasattr(self, "_conn") and self._conn:
            self._conn.close()

    def _init_codebook(self, labels: List[str], prefix: str) -> np.ndarray:
        return np.stack([self.hdc.generate_vector(f"CANONICAL_{prefix}_{lbl}") for lbl in labels]).astype(np.complex64)

    def _init_domains_codebook(self) -> np.ndarray:
        """Walsh-Hadamard para ortogonalidade estrita (5 domínios)."""
        H = np.array([[1, 1, 1, 1, 1, 1, 1, 1],
                      [1, -1, 1, -1, 1, -1, 1, -1],
                      [1, 1, -1, -1, 1, 1, -1, -1],
                      [1, -1, -1, 1, 1, -1, -1, 1],
                      [1, 1, 1, 1, -1, -1, -1, -1],
                      [1, -1, 1, -1, -1, 1, -1, 1],
                      [1, 1, -1, -1, -1, -1, 1, 1],
                      [1, -1, -1, 1, -1, 1, 1, -1]], dtype=np.float32)
        phases = (1 - H) / 2 * np.pi
        cb = np.zeros((8, self.dim), dtype=np.complex64)
        for i in range(8):
            tiled = np.tile(phases[i], self.dim // 8)
            cb[i] = np.exp(1j * tiled)
        return cb[:5]

    def _hydrate_invariants(self) -> Dict[str, np.ndarray]:
        cache = {}
        cursor = self._conn.execute("SELECT concept_key, phases_blob FROM concept_invariants WHERE exemplar_count > 0")
        rows = cursor.fetchall()
        
        if not rows:
            for inv in TARGET_INVARIANTS:
                v = self.hdc.generate_vector(f"CANONICAL_TARGET_{inv}")
                cache[inv] = v
                with self._conn:
                    self._conn.execute(
                        "INSERT INTO concept_invariants (concept_key, phases_blob, exemplar_count, last_updated) VALUES (?, ?, 1, ?)",
                        (inv, v.tobytes(), time.time())
                    )
        else:
            for row in rows:
                key, blob = row
                cache[key] = np.frombuffer(blob, dtype=np.complex64).copy()
        return cache

    @staticmethod
    def phase_project(v: np.ndarray) -> np.ndarray:
        return np.exp(1j * np.angle(v)).astype(np.complex64)

    def evaluate_affordance(self, target_phasor: np.ndarray) -> float:
        t_vec = np.ascontiguousarray(target_phasor, dtype=np.complex64)
        dots = np.dot(self.a_so_tensor, np.conj(t_vec))
        return float(np.sqrt(np.sum(np.abs(dots)**2)) / self.dim)

    def _ground_target(self, target_text: str) -> Tuple[bool, Optional[np.ndarray]]:
        if not target_text:
            return False, None
            
        hit = self.resolver.resolve_app_probabilistic(target_text, self.hdc)
        if hit is None:
            return False, None
            
        t = hit["tipo"]
        idx = 0
        if t == "LNK":
            idx = 1
        elif t == "PROTOCOL_OR_EXE":
            idx = 2
            
        return True, self.a_so_tensor[idx]

    def _resonate(self, intent_phasor: np.ndarray) -> Tuple[str, str, str, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        a_est = self.actions_cb[0].copy()
        t_est = self.targets_cb[0].copy()
        d_est = self.domains_cb[0].copy()

        last_sx = np.zeros(len(self.actions_cb))
        last_sy = np.zeros(len(self.targets_cb))
        last_sz = np.zeros(len(self.domains_cb))

        for _ in range(15):
            # Action
            unbound_a = intent_phasor * np.conj(self.hdc.permute(t_est, 1)) * np.conj(self.hdc.permute(d_est, 2))
            sims_a = np.real(np.dot(self.actions_cb, np.conj(unbound_a))) / self.dim
            w_a = np.exp(20.0 * (sims_a - np.max(sims_a)))
            w_a /= np.sum(w_a)
            a_proj = np.sum(self.actions_cb * w_a[:, None], axis=0)
            a_est = self.phase_project(0.7 * a_est + 0.3 * a_proj)
            last_sx = sims_a

            # Target
            unbound_t = intent_phasor * np.conj(a_est) * np.conj(self.hdc.permute(d_est, 2))
            unbound_t = self.hdc.permute(unbound_t, -1)
            sims_t = np.real(np.dot(self.targets_cb, np.conj(unbound_t))) / self.dim
            w_t = np.exp(20.0 * (sims_t - np.max(sims_t)))
            w_t /= np.sum(w_t)
            t_proj = np.sum(self.targets_cb * w_t[:, None], axis=0)
            t_est = self.phase_project(0.7 * t_est + 0.3 * t_proj)
            last_sy = sims_t

            # Domain
            unbound_d = intent_phasor * np.conj(a_est) * np.conj(self.hdc.permute(t_est, 1))
            unbound_d = self.hdc.permute(unbound_d, -2)
            sims_d = np.real(np.dot(self.domains_cb, np.conj(unbound_d))) / self.dim
            w_d = np.exp(20.0 * (sims_d - np.max(sims_d)))
            w_d /= np.sum(w_d)
            d_proj = np.sum(self.domains_cb * w_d[:, None], axis=0)
            d_est = self.phase_project(0.7 * d_est + 0.3 * d_proj)
            last_sz = sims_d

        a_idx = np.argmax(last_sx)
        t_idx = np.argmax(last_sy)
        d_idx = np.argmax(last_sz)

        return (
            ACTIONS[a_idx],
            TARGET_INVARIANTS[t_idx],
            DOMAINS[d_idx],
            a_est, t_est, d_est,
            last_sx, last_sy, last_sz
        )

    @staticmethod
    def SUBSTITUIR_SLOT(pipeline_mielinizado: Dict[str, Any], variaveis_extraidas: Dict[str, str]) -> Dict[str, Any]:
        bindings = dict(variaveis_extraidas)
        if "APP_ALVO" in bindings or "SLOT_APP" in bindings:
            app = bindings.get("APP_ALVO", bindings.get("SLOT_APP"))
            if bindings.get("SLOT_APP", app) != app:
                raise ValueError("Slots de aplicativo conflitantes")
            bindings.update(APP_ALVO=app, SLOT_APP=app)
        return substitute_slots(pipeline_mielinizado, bindings)

    def hash_visual_para_fhrr(self, img_roi) -> np.ndarray:
        """dHash geometrico distribuido: bits proximos geram FHRRs proximos, sem avalanche."""
        from PIL import Image
        if not isinstance(img_roi, Image.Image) or min(img_roi.size) < 1:
            raise ValueError("Assinatura visual exige ROI PIL valida")
        gray = np.asarray(img_roi.convert("L"), dtype=np.float32)
        normalized = (gray-gray.min()) / max(float(np.ptp(gray)), 1.0)
        pixels = np.asarray(Image.fromarray(normalized).resize((9, 8), Image.Resampling.LANCZOS))
        bits = (pixels[:, :-1] - pixels[:, 1:] > 1/255).reshape(-1)
        signs = np.where(bits[np.arange(self.hdc.dim) % 64], 1.0, -1.0)
        basis = self.hdc.generate_vector("__VISUAL_DHASH_GEOMETRY__")
        return np.ascontiguousarray(basis * signs, dtype=np.complex64)

    def deduzir_funcao_visual(self, descricao: str, objetivo: str, contexto: str) -> Dict[str, Any]:
        """Similaridade associativa e hipotese funcional, nunca prova de execucao."""
        if not all(isinstance(text, str) and text.strip() for text in (descricao, objetivo, contexto)):
            raise ValueError("Deducao exige descricao, objetivo e contexto")
        context = self.hdc.text_to_hypervector(contexto)
        visual = self.hdc.bind(self.hdc.text_to_hypervector(descricao), context)
        intent = self.hdc.bind(self.hdc.text_to_hypervector(objetivo), context)
        score = float(self.hdc.similarity(visual, intent))
        if not np.isfinite(score):
            raise ValueError("Similaridade visual nao finita")
        return {"encontrado": score > 0.40, "similaridade": score,
                "descricao": descricao, "contexto": contexto, "verificado": False}

    @staticmethod
    def abstract_application_route(steps, app):
        return abstract_app_demonstration(steps, app)

    @staticmethod
    def instantiate_generic_opening(pdag, app):
        if pdag is None or pdag.is_verified_demonstration("abrir_app_generico") is not True:
            return None
        route = pdag.find_myelinated_path("trajectory:abrir_app_generico", exact_only=True)
        if not route or route.get("meta_primitive") != "OPEN_APP" or route.get("slot_roles", {}).get("APP_ALVO") != "application":
            return None
        steps = route.get("passos", [])
        core = [step for step in steps if step.get("acao") != "WAIT"]
        if len(core) != 3 or core[1].get("text") != "{APP_ALVO}":
            raise ValueError("Template generico invalido; refaca a demonstracao abstrata")
        abstract_app_demonstration(steps, "{APP_ALVO}")
        template = {"passos": steps, "meta_primitive": "OPEN_APP", "slot_roles": route["slot_roles"], "professor_verified": True}
        return {"template": template, "pipeline": substitute_slots(template, {"APP_ALVO": app}), "bindings": {"APP_ALVO": app}}

    def _build_intent_phasor(self, roles: Dict[str, Any], context: str) -> np.ndarray:
        return self.hdc.encode_compositional(
            action=roles["action"], target=roles["target"],
            param=roles.get("domain", ""), context=context,
        )

    def vincular_alvo_ao_slot(self, target: str) -> np.ndarray:
        if not isinstance(target, str) or not target.strip():
            raise ValueError("ROLE_TARGET exige valor explicito")
        return self.hdc.bind(self.hdc.role_target, self.hdc.text_to_hypervector(target))

    def parse_and_route(self, intent_phasor: np.ndarray, target_text: Optional[str] = None, raw_text: str = "", context: str = "", roles: Optional[Dict[str, Any]] = None, pdag_engine: Any = None) -> Dict[str, Any]:
        goals = parse_objectives(raw_text)
        if len(goals) == 1 and goals[0]["kind"] == "CLICK_TEXT":
            return {"decision": "OS_AUTOMATION", "action": "CLICK", "target": goals[0]["roles"]["TARGET"],
                    "domain": "DIGITAL_UI", "context": context, "kappa": None, "is_physically_viable": True,
                    "is_verified": False, "grounding": "HYBRID_LOCATE_PENDING_VERIFICATION",
                    "mechanism_hint": {"kind": "COMPOSE_OBJECTIVES", "goals": goals, "requires_hwnd_verification": True}}
        if len(goals) > 1:
            return {"decision": "OS_AUTOMATION", "action": "COMPOSE", "target": goals[0]["roles"]["APP_ALVO"],
                    "domain": "DIGITAL_UI", "context": context, "kappa": None, "is_physically_viable": True,
                    "is_verified": False, "grounding": "EXPLICIT_GOALS_PENDING_VERIFICATION",
                    "mechanism_hint": {"kind": "COMPOSE_OBJECTIVES", "goals": goals, "requires_hwnd_verification": True}}
        literal = system_launch_target(raw_text)
        if literal and not is_web_navigation(raw_text):
            generic = self.instantiate_generic_opening(pdag_engine, literal)
            return {"decision": "OS_AUTOMATION", "action": "OPEN", "target": literal, "domain": "DIGITAL_UI",
                    "context": context, "kappa": None, "grounding": "START_MENU_SEARCH_PENDING",
                    "is_physically_viable": True, "is_verified": False,
                    "mechanism_hint": {"kind": "INSTANTIATE_META" if generic else "START_MENU_SEARCH", "app": literal,
                                       "pipeline": generic["pipeline"] if generic else None, "requires_hwnd_verification": True}}
        contextual_match = None
        if raw_text and context and roles:
            contextual_match = self.hdc.cleanup_query(self._build_intent_phasor(roles, context), threshold=0.30)
        a_label, t_label, d_label, x_est, y_est, z_est, last_sx, last_sy, last_sz = self._resonate(intent_phasor)

        v_target_atom = y_est

        grounded = False
        grounding_status = "DEGRADED_NO_TEXT"
        
        if target_text is not None:
            grounded, a_k = self._ground_target(target_text)
            if grounded and a_k is not None:
                v_target_atom = self.phase_project(v_target_atom + a_k)
                grounding_status = "GROUNDED"
            else:
                # Bug 1 Fix: Use the actual text target when probe fails
                v_target_atom = self.hdc.text_to_hypervector(target_text)
                grounding_status = "NO_AFFORDANCE_FOUND"

        kappa = self.evaluate_affordance(v_target_atom)
        viable = kappa >= self.tau_affordance

        def _margin(s: np.ndarray) -> float:
            if len(s) < 2: return 0.0
            top2 = np.sort(s)[-2:]
            max_s = top2[1]
            sec_s = top2[0]
            return float((max_s - sec_s) / (max_s + 1e-9))

        m_act = _margin(last_sx)
        m_dom = _margin(last_sz)
        confidence = float(np.clip(kappa * (m_act + m_dom) / 2.0, 0.0, 1.0))

        # Bug 3 Fix: Map strictly to the contract vocabulary
        mechanism_map = {"OPEN": "LAUNCH", "TYPE": "TYPE", "CLICK": "CLICK", "WAIT": "HOTKEY"}
        kind = mechanism_map.get(a_label, "LAUNCH")

        route = {
            "context": context,
            "contextual_match": contextual_match,
            "action": a_label,
            "target": t_label,
            "domain": d_label,
            "kappa": kappa,
            "is_physically_viable": viable,
            "grounding": grounding_status,
            "mechanism_hint": {
                "kind": kind,
                "confidence": confidence
            }
        }

        if not viable:
            route["decision"] = "REJECT_NO_AFFORDANCE"
            route["reply"] = "Ação rejeitada: o alvo não possui affordance física ou interface no Windows 11."
            return route

        if d_label == "LOGICAL_MATH":
            route["decision"] = "MATH"
            route["reply"] = self._safe_eval_math(raw_text)
            return route

        if d_label == "SOCIAL_AFFECT":
            route["decision"] = "SOCIAL"
            route["reply"] = "Eu sou uma inteligencia artificial, nao possuo corpo fisico, mas estou aqui conectada com voce no sistema!"
            return route

        if d_label == "TELEMETRY":
            route["decision"] = "TELEMETRY"
            route["reply"] = self._get_telemetry()
            return route

        route["decision"] = "OS_AUTOMATION"
        return route

    def _safe_eval_math(self, text: str) -> str:
        # Bug 4 Fix: Removed Portuguese hardcoded replaces
        t = re.sub(r"[^\d\+\-\*\/\.\(\)\s]", "", text).strip()
        
        if "/0" in t:
            return "Indeterminação matemática: divisão por zero não é definida nos reais."
            
        try:
            ops = {
                ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                ast.Div: operator.truediv, ast.USub: operator.neg
            }
            def _eval(node):
                if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                    return node.value
                elif isinstance(node, ast.BinOp):
                    return ops[type(node.op)](_eval(node.left), _eval(node.right))
                elif isinstance(node, ast.UnaryOp):
                    return ops[type(node.op)](_eval(node.operand))
                else:
                    raise TypeError(node)
                
            result = _eval(ast.parse(t, mode='eval').body)
            return f"Resultado: {result}"
        except Exception:
            return "Expressão matemática inválida."

    def _get_telemetry(self) -> str:
        if not HAS_WIN32:
            return "Erro: API win32gui indisponivel."
            
        windows = []
        def enum_handler(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).strip()
                if title:
                    windows.append(title)
        win32gui.EnumWindows(enum_handler, None)
        
        if not windows:
            return "Nenhuma janela ativa detectada."
        return "Janelas abertas:\n" + "\n".join(f"- {w}" for w in windows[:10])

    def learn_exemplar(self, v_obs: np.ndarray, concept: str, success: bool, eta: float = 0.15) -> None:
        observed = np.asarray(v_obs)
        if observed.shape != (self.dim,) or not np.iscomplexobj(observed) or not np.all(np.isfinite(observed)) or np.any(np.abs(observed) < 1e-12):
            raise ValueError("Exemplar deve ser FHRR complexo finito com dimensao correta")
        if not isinstance(concept, str) or not concept.strip() or not isinstance(success, (bool, np.bool_)):
            raise ValueError("Conceito e sucesso do exemplar invalidos")
        if not np.isfinite(eta) or not 0 < eta <= 1:
            raise ValueError("eta deve estar em (0, 1]")
        observed = self.phase_project(observed)
        with self._learning_lock:
            positive = self.invariants_cache.get(concept)
            negative = self.negative_cache.get(concept)
            current = positive if success else negative
            candidate = observed if current is None else current + eta * observed
            if current is not None:
                candidate = np.where(np.abs(candidate) < 1e-12, current, candidate)
            learned = self.phase_project(candidate)
            positive = learned if success else positive
            negative = negative if success else learned
            self._conn.execute("""
                INSERT INTO concept_invariants (concept_key, phases_blob, exemplar_count, last_updated, negative_phases_blob, failure_count)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(concept_key) DO UPDATE SET
                phases_blob = excluded.phases_blob,
                exemplar_count = exemplar_count + excluded.exemplar_count,
                negative_phases_blob = excluded.negative_phases_blob,
                failure_count = failure_count + excluded.failure_count,
                last_updated = excluded.last_updated;
            """, (concept, (positive if positive is not None else np.zeros(self.dim, dtype=np.complex64)).tobytes(),
                  int(success), time.time(), negative.tobytes() if negative is not None else None, int(not success)))
            if positive is not None:
                self.invariants_cache[concept] = positive
            if negative is not None:
                self.negative_cache[concept] = negative

    def log_click(self, intent_hash: str, element: str, app_name: str, change_type: str,
                  pre_state: Dict[str, Any], post_state: Dict[str, Any], verified: bool,
                  expected_ncd: float, prototype_success: Optional[bool]) -> str:
        event_id = uuid.uuid4().hex
        with self._learning_lock:
            self._conn.execute("""INSERT INTO click_audit VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                               (event_id, time.time(), intent_hash, element, app_name, change_type,
                                pre_state.get("pid"), post_state.get("pid"), pre_state.get("hwnd"), post_state.get("hwnd"),
                                float(post_state["ncd_real"]), float(expected_ncd), int(verified),
                                None if prototype_success is None else int(prototype_success)))
        return event_id


# Alias Canonico
ThalamicGate = ConceptCortex
