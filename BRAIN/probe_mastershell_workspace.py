"""Opt-in Windows smoke test of the official React bundle and minimal Python bridge."""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time


ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / "INTERFACE DE USUARIO/BRAINDET IU/project"


class BundleHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self' 'unsafe-eval' 'unsafe-inline'; "
                         "style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'; "
                         "frame-ancestors 'none'; form-action 'self'")
        super().end_headers()


def exercise(work):
    bundle = work / "bundle"
    subprocess.run(["npm.cmd", "run", "build", "--", "--outDir", str(bundle)], cwd=GUI,
                   check=True, timeout=180)
    os.environ.update(LOCALAPPDATA=str(work), BRAINNET_MINIMAL="1", BRAINNET_MANAGE_INFERENCE="0",
                      BRAINNET_P4_DIRECT_MOVE="0", BRAINNET_P4_PHYSICAL_PROPOSALS="0",
                      BRAINNET_MOTOR_SEMANTIC="0", BRAINNET_PERCEPTUAL_PRESENT="0",
                      BRAINNET_PERSIST_EXPERIENCES="0", BRAINNET_ADAPTIVE_OBSERVE="0")
    import BRAINNET as app
    import webview
    import workspace_chat_archive as archive
    app.CONFIG_FILE = work / "test-config.json"
    kernel = app.BrainnetKernel()
    bridge = app.BrainnetBridge(kernel)
    worker = threading.Thread(target=app.start_kernel_thread, args=(kernel,), daemon=True)
    worker.start()
    result = {}
    handler = functools.partial(BundleHandler, directory=str(bundle))
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        http = threading.Thread(target=server.serve_forever, daemon=True)
        http.start()
        window = webview.create_window("BRAINNET · teste de integração", url=f"http://127.0.0.1:{server.server_port}/",
                                       js_api=bridge, width=1100, height=720, focus=False)
        bridge._window = window

        def wait_for(stage, check):
            deadline = time.monotonic() + 18
            while time.monotonic() < deadline:
                value = check()
                if value:
                    return value
                time.sleep(0.15)
            raise RuntimeError(f"Tempo esgotado: {stage}")

        def run():
            try:
                js = window.evaluate_js
                wait_for("React/PyWebView", lambda: js("Boolean(window.pywebview?.api?.send_command && document.querySelector('[aria-label=\"Abrir chat\"]'))"))
                js("document.querySelector('[aria-label=\"Abrir chat\"]').click(); true")
                wait_for("arquivo de conversas", lambda: js("Boolean(document.querySelector('select[aria-label=\"Conversas salvas\"]')?.value)"))
                def send(text):
                    js("""((text) => {
                    const el = document.querySelector('.bn-main-form input');
                    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,text);
                    el.dispatchEvent(new Event('input',{bubbles:true}));
                    return true;
                    })(""" + json.dumps(text) + ")")
                    js("document.querySelector('.bn-main-form').requestSubmit(); true")
                started = time.perf_counter()
                send("/kernel status")
                needle = f"Kernel real: pronto; PID {os.getpid()}; perfil mínimo;"
                wait_for("resposta no Chat com PID atual", lambda: js(
                    "document.querySelector('.bn-chat-messages')?.innerText.includes(" + json.dumps(needle) + ")"))
                result["observed_roundtrip_ms"] = round((time.perf_counter()-started)*1000, 2)
                def saved_reply():
                    for chat in archive.listing():
                        for row in archive.load(chat["id"]):
                            if row["role"] == "ai" and needle in row["text"] and row.get("taskId"):
                                return row
                row = wait_for("resposta persistida com taskId", saved_reply)
                result.update(pid=os.getpid(), task_id=row["taskId"], status=row.get("resultStatus"),
                              gui_roundtrip_ms=row.get("durationMs"), private_archive=True)
                if result["status"] != "READY":
                    raise RuntimeError("Estado persistido divergente")
                select = "document.querySelector('select[aria-label=\"Conversas salvas\"]')"
                first = js(select + ".value")
                js("Array.from(document.querySelectorAll('.bn-archive-menu button')).find(b=>b.textContent.includes('Nova conversa')).click(); true")
                wait_for("nova conversa isolada", lambda: js(select + ".value !== " + json.dumps(first)
                    + " && !document.querySelector('.bn-chat-messages').innerText.includes(" + json.dumps(needle) + ")"))
                send("/nota criar GuiaTeste | [Fonte](https://example.org/) e [[MotorTeste]]")
                wait_for("criação de nota", lambda: js("document.querySelector('.bn-chat-messages').innerText.includes('NOTE_SAVED')"))
                send("/nota ler GuiaTeste")
                wait_for("Markdown com link e referência interna", lambda: js(
                    "Boolean(document.querySelector('.bn-chat-messages a[href=\"https://example.org/\"]') && "
                    "Array.from(document.querySelectorAll('.bn-chat-messages .bn-link')).some(b=>b.textContent==='MotorTeste'))"))
                wait_for("controle de troca habilitado com destino arquivado", lambda: js(
                    f"!({select}).disabled && Array.from(({select}).options).some(o=>o.value==={json.dumps(first)})"))
                js(f"({select}).value={json.dumps(first)}; ({select}).dispatchEvent(new Event('change',{{bubbles:true}})); true")
                wait_for("restauração da primeira conversa", lambda: js(
                    "document.querySelector('.bn-chat-messages').innerText.includes(" + json.dumps(needle) + ")"
                    " && !document.querySelector('.bn-chat-messages a[href=\"https://example.org/\"]')"))
                result.update(chat_switch=True, markdown_link=True, wiki_link=True)
            except Exception as exc:
                result["error"] = f"{type(exc).__name__}: {exc}"
                # This window reads only the fresh synthetic archive owned by the probe.
                result["archive_diagnostic"] = window.evaluate_js("""(() => {
                    const el=document.querySelector('select[aria-label="Conversas salvas"]');
                    return {choices:el?.options.length, disabled:el?.disabled,
                      selected:el?.value, alert:document.querySelector('.bn-archive-menu [role=alert]')?.textContent,
                      statusVisible:document.querySelector('.bn-chat-messages')?.innerText.includes('Kernel real: pronto'),
                      noteVisible:!!document.querySelector('.bn-chat-messages a[href="https://example.org/"]')};
                })()""")
            finally:
                window.destroy()

        try:
            webview.start(run, private_mode=True, storage_path=str(work / "webview"))
        finally:
            kernel.is_running = False
            worker.join(5)
            server.shutdown()
            http.join(2)
    result["shutdown"] = not worker.is_alive() and not kernel.bridge._running and not http.is_alive()
    if result.get("chat_switch"):
        # A second interpreter must recover both the original task and the saved note.
        import sys
        verify = subprocess.run([sys.executable, "-B", "-c",
            "import sys,workspace_chat_archive as a; from workspace_notes import Notes; "
            "assert any(m.get('taskId')==sys.argv[1] for c in a.listing() for m in a.load(c['id'])); "
            "assert len(a.listing())==2 and '[[MotorTeste]]' in Notes().by_title('GuiaTeste')['body']",
            result["task_id"]], cwd=ROOT / "BRAIN", timeout=15, check=False)
        result["reopened_in_new_process"] = verify.returncode == 0
        if verify.returncode:
            result["error"] = "Arquivo não confirmado por um novo processo"
    result["result"] = "PASS_REAL" if result.get("status") == "READY" and result["shutdown"] and "error" not in result else "FAIL"
    return result


if __name__ == "__main__":
    import sys
    if os.name != "nt" or sys.argv[1:] != ["--run"]:
        raise SystemExit("Uso explícito em Windows: probe_mastershell_workspace.py --run")
    # PyWebView derives base_uri from argv[0] on import, after we change cwd.
    sys.argv[0] = str(Path(__file__).resolve())
    scratch = ROOT / ".pytest_runs"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="shell-", dir=scratch, ignore_cleanup_errors=True) as folder:
        original = Path.cwd()
        try:
            os.chdir(folder)
            result = exercise(Path(folder))
        finally:
            os.chdir(original)
    print(json.dumps(result, ensure_ascii=True), flush=True)
    raise SystemExit(0 if result["result"] == "PASS_REAL" else 1)
