#!/usr/bin/env python3
"""Environment verification script for WC26 Predict.

Checks: Python version, critical imports, DeepSeek config, DB integrity,
env safety, and output policy compliance.

Usage:
    python scripts/verify_env.py          # full check
    python scripts/verify_env.py --ci     # CI mode (no DB check)
    python scripts/verify_env.py --quick  # minimal check (imports + config only)
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"

EXIT_OK = 0
EXIT_WARN = 1
EXIT_FAIL = 2


def check_python_version() -> tuple[str, str]:
    """Python >= 3.11 required."""
    v = sys.version_info
    if v >= (3, 11):
        return PASS, f"Python {v.major}.{v.minor}.{v.micro}"
    return FAIL, f"Python {v.major}.{v.minor}.{v.micro} (need >= 3.11)"


def check_critical_imports() -> list[tuple[str, str]]:
    """Verify all critical packages can be imported."""
    results = []
    packages = [
        ("numpy", "np"),
        ("pandas", "pd"),
        ("scipy", "scipy"),
        ("sklearn", "scikit-learn"),
        ("fastapi", "fastapi"),
        ("httpx", "httpx"),
        ("pydantic_settings", "pydantic-settings"),
        ("sqlalchemy", "sqlalchemy"),
        ("penaltyblog", "penaltyblog"),
    ]
    for module, pkg_name in packages:
        try:
            __import__(module)
            results.append((PASS, pkg_name))
        except ImportError:
            results.append((FAIL, f"{pkg_name} NOT INSTALLED"))
    return results


def check_deepseek_config() -> list[tuple[str, str]]:
    """Verify DeepSeek V4 Pro is the configured model, without printing API key."""
    results = []
    model = os.environ.get("LLM_MODEL", "")
    provider = os.environ.get("LLM_PROVIDER", "")
    base_url = os.environ.get("LLM_BASE_URL", "")

    if provider == "deepseek" or not provider:
        results.append((PASS, f"LLM_PROVIDER={provider or '(default: deepseek)'}"))
    else:
        results.append((FAIL, f"LLM_PROVIDER={provider} (expected: deepseek)"))

    if model == "deepseek-v4-pro":
        results.append((PASS, f"LLM_MODEL=deepseek-v4-pro"))
    elif model == "deepseek-chat":
        results.append((FAIL, f"LLM_MODEL=deepseek-chat (deprecated — use deepseek-v4-pro)"))
    elif not model:
        # Check config.py default
        try:
            from app.config import get_settings
            default_model = get_settings().llm_model
            if default_model == "deepseek-v4-pro":
                results.append((PASS, f"LLM_MODEL=(default: {default_model})"))
            else:
                results.append((FAIL, f"LLM_MODEL default is {default_model} (expected: deepseek-v4-pro)"))
        except Exception:
            results.append((WARN, "LLM_MODEL not set and cannot load config default"))
    else:
        results.append((WARN, f"LLM_MODEL={model}"))

    api_key = os.environ.get("LLM_API_KEY", "")
    if api_key:
        masked = api_key[:4] + "****" + api_key[-4:] if len(api_key) > 8 else "****"
        results.append((PASS, f"LLM_API_KEY={masked}"))
    else:
        results.append((WARN, "LLM_API_KEY not set (signal extraction will fail)"))

    # Check base URL
    if base_url:
        if "/v1" in base_url:
            results.append((WARN, f"LLM_BASE_URL={base_url} — contains /v1; should be https://api.deepseek.com (without /v1). The adapter appends /v1 internally."))
        else:
            results.append((PASS, f"LLM_BASE_URL={base_url}"))
    else:
        results.append((WARN, "LLM_BASE_URL not set (will use code default: https://api.deepseek.com)"))

    return results


def check_db_integrity(db_path: Path | None = None) -> list[tuple[str, str]]:
    """Verify SQLite database exists and has expected tables."""
    if db_path is None:
        db_path = BACKEND_DIR / "data" / "local_stage2.db"

    results = []
    if not db_path.exists():
        results.append((FAIL, f"DB not found: {db_path}"))
        return results

    try:
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()

        # Check critical tables exist
        critical_tables = [
            "matches", "teams", "prediction_snapshots",
            "news_articles", "news_signals", "market_odds",
            "postmatch_eval", "source_registry",
        ]
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing = {r[0] for r in c.fetchall()}

        for table in critical_tables:
            if table in existing:
                results.append((PASS, f"Table exists: {table}"))
            else:
                results.append((WARN, f"Table missing: {table}"))

        # Check record counts
        c.execute("SELECT COUNT(*) FROM matches")
        match_count = c.fetchone()[0]
        results.append((PASS if match_count > 0 else WARN, f"matches: {match_count}"))

        c.execute("SELECT COUNT(*) FROM news_signals")
        sig_count = c.fetchone()[0]
        results.append((PASS if sig_count > 0 else WARN, f"news_signals: {sig_count}"))

        c.execute("SELECT COUNT(*) FROM news_articles")
        art_count = c.fetchone()[0]
        results.append((PASS if art_count > 0 else WARN, f"news_articles: {art_count}"))

        conn.close()
    except Exception as e:
        results.append((FAIL, f"DB error: {e}"))

    return results


def check_env_safety() -> list[tuple[str, str]]:
    """Check for unsafe default values."""
    results = []

    admin_token = os.environ.get("ADMIN_TOKEN", "")
    if admin_token == "change-me" or admin_token == "":
        results.append((WARN, "ADMIN_TOKEN is default 'change-me' or empty — unsafe for production"))
    else:
        results.append((PASS, "ADMIN_TOKEN is set (non-default)"))

    # Check we don't print full keys
    for var in ["LLM_API_KEY", "FOOTBALL_DATA_API_KEY", "ODDS_API_KEY",
                "API_FOOTBALL_KEY", "APIFOOTBALL_COM_KEY", "DEEPSEEK_API_KEY"]:
        val = os.environ.get(var, "")
        key_len = len(val)
        if key_len > 0:
            results.append((PASS, f"{var}=**** (len={key_len})"))
        # Don't warn for missing optional keys

    return results


def main():
    parser = argparse.ArgumentParser(description="WC26 Predict environment verification")
    parser.add_argument("--ci", action="store_true", help="CI mode (skip DB check)")
    parser.add_argument("--quick", action="store_true", help="Quick check (imports + config only)")
    args = parser.parse_args()

    all_results: list[tuple[str, list[tuple[str, str]]]] = []
    exit_code = EXIT_OK

    # Always run these
    sections = [("Python Version", [check_python_version()])]

    sections.append(("Critical Imports", check_critical_imports()))
    sections.append(("DeepSeek Config", check_deepseek_config()))
    sections.append(("Env Safety", check_env_safety()))

    if not args.ci and not args.quick:
        sections.append(("Database Integrity", check_db_integrity()))

    # Print results
    print("=" * 60)
    print("WC26 Predict — Environment Verification")
    print("=" * 60)

    for section_name, results in sections:
        print(f"\n--- {section_name} ---")
        for status, msg in results:
            prefix = {"PASS": "  [PASS]", "FAIL": "  [FAIL]", "WARN": "  [WARN]"}[status]
            print(f"{prefix} {msg}")
            if status == FAIL:
                exit_code = EXIT_FAIL
            elif status == WARN and exit_code != EXIT_FAIL:
                exit_code = EXIT_WARN

    print("\n" + "=" * 60)
    if exit_code == EXIT_OK:
        print("All checks passed.")
    elif exit_code == EXIT_WARN:
        print("Warnings found — review before production use.")
    else:
        print("FAILURES found — must fix before running.")
    print("=" * 60)

    if args.ci:
        # CI mode: non-zero exit on any failure
        sys.exit(0 if exit_code != EXIT_FAIL else 1)
    else:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
