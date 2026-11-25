"""Static code maps, including integration on the versioned source tree."""

import hashlib
from pathlib import Path

import pytest

from code_mapper import format_code_summary, summarize_modules


def test_summaries_for_real_modules_preserve_source_and_line_provenance():
    root = Path(__file__).resolve().parent
    names = ['actuator_bridge.py', 'execution_authority.py']
    before = {name: (root / name).read_bytes() for name in names}
    report = summarize_modules(root, names, symbol_limit=20)
    assert report['analysis'] == 'static_references_only'
    assert [row['path'] for row in report['modules']] == names
    actuator, authority = report['modules']
    for module in (actuator, authority):
        assert module['status'] == 'OK'
        assert module['sha256'] == hashlib.sha256(before[module['path']]).hexdigest()
        assert (root / module['path']).read_bytes() == before[module['path']]
    dependency = next(item for item in actuator['dependencies'] if item['name'] == 'execution_authority')
    assert 'from execution_authority import' in before[names[0]].splitlines()[dependency['evidence']['line'] - 1].decode()
    dispatch = next(item for item in actuator['symbols'] if item['name'] == 'ActuatorBridge.dispatch')
    assert dispatch['kind'] == 'async_function'
    assert dispatch['parameters'][0] == 'self'
    assert 'async def dispatch(' in before[names[0]].splitlines()[dispatch['evidence']['line'] - 1].decode()
    assert authority['responsibility']['source'] == 'docstring'
    rendered = format_code_summary(report)
    assert 'ActuatorBridge.dispatch(' in rendered
    assert 'Dependências importadas' in rendered
    assert 'Comportamento em execução' in rendered


def test_docstrings_and_static_inference_keep_separate_evidence(tmp_path):
    source = tmp_path / 'sample.py'
    source.write_text(
        '"""Descreve a responsabilidade do módulo."""\n'
        'raise AssertionError("Este módulo jamais deve ser executado pelo mapeador")\n'
        'def main(a, /, *, b) -> int:\n'
        '    def inner():\n'
        '        callback()\n'
        '    return int(a) + int(b)\n',
        encoding='utf-8',
    )
    module = summarize_modules(tmp_path, ['sample.py'])['modules'][0]
    assert module['responsibility']['source'] == 'docstring'
    main, inner = module['symbols']
    assert main['parameters'] == ['a', '/', '*', 'b']
    assert main['return_annotation'] == 'int'
    assert main['responsibility']['source'] == 'static_inference'
    assert [item['name'] for item in main['calls']] == ['int']
    assert [item['name'] for item in inner['calls']] == ['callback']


def test_invalid_missing_and_oversize_modules_report_separate_states(tmp_path):
    (tmp_path / 'invalid.py').write_text('def oops(:\n', encoding='utf-8')
    (tmp_path / 'large.py').write_bytes(b'#' * (512 * 1024 + 1))
    report = summarize_modules(tmp_path, ['invalid.py', 'missing.py', 'large.py'])
    assert [row['status'] for row in report['modules']] == ['INVALID_SOURCE', 'UNAVAILABLE', 'SOURCE_TOO_LARGE']


def test_summary_bounds_and_scope(tmp_path):
    path = tmp_path / 'code.py'
    path.write_text('def first(): ...\ndef second(): ...\n', encoding='utf-8')
    module = summarize_modules(tmp_path, ['code.py', 'code.py'], symbol_limit=1)['modules']
    assert len(module) == 1
    assert module[0]['symbol_count'] == 2
    assert [symbol['name'] for symbol in module[0]['symbols']] == ['first']
    for unsafe in [str(path), '../code.py', 'nested/code.py', 'nested\\code.py', 'code.txt']:
        with pytest.raises(ValueError):
            summarize_modules(tmp_path, [unsafe])
