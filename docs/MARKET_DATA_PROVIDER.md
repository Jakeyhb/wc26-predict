# WC26 Predict — Market Data Providers

This document describes the market odds data providers used by WC26 Predict for internal calibration research (shadow mode only).

> **IMPORTANT**: All market data is used exclusively for internal research and model calibration.  
> Public outputs (`creator_safe`, `public_safe`) must never expose odds, bookmaker names, or betting-oriented language.

---

## 1. Provider overview

WC26 Predict supports three market data providers:

| Provider | Base URL | Auth Method | Env Variable | Status |
|---|---|---|---|---|
| apifootball.com | `https://apiv3.apifootball.com/` | `APIkey` query param | `APIFOOTBALL_COM_KEY` | Base API OK, odds pending |
| API-Sports | `https://v3.football.api-sports.io` | `x-apisports-key` header | `API_FOOTBALL_KEY` | Not configured |
| The Odds API | `https://api.the-odds-api.com/v4` | `apiKey` query param | `ODDS_API_KEY` | Operational |

---

## 2. Service distinction

**API-Sports / api-football.com** and **apifootball.com** are two different services:

### API-Sports / api-football.com

- Base URL: `https://v3.football.api-sports.io`
- Auth: `x-apisports-key` HTTP header
- Env: `API_FOOTBALL_KEY`
- Free tier: 100 requests/day
- Code: `backend/app/services/market/api_football_provider.py`

### apifootball.com

- Base URL: `https://apiv3.apifootball.com/`
- Auth: `APIkey` query parameter (appended to every request URL)
- Env: `APIFOOTBALL_COM_KEY`
- Rate limit: not documented (subscription-plan dependent)
- Code: `backend/app/services/market/apifootball_com_provider.py`

---

## 3. Provider selection logic

The `MarketCalibrator` resolves the best available provider at runtime:

1. Try **apifootball.com** (if `APIFOOTBALL_COM_KEY` is set and `is_odds_available()` returns True)
2. Try **API-Sports** (if `API_FOOTBALL_KEY` is set and `is_available()` returns True)
3. Fall back to **The Odds API** (if `ODDS_API_KEY` is set)

If no provider has odds available, market calibration is automatically skipped. The prediction pipeline continues unaffected — this is graceful degradation, not a failure.

### Log messages

| Message | Meaning |
|---|---|
| `no_provider` | No API key configured for any provider |
| `provider_no_odds` | Provider's base API works but odds endpoint unavailable (plan-limited or no data) |
| `no_match` | No matching fixture found for the given team names |
| `no_odds_for_match` | Match found but no odds data available for it |

---

## 4. Diagnostic script

Run to check all provider statuses:

```bash
cd backend
python scripts/check_market_providers.py
```

This script:
- Shows which keys are configured (masked: first 4 + last 4 characters only)
- Checks base API availability for each provider
- Checks odds endpoint availability
- Reports whether market calibration can currently run
- Never prints full API keys

---

## 5. Graceful degradation

Market calibration failure never blocks the main prediction pipeline.

If a provider returns an error:
- `fetch()` returns `None`
- `MarketCalibrator.calibrate()` returns model probabilities unchanged
- Errors are logged at `WARNING` level
- The prediction snapshot is still generated successfully

---

## 6. Compliance boundary

- Market data is **internal research only**
- Public-safe and creator-safe outputs must not include: odds numbers, bookmaker names, provider names, betting language
- The `audit_public_outputs_no_odds.py` script scans for forbidden terms before any public release
- For full compliance rules, see [`docs/COMPLIANCE_AND_OUTPUT_POLICY.md`](COMPLIANCE_AND_OUTPUT_POLICY.md)

---

## 7. Adding a new provider

To add a new market data provider:

1. Create a new file in `backend/app/services/market/`
2. Implement the `MarketProvider` abstract base class (see `provider_base.py`)
3. Add the provider to `MarketCalibrator._resolve_odds_provider()` with appropriate priority
4. Add the API key to `backend/app/config.py` (with `alias=` for the env var name)
5. Add a placeholder to `.env.example`
6. Update this document
