from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.logging import get_logger

logger = get_logger(__name__)


class WeatherService:
    """
    使用 Open-Meteo 免费 API 获取比赛时段天气。
    """

    OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
    VENUE_COORDS = {
        # WC26 venues — USA
        "metlife stadium": (40.8135, -74.0745),           # East Rutherford, NJ
        "new york new jersey stadium": (40.8135, -74.0745), # FIFA name
        "sofi stadium": (33.9535, -118.3392),             # Inglewood, CA
        "los angeles stadium": (33.9535, -118.3392),       # FIFA name
        "at&t stadium": (32.7478, -97.0931),              # Arlington, TX
        "dallas stadium": (32.7478, -97.0931),             # FIFA name
        "levi's stadium": (37.4033, -121.9700),           # Santa Clara, CA
        "san francisco bay area stadium": (37.4033, -121.9700), # FIFA name
        "arrowhead stadium": (39.0489, -94.4839),         # Kansas City, MO
        "kansas city stadium": (39.0489, -94.4839),        # FIFA name
        "lincoln financial field": (39.9007, -75.1675),    # Philadelphia, PA
        "philadelphia stadium": (39.9007, -75.1675),       # FIFA name
        "gillette stadium": (42.0909, -71.2643),           # Foxborough, MA
        "boston stadium": (42.0909, -71.2643),             # FIFA name
        "lumen field": (47.5952, -122.3316),               # Seattle, WA
        "seattle stadium": (47.5952, -122.3316),           # FIFA name
        "hard rock stadium": (25.9580, -80.2389),          # Miami Gardens, FL
        "miami stadium": (25.9580, -80.2389),              # FIFA name
        "nrg stadium": (29.6847, -95.4110),                # Houston, TX
        "houston stadium": (29.6847, -95.4110),            # FIFA name
        "mercedes-benz stadium": (33.7555, -84.4010),      # Atlanta, GA
        "atlanta stadium": (33.7555, -84.4010),            # FIFA name
        # WC26 venues — Canada
        "bc place": (49.2767, -123.1117),                  # Vancouver
        "bmo field": (43.6333, -79.4187),                  # Toronto
        "toronto stadium": (43.6333, -79.4187),            # FIFA name
        # WC26 venues — Mexico
        "estadio azteca": (19.3029, -99.1505),             # Mexico City
        "azteca stadium": (19.3029, -99.1505),             # alias
        "mexico city stadium": (19.3029, -99.1505),        # FIFA name
        "estadio bbva": (25.6694, -100.3114),              # Monterrey
        "monterrey stadium": (25.6694, -100.3114),         # FIFA name
        "estadio akron": (20.6729, -103.4692),             # Guadalajara
        "guadalajara stadium": (20.6729, -103.4692),       # FIFA name
        # European national stadiums (for friendlies/qualifiers)
        "king baudouin stadium": (50.8958, 4.3339),
        "wembley stadium": (51.5560, -0.2795),
        "stade de france": (48.9245, 2.3601),
        "santiago bernabeu": (40.4531, -3.6884),
        "olympiastadion berlin": (52.5147, 13.2395),
        "allianz stadium": (48.2188, 11.6247),
        "san siro": (45.4781, 9.1240),
        "johan cruijff arena": (52.3142, 4.9419),
        "estadio da luz": (38.7528, -9.1847),
    }
    # Team -> likely home venue mapping
    TEAM_VENUE_MAP: dict[str, str] = {
        "belgium": "king baudouin stadium",
        "england": "wembley stadium",
        "france": "stade de france",
        "spain": "santiago bernabeu",
        "germany": "olympiastadion berlin",
        "italy": "san siro",
        "netherlands": "johan cruijff arena",
        "portugal": "estadio da luz",
    }
    WEATHER_CODE_MAP = {
        0: "晴",
        1: "大致晴朗",
        2: "局部多云",
        3: "多云",
        45: "有雾",
        48: "冻雾",
        51: "小毛雨",
        53: "毛雨",
        55: "大毛雨",
        61: "小雨",
        63: "中雨",
        65: "大雨",
        71: "小雪",
        73: "中雪",
        75: "大雪",
        80: "阵雨",
        81: "较强阵雨",
        82: "暴雨阵雨",
        95: "雷暴",
    }

    async def fetch_match_weather(self, venue: str | None, match_datetime: datetime) -> dict[str, Any]:
        default = {
            "temperature_c": None,
            "precipitation_mm": 0.0,
            "wind_speed_kmh": None,
            "humidity_percent": None,
            "weather_code": None,
            "weather_description": "未知",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "forecast_available": False,
        }
        if not venue:
            return default

        venue_key = self._match_venue_key(venue)
        if venue_key is None:
            return default

        match_utc = match_datetime.astimezone(timezone.utc)
        horizon = datetime.now(timezone.utc) + timedelta(days=16)
        if match_utc > horizon:
            return default

        latitude, longitude = self.VENUE_COORDS[venue_key]
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": "temperature_2m,precipitation,wind_speed_10m,relative_humidity_2m,weather_code",
            "timezone": "UTC",
            "forecast_days": 16,
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(self.OPEN_METEO_URL, params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            logger.warning("Open-Meteo request failed for venue %s: %s", venue, exc)
            return default

        hourly = payload.get("hourly", {})
        times = hourly.get("time", [])
        if not times:
            return default

        best_index = min(
            range(len(times)),
            key=lambda index: abs(
                datetime.fromisoformat(times[index]).replace(tzinfo=timezone.utc) - match_utc
            ),
        )
        weather_code = hourly.get("weather_code", [None])[best_index]
        result = {
            "temperature_c": self._value(hourly.get("temperature_2m"), best_index),
            "precipitation_mm": self._value(hourly.get("precipitation"), best_index, default=0.0),
            "wind_speed_kmh": self._value(hourly.get("wind_speed_10m"), best_index),
            "humidity_percent": self._value(hourly.get("relative_humidity_2m"), best_index),
            "weather_code": weather_code,
            "weather_description": self.WEATHER_CODE_MAP.get(weather_code, "未知"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "forecast_available": True,
        }
        return result

    def weather_impact_tags(self, weather: dict[str, Any]) -> list[str]:
        tags: list[str] = []
        precipitation = float(weather.get("precipitation_mm") or 0.0)
        wind_speed = float(weather.get("wind_speed_kmh") or 0.0)
        temperature = weather.get("temperature_c")
        if precipitation > 5:
            tags.append("大雨天气")
        elif precipitation > 1:
            tags.append("雨天影响")
        if wind_speed > 40:
            tags.append("强风天气")
        if temperature is not None and float(temperature) > 32:
            tags.append("高温酷暑")
        if temperature is not None and float(temperature) < 5:
            tags.append("低温条件")
        return tags

    def _match_venue_key(self, venue: str) -> str | None:
        normalized = venue.strip().lower()
        if normalized in self.VENUE_COORDS:
            return normalized
        for key in self.VENUE_COORDS:
            if key in normalized or normalized in key:
                return key
        return None

    def _value(self, values: list[Any] | None, index: int, default: Any = None) -> Any:
        if not values or index >= len(values):
            return default
        value = values[index]
        try:
            return float(value)
        except (TypeError, ValueError):
            return value if value is not None else default

    # ── Sync wrappers for Dashboard ──────────────────────────────────────────

    def get_weather_for_match_sync(
        self,
        venue: str | None = None,
        home_team: str | None = None,
        away_team: str | None = None,
    ) -> dict[str, Any]:
        """Synchronous wrapper for Dashboard — fetch weather without async.

        If venue is unknown, tries to guess from team names (for neutral friendlies,
        defaults to a reasonable location).

        Returns a dict with weather_description, temperature_c, etc.
        Always returns a dict — forecast_available=False if lookup failed.
        """
        import asyncio

        default = {
            "temperature_c": None,
            "precipitation_mm": 0.0,
            "wind_speed_kmh": None,
            "humidity_percent": None,
            "weather_code": None,
            "weather_description": "未知",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "forecast_available": False,
        }

        # Resolve venue
        resolved_venue = venue or self._guess_venue(home_team, away_team)
        if resolved_venue is None:
            return default

        # Use match time = now + 24h (best-effort for upcoming matches)
        match_dt = datetime.now(timezone.utc) + timedelta(hours=24)

        # Check for existing event loop before calling asyncio.run()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            logger.warning(
                "Weather fetch skipped — asyncio.run() cannot be called from "
                "existing event loop (venue=%s). Returning degraded result.",
                resolved_venue,
            )
            degraded = dict(default)
            degraded["degraded"] = True
            degraded["source"] = "weather"
            degraded["reason"] = "event_loop_conflict"
            return degraded

        try:
            return asyncio.run(self.fetch_match_weather(resolved_venue, match_dt))
        except Exception as exc:
            logger.warning("Weather sync fetch failed: %s", exc)
            return default

    def _guess_venue(
        self, home_team: str | None, away_team: str | None
    ) -> str | None:
        """Guess venue from home team's national stadium.

        1. Check TEAM_VENUE_MAP for home team (most friendlies are home games)
        2. Fall back to WC26 venue hints
        3. Default to MetLife as last resort
        """
        if home_team:
            key = home_team.lower().strip()
            if key in self.TEAM_VENUE_MAP:
                return self.TEAM_VENUE_MAP[key]
        if away_team:
            key = away_team.lower().strip()
            if key in self.TEAM_VENUE_MAP:
                return self.TEAM_VENUE_MAP[key]

        hints = {"united states": "metlife stadium", "usa": "metlife stadium",
                 "mexico": "estadio azteca", "canada": "bmo field"}
        for team in (home_team, away_team):
            if team is None:
                continue
            h = hints.get(team.lower().strip())
            if h:
                return h
        return "metlife stadium"
