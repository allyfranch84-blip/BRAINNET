import json
import logging
import os
import re
import subprocess
import tempfile
import time
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Dict, Any, List
from assistant_prompts import MODELO_DEEP

logger = logging.getLogger("BRAINNET_Engineer")

def assess_change(evidence):
    """Review-only gate; never applies a patch or executes untrusted code."""
    if not isinstance(evidence,dict): raise ValueError('evidence must be a mapping')
    if evidence.get('rejected') is True:return 'REJECTED'
    stages=(('static_valid','STATIC_VALID'),('safe_tests_passed','TESTED_SAFE'),
            ('integration_validated','INTEGRATION_VALIDATED'),('stability_validated','STABILITY_VALIDATED'))
    state='PROPOSED'
    for key,label in stages:
        if evidence.get(key) is not True:return state
        state=label
    if evidence.get('human_approved') is not True:return state
    return 'APPROVED'

def classify_error(error):
    """Classifica sem executar codigo nem propor correcao automatica."""
    if isinstance(error, BaseException):
        if isinstance(error, IndentationError): return 'IndentationError'
        if isinstance(error, SyntaxError): return 'SyntaxError'
        if isinstance(error, ModuleNotFoundError): return 'ModuleNotFoundError'
        if isinstance(error, ImportError): return 'ImportError'
        if isinstance(error, TypeError): return 'TypeError'
        if isinstance(error, NameError): return 'NameError'
        return 'UNKNOWN'
    if not isinstance(error, str): return 'UNKNOWN'
    matches = re.findall(r'(?m)^\s*(IndentationError|SyntaxError|ModuleNotFoundError|ImportError|TypeError|NameError)\s*:', error)
    return matches[-1] if matches else 'UNKNOWN'


@dataclass(frozen=True)
class ProjectBrief:
    goal: str
    platform: str | None = None
    dimension: str | None = None

    def clarification_questions(self):
        questions = []
        if not self.platform:
            questions.append('Onde você quer jogar, no navegador ou em outro ambiente?')
        if not self.dimension:
            questions.append('Você prefere corrida 2D ou 3D?')
        return questions


@dataclass(frozen=True)
class ProjectVerification:
    status: str
    checks: tuple[str, ...] = ()
    detail: str = ''


def _validate_artifacts(files):
    """Validate a complete draft before creating files, including Windows aliases."""
    if not isinstance(files, Mapping) or not files or len(files) > 32:
        raise ValueError('invalid number of project files')
    paths = set()
    artifacts = []
    total_size = 0
    for name, content in files.items():
        if not isinstance(name, str) or not isinstance(content, str):
            raise ValueError('project files require a relative name and UTF-8 text')
        parts = name.replace('\\', '/').split('/')
        if len(name) > 160 or any(
            not part or part in ('.', '..') or part.endswith((' ', '.'))
            or PureWindowsPath(part).is_reserved()
            or re.search(r'[<>:"|?*\x00-\x1f]', part)
            for part in parts
        ):
            raise ValueError('invalid relative artifact path')
        key = tuple(part.casefold() for part in parts)
        if any(key[:len(existing)] == existing or existing[:len(key)] == key for existing in paths):
            raise ValueError('conflicting artifact paths')
        encoded = content.encode('utf-8')
        total_size += len(encoded)
        if total_size > 2_000_000:
            raise ValueError('project files exceed the draft size limit')
        paths.add(key)
        artifacts.append((parts, encoded))
    return artifacts


def _write_artifacts(root, artifacts):
    for parts, content in artifacts:
        path = root.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.parent.resolve().is_relative_to(root):
            raise ValueError('artifact outside project path')
        with path.open('xb') as file:
            file.write(content)


