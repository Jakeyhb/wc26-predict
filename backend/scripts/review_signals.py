#!/usr/bin/env python3
"""Interactive CLI for reviewing and actioning PENDING news signals.

Lists all PENDING signals, allows the reviewer to inspect each one,
and perform actions: approve, reject, mark expired, mark conflicted, or skip.

Each action updates the news_signals row and logs to signal_review_log.

Usage:
    python scripts/review_signals.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "data" / "local_stage2.db"
VALID_SIGNAL_TYPES = [
    "injury", "suspension", "lineup_change", "tactical_shift",
    "schedule_pressure", "travel_fatigue", "form_change",
    "manager_change", "morale_event", "weather_impact", "other",
]


def get_db() -> sqlite3.Connection:
    """Open a connection to the local SQLite database."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def fmt(val, default: str = "N/A") -> str:
    """Format a database value for display."""
    if val is None:
        return default
    return str(val)


def list_pending_signals(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Fetch all PENDING signals with team name, ordered by created_at desc."""
    rows = conn.execute(
        """
        SELECT ns.id, ns.signal_type, ns.impact_direction, ns.confidence,
               ns.source_reliability, ns.player_name, ns.claim, ns.evidence_snippet,
               ns.summary_zh, ns.normalized_availability, ns.expected_minutes_delta,
               ns.effective_until, ns.conflict_group_id, ns.contradiction_risk,
               ns.review_status, ns.review_notes, ns.reviewed_by, ns.reviewed_at,
               ns.enters_model, ns.created_at, ns.match_id, ns.team_id,
               t.name AS team_name
        FROM news_signals ns
        LEFT JOIN teams t ON ns.team_id = t.id
        WHERE ns.review_status = 'PENDING'
        ORDER BY ns.created_at DESC
        """
    ).fetchall()
    return rows


def print_signal_row(idx: int, row: sqlite3.Row) -> None:
    """Print a single signal in the summary list."""
    team = fmt(row["team_name"])
    player = fmt(row["player_name"])
    stype = row["signal_type"]
    conf = row["confidence"] or 0.0
    rel = row["source_reliability"] or 0.0
    claim = (row["claim"] or "")[:55]
    print(
        f"  {idx:>3}. {stype:<18s} {team:<22s} {player:<20s} "
        f"{conf:.2f} {rel:.2f}  {claim}"
    )


def show_signal_details(row: sqlite3.Row) -> None:
    """Print full details of a single signal."""
    print()
    print(f"  {'=' * 70}")
    print(f"  Signal ID:       {row['id']}")
    print(f"  Type:            {row['signal_type']}")
    print(f"  Impact:          {row['impact_direction']}")
    print(f"  Confidence:      {row['confidence']:.2f}")
    print(f"  Source Reliab.:  {row['source_reliability']:.2f}")
    print(f"  Team:            {fmt(row['team_name'])}")
    print(f"  Player:          {fmt(row['player_name'])}")
    print(f"  Claim:           {fmt(row['claim'])}")
    print(f"  Evidence:        {fmt(row['evidence_snippet'])}")
    print(f"  Summary(zh):     {fmt(row['summary_zh'])}")
    print(f"  Match ID:        {fmt(row['match_id'])}")
    print(f"  Norm. Avail:     {fmt(row['normalized_availability'])}")
    print(f"  Expected Min Δ:  {fmt(row['expected_minutes_delta'])}")
    print(f"  Effective Until: {fmt(row['effective_until'])}")
    print(f"  Conflict Group:  {fmt(row['conflict_group_id'])}")
    print(f"  Contradiction:   {fmt(row['contradiction_risk'])}")
    print(f"  Created At:      {fmt(row['created_at'])}")
    print(f"  Review Status:   {row['review_status']}")
    print(f"  {'=' * 70}")
    print()


def prompt_action() -> str:
    """Prompt the user for an action letter. Returns the chosen action key."""
    while True:
        choice = (
            input("  Action: (A)pprove, (R)eject, mar(E)xpired, (C)onflict, (S)kip, (Q)uit: ")
            .strip()
            .upper()
        )
        if choice in ("A", "R", "E", "C", "S", "Q"):
            return choice
        print("  Invalid choice. Please enter A, R, E, C, S, or Q.")


def prompt_reviewer() -> str:
    """Prompt for reviewer name."""
    while True:
        name = input("  Reviewer name: ").strip()
        if name:
            return name
        print("  Reviewer name cannot be empty.")


def prompt_enter_model() -> bool:
    """Prompt whether the signal should enter the model."""
    val = input("  Enter model (y/N): ").strip().lower()
    return val in ("y", "yes")


def prompt_reject_reason() -> str:
    """Prompt for a rejection reason (required)."""
    while True:
        reason = input("  Rejection reason / notes: ").strip()
        if reason:
            return reason
        print("  A rejection reason is required.")


def prompt_conflict_group_id() -> str:
    """Prompt for conflict group ID."""
    while True:
        gid = input("  Conflict group ID (e.g., UUID of the conflicting signal): ").strip()
        if gid:
            return gid
        print("  Conflict group ID is required.")


def format_now() -> str:
    """Return current UTC timestamp as ISO string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def log_action(
    conn: sqlite3.Connection,
    signal_id: str,
    action: str,
    previous_status: str | None,
    new_status: str,
    reviewer: str | None,
    notes: str | None,
) -> None:
    """Insert a row into signal_review_log."""
    conn.execute(
        """
        INSERT INTO signal_review_log
            (signal_id, action, previous_status, new_status, reviewer, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (signal_id, action, previous_status, new_status, reviewer, notes),
    )


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
        sys.exit(1)

    conn = get_db()

    # Ensure the signal_review_log table exists
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

    print()
    print("=" * 70)
    print("  WC26 Predict - Signal Review Workflow")
    print("=" * 70)

    # Track summary stats
    summary = {"APPROVED": 0, "REJECTED": 0, "EXPIRED": 0, "CONFLICTED": 0, "SKIPPED": 0}

    while True:
        signals = list_pending_signals(conn)
        if not signals:
            print("\n  No more PENDING signals to review.")
            break

        print(f"\n  Found {len(signals)} PENDING signal(s):\n")
        print(f"  {'No.':>4} {'Type':<18s} {'Team':<22s} {'Player':<20s} {'Conf':>5s} {'Rel':>5s}  Claim")
        print(f"  {'-' * 4} {'-' * 18} {'-' * 22} {'-' * 20} {'-' * 5} {'-' * 5}  {'-' * 40}")

        for i, row in enumerate(signals, start=1):
            print_signal_row(i, row)

        print()
        choice = input(f"  Enter signal number to review (1-{len(signals)}), or 'q' to quit: ").strip()

        if choice.lower() == "q":
            break

        try:
            idx = int(choice)
            if idx < 1 or idx > len(signals):
                print(f"  Invalid number. Please enter 1-{len(signals)}.")
                continue
        except ValueError:
            print("  Invalid input. Please enter a number or 'q'.")
            continue

        signal_row = signals[idx - 1]
        show_signal_details(signal_row)

        action = prompt_action()

        if action == "Q":
            break

        if action == "S":
            print(f"  Signal #{idx} skipped.\n")
            summary["SKIPPED"] += 1
            continue

        reviewer = prompt_reviewer()
        now = format_now()
        signal_id = signal_row["id"]
        previous_status = signal_row["review_status"]

        if action == "A":
            # Approve
            enters = prompt_enter_model()
            conn.execute(
                """
                UPDATE news_signals
                SET review_status = 'APPROVED',
                    enters_model = ?,
                    reviewed_by = ?,
                    reviewed_at = ?
                WHERE id = ?
                """,
                (1 if enters else 0, reviewer, now, signal_id),
            )
            log_action(conn, signal_id, "APPROVED", previous_status, "APPROVED", reviewer, None)
            conn.commit()
            print(f"  Signal #{idx} APPROVED. ✓\n")
            summary["APPROVED"] += 1

        elif action == "R":
            # Reject (reason required)
            notes = prompt_reject_reason()
            conn.execute(
                """
                UPDATE news_signals
                SET review_status = 'REJECTED',
                    enters_model = 0,
                    review_notes = ?,
                    reviewed_by = ?,
                    reviewed_at = ?
                WHERE id = ?
                """,
                (notes, reviewer, now, signal_id),
            )
            log_action(conn, signal_id, "REJECTED", previous_status, "REJECTED", reviewer, notes)
            conn.commit()
            print(f"  Signal #{idx} REJECTED. ✗\n")
            summary["REJECTED"] += 1

        elif action == "E":
            # Expired
            conn.execute(
                """
                UPDATE news_signals
                SET review_status = 'EXPIRED',
                    effective_until = ?,
                    reviewed_by = ?,
                    reviewed_at = ?
                WHERE id = ?
                """,
                (now, reviewer, now, signal_id),
            )
            log_action(conn, signal_id, "EXPIRED", previous_status, "EXPIRED", reviewer, "Marked expired")
            conn.commit()
            print(f"  Signal #{idx} EXPIRED. ⌛\n")
            summary["EXPIRED"] += 1

        elif action == "C":
            # Conflict
            conflict_group_id = prompt_conflict_group_id()
            conn.execute(
                """
                UPDATE news_signals
                SET review_status = 'CONFLICTED',
                    conflict_group_id = ?,
                    contradiction_risk = 'HIGH',
                    reviewed_by = ?,
                    reviewed_at = ?
                WHERE id = ?
                """,
                (conflict_group_id, reviewer, now, signal_id),
            )
            log_action(
                conn, signal_id, "CONFLICTED", previous_status, "CONFLICTED",
                reviewer, f"Conflict group: {conflict_group_id}",
            )
            conn.commit()
            print(f"  Signal #{idx} CONFLICTED. ⚠\n")
            summary["CONFLICTED"] += 1

    # Final summary - use a fresh connection to count remaining
    fresh = get_db()
    remaining_count = fresh.execute(
        "SELECT COUNT(*) FROM news_signals WHERE review_status = 'PENDING'"
    ).fetchone()[0]
    fresh.close()
    conn.close()

    print()
    print("=" * 70)
    print("  Review Summary")
    print("=" * 70)
    print(f"  APPROVED:    {summary['APPROVED']}")
    print(f"  REJECTED:    {summary['REJECTED']}")
    print(f"  EXPIRED:     {summary['EXPIRED']}")
    print(f"  CONFLICTED:  {summary['CONFLICTED']}")
    print(f"  SKIPPED:     {summary['SKIPPED']}")
    print(f"  Remaining PENDING: {remaining_count}")
    print("=" * 70)
    print("  Done.")


if __name__ == "__main__":
    main()
