"""sync_provider.py — Synchronous market odds wrapper for Dashboard.

Wraps the async apifootball.com provider (and The Odds API fallback) in
sync functions via asyncio.run(). Designed for Streamlit which runs in a
synchronous context.

Provides:
    fetch_market_consensus_sync(home_team, away_team, competition)
        -> dict | None

Graceful degradation: returns None if all providers are unavailable.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


def fetch_market_consensus_sync(
    home_team: str,
    away_team: str,
    competition: str | None = None,
    timeout: float = 8.0,
) -> dict[str, Any] | None:
    """Fetch 1X2 market implied probabilities synchronously.

    Tries providers in order:
    1. apifootball.com (API key configured)
    2. The Odds API (fallback)

    Returns:
        {
            "home_prob": 0.52,
            "draw_prob": 0.24,
            "away_prob": 0.24,
            "provider": "apifootball.com",
            "overround": 0.05,
            "home_odds": 1.85,
            "draw_odds": 3.50,
            "away_odds": 4.00,
        }
        or None if all providers failed.
        Returns degraded flag if called from within an existing event loop.
    """
    # Check for existing event loop before calling asyncio.run()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        logger.warning(
            "Market consensus fetch skipped — asyncio.run() cannot be called "
            "from existing event loop (match: %s vs %s). Returning degraded result.",
            home_team,
            away_team,
        )
        return {
            "degraded": True,
            "source": "market_consensus",
            "reason": "event_loop_conflict",
        }

    return asyncio.run(
        _fetch_consensus_async(home_team, away_team, competition, timeout)
    )


async def _fetch_consensus_async(
    home_team: str,
    away_team: str,
    competition: str | None,
    timeout: float,
) -> dict[str, Any] | None:
    """Async implementation — tries providers sequentially."""
    result = None

    # Provider 1: apifootball.com
    try:
        from app.services.market.apifootball_com_provider import (
            ApifootballComProvider,
        )

        provider = ApifootballComProvider()
        if await asyncio.wait_for(provider.is_available(), timeout=timeout):
            odds = await asyncio.wait_for(
                provider.fetch(home_team, away_team, competition),
                timeout=timeout,
            )
            if odds is not None:
                result = {
                    "home_prob": odds.implied_home,
                    "draw_prob": odds.implied_draw,
                    "away_prob": odds.implied_away,
                    "provider": odds.provider,
                    "overround": odds.overround,
                    "home_odds": odds.home_odds,
                    "draw_odds": odds.draw_odds,
                    "away_odds": odds.away_odds,
                    "bookmaker": odds.bookmaker,
                }
                logger.info(
                    f"Market odds from {odds.provider}: "
                    f"H={odds.implied_home:.3f} D={odds.implied_draw:.3f} "
                    f"A={odds.implied_away:.3f}"
                )
        await provider.close()
    except (asyncio.TimeoutError, Exception) as e:
        logger.warning(f"apifootball.com sync fetch failed: {e}")

    if result is not None:
        return result

    # Provider 2: The Odds API
    try:
        result = await _fetch_theodds_api(home_team, away_team, competition, timeout)
    except Exception as e:
        logger.warning(f"The Odds API sync fetch failed: {e}")

    return result


async def _fetch_theodds_api(
    home_team: str,
    away_team: str,
    competition: str | None,
    timeout: float,
) -> dict[str, Any] | None:
    """Fetch from The Odds API (sports odds aggregator)."""
    import httpx

    from app.config import get_settings

    settings = get_settings()
    api_key = settings.odds_api_key
    if not api_key:
        logger.info("The Odds API: no key configured")
        return None

    base_url = "https://api.the-odds-api.com/v4"
    # The Odds API uses 'soccer' for all football
    sport = "soccer"

    # Map competition to region hint
    region = "eu"  # default
    if competition:
        comp_lower = competition.lower()
        if "world cup" in comp_lower or "fifa" in comp_lower:
            region = "us"  # WC 2026 in USA

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            url = f"{base_url}/sports/{sport}/odds"
            params = {
                "apiKey": api_key,
                "regions": region,
                "markets": "h2h",
                "oddsFormat": "decimal",
            }
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                logger.warning(
                    f"The Odds API returned {resp.status_code}: {resp.text[:200]}"
                )
                return None

            data = resp.json()
            if not isinstance(data, list) or len(data) == 0:
                return None

            # Search for our match
            home_lower = home_team.lower().strip()
            away_lower = away_team.lower().strip()
            for event in data:
                ev_home = event.get("home_team", "").lower().strip()
                ev_away = event.get("away_team", "").lower().strip()
                if (home_lower in ev_home or ev_home in home_lower) and (
                    away_lower in ev_away or ev_away in away_lower
                ):
                    # Found match — extract best 1X2 odds
                    bookmakers = event.get("bookmakers", [])
                    if not bookmakers:
                        continue
                    # Use first bookmaker's h2h market
                    for bk in bookmakers:
                        for market in bk.get("markets", []):
                            if market.get("key") == "h2h":
                                outcomes = market.get("outcomes", [])
                                odds_map = {}
                                for o in outcomes:
                                    odds_map[o.get("name", "")] = float(
                                        o.get("price", 0)
                                    )
                                home_odds = odds_map.get(
                                    event.get("home_team", ""), 0
                                )
                                away_odds = odds_map.get(
                                    event.get("away_team", ""), 0
                                )
                                draw_odds = odds_map.get("Draw", 0)

                                if (
                                    home_odds > 1.0
                                    and draw_odds > 1.0
                                    and away_odds > 1.0
                                ):
                                    from app.services.market.probability import (
                                        normalize_1x2_odds,
                                    )

                                    norm = normalize_1x2_odds(
                                        home_odds, draw_odds, away_odds
                                    )
                                    logger.info(
                                        f"Market odds from The Odds API ({bk.get('title', '?')}): "
                                        f"H={norm['home']:.3f} D={norm['draw']:.3f} "
                                        f"A={norm['away']:.3f}"
                                    )
                                    return {
                                        "home_prob": norm["home"],
                                        "draw_prob": norm["draw"],
                                        "away_prob": norm["away"],
                                        "provider": "the-odds-api",
                                        "overround": norm["overround"],
                                        "home_odds": home_odds,
                                        "draw_odds": draw_odds,
                                        "away_odds": away_odds,
                                        "bookmaker": bk.get("title", "unknown"),
                                    }
            logger.info(
                f"The Odds API: no match found for {home_team} vs {away_team}"
            )
            return None

    except Exception as e:
        logger.warning(f"The Odds API error: {e}")
        return None
