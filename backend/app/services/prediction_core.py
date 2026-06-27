"""prediction_core.py — shared model-loading helpers for the prediction pipeline.

The current entry point is PredictionPipeline.from_artifacts(...).predict_sync(...)
or scripts/predict_match_full.py for the full pipeline (DC → Enhancer → Elo → Pi → Market).

Provides:
    _load_dc, _load_enhancer, _load_elo, _load_pi, _load_training_df
        → model objects ready for prediction
"""

from __future__ import annotations

import json
import logging
import pickle
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

# ── Path setup ───────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.prediction_timer import PredictionTimer
from app.services.run_quality import RunQuality
from app.services.dixon_coles import DixonColesModel
from app.services.tabular_match_model import TabularMatchEnhancer
from app.services.weibull_model import WeibullWrapper
from app.services.elo_ratings import EloRatingSystem
from app.services.pi_ratings import PiRatingWrapper
from app.services.weights import get_weight_config
from app.services.fusion_graph import FusionGraph

logger = logging.getLogger(__name__)

# ── Artifact paths (relative to backend/) ────────────────────────────────────
ARTIFACTS_DIR = BACKEND_DIR / "artifacts"
MODELS_DIR = ARTIFACTS_DIR / "models"
RATINGS_DIR = ARTIFACTS_DIR / "ratings"
DATAFRAMES_DIR = ARTIFACTS_DIR / "dataframes"

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
    """Load Dixon-Coles model from disk cache. Auto-fits on cold start.

    The disk cache in ``model_artifacts/dc_cache/`` is the **only** loading path.
    Static pickle artifacts have been removed (V3.8.0) — they were a root cause
    of silent model-parameter reversion.

    On first run (empty cache), the model is fitted from the artifact training
    DataFrame and saved to disk cache. Subsequent runs load the latest cache.
    """
    timer.start("load_dc")

    dc = _load_model_from_disk_cache(
        prefix="dc",
        cache_dir=_resolve_cache_dir(),
        model_class=DixonColesModel,
        timer=timer,
    )
    if dc is not None:
        timer.stop()
        return dc

    # Cold start: fit from training data, save to cache
    logger.info("DC disk cache empty — fitting from training data (cold start)")
    df = _load_training_df(timer)
    dc = DixonColesModel()
    dc.fit(df)
    _save_to_disk_cache("dc", dc, timer)
    timer.stop()
    return dc


def _load_enhancer(timer: PredictionTimer) -> TabularMatchEnhancer:
    """Load TabularMatchEnhancer from disk cache. Auto-fits on cold start.

    Same single-path design as ``_load_dc`` — no static artifact fallback.
    Sklearn version-mismatch warnings are suppressed during cache loading
    (disk caches may be trained with sklearn 1.9.0 while runtime uses 1.8.0).
    """
    timer.start("load_enhancer")

    import warnings as _warnings
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore", category=UserWarning)
        enh = _load_model_from_disk_cache(
            prefix="enhancer",
            cache_dir=_resolve_cache_dir(),
            model_class=TabularMatchEnhancer,
            timer=timer,
        )
    if enh is not None:
        timer.stop()
        return enh

    # Cold start: fit from training data, save to cache
    logger.info("Enhancer disk cache empty — fitting from training data (cold start)")
    df = _load_training_df(timer)
    enhancer = TabularMatchEnhancer()
    enhancer.fit(df)
    _save_to_disk_cache("enhancer", enhancer, timer)
    timer.stop()
    return enhancer


# ── Disk cache helpers ────────────────────────────────────────────────────────

def _resolve_cache_dir() -> Path:
    """Resolve the disk cache directory, creating it if needed."""
    from app.services.model_cache_disk import _cache_dir
    return _cache_dir()


def _load_model_from_disk_cache(
    *,
    prefix: str,
    cache_dir: Path,
    model_class: type,
    timer: PredictionTimer,
) -> Any | None:
    """Load the **newest** ``{prefix}_*.pkl`` from the disk cache directory.

    Returns None if no cache exists.  Raises on corrupt/unexpected cache files
    so that callers can fall back to cold-start fitting.
    """
    import glob as _glob
    import os as _os

    files = sorted(
        _glob.glob(str(cache_dir / f"{prefix}_*.pkl")),
        key=lambda p: _os.path.getmtime(p),
    )
    if not files:
        return None

    latest = Path(files[-1])
    try:
        with open(latest, "rb") as f:
            cached = pickle.load(f)
    except Exception as exc:
        logger.error("Disk cache %s load failed: %s", latest.name, exc)
        raise

    from app.services.model_cache import CachedDC, CachedEnhancer, ModelCache

    # If it's already the right type, return directly
    if isinstance(cached, model_class):
        logger.info("%s loaded from disk cache: %s", prefix.upper(), latest.name)
        return cached

    # If it's a CachedDC / CachedEnhancer wrapper, reconstruct
    mc = ModelCache()
    if isinstance(cached, CachedDC) and model_class is DixonColesModel:
        model = DixonColesModel()
        mc.restore_dc(cached, model)
        logger.info("DC reconstructed from disk cache: %s", latest.name)
        return model
    if isinstance(cached, CachedEnhancer) and model_class is TabularMatchEnhancer:
        model = TabularMatchEnhancer()
        mc.restore_enhancer(cached, model)
        logger.info("Enhancer reconstructed from disk cache: %s", latest.name)
        return model

    raise TypeError(
        f"Unexpected {prefix} cache type {type(cached).__name__} in {latest.name}"
    )


def _save_to_disk_cache(
    prefix: str, model: Any, timer: PredictionTimer
) -> None:
    """Persist a fitted model to the disk cache directory."""
    from app.services.model_cache_disk import save_dc_to_disk, save_enhancer_to_disk
    from app.services.model_cache import CachedDC, CachedEnhancer

    df = _load_training_df(timer)
    competition_type = "FIFA World Cup 2026"

    if prefix == "dc" and isinstance(model, DixonColesModel):
        cached = CachedDC(
            attack_params=model.attack_params.copy(),
            defense_params=model.defense_params.copy(),
            home_advantage=model.home_advantage,
            rho=model.rho,
            _team_order=list(model._team_order),
            trained_at=datetime.now(),
        )
        save_dc_to_disk(cached, competition_type, df)
    elif prefix == "enhancer" and isinstance(model, TabularMatchEnhancer):
        cached = CachedEnhancer(
            model=model.model,
            feature_columns=model.feature_columns.copy(),
            training_sample_count=model.training_sample_count,
            fitted_at=getattr(model, "fitted_at", datetime.now()),
        )
        save_enhancer_to_disk(cached, competition_type, df)
    else:
        logger.warning(
            "Cannot save %s to disk cache: unsupported type %s",
            prefix, type(model).__name__,
        )


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
