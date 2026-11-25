import ast
import hashlib
import json
import logging
import urllib.request
from pathlib import Path
import time

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("CODE_MAPPER")

BRAIN_DIR = Path(r"A:\BRAINNET\BRAIN")
OUTPUT_FILE = Path(r"A:\BRAINNET\ESCRITA\GUIA_DO_CODIGO.md")

_DECLARATIONS = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
_MAX_SOURCE_BYTES = 512 * 1024


def _imports(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield {'module': alias.name, 'line': node.lineno}
        elif isinstance(node, ast.ImportFrom):
            names = [node.module] if node.module else [alias.name for alias in node.names]
            for name in names:
                yield {'module': name, 'line': node.lineno, 'relative': node.level}


def _declarations(body, parents=()):
    for node in body:
        if isinstance(node, _DECLARATIONS):
            name = (*parents, node.name)
            yield name, node
            yield from _declarations(node.body, name)


def _symbol_kind(node):
    if isinstance(node, ast.ClassDef):
        return 'class'
    return 'async_function' if isinstance(node, ast.AsyncFunctionDef) else 'function'


def index_symbols(file_path):
    """Read-only AST inventory; metadata only, no model calls or code execution."""
    file_path = Path(file_path)
    source = file_path.read_text(encoding='utf-8')
    tree = ast.parse(source, filename=str(file_path))
    imports, symbols = list(_imports(tree)), []
    for parts, node in _declarations(tree.body):
        calls = []
        exceptions = []
        for child in (() if isinstance(node, ast.ClassDef) else ast.walk(node)):
            if isinstance(child, ast.Call):
                try:
                    called = ast.unparse(child.func)
                except Exception:
                    called = '<unresolved>'
                calls.append({'name': called, 'line': child.lineno})
            elif isinstance(child, ast.Raise):
                exceptions.append({'expression': ast.unparse(child.exc) if child.exc else 're-raise', 'line': child.lineno})
        args = [] if isinstance(node, ast.ClassDef) else [a.arg for a in node.args.posonlyargs + node.args.args + node.args.kwonlyargs]
        symbols.append({'name': '.'.join(parts), 'kind': _symbol_kind(node), 'line': node.lineno, 'end_line': node.end_lineno,
                        'arguments': args, 'return_annotation': ast.unparse(node.returns) if not isinstance(node, ast.ClassDef) and node.returns else None,
                        'calls': calls, 'raises': exceptions})
    return {'path':str(file_path),'line_count':len(source.splitlines()),'imports':imports,'symbols':symbols,
            'analysis':'static_references_only','warnings':['calls are not proof of runtime execution']}


def _reference(path, node):
    return {'path': path, 'line': node.lineno, 'end_line': node.end_lineno}


def _responsibility(node, path, observation, evidence):
    doc = ast.get_docstring(node)
    if doc and doc.strip():
        first_line = next(line.strip() for line in doc.splitlines() if line.strip())
        return {'source': 'docstring', 'text': first_line[:160], 'evidence': _reference(path, node.body[0])}
    return {'source': 'static_inference', 'text': observation, 'evidence': evidence}


def _own_statements(node):
    for statement in node.body:
        # Nested declarations have their own scope and must retain their own evidence.
        pending = [statement]
        while pending:
            child = pending.pop()
            if isinstance(child, _DECLARATIONS + (ast.Lambda,)):
                continue
            yield child
            pending.extend(reversed(list(ast.iter_child_nodes(child))))


def _dotted_name(expression):
    parts = []
    while isinstance(expression, ast.Attribute):
        parts.append(expression.attr)
        expression = expression.value
    if isinstance(expression, ast.Name):
        return '.'.join([expression.id, *reversed(parts)])[:96]
    return '<dinâmico>'


def _brief_symbol(parts, node, path):
    evidence = _reference(path, node)
    result = {'name': '.'.join(parts)[:160], 'kind': _symbol_kind(node), 'evidence': evidence}
    if isinstance(node, ast.ClassDef):
        methods = [item for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))]
        public = [method.name[:96] for method in methods if not method.name.startswith('_')]
        result['public_methods'] = public[:8]
        observation = f'A classe declara {len(methods)} método(s), incluindo {len(public)} público(s).'
    else:
        args = node.args
        argument_names = [arg.arg[:96] for arg in args.posonlyargs + args.args]
        if args.posonlyargs:
            argument_names.insert(len(args.posonlyargs), '/')
        if args.vararg:
            argument_names.append('*' + args.vararg.arg[:96])
        elif args.kwonlyargs:
            argument_names.append('*')
        argument_names.extend(arg.arg[:96] for arg in args.kwonlyargs)
        if args.kwarg:
            argument_names.append('**' + args.kwarg.arg[:96])
        result['parameters'] = argument_names[:12]
        try:
            result['return_annotation'] = ast.unparse(node.returns)[:120] if node.returns else None
        except RecursionError:
            result['return_annotation'] = '<anotação complexa>'
        calls, seen, returns = [], set(), 0
        for child in _own_statements(node):
            if isinstance(child, ast.Return):
                returns += 1
            if isinstance(child, ast.Call) and len(calls) < 4:
                target = _dotted_name(child.func)
                if target not in seen:
                    seen.add(target)
                    calls.append({'name': target, 'evidence': _reference(path, child)})
        result['calls'] = calls
        observation = 'Contém chamadas a ' + ', '.join(call['name'] for call in calls) + '.' if calls else (
            f'Corpo declara {returns} retorno(s) explícito(s).')
    result['responsibility'] = _responsibility(node, path, observation, evidence)
    return result


