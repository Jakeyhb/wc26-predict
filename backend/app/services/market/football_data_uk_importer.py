"""Football-Data.co.uk historical odds importer.

Downloads and parses CSV files from football-data.co.uk containing:
- Match results (FTHG, FTAG)
- Opening/closing odds from multiple bookmakers (Bet365, Pinnacle, market average)
- Closing odds MUST NOT be used for T-24h/T-6h prediction training (leakage).

CSV URL pattern: https://www.football-data.co.uk/mmz4281/{season_code}/{division}.csv

Key fields:
  B365H/B365D/B365A  — Bet365 opening odds
  PSH/PSD/PSA        — Pinnacle opening odds
  AvgH/AvgD/AvgA     — Market average odds
  B365CH/B365CD/B365CA — Bet365 CLOSING odds (benchmark only!)
  AvgCH/AvgCD/AvgCA  — Market average CLOSING odds (benchmark only!)
"""
from __future__ import annotations

import csv
import logging
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from app.services.market.probability import normalize_1x2_odds

logger = logging.getLogger(__name__)

# ── Known league codes ──
LEAGUE_CODES = {
    "E0": "Premier League",
    "E1": "Championship",
    "E2": "League One",
    "E3": "League Two",
    "SP1": "La Liga",
    "SP2": "Segunda Division",
    "D1": "Bundesliga",
    "D2": "Bundesliga 2",
    "I1": "Serie A",
    "I2": "Serie B",
    "F1": "Ligue 1",
    "F2": "Ligue 2",
    "N1": "Eredivisie",
    "P1": "Primeira Liga",
    "SC0": "Scottish Premiership",
    "B1": "Belgian Pro League",
    "T1": "Turkish Super Lig",
}

# ── Season code mapping ──
# Format: "mmz4281" prefix + season code
# 2324 = 2023-24, 2425 = 2024-25, etc.
SEASONS = ["2425", "2324", "2223", "2122", "2021", "1920", "1819"]

BASE_URL = "https://www.football-data.co.uk/mmz4281"


@dataclass
class ImportResult:
    """Result of importing a single CSV file."""
    league: str
    season: str
    rows_parsed: int
    rows_imported: int
    rows_skipped: int
    errors: list[str]


