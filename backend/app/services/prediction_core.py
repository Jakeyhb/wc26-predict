"""prediction_core.py — WC26 Predict artifact-based prediction engine.

Shared by CLI (predict_match.py) and Dashboard.
Loads pre-trained models from backend/artifacts/ — NO .fit() calls.

Provides:
    run_artifact_pipeline(home_team, away_team, competition, is_neutral, mode)
        -> (result_dict, RunQuality, PredictionTimer)
"""

from __future__ import annotations

import json
import logging
import pickle
import re
import sys
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

# ── Path setup ───────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

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
from app.services.injury_data import fuse_injury_signals
from app.services.fusion_graph import FusionGraph, probs_dict_to_list
from app.services.signal_adjuster_sync import apply_signal_adjustments, load_approved_signals

logger = logging.getLogger(__name__)

# ── Artifact paths (relative to backend/) ────────────────────────────────────
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
MODE_REQUIRED_COMPONENTS: dict[str, list[str]] = {
    "baseline": ["dixon_coles"],
    "standard": ["dixon_coles", "tabular_enhancer", "elo"],
    "full": ["dixon_coles", "tabular_enhancer", "elo", "pi_rating"],
    "research-full": ["dixon_coles", "tabular_enhancer", "elo", "pi_rating"],
}

MODE_LABELS: dict[str, str] = {
    "baseline": "baseline",
    "standard": "standard",
    "full": "full",
    "research-full": "research-full",
}


# ── Artifact loaders ─────────────────────────────────────────────────────────


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
        raise ValueError(
            "Loaded DC model has empty attack_params — artifact appears un-fitted"
        )
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
        raise TypeError(
            f"Expected TabularMatchEnhancer, got {type(enhancer).__name__}"
        )
    if not enhancer.is_fitted:
        raise ValueError(
            "Loaded enhancer is not fitted — artifact appears invalid. "
            "Retrain with train_models.py"
        )
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
    pi_model = PiRatingWrapper()
    pi_model.team_ratings = {str(k): float(v) for k, v in pi_data.items()}
    timer.stop()
    return pi_model


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
            logger.info("  [load] Weibull model loaded from artifact")
            timer.stop()
            return wb
    except Exception as exc:
        logger.warning(f"  [load] Weibull load failed: {exc}")
    timer.stop()
    return None


def _load_training_df(timer: PredictionTimer) -> pd.DataFrame:
    """Load training DataFrame from artifact pickle, with SQLite fallback."""
    timer.start("load_df")
    try:
        if DF_PATH.exists():
            df = pd.read_pickle(str(DF_PATH))
            logger.info(
                f"  [data] Training DF: {len(df)} rows, "
                f"{df.home_team.nunique()} teams",
            )
            timer.stop()
            return df
    except Exception as exc:
        logger.warning(
            f"  [data] Pickle load failed ({exc}), trying SQLite..."
        )

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
    logger.info(
        f"  [data] Training DF: {len(df)} rows, "
        f"{df.home_team.nunique()} teams (SQLite)",
    )
    timer.stop()
    return df


# ── Pipeline runner ──────────────────────────────────────────────────────────


