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
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import pandas as pd

from app.services.prediction_timer import PredictionTimer
from app.services.run_quality import RunQuality
from app.services.weights import get_weight_config
from app.services.fusion_graph import FusionGraph, probs_dict_to_list
from app.services.dixon_coles import DixonColesModel
from app.services.tabular_match_model import (
    TabularMatchEnhancer,
    fuse_outcome_probabilities,
)
from app.services.weibull_model import WeibullWrapper, fuse_weibull_probs
from app.services.elo_ratings import EloRatingSystem, fuse_elo_probabilities
from app.services.pi_ratings import PiRatingWrapper, fuse_pi_probabilities
from app.version import VERSION
from app.services.prediction_core import (
    run_artifact_pipeline,
    MODE_REQUIRED_COMPONENTS,
    MODE_LABELS,
    _load_dc,
    _load_enhancer,
    _load_elo,
    _load_pi,
    _load_training_df,
    _try_load_weibull,
)


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

    # Fusion diagnostics
    fg_data = result.get("fusion_graph", {})
    if fg_data:
        lines.extend([
            "",
            sep,
            "FUSION DIAGNOSTICS",
            sep,
        ])
        bp = fg_data.get("blend_params", {})
        lines.append(f"  blend_params:  dc={bp.get('dc_weight', 0):.3f}  "
                      f"elo={bp.get('elo_weight', 0):.3f}  pi={bp.get('pi_weight', 0):.3f}")
        ew = fg_data.get("effective_weights", {})
        lines.append(f"  effective:     dc={ew.get('dc_effective', 0):.3f}  "
                      f"enh={ew.get('enhancer_effective', 0):.3f}  "
                      f"elo={ew.get('elo_effective', 0):.3f}  pi={ew.get('pi_effective', 0):.3f}")
        md = fg_data.get("model_disagreement", {})
        lines.append(f"  disagreement:  max_home_diff={md.get('max_home_diff', 0):.4f}")
        for step in fg_data.get("steps", []):
            after = step.get("after", [])
            lines.append(
                f"  step {step['name']:20s}  [{after[0]:.4f} {after[1]:.4f} {after[2]:.4f}]  "
                f"({step['formula']})"
            )

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
    fg = FusionGraph(blend_params={
        "dc_weight": wc.dc,
        "elo_weight": wc.elo,
        "pi_weight": wc.pi,
    })
    fg.compute_effective_weights()
    eff = fg.effective_weights
    print(
        f"  [weights] {wc.label} DC={wc.dc:.2f} Enh={wc.enhancer:.2f} "
        f"Elo={wc.elo:.2f} Pi={wc.pi:.2f} Wb={wc.weibull:.2f}",
        flush=True,
    )
    print(
        f"  [effective]  dc={eff['dc_effective']:.3f}  enh={eff['enhancer_effective']:.3f}  "
        f"elo={eff['elo_effective']:.3f}  pi={eff['pi_effective']:.3f}",
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
        before_r1 = {
            "dixon_coles": probs_dict_to_list(component_probs["dixon_coles"]),
            "enhancer": probs_dict_to_list(component_probs["enhancer"]),
        }
        fused = fuse_outcome_probabilities(fused, enh_pred, base_weight=wc.dc)
        fg.add_step("dc+enhancer", f"base_weight={wc.dc}", before_r1, probs_dict_to_list(fused))
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
        before_r2 = {
            "dc+enhancer": probs_dict_to_list(fused),
            "elo": [elo_pred.home_win_prob, elo_pred.draw_prob, elo_pred.away_win_prob],
        }
        fused = fuse_elo_probabilities(fused, elo_pred, elo_weight=wc.elo)
        fg.add_step("+elo", f"elo_weight={wc.elo}", before_r2, probs_dict_to_list(fused))
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
            before_r3 = {
                "dc+enhancer+elo": probs_dict_to_list(fused),
                "pi_rating": probs_dict_to_list(component_probs["pi_rating"]),
            }
            fused = fuse_pi_probabilities(fused, pi_pred, pi_weight=wc.pi)
            fg.add_step("+pi", f"pi_weight={wc.pi}", before_r3, probs_dict_to_list(fused))
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
                component_probs["weibull"] = {
                    "home": wb_pred.get("home_win_prob", wb_pred.get("home", 0)),
                    "draw": wb_pred.get("draw_prob", wb_pred.get("draw", 0)),
                    "away": wb_pred.get("away_win_prob", wb_pred.get("away", 0)),
                }
                timer.start("fusion")
                before_rw = {k: probs_dict_to_list(fused) for k in ["dc+enhancer+elo+pi"]}
                before_rw["weibull"] = probs_dict_to_list(component_probs["weibull"])
                fused = fuse_weibull_probs(fused, wb_pred, wb_weight=wc.weibull)
                fg.add_step("+weibull", f"wb_weight={wc.weibull}", before_rw, probs_dict_to_list(fused))
                timer.stop()
                print(f"  [+Weibull] H={fused['home_win_prob']:.3f} D={fused['draw_prob']:.3f} A={fused['away_win_prob']:.3f}", flush=True)
        else:
            quality.model_components["weibull"] = "failed"
            quality.mark_degraded("Weibull fit failed")
            print("  [Weibull] FAILED — continuing", flush=True)

    # Fusion diagnostics
    fg.compute_disagreement(component_probs)

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
        "fusion_graph": fg.to_dict(),
    }
    return result, quality, timer


if __name__ == "__main__":
    main()