def summarize_modules(root, modules, *, symbol_limit=8):
    """Read and summarize explicitly selected direct Python modules under a trusted root."""
    if not isinstance(modules, (list, tuple)) or not 1 <= len(modules) <= 6:
        raise ValueError('Informe de um a seis módulos Python.')
    if type(symbol_limit) is not int or not 1 <= symbol_limit <= 20:
        raise ValueError('Limite de símbolos entre 1 e 20.')
    root = Path(root).resolve()
    targets = []
    for name in modules:
        if not isinstance(name, str) or len(name) > 128 or not name.endswith('.py') or not name[:-3].isidentifier():
            raise ValueError('Informe somente nomes de módulos locais com extensão .py.')
        path = root / name
        if path.is_reserved() or path.resolve() != path:
            raise ValueError('Módulo fora do escopo de leitura.')
        if path not in targets:
            targets.append(path)

    entries = []
    for path in targets:
        row = {'path': path.name}
        entries.append(row)
        try:
            if not path.is_file():
                row['status'] = 'UNAVAILABLE'
                continue
            with path.open('rb') as file:
                source = file.read(_MAX_SOURCE_BYTES + 1)
            if len(source) > _MAX_SOURCE_BYTES:
                row['status'] = 'SOURCE_TOO_LARGE'
                continue
            tree = ast.parse(source, filename=path.name)
        except OSError:
            row['status'] = 'UNAVAILABLE'
            continue
        except (SyntaxError, ValueError, RecursionError):
            row['status'] = 'INVALID_SOURCE'
            continue
        declarations = list(_declarations(tree.body))
        # Public module symbols and class methods come before helpers and closures.
        declarations.sort(key=lambda item: (any(part.startswith('_') for part in item[0]), len(item[0])))
        imports = sorted(_imports(tree), key=lambda item: item['line'])
        grouped = {}
        for entry in imports:
            name = '.' * entry.get('relative', 0) + entry['module']
            grouped.setdefault(name, {'name': name[:120], 'evidence': {'path': path.name, 'line': entry['line']}})
        row.update(status='OK', sha256=hashlib.sha256(source).hexdigest(),
                   responsibility=_responsibility(tree, path.name, f'Declara {len(declarations)} símbolo(s) no código legível pela AST.',
                                                  {'path': path.name, 'line': 1}),
                   dependencies=list(grouped.values())[:8], dependency_count=len(grouped),
                   symbols=[_brief_symbol(parts, node, path.name) for parts, node in declarations[:symbol_limit]],
                   symbol_count=len(declarations))
    return {'analysis': 'static_references_only', 'modules': entries,
            'limitations': ['A leitura estática inclui declarações e chamadas visíveis no código.',
                            'Comportamento em execução e dependências carregadas dinamicamente exigem verificação.']}


