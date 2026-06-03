"""MarketCalibrator — extract signals from betting markets without blending.

Design principles (confirmed with user 2026-05-15):
1. Phase 1: divergence detection ONLY — no probability modification
2. Only store implied probabilities (after vig removal), never raw odds
3. Max 25% market blend reserved for future, not active now
4. Divergence > 12pp → risk_tags + confidence_penalty + logging
5. Never display odds numbers to users
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings

logger = logging.getLogger(__name__)

# Only fetch odds for high-weight competitions (World Cup, UCL, Top 5 leagues)
HIGH_WEIGHT_THRESHOLD = 0.82
DIVERGENCE_THRESHOLD = 0.12   # 12pp divergence triggers risk tag
MAX_MARKET_BLEND = 0.25       # market contributes at most 25%
MIN_MARKET_BLEND = 0.05       # always blend at least 5% when market data available
BLEND_SATURATION = 2000       # sample_size at which market weight reaches minimum


class MarketCalibrator:
    """Fetch market consensus and detect model-market divergence."""

    def __init__(self, shadow_mode: bool = True) -> None:
        settings = get_settings()
        self.api_key: str | None = settings.odds_api_key
        self.base_url = "https://api.the-odds-api.com/v4"
        self._client: httpx.AsyncClient | None = None
        self._available: bool | None = None
        self.shadow_mode: bool = shadow_mode  # Default: record only, don't blend

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    async def is_available(self) -> bool:
        """Check if the odds API is configured and reachable.

        Always re-checks if previously unavailable — transient errors
        (network blips, DNS, timeouts) should not permanently disable odds.
        """
        if self._available is not None and self._available:
            return True
        if not self.api_key:
            logger.info("ODDS_API_KEY not configured — market calibrator disabled")
            self._available = False
            return False
        try:
            client = await self._get_client()
            resp = await client.get(
                f"{self.base_url}/sports",
                params={"apiKey": self.api_key},
            )
            self._available = resp.status_code == 200
            if not self._available:
                logger.warning(f"Odds API returned {resp.status_code}")
        except Exception as e:
            logger.warning(f"Odds API unreachable: {e}")
            self._available = False
        return self._available

    async def fetch_market_probs(
        self,
        home_team: str,
        away_team: str,
        competition_weight: float = 0.9,
        competition: str | None = None,
    ) -> dict[str, Any] | None:
        """Fetch market-implied probabilities for a match.

        Returns None if:
        - API key is not configured
        - Competition weight is below threshold
        - API call fails
        - Odds not available for this match
        """
        if not await self.is_available():
            return None
        if competition_weight < HIGH_WEIGHT_THRESHOLD:
            return None

        # Map competition to sport key
        sport_keys = self._competition_sport_keys(competition)

        try:
            client = await self._get_client()

            for sport_key in sport_keys:
                resp = await client.get(
                    f"{self.base_url}/sports/{sport_key}/odds",
                    params={
                        "apiKey": self.api_key,
                        "regions": "eu",
                        "markets": "h2h",
                        "oddsFormat": "decimal",
                    },
                )
                if resp.status_code != 200:
                    continue

                data = resp.json()
                if not data:
                    continue

                # Find match by team names (fuzzy match)
                for match_data in data:
                    if self._teams_match(match_data, home_team, away_team):
                        result = self._extract_probs(match_data, home_team, away_team)
                        if result:
                            from datetime import datetime as _dt, timezone as _tz
                            result["sport_key"] = sport_key
                            result["fetched_at"] = _dt.now(_tz.utc).isoformat()
                            logger.info(
                                f"Market data found for {home_team} vs {away_team} "
                                f"in {sport_key}: home={result['home_prob']:.3f}"
                            )
                            return result

            logger.info(f"No odds found for {home_team} vs {away_team} in {sport_keys}")
            return None

        except Exception as e:
            logger.warning(f"Market fetch error: {e}")
            return None

    @staticmethod
    def _competition_sport_keys(competition: str | None) -> list[str]:
        """Map competition name to The Odds API sport keys to try.

        Returns a list — first match wins. Falls back to EPL if unknown.
        """
        if not competition:
            return ["soccer_epl"]

        comp_lower = competition.lower()

        mapping = {
            "premier league": ["soccer_epl"],
            "primera division": ["soccer_spain_la_liga"],
            "la liga": ["soccer_spain_la_liga"],
            "bundesliga": ["soccer_germany_bundesliga"],
            "serie a": ["soccer_italy_serie_a"],
            "ligue 1": ["soccer_france_ligue_one"],
            "champions league": ["soccer_uefa_champs_league"],
            "europa league": ["soccer_uefa_europa_league"],
            "fa cup": ["soccer_fa_cup", "soccer_epl"],
            "world cup": ["soccer_fifa_world_cup"],
            "fifa world cup": ["soccer_fifa_world_cup"],
        }

        for key, sport_keys in mapping.items():
            if key in comp_lower:
                return sport_keys

        return ["soccer_epl"]  # fallback

    @staticmethod
    def _normalize_team(name: str) -> str:
        """Normalize team name for fuzzy matching.

        Handles: & ↔ and, FC/AFC suffix, extra whitespace, punctuation.
        """
        import re
        n = name.lower().strip()
        n = n.replace("&", "and")
        n = re.sub(r"\s+", " ", n)
        # Remove common affixes that differ between data sources
        for suffix in (" fc", " afc"):
            if n.endswith(suffix):
                n = n[:-len(suffix)]
                break
        for prefix in ("afc ",):
            if n.startswith(prefix):
                n = n[len(prefix):]
                break
        return n

    def _teams_match(self, match_data: dict, home: str, away: str) -> bool:
        """Fuzzy check if API match data matches our team names."""
        api_home = self._normalize_team(match_data.get("home_team", ""))
        api_away = self._normalize_team(match_data.get("away_team", ""))
        home_norm = self._normalize_team(home)
        away_norm = self._normalize_team(away)
        return (
            home_norm in api_home or api_home in home_norm
        ) and (
            away_norm in api_away or api_away in away_norm
        )

    def _extract_probs(self, match_data: dict, home_team: str, away_team: str) -> dict[str, Any] | None:
        """Extract vig-removed implied probabilities from odds data.

        Matches by team name, not outcome order (API does not guarantee
        home-first ordering).
        """
        bookmakers = match_data.get("bookmakers", [])
        if not bookmakers:
            return None

        # Use Pinnacle if available (most efficient market), else first bookmaker
        pinnacle = None
        for bm in bookmakers:
            if bm.get("key") == "pinnacle":
                pinnacle = bm
                break
        bm = pinnacle or bookmakers[0]

        markets = bm.get("markets", [])
        h2h = None
        for m in markets:
            if m.get("key") == "h2h":
                h2h = m
                break
        if not h2h:
            return None

        outcomes = h2h.get("outcomes", [])
        prices: dict[str, float] = {}
        for o in outcomes:
            name = o.get("name", "")
            price = o.get("price")
            if price and name:
                prices[name] = float(price)

        if len(prices) < 3:
            return None

        # Match by team name (normalized), not by position
        home_norm = self._normalize_team(home_team)
        away_norm = self._normalize_team(away_team)
        home_price = None
        draw_price = None
        away_price = None
        for name, price in prices.items():
            norm = self._normalize_team(name)
            if norm == "draw":
                draw_price = price
            elif home_norm in norm or norm in home_norm:
                home_price = price
            elif away_norm in norm or norm in away_norm:
                away_price = price

        if not all([home_price, draw_price, away_price]):
            # Fallback: first non-draw = home, second = away
            for name, price in prices.items():
                lower = name.lower()
                if lower == "draw":
                    continue
                if home_price is None:
                    home_price = price
                elif away_price is None:
                    away_price = price
            if not all([home_price, draw_price, away_price]):
                return None

        return self._remove_vig(
            float(home_price), float(draw_price), float(away_price)
        )

    def _remove_vig(
        self, home_price: float, draw_price: float, away_price: float
    ) -> dict[str, Any]:
        """Convert raw odds to fair probabilities by removing bookmaker margin.

        Raw odds like 1.85/3.60/4.20 sum to >1.0 in implied prob space.
        We normalize to sum=1.0 and record the removed vig.
        """
        home_implied = 1.0 / home_price
        draw_implied = 1.0 / draw_price
        away_implied = 1.0 / away_price
        total = home_implied + draw_implied + away_implied

        return {
            "home_prob": home_implied / total,
            "draw_prob": draw_implied / total,
            "away_prob": away_implied / total,
            "vig": total - 1.0,
            "sample_bookmakers": 1,
        }

    def calibrate(
        self,
        model_probs: dict[str, float],
        market_probs: dict[str, Any] | None,
        sample_size: int = 0,
    ) -> dict[str, Any]:
        """Detect model-market divergence and blend probabilities.

        Phase 2 (full): blends market implied probabilities into model output
        with sample-size-aware weighting.

        Parameters
        ----------
        model_probs : dict with home_win_prob, draw_prob, away_win_prob
        market_probs : dict from fetch_market_probs() or None
        sample_size : training sample count (more samples → less market weight)

        Returns
        -------
        dict with blended probabilities + metadata
        """
        if market_probs is None:
            return {
                "home_win_prob": model_probs["home_win_prob"],
                "draw_prob": model_probs.get("draw_prob", 0.0),
                "away_win_prob": model_probs["away_win_prob"],
                "market_applied": False,
                "market_weight_used": 0.0,
                "divergence": None,
                "risk_tags": [],
                "confidence_penalty": 0.0,
                "market_home_prob": None,
            }

        # Divergence detection (always computed, even in shadow mode)
        model_home = model_probs.get("home_win_prob", 0.5)
        market_home = market_probs["home_prob"]
        divergence = abs(model_home - market_home)

        risk_tags = []
        confidence_penalty = 0.0

        if divergence > DIVERGENCE_THRESHOLD:
            risk_tags.append(
                f"模型与市场存在显著分歧 ({divergence*100:.1f}pp)"
            )
            confidence_penalty = min(divergence * 0.5, 0.15)

        # Compute blend weight (for audit tracking, even in shadow mode)
        market_weight = max(
            MIN_MARKET_BLEND,
            min(MAX_MARKET_BLEND, 0.25 - sample_size / BLEND_SATURATION),
        )

        # ── Shadow mode: return model probs unchanged ──
        if self.shadow_mode:
            return {
                "home_win_prob": model_probs["home_win_prob"],
                "draw_prob": model_probs.get("draw_prob", 0.0),
                "away_win_prob": model_probs["away_win_prob"],
                "market_applied": False,  # NOT applied — shadow mode
                "market_weight_used": market_weight,  # candidate weight (recorded)
                "divergence": divergence,
                "divergence_triggered": divergence > DIVERGENCE_THRESHOLD,
                "risk_tags": risk_tags,
                "confidence_penalty": confidence_penalty,
                "market_home_prob": market_probs["home_prob"],
                "market_draw_prob": market_probs["draw_prob"],
                "market_away_prob": market_probs["away_prob"],
                "market_vig": market_probs.get("vig", 0),
                "shadow_mode": True,
            }

        # ── Active mode: blend market into model ──
        model_weight = 1.0 - market_weight

        blended_home = (
            model_home * model_weight + market_probs["home_prob"] * market_weight
        )
        blended_draw = (
            model_probs.get("draw_prob", 0.0) * model_weight
            + market_probs["draw_prob"] * market_weight
        )
        blended_away = (
            model_probs.get("away_win_prob", 0.0) * model_weight
            + market_probs["away_prob"] * market_weight
        )

        # Normalize
        total = blended_home + blended_draw + blended_away
        if total > 0:
            blended_home /= total
            blended_draw /= total
            blended_away /= total

        return {
            "home_win_prob": blended_home,
            "draw_prob": blended_draw,
            "away_win_prob": blended_away,
            "market_applied": True,
            "market_weight_used": market_weight,
            "divergence": divergence,
            "divergence_triggered": divergence > DIVERGENCE_THRESHOLD,
            "risk_tags": risk_tags,
            "confidence_penalty": confidence_penalty,
            "market_home_prob": market_probs["home_prob"],
            "market_draw_prob": market_probs["draw_prob"],
            "market_away_prob": market_probs["away_prob"],
            "market_vig": market_probs.get("vig", 0),
            "shadow_mode": False,
        }

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton
_calibrator: MarketCalibrator | None = None


def get_calibrator(shadow_mode: bool = True) -> MarketCalibrator:
    """Get or create the MarketCalibrator singleton.

    Args:
        shadow_mode: If True (default), market data is recorded but NOT
            blended into predictions. Set to False only after backtest
            proves improvement over BaseOnly.
    """
    global _calibrator
    if _calibrator is None or _calibrator.shadow_mode != shadow_mode:
        _calibrator = MarketCalibrator(shadow_mode=shadow_mode)
    return _calibrator
