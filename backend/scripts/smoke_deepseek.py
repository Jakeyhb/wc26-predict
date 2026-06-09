"""DeepSeek V4 Pro smoke test — minimal JSON request to verify connectivity.

Usage:
    python scripts/smoke_deepseek.py          # full smoke test
    python scripts/smoke_deepseek.py --quick   # just test connectivity, no JSON

Prints the effective URL being used and masks API key.
Exits 0 on success, 1 on failure.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import httpx


def main():
    parser = argparse.ArgumentParser(description="DeepSeek V4 Pro smoke test")
    parser.add_argument("--quick", action="store_true", help="Connectivity-only test")
    args = parser.parse_args()

    from app.config import get_settings

    settings = get_settings()

    api_key = settings.llm_api_key or os.getenv("LLM_API_KEY", "")
    model = settings.llm_model or "deepseek-v4-pro"
    _base = (settings.llm_base_url or "https://api.deepseek.com").rstrip("/")
    effective_url = f"{_base}/v1/chat/completions"
    masked_key = api_key[:7] + "****" + api_key[-4:] if len(api_key) > 12 else "****"

    print("=" * 60)
    print("DeepSeek V4 Pro — Smoke Test")
    print("=" * 60)
    print(f"  Model:        {model}")
    print(f"  Base URL:     {_base}")
    print(f"  Effective:    {effective_url}")
    print(f"  API Key:      {masked_key}")

    if not api_key:
        print("\n  [SKIP] No LLM_API_KEY configured — skipping live test.")
        print("  Set LLM_API_KEY in .env.local to run the smoke test.")
        sys.exit(0)

    print("\n--- Sending smoke test request ---")

    try:
        with httpx.Client(timeout=30.0) as client:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a test validator. Respond with JSON only."},
                    {"role": "user", "content": 'Return exactly: {"status":"ok","model":"' + model + '"}  No other text.'},
                ],
                "temperature": 0.0,
                "max_tokens": 50,
                "response_format": {"type": "json_object"},
            }
            response = client.post(
                effective_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            print(f"  HTTP status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                print(f"  Response:    {content}")
                print("\n  [PASS] DeepSeek V4 Pro is reachable and responding.")
                sys.exit(0)
            elif response.status_code == 401:
                print("\n  [FAIL] 401 Unauthorized — API key is invalid or expired.")
                sys.exit(1)
            elif response.status_code == 404:
                print(f"\n  [FAIL] 404 Not Found — URL may be wrong: {effective_url}")
                print("  Check that LLM_BASE_URL does NOT end with /v1 (the adapter appends it).")
                sys.exit(1)
            else:
                print(f"\n  [FAIL] Unexpected response: {response.status_code}")
                print(f"  Body: {response.text[:500]}")
                sys.exit(1)

    except httpx.ConnectError as e:
        print(f"\n  [FAIL] Connection error: {e}")
        print("  Check network connectivity and that the URL is correct.")
        sys.exit(1)
    except httpx.TimeoutException:
        print("\n  [FAIL] Request timed out after 30s.")
        sys.exit(1)
    except Exception as e:
        print(f"\n  [FAIL] Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
