"""P1-only real PyWebView bridge: explicit UIA observation, no full kernel."""
from __future__ import annotations
import argparse
import re
from uia_chat_readonly import scan_explicit_window, chat_reply

class ReadOnlyBridge:
    def send_command(self, text):
        m = re.fullmatch(r'\s*/uia\s+scan\s+(\d+)\s+(\d+)\s*', text or '', re.I)
        if not m:
            return {'status': 'TARGET_REQUIRED', 'reply': 'Modo diagnóstico: use /uia scan <HWND> <PID>.', 'logs': []}
        try:
            from perception_eye import PerceptionEye, HAS_UIA_NATIVE
            # The scanner method has no dependency on initialized Eye state.
            eye = object.__new__(PerceptionEye)
            result = scan_explicit_window(int(m.group(1)), int(m.group(2)), scanner=eye.scan_uia_properties, provider_available=HAS_UIA_NATIVE)
            return {**result, 'reply': chat_reply(result), 'logs': [], 'source': 'windows_uia_readonly'}
        except Exception as exc:
            return {'status': 'UNAVAILABLE', 'reply': f'UIA indisponível: {type(exc).__name__}', 'logs': []}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535: parser.error('porta inválida')
    import webview
    webview.create_window('BRAINNET — P1 diagnóstico UIA (sem Kernel)', f'http://127.0.0.1:{args.port}', js_api=ReadOnlyBridge())
    webview.start(debug=False, private_mode=True)

if __name__ == '__main__': main()
