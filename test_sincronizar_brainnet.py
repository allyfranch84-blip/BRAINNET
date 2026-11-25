import json
import subprocess
from unittest.mock import Mock

import pytest
import sincronizar_brainnet as sync


@pytest.fixture
def package(tmp_path):
    name = "BRAIN/inference_supervisor.py"
    path = tmp_path / name
    path.parent.mkdir()
    (tmp_path / ".git").mkdir()
    path.write_bytes(b"old\r\n")
    new = b"new\n"
    release = {"format": 1, "files": [{"path": name, "before": sync.source_hash(b"old\n"),
                                        "after": sync.source_hash(new)}]}
    return path, release, lambda: sync.plan(tmp_path, release, lambda _: new)


def test_preview_apply_reopen_and_reapply(tmp_path, package):
    path, release, prepare = package
    assert prepare()["BRAIN/inference_supervisor.py"][0] == "UPDATE"
    assert path.read_bytes() == b"old\r\n"
    check = Mock()
    assert sync.install(tmp_path, "a"*40, prepare, check)["status"] == "VERIFIED"
    assert path.read_bytes() == b"new\r\n"
    assert prepare()["BRAIN/inference_supervisor.py"][0] == "PRESENT"
    assert sync.install(tmp_path, "a"*40, prepare, check)["status"] == "VERIFIED"
    journals = list((tmp_path / ".git").rglob("result.json"))
    assert len(journals) == 2 and check.call_count == 2
    backups = list((tmp_path / ".git").rglob("inference_supervisor.py"))
    assert len(backups) == 1 and backups[0].read_bytes() == b"old\r\n"


def test_local_change_stops_before_validation(tmp_path, package):
    path, _, prepare = package
    path.write_bytes(b"private edit")
    check = Mock()
    with pytest.raises(RuntimeError, match="CONFLICT"):
        sync.install(tmp_path, "a"*40, prepare, check)
    check.assert_not_called()
    assert path.read_bytes() == b"private edit"


@pytest.mark.parametrize("concurrent", [True, False])
def test_failed_real_validation_keeps_edits_or_restores_original(tmp_path, package, concurrent):
    path, _, prepare = package
    def fail(root):
        assert path.read_bytes() == b"new\r\n"
        if concurrent:
            path.write_bytes(b"new user edit")
        raise subprocess.CalledProcessError(1, "validation")
    with pytest.raises(subprocess.CalledProcessError):
        sync.install(tmp_path, "a"*40, prepare, fail)
    journal = json.loads(next((tmp_path / ".git").rglob("result.json")).read_text())
    assert journal["status"] == ("ROLLBACK_CONFLICT" if concurrent else "ROLLED_BACK")
    assert path.read_bytes() == (b"new user edit" if concurrent else b"old\r\n")


def test_second_application_cannot_enter_lock(tmp_path, package):
    _, _, prepare = package
    def validate(_):
        with pytest.raises(FileExistsError):
            sync.install(tmp_path, "b"*40, prepare, Mock())
    sync.install(tmp_path, "a"*40, prepare, validate)


@pytest.mark.parametrize("wrong_path", ["../outside.py", "BRAIN/brainnet_config.json", "BRAIN/hmem_memory.db"])
def test_manifest_cannot_choose_other_targets(package, wrong_path):
    _, release, prepare = package
    release["files"][0]["path"] = wrong_path
    with pytest.raises(ValueError, match="Destino"):
        prepare()


def test_rejects_hash_and_format_mismatches(package):
    _, release, prepare = package
    release["files"][0]["after"] = "0"*64
    with pytest.raises(ValueError, match="Hash"):
        prepare()
    release["format"] = 2
    with pytest.raises(ValueError, match="Formato"):
        prepare()


def test_new_file_rollback_and_conflict(tmp_path, package):
    _, release, _ = package
    name = "BRAIN/test_workspace_choice.py"
    path = tmp_path / name
    release["files"] = [{"path":name, "before":None, "after":sync.source_hash(b"fixture")}]
    def prepare():
        return sync.plan(tmp_path, release, lambda _: b"fixture")
    with pytest.raises(RuntimeError, match="fixture failure"):
        sync.install(tmp_path, "c"*40, prepare, Mock(side_effect=RuntimeError("fixture failure")))
    assert not path.exists()
    path.write_bytes(b"local change")
    assert prepare()[name][0] == "CONFLICT"


def test_legacy_preview_never_runs_installer(tmp_path, monkeypatch, capsys):
    # Real Git object reads. A top-level side effect would reveal execution even in preview.
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args])
    git("init", "-q")
    target = tmp_path / sync.PATCH
    target.parent.mkdir()
    marker = tmp_path / "legacy-ran"
    target.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
    git("add", sync.PATCH)
    git("-c", "user.name=Test", "-c", "user.email=test@invalid", "commit", "-qm", "fixture")
    git("update-ref", sync.REF, "HEAD")
    monkeypatch.setattr(sync, "ROOT", tmp_path)
    sync.sync(cached=True)
    assert "LEGACY_PREVIEW" in capsys.readouterr().out and not marker.exists()
    with pytest.raises(ValueError, match="Cache"):
        sync.sync(cached=True, apply="a"*40)
