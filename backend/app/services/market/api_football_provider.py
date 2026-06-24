"""API-Football odds provider — primary real-time market data source.

Free tier: 100 requests/day, Pre-match + In-play odds.
Uses x-apisports-key header authentication.

Provider is designed to fail gracefully — if the key is invalid or rate-limited,
fetch() returns None and the main prediction pipeline continues unaffected.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import get_settings
from app.services.market.probability import normalize_1x2_odds
from app.services.market.provider_base import MarketOddsResult, MarketProvider

logger = logging.getLogger(__name__)

# API-Football competition IDs (free tier coverage)
LEAGUE_IDS = {
    "world cup": 1,           # FIFA World Cup
    "premier league": 39,     # Premier League
    "la liga": 140,           # La Liga
    "bundesliga": 78,         # Bundesliga
    "serie a": 135,           # Serie A
    "ligue 1": 61,            # Ligue 1
    "champions league": 2,    # UEFA Champions League
    "europa league": 3,       # UEFA Europa League
}

BOOKMAKER_PREFERENCE = [8, 6, 1]  # Bet365=8, Bwin=6, 1xBet=1


class ApiFootballProvider(MarketProvider):
    """API-Football v3 odds provider.

    Fetches pre-match 1X2 odds for a given match via team name matching.
    Falls back gracefully when the API is unavailable.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.api_key: str | None = settings.api_football_key
        self.base_url = "https://v3.football.api-sports.io"
        self._client: httpx.AsyncClient | None = None
        self._available: bool | None = None
        self._available_checked_at: float = 0.0  # monotonic timestamp of last check

    @property
    def name(self) -> str:
        return "api-football"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    def _headers(self) -> dict[str, str]:
        return {"x-apisports-key": self.api_key or ""}

    async def is_available(self) -> bool:
        """Check API status with 120 s retry cooldown on failure."""
        import time as _time
        if self._available is not None:
            if self._available or _time.monotonic() - self._available_checked_at < 120:
                return self._available
            logger.info("API-Football: retrying availability check after cooldown")
        if not self.api_key:
            self._available = False
            self._available_checked_at = _time.monotonic()
            return False
        try:
            client = await self._get_client()
            r = await client.get(
                f"{self.base_url}/status",
                headers=self._headers(),
            )
            body = r.json()
            # Check for auth errors
            if body.get("errors"):
                logger.warning(f"API-Football auth error: {body['errors']}")
                self._available = False
            else:
                self._available = True
        except Exception as e:
            logger.warning(f"API-Football unavailable: {e}")
            self._available = False
        self._available_checked_at = _time.monotonic()
        return self._available

    async def fetch(
        self,
        home_team: str,
        away_team: str,
        competition: str | None = None,
    ) -> MarketOddsResult | None:
        """Fetch 1X2 odds from API-Football.

        Strategy:
        1. Map competition to league ID
        2. Search fixtures by team names in current season
        3. Fetch odds for matching fixture
        4. Normalize via vig removal
        """
        if not await self.is_available():
            return None

        league_id = self._resolve_league_id(competition)
        if league_id is None:
            logger.info(f"API-Football: no league mapping for '{competition}'")
            return None

        try:
            client = await self._get_client()

            # Get current season fixtures for the league
            # Free tier gives current season access
            r = await client.get(
                f"{self.base_url}/fixtures",
                headers=self._headers(),
                params={
                    "league": str(league_id),
                    "season": "2026",  # Current World Cup year
                    "status": "NS",     # Not Started (future matches)
                },
            )
            body = r.json()
            if body.get("errors"):
                logger.warning(f"API-Football fixtures error: {body['errors']}")
                return None

            fixtures = body.get("response", [])
            if not fixtures:
                # Try without status filter
                r = await client.get(
                    f"{self.base_url}/fixtures",
                    headers=self._headers(),
                    params={
                        "league": str(league_id),
                        "season": "2026",
                    },
                )
                body = r.json()
                fixtures = body.get("response", [])

            # Match by team name
            fixture_id = None
            for f in fixtures:
                f_home = self._normalize(f["teams"]["home"]["name"])
                f_away = self._normalize(f["teams"]["away"]["name"])
                if (f_home in home_team or home_team in f_home) and \
                   (f_away in away_team or away_team in f_away):
                    fixture_id = f["fixture"]["id"]
                    break

            if fixture_id is None:
                logger.info(
                    f"API-Football: no fixture found for {home_team} vs {away_team}"
                )
                return None

            # Fetch odds for the matched fixture
            r = await client.get(
                f"{self.base_url}/odds",
                headers=self._headers(),
                params={"fixture": str(fixture_id), "bet": "1"},
            )
            body = r.json()
            if body.get("errors"):
                logger.warning(f"API-Football odds error: {body['errors']}")
                return None

            odds_data = body.get("response", [])
            if not odds_data:
                return None

            # Find preferred bookmaker with 1X2 odds
            return self._extract_odds(odds_data, fixture_id)

        except Exception as e:
            logger.warning(f"API-Football fetch error: {e}")
            return None

    def _extract_odds(
        self, odds_data: list[dict], fixture_id: int
    ) -> MarketOddsResult | None:
        """Extract 1X2 odds from odds response, preferring reliable bookmakers."""
        bookmakers = odds_data[0].get("bookmakers", []) if odds_data else []

        # Try preferred bookmakers first, then any
        for pref_id in BOOKMAKER_PREFERENCE:
            for bm in bookmakers:
                if bm.get("id") == pref_id:
                    result = self._parse_bookmaker(bm, fixture_id)
                    if result:
                        return result

        # Fallback: first bookmaker with valid 1X2
        for bm in bookmakers:
            result = self._parse_bookmaker(bm, fixture_id)
            if result:
                return result

        return None

    def _parse_bookmaker(
        self, bm: dict, fixture_id: int
    ) -> MarketOddsResult | None:
        """Parse a single bookmaker's odds into a normalized result."""
        for bet in bm.get("bets", []):
            if bet.get("name") != "Match Winner":
                continue
            values = bet.get("values", [])
            if len(values) != 3:
                continue

            # Map values by outcome
            odds_map = {}
            for v in values:
                odds_map[v["value"]] = float(v["odd"])

            home_odds = odds_map.get("Home", 0)
            draw_odds = odds_map.get("Draw", 0)
            away_odds = odds_map.get("Away", 0)

            if not all([home_odds, draw_odds, away_odds]):
                continue

            # Vig removal
            norm = normalize_1x2_odds(home_odds, draw_odds, away_odds)

            return MarketOddsResult(
                provider=self.name,
                home_odds=home_odds,
                draw_odds=draw_odds,
                away_odds=away_odds,
                implied_home=norm["home"],
                implied_draw=norm["draw"],
                implied_away=norm["away"],
                overround=norm["overround"],
                bookmaker=bm.get("name", "unknown"),
                external_fixture_id=str(fixture_id),
                fetched_at=datetime.now(timezone.utc).isoformat(),
            )

        return None

    def _resolve_league_id(self, competition: str | None) -> int | None:
        """Map competition name to API-Football league ID."""
        if not competition:
            return None
        c = competition.lower()
        for key, lid in LEAGUE_IDS.items():
            if key in c:
                return lid
        return None

    @staticmethod
    def _normalize(name: str) -> str:
        """Normalize team name for fuzzy matching."""
        return name.lower().replace("&", "and").strip()

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
