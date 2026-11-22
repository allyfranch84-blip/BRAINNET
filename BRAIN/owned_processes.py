"""Only subprocesses created by an active BrainNet command may be stopped."""
import threading
import subprocess

from execution_authority import current_command_token, require_action_allowed

_lock = threading.Lock()
_owned = {}


def track_process(process):
    token = current_command_token()
    if token is not None:
        with _lock:
            for pid, (old, _) in list(_owned.items()):
                if old.poll() is not None:
                    _owned.pop(pid, None)
            _owned[process.pid] = (process, token)
        if token.is_set():
            process.terminate()
            require_action_allowed("EXECUTE")
    return process


def release_processes(token):
    with _lock:
        for pid, (_, owner) in list(_owned.items()):
            if owner is token:
                _owned.pop(pid, None)


def run_owned(command, *, capture_output=False, timeout=None, check=False, **kwargs):
    if current_command_token() is None:
        return subprocess.run(command, capture_output=capture_output, timeout=timeout, check=check, **kwargs)
    require_action_allowed("EXECUTE")
    if capture_output:
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    process = track_process(subprocess.Popen(command, **kwargs))
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except BaseException:
        process.kill()
        process.communicate()
        raise
    result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    if check:
        result.check_returncode()
    return result


def stop_owned_processes(tokens):
    import psutil
    count, errors = 0, []
    with _lock:
        selected = [(pid, proc) for pid, (proc, token) in _owned.items() if token in tokens]
    for pid, process in selected:
        try:
            if process.poll() is None:
                owner = psutil.Process(pid)
                children = owner.children(recursive=True)
                for child in reversed(children):
                    child.terminate()
                process.terminate()
                _, alive = psutil.wait_procs(children + [owner], timeout=.5)
                for child in alive:
                    child.kill()
                count += 1
            with _lock:
                _owned.pop(pid, None)
        except (psutil.Error, OSError) as ex:
            errors.append(str(ex))
    return count, errors
