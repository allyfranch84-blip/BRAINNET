"""Authenticated loopback transport; no browser, model or desktop dependencies."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
import uuid

from browser_bridge_protocol import authorized, read_result, valid_token


class BrowserTransport:
    def __init__(self, token, port=9876, *, poll_timeout=8.0, max_pending=32):
        if not valid_token(token):
            raise ValueError("Configure BRAINNET_BROWSER_TOKEN")
        self._token = token
        self._condition = threading.Condition()
        self._pending = {}
        self._closed = False
        self._last_seen = None
        self._poll_timeout = poll_timeout
        self._max_pending = max_pending
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def setup(self):
                self.request.settimeout(5.0)
                super().setup()

            def reply(self, code, value):
                raw = json.dumps(value, ensure_ascii=True, allow_nan=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except OSError:
                    pass

            def authenticate(self):
                values = self.headers.get_all("X-Brainnet-Token", [])
                if len(values) != 1 or not authorized(owner._token, values[0]):
                    self.reply(403, {"ok": False, "error": "Unauthorized"})
                    return False
                return True

            def do_GET(self):
                if not self.authenticate():
                    return
                if self.path == "/heartbeat":
                    owner.touch()
                    self.reply(200, {"ok": True, "status": "alive"})
                elif self.path == "/poll":
                    owner.touch()
                    command = owner.pull()
                    self.reply(200, command or {"id": None, "action": "IDLE"})
                else:
                    self.reply(404, {"ok": False, "error": "Unknown route"})

            def do_POST(self):
                if not self.authenticate():
                    return
                if self.path != "/result":
                    self.reply(404, {"ok": False, "error": "Unknown route"})
                    return
                try:
                    if any(len(self.headers.get_all(h, [])) != 1 for h in ("Content-Length", "Content-Type")):
                        raise ValueError("Ambiguous headers")
                    cmd_id, result = read_result(self.headers, self.rfile)
                    json.dumps(result, allow_nan=False)
                except (ValueError, OSError, RecursionError):
                    self.reply(400, {"ok": False, "error": "Invalid result"})
                    return
                if not owner.complete(cmd_id, result):
                    self.reply(409, {"ok": False, "error": "Unknown, expired, undispatched or duplicate result"})
                    return
                self.reply(200, {"ok": True})

        self._server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
        self._thread.start()

    def touch(self):
        with self._condition:
            if not self._closed:
                self._last_seen = time.monotonic()

    @property
    def connected(self):
        with self._condition:
            return not self._closed and self._last_seen is not None and time.monotonic() - self._last_seen < 12

    def send(self, action, timeout=10.0, **kwargs):
        if not isinstance(action, str) or not action or not 0 < timeout <= 120:
            raise ValueError("Invalid action or timeout")
        with self._condition:
            if self._closed or len(self._pending) >= self._max_pending:
                return {"ok": False, "error": "Bridge closed or busy", "dispatch_state": "NOT_DISPATCHED"}
            cmd_id = uuid.uuid4().hex[:10]
            while cmd_id in self._pending:
                cmd_id = uuid.uuid4().hex[:10]
            deadline = time.monotonic() + timeout
            row = {"command": {**kwargs, "id": cmd_id, "action": action, "deadline_epoch_ms": int((time.time() + timeout) * 1000)},
                   "deadline": deadline, "dispatched": False, "result": None}
            json.dumps(row["command"], allow_nan=False)
            self._pending[cmd_id] = row
            self._condition.notify_all()
            try:
                while not self._closed and row["result"] is None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self._condition.wait(remaining)
                if row["result"] is not None:
                    return row["result"]
                return {"ok": False, "error": "Bridge closed or deadline exceeded",
                        "dispatch_state": "DISPATCHED_EFFECT_UNKNOWN" if row["dispatched"] else "NOT_DISPATCHED"}
            finally:
                self._pending.pop(cmd_id, None)

    def pull(self):
        deadline = time.monotonic() + self._poll_timeout
        with self._condition:
            while not self._closed:
                now = time.monotonic()
                for row in self._pending.values():
                    if not row["dispatched"] and row["deadline"] > now:
                        row["dispatched"] = True
                        return dict(row["command"])
                remaining = deadline - now
                if remaining <= 0:
                    break
                self._condition.wait(remaining)
        return None

    def complete(self, cmd_id, result):
        with self._condition:
            row = self._pending.get(cmd_id)
            if self._closed or row is None or not row["dispatched"] or row["result"] is not None or row["deadline"] <= time.monotonic():
                return False
            row["result"] = result
            self._last_seen = time.monotonic()
            self._condition.notify_all()
            return True

    def close(self):
        with self._condition:
            if self._closed:
                return
            self._closed = True
            self._condition.notify_all()
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)
