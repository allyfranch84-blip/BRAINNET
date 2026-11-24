"""Explicit read-only UIA diagnostic for an already open controlled window.

This module never changes focus, starts an app, captures pixels or actuates.
"""
import argparse
import datetime
import json
import time
import uuid


def diagnose(hwnd, pid, *, inspect, scan, provider_available, include_names=False):
    start = time.perf_counter()
    result = {'diagnostic_id': uuid.uuid4().hex,
              'timestamp_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'hwnd': hwnd, 'pid': pid, 'status': 'UNAVAILABLE',
              'uia_library_available': bool(provider_available),
              'uia_provider_status': 'UNKNOWN', 'control_count': None}
    try:
        before = inspect(hwnd)
        if not before or not before.get('controlled') or before.get('pid') != pid:
            result.update(status='TARGET_INVALID', reason='window, pid or controlled-window identity not confirmed')
        elif not provider_available:
            result['process_name'] = before.get('process_name')
            result.update(status='PROVIDER_UNAVAILABLE', reason='uiautomation is unavailable')
        else:
            result['process_name'] = before.get('process_name')
            rows = scan(hwnd)
            after = inspect(hwnd)
            if not after or any(after.get(k) != before.get(k) for k in ('pid', 'started', 'controlled')):
                result.update(status='CONTEXT_CHANGED', reason='window or process identity changed')
            elif not isinstance(rows, list):
                result.update(status='ERROR', reason='unexpected scan result type')
            elif not rows:
                result.update(status='EMPTY_OR_PROVIDER_UNAVAILABLE', control_count=0,
                              reason='existing API returns an empty list for multiple conditions')
            else:
                def has_evidence(item):
                    if not isinstance(item, dict):
                        return False
                    kind, rect = item.get('control_type'), item.get('rect')
                    return (isinstance(kind, str) and bool(kind.strip())) or (
                        isinstance(rect, (tuple, list)) and len(rect) == 4 and
                        all(type(value) is int for value in rect))
                valid = [item for item in rows if has_evidence(item)]
                if not valid:
                    result.update(status='INSUFFICIENT_EVIDENCE', control_count=len(rows),
                                  reason='controls lack usable type and geometry')
                    result['elapsed_ms'] = round((time.perf_counter() - start) * 1000, 3)
                    return result
                result.update(status='OBSERVED', control_count=len(rows), uia_provider_status='RESPONDED')
                examples = []
                for item in valid[:3]:
                    example = {'control_type': item.get('control_type'), 'rect': item.get('rect')}
                    if include_names:
                        example['name'] = item.get('name')
                        example['automation_id'] = item.get('automation_id')
                    examples.append(example)
                result['examples'] = examples
    except Exception as exc:
        result.update(status='ERROR', reason=type(exc).__name__)
    result['elapsed_ms'] = round((time.perf_counter() - start) * 1000, 3)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hwnd', required=True, type=lambda x: int(x, 0))
    p.add_argument('--pid', required=True, type=int)
    p.add_argument('--include-control-names', action='store_true', help='explicitly allow potentially sensitive UIA Names')
    args = p.parse_args()
    import ctypes
    from ctypes import wintypes
    try:
        import psutil
        import perception_eye
    except ImportError as exc:
        print(json.dumps({'status': 'DEPENDENCY_UNAVAILABLE', 'hwnd': args.hwnd,
                          'pid': args.pid, 'reason': type(exc).__name__}))
        return 2

    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

    def inspect(hwnd):
        if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
            return None
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process = psutil.Process(pid.value)
        name = process.name().lower()
        controlled = name == 'notepad.exe'
        if not controlled:
            length = min(user32.GetWindowTextLengthW(hwnd), 512)
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)
            controlled = title.value == 'BRAINNET — Laboratório seguro'
        return {'pid': pid.value, 'started': process.create_time(), 'controlled': controlled, 'process_name': name}

    eye = perception_eye.PerceptionEye.__new__(perception_eye.PerceptionEye)
    result = diagnose(args.hwnd, args.pid, inspect=inspect,
                      scan=lambda hwnd: eye.scan_uia_properties(
                          hwnd, max_controls=100, include_sensitive=args.include_control_names),
                      provider_available=perception_eye.HAS_UIA_NATIVE,
                      include_names=args.include_control_names)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] == 'OBSERVED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
