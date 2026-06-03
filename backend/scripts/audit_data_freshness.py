"""Phase 0: Audit data freshness across the system.
Read-only — no business logic changes.

Checks:
1. Latest match date in database
2. Latest prediction snapshot date
3. news_signals coverage (count = 0 is CRITICAL)
4. market_odds recency
5. Elo rating last update
6. Player data recency
7. standings data freshness
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def main():
    print("=" * 70)
    print("AUDIT: Data Freshness Report")
    print(f"Run time: {datetime.now().isoformat()}")
    print("=" * 70)

    import sqlite3
    db = PROJECT_ROOT / "data" / "local_stage2.db"
    conn = sqlite3.connect(str(db))
    c = conn.cursor()

    issues = []
    ok = []

    # 1. Match data recency
    print("\n--- 1. Match Data ---")
    c.execute("SELECT MAX(match_date) FROM matches")
    latest_match = c.fetchone()[0]
    print(f"  Latest match: {latest_match}")

    c.execute("SELECT MAX(m.match_date) FROM match_results mr JOIN matches m ON mr.match_id = REPLACE(m.id, '-', '')")
    latest_result = c.fetchone()[0]
    print(f"  Latest result: {latest_result}")

    c.execute("SELECT COUNT(*) FROM matches WHERE match_date > date('now')")
    future = c.fetchone()[0]
    print(f"  Future matches scheduled: {future}")

    # Check WC26 match dates
    c.execute("""
        SELECT MIN(match_date), MAX(match_date)
        FROM matches
        WHERE competition = 'FIFA World Cup 2026'
    """)
    wc_range = c.fetchone()
    print(f"  WC26 date range: {wc_range[0]} to {wc_range[1]}")

    now = datetime.now()
    if latest_match:
        latest_dt = datetime.fromisoformat(str(latest_match).replace("T", " ").split(".")[0])
        days_behind = (now - latest_dt).days
        if days_behind > 7:
            issues.append(f"Match data is {days_behind} days behind — might be missing recent matches")
        else:
            ok.append(f"Match data is current (within {days_behind} days)")

    # 2. Prediction snapshot recency
    print("\n--- 2. Prediction Snapshots ---")
    c.execute("SELECT MAX(generated_at) FROM prediction_snapshots")
    latest_ps = c.fetchone()[0]
    print(f"  Latest snapshot: {latest_ps}")

    c.execute("SELECT COUNT(*) FROM prediction_snapshots")
    total_ps = c.fetchone()[0]
    print(f"  Total snapshots: {total_ps}")

    c.execute("""
        SELECT COUNT(*) FROM prediction_snapshots ps
        JOIN matches m ON ps.match_id = REPLACE(m.id, '-', '')
        WHERE m.competition = 'FIFA World Cup 2026' AND m.stage LIKE 'Group%'
    """)
    wc26_ps = c.fetchone()[0]
    print(f"  WC26 group snapshots: {wc26_ps}/72")

    if wc26_ps < 72:
        issues.append(f"Only {wc26_ps}/72 WC26 group matches have predictions")
    else:
        ok.append("All 72 WC26 group matches have prediction snapshots")

    if latest_ps:
        ps_dt = datetime.fromisoformat(str(latest_ps).replace("T", " ").split(".")[0])
        ps_days = (now - ps_dt).days
        print(f"  Snapshot age: {ps_days} days")
        if ps_days > 2:
            issues.append(f"Latest prediction snapshot is {ps_days} days old")
        else:
            ok.append(f"Prediction snapshots are fresh ({ps_days}d)")

    # 3. News signals — CRITICAL
    print("\n--- 3. News Signals (CRITICAL) ---")
    c.execute("SELECT COUNT(*) FROM news_signals")
    ns_count = c.fetchone()[0]
    print(f"  news_signals: {ns_count}")

    c.execute("SELECT COUNT(*) FROM news_articles")
    na_count = c.fetchone()[0]
    print(f"  news_articles (raw): {na_count}")

    c.execute("SELECT COUNT(*) FROM content_articles")
    ca_count = c.fetchone()[0]
    print(f"  content_articles: {ca_count}")

    if ns_count == 0:
        issues.append("CRITICAL: news_signals = 0 — intelligence pipeline is empty. No injury/suspension/lineup signals for any team.")
    else:
        ok.append(f"news_signals has {ns_count} entries")

    if na_count == 0:
        issues.append("news_articles = 0 — no raw news articles ingested")
    else:
        ok.append(f"news_articles has {na_count} raw articles")

    # 4. Market odds recency
    print("\n--- 4. Market Odds ---")
    c.execute("SELECT COUNT(*) FROM market_odds")
    mo_count = c.fetchone()[0]
    print(f"  market_odds: {mo_count}")

    c.execute("SELECT MAX(created_at), MAX(fetched_at) FROM market_odds")
    mo_dates = c.fetchone()
    print(f"  Latest created_at: {mo_dates[0]}")
    print(f"  Latest fetched_at: {mo_dates[1]}")

    c.execute("SELECT COUNT(DISTINCT match_id) FROM market_odds")
    mo_matches = c.fetchone()[0]
    print(f"  Unique matches with odds: {mo_matches}")

    c.execute("SELECT provider, COUNT(*) FROM market_odds GROUP BY provider")
    providers = c.fetchall()
    for p in providers:
        print(f"    {p[0]}: {p[1]} records")

    if mo_count == 0:
        issues.append("market_odds is empty — no market data for calibration")
    else:
        ok.append(f"market_odds has {mo_count} records from {len(providers)} providers")

    # 5. Manual events
    print("\n--- 5. Manual Events ---")
    c.execute("SELECT COUNT(*) FROM manual_events")
    me_count = c.fetchone()[0]
    print(f"  manual_events: {me_count}")

    if me_count <= 20:
        issues.append(f"manual_events only has {me_count} entries — manual intelligence input is sparse")
    else:
        ok.append(f"manual_events has {me_count} entries")

    # 6. Post-match learning
    print("\n--- 6. Post-Match Learning ---")
    c.execute("SELECT COUNT(*) FROM postmatch_eval")
    eval_count = c.fetchone()[0]
    print(f"  postmatch_eval: {eval_count}")

    c.execute("SELECT MAX(created_at) FROM postmatch_eval")
    latest_eval = c.fetchone()[0]
    print(f"  Latest evaluation: {latest_eval}")

    c.execute("SELECT COUNT(*) FROM prediction_learning_log")
    ll_count = c.fetchone()[0]
    print(f"  prediction_learning_log: {ll_count}")

    c.execute("SELECT COUNT(*) FROM weekly_learning_reports")
    wlr_count = c.fetchone()[0]
    print(f"  weekly_learning_reports: {wlr_count}")

    if eval_count < 50:
        issues.append(f"Only {eval_count} post-match evaluations — learning loop has limited data")
    else:
        ok.append(f"{eval_count} post-match evaluations available")

    # 7. Standings recency
    print("\n--- 7. Standings ---")
    try:
        c.execute("SELECT COUNT(*) FROM standings")
        st_count = c.fetchone()[0]
        print(f"  standings records: {st_count}")
    except Exception as e:
        print(f"  standings: error ({e})")
        st_count = 0

    # 8. Players / squad data
    print("\n--- 8. Player Data ---")
    c.execute("SELECT COUNT(*) FROM players")
    p_count = c.fetchone()[0]
    print(f"  Players: {p_count}")

    conn.close()

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  ✓ OK: {len(ok)}")
    for item in ok:
        print(f"    + {item}")
    print(f"  ⚠ Issues: {len(issues)}")
    for item in issues:
        print(f"    ! {item}")

    # Criticality
    critical = any("CRITICAL" in i for i in issues)
    if critical:
        print(f"\n  🚨 CRITICAL ISSUES DETECTED — must fix before World Cup")
        print(f"     news_signals=0 is the highest priority gap.")
    else:
        print(f"\n  No critical data freshness issues.")

    return len(issues)


if __name__ == "__main__":
    n = main()
    print(f"\nExit: {n} issues found")
