import hashlib
import json
import logging
import difflib
from pathlib import Path

logger = logging.getLogger("BRAINNET_Introspection")

class SelfInspector:
    def __init__(self, brain_dir):
        self.brain_dir = Path(brain_dir)
        self.history_file = self.brain_dir / ".code_history.json"

    def _scan_files(self):
        files = {}
        for p in self.brain_dir.rglob("*.py"):
            # Ignora testes e o próprio inspetor para não gerar loop
            if p.name.startswith("test_") or p.name in ("self_inspector.py", "conftest.py"):
                continue
            rel = str(p.relative_to(self.brain_dir))
            try:
                files[rel] = p.read_text(encoding="utf-8")
            except Exception:
                pass
        return files

    def load_history(self):
        if self.history_file.exists():
            try:
                return json.loads(self.history_file.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def save_history(self, files):
        self.history_file.write_text(json.dumps(files, indent=2), encoding="utf-8")

    def audit_read_only(self, modules, *, run_tests=False, hash_baseline=None):
        """Evidence-only audit; never invokes legacy rollback or updates baseline."""
        import subprocess
        import sys
        import time
        import uuid
        from code_mapper import index_symbols
        from development_logs.mission_log import append_event
        from regression_runner import MAP, GROUPS
        if not isinstance(modules, (tuple, list)) or not modules:
            raise ValueError('modules required')
        inventories, hashes = {}, {}
        root = self.brain_dir.resolve()
        for name in modules:
            path = (root / name).resolve()
            if path.parent != root or path.suffix != '.py' or not path.is_file():
                raise ValueError('module outside audit scope or missing')
            hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
            info = index_symbols(path)
            inventories[path.name] = {'symbols': info['symbols'], 'imports': info['imports'],
                                      'analysis': info['analysis']}
        changes = {'source': 'UNKNOWN', 'paths': [], 'limitations': []}
        try:
            git = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=normal'],
                                 cwd=root, capture_output=True, text=True, timeout=5, check=False)
            if git.returncode == 0:
                changes = {'source': 'git', 'paths': git.stdout.splitlines(), 'limitations': ['includes untracked files; status paths are not function-level diffs']}
        except (OSError, subprocess.TimeoutExpired):
            pass
        if changes['source'] == 'UNKNOWN' and hash_baseline is not None:
            baseline = json.loads(Path(hash_baseline).read_text(encoding='utf-8'))
            changes = {'source': 'hash_manifest', 'paths': [name for name, value in hashes.items() if baseline.get(name) != value],
                       'limitations': ['only explicitly audited modules; no rename detection']}
        selected_groups = sorted({group for name in inventories for group in MAP.get(name, ['fast', 'integration'])})
        targets = list(dict.fromkeys(target for group in selected_groups for target in GROUPS[group]))
        result = {'audit_id': uuid.uuid4().hex, 'timestamp': time.time(), 'mode': 'READ_ONLY',
                  'hashes': hashes, 'changes': changes, 'inventories': inventories,
                  'test_targets': targets, 'regression': {'status': 'NOT_RUN'},
                  'limitations': ['AST calls and imports do not prove runtime use',
                                  'dynamic imports and event dispatch require separate review',
                                  'no code fixes are applied']}
        if {'BRAINNET.py', 'adaptive_resource_controller.py'} <= inventories.keys():
            bridge_text = (root / 'BRAINNET.py').read_text(encoding='utf-8')
            budget_text = (root / 'adaptive_resource_controller.py').read_text(encoding='utf-8')
            result['motor_review'] = {
                'waiting_authorization': {'present': 'WAITING_AUTHORIZATION' in budget_text,
                                          'evidence': 'adaptive_resource_controller.py:begin_pending_motor'},
                'simulated_transitions': {'present': 'def transition_motor_simulation' in budget_text,
                                          'evidence': 'adaptive_resource_controller.py:transition_motor_simulation',
                                          'classification': 'TESTADA ISOLADAMENTE; verificar testes executados'},
                'chat_proposal': {'present': 'pending_operation_id' in bridge_text,
                                  'evidence': 'BRAINNET.py:_send_command_impl',
                                  'classification': 'INTEGRADA EM SIMULAÇÃO; não comprova despacho'},
                'resume': {'status': 'NOT_PROVEN', 'reason': 'busca estática não demonstra retomada ou evento confiável da GUI'},
                'physical_execution': {'status': 'NOT_PROVEN', 'reason': 'auditoria não realiza atuação'},
                'suggested_tests': ['handler real com aprovação simulada vinculada e exatamente um despacho simulado',
                                    'cancelamento, expiração e aprovação concorrentes',
                                    'janela ou região alterada bloqueia a continuação'],
            }
        if run_tests:
            cmd = [sys.executable, str(root / 'regression_runner.py'), '--suite', 'safe-full']
            try:
                proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=330)
                try: summary = json.loads(proc.stdout)
                except ValueError: summary = None
                result['regression'] = {'status': 'COMPLETED' if summary is not None else 'INCONCLUSIVE',
                                        'exit_code': proc.returncode, 'summary': summary,
                                        'stderr_tail': proc.stderr[-2000:]}
            except (OSError, subprocess.TimeoutExpired) as exc:
                result['regression'] = {'status': 'TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else 'ERROR',
                                        'error': str(exc)}
        directory = root / 'development_logs'
        directory.mkdir(exist_ok=True)
        audit_path = directory / ('SELF_AUDIT_' + result['audit_id'] + '.json')
        audit_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        append_event(directory, 'mission', {'mission_id': 'V9.8-Q1', 'audit_id': result['audit_id'],
                                             'timestamp': result['timestamp'], 'evidence': str(audit_path),
                                             'regression_status': result['regression']['status']})
        result['evidence_path'] = str(audit_path)
        return result

    def diagnose_audited_timeout(self, test_id, *, timeout=12):
        """Run one audited mocked test in an owned subprocess, with stack capture."""
        import os
        import subprocess
        import sys
        import uuid
        allowed = {'test_v98a_capability_lab.py::test_move_requires_authorization_and_independent_observation'}
        if test_id not in allowed or not 5 <= timeout <= 30:
            raise ValueError('test or timeout not audited')
        directory = self.brain_dir / 'development_logs'
        directory.mkdir(exist_ok=True)
        path = directory / ('SELF_AUDIT_TIMEOUT_' + uuid.uuid4().hex + '.log')
        env = os.environ.copy()
        env['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
        command = [sys.executable, '-m', 'pytest', '-vv', '-s', '-p', 'no:cacheprovider',
                   '-o', 'faulthandler_timeout=4', test_id]
        with path.open('w', encoding='utf-8') as output:
            try:
                child = subprocess.run(command, cwd=self.brain_dir, env=env, stdout=output,
                                       stderr=subprocess.STDOUT, timeout=timeout, check=False)
                status, code = ('PASS' if child.returncode == 0 else 'FAILED'), child.returncode
            except subprocess.TimeoutExpired:
                output.write('\nTIMEOUT: owned test subprocess terminated after deadline\n')
                status, code = 'TIMEOUT', None
        return {'test_id': test_id, 'status': status, 'exit_code': code, 'log': str(path)}

    def _run_tests(self):
        """Roda pytest em background. Retorna (passou, saida)."""
        import subprocess
        import sys
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "--tb=short", "--basetemp=C:\\pytest_temp"],
                cwd=str(self.brain_dir),
                capture_output=True, text=True, timeout=180,
            )
            return r.returncode == 0, (r.stdout or "") + "\n" + (r.stderr or "")
        except Exception as e:
            return False, f"Falha ao rodar pytest: {e}"

    def check_for_changes(self):
        old_files = self.load_history()
        new_files = self._scan_files()

        # Se for a primeira vez, apenas salva o estado e não avisa nada
        if not old_files:
            self.save_history(new_files)
            return None

        added = [f for f in new_files if f not in old_files]
        removed = [f for f in old_files if f not in new_files]
        modified = [f for f in new_files if f in old_files and new_files[f] != old_files[f]]

        if not (added or removed or modified):
            return None

        diffs = {}
        for f in modified:
            old_lines = old_files[f].splitlines()
            new_lines = new_files[f].splitlines()
            diff = list(difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{f}", tofile=f"b/{f}", lineterm=""))
            diffs[f] = "\n".join(diff[:50]) # Limita a 50 linhas para não poluir

        # P152: valida integridade antes de aceitar a mudança
        py_changes = [f for f in (added + removed + modified) if f.endswith(".py")]
        test_ok = None
        if py_changes:
            logger.info(f"[INTROSPECTION]: {len(py_changes)} arquivo(s) .py alterado(s). Validando com pytest...")
            test_ok, test_output = self._run_tests()
            if not test_ok:
                restored = []
                for f in modified:
                    if f in old_files:
                        try:
                            (self.brain_dir / f).write_text(old_files[f], encoding="utf-8")
                            restored.append(f)
                        except Exception:
                            pass
                for f in added:
                    try:
                        (self.brain_dir / f).unlink(missing_ok=True)
                        restored.append(f)
                    except Exception:
                        pass
                logger.warning(f"[INTROSPECTION]: Testes falharam. Rollback em: {restored}")
                return {
                    "rolled_back": True,
                    "restored": restored,
                    "test_output": test_output[:1500],
                    "added": [], "removed": [], "modified": [], "diffs": {},
                }

        self.save_history(new_files)

        return {
            "rolled_back": False,
            "added": added,
            "removed": removed,
            "modified": modified,
            "diffs": diffs,
            "test_passed": test_ok,
        }
