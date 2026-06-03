#!/usr/bin/env python3
"""Create the signal_review_log table for tracking review actions.

This migration creates the audit/log table that records every action taken
during the signal review workflow (approve, reject, expire, conflict, revert).

Usage:
    python scripts/create_signal_review_log_table.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "data" / "local_stage2.db"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signal_review_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id CHAR(32) NOT NULL REFERENCES news_signals(id),
                action VARCHAR(20) NOT NULL,
                previous_status VARCHAR(20),
                new_status VARCHAR(20) NOT NULL,
                reviewer VARCHAR(50),
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_signal_review_log_signal_id "
            "ON signal_review_log(signal_id)"
        )
        conn.commit()
        print("signal_review_log table created successfully.")
        print("  Columns: id, signal_id, action, previous_status, new_status,")
        print("           reviewer, notes, created_at")
        print("  Index:   ix_signal_review_log_signal_id ON signal_id")
    except sqlite3.Error as e:
        print(f"Error creating table: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