def format_code_summary(report):
    """Render compact, referenced Portuguese text for the chat route."""
    lines = ['Mapa estático do código']

    def responsibility(item):
        evidence = item['evidence']
        basis = 'documentação' if item['source'] == 'docstring' else 'inferência estática'
        return f"{item['text']} [{basis} · {evidence['path']}:{evidence['line']}]"

    for module in report['modules']:
        lines.extend(('', module['path']))
        if module['status'] != 'OK':
            lines.append(f"- Leitura indisponível ({module['status']}).")
            continue
        lines.append('- ' + responsibility(module['responsibility']))
        if module['dependencies']:
            deps = ', '.join(f"{item['name']} (linha {item['evidence']['line']})" for item in module['dependencies'])
            lines.append(f"- Dependências importadas ({len(module['dependencies'])}/{module['dependency_count']}) · {deps}")
        for symbol in module['symbols']:
            signature = symbol['name']
            if 'parameters' in symbol:
                signature += '(' + ', '.join(symbol['parameters']) + ')'
                if symbol['return_annotation']:
                    signature += ' → ' + symbol['return_annotation']
            lines.append(f"- {signature} · linha {symbol['evidence']['line']} · {responsibility(symbol['responsibility'])}")
            if symbol['responsibility']['source'] == 'docstring' and symbol.get('calls'):
                calls = ', '.join(f"{item['name']} (linha {item['evidence']['line']})" for item in symbol['calls'])
                lines.append(f'  Chamadas visíveis · {calls}')
        lines.append(f"- Símbolos mostrados {len(module['symbols'])}/{module['symbol_count']}.")
    lines.extend(('', *report['limitations']))
    return '\n'.join(lines)

def call_llm(prompt):
    payload = {
        "model": "qwen2.5-coder:7b", "prompt": prompt, "stream": False,
        "keep_alive": "5m", "options": {"temperature": 0.2, "num_predict": 250}
    }
    try:
        req = urllib.request.Request("http://localhost:11434/api/generate", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8")).get("response", "").strip()
    except Exception as e:
        return f"[Erro na IA: {e}]"

def extract_blocks(file_path):
    """Usa AST para separar o código em blocos de Classes e Funções."""
    source = file_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    blocks = []
    lines = source.splitlines()

    # Adiciona o cabeçalho do arquivo (imports e docstrings globais)
    if tree.body and not isinstance(tree.body[0], (ast.ClassDef, ast.FunctionDef)):
        pass # Opcional: pegar o topo do arquivo

    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            # Extrai o código exato daquele nó
            start = node.lineno - 1
            end = node.end_lineno
            literal_code = "\n".join(lines[start:end])

            # Pula funções muito pequenas (ex: getters vazios)
            if len(literal_code.splitlines()) > 5:
                blocks.append({
                    "name": node.name,
                    "type": "Classe" if isinstance(node, ast.ClassDef) else "Função",
                    "code": literal_code
                })
    return blocks

def generate_guide():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    py_files = list(BRAIN_DIR.glob("*.py"))

    with OUTPUT_FILE.open("w", encoding="utf-8") as md:
        md.write("# 🧠 GUIA DO CÓDIGO BRAINNET\n\n")
        md.write("Este guia foi gerado automaticamente pela própria IA. Ele contém a intenção de cada bloco e o código literal.\n\n")

        for file_path in py_files:
            if file_path.name.startswith("test_") or file_path.name in ("code_mapper.py", "conftest.py"):
                continue

            blocks = extract_blocks(file_path)
            if not blocks:
                continue

            logger.info(f"Mapeando {file_path.name} ({len(blocks)} blocos)...")
            md.write(f"\n---\n## 📄 Arquivo: `{file_path.name}`\n\n")

            for block in blocks:
                logger.info(f"  -> Analisando {block['type']} {block['name']}...")
                prompt = (
                    f"Analise o seguinte trecho de código do sistema BRAINNET.\n"
                    f"Explique em uma frase curta e direta qual é a INTENÇÃO e o PROPÓSITO deste bloco.\n"
                    f"Não repita o código. Apenas diga o que ele faz.\n\n"
                    f"BLOCO:\n{block['code']}"
                )
                intencao = call_llm(prompt)

                md.write(f"### {block['type']}: `{block['name']}`\n")
                md.write(f"**Intenção:** {intencao}\n\n")
                md.write(f"<details>\n<summary>Ver código literal</summary>\n\n")
                md.write(f"```python\n{block['code']}\n```\n\n")
                md.write(f"</details>\n\n")

    logger.info(f"\n✅ Guia completo gerado em: {OUTPUT_FILE}")

if __name__ == "__main__":
    logger.info("Iniciando mapeamento semântico do código...")
    generate_guide()
