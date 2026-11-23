import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys
from types import SimpleNamespace
from unittest.mock import patch

import patch_control as pc


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dst = self.root / 'operacional'
        self.src = self.dst / 'BRAINNET'
        self.src.mkdir(parents=True)
        self.backup = self.root / 'backups'
        self.git('init', '-q')
        self.git('config', 'user.name', 'Teste Temporario')
        self.git('config', 'user.email', 'teste@example.invalid')
        self.old = 'antes'.encode()
        self.new = 'depois'.encode()
        self.path = 'BRAIN/código com espaço.py'
        self.write(self.src / self.path, self.old)
        self.write(self.dst / self.path, self.old)
        self.git('add', '.')
        self.git('commit', '-qm', 'base')
        self.base = self.git('rev-parse', 'HEAD').decode().strip()
        self.write(self.src / self.path, self.new)
        self.git('add', '.')
        self.git('commit', '-qm', 'patch')
        self.target = self.git('rev-parse', 'HEAD').decode().strip()
        self.manifest = self.root / 'manifest.json'
        self.update_manifest()

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.src), *args], check=True, capture_output=True).stdout

    @staticmethod
    def write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def update_manifest(self, entries=None):
        data = {'base_commit': self.base, 'target_commit': self.target,
                'files': entries or [{'path': self.path, 'before_sha256': pc.sha(self.old),
                                      'after_sha256': pc.sha(self.new)}]}
        self.manifest.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    def plan(self):
        return pc.plan(self.src, self.dst, self.manifest)

    @staticmethod
    def idle():
        return ''

    def test_preview_is_inert_and_unicode_path(self):
        first = self.plan(); second = self.plan()
        self.assertEqual(first['plan_sha256'], second['plan_sha256'])
        self.assertEqual((self.dst / self.path).read_bytes(), self.old)
        self.assertFalse(self.backup.exists())

    def test_apply_and_rollback_modified_file(self):
        p = self.plan(); j = pc.apply_plan(p, p['plan_sha256'], self.backup, process_check=self.idle)
        self.assertEqual((self.dst / self.path).read_bytes(), self.new)
        self.assertEqual(pc.rollback(self.backup, j['deployment_id'], process_check=self.idle)['status'], 'ROLLED_BACK')
        self.assertEqual((self.dst / self.path).read_bytes(), self.old)

    def test_add_new_file_and_rollback(self):
        name = 'BRAIN/novo arquivo.py'; content = b'new'
        self.write(self.src / name, content); self.git('add', '.'); self.git('commit', '-qm', 'new')
        self.target = self.git('rev-parse', 'HEAD').decode().strip()
        self.update_manifest([{'path': self.path, 'before_sha256': pc.sha(self.old), 'after_sha256': pc.sha(self.new)},
                              {'path': name, 'before_sha256': None, 'after_sha256': pc.sha(content)}])
        p = self.plan(); j = pc.apply_plan(p, p['plan_sha256'], self.backup, process_check=self.idle)
        self.assertEqual((self.dst / name).read_bytes(), content)
        pc.rollback(self.backup, j['deployment_id'], process_check=self.idle)
        self.assertFalse((self.dst / name).exists())
        self.assertEqual((self.dst / self.path).read_bytes(), self.old)

    def test_conflict_and_changed_after_preview_fail_closed(self):
        self.write(self.dst / self.path, b'diferente')
        p = self.plan(); self.assertTrue(p['files'][0]['conflict'])
        with self.assertRaises(pc.Refused): pc.apply_plan(p, p['plan_sha256'], self.backup, process_check=self.idle)
        self.write(self.dst / self.path, self.old); p = self.plan(); self.write(self.dst / self.path, b'alterado')
        with self.assertRaises(pc.Refused): pc.apply_plan(p, p['plan_sha256'], self.backup, process_check=self.idle)
        self.assertEqual((self.dst / self.path).read_bytes(), b'alterado')

    def test_rollback_refuses_later_edits(self):
        p = self.plan(); j = pc.apply_plan(p, p['plan_sha256'], self.backup, process_check=self.idle)
        self.write(self.dst / self.path, b'usuario')
        with self.assertRaises(pc.Refused): pc.rollback(self.backup, j['deployment_id'], process_check=self.idle)
        self.assertEqual((self.dst / self.path).read_bytes(), b'usuario')

    def test_active_process_and_wrong_approval_block(self):
        p = self.plan()
        with self.assertRaises(pc.Refused): pc.apply_plan(p, 'errado', self.backup, process_check=self.idle)
        with self.assertRaises(pc.Refused): pc.apply_plan(p, p['plan_sha256'], self.backup, process_check=lambda: '[{"Name":"node"}]')
        self.assertFalse(self.backup.exists())

    def test_operational_deployment_is_hard_disabled(self):
        with self.assertRaisesRegex(pc.Refused, 'DESATIVADO'):
            pc.require_temporary_destination(Path(r'A:\BRAINNET'))
        with patch.object(pc.tempfile, 'gettempdir', return_value='A:\\'):
            with self.assertRaisesRegex(pc.Refused, 'DESATIVADO'):
                pc.require_temporary_destination(Path(r'A:\BRAINNET'))
        p = self.plan()
        p['destination'] = r'A:\BRAINNET'
        with self.assertRaisesRegex(pc.Refused, 'DESATIVADO'):
            pc.apply_plan(p, p['plan_sha256'], self.backup, process_check=self.idle)
        self.assertFalse(self.backup.exists())

    @unittest.skipUnless(os.name == 'nt', 'coleta específica do Windows')
    def test_process_collector_fails_closed_and_ignores_itself(self):
        with patch.object(pc.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=b'[]')) as run:
            self.assertEqual(pc.active_processes(), '[]')
            query = run.call_args.args[0][-1]
            self.assertIn(str(os.getpid()), query)
            self.assertIn('IsNullOrWhiteSpace', query)
            self.assertIn('ollama app', query)
        with patch.object(pc.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout=b'')):
            with self.assertRaises(pc.Refused): pc.active_processes()

    def test_protected_paths_traversal_and_case_collisions(self):
        for s in ('../BRAIN/a.py', 'BRAIN/.env', 'BRAIN/brainnet_config.json', '.git/config',
                  'BRAIN/distill_data_generator_72b.py', 'BRAIN/a.db', 'models/a.py',
                  'BRAINNET/a.py', 'BRAIN/a.exe', 'BRAIN/node_modules/a.js', 'C:/x.py'):
            with self.subTest(path=s):
                with self.assertRaises(pc.Refused):
                    rel = pc.safe_rel(s)
                    pc.checked_path(self.dst, rel, excluded=self.src)
        entries = [{'path': self.path, 'before_sha256': pc.sha(self.old), 'after_sha256': pc.sha(self.new)},
                   {'path': self.path.upper(), 'before_sha256': pc.sha(self.old), 'after_sha256': pc.sha(self.new)}]
        self.update_manifest(entries)
        with self.assertRaises(pc.Refused): self.plan()

    def test_partial_failure_records_and_rollback(self):
        name = 'BRAIN/segundo.py'; content = b'new'; self.write(self.src / name, content)
        self.git('add', '.'); self.git('commit', '-qm', 'second'); self.target = self.git('rev-parse', 'HEAD').decode().strip()
        self.update_manifest([{'path': self.path, 'before_sha256': pc.sha(self.old), 'after_sha256': pc.sha(self.new)},
                              {'path': name, 'before_sha256': None, 'after_sha256': pc.sha(content)}])
        p = self.plan(); original = pc.atomic_write; calls = []
        def fail_second(path, data):
            calls.append(path)
            if len(calls) == 2: raise OSError('falha simulada')
            return original(path, data)
        with patch.object(pc, 'atomic_write', side_effect=fail_second):
            with self.assertRaises(pc.Refused): pc.apply_plan(p, p['plan_sha256'], self.backup, process_check=self.idle)
        folder = next(self.backup.iterdir()); journal = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(journal['status'], 'PARTIAL_FAILURE')
        pc.rollback(self.backup, journal['deployment_id'], process_check=self.idle)
        self.assertEqual((self.dst / self.path).read_bytes(), self.old)
        self.assertFalse((self.dst / name).exists())

    def test_junction_or_symlink_is_rejected(self):
        target = self.root / 'out'; target.mkdir()
        link = self.dst / 'BRAIN' / 'junction'
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            if os.name != 'nt': self.skipTest('symlink indisponível')
            p = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)], capture_output=True)
            if p.returncode: self.skipTest('junction indisponível')
        with self.assertRaises(pc.Refused): pc.checked_path(self.dst, pc.safe_rel('BRAIN/junction/a.py'), excluded=self.src)

    def test_simulated_windows_reparse_point_is_rejected(self):
        link = self.dst / 'BRAIN' / 'junction'
        link.mkdir()
        original = Path.lstat
        def fake_lstat(path, *args, **kwargs):
            if path == link:
                return SimpleNamespace(st_mode=0o040755, st_file_attributes=0x400)
            return original(path, *args, **kwargs)
        with patch.object(Path, 'lstat', fake_lstat):
            with self.assertRaises(pc.Refused):
                pc.checked_path(self.dst, pc.safe_rel('BRAIN/junction/a.py'), excluded=self.src)

    def test_rollback_checks_expected_roots_and_backup_integrity(self):
        p = self.plan(); j = pc.apply_plan(p, p['plan_sha256'], self.backup, process_check=self.idle)
        with self.assertRaises(pc.Refused):
            pc.rollback(self.backup, j['deployment_id'], expected_destination=self.root, process_check=self.idle)
        backup = self.backup / j['deployment_id'] / 'backup' / self.path
        backup.write_bytes(b'danificado')
        with self.assertRaises(pc.Refused):
            pc.rollback(self.backup, j['deployment_id'], process_check=self.idle)
        self.assertEqual((self.dst / self.path).read_bytes(), self.new)

    def test_source_modified_or_wrong_commit_is_rejected(self):
        self.write(self.src / self.path, b'local')
        with self.assertRaises(pc.Refused): self.plan()

    @unittest.skipUnless(os.name == 'nt', 'verificação de caixa específica do Windows')
    def test_existing_path_with_different_case_is_rejected(self):
        with self.assertRaises(pc.Refused):
            pc.checked_path(self.dst, pc.safe_rel('brain/código com espaço.py'), excluded=self.src)

    def test_powershell_preview(self):
        script = Path(__file__).with_name('Deploy-BrainnetPatch.ps1')
        result = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script),
                                 '-Preview', '-Source', str(self.src), '-Destination', str(self.dst),
                                 '-BackupRoot', str(self.backup), '-Manifest', str(self.manifest)],
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        self.assertFalse(self.backup.exists())

    @unittest.skipUnless(os.name == 'nt', 'resolução específica do Windows')
    def test_preview_without_git_or_python_on_path_uses_desktop_and_explicit_python(self):
        desktop = Path(os.environ['USERPROFILE']) / 'AppData/Local/GitHubDesktop'
        candidates = sorted(desktop.glob('app-*/resources/app/git/cmd/git.exe'), reverse=True)
        if not candidates: self.skipTest('GitHub Desktop indisponível')
        powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        env = os.environ.copy()
        env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
        env['LOCALAPPDATA'] = str(self.root / 'localappdata-vazio')
        script = Path(__file__).with_name('Deploy-BrainnetPatch.ps1')
        result = subprocess.run([str(powershell), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script),
                                 '-Preview', '-Source', str(self.src), '-Destination', str(self.dst),
                                 '-BackupRoot', str(self.backup), '-Manifest', str(self.manifest),
                                 '-PythonPath', sys.executable], capture_output=True, timeout=30, env=env)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        self.assertIn(b'plan_sha256', result.stdout)
        self.assertFalse(self.backup.exists())
        result = subprocess.run([str(powershell), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script),
                                 '-Preview', '-Source', str(self.src), '-Destination', str(self.dst),
                                 '-BackupRoot', str(self.backup), '-Manifest', str(self.manifest),
                                 '-PythonPath', sys.executable, '-GitPath', str(candidates[0])],
                                capture_output=True, timeout=30, env=env)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        self.assertFalse(self.backup.exists())

    def test_invalid_explicit_executable_fails_closed(self):
        script = Path(__file__).with_name('Deploy-BrainnetPatch.ps1')
        result = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script),
                                 '-Preview', '-Source', str(self.src), '-Destination', str(self.dst),
                                 '-BackupRoot', str(self.backup), '-Manifest', str(self.manifest),
                                 '-GitPath', str(self.root / 'ausente' / 'git.exe')], capture_output=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.backup.exists())

    @unittest.skipUnless(os.name == 'nt', 'resolução específica do Windows')
    def test_preview_auto_resolves_desktop_git_and_python_without_path(self):
        profile = Path(os.environ['USERPROFILE'])
        if not list((profile / 'AppData/Local/GitHubDesktop').glob('app-*/resources/app/git/cmd/git.exe')):
            self.skipTest('GitHub Desktop indisponível')
        if not (profile / 'AppData/Local/Programs/Python/Python312/python.exe').is_file():
            self.skipTest('Python 3.12 padrão indisponível')
        powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        env = os.environ.copy()
        env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
        env['LOCALAPPDATA'] = str(self.root / 'localappdata-vazio')
        script = Path(__file__).with_name('Deploy-BrainnetPatch.ps1')
        result = subprocess.run([str(powershell), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script),
                                 '-Preview', '-Source', str(self.src), '-Destination', str(self.dst),
                                 '-BackupRoot', str(self.backup), '-Manifest', str(self.manifest)],
                                capture_output=True, timeout=30, env=env)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        self.assertIn(b'plan_sha256', result.stdout)
        self.assertFalse(self.backup.exists())

    def test_powershell_apply_requires_interactive_confirmation(self):
        p = self.plan()
        script = Path(__file__).with_name('Deploy-BrainnetPatch.ps1')
        result = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script),
                                 '-Apply', '-PlanHash', p['plan_sha256'], '-Source', str(self.src),
                                 '-Destination', str(self.dst), '-BackupRoot', str(self.backup),
                                 '-Manifest', str(self.manifest)], input=b'nao\n', capture_output=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.dst / self.path).read_bytes(), self.old)
        self.assertFalse(self.backup.exists())


if __name__ == '__main__':
    unittest.main()
