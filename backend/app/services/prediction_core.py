"""prediction_core.py — legacy compatibility shim for old artifact prediction.

The current entry point is PredictionPipeline.from_artifacts(...).predict_sync(...).
Older imports are kept here to avoid import-time breakage while callers migrate.

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
    """Load Dixon-Coles model, preferring disk cache over static pickle artifact.

    Cache priority:
      1. Disk cache (model_artifacts/dc_cache/) — freshest, updated by snapshot runs
      2. Static artifact (artifacts/models/dc.pkl) — frozen baseline, June 4

    The disk cache is updated whenever snapshot.py retrains on fresh DB data.
    Using it ensures ``from_artifacts()`` predictions stay in sync with the
    latest available training data.
    """
    timer.start("load_dc")

    # 1. Try disk cache for World Cup (most common competition)
    try:
        from app.services.model_cache_disk import _cache_dir as _dc_cache_dir
        dc = _try_load_dc_from_disk(_dc_cache_dir(), timer)
        if dc is not None:
            timer.stop()
            return dc
    except Exception:
        logger.debug("Disk cache DC lookup failed, falling back to artifact", exc_info=True)

    # 2. Fallback: static artifact
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


def _try_load_dc_from_disk(
    cache_dir: Path, timer: PredictionTimer
) -> DixonColesModel | None:
    """Attempt to reconstruct a DixonColesModel from the latest disk cache file.

    Scans for ``dc_*`` files, picks the newest, and reconstructs.
    Returns None if no suitable cache exists or reconstruction fails.
    """
    import glob as _glob
    import os as _os

    dc_files = sorted(
        _glob.glob(str(cache_dir / "dc_*.pkl")),
        key=lambda p: _os.path.getmtime(p),
    )
    if not dc_files:
        return None

    latest_path = Path(dc_files[-1])
    artifact_mtime = DC_PATH.stat().st_mtime if DC_PATH.exists() else 0.0
    cache_mtime = latest_path.stat().st_mtime

    if cache_mtime <= artifact_mtime:
        logger.debug(
            "Disk cache DC (%s) is not newer than artifact; using artifact",
            latest_path.name,
        )
        return None

    try:
        with open(latest_path, "rb") as f:
            cached = pickle.load(f)
    except Exception as exc:
        logger.warning("Disk cache DC load failed: %s", exc)
        return None

    from app.services.model_cache import CachedDC, ModelCache
    from app.services.dixon_coles import DixonColesModel

    if isinstance(cached, DixonColesModel):
        # Some caches store the full model directly
        logger.info(
            "DC loaded from disk cache: %s (age=%.1fh, %d teams)",
            latest_path.name,
            (timer._started_at or 0) and 0.0,  # approximate
            len(cached.attack_params),
        )
        return cached

    if isinstance(cached, CachedDC):
        dc = DixonColesModel()
        mc = ModelCache()
        mc.restore_dc(cached, dc)
        logger.info(
            "DC reconstructed from disk cache: %s (teams=%d)",
            latest_path.name,
            len(cached.attack_params),
        )
        return dc

    logger.warning(
        "Unexpected DC cache type %s in %s; falling back to artifact",
        type(cached).__name__,
        latest_path.name,
    )
    return None


def _load_enhancer(timer: PredictionTimer) -> TabularMatchEnhancer:
    """Load TabularMatchEnhancer, preferring disk cache over static joblib artifact.

    Cache priority:
      1. Disk cache (model_artifacts/dc_cache/) — freshest, updated by snapshot runs
      2. Static artifact (artifacts/models/enhancer.joblib) — frozen baseline, June 4
    """
    timer.start("load_enhancer")

    # 1. Try disk cache
    try:
        from app.services.model_cache_disk import _cache_dir as _enh_cache_dir
        enh = _try_load_enhancer_from_disk(_enh_cache_dir(), timer)
        if enh is not None:
            timer.stop()
            return enh
    except Exception:
        logger.debug(
            "Disk cache Enhancer lookup failed, falling back to artifact",
            exc_info=True,
        )

    # 2. Fallback: static artifact
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


def _try_load_enhancer_from_disk(
    cache_dir: Path, timer: PredictionTimer
) -> TabularMatchEnhancer | None:
    """Attempt to reconstruct a TabularMatchEnhancer from the latest disk cache.

    Scans for ``enhancer_*`` files, picks the newest, and reconstructs.
    Returns None if no suitable cache exists or reconstruction fails.
    """
    import glob as _glob
    import os as _os
    import warnings as _warnings

    enh_files = sorted(
        _glob.glob(str(cache_dir / "enhancer_*.pkl")),
        key=lambda p: _os.path.getmtime(p),
    )
    if not enh_files:
        return None

    latest_path = Path(enh_files[-1])
    artifact_mtime = ENHANCER_PATH.stat().st_mtime if ENHANCER_PATH.exists() else 0.0
    cache_mtime = latest_path.stat().st_mtime

    if cache_mtime <= artifact_mtime:
        logger.debug(
            "Disk cache Enhancer (%s) is not newer than artifact; using artifact",
            latest_path.name,
        )
        return None

    # Suppress sklearn version mismatch warnings during disk cache loading.
    # Disk caches may be trained with sklearn 1.9.0 while runtime uses 1.8.0.
    # The models are structurally compatible; minor prediction differences
    # are expected but no worse than falling back to the stale artifact.
    try:
        with _warnings.catch_warnings():
            _warnings.simplefilter("ignore", category=UserWarning)
            with open(latest_path, "rb") as f:
                cached = pickle.load(f)
    except Exception as exc:
        logger.warning("Disk cache Enhancer load failed: %s", exc)
        return None

    from app.services.model_cache import CachedEnhancer, ModelCache
    from app.services.tabular_match_model import TabularMatchEnhancer

    if isinstance(cached, TabularMatchEnhancer):
        logger.info(
            "Enhancer loaded from disk cache: %s (samples=%d)",
            latest_path.name,
            cached.training_sample_count if hasattr(cached, "training_sample_count") else 0,
        )
        return cached

    if isinstance(cached, CachedEnhancer):
        enhancer = TabularMatchEnhancer()
        mc = ModelCache()
        mc.restore_enhancer(cached, enhancer)
        logger.info(
            "Enhancer reconstructed from disk cache: %s (samples=%d)",
            latest_path.name,
            cached.training_sample_count,
        )
        return enhancer

    logger.warning(
        "Unexpected Enhancer cache type %s in %s; falling back to artifact",
        type(cached).__name__,
        latest_path.name,
    )
    return None


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
    """Legacy artifact-pipeline entry point; use PredictionPipeline instead.

    **Migration (sync, no DB):**
        pipeline = PredictionPipeline.from_artifacts(mode=mode)
        result = pipeline.predict_sync(home_team, away_team, competition,
                                       is_neutral=is_neutral)
        # result is a PredictionResult dataclass with .home_win_prob, .draw_prob, etc.

    **Migration (async, DB-aware):**
        pipeline = await PredictionPipeline.from_snapshot_env(...)
        result = await pipeline.predict_match(home_team, away_team, competition,
                                              is_neutral=is_neutral)
    """
    raise RuntimeError(
        "run_artifact_pipeline is not available in the current V3.5 branch. "
        "Use PredictionPipeline.from_artifacts(mode=mode).predict_sync(...) instead.\n"
        "Example:\n"
        "  pipeline = PredictionPipeline.from_artifacts(mode='full')\n"
        "  result = pipeline.predict_sync('Qatar', 'Switzerland', "
        "'FIFA World Cup 2026', is_neutral=True)\n"
        "  print(f'H={result.home_win_prob:.3f} D={result.draw_prob:.3f} "
        "A={result.away_win_prob:.3f}')"
    )


# ── Snapshot persistence ───────────────────────────────────────────────────────


def _save_snapshot_from_pipeline(
    result: dict[str, Any],
    quality: "RunQuality",
    component_probs: dict[str, dict[str, float]],
    fg: "FusionGraph",
    wc: "WeightConfig",
    injury_signals_count: int = 0,
    news_signals_count: int = 0,
    news_signal_ids: list[str] | None = None,
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
            news_signal_ids=news_signal_ids or [],
        )
    except Exception:
        logger.debug(
            "PreMatchSnapshot save skipped (non-critical)", exc_info=True
        )
