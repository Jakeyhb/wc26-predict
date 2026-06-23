"""WeightConfig — single source of truth for prediction model weights.

Replaces scattered hardcoded weights in snapshot.py, prediction_orchestrator.py,
fast_predict.py, and learning_engine.py.

Weights are read from model_weight_config DB table (auto-optimized by RPS),
falling back to competition-aware defaults defined here.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class WeightConfig:
    """Immutable weight configuration for a prediction run.

    All weights are in [0, 1]. They are applied sequentially in the pipeline:
      DC → +Enhancer (1-dc) → +Weibull → +Elo → +Pi → +Market → +Signal
    """

    version: str = "1.0"
    dc: float = 0.55  # Dixon-Coles base weight in DC+Enhancer fusion
    enhancer: float = 0.25  # TabularMatchEnhancer weight (1-dc in first blend)
    elo: float = 0.05  # Elo kappa-Davidson weight
    pi: float = 0.05  # Pi-Rating weight
    weibull: float = 0.10  # Weibull Copula weight
    market_max: float = 0.10  # Market consensus maximum blend
    active: bool = True  # Whether this config is active/approved

    label: str = "DEFAULT"  # Human-readable label for logging

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "dc": self.dc,
            "enhancer": self.enhancer,
            "elo": self.elo,
            "pi": self.pi,
            "weibull": self.weibull,
            "market_max": self.market_max,
            "active": self.active,
            "label": self.label,
        }

    @property
    def dc_enhancer_blend(self) -> float:
        """Base weight for Dixon-Coles in DC+Enhancer fusion.

        fuse_outcome_probabilities(base_weight=self.dc) means:
          fused = DC * dc + Enhancer * (1-dc)
        """
        return self.dc

    @property
    def enhancer_complement(self) -> float:
        """Enhancer weight = 1 - dc."""
        return 1.0 - self.dc


# ── Competition-aware defaults ──
# These are the code-level defaults used when the DB has no entry.
# They match the snapshot.py _get_model_config() logic.

_WORLD_CUP = WeightConfig(
    version="3.9.7",
    dc=0.65,            # ↓ from 0.70 (V3.9.7: 3/3 WC direction correct but xG severe underestimate, light trim)
    enhancer=0.10,      # ↓ from 0.30 (V3.9.7: 0/3 WC direction correct, avg Brier 0.92 — systematically overrates underdogs in group stage)
    elo=0.12,           # ↑ from 0.08 (V3.9.7: 3/3 WC direction correct, avg Brier 0.24 — most efficient signal, severely underutilized)
    pi=0.05,            # ↑ from 0.02 (V3.9.7: 2/3 WC direction correct, weak but positive complement to Elo)
    weibull=0.10,       # (unchanged)
    market_max=0.30,    # ↑ from 0.28 (V3.9.7: 3/3 WC direction correct, avg Brier 0.14 — best signal, raise baseline)
    label="WORLD_CUP_V3.9.7",
)

_UCL_FINAL = WeightConfig(
    version="1.0",
    dc=0.42,
    enhancer=0.30,
    elo=0.08,
    pi=0.12,
    weibull=0.08,
    market_max=0.08,
    label="UCL_FINAL",
)

_UCL_KNOCKOUT = WeightConfig(
    version="1.0",
    dc=0.45,
    enhancer=0.28,
    elo=0.07,
    pi=0.10,
    weibull=0.10,
    market_max=0.10,
    label="UCL_KNOCKOUT",
)

_LEAGUE_DEFAULT = WeightConfig(
    version="1.0",
    dc=0.50,
    enhancer=0.30,
    elo=0.05,
    pi=0.05,
    weibull=0.10,
    market_max=0.10,
    label="LEAGUE",
)

# V2.7: Self-evolution from 3-match friendly post-review dataset:
#   Match 1 (Spain 1-1 Iraq):     Enhancer 2/2 ✅, DC 0/2 ❌, Elo 0/2 ❌, Pi 0/2 ❌
#   Match 2 (France 1-2 Ivory):   Enhancer 2/2 ✅, DC 0/2 ❌, Elo 0/2 ❌, Pi 0/2 ❌
#   Match 3 (Singapore 1-2 CN):   Pi ✅ (only correct model), Enhancer ❌, DC ❌, Elo ❌
#
#   Summary: DC 0/3, Elo 0/3, Enhancer 2/3, Pi 1/3
#   → DC/Elo nearly useless in friendlies → weight ↓
#   → Pi captured pattern DC+Enhancer missed → weight ↑
#   → Enhancer still best overall but not infallible → moderate weight
_FRIENDLY = WeightConfig(
    version="2.7",
    dc=0.28,          # ↓ from 0.38 (DC 0/3 in friendlies — near total failure)
    enhancer=0.42,    # ~ (still best at 2/3, but SG-CN proves it's not infallible)
    elo=0.02,         # ↓ from 0.04 (Elo 0/3 in friendlies — irrelevant)
    pi=0.16,          # ↑ from 0.04 (sole correct model on SG-CN, 4x weight increase)
    weibull=0.12,     # slight adjustment
    market_max=0.10,
    label="FRIENDLY_ADJUSTED_V2",
)


def get_weight_config(
    competition: str = "",
    stage: str = "",
) -> WeightConfig:
    """Get the weight configuration for a given competition and stage.

    Priority:
      1. DB auto_optimized_* keys (if available) — RPS-optimized
      2. Competition-aware defaults (World Cup, UCL, etc.)
      3. Generic LEAGUE default

    Args:
        competition: Competition name (e.g., "FIFA World Cup 2026")
        stage: Match stage (e.g., "Group A - Matchday 1", "Final")

    Returns:
        WeightConfig with the appropriate weights.
    """
    c = competition.lower()
    s = (stage or "").lower()

    # 1. V2.6: Friendly matches ALWAYS get adjusted weights
    #    (overrides DB auto-optimized — post-match review proved Enhancer
    #     correctly predicted both upsets when DC/Elo/Pi failed)
    if any(kw in c for kw in ["friendly", "international friendly", "warm-up"]):
        return _FRIENDLY

    # 1b. V3.9.7: World Cup ALWAYS uses WC-specific weights
    #    (overrides DB auto-optimized — global optimizer is contaminated
    #     with friendlies data where Enhancer performs well; WC group stage
    #     is fundamentally different: lopsided, superstar-driven matches)
    if "world cup" in c:
        return _WORLD_CUP

    # 2. Try DB auto-optimized weights (for non-WC, non-friendly competitions)
    db_weights = _read_db_auto_weights()
    if db_weights:
        config = WeightConfig(
            dc=db_weights.get("dc", _LEAGUE_DEFAULT.dc),
            enhancer=db_weights.get("enhancer", _LEAGUE_DEFAULT.enhancer),
            elo=db_weights.get("elo", _LEAGUE_DEFAULT.elo),
            pi=db_weights.get("pi", _LEAGUE_DEFAULT.pi),
            weibull=db_weights.get("weibull", _LEAGUE_DEFAULT.weibull),
            market_max=db_weights.get("market_max", _LEAGUE_DEFAULT.market_max),
            label="AUTO_OPTIMIZED",
            version="2.0",
        )
        config = _apply_competition_market_max(config, competition, stage)
        return config

    # 3. Competition-aware defaults

    if "world cup" in c:
        return _WORLD_CUP
    if ("champions" in c or "ucl" in c):
        if s == "final":
            return _UCL_FINAL
        if any(k in s for k in ["quarter", "semi", "last_16", "playoff"]):
            return _UCL_KNOCKOUT
        return _UCL_KNOCKOUT  # UCL group/league phase also uses knockout weights

    return _LEAGUE_DEFAULT


def _read_db_auto_weights() -> dict[str, float] | None:
    """Read auto-optimized weights from model_weight_config DB table.

    Returns None if the table can't be read or no auto_optimized keys exist.
    """
    try:
        import sqlite3
        from pathlib import Path

        # Find the DB file relative to this module
        db_path = Path(__file__).resolve().parent.parent.parent / "data" / "local_stage2.db"
        if not db_path.exists():
            return None

        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()

        key_map = {
            "auto_optimized_dc": "dc",
            "auto_optimized_enhancer": "enhancer",
            "auto_optimized_elo": "elo",
            "auto_optimized_pi_rating": "pi",
            "auto_optimized_weibull": "weibull",
            "market_max_blend": "market_max",
        }

        c.execute(
            "SELECT config_key, config_value FROM model_weight_config "
            "WHERE config_key IN ({})".format(
                ",".join("?" for _ in key_map)
            ),
            list(key_map.keys()),
        )
        rows = c.fetchall()
        conn.close()

        if not rows:
            return None

        result: dict[str, float] = {}
        for key, value in rows:
            mapped = key_map.get(key)
            if mapped:
                result[mapped] = float(value)

        # Only return if we found at least dc (minimum viable config)
        if "dc" in result:
            return result
        return None

    except Exception:
        logger.debug("Could not read auto-optimized weights from DB", exc_info=True)
        return None


def _apply_competition_market_max(
    config: WeightConfig,
    competition: str,
    stage: str,
) -> WeightConfig:
    """Adjust market_max based on competition type."""
    c = competition.lower()
    s = (stage or "").lower()

    if ("champions" in c or "ucl" in c) and s == "final":
        return WeightConfig(
            dc=config.dc,
            enhancer=config.enhancer,
            elo=config.elo,
            pi=config.pi,
            weibull=config.weibull,
            market_max=0.08,
            label=config.label,
            version=config.version,
        )
    return config


# ── Convenience ──

def get_world_cup_weights() -> WeightConfig:
    """Get the standard World Cup weight configuration."""
    return get_weight_config(competition="FIFA World Cup 2026", stage="Group A - Matchday 1")
