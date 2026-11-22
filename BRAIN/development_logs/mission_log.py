"""Explicit development-event journal; no background worker or Kernel integration."""
import json
import os
from pathlib import Path
import time
import uuid

FILES = {'mission': 'missions.jsonl', 'benchmark': 'benchmarks.jsonl', 'failure': 'failures.jsonl'}

def append_event(directory, kind, payload, timeout=5.0):
    if kind not in FILES or not isinstance(payload, dict):
        raise ValueError('invalid journal event')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    record = {'event_id': uuid.uuid4().hex, 'kind': kind, **payload}
    # IDs and kinds are controlled by the journal, not by the caller.
    record['event_id'] = uuid.uuid4().hex
    record['kind'] = kind
    line = (json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
    lock_path = directory / '.journal.lock'
    with open(lock_path, 'a+b') as lock:
        lock.seek(0, os.SEEK_END)
        if lock.tell() == 0:
            lock.write(b'0'); lock.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                lock.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('journal lock timeout')
                time.sleep(.02)
        try:
            with open(directory / FILES[kind], 'ab') as output:
                output.write(line); output.flush(); os.fsync(output.fileno())
        finally:
            lock.seek(0)
            if os.name == 'nt':
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return record['event_id']

def read_events(directory, kind):
    if kind not in FILES:
        raise ValueError('invalid journal kind')
    path = Path(directory) / FILES[kind]
    if not path.exists():
        return []
    with path.open(encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]
