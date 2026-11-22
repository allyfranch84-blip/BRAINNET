"""Passive transition persistence through the existing P-DAG writer."""
import sqlite3

import pytest

from pdag_engine import MyelinatedPDAGEngine


@pytest.mark.parametrize("observed,ncd", [(1, 0.4), (0, 0.0)])
def test_transition_writer_persists_factual_result(tmp_path, observed, ncd):
    path = str(tmp_path / "transitions.db")
    engine = MyelinatedPDAGEngine(db_path=path, dim=16, max_nodes=4)
    try:
        engine.record_transition("before", "user_click", "after", observed, ncd, "canvas.exe")
        engine.close()
        with sqlite3.connect(path) as conn:
            assert conn.execute("""SELECT state_before_hash, action_hash, state_after_hash,
                lambda_obs, ncd, app_name FROM transitions""").fetchall() == [
                    ("before", "user_click", "after", observed, ncd, "canvas.exe")]
            assert conn.execute("SELECT timestamp FROM transitions").fetchone()[0] > 0
            assert "idx_trans_app" in {row[1] for row in conn.execute("PRAGMA index_list(transitions)")}
    finally:
        if engine._running:
            engine.close()