class FootballDataUKImporter:
    """Download and parse Football-Data.co.uk CSV files.

    Usage:
        importer = FootballDataUKImporter()
        result = await importer.import_league("E0", "2425", dry_run=True)
        print(f"Parsed {result.rows_parsed} matches")
    """

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def download_csv(self, league_code: str, season_code: str) -> str | None:
        """Download a single CSV file. Returns CSV text or None."""
        url = f"{BASE_URL}/{season_code}/{league_code}.csv"
        try:
            client = await self._get_client()
            r = await client.get(url)
            if r.status_code != 200:
                logger.warning(f"CSV not found: {url} (HTTP {r.status_code})")
                return None
            return r.text
        except Exception as e:
            logger.warning(f"Download failed for {url}: {e}")
            return None

    def parse_csv(self, csv_text: str) -> pd.DataFrame:
        """Parse CSV text into a DataFrame with normalized columns.

        Returns DataFrame with columns:
          date, home_team, away_team, home_goals, away_goals,
          b365_home_odds, b365_draw_odds, b365_away_odds,  # opening
          ps_home_odds, ps_draw_odds, ps_away_odds,         # opening (Pinnacle)
          avg_home_odds, avg_draw_odds, avg_away_odds,       # opening (market avg)
          b365_close_home, b365_close_draw, b365_close_away, # CLOSING
          avg_close_home, avg_close_draw, avg_close_away,    # CLOSING
        """
        df = pd.read_csv(StringIO(csv_text))

        # Normalize column names
        col_map = {
            "Date": "date",
            "HomeTeam": "home_team",
            "AwayTeam": "away_team",
            "FTHG": "home_goals",
            "FTAG": "away_goals",
            "B365H": "b365_home_odds",
            "B365D": "b365_draw_odds",
            "B365A": "b365_away_odds",
            "PSH": "ps_home_odds",
            "PSD": "ps_draw_odds",
            "PSA": "ps_away_odds",
            "AvgH": "avg_home_odds",
            "AvgD": "avg_draw_odds",
            "AvgA": "avg_away_odds",
            # Closing odds (BENCHMARK ONLY — do NOT use for T-24h/T-6h training)
            "B365CH": "b365_close_home",
            "B365CD": "b365_close_draw",
            "B365CA": "b365_close_away",
            "AvgCH": "avg_close_home",
            "AvgCD": "avg_close_draw",
            "AvgCA": "avg_close_away",
        }

        # Only rename columns that exist
        existing = {k: v for k, v in col_map.items() if k in df.columns}
        df = df.rename(columns=existing)

        # Parse date
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")

        return df

    def extract_odds_records(
        self, df: pd.DataFrame, league: str, season: str
    ) -> list[dict[str, Any]]:
        """Extract odds records from parsed DataFrame.

        Only extracts OPENING odds for training. Closing odds are marked
        as benchmark-only and excluded from training datasets.

        Returns list of dicts suitable for DB insertion.
        """
        records = []

        for _, row in df.iterrows():
            if pd.isna(row.get("home_goals")) or pd.isna(row.get("away_goals")):
                continue

            # ── Opening odds (safe for training) ──
            opening = None
            if all(not pd.isna(row.get(c)) for c in
                   ["avg_home_odds", "avg_draw_odds", "avg_away_odds"]):
                opening = normalize_1x2_odds(
                    float(row["avg_home_odds"]),
                    float(row["avg_draw_odds"]),
                    float(row["avg_away_odds"]),
                )
            elif all(not pd.isna(row.get(c)) for c in
                     ["b365_home_odds", "b365_draw_odds", "b365_away_odds"]):
                opening = normalize_1x2_odds(
                    float(row["b365_home_odds"]),
                    float(row["b365_draw_odds"]),
                    float(row["b365_away_odds"]),
                )

            # ── Closing odds (benchmark ONLY) ──
            closing = None
            has_closing = all(not pd.isna(row.get(c)) for c in
                              ["avg_close_home", "avg_close_draw", "avg_close_away"])
            if has_closing:
                closing = normalize_1x2_odds(
                    float(row["avg_close_home"]),
                    float(row["avg_close_draw"]),
                    float(row["avg_close_away"]),
                )

            if opening is None:
                continue

            match_date = row.get("date")
            date_str = match_date.isoformat() if hasattr(match_date, "isoformat") else str(match_date)

            records.append({
                "home_team": str(row["home_team"]),
                "away_team": str(row["away_team"]),
                "match_date": date_str[:10],
                "league": league,
                "season": season,
                "home_goals": int(row["home_goals"]),
                "away_goals": int(row["away_goals"]),
                "implied_home": round(opening["home"], 6),
                "implied_draw": round(opening["draw"], 6),
                "implied_away": round(opening["away"], 6),
                "overround": round(opening["overround"], 6),
                "is_opening": True,
                # Closing probabilities (benchmark only — tagged separately)
                "close_implied_home": round(closing["home"], 6) if closing else None,
                "close_implied_draw": round(closing["draw"], 6) if closing else None,
                "close_implied_away": round(closing["away"], 6) if closing else None,
                "source": "football-data.co.uk",
            })

        return records

    async def import_league(
        self, league_code: str, season_code: str, dry_run: bool = False
    ) -> ImportResult:
        """Download, parse, and import a league CSV.

        Args:
            league_code: e.g., "E0" for Premier League.
            season_code: e.g., "2425" for 2024-25.
            dry_run: If True, parse but don't write to DB.
        """
        league_name = LEAGUE_CODES.get(league_code, league_code)
        result = ImportResult(
            league=league_name,
            season=f"20{season_code[:2]}-{season_code[2:]}",
            rows_parsed=0,
            rows_imported=0,
            rows_skipped=0,
            errors=[],
        )

        csv_text = await self.download_csv(league_code, season_code)
        if csv_text is None:
            result.errors.append(f"Download failed for {league_code}/{season_code}")
            return result

        try:
            df = self.parse_csv(csv_text)
            result.rows_parsed = len(df)
        except Exception as e:
            result.errors.append(f"Parse error: {e}")
            return result

        records = self.extract_odds_records(df, league_name, result.season)
        result.rows_imported = len(records)
        result.rows_skipped = result.rows_parsed - result.rows_imported

        if dry_run:
            logger.info(
                f"[DRY RUN] {league_name} {result.season}: "
                f"{result.rows_imported} records with odds"
            )
            return result

        # Write to DB
        try:
            await self._save_to_db(records)
        except Exception as e:
            result.errors.append(f"DB write error: {e}")
            logger.error(f"Failed to save odds to DB: {e}")

        return result

    async def _save_to_db(self, records: list[dict]) -> None:
        """Save odds records to market_odds_snapshots table."""
        import uuid
        from app.database import AsyncSessionLocal
        from sqlalchemy import text

        async with AsyncSessionLocal() as db:
            for rec in records:
                await db.execute(
                    text(
                        "INSERT OR IGNORE INTO market_odds_snapshots "
                        "(id, match_id, provider, captured_at, home_odds, draw_odds, "
                        " away_odds, implied_home, implied_draw, implied_away, "
                        " overround, is_closing, home_team_name, away_team_name) "
                        "VALUES (:id, :mid, :prov, :ts, :ho, :do, :ao, "
                        " :ih, :idr, :ia, :ov, :ic, :hn, :an)"
                    ),
                    {
                        "id": str(uuid.uuid4()).replace("-", ""),
                        "mid": f"{rec['home_team']}_{rec['away_team']}_{rec['match_date']}",
                        "prov": "football-data.co.uk",
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "ho": 0, "do": 0, "ao": 0,  # Raw odds not stored
                        "ih": rec["implied_home"],
                        "idr": rec["implied_draw"],
                        "ia": rec["implied_away"],
                        "ov": rec["overround"],
                        "ic": False,  # These are OPENING odds, not closing
                        "hn": rec["home_team"],
                        "an": rec["away_team"],
                    },
                )
            await db.commit()

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
