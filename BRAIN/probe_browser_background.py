"""Opt-in Windows probe: real extension, public test query, disposable SQLite."""
import argparse
import json
import os
from pathlib import Path
import socket
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

from browser_bridge_protocol import valid_token


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Authorize one public test search")
    args = parser.parse_args()
    if not args.run:
        parser.print_help()
        return 2
    if os.name != "nt":
        print("BLOCKED: requires Windows")
        return 2
    if not valid_token(os.environ.get("BRAINNET_BROWSER_TOKEN", "")):
        print("BLOCKED: configure the local bridge token first")
        return 2
    # Never stop an existing bridge or use its private state.
    with socket.socket() as sock:
        sock.settimeout(1)
        if sock.connect_ex(("127.0.0.1", 9876)) == 0:
            print("BLOCKED: port 9876 in use; close the existing bridge manually")
            return 2
    import win32gui
    from browser_bridge import BrowserDeepBridge
    with tempfile.TemporaryDirectory(prefix="bn-web-probe-") as directory:
        bridge = BrowserDeepBridge(None, None, None, db_path=str(Path(directory) / "probe.sqlite3"))
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline and not bridge.extension_connected:
            time.sleep(.25)
        if not bridge.extension_connected:
            print("BLOCKED: authenticated extension heartbeat not observed")
            return 2
        focus = win32gui.GetForegroundWindow()
        cursor = win32gui.GetCursorPos()
        focus_stable = True
        cursor_stable = True
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(bridge.research_background, "Python sqlite3 official documentation")
            while not future.done():
                focus_stable &= win32gui.GetForegroundWindow() == focus
                cursor_stable &= win32gui.GetCursorPos() == cursor
                time.sleep(.05)
            result = future.result()
        focus_stable &= win32gui.GetForegroundWindow() == focus
        cursor_stable &= win32gui.GetCursorPos() == cursor
        report = {
            "elapsed_ms": round((time.perf_counter()-start)*1000),
            "result": result,
            "foreground_unchanged_at_samples": focus_stable,
            "cursor_unchanged_at_samples": cursor_stable,
            "sampling_ms_approx": 50,
        }
        passed = (result.get("ok") is True and result.get("browser_active_tab_unchanged") is True
                  and result.get("cleanup") == "OWNED_TAB_REMOVED" and focus_stable and cursor_stable)
        report["classification"] = "PASS_REAL" if passed else "INCONCLUSIVE_OR_FAILED"
        print(json.dumps(report, ensure_ascii=True, indent=2))
        return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
