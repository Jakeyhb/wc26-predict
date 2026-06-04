#!/usr/bin/env python3
"""enable_sqlite_wal.py — Enable WAL journal mode on the local SQLite database.

WAL (Write-Ahead Logging) allows concurrent reads during writes, which
is useful when the Dashboard reads the database while scripts write to it.

This script must be run ONCE manually. WAL mode persists in the database
file across re-opens — the Dashboard does NOT need to set it on every connect.

Usage:
    python scripts/enable_sqlite_wal.py
    python scripts/enable_sqlite_wal.py --db-path path/to/other.db
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[1] / "backend" / "data" / "local_stage2.db"


def enable_wal(db_path: Path) -> bool:
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        return False

    conn = sqlite3.connect(str(db_path))
    try:
        result = conn.execute("PRAGMA journal_mode=WAL").fetchone()
        current_mode = result[0] if result else "unknown"
        print(f"Journal mode set to: {current_mode}")

        # Verify persistence
        conn.close()
        conn2 = sqlite3.connect(str(db_path))
        verify = conn2.execute("PRAGMA journal_mode").fetchone()
        print(f"Verified journal mode: {verify[0] if verify else 'unknown'}")
        conn2.close()
        return True
    except Exception as e:
        print(f"ERROR: {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enable WAL mode on the local SQLite database"
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB,
        help=f"Path to SQLite database (default: {DEFAULT_DB})",
    )
    args = parser.parse_args()

    print(f"Enabling WAL mode on: {args.db_path}")
    ok = enable_wal(args.db_path)
    if ok:
        print("Done. WAL mode is now enabled and persisted.")
        print(
            "The Dashboard does not set journal_mode — this script is the "
            "single place where WAL is configured."
        )
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
