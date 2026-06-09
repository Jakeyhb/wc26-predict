"""backtest_report.py — Unified backtest & calibration report (Ticket 9).

One script, three modes:

    python scripts/backtest_report.py walk-forward [--quick|--full|--limit N]
    python scripts/backtest_report.py evaluate [--output report.md]
    python scripts/backtest_report.py calibrate [--output report.md]

Reuses existing walk-forward logic from backtest_models.py and calibration
from app.services.calibration.py. Produces a comprehensive Markdown report
with Brier/LogLoss/RPS/ECE, component comparison, calibration reliability
table, and before/after weight evidence.

Reports written to: backend/reports/backtest_YYYYMMDD_HHMMSS.md (gitignored)
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
REPORTS_DIR = BACKEND_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import numpy as np
import pandas as pd

# Import metric functions from existing backtest script
from scripts.backtest_models import (
    brier_score,
    log_loss_score,
    ranked_probability_score,
    calibration_ece,
    fuse_ensemble,
    load_data,
    run_walk_forward_backtest,
    compute_component_metrics,
    DB_PATH,
)

DB_PATH_SQLITE = DB_PATH


# ============================================================================
# Thresholds
# ============================================================================

THRESHOLDS = {
    "brier": (0.225, "lower=better; <0.20 excellent, <0.22 good, >0.25 poor"),
    "log_loss": (0.700, "lower=better; <0.65 excellent, <0.70 good, >0.75 poor"),
    "rps": (0.150, "lower=better; <0.14 excellent, <0.15 good, >0.17 poor"),
    "ece": (0.100, "lower=better; <0.05 excellent, <0.10 acceptable, >0.15 poor"),
    "directional": (0.50, "higher=better; fraction of highest-prob outcome being correct"),
}

STATUS_ICONS = {
    "pass": "✅",
    "warn": "⚠️",
    "fail": "❌",
}


def _status(value: float, threshold: float, lower_is_better: bool = True) -> str:
    """Return pass/warn/fail icon based on threshold."""
    if lower_is_better:
        if value <= threshold * 0.7:
            return STATUS_ICONS["pass"]
        elif value <= threshold:
            return STATUS_ICONS["warn"]
        return STATUS_ICONS["fail"]
    else:
        if value >= threshold * 1.15:
            return STATUS_ICONS["pass"]
        elif value >= threshold:
            return STATUS_ICONS["warn"]
        return STATUS_ICONS["fail"]


# ============================================================================
# Report writer
# ============================================================================

def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _md_hdr(level: int, text: str) -> str:
    return f"{'#' * level} {text}"


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join("---" for _ in headers) + "|")
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def _fmt_pct(v: float) -> str:
    return f"{v:.1%}"


def _fmt_float(v: float, decimals: int = 4) -> str:
    return f"{v:.{decimals}f}"


def write_report(sections: list[str], output_path: Path | None = None) -> Path:
    """Write report sections to a Markdown file."""
    if output_path is None:
        output_path = REPORTS_DIR / f"backtest_{_timestamp()}.md"

    header = f"""# WC26 Predict — Backtest & Calibration Report

**Generated**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
**Code Version**: TBD
**DB**: {DB_PATH_SQLITE}

---

