"""Diagnostic script: check all market data providers.

Checks:
  1. Which API keys are configured (masked display: first 4 + last 4)
  2. apifootball.com: base API availability + odds availability
  3. API-Sports: base API availability
  4. The Odds API: base API availability
  5. Which provider can currently be used for market calibration

Usage:
    python scripts/check_market_providers.py
    python scripts/check_market_providers.py --verbose
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ["POSTGRES_URL"] = "sqlite+aiosqlite:///./data/local_stage2.db"
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# Try loading env from backend/.env if present
_env_file = PROJECT_ROOT / ".env"
if _env_file.exists():
    with open(_env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                if key.strip() and val.strip() and key.strip() not in os.environ:
                    os.environ[key.strip()] = val.strip()


def mask_key(key: str | None) -> str:
    """Display key as first 4 + **** + last 4."""
    if not key:
        return "<not set>"
    if len(key) <= 8:
        return key[:4] + "****"
    return f"{key[:4]}****{key[-4:]}"


async def check_apifootball_com(verbose: bool = False) -> dict:
    """Check apifootball.com provider status."""
    from app.services.market.apifootball_com_provider import \
        ApifootballComProvider

    result = {
        "provider": "apifootball.com",
        "base_url": "https://apiv3.apifootball.com/",
        "auth": "APIkey query param",
        "key_configured": False,
        "key_masked": "",
        "base_api_ok": False,
        "odds_available": False,
        "can_calibrate": False,
    }

    prov = ApifootballComProvider()
    if prov.api_key:
        result["key_configured"] = True
        result["key_masked"] = mask_key(prov.api_key)

    try:
        result["base_api_ok"] = await prov.is_available()
        if result["base_api_ok"]:
            result["odds_available"] = await prov.is_odds_available()
            result["can_calibrate"] = result["odds_available"]
    except Exception as e:
        result["error"] = str(e)
    finally:
        await prov.close()

    return result


async def check_api_sports(verbose: bool = False) -> dict:
    """Check API-Sports / api-football.com provider status."""
    from app.services.market.api_football_provider import \
        ApiFootballProvider

    result = {
        "provider": "API-Sports / api-football.com",
        "base_url": "https://v3.football.api-sports.io",
        "auth": "x-apisports-key header",
        "key_configured": False,
        "key_masked": "",
        "base_api_ok": False,
        "can_calibrate": False,
    }

    prov = ApiFootballProvider()
    if prov.api_key:
        result["key_configured"] = True
        result["key_masked"] = mask_key(prov.api_key)

    try:
        result["base_api_ok"] = await prov.is_available()
        result["can_calibrate"] = result["base_api_ok"]
    except Exception as e:
        result["error"] = str(e)
    finally:
        await prov.close()

    return result


async def check_odds_api(verbose: bool = False) -> dict:
    """Check The Odds API status."""
    from app.config import get_settings

    result = {
        "provider": "The Odds API",
        "base_url": "https://api.the-odds-api.com/v4",
        "auth": "apiKey query param",
        "key_configured": False,
        "key_masked": "",
        "base_api_ok": False,
        "can_calibrate": False,
    }

    settings = get_settings()
    if settings.odds_api_key:
        result["key_configured"] = True
        result["key_masked"] = mask_key(settings.odds_api_key)

    if settings.odds_api_key:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "https://api.the-odds-api.com/v4/sports",
                    params={"apiKey": settings.odds_api_key},
                )
                result["base_api_ok"] = resp.status_code == 200
                result["can_calibrate"] = result["base_api_ok"]
                if not result["base_api_ok"]:
                    result["status_code"] = resp.status_code
        except Exception as e:
            result["error"] = str(e)

    return result


async def main():
    parser = argparse.ArgumentParser(
        description="Check all market data provider statuses"
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    print("=" * 60)
    print("MARKET DATA PROVIDER DIAGNOSTIC")
    print("=" * 60)
    print()

    # ── Key status ──
    print("── API Keys ──")
    from app.config import get_settings
    settings = get_settings()
    print(f"  APIFOOTBALL_COM_KEY : {mask_key(settings.apifootball_com_key)}")
    print(f"  API_FOOTBALL_KEY    : {mask_key(settings.api_football_key)}")
    print(f"  ODDS_API_KEY        : {mask_key(settings.odds_api_key)}")
    print()

    # ── Provider checks ──
    results = await asyncio.gather(
        check_apifootball_com(args.verbose),
        check_api_sports(args.verbose),
        check_odds_api(args.verbose),
    )

    any_odds = False

    for r in results:
        print(f"── {r['provider']} ──")
        print(f"  Key configured : [OK] {r['key_masked']}" if r['key_configured'] else f"  Key configured : [NO] {r['key_masked']}")
        status_ok = "[OK]" if r['base_api_ok'] else "[NO]"
        print(f"  Base API       : {status_ok} ", end="")
        if not r["base_api_ok"]:
            reason = r.get("error") or r.get("status_code") or "unknown"
            print(f"({reason})", end="")
        print()

        if "odds_available" in r:
            odds_ok = "[OK]" if r['odds_available'] else "[NO]"
            print(f"  Odds endpoint  : {odds_ok}")
        cal_ok = "[YES]" if r['can_calibrate'] else "[NO]"
        print(f"  Can calibrate  : {cal_ok}")
        if r.get("can_calibrate"):
            any_odds = True
        print()

    # ── Summary ──
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    if any_odds:
        print("  [OK] At least one market provider is ready for calibration.")
    else:
        print("  [WARN] No market provider has odds available.")
        print()
        has_keys = any(
            settings.apifootball_com_key
            or settings.api_football_key
            or settings.odds_api_key
        )
        if has_keys:
            print("  Keys are configured but odds are not available.")
            print("  Possible reasons:")
            print("    - Free tier doesn't include odds data")
            print("    - Subscription plan doesn't cover the requested leagues")
            print("    - No matches/odds in the current date range")
            print("    - Key needs activation at the provider's dashboard")
        else:
            print("  No market API keys are configured.")
            print("  Set one of: APIFOOTBALL_COM_KEY, API_FOOTBALL_KEY, ODDS_API_KEY")

    print()
    print("  Market calibration mode: SHADOW (internal research only)")
    print("  Public outputs must not expose odds, bookmakers, or betting terms.")


if __name__ == "__main__":
    asyncio.run(main())
