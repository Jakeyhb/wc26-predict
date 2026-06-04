#!/usr/bin/env python3
"""predict_match.py — WC26 Predict artifact-based single-match prediction CLI.

Loads pre-trained models from backend/artifacts/ — NO .fit() calls in default mode.

Usage:
    python scripts/predict_match.py --home France --away "Ivory Coast" \
        --competition "International Friendly" --neutral --mode full
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import joblib
import pandas as pd

from app.services.artifact_registry import load_registry, validate_bundle
from app.services.prediction_timer import PredictionTimer
from app.services.run_quality import RunQuality
from app.services.dixon_coles import DixonColesModel
from app.services.tabular_match_model import (
    TabularMatchEnhancer,
    fuse_outcome_probabilities,
)
from app.services.weibull_model import WeibullWrapper, fuse_weibull_probs
from app.services.elo_ratings import EloRatingSystem, fuse_elo_probabilities
from app.services.pi_ratings import PiRatingWrapper, fuse_pi_probabilities
from app.services.weights import get_weight_config

VERSION = "1.92"

# ── Artifact paths (relative to backend/) ──────────────────────────────────
ARTIFACTS_DIR = BACKEND_DIR / "artifacts"
MODELS_DIR = ARTIFACTS_DIR / "models"
RATINGS_DIR = ARTIFACTS_DIR / "ratings"
DATAFRAMES_DIR = ARTIFACTS_DIR / "dataframes"

DC_PATH = MODELS_DIR / "dc.pkl"
ENHANCER_PATH = MODELS_DIR / "enhancer.joblib"
ELO_PATH = RATINGS_DIR / "elo.json"
PI_PATH = RATINGS_DIR / "pi.json"
DF_PATH = DATAFRAMES_DIR / "national_finished_matches.pkl"

# Components that each mode expects in the registry
MODE_REQUIRED_COMPONENTS = {
    "baseline": ["dixon_coles"],
    "standard": ["dixon_coles", "tabular_enhancer", "elo"],
    "full": ["dixon_coles", "tabular_enhancer", "elo", "pi_rating"],
    "research-full": ["dixon_coles", "tabular_enhancer", "elo", "pi_rating"],
}

MODE_LABELS = {
    "baseline": "baseline",
    "standard": "standard",
    "full": "full",
    "research-full": "research-full",
}


# ── Artifact loaders ───────────────────────────────────────────────────────


def _load_dc(timer: PredictionTimer) -> DixonColesModel:
    """Load Dixon-Coles model from pickle artifact."""
    timer.start("load_dc")
    if not DC_PATH.exists():
        raise FileNotFoundError(
            f"DC artifact not found at {DC_PATH}. Run train_models.py first."
        )
    with open(DC_PATH, "rb") as f:
        dc = pickle.load(f)
    if not isinstance(dc, DixonColesModel):
        raise TypeError(f"Expected DixonColesModel, got {type(dc).__name__}")
    if not dc.attack_params:
        raise ValueError("Loaded DC model has empty attack_params — artifact appears un-fitted")
    timer.stop()
    return dc


def _load_enhancer(timer: PredictionTimer) -> TabularMatchEnhancer:
    """Load TabularMatchEnhancer from joblib artifact."""
    timer.start("load_enhancer")
    if not ENHANCER_PATH.exists():
        raise FileNotFoundError(
            f"Enhancer artifact not found at {ENHANCER_PATH}. Run train_models.py first."
        )
    enhancer = joblib.load(str(ENHANCER_PATH))
    if not isinstance(enhancer, TabularMatchEnhancer):
        raise TypeError(f"Expected TabularMatchEnhancer, got {type(enhancer).__name__}")
    if not enhancer.is_fitted:
        raise ValueError("Loaded enhancer is not fitted — artifact appears invalid. Retrain with train_models.py")
    timer.stop()
    return enhancer


def _load_elo(timer: PredictionTimer) -> EloRatingSystem:
    """Load Elo ratings from JSON artifact and restore EloRatingSystem."""
    timer.start("load_elo")
    if not ELO_PATH.exists():
        raise FileNotFoundError(
            f"Elo artifact not found at {ELO_PATH}. Run train_models.py first."
        )
    elo_data = json.loads(ELO_PATH.read_text("utf-8"))
    # elo.json is a flat {team_name: rating_value} dict
    elo = EloRatingSystem()
    elo.ratings = {str(k): float(v) for k, v in elo_data.items()}
    timer.stop()
    return elo


def _load_pi(timer: PredictionTimer) -> PiRatingWrapper:
    """Load Pi-Ratings from JSON artifact and restore PiRatingWrapper."""
    timer.start("load_pi")
    if not PI_PATH.exists():
        raise FileNotFoundError(
            f"Pi-Rating artifact not found at {PI_PATH}. Run train_models.py first."
        )
    pi_data = json.loads(PI_PATH.read_text("utf-8"))
    # pi.json is a flat {team_name: rating_value} dict
    pi_model = PiRatingWrapper()
    pi_model.team_ratings = {str(k): float(v) for k, v in pi_data.items()}
    timer.stop()
    return pi_model


def _load_training_df(timer: PredictionTimer) -> pd.DataFrame:
    """Load training DataFrame from artifact pickle, with SQLite fallback."""
    timer.start("load_df")
    try:
        if DF_PATH.exists():
            df = pd.read_pickle(str(DF_PATH))
            print(
                f"  [data] Training DF: {len(df)} rows, "
                f"{df.home_team.nunique()} teams",
                flush=True,
            )
            timer.stop()
            return df
    except Exception as exc:
        print(f"  [data] Pickle load failed ({exc}), trying SQLite...", flush=True)

    # Fallback: SQLite query
    db_path = BACKEND_DIR / "data" / "local_stage2.db"
    if not db_path.exists():
        raise FileNotFoundError(
            f"No training data found. Expected {DF_PATH} or {db_path}. "
            "Run train_models.py first."
        )
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    df = pd.read_sql_query(
        """
        SELECT ht.name AS home_team, at.name AS away_team,
               mr.home_goals, mr.away_goals, m.match_date,
               COALESCE(m.competition_weight, 1.0) AS competition_weight,
               COALESCE(m.is_neutral_venue, 0) AS is_neutral_venue,
               m.competition, m.stage
        FROM matches m
        JOIN teams ht ON m.home_team_id = ht.id
        JOIN teams at ON m.away_team_id = at.id
        JOIN match_results mr ON m.id = mr.match_id
        WHERE m.status = 'finished'
        ORDER BY m.match_date ASC
    """,
        conn,
    )
    conn.close()
    df["match_date"] = pd.to_datetime(df["match_date"], utc=True, format="ISO8601")
    print(
        f"  [data] Training DF: {len(df)} rows, {df.home_team.nunique()} teams (SQLite)",
        flush=True,
    )
    timer.stop()
    return df


# ── Weibull (optional, research-full only) ────────────────────────────────


def _try_load_weibull(timer: PredictionTimer) -> WeibullWrapper | None:
    """Attempt to load a pre-fitted Weibull model from pickle.

    Weibull is not part of the standard artifact bundle — returns None
    if the file does not exist.
    """
    weibull_path = MODELS_DIR / "weibull.pkl"
    if not weibull_path.exists():
        return None
    timer.start("load_weibull")
    try:
        with open(weibull_path, "rb") as f:
            wb = pickle.load(f)
        if isinstance(wb, WeibullWrapper) and wb._fitted:
            print("  [load] Weibull model loaded from artifact", flush=True)
            timer.stop()
            return wb
    except Exception as exc:
        print(f"  [load] Weibull load failed: {exc}", flush=True)
    timer.stop()
    return None


# ── Pipeline runner ────────────────────────────────────────────────────────


def run_artifact_pipeline(
    home_team: str,
    away_team: str,
    competition: str,
    is_neutral: bool,
    mode: str,
    *,
    allow_retrain: bool = False,
) -> tuple[dict[str, Any], RunQuality, dict[str, float]]:
    """Run artifact-based inference pipeline.

    Loads pre-trained models from artifacts/ — no .fit() calls (unless
    allow_retrain=True, which is only for debugging/retraining).

    Returns (result_dict, run_quality, timings_dict).
    """
    timer = PredictionTimer()
    quality = RunQuality()
    component_probs: dict[str, dict[str, float]] = {}

    # ── 1. Load & validate registry ──
    timer.start("load_registry")
    registry = load_registry()
    timer.stop()

    # For research-full, validate as "full" (weibull is optional)
    validation_mode = "full" if mode == "research-full" else mode
    ok, missing = validate_bundle(registry, validation_mode)
    if not ok:
        print(json.dumps({
            "ok": False,
            "error": "failed_missing_artifacts",
            "mode": mode,
            "missing_components": missing,
            "message": f"Required artifacts missing: {missing}. Run train_models.py first.",
            "hint": (
                "baseline: DC | standard: DC+Enhancer+Elo | "
                "full/research-full: DC+Enhancer+Elo+Pi\n"
                "Run: python scripts/train_models.py"
            ),
        }, indent=2, ensure_ascii=False))
        sys.exit(1)

    # ── 2. Weight config ──
    wc = get_weight_config(competition)
    print(
        f"  [weights] {wc.label}  DC={wc.dc:.2f}  Enh={wc.enhancer:.2f}  "
        f"Elo={wc.elo:.2f}  Pi={wc.pi:.2f}  Wb={wc.weibull:.2f}",
        flush=True,
    )

    # ── 3. Load training DataFrame (needed by enhancer + as context) ──
    training_df = _load_training_df(timer)
    match_date = training_df["match_date"].max().to_pydatetime()

    # ── 4. Dixon-Coles ──
    dc = _load_dc(timer)
    quality.model_components["dixon_coles"] = "loaded_from_artifact"
    timer.start("dc_predict")
    dc_pred = dc.predict_match(home_team, away_team, is_neutral_venue=is_neutral)
    timer.stop()
    print(
        f"  [DC] H={dc_pred['home_win_prob']:.3f}  "
        f"D={dc_pred['draw_prob']:.3f}  A={dc_pred['away_win_prob']:.3f}",
        flush=True,
    )
    component_probs["dixon_coles"] = {
        "home": dc_pred["home_win_prob"],
        "draw": dc_pred["draw_prob"],
        "away": dc_pred["away_win_prob"],
    }

    fused = dict(dc_pred)  # start with DC as base

    # ── 5. TabularMatchEnhancer (standard+) ──
    if mode in ("standard", "full", "research-full"):
        enhancer = _load_enhancer(timer)
        quality.model_components["tabular_enhancer"] = "loaded_from_artifact"
        timer.start("enhancer_predict")
        enh_pred = enhancer.predict_match(
            home_team=home_team,
            away_team=away_team,
            match_date=match_date,
            competition_weight=0.5,
            is_neutral_venue=is_neutral,
            training_df=training_df,
        )
        timer.stop()
        print(
            f"  [Enhancer] H={enh_pred['home_win_prob']:.3f}  "
            f"D={enh_pred['draw_prob']:.3f}  A={enh_pred['away_win_prob']:.3f}",
            flush=True,
        )
        component_probs["enhancer"] = {
            "home": enh_pred["home_win_prob"],
            "draw": enh_pred["draw_prob"],
            "away": enh_pred["away_win_prob"],
        }

        # Fuse DC + Enhancer
        timer.start("fusion")
        fused = fuse_outcome_probabilities(fused, enh_pred, base_weight=wc.dc)
        timer.stop()
        print(
            f"  [DC+Enh] H={fused['home_win_prob']:.3f}  "
            f"D={fused['draw_prob']:.3f}  A={fused['away_win_prob']:.3f}",
            flush=True,
        )

    # ── 6. Elo (standard+) ──
    if mode in ("standard", "full", "research-full"):
        elo = _load_elo(timer)
        quality.model_components["elo"] = "loaded_from_artifact"
        timer.start("elo_predict")
        elo_pred = elo.predict(
            home_team,
            away_team,
            is_neutral=is_neutral,
            competition_weight=0.5,
            competition=competition,
        )
        timer.stop()
        print(
            f"  [Elo] H={elo_pred.home_win_prob:.3f}  "
            f"D={elo_pred.draw_prob:.3f}  A={elo_pred.away_win_prob:.3f}",
            flush=True,
        )
        component_probs["elo"] = {
            "home": elo_pred.home_win_prob,
            "draw": elo_pred.draw_prob,
            "away": elo_pred.away_win_prob,
        }

        timer.start("fusion")
        fused = fuse_elo_probabilities(fused, elo_pred, elo_weight=wc.elo)
        timer.stop()
        print(
            f"  [+Elo] H={fused['home_win_prob']:.3f}  "
            f"D={fused['draw_prob']:.3f}  A={fused['away_win_prob']:.3f}",
            flush=True,
        )

    # ── 7. Pi-Rating (full+) ──
    if mode in ("full", "research-full"):
        pi_model = _load_pi(timer)
        quality.model_components["pi_rating"] = "loaded_from_artifact"
        timer.start("pi_predict")
        try:
            pi_pred = pi_model.predict(home_team, away_team, is_neutral)
            timer.stop()
            print(
                f"  [Pi] H={pi_pred['home_win_prob']:.3f}  "
                f"D={pi_pred['draw_prob']:.3f}  A={pi_pred['away_win_prob']:.3f}",
                flush=True,
            )
            component_probs["pi_rating"] = {
                "home": pi_pred["home_win_prob"],
                "draw": pi_pred["draw_prob"],
                "away": pi_pred["away_win_prob"],
            }

            timer.start("fusion")
            fused = fuse_pi_probabilities(fused, pi_pred, pi_weight=wc.pi)
            timer.stop()
            print(
                f"  [+Pi] H={fused['home_win_prob']:.3f}  "
                f"D={fused['draw_prob']:.3f}  A={fused['away_win_prob']:.3f}",
                flush=True,
            )
        except Exception as exc:
            timer.stop()
            quality.model_components["pi_rating"] = "failed"
            quality.mark_degraded(f"Pi-Rating artifact prediction failed: {exc}")
            print(f"  [Pi] FAILED: {exc} — continuing without Pi", flush=True)

    # ── 8. Weibull (research-full only, optional) ──
    if mode == "research-full":
        wb = _try_load_weibull(timer)
        if wb is not None:
            quality.model_components["weibull"] = "loaded_from_artifact"
            timer.start("weibull_predict")
            try:
                wb_pred = wb.predict(home_team, away_team, is_neutral)
                timer.stop()
                if wb_pred is not None:
                    timer.start("fusion")
                    fused = fuse_weibull_probs(fused, wb_pred, wb_weight=wc.weibull)
                    timer.stop()
                    print(
                        f"  [+Weibull] H={fused['home_win_prob']:.3f}  "
                        f"D={fused['draw_prob']:.3f}  A={fused['away_win_prob']:.3f}",
                        flush=True,
                    )
                else:
                    timer.stop()
                    print("  [Weibull] predict returned None — skipping", flush=True)
            except Exception as exc:
                timer.stop()
                print(f"  [Weibull] prediction failed: {exc} — skipping", flush=True)
        else:
            quality.model_components["weibull"] = "unavailable"
            print("  [Weibull] artifact not found — optional, continuing", flush=True)

    # ── 9. Renormalize ──
    total = fused["home_win_prob"] + fused["draw_prob"] + fused["away_win_prob"]
    if abs(total - 1.0) > 0.001:
        fused["home_win_prob"] /= total
        fused["draw_prob"] /= total
        fused["away_win_prob"] /= total

    # ── 10. Pipeline status ──
    # Determine which components were actually used
    used_components = [
        c for c, s in quality.model_components.items()
        if s == "loaded_from_artifact"
    ]
    expected = MODE_REQUIRED_COMPONENTS.get(mode, [])
    all_loaded = all(
        quality.model_components.get(c) == "loaded_from_artifact"
        for c in expected
    )
    if mode == "research-full":
        # research-full only requires the "full" set; weibull is optional
        research_expected = MODE_REQUIRED_COMPONENTS["full"]
        all_loaded = all(
            quality.model_components.get(c) == "loaded_from_artifact"
            for c in research_expected
        )

    if all_loaded:
        quality.pipeline_status = "full"
    elif len(used_components) >= 2:
        quality.pipeline_status = "degraded"
    else:
        quality.pipeline_status = "failed"

    # ── 11. Assemble result ──
    result = {
        "home_team": home_team,
        "away_team": away_team,
        "competition": competition,
        "is_neutral": is_neutral,
        "home_win_prob": fused["home_win_prob"],
        "draw_prob": fused["draw_prob"],
        "away_win_prob": fused["away_win_prob"],
        "home_xg": dc_pred.get("home_xg", 0),
        "away_xg": dc_pred.get("away_xg", 0),
        "top_scores": dc_pred.get("top3_scores", []),
        "components_used": used_components,
        "weight_config": wc,
        "risk_tags": dc_pred.get("risk_tags", []),
        "confidence_penalty": dc_pred.get("confidence_penalty", 0.0),
        "mode": mode,
        "artifacts_used": used_components,
    }

    return result, quality, timer


# ── Report formatter ───────────────────────────────────────────────────────


def _format_weibull_status(quality: RunQuality) -> str:
    status = quality.model_components.get("weibull", "skipped")
    if status == "loaded_from_artifact":
        return "available (applied)"
    if status == "unavailable":
        return "unavailable (not required for this mode)"
    if status == "failed":
        return "failed"
    return "skipped"


def format_report(
    result: dict[str, Any],
    quality: RunQuality,
    timer: PredictionTimer,
    args: argparse.Namespace,
) -> str:
    """Render the human-readable prediction report."""
    sep = "=" * 60
    mode_label = MODE_LABELS.get(args.mode, args.mode)
    weibull_status = _format_weibull_status(quality)

    lines = [
        f"WC26 Predict v{VERSION} — Artifact Inference (mode: {mode_label})",
        "",
        f"  {result['home_team']} vs {result['away_team']}",
        f"  {result['competition']} | Neutral: {result['is_neutral']}",
        "",
        sep,
        "RUN QUALITY",
        sep,
        f"  pipeline_status: {quality.pipeline_status}",
        f"  mode: {mode_label}",
        f"  artifacts_used: {result.get('artifacts_used', [])}",
        f"  weibull: {weibull_status}",
    ]

    if quality.warnings:
        for w in quality.warnings:
            lines.append(f"  warning: {w}")

    if quality.pipeline_status == "degraded":
        lines.append("  NOTE: Not all components loaded — partial inference.")

    # Timings
    lines.extend([
        "",
        sep,
        "TIMINGS",
        sep,
    ])
    timings = timer.steps
    for step_name in [
        "load_registry", "load_df", "load_dc", "load_enhancer",
        "load_elo", "load_pi", "dc_predict", "enhancer_predict",
        "elo_predict", "pi_predict", "fusion",
    ]:
        sec = timings.get(step_name, 0.0)
        lines.append(f"  {step_name:20s} {sec:>6.2f}s")

    render_sec = timings.get("render_report", 0.0)
    lines.append(f"  {'render_report':20s} {render_sec:>6.2f}s")
    lines.append(f"  {'TOTAL':-<28s} {timer.total():>6.2f}s")

    # Prediction
    lines.extend([
        "",
        sep,
        "PREDICTION",
        sep,
        f"  Home Win:  {result['home_win_prob']:.4f} ({result['home_win_prob'] * 100:.1f}%)",
        f"  Draw:      {result['draw_prob']:.4f} ({result['draw_prob'] * 100:.1f}%)",
        f"  Away Win:  {result['away_win_prob']:.4f} ({result['away_win_prob'] * 100:.1f}%)",
    ])

    # xG
    lines.append("")
    lines.append(
        f"  xG: {result['home_team']} {result['home_xg']:.2f} - "
        f"{result['away_team']} {result['away_xg']:.2f}"
    )

    # Top scores
    if result.get("top_scores"):
        lines.append("")
        lines.append("  Top Scores:")
        for s in result["top_scores"][:5]:
            bar = "#" * int(s["prob"] * 160) if s["prob"] > 0 else ""
            lines.append(
                f"    {s['score']}  {s['prob']:.4f} ({s['prob'] * 100:5.2f}%) |{bar}"
            )

    # Components active + risk tags
    lines.append("")
    lines.append(f"  Components active: {result['components_used']}")
    if result.get("risk_tags"):
        lines.append(f"  Risk tags: {result['risk_tags']}")

    # Disclaimer
    lines.extend([
        "",
        sep,
        "DISCLAIMER: Internal research only. Not betting advice.",
        sep,
    ])
    return "\n".join(lines)


# ── CLI ────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=f"WC26 Predict v{VERSION} — artifact-based single-match prediction"
    )
    p.add_argument("--home", required=True, help="Home team name")
    p.add_argument("--away", required=True, help="Away team name")
    p.add_argument("--competition", required=True, help="Competition name")
    p.add_argument("--neutral", action="store_true", help="Neutral venue")
    p.add_argument(
        "--mode",
        choices=["baseline", "standard", "full", "research-full"],
        default="full",
        help=(
            "baseline=DC only | standard=DC+Enhancer+Elo | "
            "full=DC+Enhancer+Elo+Pi | research-full=full+Weibull+market-shadow"
        ),
    )
    p.add_argument(
        "--allow-retrain",
        action="store_true",
        help="Allow .fit() calls (fallback to training, NOT artifact inference)",
    )
    p.add_argument("--output", choices=["text", "json"], default="text")
    p.add_argument(
        "--require-full",
        action="store_true",
        help="Exit with error if pipeline_status != full",
    )
    return p.parse_args()


# ── Main ───────────────────────────────────────────────────────────────────


def main() -> None:
    args = parse_args()

    print(
        f"WC26 Predict v{VERSION} — Artifact Inference (mode: {args.mode})",
        flush=True,
    )
    print(
        f"  {args.home} vs {args.away} | {args.competition} | "
        f"Neutral: {args.neutral}",
        flush=True,
    )
    print(flush=True)

    # ── Allow-retrain mode: fallback to old .fit() behavior ──
    if args.allow_retrain:
        print("  WARNING: --allow-retrain enabled — using .fit() instead of artifacts\n", flush=True)
        result, quality, timer = _run_retrain_pipeline(args)
    else:
        result, quality, timer = run_artifact_pipeline(
            home_team=args.home,
            away_team=args.away,
            competition=args.competition,
            is_neutral=args.neutral,
            mode=args.mode,
        )

    # ── require-full check ──
    if args.require_full and quality.pipeline_status != "full":
        missing = [
            c for c in MODE_REQUIRED_COMPONENTS.get(args.mode, [])
            if quality.model_components.get(c) != "loaded_from_artifact"
        ]
        print(f"\n[FATAL] --require-full specified but pipeline_status={quality.pipeline_status}", flush=True)
        print(f"  Missing/failed components: {missing}", flush=True)
        print(json.dumps({
            "ok": False,
            "requested_mode": args.mode,
            "pipeline_status": "failed_full_required",
            "missing_components": missing,
            "message": "Full pipeline required but components missing/not loaded.",
        }, indent=2, ensure_ascii=False))
        sys.exit(1)

    # ── Output ──
    if args.output == "json":
        report = {
            **result,
            "run_quality": quality.to_dict(),
            "timings": timer.to_dict(),
            "total_seconds": round(timer.total(), 3),
        }
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    else:
        timer.start("render_report")
        report = format_report(result, quality, timer, args)
        timer.stop()
        # Re-render with final timing line
        report = format_report(result, quality, timer, args)
        print(report)


# ── Retrain fallback (legacy, for --allow-retrain) ─────────────────────────


def _run_retrain_pipeline(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], RunQuality, PredictionTimer]:
    """Run the old .fit()-based pipeline (for --allow-retrain).

    Mirrors the v1.91 behavior. Only used when --allow-retrain is set.
    """
    timer = PredictionTimer()
    quality = RunQuality()
    component_probs: dict[str, Any] = {}

    # Data
    training_df = _load_training_df(timer)
    match_date = training_df["match_date"].max().to_pydatetime()
    wc = get_weight_config(args.competition)
    print(
        f"  [weights] {wc.label} DC={wc.dc:.2f} Enh={wc.enhancer:.2f} "
        f"Elo={wc.elo:.2f} Pi={wc.pi:.2f} Wb={wc.weibull:.2f}",
        flush=True,
    )

    # DC
    timer.start("dc_fit")
    dc = DixonColesModel()
    dc.fit(training_df)
    timer.stop()
    quality.model_components["dixon_coles"] = "used"

    timer.start("dc_predict")
    dc_pred = dc.predict_match(args.home, args.away, is_neutral_venue=args.neutral)
    timer.stop()
    print(f"  [DC] H={dc_pred['home_win_prob']:.3f} D={dc_pred['draw_prob']:.3f} A={dc_pred['away_win_prob']:.3f}", flush=True)
    component_probs["dixon_coles"] = {
        "home": dc_pred["home_win_prob"],
        "draw": dc_pred["draw_prob"],
        "away": dc_pred["away_win_prob"],
    }
    fused = dict(dc_pred)

    # Enhancer (standard+)
    if args.mode in ("standard", "full", "research-full"):
        timer.start("enhancer_fit")
        enhancer = TabularMatchEnhancer()
        enhancer.fit(training_df)
        timer.stop()
        quality.model_components["tabular_enhancer"] = "used"

        timer.start("enhancer_predict")
        enh_pred = enhancer.predict_match(
            home_team=args.home, away_team=args.away,
            match_date=match_date, competition_weight=0.5,
            is_neutral_venue=args.neutral, training_df=training_df,
        )
        timer.stop()
        print(f"  [Enhancer] H={enh_pred['home_win_prob']:.3f} D={enh_pred['draw_prob']:.3f} A={enh_pred['away_win_prob']:.3f}", flush=True)
        component_probs["enhancer"] = {
            "home": enh_pred["home_win_prob"],
            "draw": enh_pred["draw_prob"],
            "away": enh_pred["away_win_prob"],
        }

        timer.start("fusion")
        fused = fuse_outcome_probabilities(fused, enh_pred, base_weight=wc.dc)
        timer.stop()
        print(f"  [DC+Enh] H={fused['home_win_prob']:.3f} D={fused['draw_prob']:.3f} A={fused['away_win_prob']:.3f}", flush=True)

    # Elo (standard+)
    if args.mode in ("standard", "full", "research-full"):
        timer.start("elo_fit")
        elo = EloRatingSystem()
        elo.fit(training_df)
        timer.stop()
        quality.model_components["elo"] = "used"

        timer.start("elo_predict")
        elo_pred = elo.predict(args.home, args.away, is_neutral=args.neutral, competition_weight=0.5, competition=args.competition)
        timer.stop()
        print(f"  [Elo] H={elo_pred.home_win_prob:.3f} D={elo_pred.draw_prob:.3f} A={elo_pred.away_win_prob:.3f}", flush=True)
        component_probs["elo"] = {
            "home": elo_pred.home_win_prob,
            "draw": elo_pred.draw_prob,
            "away": elo_pred.away_win_prob,
        }

        timer.start("fusion")
        fused = fuse_elo_probabilities(fused, elo_pred, elo_weight=wc.elo)
        timer.stop()
        print(f"  [+Elo] H={fused['home_win_prob']:.3f} D={fused['draw_prob']:.3f} A={fused['away_win_prob']:.3f}", flush=True)

    # Pi (full+)
    if args.mode in ("full", "research-full"):
        timer.start("pi_fit")
        pi_model = PiRatingWrapper()
        pi_model.fit(training_df)
        timer.stop()
        quality.model_components["pi_rating"] = "used"

        timer.start("pi_predict")
        try:
            pi_pred = pi_model.predict(args.home, args.away, args.neutral)
            timer.stop()
            print(f"  [Pi] H={pi_pred['home_win_prob']:.3f} D={pi_pred['draw_prob']:.3f} A={pi_pred['away_win_prob']:.3f}", flush=True)
            component_probs["pi_rating"] = {
                "home": pi_pred["home_win_prob"],
                "draw": pi_pred["draw_prob"],
                "away": pi_pred["away_win_prob"],
            }
            timer.start("fusion")
            fused = fuse_pi_probabilities(fused, pi_pred, pi_weight=wc.pi)
            timer.stop()
            print(f"  [+Pi] H={fused['home_win_prob']:.3f} D={fused['draw_prob']:.3f} A={fused['away_win_prob']:.3f}", flush=True)
        except Exception as exc:
            timer.stop()
            quality.model_components["pi_rating"] = "failed"
            quality.mark_degraded(f"Pi-Rating failed: {exc}")
            print(f"  [Pi] FAILED: {exc}", flush=True)

    # Weibull (research-full only)
    if args.mode == "research-full":
        timer.start("weibull_fit")
        wb = WeibullWrapper()
        wb_fitted = wb.fit(training_df, timeout=60)
        timer.stop()
        if wb_fitted:
            quality.model_components["weibull"] = "used"
            timer.start("weibull_predict")
            wb_pred = wb.predict(args.home, args.away, args.neutral)
            timer.stop()
            if wb_pred:
                timer.start("fusion")
                fused = fuse_weibull_probs(fused, wb_pred, wb_weight=wc.weibull)
                timer.stop()
                print(f"  [+Weibull] H={fused['home_win_prob']:.3f} D={fused['draw_prob']:.3f} A={fused['away_win_prob']:.3f}", flush=True)
        else:
            quality.model_components["weibull"] = "failed"
            quality.mark_degraded("Weibull fit failed")
            print("  [Weibull] FAILED — continuing", flush=True)

    # Renormalize
    total = fused["home_win_prob"] + fused["draw_prob"] + fused["away_win_prob"]
    if abs(total - 1.0) > 0.001:
        fused["home_win_prob"] /= total
        fused["draw_prob"] /= total
        fused["away_win_prob"] /= total

    # Pipeline status
    expected = MODE_REQUIRED_COMPONENTS.get(args.mode, MODE_REQUIRED_COMPONENTS["full"])
    used_names = [c for c, s in quality.model_components.items() if s == "used"]
    all_used = all(
        quality.model_components.get(c) == "used"
        for c in expected
        if c != "weibull"
    )
    if args.mode == "research-full":
        all_used = all(
            quality.model_components.get(c) == "used"
            for c in MODE_REQUIRED_COMPONENTS["full"]
        )
    if all_used:
        quality.pipeline_status = "full"
    elif len(used_names) >= 2:
        quality.pipeline_status = "degraded"
    else:
        quality.pipeline_status = "failed"

    result = {
        "home_team": args.home,
        "away_team": args.away,
        "competition": args.competition,
        "is_neutral": args.neutral,
        "home_win_prob": fused["home_win_prob"],
        "draw_prob": fused["draw_prob"],
        "away_win_prob": fused["away_win_prob"],
        "home_xg": dc_pred.get("home_xg", 0),
        "away_xg": dc_pred.get("away_xg", 0),
        "top_scores": dc_pred.get("top3_scores", []),
        "components_used": used_names,
        "weight_config": wc,
        "risk_tags": dc_pred.get("risk_tags", []),
        "confidence_penalty": dc_pred.get("confidence_penalty", 0.0),
        "mode": args.mode,
        "artifacts_used": used_names,
    }
    return result, quality, timer


if __name__ == "__main__":
    main()