"""
    full = header + "\n\n".join(sections)
    output_path.write_text(full, encoding="utf-8")
    print(f"\nReport written to: {output_path}")
    return output_path


# ============================================================================
# Mode 1: Walk-Forward Backtest
# ============================================================================


def _run_walk_forward(
    *,
    quick: bool = False,
    full: bool = False,
    limit: int | None = None,
    team_type: str = "national",
    dc_weight: float = 0.50,
    elo_weight: float = 0.05,
    pi_weight: float = 0.05,
) -> tuple[list[dict], dict]:
    """Execute walk-forward backtest and return raw results + metrics."""
    if quick:
        initial_window = 100
        step = 1
        max_rows = 200
        label = "quick"
    elif full:
        initial_window = 500
        step = 3
        max_rows = None
        label = "full"
    elif limit is not None:
        initial_window = min(300, max(50, limit // 3))
        step = max(1, limit // 300)
        max_rows = limit
        label = f"limit-{limit}"
    else:
        initial_window = 300
        step = 1
        max_rows = 500
        label = "default"

    print(f"\n{'='*60}")
    print(f"  Walk-Forward Backtest [{label}]")
    print(f"  initial_window={initial_window}  step={step}  max_rows={max_rows or 'all'}")
    print(f"  fusion: DC={dc_weight}  Elo={elo_weight}  Pi={pi_weight}")
    print(f"{'='*60}")

    df = load_data(team_type=team_type, max_rows=max_rows)
    min_req = initial_window + 1
    if len(df) < min_req:
        print(f"ERROR: {len(df)} matches < {min_req} required")
        return [], {}

    print(f"\nRunning {len(df) - initial_window} predictions...")
    results = run_walk_forward_backtest(
        df,
        initial_window=initial_window,
        step=step,
        dc_weight=dc_weight,
        elo_weight=elo_weight,
        pi_weight=pi_weight,
    )
    metrics = compute_component_metrics(results)

    return results, metrics


def _render_wf_report(
    results: list[dict],
    metrics: dict,
    config: dict,
) -> str:
    """Render walk-forward sections of the report."""
    sections: list[str] = []

    # ── 1. Summary ──
    fused = metrics.get("fused", {})
    dc_m = metrics.get("dc", {})
    enh_m = metrics.get("enhancer", {})
    elo_m = metrics.get("elo", {})
    pi_m = metrics.get("pi_rating", {})

    n_preds = len(results)
    directional_correct = 0
    for r in results:
        actual = r["actual_label"]
        probs = r["fused_probs"]
        predicted = int(np.argmax(probs))
        if predicted == actual:
            directional_correct += 1
    dir_acc = directional_correct / n_preds if n_preds else 0

    sections.append(_md_hdr(1, "Summary"))
    sections.append(
        _md_table(
            ["Metric", "Value", "Threshold", "Status"],
            [
                _metric_cell("Brier Score", fused.get("brier", 0), "brier"),
                _metric_cell("Log Loss", fused.get("log_loss", 0), "log_loss"),
                _metric_cell("RPS", fused.get("rps", 0), "rps"),
                _metric_cell("ECE", fused.get("calibration_ece", 0), "ece"),
                _metric_cell("Directional Accuracy", dir_acc, "directional"),
            ],
        )
    )
    sections.append(f"\n**Config**: {json.dumps(config, indent=2)}")

    # ── 2. Walk-Forward Detail ──
    sections.append(_md_hdr(2, "Walk-Forward Backtest"))
    sections.append(f"{n_preds} predictions, {config.get('initial_window', '?')} initial window, step={config.get('step', '?')}")

    sections.append(_md_hdr(3, "Component Performance"))
    sections.append(
        _md_table(
            ["Component", "Brier ↓", "LogLoss ↓", "RPS ↓", "ECE ↓", "Directional"],
            [
                _component_row("DC only", dc_m, results, "dc"),
                _component_row("Enhancer only", enh_m, results, "enh"),
                _component_row("Elo only", elo_m, results, "elo"),
                _component_row("Pi only", pi_m, results, "pi"),
                _component_row("**Fused (all)**", fused, results, "fused"),
            ],
        )
    )

    # ── 3. Component contribution (marginal Δ Brier) ──
    sections.append(_md_hdr(3, "Marginal Contribution (Δ Brier vs DC-only)"))
    base_brier = dc_m.get("brier", 0)
    contrib_rows = []
    for label, key in [("+Enhancer", "enhancer"), ("+Elo", "elo"), ("+Pi", "pi_rating")]:
        val = metrics.get(key, {}).get("brier", 0)
        delta = val - base_brier
        icon = "✅" if delta < 0 else "❌"
        contrib_rows.append([label, _fmt_float(val), _fmt_float(base_brier), f"{delta:+.4f}", icon])
    # Fused
    fused_brier = fused.get("brier", 0)
    fused_delta = fused_brier - base_brier
    contrib_rows.append(["**Fused**", _fmt_float(fused_brier), _fmt_float(base_brier), f"{fused_delta:+.4f}", "✅" if fused_delta < 0 else "❌"])
    sections.append(
        _md_table(
            ["Component", "Brier", "DC Brier", "Δ", ""],
            contrib_rows,
        )
    )

    return "\n\n".join(sections)


def _component_row(label: str, m: dict, results: list[dict], key: str) -> list[str]:
    """Build a table row for a single component."""
    n = len(results)
    if n == 0:
        return [label, "-", "-", "-", "-", "-"]
    correct = sum(
        1 for r in results
        if int(np.argmax(r[f"{key}_probs"])) == r["actual_label"]
    )
    dir_acc = correct / n
    return [
        label,
        _fmt_float(m.get("brier", 0)),
        _fmt_float(m.get("log_loss", 0)),
        _fmt_float(m.get("rps", 0)),
        _fmt_float(m.get("calibration_ece", 0)),
        _fmt_pct(dir_acc),
    ]


def _metric_cell(name: str, value: float, key: str) -> list[str]:
    threshold, _ = THRESHOLDS[key]
    lower = key != "directional"
    status = _status(value, threshold, lower_is_better=lower)
    return [name, _fmt_float(value, 3) if isinstance(value, float) else str(value), str(threshold), status]


# ============================================================================
# Mode 2: Evaluate — existing prediction_runs vs actual results
# ============================================================================


def _run_evaluate(limit: int = 200) -> tuple[list[dict], dict]:
    """Evaluate existing prediction_runs against match_results."""
    if not DB_PATH_SQLITE.exists():
        print(f"DB not found: {DB_PATH_SQLITE}")
        return [], {}

    conn = sqlite3.connect(str(DB_PATH_SQLITE))
    conn.row_factory = sqlite3.Row

    rows = conn.execute(f"""
        SELECT pr.id, pr.home_win_prob, pr.draw_prob, pr.away_win_prob,
               pr.confidence_score, pr.run_type, pr.model_version,
               ht.name as home_team_name, at.name as away_team_name,
               m.competition,
               mr.home_goals, mr.away_goals,
               pe.brier_score, pe.log_loss, pe.calibration_bucket, pe.top3_hit
        FROM prediction_runs pr
        JOIN matches m ON pr.match_id = m.id
        JOIN teams ht ON m.home_team_id = ht.id
        JOIN teams at ON m.away_team_id = at.id
        JOIN match_results mr ON pr.match_id = mr.match_id
        LEFT JOIN postmatch_eval pe ON pe.prediction_run_id = pr.id
        WHERE mr.home_goals IS NOT NULL
        ORDER BY pr.created_at DESC
        LIMIT ?
    """, (limit,)).fetchall()

    conn.close()

    results: list[dict] = []
    directional_correct = 0
    evaluated = 0
    brier_sum = 0.0
    log_loss_sum = 0.0

    for r in rows:
        actual_label = 0 if r["home_goals"] > r["away_goals"] else 1 if r["home_goals"] == r["away_goals"] else 2
        probs = np.array([r["home_win_prob"], r["draw_prob"], r["away_win_prob"]], dtype=float)
        actual = np.zeros(3, dtype=float)
        actual[actual_label] = 1.0

        pred_label = int(np.argmax(probs))
        if pred_label == actual_label:
            directional_correct += 1

        b = brier_score(actual, probs)
        ll = log_loss_score(actual, probs)
        brier_sum += b
        log_loss_sum += ll
        evaluated += 1

        results.append({
            "id": r["id"],
            "home_team": r["home_team_name"] or "?",
            "away_team": r["away_team_name"] or "?",
            "competition": r["competition"] or "?",
            "home_prob": float(r["home_win_prob"]),
            "draw_prob": float(r["draw_prob"]),
            "away_prob": float(r["away_win_prob"]),
            "confidence": float(r["confidence_score"]) if r["confidence_score"] else 0.0,
            "home_goals": r["home_goals"],
            "away_goals": r["away_goals"],
            "actual_label": actual_label,
            "predicted_label": pred_label,
            "brier": round(b, 4),
            "log_loss": round(ll, 4),
            "top3_hit": bool(r["top3_hit"]) if r["top3_hit"] is not None else None,
            "calibration_bucket": r["calibration_bucket"],
            "run_type": r["run_type"],
            "model_version": r["model_version"],
        })

    avg_brier = brier_sum / evaluated if evaluated else 0
    avg_log_loss = log_loss_sum / evaluated if evaluated else 0

    # Compute RPS on all evaluations
    rps_vals = []
    for r in results:
        probs = np.array([r["home_prob"], r["draw_prob"], r["away_prob"]])
        actual = np.zeros(3)
        actual[r["actual_label"]] = 1.0
        rps_vals.append(ranked_probability_score(actual, probs))
    avg_rps = float(np.mean(rps_vals)) if rps_vals else 0

    # ECE
    all_preds = [np.array([r["home_prob"], r["draw_prob"], r["away_prob"]]) for r in results]
    all_actuals = [np.zeros(3) for _ in results]
    for i, r in enumerate(results):
        all_actuals[i][r["actual_label"]] = 1.0
    avg_ece = calibration_ece(all_preds, all_actuals) if all_preds else 0

    metrics = {
        "brier": round(avg_brier, 4),
        "log_loss": round(avg_log_loss, 4),
        "rps": round(avg_rps, 4),
        "ece": round(avg_ece, 4),
        "directional": round(directional_correct / evaluated, 4) if evaluated else 0,
        "evaluated": evaluated,
    }

    return results, metrics


def _render_eval_report(results: list[dict], metrics: dict) -> str:
    """Render evaluate-mode sections."""
    sections: list[str] = []

    sections.append(_md_hdr(1, "Prediction Evaluation (Existing prediction_runs)"))
    sections.append(f"**Evaluated**: {metrics.get('evaluated', 0)} prediction-vs-result pairs")

    # ── Metrics summary ──
    sections.append(_md_hdr(2, "Metrics"))
    sections.append(
        _md_table(
            ["Metric", "Value", "Threshold", "Status"],
            [
                _metric_cell("Brier Score", metrics.get("brier", 0), "brier"),
                _metric_cell("Log Loss", metrics.get("log_loss", 0), "log_loss"),
                _metric_cell("RPS", metrics.get("rps", 0), "rps"),
                _metric_cell("ECE", metrics.get("ece", 0), "ece"),
                _metric_cell("Directional Accuracy", metrics.get("directional", 0), "directional"),
            ],
        )
    )

    # ── By confidence bucket ──
    sections.append(_md_hdr(2, "Confidence Bucket Analysis"))
    buckets: dict[str, list[dict]] = {"<0.5": [], "0.5-0.6": [], "0.6-0.7": [], "0.7-0.8": [], "0.8+": []}
    for r in results:
        c = r["confidence"]
        if c < 0.5:
            buckets["<0.5"].append(r)
        elif c < 0.6:
            buckets["0.5-0.6"].append(r)
        elif c < 0.7:
            buckets["0.6-0.7"].append(r)
        elif c < 0.8:
            buckets["0.7-0.8"].append(r)
        else:
            buckets["0.8+"].append(r)

    bucket_rows = []
    for label, items in buckets.items():
        if not items:
            bucket_rows.append([label, "0", "-", "-", "-"])
            continue
        n = len(items)
        correct = sum(1 for r in items if r["predicted_label"] == r["actual_label"])
        avg_conf = np.mean([r["confidence"] for r in items])
        briers = [r["brier"] for r in items]
        avg_b = np.mean(briers)
        bucket_rows.append([
            label, str(n), _fmt_pct(correct / n), _fmt_float(avg_conf, 3), _fmt_float(avg_b, 4),
        ])

    sections.append(
        _md_table(
            ["Confidence", "N", "Accuracy", "Avg Confidence", "Avg Brier"],
            bucket_rows,
        )
    )

    # ── By competition ──
    sections.append(_md_hdr(2, "By Competition"))
    by_comp: dict[str, list[dict]] = {}
    for r in results:
        comp = r["competition"]
        by_comp.setdefault(comp, []).append(r)

    comp_rows = []
    for comp in sorted(by_comp, key=lambda c: len(by_comp[c]), reverse=True)[:10]:
        items = by_comp[comp]
        n = len(items)
        correct = sum(1 for r in items if r["predicted_label"] == r["actual_label"])
        avg_b = np.mean([r["brier"] for r in items])
        comp_rows.append([comp, str(n), _fmt_pct(correct / n), _fmt_float(avg_b, 4)])
    sections.append(
        _md_table(["Competition", "N", "Accuracy", "Avg Brier"], comp_rows)
    )

    # ── Worst/best predictions ──
    sorted_by_brier = sorted(results, key=lambda r: r["brier"], reverse=True)
    sections.append(_md_hdr(2, "Best & Worst Predictions"))
    sections.append(_md_hdr(3, "Top 5 Worst (highest Brier)"))
    for r in sorted_by_brier[:5]:
        sections.append(
            f"- {r['home_team']} {r['home_goals']}-{r['away_goals']} {r['away_team']} "
            f"({r['competition']}) — pred: {_fmt_pct(r['home_prob'])}/{_fmt_pct(r['draw_prob'])}/{_fmt_pct(r['away_prob'])} "
            f"→ Brier={_fmt_float(r['brier'], 4)}"
        )
    sections.append(_md_hdr(3, "Top 5 Best (lowest Brier)"))
    for r in sorted_by_brier[-5:]:
        sections.append(
            f"- {r['home_team']} {r['home_goals']}-{r['away_goals']} {r['away_team']} "
            f"({r['competition']}) — pred: {_fmt_pct(r['home_prob'])}/{_fmt_pct(r['draw_prob'])}/{_fmt_pct(r['away_prob'])} "
            f"→ Brier={_fmt_float(r['brier'], 4)}"
        )

    return "\n\n".join(sections)


# ============================================================================
# Mode 3: Calibration Analysis
# ============================================================================


def _run_calibrate(results: list[dict] | None, wf_metrics: dict | None) -> str:
    """Build calibration analysis: reliability table, ECE, recommendations.

    If walk-forward results are available, uses those. Otherwise uses
    evaluate results.
    """
    sections: list[str] = []

    sections.append(_md_hdr(1, "Calibration Analysis"))

    if not results:
        sections.append("**No prediction data available for calibration analysis.**")
        sections.append("\nRun `walk-forward` or `evaluate` mode first to generate data.")
        return "\n\n".join(sections)

    # ── Build reliability table: bin predictions by confidence, compare to actual frequency ──
    sections.append(_md_hdr(2, "Reliability Table (10 bins)"))

    # Extract probs and actuals
    all_probs: list[np.ndarray] = []
    all_actuals: list[np.ndarray] = []

    for r in results:
        if "fused_probs" in r:
            probs = np.array(r["fused_probs"], dtype=float)
        elif "home_prob" in r:
            probs = np.array([r["home_prob"], r["draw_prob"], r["away_prob"]], dtype=float)
        else:
            continue

        if "actual_onehot" in r:
            actual = np.array(r["actual_onehot"], dtype=float)
        elif "actual_label" in r:
            actual = np.zeros(3, dtype=float)
            actual[r["actual_label"]] = 1.0
        else:
            continue

        all_probs.append(probs)
        all_actuals.append(actual)

    if not all_probs:
        sections.append("No valid probability data found.")
        return "\n\n".join(sections)

    probs_arr = np.array(all_probs)
    actuals_arr = np.array(all_actuals)

    # Reliability per outcome class
    n_bins = 10
    bin_rows = []
    ece_class_values: list[float] = []

    for c, outcome_name in enumerate(["Home Win", "Draw", "Away Win"]):
        conf = probs_arr[:, c]
        correct = actuals_arr[:, c]
        bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
        ece_c = 0.0

        for b in range(n_bins):
            lo, hi = bin_edges[b], bin_edges[b + 1]
            in_bin = (conf > lo) & (conf <= hi)
            n_bin = int(in_bin.sum())
            if n_bin == 0:
                continue
            bin_acc = float(correct[in_bin].mean())
            bin_conf = float(conf[in_bin].mean())
            err = bin_acc - bin_conf
            ece_c += (n_bin / len(conf)) * abs(err)

            if c == 0:  # Only print bins once (for Home Win)
                bin_rows.append([
                    str(b + 1),
                    f"{lo:.1f}–{hi:.1f}",
                    str(n_bin),
                    _fmt_float(bin_conf, 3),
                    _fmt_float(bin_acc, 3),
                    f"{err:+.3f}",
                ])

        ece_class_values.append(ece_c)

    sections.append(
        _md_table(
            ["Bin", "Prob Range", "N", "Avg Predicted", "Actual Win%", "Error"],
            bin_rows,
        )
    )

    ece_total = float(np.mean(ece_class_values))
    sections.append(f"\n**ECE (Expected Calibration Error)**: {_fmt_float(ece_total, 4)}")
    sections.append(f"  - Home Win ECE: {_fmt_float(ece_class_values[0], 4)}")
    sections.append(f"  - Draw ECE:     {_fmt_float(ece_class_values[1], 4)}")
    sections.append(f"  - Away Win ECE: {_fmt_float(ece_class_values[2], 4)}")

    # ── ECE Status ──
    ece_status = _status(ece_total, 0.10, lower_is_better=True)
    sections.append(f"\n**ECE Status**: {ece_status} " +
                    ("well calibrated" if ece_total < 0.05 else
                     "acceptable" if ece_total < 0.10 else
                     "needs recalibration"))

    # ── Isotonic calibrator fitting attempt ──
    sections.append(_md_hdr(2, "Isotonic Calibration"))
    try:
        from app.services.calibration import IsotonicCalibrator

        # Build eval records in the format calibrator expects
        eval_records = []
        for r in results:
            if "actual_label" in r:
                actual_label = r["actual_label"]
                actual_home = 1 if actual_label == 0 else 0
                actual_draw = 1 if actual_label == 1 else 0
                actual_away = 1 if actual_label == 2 else 0
            elif "home_goals" in r:
                actual_home = 1 if r["home_goals"] > r["away_goals"] else 0
                actual_draw = 1 if r["home_goals"] == r["away_goals"] else 0
                actual_away = 1 if r["home_goals"] < r["away_goals"] else 0
            else:
                continue

            if "fused_probs" in r:
                probs = r["fused_probs"]
            elif "home_prob" in r:
                probs = [r["home_prob"], r["draw_prob"], r["away_prob"]]
            else:
                continue

            eval_records.append({
                "home_win_prob": float(probs[0]),
                "draw_prob": float(probs[1]),
                "away_win_prob": float(probs[2]),
                "actual_home": actual_home,
                "actual_draw": actual_draw,
                "actual_away": actual_away,
            })

        if len(eval_records) >= 20:
            cal = IsotonicCalibrator()
            cal.fit_from_db_records(eval_records)
            stats = cal.calibration_stats()
            sections.append(f"- **Fitted**: {'yes' if stats.get('is_fitted') else 'no'}")
            sections.append(f"- **Training samples**: {stats.get('training_samples', len(eval_records))}")
            sections.append(f"- **ECE (after fitting)**: {_fmt_float(stats.get('expected_calibration_error', ece_total), 4)}")

            # Save calibrator
            out_path = BACKEND_DIR / "artifacts" / "calibrator.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            cal.save(str(out_path))
            sections.append(f"- **Saved to**: `{out_path}`")
        else:
            sections.append(f"- **Not fitted**: only {len(eval_records)} records (need ≥ 20)")

    except ImportError as e:
        sections.append(f"- IsotonicCalibrator not available: {e}")
    except Exception as e:
        sections.append(f"- Calibrator fitting failed: {e}")

    # ── Recommendations based on calibration ──
    sections.append(_md_hdr(2, "Recommendations"))
    recs = []
    if ece_total > 0.10:
        recs.append("- [ ] **ECE > 0.10**: Consider fitting isotonic calibrator when ≥ 20 eval records available")
    if ece_class_values[1] > 0.15:
        recs.append("- [ ] **Draw calibration poor**: Draw outcome is notoriously hard to predict; consider adding draw-specific features")
    if len(eval_records) < 20:
        recs.append(f"- [ ] **Insufficient eval data** ({len(eval_records)} records): Need ≥ 20 to fit calibrator. Run more predictions.")
    if not recs:
        recs.append("- [x] Calibration is within acceptable range. No action needed.")
    sections.append("\n".join(recs))

    return "\n\n".join(sections)


# ============================================================================
# Before/After Weight Evidence
# ============================================================================


def _run_weight_comparison(
    df: pd.DataFrame | None = None,
    initial_window: int = 100,
    step: int = 1,
) -> str:
    """Compare multiple weight configurations on the same data."""
    sections: list[str] = []
    sections.append(_md_hdr(1, "Before/After Weight Evidence"))

    if df is None or len(df) < initial_window + 1:
        sections.append("Insufficient data for weight comparison.")
        return "\n\n".join(sections)

    configs = [
        ("current (default)", 0.50, 0.05, 0.05),
        ("dc=0.55 enh=0.30 elo=0.10 pi=0.05", 0.55, 0.10, 0.05),
        ("dc=0.45 enh=0.35 elo=0.10 pi=0.10", 0.45, 0.10, 0.10),
        ("dc=0.60 enh=0.25 elo=0.05 pi=0.10", 0.60, 0.05, 0.10),
    ]

    config_rows = []
    best_brier = float("inf")
    best_config = ""
    baseline_brier = None
    baseline_rps = None

    for label, dc_w, elo_w, pi_w in configs:
        print(f"  Testing: {label} (DC={dc_w}, Elo={elo_w}, Pi={pi_w})")
        results = run_walk_forward_backtest(
            df,
            initial_window=initial_window,
            step=step,
            dc_weight=dc_w,
            elo_weight=elo_w,
            pi_weight=pi_w,
            verbose=False,
        )
        metrics = compute_component_metrics(results)
        fused = metrics.get("fused", {})
        b = fused.get("brier", 0)
        ll = fused.get("log_loss", 0)
        r = fused.get("rps", 0)
        e = fused.get("calibration_ece", 0)

        if baseline_brier is None:
            baseline_brier = b
            baseline_rps = r

        delta = ""
        if baseline_brier is not None and label != "current (default)":
            delta = f"{b - baseline_brier:+.4f}"

        config_rows.append([label, _fmt_float(b), _fmt_float(ll), _fmt_float(r), _fmt_float(e), delta])

        if b < best_brier:
            best_brier = b
            best_config = label

    sections.append(
        _md_table(
            ["Weight Config", "Brier ↓", "LogLoss ↓", "RPS ↓", "ECE ↓", "Δ vs Default"],
            config_rows,
        )
    )

    sections.append(f"\n**Best config by Brier**: `{best_config}` (Brier={_fmt_float(best_brier)})")

    if baseline_brier and best_brier < baseline_brier:
        improvement = baseline_brier - best_brier
        sections.append(f"\n**Action**: Candidate weights improve Brier by {improvement:.4f}. "
                        f"Submit for review with this backtest evidence before applying to production.")
    else:
        sections.append(f"\n**Action**: No weight config improves on default. Keep current production weights.")

    sections.append(f"\n⚠️ **Per CLAUDE.md Section 6**: Weight changes require PR with before/after evidence + backtest proof + change rationale.")

    return "\n\n".join(sections)


# ============================================================================
# Market Baseline
# ============================================================================


def _run_market_baseline() -> str:
    """Build market baseline comparison section (best-effort)."""
    sections: list[str] = []
    sections.append(_md_hdr(1, "Market Baseline Comparison"))

    if not DB_PATH_SQLITE.exists():
        sections.append("Database not available.")
        return "\n\n".join(sections)

    conn = sqlite3.connect(str(DB_PATH_SQLITE))
    conn.row_factory = sqlite3.Row

    # Find predictions that have market odds available
    rows = conn.execute("""
        SELECT pr.home_win_prob, pr.draw_prob, pr.away_win_prob,
               mr.home_goals, mr.away_goals,
               mo.home_implied_prob as mkt_home, mo.draw_implied_prob as mkt_draw,
               mo.away_implied_prob as mkt_away
        FROM prediction_runs pr
        JOIN matches m ON pr.match_id = m.id
        JOIN match_results mr ON pr.match_id = mr.match_id
        LEFT JOIN market_odds mo ON mo.match_id = pr.match_id
        WHERE mo.home_implied_prob IS NOT NULL
        LIMIT 200
    """).fetchall()

    conn.close()

    if not rows:
        sections.append("**No prediction-vs-market pairs found.** Run more predictions with market odds available.")
        return "\n\n".join(sections)

    model_briers = []
    market_briers = []
    model_directional = 0
    market_directional = 0
    n = 0

    for r in rows:
        actual_label = 0 if r["home_goals"] > r["away_goals"] else 1 if r["home_goals"] == r["away_goals"] else 2
        actual = np.zeros(3, dtype=float)
        actual[actual_label] = 1.0

        model_probs = np.array([r["home_win_prob"], r["draw_prob"], r["away_win_prob"]], dtype=float)
        market_probs = np.array([r["mkt_home"], r["mkt_draw"], r["mkt_away"]], dtype=float)

        model_briers.append(brier_score(actual, model_probs))
        market_briers.append(brier_score(actual, market_probs))

        if int(np.argmax(model_probs)) == actual_label:
            model_directional += 1
        if int(np.argmax(market_probs)) == actual_label:
            market_directional += 1
        n += 1

    if n == 0:
        sections.append("No valid comparisons available.")
        return "\n\n".join(sections)

    avg_model_brier = float(np.mean(model_briers))
    avg_market_brier = float(np.mean(market_briers))
    delta = avg_model_brier - avg_market_brier

    sections.append(f"**Pairs compared**: {n}")
    sections.append(
        _md_table(
            ["Metric", "Model", "Market", "Δ (Model − Market)"],
            [
                ["Brier Score", _fmt_float(avg_model_brier), _fmt_float(avg_market_brier), f"{delta:+.4f}"],
                ["Directional Accuracy", _fmt_pct(model_directional / n), _fmt_pct(market_directional / n),
                 f"{model_directional/n - market_directional/n:+.1%}"],
            ],
        )
    )

    if delta > 0:
        sections.append(f"\n⚠️ Model underperforms market by {delta:.4f} Brier points. Consider increasing market blend weight or investigating model bias.")
    else:
        sections.append(f"\n✅ Model beats market by {-delta:.4f} Brier points.")

    return "\n\n".join(sections)


# ============================================================================
# Main CLI
# ============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="WC26 Predict — Unified Backtest & Calibration Report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/backtest_report.py walk-forward --quick
  python scripts/backtest_report.py walk-forward --full
  python scripts/backtest_report.py walk-forward --limit 500 --compare-weights
  python scripts/backtest_report.py evaluate
  python scripts/backtest_report.py calibrate
  python scripts/backtest_report.py walk-forward --quick --compare-weights --market
""",
    )

    sub = parser.add_subparsers(dest="mode", help="Mode: walk-forward, evaluate, calibrate")

    # walk-forward
    p_wf = sub.add_parser("walk-forward", help="Expanding-window walk-forward backtest")
    p_wf.add_argument("--quick", action="store_true", help="Quick mode: last 200 matches, window=100")
    p_wf.add_argument("--full", action="store_true", help="Full mode: all data, window=500, step=3")
    p_wf.add_argument("--limit", type=int, help="Limit to last N matches")
    p_wf.add_argument("--team-type", default="national", help="Team type filter (default: national)")
    p_wf.add_argument("--dc-weight", type=float, default=0.50)
    p_wf.add_argument("--elo-weight", type=float, default=0.05)
    p_wf.add_argument("--pi-weight", type=float, default=0.05)
    p_wf.add_argument("--compare-weights", action="store_true", help="Run weight comparison")
    p_wf.add_argument("--market", action="store_true", help="Include market baseline section")
    p_wf.add_argument("--output", type=str, help="Output report path")
    p_wf.add_argument("--save-results", type=str, help="Save raw backtest results as JSON")

    # evaluate
    p_eval = sub.add_parser("evaluate", help="Evaluate existing prediction_runs vs match_results")
    p_eval.add_argument("--limit", type=int, default=200, help="Max predictions to evaluate")
    p_eval.add_argument("--output", type=str, help="Output report path")

    # calibrate
    p_cal = sub.add_parser("calibrate", help="Calibration analysis (reliability table + ECE)")
    p_cal.add_argument("--wf-results", type=str, help="JSON file from walk-forward --save-results")
    p_cal.add_argument("--output", type=str, help="Output report path")

    args = parser.parse_args()

    if not args.mode:
        parser.print_help()
        return

    sections: list[str] = []
    output_path = None

    if args.mode == "walk-forward":
        output_path = Path(args.output) if hasattr(args, "output") and args.output else None
        results, metrics = _run_walk_forward(
            quick=args.quick,
            full=args.full,
            limit=args.limit,
            team_type=args.team_type,
            dc_weight=args.dc_weight,
            elo_weight=args.elo_weight,
            pi_weight=args.pi_weight,
        )

        if not results:
            print("No results generated.")
            return

        config = {
            "mode": "quick" if args.quick else "full" if args.full else "custom",
            "initial_window": 100 if args.quick else 500 if args.full else 300,
            "step": 1 if args.quick else 3 if args.full else 1,
            "team_type": args.team_type,
            "dc_weight": args.dc_weight,
            "elo_weight": args.elo_weight,
            "pi_weight": args.pi_weight,
        }

        sections.append(_render_wf_report(results, metrics, config))

        # Calibration section from walk-forward results
        sections.append(_run_calibrate(results, metrics))

        # Weight comparison
        if args.compare_weights:
            df = load_data(team_type=args.team_type, max_rows=200 if args.quick else 500 if args.full else (args.limit or 200))
            sections.append(_run_weight_comparison(df, initial_window=100 if args.quick else 300))

        # Market baseline
        if args.market:
            sections.append(_run_market_baseline())

        # Recommendations
        sections.append(_md_hdr(1, "Recommendations"))
        fused = metrics.get("fused", {})
        recs = []
        if fused.get("brier", 0) > 0.225:
            recs.append("- [ ] Brier > 0.225 — investigate component weights")
        if fused.get("log_loss", 0) > 0.700:
            recs.append("- [ ] Log Loss > 0.700 — check probability calibration")
        if fused.get("rps", 0) > 0.150:
            recs.append("- [ ] RPS > 0.150 — review fusion strategy")
        if fused.get("calibration_ece", 0) > 0.10:
            recs.append("- [ ] ECE > 0.10 — fit isotonic calibrator when data available")
        if not recs:
            recs.append("- [x] All metrics within acceptable range.")
        recs.append("- [ ] Per CLAUDE.md: weight changes must go through PR with before/after evidence + backtest proof")
        sections.append("\n".join(recs))

        # Save raw results if requested
        if args.save_results:
            result_path = Path(args.save_results)
            result_path.parent.mkdir(parents=True, exist_ok=True)
            serializable = []
            for r in results:
                entry = {k: v for k, v in r.items()}
                for k in ("actual_onehot", "dc_probs", "enh_probs", "elo_probs", "pi_probs", "fused_probs"):
                    if k in entry and isinstance(entry[k], np.ndarray):
                        entry[k] = entry[k].tolist()
                serializable.append(entry)
            result_path.write_text(json.dumps(serializable, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"Raw results saved to: {result_path}")

    elif args.mode == "evaluate":
        output_path = Path(args.output) if hasattr(args, "output") and args.output else None
        results, metrics = _run_evaluate(limit=args.limit)
        if results:
            sections.append(_render_eval_report(results, metrics))
            sections.append(_run_calibrate(results, metrics))
            sections.append(_run_market_baseline())
        else:
            sections.append("# Evaluation\n\nNo prediction-result pairs found in database.")

    elif args.mode == "calibrate":
        output_path = Path(args.output) if hasattr(args, "output") and args.output else None
        results = None
        if hasattr(args, "wf_results") and args.wf_results:
            wf_path = Path(args.wf_results)
            if wf_path.exists():
                raw = json.loads(wf_path.read_text(encoding="utf-8"))
                results = []
                for entry in raw:
                    for k in ("actual_onehot", "dc_probs", "enh_probs", "elo_probs", "pi_probs", "fused_probs"):
                        if k in entry and isinstance(entry[k], list):
                            entry[k] = np.array(entry[k], dtype=float)
                    if "actual_label" not in entry and "actual_onehot" in entry:
                        entry["actual_label"] = int(np.argmax(entry["actual_onehot"]))
                    results.append(entry)
                print(f"Loaded {len(results)} results from {wf_path}")
            else:
                print(f"File not found: {wf_path}")
        else:
            results, _ = _run_evaluate(limit=200)
        sections.append(_run_calibrate(results, {}))

    # Write report
    if sections:
        write_report(sections, output_path)


if __name__ == "__main__":
    main()
