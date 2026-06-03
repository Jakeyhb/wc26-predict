#!/usr/bin/env python3
"""Interactive CLI for manually entering a news signal without an article.

Walks through each field interactively with validation before inserting
into the news_signals table with review_status='PENDING'.

Usage:
    python scripts/enter_manual_signal.py
"""
from __future__ import annotations

import re
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "data" / "local_stage2.db"

SIGNAL_TYPES = [
    ("injury", "Player injury - physical ailment keeping player out"),
    ("suspension", "Player suspension - yellow/red card accumulation, ban"),
    ("lineup_change", "Lineup change - confirmed XI rotation or surprise start"),
    ("tactical_shift", "Tactical shift - formation change, strategy pivot"),
    ("schedule_pressure", "Schedule pressure - congested fixture, short rest"),
    ("travel_fatigue", "Travel fatigue - long-haul travel, time zone changes"),
    ("form_change", "Form change - recent performance trend, hot/cold streak"),
    ("manager_change", "Manager change - sacking, resignation, new appointment"),
    ("morale_event", "Morale event - off-field distraction, team spirit shift"),
    ("weather_impact", "Weather impact - extreme conditions affecting play"),
    ("other", "Other - signal that doesn't fit above categories"),
]

IMPACT_DIRECTIONS = [
    "positive",
    "negative",
    "neutral",
    "unknown",
]

URL_PATTERN = re.compile(
    r"^https?://"  # http:// or https://
    r"([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}"  # domain
    r"(:\d+)?"  # optional port
    r"(/.*)?$",  # optional path
    re.IGNORECASE,
)