def run_project(brief, *, workspace, builder, verifier, repair=None, max_attempts=3,
                timeout_seconds=60, cancelled=None):
    """Build, verify and optionally repair immutable attempts in fresh workspaces.

    The caller chooses the tools and their execution isolation. A verifier may
    execute model-generated code only via a separately configured sandbox.
    """
    result = {'status': 'CLARIFICATION_REQUIRED', 'questions': brief.clarification_questions(),
              'project_path': None, 'artifacts': [], 'checks': [], 'attempts': [], 'detail': ''}
    if result['questions']:
        return result
    if type(max_attempts) is not int or not 1 <= max_attempts <= 8:
        raise ValueError('max_attempts must be between 1 and 8')
    if type(timeout_seconds) not in (int, float) or not 0 < timeout_seconds <= 300:
        raise ValueError('timeout_seconds must be between 0 and 300')
    if not callable(builder) or not callable(verifier):
        raise TypeError('builder and verifier must be callable')
    deadline = time.monotonic() + timeout_seconds

    def stop_status():
        if cancelled is not None and cancelled():
            return 'CANCELLED'
        if time.monotonic() >= deadline:
            return 'BUDGET_EXHAUSTED'
        return None

    files = None
    previous = None
    for attempt in range(1, max_attempts + 1):
        stopped = stop_status()
        if stopped:
            return {**result, 'status': stopped}
        try:
            candidate = builder(brief) if attempt == 1 else repair(brief, dict(files), previous)
        except Exception as exc:
            return {**result, 'status': 'DRAFT_FAILED', 'detail': type(exc).__name__}
        try:
            if not isinstance(candidate, Mapping):
                raise TypeError('draft must be a mapping')
            candidate = dict(candidate)
            if candidate == files:
                return {**result, 'status': 'NO_PROGRESS', 'detail': 'A tentativa produziu os mesmos arquivos.'}
            artifacts = _validate_artifacts(candidate)
            stopped = stop_status()
            if stopped:
                return {**result, 'status': stopped}
            work_root = Path(workspace).resolve()
            work_root.mkdir(parents=True, exist_ok=True)
            root = Path(tempfile.mkdtemp(prefix='brainnet-project-', dir=work_root))
            _write_artifacts(root, artifacts)
            result.update(project_path=str(root), artifacts=['/'.join(parts) for parts, _ in artifacts])
        except (OSError, TypeError, ValueError) as exc:
            return {**result, 'status': 'DRAFT_FAILED', 'detail': type(exc).__name__}
        files = candidate
        stopped = stop_status()
        if stopped:
            return {**result, 'status': stopped}
        try:
            current = verifier(root)
        except subprocess.TimeoutExpired:
            current = ProjectVerification('INCONCLUSIVE', detail='O verificador excedeu o prazo.')
        except Exception as exc:
            current = ProjectVerification('VERIFIER_FAILED', detail=type(exc).__name__)
        if not isinstance(current, ProjectVerification) or (
            current.status not in ('GOAL_VERIFIED', 'CHECK_FAILED', 'INCONCLUSIVE', 'VERIFIER_UNAVAILABLE',
                                   'VERIFIER_FAILED', 'CANCELLED')
            or not isinstance(current.checks, tuple)
            or any(not isinstance(check, str) or not check.strip() for check in current.checks)
            or (current.status == 'GOAL_VERIFIED' and not current.checks)
        ):
            current = ProjectVerification('INCONCLUSIVE', detail='Verificação sem evidência.')
        result['attempts'].append({'attempt': attempt, 'status': current.status,
                                   'checks': list(current.checks), 'detail': current.detail})
        result.update(status=current.status, checks=list(current.checks), detail=current.detail)
        stopped = stop_status()
        if stopped:
            return {**result, 'status': stopped}
        if current.status != 'CHECK_FAILED' or not callable(repair):
            return result
        previous = current
    return result


_RACE_HTML = """<!doctype html>
<html lang="pt-BR">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Circuito Noturno</title>
<style>
body { margin:0; background:#151d2b; color:#eef4ff; font:1rem system-ui; text-align:center }
canvas { display:block; width:min(100%,480px); height:auto; margin:1rem auto; background:#202e40 }
button { padding:.6rem 1rem } p { padding:0 1rem }
</style>
<h1>Circuito Noturno</h1>
<p>Setas para dirigir e acelerar. Complete o percurso.</p>
<canvas id="track" width="480" height="460" aria-label="Pista de corrida"></canvas>
<p><output id="race-status" aria-live="polite">Pronto</output></p>
<button id="restart" type="button">Reiniciar</button>
<script src="game.js"></script>
"""

