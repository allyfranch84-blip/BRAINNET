import os
from pathlib import Path
from subprocess import Popen, TimeoutExpired, run
from unittest.mock import Mock

import pytest

from engineering_agent import (
    EngineeringAgent,
    ProjectBrief,
    ProjectVerification,
    _find_node,
    run_project,
    run_racing_prototype,
)


BRIEF = ProjectBrief('faça um jogo de corrida', 'browser', '2d')


def test_vague_request_asks_without_creating_a_project(tmp_path):
    workspace = tmp_path / 'projects'
    result = run_racing_prototype(ProjectBrief(BRIEF.goal), workspace=workspace)
    assert result['status'] == 'CLARIFICATION_REQUIRED'
    assert len(result['questions']) == 2
    assert not workspace.exists()


def test_unsupported_variant_does_not_build_a_different_project(tmp_path):
    workspace = tmp_path / 'projects'
    result = run_racing_prototype(ProjectBrief(BRIEF.goal, 'browser', '3d'), workspace=workspace)
    assert result['status'] == 'UNSUPPORTED'
    assert not workspace.exists()


def test_timeout_is_inconclusive_and_does_not_restart(tmp_path):
    verifier = Mock(side_effect=TimeoutExpired('test-only', 1))
    repair = Mock()
    result = run_project(BRIEF, workspace=tmp_path, builder=lambda _: {'a.txt': 'draft'},
                         verifier=verifier, repair=repair)
    assert result['status'] == 'INCONCLUSIVE'
    assert len(result['attempts']) == 1
    assert not result['checks']
    repair.assert_not_called()


def test_legacy_test_project_requires_evidence(tmp_path):
    agent = EngineeringAgent.__new__(EngineeringAgent)
    assert agent.test_project(tmp_path) is False
    timed_out = Mock(side_effect=TimeoutExpired('test-only', 1))
    assert agent.test_project(tmp_path, verifier=timed_out) is False
    assert agent.test_project(tmp_path, verifier=lambda *_: ProjectVerification('GOAL_VERIFIED')) is False


@pytest.mark.parametrize('name', ['../outside', '/outside', 'Q:/outside', 'Q:outside',
                                  'folders\\..\\outside', 'nul.txt', 'nested/a.txt:stream', 'foo.'])
def test_draft_rejects_dangerous_paths_before_writing(tmp_path, name):
    verifier = Mock()
    result = run_project(BRIEF, workspace=tmp_path, builder=lambda _: {name: 'draft'}, verifier=verifier)
    assert result['status'] == 'DRAFT_FAILED'
    assert not list(tmp_path.iterdir())
    verifier.assert_not_called()


def test_cancelled_work_does_not_build_or_verify(tmp_path):
    builder = Mock()
    verifier = Mock()
    result = run_project(BRIEF, workspace=tmp_path, builder=builder, verifier=verifier,
                         cancelled=lambda: True)
    assert result['status'] == 'CANCELLED'
    builder.assert_not_called()
    verifier.assert_not_called()


def test_identical_repair_is_stopped(tmp_path):
    draft = {'race.txt': 'same files'}
    verifier = Mock(return_value=ProjectVerification('CHECK_FAILED', detail='failed test'))
    result = run_project(BRIEF, workspace=tmp_path, builder=lambda _: draft, verifier=verifier,
                         repair=lambda *_: draft)
    assert result['status'] == 'NO_PROGRESS'
    assert verifier.call_count == 1


def test_callback_failure_is_diagnosed_without_false_success(tmp_path):
    verifier = Mock(side_effect=RuntimeError('provider failed'))
    result = run_project(BRIEF, workspace=tmp_path, builder=lambda _: {'a.txt': 'draft'},
                         verifier=verifier)
    assert result['status'] == 'VERIFIER_FAILED'
    assert result['detail'] == 'RuntimeError'
    assert not result['checks']


def test_racing_prototype_verifies_real_javascript(tmp_path):
    if _find_node() is None:
        pytest.skip('Node.js required for real runtime verification')
    result = run_racing_prototype(BRIEF, workspace=tmp_path)
    assert result['status'] == 'GOAL_VERIFIED', result
    assert len(result['checks']) == 4
    project = Path(result['project_path'])
    assert project.parent == tmp_path.resolve()
    assert {item.name for item in project.iterdir()} == {'index.html', 'game.js', 'README.md'}