def run_artifact_pipeline(
    home_team: str,
    away_team: str,
    competition: str,
    is_neutral: bool,
    mode: str,
) -> tuple[dict[str, Any], RunQuality, PredictionTimer]:
    """Run artifact-based inference pipeline.

    Loads pre-trained models from artifacts/ — no .fit() calls.

    Returns (result_dict, run_quality, prediction_timer).
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
        msg = (
            f"Required artifacts missing: {missing}. Run train_models.py first."
        )
        logger.warning(
            json.dumps(
                {
                    "ok": False,
                    "error": "failed_missing_artifacts",
                    "mode": mode,
                    "missing_components": missing,
                    "message": msg,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        quality.pipeline_status = "failed"
        quality.warnings.append(msg)
        # Return degraded result rather than exiting (CLI can choose to exit)
        result: dict[str, Any] = {
            "home_team": home_team,
            "away_team": away_team,
            "competition": competition,
            "is_neutral": is_neutral,
            "home_win_prob": 0.333,
            "draw_prob": 0.334,
            "away_win_prob": 0.333,
            "home_xg": 0.0,
            "away_xg": 0.0,
            "top_scores": [],
            "components_used": [],
            "weight_config": None,
            "risk_tags": [],
            "confidence_penalty": 1.0,
            "mode": mode,
            "artifacts_used": [],
            "fusion_graph": {},
        }
        return result, quality, timer

    # ── 2. Weight config ──
    wc = get_weight_config(competition)
    fg = FusionGraph(
        blend_params={
            "dc_weight": wc.dc,
            "elo_weight": wc.elo,
            "pi_weight": wc.pi,
        }
    )
    fg.compute_effective_weights()
    eff = fg.effective_weights
    logger.info(
        f"  [weights] {wc.label}  DC={wc.dc:.2f}  Enh={wc.enhancer:.2f}  "
        f"Elo={wc.elo:.2f}  Pi={wc.pi:.2f}  Wb={wc.weibull:.2f}",
    )
    logger.info(
        f"  [effective]  dc={eff['dc_effective']:.3f}  "
        f"enh={eff['enhancer_effective']:.3f}  "
        f"elo={eff['elo_effective']:.3f}  pi={eff['pi_effective']:.3f}",
    )

    # ── 3. Load training DataFrame ──
    training_df = _load_training_df(timer)
    match_date = training_df["match_date"].max().to_pydatetime()

    # ── 4. Dixon-Coles ──
    dc = _load_dc(timer)
    quality.model_components["dixon_coles"] = "loaded_from_artifact"
    timer.start("dc_predict")
    dc_pred = dc.predict_match(home_team, away_team, is_neutral_venue=is_neutral)
    timer.stop()
    logger.info(
        f"  [DC] H={dc_pred['home_win_prob']:.3f}  "
        f"D={dc_pred['draw_prob']:.3f}  A={dc_pred['away_win_prob']:.3f}",
    )
    component_probs["dixon_coles"] = {
        "home": dc_pred["home_win_prob"],
        "draw": dc_pred["draw_prob"],
        "away": dc_pred["away_win_prob"],
    }

    fused: dict[str, float] = dict(dc_pred)

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
        logger.info(
            f"  [Enhancer] H={enh_pred['home_win_prob']:.3f}  "
            f"D={enh_pred['draw_prob']:.3f}  A={enh_pred['away_win_prob']:.3f}",
        )
        component_probs["enhancer"] = {
            "home": enh_pred["home_win_prob"],
            "draw": enh_pred["draw_prob"],
            "away": enh_pred["away_win_prob"],
        }

        # Fuse DC + Enhancer
        timer.start("fusion")
        before_step1 = {
            "dixon_coles": probs_dict_to_list(component_probs["dixon_coles"]),
            "enhancer": probs_dict_to_list(component_probs["enhancer"]),
        }
        fused = fuse_outcome_probabilities(fused, enh_pred, base_weight=wc.dc)
        fg.add_step(
            "dc+enhancer",
            f"base_weight={wc.dc}",
            before_step1,
            probs_dict_to_list(fused),
        )
        timer.stop()
        logger.info(
            f"  [DC+Enh] H={fused['home_win_prob']:.3f}  "
            f"D={fused['draw_prob']:.3f}  A={fused['away_win_prob']:.3f}",
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
        logger.info(
            f"  [Elo] H={elo_pred.home_win_prob:.3f}  "
            f"D={elo_pred.draw_prob:.3f}  A={elo_pred.away_win_prob:.3f}",
        )
        component_probs["elo"] = {
            "home": elo_pred.home_win_prob,
            "draw": elo_pred.draw_prob,
            "away": elo_pred.away_win_prob,
        }

        timer.start("fusion")
        before_step2 = {
            "dc+enhancer": probs_dict_to_list(fused),
            "elo": [
                elo_pred.home_win_prob,
                elo_pred.draw_prob,
                elo_pred.away_win_prob,
            ],
        }
        fused = fuse_elo_probabilities(fused, elo_pred, elo_weight=wc.elo)
        fg.add_step(
            "+elo", f"elo_weight={wc.elo}", before_step2, probs_dict_to_list(fused)
        )
        timer.stop()
        logger.info(
            f"  [+Elo] H={fused['home_win_prob']:.3f}  "
            f"D={fused['draw_prob']:.3f}  A={fused['away_win_prob']:.3f}",
        )

    # ── 7. Pi-Rating (full+) ──
    if mode in ("full", "research-full"):
        pi_model = _load_pi(timer)
        quality.model_components["pi_rating"] = "loaded_from_artifact"
        timer.start("pi_predict")
        try:
            pi_pred = pi_model.predict(home_team, away_team, is_neutral)
            timer.stop()
            logger.info(
                f"  [Pi] H={pi_pred['home_win_prob']:.3f}  "
                f"D={pi_pred['draw_prob']:.3f}  A={pi_pred['away_win_prob']:.3f}",
            )
            component_probs["pi_rating"] = {
                "home": pi_pred["home_win_prob"],
                "draw": pi_pred["draw_prob"],
                "away": pi_pred["away_win_prob"],
            }

            timer.start("fusion")
            before_step3 = {
                "dc+enhancer+elo": probs_dict_to_list(fused),
                "pi_rating": probs_dict_to_list(component_probs["pi_rating"]),
            }
            fused = fuse_pi_probabilities(fused, pi_pred, pi_weight=wc.pi)
            fg.add_step(
                "+pi",
                f"pi_weight={wc.pi}",
                before_step3,
                probs_dict_to_list(fused),
            )
            timer.stop()
            logger.info(
                f"  [+Pi] H={fused['home_win_prob']:.3f}  "
                f"D={fused['draw_prob']:.3f}  A={fused['away_win_prob']:.3f}",
            )
        except Exception as exc:
            timer.stop()
            quality.model_components["pi_rating"] = "failed"
            quality.mark_degraded(
                f"Pi-Rating artifact prediction failed: {exc}"
            )
            logger.warning(
                f"  [Pi] FAILED: {exc} — continuing without Pi"
            )

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
                    component_probs["weibull"] = {
                        "home": wb_pred.get(
                            "home_win_prob", wb_pred.get("home", 0)
                        ),
                        "draw": wb_pred.get(
                            "draw_prob", wb_pred.get("draw", 0)
                        ),
                        "away": wb_pred.get(
                            "away_win_prob", wb_pred.get("away", 0)
                        ),
                    }
                    timer.start("fusion")
                    before_wb = {
                        "dc+enhancer+elo+pi": probs_dict_to_list(fused),
                        "weibull": probs_dict_to_list(
                            component_probs["weibull"]
                        ),
                    }
                    fused = fuse_weibull_probs(
                        fused, wb_pred, wb_weight=wc.weibull
                    )
                    fg.add_step(
                        "+weibull",
                        f"wb_weight={wc.weibull}",
                        before_wb,
                        probs_dict_to_list(fused),
                    )
                    timer.stop()
                    logger.info(
                        f"  [+Weibull] H={fused['home_win_prob']:.3f}  "
                        f"D={fused['draw_prob']:.3f}  "
                        f"A={fused['away_win_prob']:.3f}",
                    )
                else:
                    timer.stop()
                    logger.info(
                        "  [Weibull] predict returned None — skipping",
                    )
            except Exception as exc:
                timer.stop()
                logger.warning(
                    f"  [Weibull] prediction failed: {exc} — skipping",
                )
        else:
            quality.model_components["weibull"] = "unavailable"
            logger.info(
                "  [Weibull] artifact not found — optional, continuing",
            )

    # ── 9. Fusion diagnostics ──
    fg.compute_disagreement(component_probs)

    # ── 10. Renormalize ──
    total = fused["home_win_prob"] + fused["draw_prob"] + fused["away_win_prob"]
    if abs(total - 1.0) > 0.001:
        fused["home_win_prob"] /= total
        fused["draw_prob"] /= total
        fused["away_win_prob"] /= total

    # ── 11. Pipeline status ──
    used_components = [
        c
        for c, s in quality.model_components.items()
        if s == "loaded_from_artifact"
    ]
    expected = MODE_REQUIRED_COMPONENTS.get(mode, [])
    if mode == "research-full":
        expected = MODE_REQUIRED_COMPONENTS["full"]

    all_loaded = all(
        quality.model_components.get(c) == "loaded_from_artifact"
        for c in expected
    )

    if all_loaded:
        quality.pipeline_status = "full"
    elif len(used_components) >= 2:
        quality.pipeline_status = "degraded"
    else:
        quality.pipeline_status = "failed"

    # ── 12. Injury data (best-effort, optional) ──
    injury_signals: list[dict[str, Any]] = []
    try:
        from app.services.injury_data import InjuryDataService
        injury_svc = InjuryDataService()
        injury_records = injury_svc.load()
        if injury_records:
            quality.model_components["injury_data"] = "loaded"
            # Filter to relevant teams
            relevant = [
                r for r in injury_records
                if r.team_name.lower() in (home_team.lower(), away_team.lower())
            ]
            if relevant:
                # Convert to dict format expected by fuse_injury_signals
                injury_dicts = [
                    {
                        "team_name": r.team_name,
                        "player_name": r.player_name,
                        "status": r.status,
                        "confidence": r.confidence,
                    }
                    for r in relevant
                ]
                fused = fuse_injury_signals(
                    fused, injury_dicts, home_team=home_team, away_team=away_team
                )
                quality.model_components["injury_data"] = "applied"
                injury_signals = injury_dicts
                logger.info(
                    f"  [Injury] {len(relevant)} records applied — "
                    f"H={fused['home_win_prob']:.3f} "
                    f"D={fused['draw_prob']:.3f} "
                    f"A={fused['away_win_prob']:.3f}"
                )
    except Exception as exc:
        logger.debug(f"  [Injury] Skipped: {exc}")

    # ── 13. News signals (best-effort, optional) ──
    signal_risk_tags: list[str] = []
    approved_signals_count = 0
    try:
        approved = load_approved_signals(home_team, away_team)
        if approved:
            approved_signals_count = len(approved)
            (
                fused["home_win_prob"],
                fused["draw_prob"],
                fused["away_win_prob"],
                signal_risk_tags,
            ) = apply_signal_adjustments(
                home_prob=fused["home_win_prob"],
                draw_prob=fused["draw_prob"],
                away_prob=fused["away_win_prob"],
                home_team=home_team,
                away_team=away_team,
                signals=approved,
            )
            quality.model_components["news_signals"] = "applied"
            logger.info(
                f"  [Signals] {len(approved)} approved signals applied — "
                f"H={fused['home_win_prob']:.3f} "
                f"D={fused['draw_prob']:.3f} "
                f"A={fused['away_win_prob']:.3f}"
            )
    except Exception as exc:
        logger.debug(f"  [Signals] Skipped: {exc}")

    # ── 14. Assemble result ──
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
        "risk_tags": dc_pred.get("risk_tags", []) + signal_risk_tags,
        "injury_signals_applied": len(injury_signals),
        "news_signals_applied": approved_signals_count,
        "confidence_penalty": dc_pred.get("confidence_penalty", 0.0),
        "mode": mode,
        "artifacts_used": used_components,
        "fusion_graph": fg.to_dict(),
    }

    # ── 14. Save pre-match snapshot (non-blocking, best-effort) ──
    _save_snapshot_from_pipeline(
        result=result,
        quality=quality,
        component_probs=component_probs,
        fg=fg,
        wc=wc,
        injury_signals_count=len(injury_signals),
        news_signals_count=approved_signals_count,
    )

    return result, quality, timer


# ── Snapshot persistence ───────────────────────────────────────────────────────


def _save_snapshot_from_pipeline(
    result: dict[str, Any],
    quality: "RunQuality",
    component_probs: dict[str, dict[str, float]],
    fg: "FusionGraph",
    wc: "WeightConfig",
    injury_signals_count: int = 0,
    news_signals_count: int = 0,
) -> None:
    """Save a PreMatchSnapshot to the database (best-effort, never throws)."""
    try:
        from app.services.snapshot_service import save_pre_match_snapshot
        from app.version import VERSION, get_git_commit

        # Collect risk tags from all sources
        risk_tags = list(result.get("risk_tags", []))
        if quality.warnings:
            risk_tags.extend(quality.warnings)

        # Detect model disagreement as a risk flag
        max_diff = (
            fg.model_disagreement.get("max_home_diff", 0.0)
            if fg.model_disagreement
            else 0.0
        )
        if max_diff > 0.30:
            risk_tags.append(f"high_model_disagreement_{max_diff:.2f}")

        # Convert degraded reasons
        degraded: list[dict[str, str]] = []
        for w in quality.warnings:
            degraded.append({
                "source": "pipeline",
                "reason": w,
                "severity": "warning",
            })

        save_pre_match_snapshot(
            home_team=result["home_team"],
            away_team=result["away_team"],
            competition=result["competition"],
            is_neutral=result.get("is_neutral", False),
            prediction_mode=result.get("mode", "full"),
            final_home_prob=result["home_win_prob"],
            final_draw_prob=result["draw_prob"],
            final_away_prob=result["away_win_prob"],
            home_xg=result.get("home_xg"),
            away_xg=result.get("away_xg"),
            top_scores=result.get("top_scores", []),
            component_probs=component_probs,
            weight_config_label=getattr(wc, "label", ""),
            weight_config=wc.to_dict() if hasattr(wc, "to_dict") else None,
            effective_weights=fg.effective_weights,
            fusion_graph=fg.to_dict(),
            model_disagreement=max_diff,
            confidence="medium",
            confidence_penalty=result.get("confidence_penalty", 0.0),
            risk_tags=risk_tags,
            pipeline_status=quality.pipeline_status,
            missing_inputs=[],
            degraded_reasons=degraded,
            code_version=VERSION,
            git_commit=get_git_commit(),
            injury_data_available=injury_signals_count > 0,
            news_signals_available=news_signals_count > 0,
        )
    except Exception:
        logger.debug(
            "PreMatchSnapshot save skipped (non-critical)", exc_info=True
        )
