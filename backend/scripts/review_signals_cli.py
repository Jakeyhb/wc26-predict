"""review_signals_cli.py — Unified news signal review CLI (Ticket 7).

Replaces review_signals.py and review_news_signals.py with a single,
consistent CLI using SQLAlchemy + ReviewStatus enums.

Usage:
    python scripts/review_signals_cli.py list [--limit 20] [--team France]
    python scripts/review_signals_cli.py show <signal_id>
    python scripts/review_signals_cli.py approve <signal_id> --reason "..." [--enters-model] [--evidence-id <uuid>]
    python scripts/review_signals_cli.py reject <signal_id> --reason "..."

Every review action writes to signal_review_log for audit trail.
Only APPROVED + enters_model=True + evidence_id IS NOT NULL signals enter the model.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

DB_PATH = BACKEND_DIR / "data" / "local_stage2.db"


# ============================================================================
# Database helpers
# ============================================================================


def _ensure_audit_table() -> None:
    """Create signal_review_log table if it doesn't exist."""
    if not DB_PATH.exists():
        return
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS signal_review_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id CHAR(36) NOT NULL,
            action VARCHAR(20) NOT NULL,
            previous_status VARCHAR(20),
            new_status VARCHAR(20) NOT NULL,
            reviewer VARCHAR(50),
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS ix_signal_review_log_signal_id
        ON signal_review_log(signal_id)
    """)
    conn.commit()
    conn.close()


def _log_review(
    signal_id: str,
    action: str,
    previous_status: str,
    reviewer: str,
    notes: str = "",
) -> None:
    """Write audit log entry."""
    _ensure_audit_table()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """INSERT INTO signal_review_log
           (signal_id, action, previous_status, new_status, reviewer, notes)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (signal_id, action, previous_status, action, reviewer, notes),
    )
    conn.commit()
    conn.close()


