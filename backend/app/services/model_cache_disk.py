"""Disk-persistent model cache — survives process restarts.

Extends the in-memory ModelCache with pickle-based disk persistence.
When the memory cache misses, the disk cache is checked before re-fitting.
After a successful fit, models are saved to both memory and disk.

Cache directory: model_artifacts/dc_cache/
Cache key: MD5(competition_type, n_rows, min_date, max_date, n_teams)
"""

from __future__ import annotations

import hashlib
import logging
import os
import pickle
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.services.model_cache import CachedDC, CachedEnhancer

logger = logging.getLogger(__name__)

# Default cache root — relative to backend/
DEFAULT_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "model_artifacts",
    "dc_cache",
)


def _compute_disk_key(competition_type: str, df: pd.DataFrame) -> str:
    """Same fingerprint as ModelCache._compute_key so disk ↔ memory keys match."""
    team_count = len(
        frozenset(df["home_team"].unique()) | frozenset(df["away_team"].unique())
    )
    fingerprint = (
        competition_type,
        len(df),
        str(df["match_date"].min()),
        str(df["match_date"].max()),
        team_count,
    )
    return hashlib.md5(str(fingerprint).encode()).hexdigest()


def _cache_dir() -> Path:
    """Ensure the disk cache directory exists."""
    p = Path(DEFAULT_CACHE_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── DC disk cache ──────────────────────────────────────────


def load_dc_from_disk(competition_type: str, df: pd.DataFrame) -> CachedDC | None:
    """Load a previously-saved DC model from disk. Returns None on miss."""
    key = _compute_disk_key(competition_type, df)
    path = _cache_dir() / f"dc_{competition_type}_{key}.pkl"

    if not path.exists():
        return None

    try:
        with open(path, "rb") as f:
            cached: CachedDC = pickle.load(f)
        age_hours = (time.time() - os.path.getmtime(path)) / 3600
        logger.info(
            "Disk cache DC hit: key=%s… age=%.1fh teams=%d",
            key[:12], age_hours, len(cached._team_order),
        )
        print(f"  💾 磁盘缓存命中 (DC, {age_hours:.1f}h 前生成, {len(cached._team_order)} 队)")
        return cached
    except Exception as exc:
        logger.warning("Disk cache DC load failed: %s", exc)
        return None


def save_dc_to_disk(
    cached: CachedDC, competition_type: str, df: pd.DataFrame
) -> None:
    """Persist a fitted DC model snapshot to disk."""
    key = _compute_disk_key(competition_type, df)
    path = _cache_dir() / f"dc_{competition_type}_{key}.pkl"

    try:
        with open(path, "wb") as f:
            pickle.dump(cached, f, protocol=pickle.HIGHEST_PROTOCOL)
        logger.info(
            "Disk cache DC saved: key=%s… teams=%d",
            key[:12], len(cached._team_order),
        )
        print(f"  💾 磁盘缓存已保存 (DC, {len(cached._team_order)} 队)")
    except Exception as exc:
        logger.error("Disk cache DC save failed: %s", exc)


def save_dc_model_to_disk(
    dc_model: Any, competition_type: str, df: pd.DataFrame
) -> None:
    """Convenience: wrap a live DixonColesModel → CachedDC → disk."""
    cached = CachedDC(
        attack_params=dc_model.attack_params.copy(),
        defense_params=dc_model.defense_params.copy(),
        home_advantage=dc_model.home_advantage,
        rho=dc_model.rho,
        _team_order=list(dc_model._team_order),
        trained_at=getattr(dc_model, "trained_at", datetime.now()),
    )
    save_dc_to_disk(cached, competition_type, df)


# ── Enhancer disk cache ────────────────────────────────────


def load_enhancer_from_disk(
    competition_type: str, df: pd.DataFrame
) -> CachedEnhancer | None:
    """Load a previously-saved enhancer model from disk."""
    key = _compute_disk_key(competition_type, df)
    path = _cache_dir() / f"enhancer_{competition_type}_{key}.pkl"

    if not path.exists():
        return None

    try:
        with open(path, "rb") as f:
            cached: CachedEnhancer = pickle.load(f)
        age_hours = (time.time() - os.path.getmtime(path)) / 3600
        logger.info("Disk cache Enhancer hit: key=%s… age=%.1fh", key[:12], age_hours)
        print(f"  💾 磁盘缓存命中 (Enhancer, {age_hours:.1f}h 前)")
        return cached
    except Exception as exc:
        logger.warning("Disk cache Enhancer load failed: %s", exc)
        return None


def save_enhancer_to_disk(
    cached: CachedEnhancer, competition_type: str, df: pd.DataFrame
) -> None:
    """Persist a fitted enhancer model snapshot to disk."""
    key = _compute_disk_key(competition_type, df)
    path = _cache_dir() / f"enhancer_{competition_type}_{key}.pkl"

    try:
        with open(path, "wb") as f:
            pickle.dump(cached, f, protocol=pickle.HIGHEST_PROTOCOL)
        logger.info("Disk cache Enhancer saved: key=%s…", key[:12])
        print(f"  💾 磁盘缓存已保存 (Enhancer)")
    except Exception as exc:
        logger.error("Disk cache Enhancer save failed: %s", exc)


# ── Maintenance ────────────────────────────────────────────


def clear_old_disk_cache(keep_latest: int = 3) -> int:
    """Remove old cache files, keeping the newest `keep_latest` per type.

    Returns the number of files deleted.
    """
    import glob

    deleted = 0
    for prefix in ("dc", "enhancer"):
        pattern = str(_cache_dir() / f"{prefix}_*.pkl")
        files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
        for f in files[keep_latest:]:
            try:
                os.remove(f)
                deleted += 1
                logger.info("Removed old disk cache: %s", os.path.basename(f))
            except OSError:
                pass

    if deleted:
        print(f"  🗑️  清理了 {deleted} 个旧磁盘缓存文件")
    return deleted
