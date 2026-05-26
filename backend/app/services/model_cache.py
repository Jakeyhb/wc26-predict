"""ModelCache — avoid re-fitting DC/Enhancer models on every prediction call.

For batch prediction (e.g., 72+ WC26 matches), the same 5000-row training dataset
gets re-fitted identically N times. ModelCache stores fitted models in memory,
keyed by (competition, data_fingerprint), with a 30-min TTL.

Invalidates automatically when training data changes (different row count,
date range, or team set triggers a new key).
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class CachedDC:
    """Serializable snapshot of a fitted Dixon-Coles model."""
    attack_params: dict[str, float]
    defense_params: dict[str, float]
    home_advantage: float
    rho: float
    _team_order: list[str]
    trained_at: datetime


@dataclass
class CachedEnhancer:
    """Serializable snapshot of a fitted TabularEnhancer model."""
    model: Any           # fitted HGBClassifier or XGBClassifier
    feature_columns: list[str]
    training_sample_count: int
    fitted_at: datetime


class ModelCache:
    """In-memory cache for fitted prediction models.

    Keyed by (competition, data_hash) to auto-invalidate when training data changes.
    Default TTL: 30 minutes.
    """

    def __init__(self, ttl_seconds: int = 1800) -> None:
        self.ttl = ttl_seconds
        self._dc: dict[str, tuple[float, CachedDC]] = {}
        self._enhancer: dict[str, tuple[float, CachedEnhancer]] = {}
        self._hits: int = 0
        self._misses: int = 0

    @staticmethod
    def _compute_key(competition: str, df: pd.DataFrame) -> str:
        """Derive a fingerprint from training data to detect staleness.

        Hash includes: competition name, row count, date range, and team count.
        Any change in these triggers a cache miss and re-fit.
        """
        team_count = len(
            frozenset(df["home_team"].unique()) | frozenset(df["away_team"].unique())
        )
        fingerprint = (
            competition,
            len(df),
            str(df["match_date"].min()),
            str(df["match_date"].max()),
            team_count,
        )
        return hashlib.md5(str(fingerprint).encode()).hexdigest()

    def _is_fresh(self, timestamp: float) -> bool:
        return (time.time() - timestamp) < self.ttl

    # ── DC cache ──────────────────────────────────────────

    def get_dc(self, competition: str, df: pd.DataFrame) -> CachedDC | None:
        key = self._compute_key(competition, df)
        entry = self._dc.get(key)
        if entry and self._is_fresh(entry[0]):
            self._hits += 1
            total = self._hits + self._misses
            logger.info(f"ModelCache DC hit ({self._hits}/{total})")
            return entry[1]
        self._misses += 1
        return None

    def set_dc(self, competition: str, df: pd.DataFrame, dc_model: Any) -> None:
        """Store a fitted DixonColesModel for later reuse."""
        key = self._compute_key(competition, df)
        self._dc[key] = (time.time(), CachedDC(
            attack_params=dc_model.attack_params.copy(),
            defense_params=dc_model.defense_params.copy(),
            home_advantage=dc_model.home_advantage,
            rho=dc_model.rho,
            _team_order=list(dc_model._team_order),
            trained_at=getattr(dc_model, "trained_at", datetime.now(UTC)),
        ))
        logger.info(f"ModelCache DC stored (competition={competition}, teams={len(dc_model._team_order)})")

    def restore_dc(self, cached: CachedDC, dc_model: Any) -> None:
        """Restore cached state onto a fresh DixonColesModel instance."""
        dc_model.attack_params = cached.attack_params
        dc_model.defense_params = cached.defense_params
        dc_model.home_advantage = cached.home_advantage
        dc_model.rho = cached.rho
        dc_model._team_order = cached._team_order
        dc_model.trained_at = cached.trained_at

    # ── Enhancer cache ────────────────────────────────────

    def get_enhancer(self, competition: str, df: pd.DataFrame) -> CachedEnhancer | None:
        key = self._compute_key(competition, df)
        entry = self._enhancer.get(key)
        if entry and self._is_fresh(entry[0]):
            self._hits += 1
            return entry[1]
        self._misses += 1
        return None

    def set_enhancer(self, competition: str, df: pd.DataFrame, enhancer_model: Any) -> None:
        """Store a fitted TabularMatchEnhancer for later reuse."""
        key = self._compute_key(competition, df)
        self._enhancer[key] = (time.time(), CachedEnhancer(
            model=enhancer_model.model,
            feature_columns=enhancer_model.feature_columns.copy(),
            training_sample_count=enhancer_model.training_sample_count,
            fitted_at=getattr(enhancer_model, "fitted_at", datetime.now(UTC)),
        ))
        logger.info(f"ModelCache Enhancer stored (samples={enhancer_model.training_sample_count})")

    def restore_enhancer(self, cached: CachedEnhancer, enhancer_model: Any) -> None:
        """Restore cached state onto a fresh TabularMatchEnhancer instance."""
        enhancer_model.model = cached.model
        enhancer_model.feature_columns = cached.feature_columns
        enhancer_model.is_fitted = True
        enhancer_model.training_sample_count = cached.training_sample_count
        enhancer_model.fitted_at = cached.fitted_at

    # ── Admin ─────────────────────────────────────────────

    def invalidate(self) -> None:
        """Clear all caches."""
        self._dc.clear()
        self._enhancer.clear()
        self._hits = 0
        self._misses = 0

    def stats(self) -> dict[str, Any]:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total else 0.0,
            "cached_dc": len(self._dc),
            "cached_enhancer": len(self._enhancer),
        }


# ── Singleton ─────────────────────────────────────────

_cache: ModelCache | None = None


def get_cache() -> ModelCache:
    global _cache
    if _cache is None:
        _cache = ModelCache()
    return _cache


def invalidate_cache() -> None:
    """Force-clear the model cache (e.g., after training data refresh)."""
    get_cache().invalidate()
