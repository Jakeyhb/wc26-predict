"""Market Consensus Calibration — provider abstraction and consensus layer.

Sub-packages:
- provider_base: Abstract base class for odds providers
- probability: Vig removal (proportional, Shin, Power methods)
- consensus: Multi-provider aggregation
- schemas: OddsSnapshot and MarketConsensus dataclasses
"""
from app.services.market.schemas import MarketConsensus, OddsSnapshot
from app.services.market.probability import normalize_1x2_odds, normalize_1x2_shin, normalize_1x2_power
from app.services.market.consensus import build_consensus, snapshots_from_market_probs
from app.services.market.provider_base import MarketProvider, MarketOddsResult

__all__ = [
    "MarketConsensus",
    "OddsSnapshot",
    "MarketProvider",
    "MarketOddsResult",
    "normalize_1x2_odds",
    "normalize_1x2_shin",
    "normalize_1x2_power",
    "build_consensus",
    "snapshots_from_market_probs",
]
