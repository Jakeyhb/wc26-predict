"""Utilities for the closed-loop resolution ledger."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


RESOLVER_VERSION = "closed_loop_v1"

STATUS_RESOLVED = "resolved"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_UNRESOLVABLE_LEGACY = "unresolvable_legacy"
STATUS_SKIPPED_NOT_LEARNING_ELIGIBLE = "skipped_not_learning_eligible"

QUARANTINE_STATUSES = (
    STATUS_AMBIGUOUS,
    STATUS_UNRESOLVABLE_LEGACY,
    STATUS_SKIPPED_NOT_LEARNING_ELIGIBLE,
)


@dataclass(frozen=True)
class ResolutionRecord:
    entity_table: str
    entity_id: str
    status: str
    reason: str
    resolved_match_id: str | None = None
    resolved_prediction_run_id: str | None = None
    confidence: float | None = None
    source_payload: dict[str, Any] | None = None
    resolver_version: str = RESOLVER_VERSION


def ensure_resolution_ledger(conn: sqlite3.Connection) -> None:
    """Create the ledger table for SQLite-based scripts if needed."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS closed_loop_resolution_ledger (
            id TEXT PRIMARY KEY,
            entity_table TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            status TEXT NOT NULL,
            resolved_match_id TEXT,
            resolved_prediction_run_id TEXT,
            confidence REAL,
            reason TEXT NOT NULL,
            resolver_version TEXT NOT NULL,
            source_payload TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(entity_table, entity_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_closed_loop_resolution_entity "
        "ON closed_loop_resolution_ledger(entity_table, entity_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_closed_loop_resolution_status "
        "ON closed_loop_resolution_ledger(status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_closed_loop_resolution_match "
        "ON closed_loop_resolution_ledger(resolved_match_id)"
    )


def upsert_resolution(conn: sqlite3.Connection, record: ResolutionRecord) -> None:
    """Insert or update a ledger record."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO closed_loop_resolution_ledger (
            id, entity_table, entity_id, status, resolved_match_id,
            resolved_prediction_run_id, confidence, reason, resolver_version,
            source_payload, created_at, updated_at
        )
        VALUES (
            :id, :entity_table, :entity_id, :status, :resolved_match_id,
            :resolved_prediction_run_id, :confidence, :reason, :resolver_version,
            :source_payload, :now, :now
        )
        ON CONFLICT(entity_table, entity_id) DO UPDATE SET
            status = excluded.status,
            resolved_match_id = excluded.resolved_match_id,
            resolved_prediction_run_id = excluded.resolved_prediction_run_id,
            confidence = excluded.confidence,
            reason = excluded.reason,
            resolver_version = excluded.resolver_version,
            source_payload = excluded.source_payload,
            updated_at = excluded.updated_at
        """,
        {
            **asdict(record),
            "id": str(uuid.uuid4()),
            "source_payload": json.dumps(record.source_payload or {}, ensure_ascii=False, sort_keys=True),
            "now": now,
        },
    )


def has_resolution_ledger(conn: sqlite3.Connection) -> bool:
    return (
        conn.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE type = 'table' AND name = 'closed_loop_resolution_ledger'
            """
        ).fetchone()[0]
        > 0
    )


def ledger_status_counts(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return grouped ledger status counts, or an empty list if missing."""
    if not has_resolution_ledger(conn):
        return []
    return list(
        conn.execute(
            """
            SELECT entity_table, status, COUNT(*) AS count
            FROM closed_loop_resolution_ledger
            GROUP BY entity_table, status
            ORDER BY entity_table, status
            """
        )
    )
