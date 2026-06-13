from __future__ import annotations

import sqlite3

from app.services.closed_loop_resolution import (
    STATUS_RESOLVED,
    ResolutionRecord,
    ensure_resolution_ledger,
    upsert_resolution,
)


def test_resolution_ledger_upsert_updates_status(tmp_path):
    db = tmp_path / "ledger.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    ensure_resolution_ledger(conn)

    upsert_resolution(
        conn,
        ResolutionRecord(
            entity_table="prediction_snapshots",
            entity_id="snap-1",
            status=STATUS_RESOLVED,
            reason="team_pair+time",
            resolved_match_id="11111111111111111111111111111111",
            confidence=0.95,
        ),
    )
    upsert_resolution(
        conn,
        ResolutionRecord(
            entity_table="prediction_snapshots",
            entity_id="snap-1",
            status=STATUS_RESOLVED,
            reason="updated",
            resolved_match_id="22222222222222222222222222222222",
            confidence=0.99,
        ),
    )
    conn.commit()

    rows = list(conn.execute("SELECT * FROM closed_loop_resolution_ledger"))
    assert len(rows) == 1
    assert rows[0]["reason"] == "updated"
    assert rows[0]["resolved_match_id"] == "22222222222222222222222222222222"
    conn.close()