def test_actual_node_assertion_failure_is_diagnosed_then_repaired(tmp_path):
    node = _find_node()
    if node is None:
        pytest.skip('Node.js required for real runtime verification')
    # Two immutable, test-authored fixtures. Never dispatch workspace bytes.
    broken = "require('node:assert/strict').equal(34, 42);"
    fixed = "require('node:assert/strict').equal(42, 42);"
    paths = []

    def verify(project):
        paths.append(project)
        fixture = (project / 'motion.js').read_text(encoding='utf-8')
        assert fixture in (broken, fixed)
        audited_source = fixed if fixture == fixed else broken
        child = run([str(node), '-'], input=audited_source, cwd=node.parent, text=True,
                    capture_output=True, timeout=10)
        if child.returncode == 0:
            return ProjectVerification('GOAL_VERIFIED', ('valor esperado',))
        assert 'AssertionError' in child.stderr
        return ProjectVerification('CHECK_FAILED', detail='AssertionError: expected 42')

    def repair(brief, files, failure):
        assert brief == BRIEF and files == {'motion.js': broken}
        assert failure.detail == 'AssertionError: expected 42'
        return {'motion.js': fixed}

    result = run_project(BRIEF, workspace=tmp_path, builder=lambda _: {'motion.js': broken},
                         verifier=verify, repair=repair)
    assert result['status'] == 'GOAL_VERIFIED'
    assert [attempt['status'] for attempt in result['attempts']] == ['CHECK_FAILED', 'GOAL_VERIFIED']
    assert paths[0] != paths[1]
    assert (paths[0] / 'motion.js').read_text(encoding='utf-8') == broken


_BROWSER_CLOCK = """
<script>
const pendingFrames = [];
window.requestAnimationFrame = callback => pendingFrames.push(callback);
</script>
"""

_BROWSER_CHECK = """
<script>
const landmark = document.documentElement.dataset;
const canvas = document.getElementById('track');
const output = document.getElementById('race-status');
const restart = document.getElementById('restart');
const accelerate = new KeyboardEvent('keydown', { key: 'ArrowUp', cancelable: true });
window.dispatchEvent(accelerate);
for (let step = 0; step < 500 && pendingFrames.length; step++) {
    pendingFrames.shift()(step * 16);
}
if (!accelerate.defaultPrevented) landmark.brainnetBrowser = 'keyboard-unbound';
else if (canvas.getContext('2d').getImageData(0, 0, 1, 1).data[3] !== 255) {
    landmark.brainnetBrowser = 'canvas-not-drawn';
} else if (!output.value.startsWith('Chegada em')) landmark.brainnetBrowser = 'race-not-finished';
else {
    window.dispatchEvent(new KeyboardEvent('keyup', { key: 'ArrowUp' }));
    restart.click();
    if (pendingFrames.length) pendingFrames.shift()(8000);
    landmark.brainnetBrowser = output.value === '0 de 600 m' ? 'ok' : 'restart-failed';
}
</script>
"""


@pytest.mark.skipif(os.environ.get('BRAINNET_TEST_HEADLESS_EDGE') != '1',
                    reason='optional test using an isolated headless Edge instance')
def test_racing_renders_and_restarts_in_headless_edge(tmp_path):
    if os.name != 'nt':
        pytest.skip('Edge Windows executable required')
    candidates = [
        Path(os.environ[key]) / 'Microsoft' / 'Edge' / 'Application' / 'msedge.exe'
        for key in ('ProgramFiles(x86)', 'ProgramFiles') if os.environ.get(key)
    ]
    edge = next((path for path in candidates if path.is_file()), None)
    if edge is None or _find_node() is None:
        pytest.skip('Edge and Node.js required for real browser verification')
    result = run_racing_prototype(BRIEF, workspace=tmp_path)
    assert result['status'] == 'GOAL_VERIFIED', result
    project = Path(result['project_path'])
    source = (project / 'index.html').read_text(encoding='utf-8')
    fixture = project / 'browser-probe.html'
    entry = '<script src="game.js"></script>'
    assert source.count(entry) == 1
    fixture.write_text(source.replace(entry, _BROWSER_CLOCK + entry + _BROWSER_CHECK), encoding='utf-8')

    stdout_path = tmp_path / 'edge-output.txt'
    with stdout_path.open('wb') as stdout, (tmp_path / 'edge-errors.txt').open('wb') as stderr:
        args = [
            str(edge), '--headless=new', '--no-first-run', '--no-default-browser-check',
            '--disable-background-networking', '--disable-component-update', '--disable-sync',
            '--disable-crash-reporter', '--disable-breakpad', '--disable-default-apps',
            '--host-resolver-rules=MAP * ~NOTFOUND',
            f'--user-data-dir={tmp_path / "edge-profile"}',
            '--dump-dom', fixture.as_uri(),
        ]
        with Popen(args, stdout=stdout, stderr=stderr, cwd=tmp_path) as child:
            try:
                assert child.wait(timeout=25) == 0
            except TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
                pytest.fail('isolated Edge probe timed out')
    rendered = stdout_path.read_text(encoding='utf-8', errors='replace')
    assert 'data-brainnet-browser="ok"' in rendered, rendered[:700]
