"""Qualia composition at the application boundary; existing FHRR/P-DAG APIs."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np

from role_binding import substitute_slots


def compose_qualia(vsa, purpose, steps):
    return vsa.bundle([
        vsa.bind(vsa.role_formal, vsa.text_to_hypervector("MACRO_ACTION")),
        vsa.bind(vsa.role_constitutive, vsa.text_to_hypervector("OS_INTERFACE")),
        vsa.bind(vsa.role_telic, vsa.text_to_hypervector(purpose)),
        vsa.bind(vsa.role_agentive, vsa.text_to_hypervector(str(steps))),
    ])


def save_qualia(pdag, vsa, purpose, steps, vector):
    vector = np.ascontiguousarray(vector, dtype=np.complex64)
    if vector.shape != (vsa.dim,) or not np.isfinite(vector).all():
        raise ValueError("Vetor algebrico de Qualia invalido")
    key = f"qualia:{purpose}"
    snapshot = deepcopy(steps)
    spec = {"passos": snapshot, "qualia_algebraic": True, "qualia_telic": purpose,
            "formal": "MACRO_ACTION", "constitutive": "OS_INTERFACE"}
    # Existing nodes retain their phase in record_human_demonstration; update
    # that same RAM row before asking the existing writer to persist it.
    with pdag._lock:
        idx = pdag.id_to_index.get(key)
        if idx is not None:
            pdag.phase_matrix[idx] = vector
    source = SimpleNamespace(text_to_hypervector=lambda _label: vector.copy())
    if pdag.record_human_demonstration(key, purpose, spec, source) is not True:
        raise RuntimeError("P-DAG nao confirmou a tupla Qualia")
    label = f"QUALIA_TELIC_{purpose}"
    if label not in vsa.cleanup_keys:
        vsa.register_cleanup(label, vsa.text_to_hypervector(purpose))
    return True


def retrieve_opening(engine, app):
    """Denoise the unbound telic role before the strict 0.70 comparison."""
    pdag, vsa = getattr(engine, "pdag", None), getattr(engine, "vsa", None)
    if pdag is None or vsa is None:
        return None
    purpose, key = "ABRIR_APP", "qualia:ABRIR_APP"
    spec = pdag.find_taught_path(key)
    if not isinstance(spec, dict) or spec.get("qualia_algebraic") is not True or spec.get("qualia_telic") != purpose:
        return None
    vector = pdag.get_node_phases(key)
    if not isinstance(vector, np.ndarray) or vector.shape != (vsa.dim,) or not np.isfinite(vector).all():
        return None
    steps = spec.get("passos", [])
    if float(vsa.similarity(vector, compose_qualia(vsa, purpose, steps))) < .99:
        return None
    noisy = engine.extrair_proposito(vector)
    expected = vsa.text_to_hypervector(purpose)
    raw_score = float(vsa.similarity(noisy, expected))
    if not np.isfinite(raw_score) or raw_score < .30:
        return None
    label = f"QUALIA_TELIC_{purpose}"
    if label not in vsa.cleanup_keys:
        vsa.register_cleanup(label, expected)
    cleaned = vsa.cleanup_query(noisy, threshold=.30)
    if cleaned is None or cleaned[0] != label:
        return None
    score = float(vsa.similarity(vsa.text_to_hypervector(cleaned[0][len("QUALIA_TELIC_"):]), expected))
    if not np.isfinite(score) or score <= .70:
        return None
    # Opening is a constrained macro: don't transfer arbitrary clicks or text.
    if (len(steps) != 3 or [s.get("acao") for s in steps] != ["HOTKEY", "TYPE", "HOTKEY"]
            or steps[0].get("keys") != ["win"] or steps[2].get("keys") != ["enter"]
            or steps[1].get("text") not in ("{APP_ALVO}", "{SLOT_APP}")):
        return None
    bound = substitute_slots(steps, {"APP_ALVO": app, "SLOT_APP": app})
    return {"source": key, "similarity": score, "raw_similarity": raw_score,
            "similarity_space": "CLEANED_TELIC", "agentive": bound,
            "pipeline": [{"p": "OPEN_APP", "app": app}], "pending_validation": True}
