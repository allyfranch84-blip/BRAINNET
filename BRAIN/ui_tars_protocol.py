"""Contrato UI-TARS restrito; a saida do modelo nunca e executada como codigo."""
from __future__ import annotations

import ast
import logging

logger = logging.getLogger("BRAINNET_UITars")
import asyncio
from collections import deque
from contextvars import ContextVar
import json
import math
import re
import time
import uuid
from typing import Any, Dict
from execution_authority import authorized_trajectory


_parse_ms = ContextVar("ui_parse_ms", default=None)


def parse_ui_action(response: str, vision_eye=None) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        return _parse_ui_action(response, vision_eye)
    finally:
        _parse_ms.set((time.perf_counter() - started) * 1000.0)


def _parse_ui_action(response: str, vision_eye=None) -> Dict[str, Any]:
    """Interpreta exclusivamente propostas estruturadas, sem executar codigo."""
    if not isinstance(response, str) or not response.strip() or len(response) > 16000:
        raise ValueError("Resposta UI vazia ou excessiva")
    text = response.strip()
    thought = ""
    if text.startswith("{"):
        try:
            envelope = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON visual invalido: {exc.msg}") from exc
        if not isinstance(envelope, dict) or set(envelope) != {"thought", "action"}:
            raise ValueError("Resposta exige somente thought e action")
        thought, expression = envelope["thought"], envelope["action"]
        if not isinstance(thought, str) or not isinstance(expression, str):
            raise ValueError("thought e action devem ser strings")
    else:
        match = re.fullmatch(r"\s*(?:Thought:\s*(.*?)\s*)?Action:\s*(.*?)\s*", text, re.S)
        if not match:
            raise ValueError("Formato visual invalido: esperado JSON ou Thought/Action")
        thought, expression = match.group(1) or "", match.group(2)
    try:
        node = ast.parse(expression, mode="eval").body
    except SyntaxError as exc:
        # Natural language is not a verified target or an executable proposal.
        raise ValueError("Acao visual nao e uma chamada valida") from exc
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
        raise ValueError("Somente chamada de funcao simples e permitida")
    action = node.func.id
    logger.info("[UI-TARS] Tipo de acao gerada: %s", action[:40])
    schema = {"click": {"start_box"}, "left_double": {"start_box"},
              "right_single": {"start_box"}, "drag": {"start_box", "end_box"},
              "type": {"content"}, "hotkey": {"key"}, "scroll": {"direction", "clicks"},
              "wait": set(), "finished": {"content"}}
    if action not in schema:
        raise ValueError(f"Acao UI nao suportada: {action}")
    inputs = {}
    if node.args:
        if node.keywords:
            raise ValueError("Mistura de argumentos posicionais e nomeados nao permitida")
        
        # P0-FIX: Suporte flexivel a argumentos posicionais
        if action in ("click", "left_double", "right_single"):
            if len(node.args) == 2:
                try:
                    x = ast.literal_eval(node.args[0])
                    y = ast.literal_eval(node.args[1])
                    inputs["start_box"] = [x, y]
                except Exception:
                    raise ValueError("Coordenadas posicionais devem ser numeros literais")
            elif len(node.args) == 1:
                value = node.args[0]
                if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                    raise ValueError("Argumento posicional unico deve ser string literal")
                inputs["start_box"] = value.value
            else:
                raise ValueError(f"Numero invalido de argumentos para {action}")
                
        elif action == "drag":
            if len(node.args) == 2:
                try:
                    p1 = ast.literal_eval(node.args[0])
                    p2 = ast.literal_eval(node.args[1])
                    inputs["start_box"] = list(p1)
                    inputs["end_box"] = list(p2)
                except Exception:
                    raise ValueError("Coordenadas de drag devem ser tuplas de numeros")
            else:
                raise ValueError("Drag exige dois argumentos posicionais (start, end)")
                
        elif action in ("type", "finished"):
            if len(node.args) == 1:
                value = node.args[0]
                if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                    raise ValueError("Argumento posicional deve ser string literal")
                inputs["content"] = value.value
            else:
                raise ValueError(f"Numero invalido de argumentos para {action}")
        else:
            raise ValueError(f"Acao {action} nao suporta argumentos posicionais")
    for keyword in node.keywords:
        if keyword.arg is None or keyword.arg in inputs:
            raise ValueError("Argumentos devem ser unicos; expansoes sao proibidas")
        if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
            inputs[keyword.arg] = keyword.value.value
        elif action == "scroll" and keyword.arg == "clicks" and isinstance(keyword.value, ast.Constant) and type(keyword.value.value) is int:
            inputs[keyword.arg] = str(keyword.value.value)
        elif isinstance(keyword.value, ast.Tuple) and action in ("click", "left_double", "right_single", "drag"):
            try:
                inputs[keyword.arg] = ast.literal_eval(keyword.value)
            except (ValueError, SyntaxError) as exc:
                raise ValueError("Coordenadas devem conter apenas numeros literais") from exc
        else:
            raise ValueError("Argumentos devem ser strings literais ou tuplas de coordenadas")
    if set(inputs) != schema[action]:
        raise ValueError(f"Argumentos invalidos para {action}. Recebido: {inputs}. Esperado: {schema[action]}")
    for box_name in ("start_box", "end_box"):
        if box_name not in inputs:
            continue
        raw = inputs[box_name]
        try:
            point = ast.literal_eval(raw) if isinstance(raw, str) else raw
        except (ValueError, SyntaxError) as exc:
            raise ValueError(f"Coordenadas invalidas em {box_name}: {raw}") from exc
        if not isinstance(point, (tuple, list)) or len(point) not in (2, 4):
            raise ValueError(f"{box_name} deve conter duas ou quatro coordenadas")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in point):
            raise ValueError(f"Coordenadas invalidas em {box_name}")
        if len(point) == 4:
            if point[2] < point[0] or point[3] < point[1]:
                raise ValueError(f"Caixa invertida em {box_name}")
            point = ((point[0] + point[2]) / 2, (point[1] + point[3]) / 2)
        inputs[box_name] = list(point)
    if action == "scroll":
        direction, clicks = inputs["direction"].lower(), inputs["clicks"]
        if direction not in ("up", "down") or not re.fullmatch(r"[1-9][0-9]?", clicks):
            raise ValueError("Scroll exige direction up/down e clicks de 1 a 99")
        inputs.update(direction=direction, clicks=int(clicks))
    if action == "hotkey":
        aliases = {"control": "ctrl", "return": "enter", "escape": "esc"}
        keys = [aliases.get(key, key) for key in inputs["key"].lower().split()]
        allowed = {"ctrl", "alt", "shift", "enter", "tab", "esc", "backspace"}
        if not 1 <= len(keys) <= 3 or any(key not in allowed and not re.fullmatch(r"[a-z0-9]", key) for key in keys):
            raise ValueError("Atalho fora do catalogo permitido")
        if len(set(keys)) != len(keys):
            raise ValueError("Atalho com teclas duplicadas")
        inputs["keys"] = keys
    if action == "type" and (not inputs["content"] or len(inputs["content"]) > 4096 or any(ord(c) < 32 for c in inputs["content"])):
        raise ValueError("Texto deve ser literal, limitado e sem teclas de controle; use hotkey")
    return {"thought": thought[:1000], "action_type": action, "action_inputs": inputs}


