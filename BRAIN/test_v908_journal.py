import concurrent.futures
import tempfile
import unittest
from pathlib import Path
from development_logs.mission_log import append_event, read_events

class JournalTests(unittest.TestCase):
    def test_demo_and_concurrent_append(self):
        with tempfile.TemporaryDirectory() as folder:
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                ids = list(pool.map(lambda n: append_event(folder, 'mission', {'mission_id': 'demo', 'n': n}), range(40)))
            events = read_events(folder, 'mission')
            self.assertEqual(len(events), 40)
            self.assertEqual(len(set(ids)), 40)
            self.assertEqual({item['n'] for item in events}, set(range(40)))
            self.assertTrue((Path(folder) / 'missions.jsonl').is_file())
