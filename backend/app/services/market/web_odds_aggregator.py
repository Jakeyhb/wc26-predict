"""web_odds_aggregator.py — Multi-bookmaker odds consensus from web cache.

When live APIs return only 1-2 bookmakers (free tier limitation), this module
reads a web-search-populated cache of 8+ bookmakers to produce a robust
cross-validated market consensus.

Cache file: backend/data/_web_odds_cache.json
TTL: 6 hours (odds can shift in the hours before kickoff)

Data flow:
    WebSearch (manual / Claude) → ingest_web_odds.py → _web_odds_cache.json
                                                              ↓
    sync_provider.py / market_calibrator.py → web_odds_aggregator.lookup()
                                                              ↓
    compute_consensus() → median odds + de-vig + CV

Design:
    - Pure file I/O — works in both sync and async contexts.
    - Returns None when cache is stale (>6h) or missing → upstream falls back.
    - Logs CV (coefficient of variation) to signal consensus robustness.
"""

from __future__ import annotations

import json
import logging
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Path relative to this module: .../market/web_odds_aggregator.py → .../../../../data/
_CACHE_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data"
    / "_web_odds_cache.json"
)

_CACHE_TTL_HOURS = 6  # Odds consensus is valid for 6 hours


# ── Public API ────────────────────────────────────────────────────────────

def lookup(home_team: str, away_team: str) -> dict[str, Any] | None:
    """Look up multi-bookmaker consensus from the web odds cache.

    Returns None if:
    - Cache file doesn't exist
    - Match not found in cache
    - Cache entry is older than TTL (6 hours)
    - Cache entry has <3 bookmakers (not enough for consensus)

    Return dict:
        {
            "home_prob": 0.556,      # de-vigged implied probability
            "draw_prob": 0.251,
            "away_prob": 0.193,
            "home_odds": 1.71,       # median consensus odds
            "draw_odds": 3.80,
            "away_odds": 4.95,
            "provider": "web-search-consensus",
            "overround": 0.049,
            "bookmaker": "11-bookmaker-consensus",
            "sample_bookmakers": 11,
            "cv_home": 0.029,        # coefficient of variation
            "cv_draw": 0.049,
            "cv_away": 0.061,
            "bookmaker_list": ["BetOnline","DraftKings",...],
            "captured_at": "2026-06-28T07:00:00Z",
        }
    """
    if not _CACHE_PATH.exists():
        logger.debug("Web odds cache not found at %s", _CACHE_PATH)
        return None

    try:
        cache = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read web odds cache: %s", exc)
        return None

    key = f"{home_team}|{away_team}"
    entry = cache.get(key)
    if entry is None:
        logger.debug("Match '%s' not found in web odds cache", key)
        return None

    # ── TTL check ──
    captured_str = entry.get("captured_at", "")
    try:
        captured = datetime.fromisoformat(captured_str)
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - captured
        if age > timedelta(hours=_CACHE_TTL_HOURS):
            logger.info(
                "Web odds cache for '%s' is stale (age=%.1fh > TTL=%dh)",
                key, age.total_seconds() / 3600, _CACHE_TTL_HOURS,
            )
            return None
    except (ValueError, TypeError):
        logger.warning("Invalid captured_at in web odds cache for '%s'", key)
        return None

    # ── Bookmaker count check ──
    bookmakers = entry.get("bookmakers", [])
    if len(bookmakers) < 3:
        logger.info(
            "Web odds cache for '%s' has only %d bookmakers (<3), skipping",
            key, len(bookmakers),
        )
        return None

    # ── Compute consensus (median of decimal odds → de-vig) ──
    result = _compute_consensus(bookmakers, captured_str)
    if result is None:
        return None

    logger.info(
        "Web odds consensus for '%s': %d bookmakers, "
        "H=%.3f D=%.3f A=%.3f, CV=(%.1f%%, %.1f%%, %.1f%%)",
        key, len(bookmakers),
        result["home_prob"], result["draw_prob"], result["away_prob"],
        result["cv_home"] * 100, result["cv_draw"] * 100, result["cv_away"] * 100,
    )

    return result


# ── Consensus computation ─────────────────────────────────────────────────