_RACE_JS = """'use strict';
const trackLength = 600;
const clamp = (n, low, high) => Math.max(low, Math.min(high, n));
const newRace = () => ({ x: 240, distance: 0, speed: 0, time: 0, finished: false });

function advanceRace(state, controls, dt) {
    if (state.finished) return state;
    dt = clamp(dt, 0, 0.05);
    const speed = clamp(state.speed + (controls.accelerate ? 95 : -60) * dt, 0, 155);
    const x = clamp(state.x + (Number(controls.right) - Number(controls.left)) * 130 * dt, 98, 382);
    const distance = Math.min(trackLength, state.distance + speed * dt);
    return { x, distance, speed, time: state.time + dt, finished: distance >= trackLength };
}

if (typeof module !== 'undefined') module.exports = { newRace, advanceRace };

if (typeof document !== 'undefined') {
    const canvas = document.getElementById('track');
    const context = canvas.getContext('2d');
    const status = document.getElementById('race-status');
    const pressed = new Set();
    let race = newRace();
    let previous = null;
    document.getElementById('restart').addEventListener('click', () => { race = newRace(); });
    window.addEventListener('keydown', (event) => {
        if (['ArrowLeft', 'ArrowRight', 'ArrowUp'].includes(event.key)) {
            event.preventDefault();
            pressed.add(event.key);
        }
    });
    window.addEventListener('keyup', (event) => pressed.delete(event.key));
    window.addEventListener('blur', () => pressed.clear());
    function frame(now) {
        const dt = previous === null ? 0 : (now - previous) / 1000;
        previous = now;
        race = advanceRace(race, { left: pressed.has('ArrowLeft'), right: pressed.has('ArrowRight'),
            accelerate: pressed.has('ArrowUp') }, dt);
        context.fillStyle = '#153b39';
        context.fillRect(0, 0, 480, 460);
        context.fillStyle = '#30394d';
        context.fillRect(78, 0, 324, 460);
        context.fillStyle = '#e8efff';
        for (let y = -65 + (race.distance * 3) % 65; y < 460; y += 65) context.fillRect(236, y, 8, 34);
        context.fillStyle = '#ffb25a';
        context.fillRect(race.x - 14, 362, 28, 48);
        const label = race.finished ? `Chegada em ${race.time.toFixed(1)} s` : `${Math.floor(race.distance)} de ${trackLength} m`;
        if (status.value !== label) status.value = label;
        requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
}
"""

_RACE_README = """# Circuito Noturno

Abra `index.html` no navegador. Use ↑ para acelerar e ← / → para dirigir.
Complete 600 m e escolha **Reiniciar** para começar outra corrida.

`game.js` contém a simulação da corrida, a leitura do teclado e o desenho da pista.
O projeto funciona offline e não carrega bibliotecas externas.
"""

_RACE_FILES = {'index.html': _RACE_HTML, 'game.js': _RACE_JS, 'README.md': _RACE_README}
_NODE_CHECKS = ('estado inicial', 'aceleração e direção', 'fim de corrida', 'reinício')
_NODE_RACE_TESTS = """
const assert = require('node:assert/strict');
let state = newRace();
assert.equal(state.distance, 0);
assert.equal(state.finished, false);
const controls = { accelerate: true, right: true, left: false };
state = advanceRace(state, controls, .05);
assert.ok(state.speed > 0 && state.distance > 0 && state.x > 240);
for (let step = 0; step < 200 && !state.finished; step++) state = advanceRace(state, controls, .05);
assert.equal(state.finished, true);
assert.equal(state.distance, trackLength);
assert.equal(advanceRace(state, controls, .05), state);
assert.deepEqual(newRace(), { x: 240, distance: 0, speed: 0, time: 0, finished: false });
console.log('RACE_CHECKS_PASSED');
"""


def _find_node():
    executable = 'node.exe' if os.name == 'nt' else 'node'
    for entry in os.environ.get('PATH', '').split(os.pathsep):
        path = Path(entry.strip('"'))
        if path.is_absolute() and (path / executable).is_file():
            return (path / executable).resolve()
    return None


def _verify_race(root):
    for name, text in _RACE_FILES.items():
        if (root / name).read_bytes() != text.encode('utf-8'):
            return ProjectVerification('CHECK_FAILED', detail=f'Artefato divergente: {name}.')
    node = _find_node()
    if node is None:
        return ProjectVerification('VERIFIER_UNAVAILABLE', detail='Node.js ausente no PATH.')
    # Execute only the source constant audited in this module. The generated
    # project directory and its files are never interpreted by the host process.
    environment = {key: os.environ[key] for key in ('SystemRoot', 'WINDIR') if key in os.environ}
    process = subprocess.run(
        [str(node), '-'], input=_RACE_JS + _NODE_RACE_TESTS, cwd=node.parent,
        env=environment, capture_output=True, text=True, encoding='utf-8',
        errors='replace', timeout=10, check=False,
    )
    if process.returncode != 0:
        failure = next((line.strip()[:200] for line in process.stderr.splitlines()
                        if line.startswith(('AssertionError', 'SyntaxError', 'TypeError', 'ReferenceError'))), '')
        return ProjectVerification('CHECK_FAILED',
                                   detail=f'O motor JavaScript terminou com código {process.returncode}. {failure}'.strip())
    if process.stdout.strip() != 'RACE_CHECKS_PASSED':
        return ProjectVerification('INCONCLUSIVE', detail='O Node.js não emitiu a confirmação esperada.')
    return ProjectVerification('GOAL_VERIFIED', _NODE_CHECKS,
                               'Artefatos conferidos e motor executado no Node.js. Interface visual pendente.')


