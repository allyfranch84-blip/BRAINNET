import http.client
import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from browser_bridge_transport import BrowserTransport

TOKEN = "a" * 64


@pytest.fixture
def bridge():
    server = BrowserTransport(TOKEN, 0, poll_timeout=.1)
    try:
        yield server
    finally:
        server.close()


def request(bridge, method, path, payload=None, token=TOKEN):
    conn = http.client.HTTPConnection("127.0.0.1", bridge.port, timeout=3)
    headers = {} if token is None else {"X-Brainnet-Token": token}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    try:
        conn.request(method, path, body=None if payload is None else json.dumps(payload), headers=headers)
        response = conn.getresponse()
        return response.status, json.loads(response.read())
    finally:
        conn.close()


def test_unauthenticated_poll_does_not_consume_command(bridge):
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(bridge.send, "PING", 2)
        assert request(bridge, "GET", "/poll", token=None)[0] == 403
        assert request(bridge, "GET", "/poll", token="b"*64)[0] == 403
        assert not bridge.connected
        code, cmd = request(bridge, "GET", "/poll")
        assert code == 200 and cmd["action"] == "PING"
        assert bridge.connected
        result = {"ok": True, "proof": 123}
        assert request(bridge, "POST", "/result", {"id": cmd["id"], "result": result})[0] == 200
        assert future.result() == result


def test_duplicate_and_unknown_results(bridge):
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(bridge.send, "PING", 2)
        _, cmd = request(bridge, "GET", "/poll")
        result = {"id": cmd["id"], "result": {"ok": True}}
        assert request(bridge, "POST", "/result", result, token="b"*64)[0] == 403
        assert not future.done()
        assert request(bridge, "POST", "/result", {**result, "id": "0000000000"})[0] == 409
        assert request(bridge, "POST", "/result", result)[0] == 200
        assert request(bridge, "POST", "/result", result)[0] == 409
        assert future.result() == {"ok": True}


def test_timeout_distinguishes_dispatched_from_queued(bridge):
    result = bridge.send("PING", .05)
    assert result["dispatch_state"] == "NOT_DISPATCHED"
    assert request(bridge, "GET", "/poll")[1]["action"] == "IDLE"
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(bridge.send, "PING", .5)
        _, cmd = request(bridge, "GET", "/poll")
        assert cmd["action"] == "PING"
        assert future.result()["dispatch_state"] == "DISPATCHED_EFFECT_UNKNOWN"
        assert request(bridge, "POST", "/result", {"id": cmd["id"], "result": {"ok": True}})[0] == 409


def test_close_releases_waiting_sender(bridge):
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(bridge.send, "PING", 10)
        _, cmd = request(bridge, "GET", "/poll")
        assert cmd["action"] == "PING"
        bridge.close()
        assert future.result(timeout=1)["dispatch_state"] == "DISPATCHED_EFFECT_UNKNOWN"
        assert not bridge.connected


def test_malformed_and_exact_paths(bridge):
    assert request(bridge, "GET", "/heartbeat?bad=1")[0] == 404
    assert not bridge.connected
    assert request(bridge, "POST", "/result", {"id":"0123456789", "result":{"ok":1}})[0] == 400
    assert request(bridge, "POST", "/result", {"id":"0123456789", "result":{"ok":True,"bad":float('nan')}})[0] == 400
    assert request(bridge, "GET", "/heartbeat")[0] == 200
    assert bridge.connected


def test_queue_is_bounded(bridge):
    bridge._max_pending = 1
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(bridge.send, "PING", 2)
        _, cmd = request(bridge, "GET", "/poll")
        assert bridge.send("PING", 1)["dispatch_state"] == "NOT_DISPATCHED"
        assert request(bridge, "POST", "/result", {"id":cmd["id"],"result":{"ok":True}})[0] == 200
        assert future.result()["ok"]


def test_two_requests_keep_result_identity(bridge):
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(bridge.send, "PING", 2, tag="first")
        second = pool.submit(bridge.send, "PING", 2, tag="second")
        commands = [request(bridge, "GET", "/poll")[1] for _ in range(2)]
        assert {cmd["tag"] for cmd in commands} == {"first", "second"}
        assert commands[0]["id"] != commands[1]["id"]
        for cmd in reversed(commands):
            assert request(bridge, "POST", "/result", {"id": cmd["id"], "result": {"ok": True, "tag": cmd["tag"]}})[0] == 200
        assert first.result()["tag"] == "first"
        assert second.result()["tag"] == "second"


def test_result_before_dispatch_is_rejected(bridge):
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(bridge.send, "PING", 2)
        deadline = time.monotonic() + 1
        with bridge._condition:
            while not bridge._pending and time.monotonic() < deadline:
                bridge._condition.wait(max(0, deadline - time.monotonic()))
            cmd_id = next(iter(bridge._pending))
        payload = {"id": cmd_id, "result": {"ok": True}}
        assert request(bridge, "POST", "/result", payload)[0] == 409
        assert not future.done()
        assert request(bridge, "GET", "/poll")[1]["id"] == cmd_id
        assert request(bridge, "POST", "/result", payload)[0] == 200
        assert future.result()["ok"]


def test_invalid_token_does_not_create_transport():
    with pytest.raises(ValueError):
        BrowserTransport("", 0)


def test_port_collision_preserves_first_server(bridge):
    with pytest.raises(OSError):
        BrowserTransport(TOKEN, bridge.port)
    assert request(bridge, "GET", "/heartbeat")[0] == 200
