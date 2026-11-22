"""Native hotbar lifecycle checks without Qt imports, real processes or windows."""
import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parent


def isolated_bridge_class():
    path = ROOT / "BRAINNET.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BrainnetBridge")
    methods = [n for n in cls.body if isinstance(n, ast.FunctionDef)
               and n.name in ("set_widget_mode", "close_window")]
    import threading
    env = {"__file__": str(path), "Dict": Dict, "Any": Any, "logger": Mock(), "threading": threading}
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(path), "exec"), env)
    return type("IsolatedBridge", (), {n.name: env[n.name] for n in methods})


class NativeHotbarLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.bridge = isolated_bridge_class()()
        self.bridge._window = Mock()
        self.bridge._hotbar_process = None
        self.bridge._widget_mode = False
        self.process = Mock()
        self.process.poll.return_value = None
        self.process.wait.return_value = 0
        self.workers = []

        def capture_worker(*, target, daemon):
            self.assertTrue(daemon)
            self.workers.append(target)
            return SimpleNamespace(start=Mock())

        self.popen = self.enterContext(patch("subprocess.Popen", return_value=self.process))
        self.enterContext(patch("threading.Thread", side_effect=capture_worker))

    def test_launches_python312_and_hides_only_main_window(self):
        self.assertEqual(self.bridge.set_widget_mode(True), {"ok": True, "widget": True})
        args, kwargs = self.popen.call_args
        self.assertEqual(args[0][:2], ["py", "-3.12"])
        self.assertEqual(Path(args[0][2]), ROOT / "main_hotbar.py")
        self.assertEqual(Path(kwargs["cwd"]), ROOT)
        self.bridge._window.hide.assert_called_once()
        self.assertEqual(len(self.workers), 1)

    def test_child_exit_restores_main_and_notifies_react(self):
        self.bridge.set_widget_mode(True)
        self.workers[0]()
        self.process.wait.assert_called_once()
        self.assertIsNone(self.bridge._hotbar_process)
        self.assertFalse(self.bridge._widget_mode)
        self.bridge._window.show.assert_called_once()
        self.assertIn("aios:widget_closed", self.bridge._window.evaluate_js.call_args.args[0])

    def test_repeated_activation_does_not_spawn_duplicate_process(self):
        self.bridge.set_widget_mode(True)
        self.bridge.set_widget_mode(True)
        self.popen.assert_called_once()
        self.assertEqual(len(self.workers), 1)

    def test_explicit_disable_terminates_child_and_restores_once(self):
        self.bridge.set_widget_mode(True)
        self.assertEqual(self.bridge.set_widget_mode(False), {"ok": True, "widget": False})
        self.process.terminate.assert_called_once()
        self.workers[0]()
        self.bridge._window.show.assert_called_once()
        self.assertFalse(self.bridge._widget_mode)

    def test_old_waiter_cannot_clear_a_new_child(self):
        self.bridge.set_widget_mode(True)
        newer = Mock()
        self.bridge._hotbar_process = newer
        self.workers[0]()
        self.assertIs(self.bridge._hotbar_process, newer)
        self.assertTrue(self.bridge._widget_mode)
        self.bridge._window.show.assert_not_called()

    def test_start_failure_does_not_leave_main_hidden(self):
        self.popen.side_effect = FileNotFoundError("py launcher unavailable")
        result = self.bridge.set_widget_mode(True)
        self.assertFalse(result["ok"])
        self.assertFalse(self.bridge._widget_mode)
        self.bridge._window.hide.assert_not_called()
        self.bridge._window.show.assert_called_once()

    def test_closing_main_terminates_owned_child_and_suppresses_restore(self):
        self.bridge.set_widget_mode(True)
        self.assertEqual(self.bridge.close_window(), {"ok": True})
        self.process.terminate.assert_called_once()
        self.bridge._window.destroy.assert_called_once()
        self.workers[0]()
        self.bridge._window.show.assert_not_called()


class NativeNavigationTests(unittest.TestCase):
    def test_close_and_expand_are_intercepted_without_real_qt(self):
        path = ROOT / "main_hotbar.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "CustomWebEnginePage")

        class PageBase:
            def __init__(self, profile, parent=None):
                pass

            def acceptNavigationRequest(self, url, kind, is_main):
                return "delegated"

        app = Mock()
        env = {"QWebEnginePage": PageBase, "QApplication": app}
        exec(compile(ast.Module(body=[cls], type_ignores=[]), str(path), "exec"), env)
        page = env["CustomWebEnginePage"](Mock())
        for host in ("close", "expand"):
            url = SimpleNamespace(scheme=lambda: "aios", host=lambda: host)
            self.assertIs(page.acceptNavigationRequest(url, 0, True), False)
        self.assertEqual(app.quit.call_count, 2)
        url = SimpleNamespace(scheme=lambda: "http", host=lambda: "localhost")
        self.assertEqual(page.acceptNavigationRequest(url, 0, True), "delegated")
        self.assertEqual(app.quit.call_count, 2)


if __name__ == "__main__":
    unittest.main()
