"""Small fail-closed protocol for the local Chromium bridge."""
import hmac
import json
import re

TOKEN = re.compile(r"[0-9a-f]{64}\Z")
COMMAND_ID = re.compile(r"[0-9a-f]{10}\Z")
MAX_RESULT_BYTES = 256 * 1024


def valid_token(value):
    return isinstance(value, str) and TOKEN.fullmatch(value) is not None


def authorized(expected, supplied):
    return valid_token(expected) and valid_token(supplied) and hmac.compare_digest(expected, supplied)


def read_result(headers, stream):
    if headers.get("Transfer-Encoding") is not None:
        raise ValueError("Transfer-Encoding not supported")
    if headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise ValueError("JSON required")
    length = headers.get("Content-Length", "")
    if not re.fullmatch(r"[0-9]{1,6}", length):
        raise ValueError("Invalid length")
    size = int(length)
    if not 1 <= size <= MAX_RESULT_BYTES:
        raise ValueError("Invalid length")
    data = stream.read(size)
    if len(data) != size:
        raise ValueError("Incomplete body")
    obj = json.loads(data.decode("utf-8"))
    if not isinstance(obj, dict) or set(obj) != {"id", "result"}:
        raise ValueError("Invalid result envelope")
    if not isinstance(obj["id"], str) or COMMAND_ID.fullmatch(obj["id"]) is None:
        raise ValueError("Invalid command ID")
    if not isinstance(obj["result"], dict) or type(obj["result"].get("ok")) is not bool:
        raise ValueError("Invalid result")
    return obj["id"], obj["result"]
