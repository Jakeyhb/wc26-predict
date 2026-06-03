"""Market Consensus Calibration — provider abstraction and consensus layer.

Sub-packages:
- provider_base: Abstract base class for odds providers
- api_football_provider: API-Football v3 provider (free tier)
- probability: Vig removal (proportional, Shin, Power methods)
- consensus: Multi-provider aggregation
- leakage_guard: Temporal data leakage prevention
- schemas: OddsSnapshot and MarketConsensus dataclasses
"""
from app.services.market.schemas import MarketConsensus, OddsSnapshot
from app.services.market.probability import normalize_1x2_odds, normalize_1x2_shin, normalize_1x2_power
from app.services.market.consensus import build_consensus, snapshots_from_market_probs
from app.services.market.leakage_guard import LeakageGuard, LeakageCheckResult, PredictionWindow
from app.services.market.provider_base import MarketProvider, MarketOddsResult

__all__ = [
    "MarketConsensus",
    "OddsSnapshot",
    "MarketProvider",
    "MarketOddsResult",
    "LeakageGuard",
    "LeakageCheckResult",
    "PredictionWindow",
    "normalize_1x2_odds",
    "normalize_1x2_shin",
    "normalize_1x2_power",
    "build_consensus",
    "snapshots_from_market_probs",
]