def _compute_consensus(
    bookmakers: list[dict[str, Any]],
    captured_at: str,
) -> dict[str, Any] | None:
    """Compute median-consensus odds and de-vig probabilities.

    Args:
        bookmakers: List of {"name": str, "home": float, "draw": float, "away": float}
        captured_at: ISO timestamp of when odds were collected

    Returns consensus dict or None if insufficient data.
    """
    homes = [b["home"] for b in bookmakers if b.get("home", 0) > 1.0]
    draws = [b["draw"] for b in bookmakers if b.get("draw", 0) > 1.0]
    aways = [b["away"] for b in bookmakers if b.get("away", 0) > 1.0]

    if len(homes) < 3 or len(draws) < 3 or len(aways) < 3:
        return None

    median_home = statistics.median(homes)
    median_draw = statistics.median(draws)
    median_away = statistics.median(aways)

    # De-vig via domain-driven method (Karimov et al. 2025).
    # Corrects for systematic bookmaker bias: draw/away overestimation.
    from app.services.market.probability import normalize_1x2_domain_driven
    corrected = normalize_1x2_domain_driven(median_home, median_draw, median_away)
    implied_h = corrected["home"]
    implied_d = corrected["draw"]
    implied_a = corrected["away"]
    # Compute original overround from raw odds for diagnostic purposes
    raw_total = 1.0 / median_home + 1.0 / median_draw + 1.0 / median_away

    # Coefficient of variation (CV = std / mean)
    cv_home = statistics.stdev(homes) / statistics.mean(homes) if len(homes) > 1 else 0
    cv_draw = statistics.stdev(draws) / statistics.mean(draws) if len(draws) > 1 else 0
    cv_away = statistics.stdev(aways) / statistics.mean(aways) if len(aways) > 1 else 0

    bookmaker_names = [b.get("name", "?") for b in bookmakers]

    return {
        "home_prob": implied_h,   # already normalized by domain-driven de-vig
        "draw_prob": implied_d,
        "away_prob": implied_a,
        "home_odds": median_home,
        "draw_odds": median_draw,
        "away_odds": median_away,
        "provider": "web-search-consensus",
        "overround": raw_total - 1.0,  # original bookmaker margin
        "bookmaker": f"{len(bookmakers)}-bookmaker-consensus",
        "sample_bookmakers": len(bookmakers),
        "cv_home": cv_home,
        "cv_draw": cv_draw,
        "cv_away": cv_away,
        "bookmaker_list": bookmaker_names,
        "captured_at": captured_at,
        "web_verified": True,
    }


# ── Cache ingestion (called by ingest_web_odds.py CLI) ────────────────────

def ingest(
    home_team: str,
    away_team: str,
    bookmakers: list[dict[str, Any]],
    over_under: list[dict[str, Any]] | None = None,
    to_advance: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Write multi-bookmaker odds into the web cache.

    Args:
        home_team: Home team name
        away_team: Away team name
        bookmakers: [{"name": "Bet365", "region": "UK", "home": 1.75, "draw": 3.60, "away": 4.75}, ...]
        over_under: Optional O/U odds per bookmaker
        to_advance: Optional to-advance odds per bookmaker

    Returns the entry that was written.
    """
    # Load existing cache
    cache: dict[str, Any] = {}
    if _CACHE_PATH.exists():
        try:
            cache = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cache = {}

    now_iso = datetime.now(timezone.utc).isoformat()
    key = f"{home_team}|{away_team}"

    entry: dict[str, Any] = {
        "captured_at": now_iso,
        "bookmakers": bookmakers,
    }
    if over_under:
        entry["over_under"] = over_under
    if to_advance:
        entry["to_advance"] = to_advance

    # Preserve schema metadata if present
    schema = cache.pop("_schema", "1.0")
    description = cache.pop("_description", "")
    ttl = cache.pop("_ttl_hours", _CACHE_TTL_HOURS)

    cache[key] = entry

    # Restore metadata at top
    result: dict[str, Any] = {
        "_schema": schema,
        "_description": description,
        "_ttl_hours": ttl,
    }
    result.update(cache)

    # Atomic write
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _CACHE_PATH.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp_path.replace(_CACHE_PATH)

    logger.info(
        "Ingested %d bookmakers for '%s' into web odds cache",
        len(bookmakers), key,
    )
    return entry


def cache_stats() -> dict[str, Any]:
    """Return cache statistics for monitoring."""
    if not _CACHE_PATH.exists():
        return {"exists": False, "matches": 0}

    try:
        cache = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"exists": False, "matches": 0, "error": "parse_failed"}

    matches = {k: v for k, v in cache.items() if not k.startswith("_")}
    stats = {
        "exists": True,
        "matches": len(matches),
        "ttl_hours": cache.get("_ttl_hours", _CACHE_TTL_HOURS),
        "entries": [],
    }

    for key, entry in matches.items():
        bm_count = len(entry.get("bookmakers", []))
        captured = entry.get("captured_at", "?")
        stats["entries"].append({
            "match": key,
            "bookmakers": bm_count,
            "captured_at": captured,
        })

    return stats
