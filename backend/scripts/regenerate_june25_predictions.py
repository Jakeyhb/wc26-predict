#!/usr/bin/env python3
"""regenerate_june25_predictions.py — V4.1.1: regenerate predictions for
June 24-25 WC matches using verified component pipeline.

Usage:
    python scripts/regenerate_june25_predictions.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import sqlite3
from app.services.prediction_pipeline import PredictionPipeline
from app.services.tabular_match_model import fuse_outcome_probabilities
from app.services.elo_ratings import fuse_elo_probabilities
from app.services.pi_ratings import fuse_pi_probabilities
from app.services.weibull_model import fuse_weibull_probs
from app.services.weights import get_weight_config
from app.services.market.sync_provider import fetch_market_consensus_sync
from app.version import VERSION

DB_PATH = BACKEND_DIR / "data" / "local_stage2.db"

MATCH_DEFS = [
    ("Switzerland", "Canada", "2026-06-24T19:00:00"),
    ("Bosnia and Herzegovina", "Qatar", "2026-06-24T19:00:00"),
    ("Scotland", "Brazil", "2026-06-24T22:00:00"),
    ("Morocco", "Haiti", "2026-06-24T22:00:00"),
    ("Czech Republic", "Mexico", "2026-06-25T01:00:00"),
    ("South Africa", "South Korea", "2026-06-25T01:00:00"),
    ("Ecuador", "Germany", "2026-06-25T20:00:00"),
    ("Curacao", "Ivory Coast", "2026-06-25T20:00:00"),
    ("Tunisia", "Netherlands", "2026-06-25T23:00:00"),
    ("Japan", "Sweden", "2026-06-25T23:00:00"),
]

COMPETITION = "FIFA World Cup 2026"
STAGE = "Group Stage"


def _p3(d: dict) -> dict[str, float]:
    """Extract only home_win_prob/draw_prob/away_win_prob as float from any dict."""
    return {
        "home_win_prob": float(d.get("home_win_prob", d.get("home", 0.33))),
        "draw_prob": float(d.get("draw_prob", d.get("draw", 0.34))),
        "away_win_prob": float(d.get("away_win_prob", d.get("away", 0.33))),
    }


def _fav(d: dict[str, float]) -> str:
    """Return the key with the highest value."""
    return max(d, key=d.get)


def _normalize(d: dict[str, float]) -> dict[str, float]:
    t = d["home_win_prob"] + d["draw_prob"] + d["away_win_prob"]
    if t > 0:
        d["home_win_prob"] /= t
        d["draw_prob"] /= t
        d["away_win_prob"] /= t
    return d


def predict_one(home: str, away: str, pipeline) -> dict:
    """Run the full component pipeline and return prediction dict."""
    wc = get_weight_config(COMPETITION, STAGE)
    md = pipeline._training_df["match_date"].max().to_pydatetime()

    # 1. DC
    dc = _p3(pipeline._dc.predict_match(home, away, is_neutral_venue=True))
    fused = dict(dc)

    # 2. Enhancer
    has_enh = getattr(pipeline, "_enhancer", None) is not None
    if has_enh:
        enh = _p3(pipeline._enhancer.predict_match(
            home_team=home, away_team=away, match_date=md,
            competition_weight=1.0, is_neutral_venue=True,
            training_df=pipeline._training_df,
        ))
        max_div = max(abs(dc[k] - enh[k]) for k in dc) * 100
        conflict = (_fav(dc) != _fav(enh))

        if max_div > 20 and conflict:
            fused = fuse_outcome_probabilities(fused, enh, base_weight=wc.dc)
        elif max_div > 20:
            shift = min(0.15, (max_div - 20) * 0.015)
            dc_w = max(0.30, wc.dc - shift)
            ew = 1.0 - dc_w
            fused = _normalize({
                "home_win_prob": dc["home_win_prob"] * dc_w + enh["home_win_prob"] * ew,
                "draw_prob": dc["draw_prob"] * dc_w + enh["draw_prob"] * ew,
                "away_win_prob": dc["away_win_prob"] * dc_w + enh["away_win_prob"] * ew,
            })
        else:
            fused = fuse_outcome_probabilities(fused, enh, base_weight=wc.dc)

    # 3. Weibull
    has_wb = (getattr(pipeline, "_weibull", None) is not None
              and getattr(pipeline._weibull, "_fitted", False))
    if has_wb:
        try:
            wb_pred = pipeline._weibull.predict(home, away, True)
            if wb_pred:
                fused = fuse_weibull_probs(fused, _p3(wb_pred), wb_weight=wc.weibull)
        except Exception:
            pass

    # 4. Elo
    if getattr(pipeline, "_elo", None) is not None:
        elo = pipeline._elo.predict(
            home, away, is_neutral=True,
            competition_weight=1.0, competition=COMPETITION,
        )
        fused = fuse_elo_probabilities(fused, elo, elo_weight=wc.elo)

    # 5. Pi
    if getattr(pipeline, "_pi", None) is not None:
        try:
            pi = _p3(pipeline._pi.predict(home, away, True))
            fused = fuse_pi_probabilities(fused, pi, pi_weight=wc.pi)
        except Exception:
            pass

    # 6. Market
    try:
        mkt = fetch_market_consensus_sync(home, away, COMPETITION, timeout=8.0)
        if mkt and not mkt.get("degraded"):
            div = max(
                abs(fused["home_win_prob"] - mkt["home_prob"]),
                abs(fused["draw_prob"] - mkt["draw_prob"]),
                abs(fused["away_win_prob"] - mkt["away_prob"]),
            )
            mw = wc.market_max
            if div > 0.15:
                mw = min(0.50, wc.market_max + min(0.20, (div - 0.15) * 1.0))
            fused = _normalize({
                "home_win_prob": fused["home_win_prob"] * (1 - mw) + mkt["home_prob"] * mw,
                "draw_prob": fused["draw_prob"] * (1 - mw) + mkt["draw_prob"] * mw,
                "away_win_prob": fused["away_win_prob"] * (1 - mw) + mkt["away_prob"] * mw,
            })
    except Exception:
        pass

    # 7. Calibration — SKIPPED (only 28 WC samples, causes probability collapse)
    # When WC calibrator reaches 50+ diverse samples, re-enable.

    return _normalize(fused)


def find_match_id(conn, home, away):
    row = conn.execute(
        "SELECT m.id FROM matches m JOIN teams ht ON m.home_team_id=ht.id "
        "JOIN teams at ON m.away_team_id=at.id "
        "WHERE ht.name=? AND at.name=?", (home, away)
    ).fetchone()
    return row[0] if row else None


def insert_run(conn, match_id, prob_h, prob_d, prob_a):
    rid = uuid.uuid4().hex[:32]
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO prediction_runs
        (id, match_id, run_type, model_version, as_of_time,
         home_win_prob, draw_prob, away_win_prob,
         home_xg, away_xg, score_matrix, top3_scores,
         confidence_score, risk_tags, approved_signals,
         input_feature_snapshot, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (rid, match_id, "V4_MANUAL", VERSION, now,
         prob_h, prob_d, prob_a,
         1.0, 1.0, "[]", "[]",
         0.5, "[]", "[]",
         json.dumps({"generated_by": "regenerate_june25", "version": VERSION}),
         now),
    )
    conn.commit()
    return rid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mode", default="full", choices=["standard", "full"])
    args = parser.parse_args()

    print(f"{'='*60}")
    print(f"  V4.1.1 Prediction Regeneration — June 24-25 WC R3")
    print(f"  Version: {VERSION}  Mode: {args.mode}  Dry-run: {args.dry_run}")
    print(f"{'='*60}")

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")

    print("\n[1] Loading pipeline...")
    pipeline = PredictionPipeline.from_artifacts(mode=args.mode)

    print(f"\n[2] Processing {len(MATCH_DEFS)} matches...")
    created = 0

    for i, (home, away, date_str) in enumerate(MATCH_DEFS):
        print(f"\n[{i+1}] {home} vs {away}")
        mid = find_match_id(conn, home, away)
        if not mid:
            print("  SKIP: match not found in DB")
            continue

        # Delete old
        conn.execute("DELETE FROM prediction_runs WHERE match_id=?", (mid,))
        conn.commit()

        if args.dry_run:
            print("  [DRY-RUN]")
            continue

        try:
            fused = predict_one(home, away, pipeline)
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            continue

        h, d, a = fused["home_win_prob"], fused["draw_prob"], fused["away_win_prob"]
        fav = _fav(fused)
        insert_run(conn, mid, h, d, a)
        created += 1
        print(f"  H={h:.4f} D={d:.4f} A={a:.4f} → {fav} wins")

    print(f"\n{'='*60}")
    print(f"  Done: {created}/{len(MATCH_DEFS)} predictions regenerated")
    print(f"{'='*60}")
    conn.close()


if __name__ == "__main__":
    main()