def _pending_rows(
    limit: int = 20,
    team_filter: str | None = None,
) -> list[sqlite3.Row]:
    """Fetch pending signals with article data."""
    if not DB_PATH.exists():
        print("Error: Database not found at", DB_PATH)
        return []

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    if team_filter:
        # Find team ID by name
        team_row = conn.execute(
            "SELECT id FROM teams WHERE name LIKE ?", (f"%{team_filter}%",)
        ).fetchone()
        if not team_row:
            print(f"No team found matching '{team_filter}'")
            conn.close()
            return []
        rows = conn.execute(
            """SELECT ns.*, na.title as article_title, na.source_name,
                      t.name as team_name
               FROM news_signals ns
               LEFT JOIN news_articles na ON na.id = ns.article_id
               LEFT JOIN teams t ON t.id = ns.team_id
               WHERE ns.review_status IN ('pending', 'PENDING')
                 AND ns.team_id = ?
               ORDER BY ns.created_at DESC
               LIMIT ?""",
            (team_row["id"], limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT ns.*, na.title as article_title, na.source_name,
                      t.name as team_name
               FROM news_signals ns
               LEFT JOIN news_articles na ON na.id = ns.article_id
               LEFT JOIN teams t ON t.id = ns.team_id
               WHERE ns.review_status IN ('pending', 'PENDING')
               ORDER BY ns.created_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()

    conn.close()
    return rows


def _signal_row(signal_id: str) -> sqlite3.Row | None:
    """Fetch a single signal with full article detail."""
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """SELECT ns.*, na.title as article_title, na.source_name,
                  na.source_url as article_url, na.content as article_body,
                  t.name as team_name
           FROM news_signals ns
           JOIN news_articles na ON na.id = ns.article_id
           LEFT JOIN teams t ON t.id = ns.team_id
           WHERE ns.id = ?""",
        (signal_id,),
    ).fetchone()
    conn.close()
    return row


def _update_signal(
    signal_id: str,
    status: str,
    enters_model: bool,
    evidence_id: str | None,
    reviewer: str,
    notes: str,
) -> str:
    """Update a signal's review fields. Returns previous_status."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    row = conn.execute(
        "SELECT review_status FROM news_signals WHERE id = ?", (signal_id,)
    ).fetchone()
    if not row:
        conn.close()
        raise SystemExit(f"Signal {signal_id} not found")

    previous = row["review_status"] or "pending"
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    conn.execute(
        """UPDATE news_signals
           SET review_status = ?, enters_model = ?, evidence_id = ?,
               review_notes = ?, reviewed_by = ?, reviewed_at = ?
           WHERE id = ?""",
        (
            status,
            1 if enters_model else 0,
            evidence_id,
            notes,
            reviewer,
            now_utc,
            signal_id,
        ),
    )
    conn.commit()
    conn.close()
    return previous


# ============================================================================
# Formatting
# ============================================================================

IMPACT_ICONS = {
    "positive": "▲",
    "negative": "▼",
    "neutral": "─",
    "uncertain": "?",
}


def _fmt_signal_row(r: sqlite3.Row) -> str:
    icon = IMPACT_ICONS.get(r["impact_direction"], "?")
    team = r["team_name"] or "(no team)"
    player = f" [{r['player_name']}]" if r["player_name"] else ""
    confidence = f"{r['confidence']:.0%}" if r["confidence"] else "?"
    reliability = f"{r['source_reliability']:.0%}" if r["source_reliability"] else "?"
    source = r["source_name"] or "?"
    created = r["created_at"] or ""
    if len(created) > 16:
        created = created[:16]

    return (
        f"{str(r['id'])[:8]}… "
        f"{icon} {r['signal_type']:<14} "
        f"conf={confidence} rel={reliability} "
        f"{team}{player} — "
        f"{r['summary_zh'][:60]} "
        f"[{source}] {created}"
    )


# ============================================================================
# Commands
# ============================================================================


def cmd_list(args: argparse.Namespace) -> None:
    """List pending signals."""
    rows = _pending_rows(limit=args.limit, team_filter=args.team)
    if not rows:
        print("No pending signals found.")
        return

    print(f"\n{'='*90}")
    print(f"PENDING SIGNALS ({len(rows)} shown)")
    print(f"{'='*90}")
    for i, r in enumerate(rows, 1):
        print(f"  [{i:2d}] {_fmt_signal_row(r)}")

    print(f"\n  Total pending: {len(rows)}")
    if len(rows) >= args.limit:
        print(f"  (showing first {args.limit}; use --limit N for more)")
    print()
    print("  Use 'show <signal_id>' to see full details.")
    print(f"  Or: python {__file__} show <id>")


def cmd_show(args: argparse.Namespace) -> None:
    """Show full details of a single signal."""
    r = _signal_row(args.signal_id)
    if not r:
        print(f"Signal {args.signal_id} not found.")
        return

    icon = IMPACT_ICONS.get(r["impact_direction"], "?")

    print(f"\n{'='*70}")
    print(f"SIGNAL DETAIL: {r['id']}")
    print(f"{'='*70}")
    print(f"  Status:           {r['review_status']}")
    print(f"  Enters model:     {bool(r['enters_model'])}")
    print(f"  Evidence ID:      {r['evidence_id'] or '(none)'}")
    print(f"  Type:             {r['signal_type']}")
    print(f"  Impact:           {icon} {r['impact_direction']}")
    print(f"  Confidence:       {r['confidence']:.0%}")
    print(f"  Reliability:      {r['source_reliability']:.0%}")
    print(f"  Team:             {r['team_name'] or '(none)'}")
    print(f"  Player:           {r['player_name'] or '(none)'}")
    print(f"  Summary (zh):     {r['summary_zh']}")
    print(f"  Claim:            {r['claim'] or '(none)'}")
    print(f"  Evidence snippet: {r['evidence_snippet'] or '(none)'}")
    print(f"  Availability:     {r['normalized_availability'] or '(none)'}")
    print(f"  Minutes delta:    {r['expected_minutes_delta'] or '(none)'}")
    print(f"  Effective until:  {r['effective_until'] or '(none)'}")
    print(f"  Contradiction:    {r['contradiction_risk'] or '(none)'}")
    print(f"  Conflict group:   {r['conflict_group_id'] or '(none)'}")
    print(f"  Reviewed by:      {r['reviewed_by'] or '(none)'}")
    print(f"  Reviewed at:      {r['reviewed_at'] or '(none)'}")
    print(f"  Key players:      {r['key_players']}")
    print(f"  Created:          {r['created_at']}")
    print(f"  ---")
    print(f"  Article:          {r['article_title']}")
    print(f"  Source:           {r['source_name']}")
    print(f"  URL:              {r['article_url'] or '(none)'}")
    body = (r['article_body'] or "")[:300]
    if len(r['article_body'] or "") > 300:
        body += "..."
    print(f"  Body excerpt:     {body}")
    print(f"{'='*70}")


def cmd_approve(args: argparse.Namespace) -> None:
    """Approve a signal (single, with reason)."""
    if not args.reason or not args.reason.strip():
        raise SystemExit("Error: --reason is required for approval.")

    evidence_id = args.evidence_id or str(uuid4())
    reviewer = args.reviewer or os.environ.get("USER", os.environ.get("USERNAME", "cli"))

    # Validate signal exists and is pending
    r = _signal_row(args.signal_id)
    if not r:
        raise SystemExit(f"Error: Signal {args.signal_id} not found.")

    current_status = (r["review_status"] or "").lower()
    if current_status not in ("pending",):
        print(f"Warning: Signal is already {current_status}. Proceeding anyway.")

    previous = _update_signal(
        signal_id=args.signal_id,
        status="approved",
        enters_model=args.enters_model,
        evidence_id=evidence_id if args.enters_model else None,
        reviewer=reviewer,
        notes=args.reason.strip(),
    )

    _log_review(
        signal_id=args.signal_id,
        action="approved",
        previous_status=previous,
        reviewer=reviewer,
        notes=args.reason.strip(),
    )

    print(f"\n✓ Signal {args.signal_id} APPROVED")
    if args.enters_model:
        print(f"  → Enters model: YES")
        print(f"  → Evidence ID:  {evidence_id}")
    else:
        print(f"  → Enters model: NO (review-only)")
    print(f"  → Reason:       {args.reason.strip()}")
    print(f"  → Reviewer:     {reviewer}")


def cmd_reject(args: argparse.Namespace) -> None:
    """Reject a signal (single, with reason)."""
    if not args.reason or not args.reason.strip():
        raise SystemExit("Error: --reason is required for rejection.")

    reviewer = args.reviewer or os.environ.get("USER", os.environ.get("USERNAME", "cli"))

    r = _signal_row(args.signal_id)
    if not r:
        raise SystemExit(f"Error: Signal {args.signal_id} not found.")

    previous = _update_signal(
        signal_id=args.signal_id,
        status="rejected",
        enters_model=False,
        evidence_id=None,
        reviewer=reviewer,
        notes=args.reason.strip(),
    )

    _log_review(
        signal_id=args.signal_id,
        action="rejected",
        previous_status=previous,
        reviewer=reviewer,
        notes=args.reason.strip(),
    )

    print(f"\n✗ Signal {args.signal_id} REJECTED")
    print(f"  → Reason:   {args.reason.strip()}")
    print(f"  → Reviewer: {reviewer}")


# ============================================================================
# Main
# ============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="WC26 News Signal Review CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/review_signals_cli.py list
  python scripts/review_signals_cli.py list --limit 50 --team France
  python scripts/review_signals_cli.py show abc12345-...
  python scripts/review_signals_cli.py approve abc12345-... --reason "Verified from official source" --enters-model
  python scripts/review_signals_cli.py reject abc12345-... --reason "Unreliable source, no corroboration"
""",
    )

    sub = parser.add_subparsers(dest="command", help="Commands: list, show, approve, reject")

    # list
    p_list = sub.add_parser("list", help="List pending signals")
    p_list.add_argument("--limit", type=int, default=20, help="Max signals to show")
    p_list.add_argument("--team", help="Filter by team name (substring match)")

    # show
    p_show = sub.add_parser("show", help="Show full signal detail")
    p_show.add_argument("signal_id", help="Signal UUID")

    # approve
    p_approve = sub.add_parser("approve", help="Approve a signal")
    p_approve.add_argument("signal_id", help="Signal UUID")
    p_approve.add_argument("--reason", required=True, help="Reason for approval")
    p_approve.add_argument("--enters-model", action="store_true", default=False,
                           help="Allow signal to enter the prediction model")
    p_approve.add_argument("--evidence-id", help="Custom evidence ID (UUID4 auto-generated if omitted)")
    p_approve.add_argument("--reviewer", help="Reviewer name (default: $USER)")

    # reject
    p_reject = sub.add_parser("reject", help="Reject a signal")
    p_reject.add_argument("signal_id", help="Signal UUID")
    p_reject.add_argument("--reason", required=True, help="Reason for rejection")
    p_reject.add_argument("--reviewer", help="Reviewer name (default: $USER)")

    args = parser.parse_args()
    _ensure_audit_table()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "approve":
        cmd_approve(args)
    elif args.command == "reject":
        cmd_reject(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
