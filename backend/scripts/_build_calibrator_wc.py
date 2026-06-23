"""
Build calibrator_wc.json from WC-specific match data.

Data sources:
1. 2022 WC group stage backtest records (seeded in postmatch_eval + prediction_runs)
2. 2026 WC completed matches with prediction JSON files + known results

Usage:
  cd backend && python scripts/_build_calibrator_wc.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.calibration import IsotonicCalibrator

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "local_stage2.db"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts"

# ── Known 2026 WC results (from post-match reviews) ──
# Key = prediction JSON file stem, Value = actual result
WC26_RESULTS: dict[str, dict[str, object]] = {
    "Spain_Saudi_Arabia":  {"actual_result": "H"},
    "Argentina_Austria":   {"actual_result": "H"},
    "France_Iraq":         {"actual_result": "H"},
    "Norway_Senegal":      {"actual_result": "H"},
    "Brazil_Haiti":        {"actual_result": "H"},
}


def load_2022_wc_from_db() -> list[dict[str, object]]:
    """Extract 2022 WC seeded calibration samples from DB."""
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    cur.execute("""
        SELECT pe.actual_result,
               pr.home_win_prob, pr.draw_prob, pr.away_win_prob
        FROM postmatch_eval pe
        JOIN prediction_runs pr ON pe.prediction_run_id = pr.id
        WHERE pe.notes LIKE '%2022 World Cup%'
          AND pr.home_win_prob IS NOT NULL
    """)
    rows = cur.fetchall()
    db.close()

    samples: list[dict[str, object]] = []
    for r in rows:
        samples.append({
            "home_win_prob": float(r["home_win_prob"]),
            "draw_prob": float(r["draw_prob"]),
            "away_win_prob": float(r["away_win_prob"]),
            "actual_result": r["actual_result"],
        })
    return samples


def load_2026_wc_from_json() -> list[dict[str, object]]:
    """Extract 2026 WC calibration samples from prediction JSON files with known results."""
    samples: list[dict[str, object]] = []

    for file_stem, result in WC26_RESULTS.items():
        json_path = DATA_DIR / f"_pred_{file_stem}.json"
        if not json_path.exists():
            print(f"  [SKIP] No prediction file: _pred_{file_stem}.json")
            continue

        try:
            with open(json_path, encoding="utf-8") as f:
                pred = json.load(f)
        except Exception as exc:
            print(f"  [ERROR] Failed to read {json_path}: {exc}")
            continue

        # Use pre-calibration "final" layer probabilities
        layers = pred.get("layers", {})
        probs = layers.get("final") or layers.get("post_market") or {}
        if not probs:
            print(f"  [SKIP] {file_stem}: no final/post_market layer")
            continue

        sample = {
            "home_win_prob": float(probs.get("home_win_prob", 0)),
            "draw_prob": float(probs.get("draw_prob", 0)),
            "away_win_prob": float(probs.get("away_win_prob", 0)),
            "actual_result": str(result["actual_result"]),
            "source": f"2026_WC_{file_stem}",
        }
        samples.append(sample)
        print(f"  [OK] {file_stem}: probs=H:{sample['home_win_prob']:.3f} "
              f"D:{sample['draw_prob']:.3f} A:{sample['away_win_prob']:.3f} "
              f"actual={sample['actual_result']}")

    return samples


def main() -> None:
    print("=" * 60)
    print("Building calibrator_wc.json")
    print("=" * 60)

    # ── Load data ──
    print("\n[1/3] Loading WC calibration data...")
    wc22_samples = load_2022_wc_from_db()
    print(f"  2022 WC (seeded): {len(wc22_samples)} samples")

    wc26_samples = load_2026_wc_from_json()
    print(f"  2026 WC (live):   {len(wc26_samples)} samples")

    all_samples = wc22_samples + wc26_samples
    print(f"  Total:            {len(all_samples)} samples")

    if len(all_samples) < 15:
        print(f"  [WARN] Only {len(all_samples)} samples — calibrator will be preliminary")

    # ── Fit via proper API ──
    print(f"\n[2/3] Fitting IsotonicCalibrator via fit_from_db_records()...")
    calibrator = IsotonicCalibrator()
    calibrator.fit_from_db_records(all_samples)

    if not calibrator.is_fitted:
        print(f"  [ERROR] Calibrator not fitted (need >= 20 samples, have {len(all_samples)})")
        sys.exit(1)

    print(f"  is_fitted:        {calibrator.is_fitted}")
    print(f"  training_samples:  {calibrator.training_sample_count}")
    print(f"  ECE:               {calibrator._expected_calibration_error:.4f}")

    # Print calibration curves
    print("\n  Calibration curves:")
    for key in ["home_win", "draw", "away_win"]:
        curve = calibrator.calibrators.get(key)
        if curve and curve.x_thresholds:
            print(f"    {key}: {len(curve.x_thresholds)} bins, "
                  f"x∈[{min(curve.x_thresholds):.3f},{max(curve.x_thresholds):.3f}], "
                  f"y∈[{min(curve.y_thresholds):.3f},{max(curve.y_thresholds):.3f}]")
        else:
            print(f"    {key}: (not fitted)")

    # Test calibration on WC26 samples
    print("\n  Calibration test on 2026 WC samples:")
    for s in wc26_samples:
        raw = {
            "home_win_prob": float(s["home_win_prob"]),
            "draw_prob": float(s["draw_prob"]),
            "away_win_prob": float(s["away_win_prob"]),
        }
        cal = calibrator.calibrate(raw)
        brier_raw = sum((raw[k] - (1.0 if k == f"{s['actual_result'].lower()}_win_prob" else 0.0)) ** 2
                        for k in ["home_win_prob", "draw_prob", "away_win_prob"])
        brier_cal = sum((cal[k] - (1.0 if k == f"{s['actual_result'].lower()}_win_prob" else 0.0)) ** 2
                        for k in ["home_win_prob", "draw_prob", "away_win_prob"])
        print(f"    {s.get('source', '?')}: "
              f"raw=({raw['home_win_prob']:.3f},{raw['draw_prob']:.3f},{raw['away_win_prob']:.3f}) "
              f"→ cal=({cal['home_win_prob']:.3f},{cal['draw_prob']:.3f},{cal['away_win_prob']:.3f}) "
              f"actual={s['actual_result']} "
              f"Brier_raw={brier_raw:.4f} Brier_cal={brier_cal:.4f}")

    # ── Save ──
    print(f"\n[3/3] Saving calibrator_wc.json...")
    output_path = ARTIFACTS_DIR / "calibrator_wc.json"
    calibrator.save(str(output_path))
    print(f"  Saved: {output_path} ({output_path.stat().st_size} bytes)")

    # Verify round-trip
    cal2 = IsotonicCalibrator()
    cal2.load(str(output_path))
    assert cal2.is_fitted, "Round-trip verification failed: is_fitted=False"
    assert cal2.training_sample_count == len(all_samples), \
        f"Round-trip: samples mismatch ({cal2.training_sample_count} != {len(all_samples)})"
    print(f"  Round-trip verified: fitted={cal2.is_fitted}, samples={cal2.training_sample_count}")

    print("\nDone!")


if __name__ == "__main__":
    main()
