"""Explicit Windows field battery. Never runs on import or on a timer."""
import asyncio
import json
import logging
import sqlite3
import threading
import time
import uuid

from execution_authority import authorized_trajectory, authorization_scope, require_action_allowed

logger = logging.getLogger("BRAINNET_FieldTests")
TEXT = "Teste, pontuação! Funciona?"
FIELD_TEST_SCHEMA = """CREATE TABLE IF NOT EXISTS field_tests (
    id TEXT PRIMARY KEY, started_at REAL NOT NULL, completed_at REAL NOT NULL,
    results_json TEXT NOT NULL, report_markdown TEXT NOT NULL
)"""


def _process_evidence(app):
    from system_intent import find_app_process
    process = find_app_process(app)
    return {"detected": process is not None, **(process or {})}


def _window_evidence(app):
    import psutil
    import win32gui
    import win32process
    from system_intent import app_process_names, find_app_window_by_title
    titled = find_app_window_by_title(app)
    if titled:
        return {"detected": True, **titled}
    matches = []
    def inspect(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            name = psutil.Process(pid).name().casefold()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return
        title = win32gui.GetWindowText(hwnd)
        from system_intent import hosted_app_window
        if name in app_process_names(app) or (name == "applicationframehost.exe" and hosted_app_window(app, hwnd)):
            matches.append({"detected": True, "hwnd": hwnd, "pid": pid, "process_name": name, "title": title})
    win32gui.EnumWindows(inspect, None)
    return matches[0] if matches else {"detected": False, "hwnd": 0}


def _app_evidence(app):
    import psutil
    import win32gui
    import win32process
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd or not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
        return {"detected": False, "hwnd": hwnd or 0}
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    name = psutil.Process(pid).name().casefold()
    title = win32gui.GetWindowText(hwnd)
    from system_intent import app_process_names, hosted_app_window
    detected = name in app_process_names(app) or (name == "applicationframehost.exe" and bool(hosted_app_window(app, hwnd)))
    return {"detected": detected, "hwnd": hwnd, "pid": pid, "process_name": name, "title": title}


def _read_notepad_text(hwnd, expected=TEXT):
    import uiautomation as auto
    with auto.UIAutomationInitializerInThread():
        control = auto.ControlFromHandle(hwnd)
        if control is None:
            raise RuntimeError("UIA não encontrou a janela do Notepad")
        for index, (child, _) in enumerate(auto.WalkControl(control, includeTop=True, maxDepth=8)):
            if index >= 300:
                break
            if child.ControlTypeName not in ("EditControl", "DocumentControl"):
                continue
            try:
                pattern = child.GetTextPattern()
                if pattern:
                    content = pattern.DocumentRange.GetText(10000)
                    if (expected is None and not content.strip()) or (expected is not None and expected in content):
                        return content
            except Exception as ex:
                logger.debug("Controle sem TextPattern legível: %s", ex)
    raise RuntimeError("Texto exato não pôde ser confirmado pela UIA")


async def _dispatch(engine, action, payload):
    require_action_allowed(action)
    result = await engine.bridge.dispatch(action, payload)
    if result.status != "completed" or result.result is not True:
        raise RuntimeError(f"Atuador não confirmou {action}: {result.status}")


async def _measure(engine, before, pids, hwnd):
    return await asyncio.to_thread(engine.verifier.measure_collapse,
        pid_snapshot_before=pids, img_pre_bytes=before, img_post_bytes=b"", timeout_sec=2.0,
        expected_delta=0.0, contract={"action": "WAIT", "expects_new_pid": False, "min_ncd": .02, "target_hwnd": hwnd})


def _markdown(rows):
    lines = ["| Cenário | Esperado | Observado | NCD | Tempo (ms) | Status |",
             "| :--- | :--- | :--- | :--- | ---: | :--- |"]
    for row in rows:
        escape = lambda value: str(value).replace("|", "\\|").replace("\n", " ")
        ncd = "Não medido" if row["ncd"] is None else f"{row['ncd']:.4f}"
        lines.append(f"| {escape(row['scenario'])} | {escape(row['expected'])} | {escape(row['observed'])} | {ncd} | {row['elapsed_ms']:.3f} | {row['status']} |")
    return "\n".join(lines)


def _save(db_path, run_id, started, rows, markdown):
    with sqlite3.connect(db_path, timeout=5) as conn:
        conn.execute(FIELD_TEST_SCHEMA)
        conn.execute("INSERT INTO field_tests VALUES (?, ?, ?, ?, ?)",
                     (run_id, started, time.time(), json.dumps(rows, ensure_ascii=False), markdown))


@authorized_trajectory
async def run_field_tests(kernel, authorization_token=None):
    engine, rows = kernel.trajectory_engine, []
    run_id, started = str(uuid.uuid4()), time.time()
    notepad_ready = False

    for scenario, expected in (("Abrir Notepad", "Processo do Notepad ativo na memória"),
                               ("Digitação", TEXT),
                               ("Calculadora via Menu Iniciar", "Processo UWP da Calculadora ativo após 3 segundos"),
                               ("Cancelamento", "Espera abortada e autorização revogada")):
        tick = time.perf_counter_ns()
        row = {"scenario": scenario, "expected": expected, "observed": "", "ncd": None,
               "status": "❌ FALHOU", "evidence": {}}
        try:
            require_action_allowed("EXECUTE")
            if scenario == "Abrir Notepad":
                async def open_notepad():
                    return await engine._start_menu_search("notepad")
                feedback = await engine.execute_subgoal(f"field:{run_id}:open", open_notepad,
                    contract=engine._contract_for_action("START_MENU_SEARCH", "notepad"),
                    intent="teste_campo: abrir notepad", step={"acao": "START_MENU_SEARCH", "app": "notepad"})
                evidence = await asyncio.to_thread(_app_evidence, "notepad")
                process = await asyncio.to_thread(_process_evidence, "notepad")
                notepad_ready = feedback.get("lambda_obs") == 1 and process["detected"]
                row.update(ncd=feedback.get("ncd_real"), evidence={"process": process, "window": evidence, "feedback": feedback},
                           observed="Processo do Notepad ativo na memória" if process["detected"] else "Processo do Notepad não detectado")
                if notepad_ready:
                    row["status"] = "✅ PASSOU"
            elif scenario == "Digitação":
                if not notepad_ready:
                    row.update(status="⚠️ INCONCLUSIVO", observed="Abertura não confirmada; nenhuma digitação enviada")
                else:
                    async def type_text():
                        # Request a fresh document; delayed UIA is not a success sensor.
                        await asyncio.sleep(1.5)
                        await asyncio.to_thread(engine.resolver.find_and_focus_window, "notepad")
                        await asyncio.sleep(1.0)
                        if not (await asyncio.to_thread(_app_evidence, "notepad"))["detected"]:
                            raise RuntimeError("Notepad ativo sem foco; digitação bloqueada")
                        await _dispatch(engine, "hotkey", {"keys": ["ctrl", "n"]})
                        await asyncio.sleep(.8)
                        evidence = await asyncio.to_thread(_app_evidence, "notepad")
                        if not evidence["detected"]:
                            raise RuntimeError("Novo documento não permaneceu no Notepad")
                        await _dispatch(engine, "send_text", {"text": TEXT})
                        return {"professor_target_hwnd": evidence["hwnd"]}
                    feedback = await engine.execute_subgoal(f"field:{run_id}:type", type_text,
                        contract={"action": "TYPE", "app": "notepad", "expects_new_pid": False, "min_ncd": .05},
                        intent="teste_campo: digitar pontuação", step={"acao": "FIELD_TYPE", "text": TEXT, "prepare": ["ctrl", "n"]})
                    evidence = await asyncio.to_thread(_app_evidence, "notepad")
                    process = await asyncio.to_thread(_process_evidence, "notepad")
                    row.update(ncd=feedback.get("ncd_real"), evidence={"window": evidence, "process": process, "feedback": feedback})
                    if feedback.get("lambda_obs") != 1 or not process["detected"] or feedback.get("ncd_real") is None or feedback["ncd_real"] <= .05:
                        row["observed"] = "Digitação ou janela não confirmada: " + str(feedback.get("failure_reason", ""))
                    else:
                        row.update(observed="Digitação confirmada por NCD > 0,05 e processo do Notepad ativo", status="✅ PASSOU")
            elif scenario == "Calculadora via Menu Iniciar":
                async def open_calculator():
                    async with engine.bridge._input_lock:
                        await asyncio.to_thread(engine.resolver._open_via_start_menu, "calculadora")
                    await asyncio.sleep(3.0)
                    return {}
                feedback = await engine.execute_subgoal(f"field:{run_id}:calculator", open_calculator,
                    contract=engine._contract_for_action("OPEN_APP", "calc"),
                    intent="teste_campo: calculadora pelo Menu Iniciar",
                    step={"acao": "OPEN_APP", "app": "calculadora", "settle_seconds": 3.0})
                evidence = await asyncio.to_thread(_window_evidence, "calc")
                process = await asyncio.to_thread(_process_evidence, "calc")
                ncd = feedback.get("ncd_real")
                elapsed = (time.perf_counter_ns() - tick) / 1_000_000_000
                visual_fallback = ncd is not None and ncd > 0.90 and elapsed < 15.0
                observed = ("Processo da Calculadora/UWP ativo" if process["detected"] else
                    "Janela da Calculadora detectada" if evidence["detected"] else
                    "Mudança visual > 0,90 em menos de 15 segundos (fallback)" if visual_fallback else
                    "Calculadora não confirmada")
                row.update(ncd=ncd, observed=observed,
                    evidence={"window": evidence, "process": process, "feedback": feedback,
                        "visual_fallback": visual_fallback, "launch_method": "_open_via_start_menu"})
                if process["detected"] or evidence["detected"] or visual_fallback:
                    row["status"] = "✅ PASSOU"
            else:
                before = await asyncio.to_thread(engine.verifier.capture_state_bytes)
                pids = await asyncio.to_thread(engine.verifier.snapshot_pids)
                context = await asyncio.to_thread(engine.ctx_engine.capture_foreground_context)
                started_wait, completed, child_token = asyncio.Event(), False, threading.Event()
                async def waiting_action():
                    nonlocal completed
                    with authorization_scope(child_token):
                        started_wait.set()
                        await engine._executar_passo_individual({"acao": "WAIT", "seconds": 30.0})
                        completed = True
                task = asyncio.create_task(waiting_action())
                try:
                    await started_wait.wait()
                    child_token.set()
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        cancelled = True
                    else:
                        cancelled = False
                finally:
                    child_token.set()
                    if not task.done():
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
                blocked = False
                with authorization_scope(child_token):
                    try:
                        require_action_allowed("TYPE")
                    except PermissionError:
                        blocked = True
                measured = await _measure(engine, before, pids, context.get("hwnd", 0))
                row.update(ncd=measured[4], observed="CancelledError confirmado; escrita bloqueada" if cancelled and blocked and not completed else "Cancelamento não confirmado",
                           evidence={"cancelled": cancelled, "completed": completed, "revoked_write_blocked": blocked,
                                     "context": context, "verifier_lambda": measured[0], "verifier_reason": measured[2]})
                if cancelled and task.cancelled() and blocked and not completed:
                    row["status"] = "✅ PASSOU"
        except Exception as ex:
            logger.exception("[FIELD_TEST] Cenário falhou: %s", scenario)
            row["observed"] = f"{type(ex).__name__}: {ex}"
        row["elapsed_ms"] = (time.perf_counter_ns() - tick) / 1_000_000
        rows.append(row)
    markdown = _markdown(rows)
    await asyncio.to_thread(_save, kernel.pdag.db_path, run_id, started, rows, markdown)
    return {"reply": f"Teste de campo `{run_id}`\n\n{markdown}\n\nRelatório salvo em `field_tests`.",
            "logs": [], "field_test_id": run_id}
