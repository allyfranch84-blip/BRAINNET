"""Compile explicit, observed transition pipelines into verified zero-LLM skills."""
import argparse
import ast
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import re
import sqlite3
import unicodedata


def _slug(value):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")[:70]


def _steps(spec):
    spec = json.loads(spec) if isinstance(spec, str) else spec
    steps = spec.get("passos", spec.get("pipeline"))
    if not isinstance(steps, list) or not 1 <= len(steps) <= 32:
        raise ValueError("Pipeline ausente ou grande demais")
    clean = []
    for step in steps:
        action = step.get("acao", step.get("p"))
        if action == "HOTKEY" and isinstance(step.get("keys"), list) and 1 <= len(step["keys"]) <= 4:
            keys = step["keys"]
            if not all(isinstance(key, str) and re.fullmatch(r"[a-z0-9_]+", key) for key in keys):
                raise ValueError("Teclas invalidas")
            clean.append({"acao": action, "keys": keys})
        elif action == "TYPE" and isinstance(step.get("text"), str) and 0 < len(step["text"]) <= 10000:
            clean.append({"acao": action, "text": step["text"]})
        elif action == "CLICK" and step.get("button", "left") in ("left", "right") and not any(k in step for k in ("x", "y", "target")):
            clean.append({"acao": action, "button": step.get("button", "left")})
        elif action == "WAIT" and isinstance(step.get("seconds"), (float, int)) and math.isfinite(step["seconds"]) and 0 <= step["seconds"] <= 300:
            clean.append({"acao": action, "seconds": float(step["seconds"])})
        else:
            raise ValueError("Acao sem suporte estatico seguro")
    return clean


def _shape(steps):
    return json.dumps([{k: v for k, v in step.items() if k != "text"} for step in steps], sort_keys=True)


def _render(app, intent, examples):
    steps = examples[0]
    parameters, calls = [], []
    text_index = 0
    for index, step in enumerate(steps):
        action = step["acao"]
        if action == "TYPE":
            text_index += 1
            values = {sample[index]["text"] for sample in examples}
            slot = re.fullmatch(r"\{([A-Za-z][A-Za-z0-9_]*)\}", step["text"])
            if slot or len(values) > 1:
                name = slot.group(1).lower() if slot else ("contato" if app == "whatsapp" and text_index == 1 else "msg" if app == "whatsapp" and text_index == 2 else f"texto_{text_index}")
                if name in ("effector", "trajectory_engine", "asyncio", "skill", "require_action_allowed") or name in parameters:
                    raise ValueError("Slot duplicado ou reservado")
                parameters.append(name)
                argument = name
            else:
                argument = repr(step["text"])
            call = f"effector.send_text, {argument}"
        elif action == "HOTKEY":
            call = f"effector.send_hotkey, {step['keys']!r}"
        elif action == "WAIT":
            call = repr(step["seconds"])
        else:
            call = f"effector.mouse_click, {step['button']!r}"
        calls.append((action, call))
    name = f"macro_{_slug(intent)}_{_slug(app)}"
    signature = ", ".join([f"{p}: str" for p in parameters] + ["*", "effector", "trajectory_engine"])
    lines = ["# Generated from observed successful pipelines; loading never executes actions.",
             "import asyncio", "from skill_loader import skill",
             "from execution_authority import require_action_allowed", "",
             f"@skill(name={name!r}, description={('Heuristica observada: ' + intent)!r})",
             f"async def {name}({signature}):", "    require_action_allowed('EXECUTE')",
             "    feedbacks = []"]
    for index, (action, call) in enumerate(calls):
        operation = f"        await asyncio.sleep({call})\n        result = True" if action == "WAIT" else f"        result = await asyncio.to_thread({call})"
        lines += [f"    async def action_{index}():", f"        require_action_allowed({action!r})",
                  operation,
                  "        if result is not True:", "            raise RuntimeError('Effector nao confirmou execucao')",
                  "        return result",
                  f"    feedback = await trajectory_engine.execute_subgoal(intent_hash={('heuristic:' + app + ':' + intent + ':' + str(index))!r}, action_fn=action_{index}, contract=trajectory_engine._contract_for_action({action!r}, {app!r}))",
                  "    feedbacks.append(feedback)", "    if feedback.get('lambda_obs') != 1:",
                  "        return {'status': 'FALHA_REALIDADE', 'detalhes': feedbacks}"]
    lines += ["    return {'status': 'CONCLUIDO', 'detalhes': feedbacks}", ""]
    source = "\n".join(lines)
    ast.parse(source)
    return source


