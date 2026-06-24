"""consensus_save.py — persist market consensus to market_consensus_snapshots.

Sync (sqlite3), best-effort, never throws. Designed to be called from any
prediction path (CLI, Dashboard, API) without async/await overhead.

Usage:
    from app.services.market.consensus_save import save_market_consensus

    save_market_consensus(
        match_id="WC26-FRA-vs-ARG",
        home_team="France", away_team="Argentina",
        market_probs={"home_prob": 0.45, "draw_prob": 0.25, "away_prob": 0.30, ...},
    )
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[3]
DB_PATH = BACKEND_DIR / "data" / "local_stage2.db"


def save_market_consensus(
    *,
    match_id: str = "",
    home_team: str = "",
    away_team: str = "",
    kickoff_at: str = "",
    market_probs: dict[str, Any] | None = None,
    competition: str = "",
) -> str | None:
    """Persist market implied probabilities to market_consensus_snapshots.

    Args:
        match_id: Match identifier (optional, derived from teams if empty).
        home_team, away_team: Team names.
        kickoff_at: ISO kickoff time.
        market_probs: Dict from _fetch_market() or MarketCalibrator.fetch_market_probs().
        competition: Competition name.

    Returns:
        Snapshot ID or None on failure.
    """
    if market_probs is None:
        return None

    # Degraded market response (event loop conflict, etc.) — skip saving
    if market_probs.get("degraded"):
        logger.debug("Market consensus degraded — skipping save for %s vs %s",
                     home_team, away_team)
        return None

    import json
    import uuid
    from datetime import datetime, timezone

    snapshot_id = str(uuid.uuid4())

    # Derive match_id from teams if not provided
    if not match_id:
        match_id = f"{home_team}-vs-{away_team}"

    try:
        if not DB_PATH.exists():
            logger.warning("DB not found at %s — consensus not saved", DB_PATH)
            return None

        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("PRAGMA journal_mode=WAL")

        # Ensure table + any new columns exist
        _ensure_consensus_table(conn)
        _migrate_consensus_columns(conn)

        # Build source_snapshot_ids as JSON array with provider info
        provider = market_probs.get("provider", "unknown")
        source_info = json.dumps([{
            "provider": provider,
            "overround": market_probs.get("overround", 0),
            "home_odds": market_probs.get("home_odds"),
            "draw_odds": market_probs.get("draw_odds"),
            "away_odds": market_probs.get("away_odds"),
            "bookmaker": market_probs.get("bookmaker", ""),
        }], ensure_ascii=False)

        # Compute confidence from provider count (single provider)
        overround = market_probs.get("overround", 0)
        confidence = max(0.0, min(1.0, 1.0 - overround))  # lower vig = higher confidence
        if overround > 0.10:
            confidence *= 0.5  # high vig = penalize

        fetch_status = "success"
        provider_names = provider

        conn.execute(
            """INSERT INTO market_consensus_snapshots
               (id, match_id, captured_at, kickoff_at,
                consensus_home, consensus_draw, consensus_away,
                bookmaker_count, provider_count, overround_avg,
                confidence, source_snapshot_ids,
                fetch_status, provider_names, home_team, away_team, competition)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot_id,
                match_id,
                datetime.now(timezone.utc).isoformat(),
                kickoff_at or None,
                round(market_probs.get("home_prob", 0), 6),
                round(market_probs.get("draw_prob", 0), 6),
                round(market_probs.get("away_prob", 0), 6),
                1,  # bookmaker_count
                1,  # provider_count
                round(overround, 6),
                round(confidence, 4),
                source_info,
                fetch_status,
                provider_names,
                home_team or None,
                away_team or None,
                competition or None,
            ),
        )
        conn.commit()
        conn.close()

        logger.info(
            "Market consensus saved: %s — %s vs %s H=%.3f D=%.3f A=%.3f (%s)",
            snapshot_id[:8], home_team, away_team,
            market_probs.get("home_prob", 0), market_probs.get("draw_prob", 0),
            market_probs.get("away_prob", 0), provider,
        )
        return snapshot_id

    except Exception:
        logger.debug("Failed to save market consensus for %s vs %s",
                     home_team, away_team, exc_info=True)
        return None


def _ensure_consensus_table(conn: sqlite3.Connection) -> None:
    """Create market_consensus_snapshots table if not exists."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS market_consensus_snapshots (
            id TEXT PRIMARY KEY,
            match_id TEXT,
            captured_at TIMESTAMP,
            kickoff_at TIMESTAMP,
            consensus_home REAL,
            consensus_draw REAL,
            consensus_away REAL,
            bookmaker_count INTEGER,
            provider_count INTEGER,
            overround_avg REAL,
            confidence REAL,
            source_snapshot_ids TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            fetch_status TEXT,
            provider_names TEXT,
            home_team TEXT,
            away_team TEXT,
            competition TEXT
        )
    """)


def _migrate_consensus_columns(conn: sqlite3.Connection) -> None:
    """Add any missing columns to existing table (idempotent)."""
    new_cols = {
        "fetch_status": "TEXT",
        "provider_names": "TEXT",
        "home_team": "TEXT",
        "away_team": "TEXT",
        "competition": "TEXT",
    }

    existing = {r[1] for r in conn.execute("PRAGMA table_info(market_consensus_snapshots)")}

    for col_name, col_type in new_cols.items():
        if col_name not in existing:
            try:
                conn.execute(
                    f"ALTER TABLE market_consensus_snapshots ADD COLUMN {col_name} {col_type}"
                )
                logger.info("market_consensus_snapshots: added column %s", col_name)
            except sqlite3.OperationalError:
                pass  # already exists
