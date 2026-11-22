import ast
import json
import logging
import urllib.request
from pathlib import Path
import time

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("CODE_MAPPER")

BRAIN_DIR = Path(r"A:\BRAINNET\BRAIN")
OUTPUT_FILE = Path(r"A:\BRAINNET\ESCRITA\GUIA_DO_CODIGO.md")

def index_symbols(file_path):
    """Read-only AST inventory; metadata only, no model calls or code execution."""
    file_path = Path(file_path)
    source = file_path.read_text(encoding='utf-8')
    tree = ast.parse(source, filename=str(file_path))
    imports, symbols = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend({'module': alias.name, 'line': node.lineno} for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append({'module': node.module or '', 'line': node.lineno, 'relative': node.level})
    def visit(body, parents=()):
        for node in body:
            if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            name='.'.join((*parents,node.name))
            kind='class' if isinstance(node,ast.ClassDef) else ('async_function' if isinstance(node,ast.AsyncFunctionDef) else 'function')
            calls=[]; exceptions=[]
            for child in (() if isinstance(node, ast.ClassDef) else ast.walk(node)):
                if isinstance(child,ast.Call):
                    try: called=ast.unparse(child.func)
                    except Exception: called='<unresolved>'
                    calls.append({'name':called,'line':child.lineno})
                elif isinstance(child,ast.Raise):
                    exceptions.append({'expression':ast.unparse(child.exc) if child.exc else 're-raise','line':child.lineno})
            args = [] if isinstance(node,ast.ClassDef) else [a.arg for a in node.args.posonlyargs+node.args.args+node.args.kwonlyargs]
            symbols.append({'name':name,'kind':kind,'line':node.lineno,'end_line':node.end_lineno,
                'arguments':args,'return_annotation':ast.unparse(node.returns) if not isinstance(node,ast.ClassDef) and node.returns else None,
                'calls':calls,'raises':exceptions})
            visit(node.body,(*parents,node.name))
    visit(tree.body)
    return {'path':str(file_path),'line_count':len(source.splitlines()),'imports':imports,'symbols':symbols,
            'analysis':'static_references_only','warnings':['calls are not proof of runtime execution']}

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