def compilar_tudo(db_path="core1_pdag.db", skills_dir=None, min_samples=10, threshold=0.90):
    if min_samples < 10 or not 0.90 <= threshold <= 1:
        raise ValueError("Exige >=10 amostras e >=90% de confianca")
    output = Path(skills_dir) if skills_dir is not None else Path(__file__).resolve().parent.parent / "HABILIDADES"
    result = {"sucessos": 0, "ignorados": 0, "arquivos": [], "avisos": []}
    groups, chains = defaultdict(list), defaultdict(list)
    with sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(transitions)")}
        intent_fields = [field for field in ("intent", "intent_base", "command_text") if field in columns]
        spec_fields = [field for field in ("steps_json", "pipeline_spec") if field in columns]
        if not intent_fields or not spec_fields:
            result["avisos"].append("Transicoes sem intencao/pipeline explicitos; hashes nao sao reversiveis.")
            return result
        source = "source" if "source" in columns else "'observed'"
        coalesce = lambda fields: f"COALESCE({', '.join(fields)}, NULL)"
        delta = coalesce([field for field in ("actual_delta", "ncd") if field in columns])
        trace = ", ".join(field if field in columns else "NULL" for field in ("trajectory_id", "step_index", "step_count"))
        query = f"SELECT app_name, {coalesce(intent_fields)}, {coalesce(spec_fields)}, lambda_obs, {delta}, {source}, {trace} FROM transitions ORDER BY id LIMIT 100001"
        for index, (app, intent, spec, hit, ncd, origin, trace_id, position, count) in enumerate(conn.execute(query)):
            if index == 100000:
                result["avisos"].append("Limite de 100000 registros; compile uma janela menor.")
                return result
            if origin != "observed" or not isinstance(intent, str) or not intent.strip() or not isinstance(app, str) or not _slug(app):
                result["ignorados"] += 1
                continue
            key = (app.casefold().strip(), intent.casefold().strip())
            success = hit == 1 and isinstance(ncd, (int, float)) and math.isfinite(ncd) and 0 <= ncd <= 1
            if trace_id:
                chains[trace_id].append((key, spec, success, position, count))
                continue
            try:
                steps = _steps(spec)
            except (ValueError, TypeError, AttributeError, KeyError):
                steps = None
            groups[key].append((steps, success))
    for records in chains.values():
        key = records[-1][0]
        steps, success = None, False
        try:
            spec = json.loads(records[0][1])
            steps = _steps(spec)
            expected = len(steps)
            ordered = sorted(records, key=lambda row: row[3])
            success = (len(ordered) == expected and [row[3] for row in ordered] == list(range(expected))
                       and all(row[4] == expected and row[0][1] == key[1] and row[2] for row in ordered))
            for index, row in enumerate(ordered):
                frame = json.loads(row[1])
                if _steps(frame) != steps or _steps({"passos": [frame["executed_step"]]}) != [steps[index]]:
                    success = False
        except (ValueError, TypeError, AttributeError, KeyError, IndexError):
            success = False
        groups[key].append((steps, success))
    output.mkdir(parents=True, exist_ok=True)
    for (app, intent), records in groups.items():
        counts = Counter(_shape(steps) for steps, success in records if steps and success)
        if not counts:
            continue
        shape, support = counts.most_common(1)[0]
        if len(records) < min_samples or support / len(records) <= threshold:
            continue
        samples = [steps for steps, success in records if steps and success and _shape(steps) == shape]
        path = output / f"auto_macro_{_slug(app)}_{_slug(intent)}.py"
        if path.exists():
            continue  # Never replace user code or a previously reviewed skill.
        try:
            source = _render(app, intent, samples)
        except (ValueError, SyntaxError):
            result["ignorados"] += len(records)
            continue
        with path.open("x", encoding="utf-8") as handle:
            handle.write(source)
        result["sucessos"] += 1
        result["arquivos"].append(str(path.resolve()))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="core1_pdag.db")
    parser.add_argument("--skills-dir")
    args = parser.parse_args()
    print(json.dumps(compilar_tudo(args.db, args.skills_dir), ensure_ascii=False))