def get_db() -> sqlite3.Connection:
    """Open a connection to the local SQLite database."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def fmt(val, default: str = "N/A") -> str:
    if val is None:
        return default
    return str(val)


# ── Prompt helpers ──────────────────────────────────────────────


def prompt_menu(title: str, options: list[tuple[str, str]]) -> str:
    """Display a numbered menu and return the chosen value string."""
    print(f"\n  {title}")
    print(f"  {'-' * 60}")
    for i, (value, desc) in enumerate(options, start=1):
        print(f"  {i:>2}. {value:<20s} - {desc}")
    while True:
        raw = input(f"\n  Enter number (1-{len(options)}): ").strip()
        try:
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1][0]
        except ValueError:
            pass
        print(f"  Invalid. Please enter a number 1-{len(options)}.")


def prompt_nonempty(prompt_text: str, field_name: str) -> str:
    """Prompt for a non-empty string value."""
    while True:
        val = input(f"  {prompt_text}: ").strip()
        if val:
            return val
        print(f"  {field_name} cannot be empty.")


def prompt_optional(prompt_text: str) -> str | None:
    """Prompt for an optional string; returns None if left blank."""
    val = input(f"  {prompt_text} (optional, press Enter to skip): ").strip()
    return val if val else None


def prompt_float(prompt_text: str, lo: float, hi: float) -> float:
    """Prompt for a float in [lo, hi]."""
    while True:
        raw = input(f"  {prompt_text} ({lo}-{hi}): ").strip()
        try:
            val = float(raw)
            if lo <= val <= hi:
                return val
        except ValueError:
            pass
        print(f"  Invalid. Must be a number between {lo} and {hi}.")


def prompt_url() -> str:
    """Prompt for a valid URL (must start with http:// or https://)."""
    while True:
        url = input("  Source URL (must be a real URL starting with http:// or https://): ").strip()
        if URL_PATTERN.match(url):
            return url
        print("  Invalid URL. Must start with http:// or https:// and be a valid URL.")


def prompt_yes_no(prompt_text: str, default: str = "n") -> bool:
    """Prompt a yes/no question, return bool."""
    hint = f"y/N" if default.lower() == "n" else "Y/n"
    raw = input(f"  {prompt_text} ({hint}): ").strip().lower()
    if not raw:
        return default.lower() == "y"
    return raw in ("y", "yes")


# ── Team lookup ─────────────────────────────────────────────────


def lookup_team(conn: sqlite3.Connection, name: str) -> tuple[str | None, str | None]:
    """Look up a team by name, name_zh, or alias.

    Returns (team_id, team_name) or (None, None) if not found.
    """
    # Exact match by name
    row = conn.execute(
        "SELECT id, name FROM teams WHERE name = ?", (name,)
    ).fetchone()
    if row:
        return row["id"], row["name"]

    # Exact match by name_zh
    row = conn.execute(
        "SELECT id, name FROM teams WHERE name_zh = ?", (name,)
    ).fetchone()
    if row:
        return row["id"], row["name"]

    # LIKE match by name
    row = conn.execute(
        "SELECT id, name FROM teams WHERE name LIKE ?", (f"%{name}%",)
    ).fetchone()
    if row:
        return row["id"], row["name"]

    # LIKE match by name_zh
    row = conn.execute(
        "SELECT id, name FROM teams WHERE name_zh LIKE ?", (f"%{name}%",)
    ).fetchone()
    if row:
        return row["id"], row["name"]

    # Alias lookup (normalized)
    alias_row = conn.execute(
        """
        SELECT t.id, t.name FROM teams t
        JOIN team_aliases ta ON ta.team_id = t.id
        WHERE ta.alias_normalized = ?
        """,
        (name.lower().strip(),),
    ).fetchone()
    if alias_row:
        return alias_row["id"], alias_row["name"]

    # Alias LIKE lookup
    alias_row = conn.execute(
        """
        SELECT t.id, t.name FROM teams t
        JOIN team_aliases ta ON ta.team_id = t.id
        WHERE ta.alias LIKE ?
        """,
        (f"%{name}%",),
    ).fetchone()
    if alias_row:
        return alias_row["id"], alias_row["name"]

    return None, None


def suggest_teams(conn: sqlite3.Connection, partial: str) -> list[str]:
    """Return matching team names for suggestion."""
    rows = conn.execute(
        "SELECT name FROM teams WHERE name LIKE ? ORDER BY name LIMIT 10",
        (f"%{partial}%",),
    ).fetchall()
    return [r["name"] for r in rows]


# ── Validation ──────────────────────────────────────────────────


def is_valid_uuid_hex(s: str) -> bool:
    """Check if string is a valid 32-char hex UUID (without hyphens)."""
    if len(s) == 36 and s.count("-") == 4:
        s = s.replace("-", "")
    if len(s) != 32:
        return False
    try:
        int(s, 16)
        return True
    except ValueError:
        return False


def is_valid_iso_datetime(s: str) -> bool:
    """Check if string is a valid ISO 8601 datetime."""
    try:
        datetime.fromisoformat(s)
        return True
    except (ValueError, TypeError):
        return False


# ── Main flow ───────────────────────────────────────────────────


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
        sys.exit(1)

    conn = get_db()

    print()
    print("=" * 60)
    print("  WC26 Predict - Manual Signal Entry")
    print("=" * 60)

    # ── 1. signal_type ───────────────────────────────────────────
    signal_type = prompt_menu(
        "Select signal type:",
        SIGNAL_TYPES,
    )

    # ── 2. impact_direction ──────────────────────────────────────
    impact_direction = prompt_menu(
        "Select impact direction:",
        [(d, "") for d in IMPACT_DIRECTIONS],
    )

    # ── 3. team_name → team_id ──────────────────────────────────
    team_name_raw = prompt_nonempty("Team name", "Team name")
    team_id, resolved_team_name = lookup_team(conn, team_name_raw)
    if team_id:
        print(f"  -> Resolved to: {resolved_team_name} (ID: {team_id})")
    else:
        suggestions = suggest_teams(conn, team_name_raw)
        if suggestions:
            print(f"  Team '{team_name_raw}' not found. Did you mean:")
            for s in suggestions:
                print(f"    - {s}")
        else:
            print(f"  Team '{team_name_raw}' not found in database.")

        confirm = prompt_yes_no("Proceed without team mapping (team_id will be NULL)?", default="n")
        if not confirm:
            # Offer to let the user retry
            retry = prompt_yes_no("Re-enter team name?", default="y")
            if retry:
                team_name_raw = prompt_nonempty("Team name", "Team name")
                team_id, resolved_team_name = lookup_team(conn, team_name_raw)
                if team_id:
                    print(f"  -> Resolved to: {resolved_team_name} (ID: {team_id})")
                else:
                    print(f"  Proceeding with team_id = NULL.")
            else:
                print(f"  Proceeding with team_id = NULL.")

    # ── 4. confidence ──────────────────────────────────────────
    confidence = prompt_float("Confidence", 0.0, 1.0)

    # ── 5. source_reliability ─────────────────────────────────
    source_reliability = prompt_float("Source reliability", 0.0, 1.0)

    # ── 6. source_url (stored in evidence_snippet) ────────────
    source_url = prompt_url()

    # ── 7. player_name (optional) ─────────────────────────────
    player_name = prompt_optional("Player name")

    # ── 8. claim (optional) ───────────────────────────────────
    claim = prompt_optional("Claim / headline")

    # ── 9. evidence_snippet (optional, merged with source_url) ─
    evidence_snippet = prompt_optional("Evidence snippet")
    final_evidence = f"[Source: {source_url}]"
    if evidence_snippet:
        final_evidence += f" {evidence_snippet}"

    # ── 10. match_id (optional UUID validation) ──────────────
    match_id = None
    raw_match_id = prompt_optional("Match ID (32-char hex or 36-char with hyphens)")
    if raw_match_id:
        cleaned = raw_match_id.replace("-", "")
        if is_valid_uuid_hex(cleaned):
            match_id = cleaned
        else:
            print("  Warning: Not a valid 32-char hex UUID. Setting match_id = NULL.")

    # ── 11. effective_until (optional ISO datetime) ──────────
    effective_until = None
    raw_eff = prompt_optional("Effective until (ISO 8601 datetime, e.g. 2026-07-15T23:59:59)")
    if raw_eff:
        if is_valid_iso_datetime(raw_eff):
            # Ensure format matches DB (YYYY-MM-DD HH:MM:SS)
            try:
                dt = datetime.fromisoformat(raw_eff)
                effective_until = dt.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                print("  Warning: Invalid datetime format. Setting effective_until = NULL.")
        else:
            print("  Warning: Invalid datetime format. Setting effective_until = NULL.")

    # ── 12. summary_zh (required) ────────────────────────────
    summary_zh = prompt_nonempty("Summary (Chinese, brief)", "Summary (Chinese)")

    # ── Generate ID ──────────────────────────────────────────
    signal_id = uuid.uuid4().hex  # 32 hex chars

    # ── Confirmation ─────────────────────────────────────────
    print()
    print("  " + "=" * 60)
    print("  Review before inserting:")
    print("  " + "=" * 60)
    print(f"  ID:               {signal_id}")
    print(f"  Type:             {signal_type}")
    print(f"  Impact:           {impact_direction}")
    print(f"  Team:             {resolved_team_name or team_name_raw if not team_id else resolved_team_name}")
    print(f"  Team ID:          {team_id or 'NULL'}")
    print(f"  Player:           {player_name or 'NULL'}")
    print(f"  Confidence:       {confidence:.2f}")
    print(f"  Source Reliab.:   {source_reliability:.2f}")
    print(f"  Source URL:       {source_url}")
    print(f"  Claim:            {claim or 'NULL'}")
    print(f"  Evidence:         {final_evidence[:120]}")
    print(f"  Match ID:         {match_id or 'NULL'}")
    print(f"  Effective Until:  {effective_until or 'NULL'}")
    print(f"  Summary (zh):     {summary_zh}")

    proceed = prompt_yes_no("\nInsert this signal?", default="y")
    if not proceed:
        print("\n  Insertion cancelled.")
        conn.close()
        return

    # ── Insert ───────────────────────────────────────────────
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn.execute(
            """
            INSERT INTO news_signals (
                id, article_id, match_id, team_id,
                signal_type, impact_direction, confidence, source_reliability,
                key_players, summary_zh,
                player_name, claim, evidence_snippet,
                normalized_availability, expected_minutes_delta,
                effective_until, conflict_group_id, contradiction_risk,
                review_status, review_notes, reviewed_by, reviewed_at,
                enters_model, created_at
            ) VALUES (
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?
            )
            """,
            (
                signal_id,
                "00000000000000000000000000000000",  # dummy article_id (all zeros)
                match_id,
                team_id,
                signal_type,
                impact_direction,
                confidence,
                source_reliability,
                "[]",  # key_players JSON
                summary_zh,
                player_name,
                claim,
                final_evidence,
                None,  # normalized_availability
                None,  # expected_minutes_delta
                effective_until,
                None,  # conflict_group_id
                None,  # contradiction_risk
                "PENDING",
                None,  # review_notes
                None,  # reviewed_by
                None,  # reviewed_at
                0,  # enters_model
                now,  # created_at
            ),
        )
        conn.commit()
        print(f"\n  Signal inserted successfully! ({signal_id})")
        print("  Status: PENDING (ready for review via review_signals.py)")
    except sqlite3.Error as e:
        print(f"\n  Error inserting signal: {e}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