def protocol_to_dispatch(action: Dict[str, Any], vision, image_size, screen_rect):
    kind, args = action["action_type"], action["action_inputs"]
    if kind in ("click", "left_double", "right_single"):
        x, y = vision.protocol_point_to_screen(args["start_box"], image_size, screen_rect)
        return "mouse_click_at", {"x": x, "y": y,
                                  "button": "right" if kind == "right_single" else "left",
                                  "count": 2 if kind == "left_double" else 1}
    if kind == "drag":
        x1, y1 = vision.protocol_point_to_screen(args["start_box"], image_size, screen_rect)
        x2, y2 = vision.protocol_point_to_screen(args["end_box"], image_size, screen_rect)
        if (x1, y1) == (x2, y2):
            raise ValueError("Arrasto exige pontos inicial e final distintos")
        return "mouse_drag", {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
    if kind == "type":
        return "send_text", {"text": args["content"]}
    if kind == "hotkey":
        return "hotkey", {"keys": args["keys"]}
    if kind == "scroll":
        return "scroll", {"direction": args["direction"], "clicks": args["clicks"]}
    raise ValueError("wait/finished sao controle de fluxo, nao comandos do atuador")


class UIProtocolController:
    """Loop visual opt-in. Cada comando fisico passa por execute_subgoal/NCD.

    O controlador nao abre um shell, nao aplica Python do modelo e nao considera
    finished uma prova. A homologacao do objetivo exige goal_check do hospedeiro.
    """
    def __init__(self, vision, trajectory_engine, context_engine):
        self.vision, self.trajectory = vision, trajectory_engine
        self.context_engine = context_engine
        self._task_lock = asyncio.Lock()

    @authorized_trajectory
    async def run_task(self, task: str, max_steps: int = 8, goal_check=None, allowed_processes=None, task_budget=None):
        if not isinstance(task, str) or not task.strip() or len(task) > 4096:
            raise ValueError("Tarefa UI invalida")
        if not isinstance(max_steps, int) or not 1 <= max_steps <= 16:
            raise ValueError("max_steps deve estar entre 1 e 16")
        async with self._task_lock:
            history, trace = deque(maxlen=8), []
            loop = asyncio.get_running_loop()
            last_verified = None
            task_id = task_budget.task_id if task_budget is not None else uuid.uuid4().hex
            initial_observation = None
            for _ in range(max_steps):
                if task_budget is not None:
                    from adaptive_resource_controller import BudgetExhausted
                    try:
                        task_budget.reserve('visual')
                    except BudgetExhausted as exc:
                        return {'status': 'BUDGET_EXHAUSTED', 'goal_state': 'GOAL_UNVERIFIED',
                                'task_id': task_id, 'sucesso_real': False, 'trace': trace, 'failure_reason': str(exc)}
                capture_started = time.perf_counter()
                image, rect, context = await loop.run_in_executor(None, self.vision.capture_ui_observation, self.context_engine)
                capture_ms = (time.perf_counter() - capture_started) * 1000.0
                hwnd = context.get("hwnd", 0)
                process = str(context.get("process_name", "")).lower()
                if not hwnd or (allowed_processes is not None and process not in allowed_processes):
                    return {"status": "BLOCKED_TARGET", "goal_state": "GOAL_UNVERIFIED",
                            "task_id": task_id, "sucesso_real": False, "trace": trace, "process": process}
                if initial_observation is None:
                    initial_observation = (image.copy(), rect, dict(context))
                try:
                    operation = task_budget.begin_inference() if task_budget is not None else None
                    def infer():
                        _parse_ms.set(None)
                        started = time.perf_counter()
                        completed = False
                        try:
                            proposal = self.vision.describe_ui_with_protocol(image, task, list(history))
                            completed = True
                            total = (time.perf_counter() - started) * 1000.0
                            parsing = _parse_ms.get()
                            return proposal, total, parsing
                        finally:
                            if task_budget is not None:
                                task_budget.finish_inference(operation, confirmed=completed)
                    try:
                        action, inference_total_ms, parsing_ms = await loop.run_in_executor(None, infer)
                    except asyncio.CancelledError:
                        if task_budget is not None:
                            task_budget.cancellation_event.set()
                            task_budget.mark_unconfirmed(operation)
                        raise
                    timings = {"capture_ms": capture_ms,
                               "inference_ms": max(0.0, inference_total_ms - (parsing_ms or 0.0)),
                               "parse_grounding_ms": parsing_ms}
                except (ValueError, SyntaxError) as exc:
                    # Apenas erros de formato recebem uma nova tentativa; alvos
                    # ambíguos e expressões não permitidas permanecem bloqueados.
                    failure = {"action_type": "invalid_proposal", "observation": str(exc)[:500]}
                    if hasattr(exc, 'visual_diagnostic'):
                        failure['diagnostic'] = exc.visual_diagnostic
                    history.append(failure)
                    trace.append(failure)
                    logger.warning("[UI-TARS] task=%s proposta invalida; reobservando", task_id)
                    format_error = str(exc).startswith(('JSON visual invalido', 'Formato visual invalido',
                        'Acao visual nao e uma chamada valida', 'Resposta exige somente thought e action'))
                    if not format_error or sum(1 for item in trace if item.get("action_type") == "invalid_proposal") >= 2:
                        return {"status": "INVALID_PROPOSAL", "goal_state": "GOAL_UNVERIFIED", "task_id": task_id, "sucesso_real": False,
                                "trace": trace, "failure_reason": str(exc)[:500]}
                    continue
                if action["action_type"] == "wait":
                    history.append({"action_type": "wait", "observation": "waiting; no success claimed"})
                    await asyncio.sleep(1.0)
                    continue
                if action["action_type"] == "finished":
                    confirmed = last_verified is not None and last_verified["lambda_obs"] == 1
                    if confirmed and goal_check is not None:
                        confirmed = bool(await loop.run_in_executor(None, goal_check))
                    else:
                        confirmed = False
                        # Somente um canvas fornecido por um sensor confiavel e
                        # explicito pode alimentar a verificacao deterministica.
                        if goal_check is None and last_verified is not None and last_verified["lambda_obs"] == 1:
                            before, before_rect, before_ctx = initial_observation
                            canvas = before_ctx.get("verified_canvas_rect")
                            if (re.search(r"\bc[ií]rculo\b", task, re.I)
                                and re.search(r"\bvermelh[oa]\b", task, re.I)
                                and process == "mspaint.exe" and canvas is not None
                                and before_ctx.get("hwnd") == hwnd and before_rect == rect
                                and context.get("verified_canvas_rect") == canvas):
                                from visual_goal_verifier import verify_new_red_circle
                                try:
                                    local_canvas = (canvas[0] - rect[0], canvas[1] - rect[1],
                                                    canvas[2] - rect[0], canvas[3] - rect[1])
                                    confirmed = await loop.run_in_executor(None, verify_new_red_circle,
                                                                           before, image, local_canvas)
                                except (TypeError, ValueError, IndexError):
                                    confirmed = False
                    return {"status": "CONCLUIDO" if confirmed else "AWAITING_GOAL_VERIFICATION",
                            "goal_state": "GOAL_VERIFIED" if confirmed else "GOAL_UNVERIFIED",
                            "task_id": task_id, "sucesso_real": confirmed, "trace": trace, "proposal": action}
                command, payload = protocol_to_dispatch(action, self.vision, action["image_size"], rect)
                if task_budget is not None and (task_budget.cancellation_event.is_set() or time.monotonic() >= task_budget.deadline_monotonic):
                    task_budget.cancellation_event.set()
                    return {'status': 'CANCEL_REQUESTED', 'goal_state': 'GOAL_UNVERIFIED', 'task_id': task_id,
                            'sucesso_real': False, 'trace': trace, 'failure_reason': 'Prazo ou cancelamento; término de chamadas em andamento não confirmado.'}
                # Cliques repetidos no mesmo pixel indicam que o modelo nao esta
                # progredindo, mesmo que a diferenca de imagens pareca alta.
                if command == "mouse_click_at":
                    previous_clicks = [item for item in trace if item.get("screen_point") == [payload["x"], payload["y"]]]
                    if len(previous_clicks) >= 2:
                        return {"status": "NO_PROGRESS", "goal_state": "GOAL_UNVERIFIED", "task_id": task_id, "sucesso_real": False, "trace": trace,
                                "failure_reason": "O modelo repetiu o mesmo alvo sem progresso confirmado."}

                actuator = {"executed": False}
                async def execute():
                    current = await loop.run_in_executor(None, self.context_engine.capture_foreground_context)
                    if current.get("hwnd") != hwnd or current.get("window_rect") != context.get("window_rect"):
                        raise RuntimeError("Foco/geometria mudou durante a inferencia; reobserve antes de executar")
                    result = await self.trajectory.bridge.dispatch(command, payload)
                    actuator["queue_wait_ms"] = getattr(result, "queue_wait_ms", None)
                    actuator["execution_ms"] = getattr(result, "latency_ms", None)
                    if result.status != "completed" or result.result is not True:
                        raise RuntimeError(f"Atuacao nao confirmada: {result.status}: {result.error}")
                    actuator["executed"] = True

                feedback = await self.trajectory.execute_subgoal(
                    intent_hash=f"ui:{task[:80]}", action_fn=execute,
                    contract={"action": {"send_text": "TYPE", "hotkey": "HOTKEY", "mouse_drag": "DRAG", "scroll": "SCROLL"}.get(command, "CLICK"),
                              "expects_new_pid": False, "min_ncd": 0.05 if command == "mouse_click_at" else 0.02,
                              "target_hwnd": hwnd},
                    click_target=({"element": f"xy({payload['x']},{payload['y']})", "x": payload["x"], "y": payload["y"]}
                                  if command == "mouse_click_at" else None),
                )
                entry = {"action_type": action["action_type"], "action_inputs": action["action_inputs"], "feedback": feedback}
                entry["action_state"] = ("ACTION_OBSERVED" if feedback["lambda_obs"] == 1
                                         else "ACTION_EXECUTED" if actuator["executed"] else "ACTION_FAILED")
                entry["execution_state"] = "ACTION_EXECUTED" if actuator["executed"] else "ACTION_FAILED"
                entry["observation_state"] = "ACTION_OBSERVED" if feedback["lambda_obs"] == 1 else None
                timings.update(queue_wait_ms=actuator.get("queue_wait_ms"),
                               execution_ms=actuator.get("execution_ms"),
                               verification_ms=feedback.get("verification_ms"))
                entry["timings_ms"] = timings
                logger.info("[UI-TARS] task=%s action=%s state=%s timings_ms=%s", task_id,
                            action["action_type"], entry["action_state"], timings)
                if command == "mouse_click_at":
                    entry["screen_point"] = [payload["x"], payload["y"]]
                history.append(entry)
                trace.append(entry)
                if feedback["lambda_obs"] != 1:
                    return {"status": "FAILED_FACTUAL", "goal_state": "GOAL_UNVERIFIED",
                            "task_id": task_id, "sucesso_real": False, "trace": trace}
                last_verified = feedback
            return {"status": "STEP_LIMIT", "goal_state": "GOAL_UNVERIFIED",
                    "task_id": task_id, "sucesso_real": False, "trace": trace}
