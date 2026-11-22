"""No recursive pytest or real LLM: exercise autotest orchestration with mocks."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import subprocess
import sys

import pytest

import autotest
from test_professor_mode import bridge, send


@pytest.fixture(autouse=True)
def isolated_validation_environment(monkeypatch):
    monkeypatch.delenv("BRAINNET_AUTOTEST_RUNNING",raising=False)
    monkeypatch.delenv("BRAINNET_AUTOCURA_VALIDATING",raising=False)


def result(code, stdout="", stderr=""):
    return SimpleNamespace(returncode=code, stdout=stdout, stderr=stderr)


def test_healthy_run_does_not_call_healer(bridge):
    with patch("autotest.subprocess.run",return_value=result(0,"525 passed in 41.84s")) as run:
        response = send(bridge,"/autoteste")
    assert response["reply"] == "✅ Todos os testes passaram. O sistema está saudável."
    assert run.call_args.args[0] == [sys.executable,"-m","pytest","-q","--tb=short"]
    assert run.call_args.kwargs["cwd"] == str(autotest.BRAIN_DIR)
    assert run.call_args.kwargs["capture_output"] and run.call_args.kwargs["text"]
    assert run.call_args.kwargs["env"]["BRAINNET_AUTOTEST_RUNNING"] == "1"
    bridge._kernel.blackbox.disparar_auto_cura.assert_not_called()
    bridge._tom.evaluate_intent.assert_not_called()


def test_failure_heals_once_then_revalidates():
    blackbox = MagicMock()
    blackbox.disparar_auto_cura.return_value = {"status":"PATCH_APLICADO_TESTES_OK"}
    with patch("autotest.subprocess.run",side_effect=[result(1,"x"*3000,"trace"),result(0,"tests green")]) as run:
        response = autotest.run_autotest(blackbox)
    assert response["reply"] == "🛠️ Código corrigido autonomamente pelo Qwen-Coder 7B. Testes verdes."
    assert run.call_count == 2
    blackbox.disparar_auto_cura.assert_called_once()
    snapshot = blackbox.disparar_auto_cura.call_args.args[0]
    assert len(snapshot["traceback"]) == 2000
    assert snapshot["estado_observado"]["stderr"] == "trace"
    blackbox.pdag.apply_user_report_penalty.assert_not_called()


@pytest.mark.parametrize("status",["NEED_EVIDENCE","NO_SAFE_PATCH","PATCH_REVERTIDO"])
def test_no_unconfirmed_repair_credit(status):
    blackbox = MagicMock()
    blackbox.disparar_auto_cura.return_value = {"status":status}
    with patch("autotest.subprocess.run",side_effect=[result(1,"failure"),result(0,"green")]):
        response = autotest.run_autotest(blackbox)
    assert status in response["reply"] and "corrigido autonomamente" not in response["reply"]


def test_remaining_failure_never_claims_success():
    blackbox = MagicMock()
    blackbox.disparar_auto_cura.return_value = {"status":"PATCH_APLICADO_TESTES_OK"}
    with patch("autotest.subprocess.run",side_effect=[result(1,"first"),result(1,"second")]) as run:
        response = autotest.run_autotest(blackbox)
    assert "continuam falhando" in response["reply"]
    assert run.call_count == 2 and blackbox.disparar_auto_cura.call_count == 1


def test_healer_exception_still_revalidates_disk_state():
    blackbox = MagicMock()
    blackbox.disparar_auto_cura.side_effect = RuntimeError("unavailable")
    with patch("autotest.subprocess.run",side_effect=[result(1,"first"),result(1,"second")]) as run:
        response = autotest.run_autotest(blackbox)
    assert "ERRO_AUTO_CURA" in response["reply"] and run.call_count == 2


@pytest.mark.parametrize("flag",["BRAINNET_AUTOTEST_RUNNING","BRAINNET_AUTOCURA_VALIDATING"])
def test_subprocess_cannot_recurse(monkeypatch,flag):
    monkeypatch.setenv(flag,"1")
    with patch("autotest.subprocess.run") as run:
        assert "recursiva bloqueada" in autotest.run_autotest(MagicMock())["reply"]
    run.assert_not_called()


def test_timeout_is_reported_without_healing():
    blackbox = MagicMock()
    with patch("autotest.subprocess.run",side_effect=subprocess.TimeoutExpired("pytest",180)):
        assert "180 segundos" in autotest.run_autotest(blackbox)["reply"]
    blackbox.disparar_auto_cura.assert_not_called()


def test_reentrant_command_is_rejected(bridge):
    import threading
    bridge._autotest_lock = threading.Lock()
    bridge._autotest_lock.acquire()
    try:
        with patch("autotest.subprocess.run") as run:
            assert "já está em execução" in send(bridge,"/autoteste")["reply"]
        run.assert_not_called()
    finally:
        bridge._autotest_lock.release()


def test_excerpt_is_local_bounded_and_exact(tmp_path,monkeypatch):
    monkeypatch.setattr(autotest,"BRAIN_DIR",tmp_path)
    lines = [f"line_{i}\n" for i in range(1,101)]
    (tmp_path/"module.py").write_text("".join(lines),encoding="utf-8")
    (tmp_path/"test_module.py").write_text("do not patch tests",encoding="utf-8")
    excerpts = autotest._local_evidence("module.py:50: in work\ntest_module.py:1: failure\n../outside.py:2: failure")
    assert len(excerpts) == 1 and excerpts[0]["file"] == "module.py"
    assert excerpts[0]["content"] == "".join(lines[41:58])
