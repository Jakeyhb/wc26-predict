"""injury_provider_probe.py — Probe injury data providers for WC26 coverage.

Reads API keys from .env, tests each provider endpoint, records:
- Status: reachable / auth_error / not_supported / no_coverage
- Coverage: which competitions/teams are covered
- Field quality: which fields are populated
- Sample response: saved to backend/data/injury_probes/ (gitignored)

Does NOT inject data into the model. Read-only probe.

Usage:
    python scripts/injury_provider_probe.py              # full probe
    python scripts/injury_provider_probe.py --provider api-sports  # single provider
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
PROBE_DIR = BACKEND_DIR / "data" / "injury_probes"
PROBE_DIR.mkdir(parents=True, exist_ok=True)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _save_sample(provider: str, label: str, data: dict | list | str) -> Path:
    """Save a raw response sample to disk (gitignored)."""
    fname = f"{_timestamp()}_{provider}_{label}.json"
    fpath = PROBE_DIR / fname
    with open(fpath, "w", encoding="utf-8") as f:
        if isinstance(data, (dict, list)):
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        else:
            f.write(str(data))
    return fpath


# ============================================================================
# Provider 1: API-Sports / api-football.com  (injuries endpoint)
# ============================================================================

API_SPORTS_BASE = "https://v3.football.api-sports.io"


def probe_api_sports_injuries(api_key: str | None) -> dict:
    """Probe https://v3.football.api-sports.io/injuries

    Requires: x-apisports-key header (API_FOOTBALL_KEY in .env)
    """
    result = {
        "provider": "api-sports",
        "base_url": API_SPORTS_BASE,
        "endpoint": "/injuries",
        "has_key": bool(api_key),
        "status": "not_tested",
        "error": None,
        "sample_count": 0,
        "sample_file": None,
        "fields_available": [],
        "fields_missing": [],
        "competition_coverage": {},
    }

    if not api_key:
        result["status"] = "no_key_configured"
        result["error"] = "API_FOOTBALL_KEY is empty — set it in .env.local to use this provider"
        return result

    try:
        # First check: do any leagues we care about have injury coverage?
        # Known FIFA World Cup league ID on API-Sports: league=1
        # Known World Cup 2026 season: 2026
        wc_params = {"league": "1", "season": "2026"}
        wc_url = f"{API_SPORTS_BASE}/injuries"

        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                wc_url,
                params=wc_params,
                headers={"x-apisports-key": api_key},
            )

        result["http_status"] = resp.status_code

        if resp.status_code == 200:
            data = resp.json()
            errors = data.get("errors", [])
            if errors:
                result["status"] = "api_error"
                result["error"] = str(errors)
            else:
                items = data.get("response", [])
                result["status"] = "success"
                result["sample_count"] = len(items)
                if items:
                    result["sample_file"] = str(_save_sample(
                        "api-sports", "injuries_wc2026", data
                    ))
                    _analyze_fields(items, result)
        elif resp.status_code == 401 or resp.status_code == 403:
            result["status"] = "auth_error"
            result["error"] = f"HTTP {resp.status_code} — API key may be invalid or expired"
        elif resp.status_code == 404:
            result["status"] = "endpoint_not_found"
            result["error"] = "Injuries endpoint returned 404"
        else:
            result["status"] = "unexpected_status"
            result["error"] = f"HTTP {resp.status_code}: {resp.text[:200]}"

    except httpx.ConnectError as e:
        result["status"] = "connection_error"
        result["error"] = str(e)
    except Exception as e:
        result["status"] = "exception"
        result["error"] = f"{type(e).__name__}: {e}"

    return result


def _analyze_fields(items: list[dict], result: dict) -> None:
    """Analyze which fields are present/missing in response items."""
    all_fields = set()
    null_fields: dict[str, int] = {}

    for item in items[:20]:  # sample first 20
        for key, val in item.items():
            all_fields.add(key)
            if val is None or val == "" or val == []:
                null_fields[key] = null_fields.get(key, 0) + 1

    result["fields_available"] = sorted(all_fields)
    result["fields_missing"] = [
        k for k, v in null_fields.items() if v == min(20, len(items))
    ]
    result["field_null_rates"] = {
        k: f"{v}/{min(20, len(items))}" for k, v in null_fields.items() if v > 0
    }


# ============================================================================
# Provider 2: apifootball.com  (check if injuries exist)
# ============================================================================

APIFOOTBALL_BASE = "https://apiv3.apifootball.com/"


def probe_apifootball_injuries(api_key: str | None) -> dict:
    """Probe apifootball.com for injuries-like data.

    apifootball.com primarily provides odds, but we check whether they
    have player availability / squad data.
    """
    result = {
        "provider": "apifootball.com",
        "base_url": APIFOOTBALL_BASE,
        "has_key": bool(api_key),
        "status": "not_tested",
        "error": None,
        "sample_count": 0,
        "sample_file": None,
        "fields_available": [],
        "fields_missing": [],
    }

    if not api_key:
        result["status"] = "no_key_configured"
        result["error"] = "APIFOOTBALL_COM_KEY is empty"
        return result

    # apifootball.com API reference: action=get_teams, get_players, etc.
    # Check if they have any squad/player endpoint
    endpoints_to_try = [
        ("get_players", {"player_name": "Mbappe"}),
        ("get_sidelined", {}),
        ("get_injuries", {}),
    ]

    for action, params in endpoints_to_try:
        try:
            merged = {"action": action, "APIkey": api_key, **params}
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(APIFOOTBALL_BASE, params=merged)

            result[f"endpoint_{action}_status"] = resp.status_code

            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and data.get("error"):
                    result[f"endpoint_{action}_msg"] = str(data["error"])[:200]
                elif isinstance(data, (dict, list)):
                    count = len(data) if isinstance(data, list) else len(data.get("players", data.get("response", [])))
                    result[f"endpoint_{action}_count"] = count
                    result["status"] = "partial_support"
            else:
                result[f"endpoint_{action}_msg"] = f"HTTP {resp.status_code}"

        except Exception as e:
            result[f"endpoint_{action}_error"] = str(e)[:200]

    return result


# ============================================================================
# Provider 3: football-data.org  (check for squad data)
# ============================================================================

FOOTBALL_DATA_BASE = "https://api.football-data.org/v4"


def probe_football_data_squads(api_key: str | None) -> dict:
    """Check football-data.org for team squad data.

    football-data.org doesn't have a dedicated injuries endpoint, but
    the /teams/{id} endpoint includes a 'squad' field with player info.
    """
    result = {
        "provider": "football-data.org",
        "base_url": FOOTBALL_DATA_BASE,
        "has_key": bool(api_key),
        "status": "not_tested",
        "error": None,
    }

    if not api_key:
        result["status"] = "no_key_configured"
        result["error"] = "FOOTBALL_DATA_API_KEY is empty"
        return result

    # World Cup 2026 competition code: WC
    try:
        with httpx.Client(timeout=10.0) as client:
            # Check competitions
            resp = client.get(
                f"{FOOTBALL_DATA_BASE}/competitions/WC/teams",
                headers={"X-Auth-Token": api_key},
            )
            result["competitions_teams_status"] = resp.status_code

            if resp.status_code == 200:
                data = resp.json()
                teams = data.get("teams", [])
                result["wc_teams_count"] = len(teams)
                if teams:
                    result["sample_team"] = teams[0].get("name", "?")
                    result["sample_file"] = str(_save_sample(
                        "football-data", "wc_teams", data
                    ))
                    result["status"] = "success"
            else:
                result["error"] = f"HTTP {resp.status_code}"

    except Exception as e:
        result["status"] = "exception"
        result["error"] = str(e)[:200]

    return result


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Probe injury data providers")
    parser.add_argument("--provider", choices=["api-sports", "apifootball", "football-data"])
    args = parser.parse_args()

    from app.config import get_settings
    settings = get_settings()

    api_sports_key = settings.api_football_key  # API_FOOTBALL_KEY
    apifootball_key = settings.apifootball_com_key  # APIFOOTBALL_COM_KEY
    football_data_key = settings.football_data_api_key  # FOOTBALL_DATA_API_KEY

    results = {}

    print("=" * 70)
    print("WC26 Predict — Injury Provider Probe")
    print(f"Run: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Samples saved to: {PROBE_DIR}")
    print("=" * 70)

    # Key status
    print("\n--- API Key Status ---")
    for name, key in [
        ("API_FOOTBALL_KEY (api-sports)", api_sports_key),
        ("APIFOOTBALL_COM_KEY (apifootball.com)", apifootball_key),
        ("FOOTBALL_DATA_API_KEY (football-data.org)", football_data_key),
    ]:
        status = "CONFIGURED" if key else "EMPTY"
        print(f"  {name}: {status}")

    if not args.provider or args.provider == "api-sports":
        print("\n--- Provider 1: API-Sports / api-football.com ---")
        r = probe_api_sports_injuries(api_sports_key)
        results["api-sports"] = r
        _print_result(r)

    if not args.provider or args.provider == "apifootball":
        print("\n--- Provider 2: apifootball.com ---")
        r = probe_apifootball_injuries(apifootball_key)
        results["apifootball.com"] = r
        _print_result(r)

    if not args.provider or args.provider == "football-data":
        print("\n--- Provider 3: football-data.org ---")
        r = probe_football_data_squads(football_data_key)
        results["football-data.org"] = r
        _print_result(r)

    # Save full report
    report_path = BACKEND_DIR / "docs" / "provider_coverage_report.md"
    _write_report(report_path, results, api_sports_key, apifootball_key, football_data_key)

    # Save raw results JSON
    json_path = _save_sample("probe", "results", results)
    print(f"\nFull probe results: {json_path}")
    print(f"Coverage report: {report_path}")
    print("=" * 70)


def _print_result(r: dict) -> None:
    print(f"  Status:      {r.get('status', '?')}")
    if r.get("error"):
        print(f"  Error:       {r['error']}")
    print(f"  Has key:     {r.get('has_key', False)}")
    if r.get("http_status"):
        print(f"  HTTP:        {r['http_status']}")
    if r.get("sample_count"):
        print(f"  Items:       {r['sample_count']}")
    if r.get("sample_file"):
        print(f"  Sample:      {r['sample_file']}")
    if r.get("fields_available"):
        print(f"  Fields:      {', '.join(r['fields_available'][:12])}")
    if r.get("fields_missing"):
        print(f"  Always null: {', '.join(r['fields_missing'][:8])}")


def _write_report(
    path: Path,
    results: dict,
    api_sports_key: str | None,
    apifootball_key: str | None,
    football_data_key: str | None,
) -> None:
    """Write the coverage report in Markdown."""
    lines = []

    lines.append("# Injury Provider Coverage Report")
    lines.append(f"\nGenerated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("\n---\n")

    # Summary table
    lines.append("## 1. Summary\n")
    lines.append("| Provider | Key Configured | Status | Notes |")
    lines.append("|----------|---------------|--------|-------|")

    for name, r in results.items():
        key_ok = "Yes" if r["has_key"] else "**No**"
        status = r["status"]
        note = r.get("error", "")[:80] if r.get("error") else ""
        lines.append(f"| {name} | {key_ok} | {status} | {note} |")

    lines.append("")

    # Recommendation
    lines.append("## 2. Recommendation\n")

    api_sports_ok = results.get("api-sports", {}).get("status") == "success"
    apifootball_ok = results.get("apifootball.com", {}).get("status") in ("success", "partial_support")
    football_data_ok = results.get("football-data.org", {}).get("status") == "success"

    if api_sports_ok:
        lines.append(
            "**API-Sports injuries endpoint is available.** Proceed to Ticket 6b "
            "(injury adapter implementation)."
        )
    elif not api_sports_key:
        lines.append(
            "**API_FOOTBALL_KEY is not configured.** This is the primary injuries "
            "data source. To enable:\n\n"
            "1. Sign up at https://www.api-football.com/\n"
            "2. Copy your API key\n"
            "3. Add to `.env.local`: `API_FOOTBALL_KEY=your_key_here`\n"
            "4. Rerun this probe\n\n"
            "Until then, the injury pipeline will remain seed-data-only."
        )
    else:
        lines.append(
            f"**API-Sports injuries endpoint returned: {results.get('api-sports', {}).get('status')}** "
            f"— {results.get('api-sports', {}).get('error', '')}\n\n"
            "Check API key validity and plan limits."
        )

    if apifootball_ok:
        lines.append(
            "\n**apifootball.com** has some player data available. This is a "
            "partial fallback but does not provide structured injury records "
            "comparable to the API-Sports `/injuries` endpoint."
        )

    if football_data_ok:
        lines.append(
            "\n**football-data.org** has team roster data via `/competitions/WC/teams`. "
            "This can provide squad lists but not injury status."
        )

    lines.append("")
    lines.append("## 3. Next Steps\n")

    if api_sports_key:
        lines.append(
            "- [ ] If probe succeeded: implement injury adapter (Ticket 6b)\n"
            "- [ ] If probe failed: debug API key / plan limits / endpoint availability"
        )
    else:
        lines.append(
            "- [ ] Configure `API_FOOTBALL_KEY` in `.env.local`\n"
            "- [ ] Rerun this probe\n"
            "- [ ] If probe succeeds: implement injury adapter (Ticket 6b)\n"
            "- [ ] Fallback: continue with seed `injuries.json` for manual injury updates"
        )

    lines.append("\n## 4. Per-Provider Detail\n")

    for name, r in results.items():
        lines.append(f"### {name}\n")
        for k, v in r.items():
            if k in ("fields_available", "fields_missing"):
                continue
            if v is not None and k not in ("has_key",):
                lines.append(f"- **{k}**: {v}")
        if r.get("fields_available"):
            lines.append(f"- **fields_available**: {', '.join(r['fields_available'])}")
        if r.get("fields_missing"):
            lines.append(f"- **always_null**: {', '.join(r['fields_missing'])}")
        if r.get("field_null_rates"):
            lines.append(f"- **null_rates**: {r['field_null_rates']}")
        lines.append("")

    report = "\n".join(lines)
    path.write_text(report, encoding="utf-8")
    return report


if __name__ == "__main__":
    main()
