# Injury Provider Coverage Report

Generated: 2026-06-09 11:52 UTC

---

## 1. Summary

| Provider | Key Configured | Status | Notes |
|----------|---------------|--------|-------|
| api-sports | **No** | no_key_configured | API_FOOTBALL_KEY is empty — set it in .env.local to use this provider |
| apifootball.com | Yes | partial_support |  |
| football-data.org | Yes | success |  |

## 2. Recommendation

**API_FOOTBALL_KEY is not configured.** This is the primary injuries data source. To enable:

1. Sign up at https://www.api-football.com/
2. Copy your API key
3. Add to `.env.local`: `API_FOOTBALL_KEY=your_key_here`
4. Rerun this probe

Until then, the injury pipeline will remain seed-data-only.

**apifootball.com** has some player data available. This is a partial fallback but does not provide structured injury records comparable to the API-Sports `/injuries` endpoint.

**football-data.org** has team roster data via `/competitions/WC/teams`. This can provide squad lists but not injury status.

## 3. Next Steps

- [ ] Configure `API_FOOTBALL_KEY` in `.env.local`
- [ ] Rerun this probe
- [ ] If probe succeeds: implement injury adapter (Ticket 6b)
- [ ] Fallback: continue with seed `injuries.json` for manual injury updates

## 4. Per-Provider Detail

### api-sports

- **provider**: api-sports
- **base_url**: https://v3.football.api-sports.io
- **endpoint**: /injuries
- **status**: no_key_configured
- **error**: API_FOOTBALL_KEY is empty — set it in .env.local to use this provider
- **sample_count**: 0
- **competition_coverage**: {}

### apifootball.com

- **provider**: apifootball.com
- **base_url**: https://apiv3.apifootball.com/
- **status**: partial_support
- **sample_count**: 0
- **endpoint_get_players_status**: 200
- **endpoint_get_players_count**: 4
- **endpoint_get_sidelined_status**: 200
- **endpoint_get_sidelined_count**: 0
- **endpoint_get_injuries_status**: 200
- **endpoint_get_injuries_count**: 0

### football-data.org

- **provider**: football-data.org
- **base_url**: https://api.football-data.org/v4
- **status**: success
- **competitions_teams_status**: 200
- **wc_teams_count**: 48
- **sample_team**: Uruguay
- **sample_file**: D:\hermes agent\2026世界杯分析\backend\data\injury_probes\20260609T115235Z_football-data_wc_teams.json