def run_racing_prototype(brief, *, workspace, cancelled=None):
    """Generate and verify the supported local 2D racing prototype."""
    if not brief.clarification_questions() and (brief.platform != 'browser' or brief.dimension != '2d'):
        return {'status': 'UNSUPPORTED', 'questions': [], 'project_path': None,
                'artifacts': [], 'checks': [], 'attempts': [],
                'detail': 'O protótipo disponível é de corrida 2D para navegador.'}
    return run_project(brief, workspace=workspace, builder=lambda _: dict(_RACE_FILES),
                       verifier=_verify_race, cancelled=cancelled)


class EngineeringAgent:
    def __init__(self, kernel, bridge):
        self.kernel = kernel
        self.bridge = bridge
        self.projects_dir = Path(__file__).resolve().parent.parent / 'PROJETOS'

    def _call_llm(self, prompt: str, model: str = MODELO_DEEP, is_json: bool = True) -> str:
        payload = {
            "model": model, "prompt": prompt, "stream": False,
            "keep_alive": "5m",
            "options": {"temperature": 0.2, "num_ctx": 8192, "num_predict": 2048}
        }
        if is_json:
            payload["format"] = "json"

        try:
            req = urllib.request.Request("http://localhost:11434/api/generate", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read().decode("utf-8")).get("response", "").strip()
        except Exception as e:
            logger.error(f"[ENGINEER]: Falha no LLM: {e}")
            return ""

    def plan_project(self, goal: str) -> Dict[str, Any]:
        """Fase 1: Pesquisa e Planejamento da estrutura do projeto."""
        self.bridge._push_event("aios:message", {"role": "ai", "text": f"📐 Planejando a arquitetura do projeto: *{goal}*..."})

        prompt = (
            "Você é o Engenheiro de Software Chefe da BRAINNET.\n"
            f"OBJETIVO DO USUÁRIO: {goal}\n"
            "Crie um plano de arquivos para este projeto. Assuma que o ambiente é Windows 11 e Python 3.12.\n"
            "Se precisar de bibliotecas externas (ex: pygame, requests), liste-as.\n"
            "Retorne APENAS um JSON válido com o seguinte formato:\n"
            '{"project_name": "nome_da_pasta", "dependencies": ["lib1", "lib2"], '
            '"files": [{"path": "main.py", "content": "# codigo completo aqui"}, {"path": "modulo.py", "content": "..."}]}'
        )

        response = self._call_llm(prompt)
        try:
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            plan = json.loads(response)
            logger.info(f"[ENGINEER]: Plano gerado para '{plan.get('project_name')}' com {len(plan.get('files', []))} arquivos.")
            return plan
        except Exception as e:
            logger.error(f"[ENGINEER]: Falha ao fazer parse do plano: {e}. Resposta: {response[:200]}")
            return None

    def create_files(self, project_name: str, files: List[Dict[str, str]]) -> Path:
        """Create a fresh project using validated relative artifact paths."""
        if not isinstance(project_name, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', project_name):
            raise ValueError('invalid project name')
        _validate_artifacts({project_name: ''})
        if not isinstance(files, list) or not all(isinstance(item, dict) for item in files):
            raise ValueError('invalid project files')
        by_path = {item['path']: item['content'] for item in files}
        if len(by_path) != len(files):
            raise ValueError('duplicate project files')
        artifacts = _validate_artifacts(by_path)
        project_path = self.projects_dir.resolve() / project_name
        project_path.mkdir(parents=True, exist_ok=False)
        _write_artifacts(project_path, artifacts)
        return project_path

    def test_project(self, project_path: Path, entry_file: str = 'main.py', *, verifier=None) -> bool:
        """Legacy boolean entry point requiring an explicit verifier."""
        if not callable(verifier):
            logger.warning('Projeto pendente de um verificador isolado.')
            return False
        try:
            result = verifier(project_path, entry_file)
        except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
            return False
        return isinstance(result, ProjectVerification) and result.status == 'GOAL_VERIFIED' and bool(result.checks)

    def _apply_auto_fix(self, project_path: Path, erro: str):
        """Aplicação automática de código gerado exige fluxo isolado e revisão."""
        raise PermissionError("Correção automática desativada; revisão explícita necessária")
