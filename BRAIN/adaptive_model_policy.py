"""Read-only model selection and explicit local Ollama benchmark (no auto-pull)."""
import argparse
import json
import time
from urllib.error import HTTPError
from urllib.request import Request, HTTPRedirectHandler, ProxyHandler, build_opener

ENDPOINT = 'http://127.0.0.1:11435'
PREFERENCES = {
    'FAST': ('qwen2.5:1.5b', 'qwen3:4b-instruct', 'qwen2.5:0.5b'),
    'BALANCED': ('qwen3:4b-instruct', 'qwen2.5:7b', 'qwen2.5:1.5b'),
    'DEEP': ('qwen3:4b-thinking', 'qwen3:4b-instruct', 'qwen2.5:7b', 'qwen2.5:1.5b'),
}
LIMITS = {'FAST': (2048, 256, 30), 'BALANCED': (4096, 768, 90), 'DEEP': (4096, 2048, 180)}
PROBES = (
    ('negation', 'Classifique a intenção: "Não abra o Paint". Retorne JSON com a chave acao e valor abrir ou nenhuma.', {'acao': 'nenhuma'}),
    ('clarification', 'Pedido: "Abra o Paint ou o Bloco de Notas". Não escolha pelo usuário. Retorne JSON com chave acao e valor esclarecer ou executar.', {'acao': 'esclarecer'}),
    ('mission', 'Missão: criar uma nota com fontes de uma pesquisa. Ordene as etapas pesquisar, verificar, salvar. Retorne JSON com chave etapas e lista de três palavras.', {'etapas': ['pesquisar', 'verificar', 'salvar']}),
)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, 'Redirect refused', headers, fp)


def local_json(path, payload=None, timeout=5):
    if path not in ('/api/version', '/api/tags', '/api/ps', '/api/generate'):
        raise ValueError('Unsupported endpoint')
    if (path == '/api/generate') != (payload is not None):
        raise ValueError('Invalid method')
    req = Request(ENDPOINT + path, data=None if payload is None else json.dumps(payload).encode(),
                  headers={'Content-Type': 'application/json'})
    with build_opener(ProxyHandler({}), NoRedirect()).open(req, timeout=timeout) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError('Response too large')
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('Invalid API object')
    return value


def catalog(api=local_json):
    version = api('/api/version').get('version')
    rows = api('/api/tags').get('models')
    if not isinstance(version, str) or not version.strip() or not isinstance(rows, list):
        raise ValueError('Invalid Ollama catalog')
    if any(not isinstance(r, dict) or not isinstance(r.get('name'), str) or not r['name'] for r in rows):
        raise ValueError('Invalid model name')
    return version, {r['name'] for r in rows}


def select_model(mode, installed, override=None):
    if mode not in PREFERENCES:
        raise ValueError('Expected FAST, BALANCED or DEEP')
    candidates = (override,) if override is not None else PREFERENCES[mode]
    selected = next((name for name in candidates if name in installed), None)
    ctx, tokens, timeout = LIMITS[mode]
    return {'mode': mode, 'model': selected, 'status': 'INSTALLED' if selected else 'UNAVAILABLE',
            'preferred': candidates[0], 'fallback': selected is not None and selected != candidates[0],
            'num_ctx': ctx, 'num_predict': tokens, 'timeout': timeout}


def benchmark(mode, api=local_json):
    # Refresh the catalog before every generation. Never call pull or run CLI.
    rows = []
    for probe_id, prompt, expected in PROBES:
        _, installed = catalog(api)
        policy = select_model(mode, installed)
        if not policy['model']:
            rows.append({**policy, 'probe': probe_id, 'status': 'BLOCKED'})
            break
        start = time.perf_counter()
        try:
            result = api('/api/generate', {'model': policy['model'], 'prompt': prompt, 'stream': False,
                         'format': 'json', 'keep_alive': '30s', 'options': {'num_ctx': policy['num_ctx'],
                         'num_predict': policy['num_predict'], 'temperature': 0}}, timeout=policy['timeout'])
            text = result.get('response')
            complete = result.get('done') is True and result.get('done_reason') not in ('length', 'max_tokens')
            try:
                correct = isinstance(text, str) and json.loads(text) == expected
            except ValueError:
                correct = False
            count, duration = result.get('eval_count'), result.get('eval_duration')
            rate = (round(count * 1e9 / duration, 2) if type(count) is int and count >= 0 and
                    type(duration) is int and duration > 0 else None)
            rows.append({'probe': probe_id, 'model': policy['model'], 'status': 'PASS_REAL' if complete and correct else 'FAIL',
                         'done_reason': result.get('done_reason'), 'output_tokens': count, 'tokens_per_second': rate,
                         'load_duration_ns': result.get('load_duration'), 'elapsed_ms': round((time.perf_counter()-start)*1000)})
        except (OSError, ValueError, HTTPError) as exc:
            rows.append({'probe': probe_id, 'model': policy['model'], 'status': 'FAIL', 'error_type': type(exc).__name__})
            break
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', choices=tuple(PREFERENCES), help='Explicitly load and test models for this mode')
    args = parser.parse_args()
    try:
        version, installed = catalog()
        report = {'version': version, 'models': sorted(installed),
                  'policies': [select_model(m, installed) for m in PREFERENCES]}
        if args.run:
            report['benchmark'] = benchmark(args.run)
        print(json.dumps(report, ensure_ascii=True, indent=2))
        return 0 if not args.run or all(r['status'] == 'PASS_REAL' for r in report['benchmark']) else 1
    except (OSError, ValueError, HTTPError) as exc:
        print(json.dumps({'status': 'BLOCKED', 'error_type': type(exc).__name__}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
