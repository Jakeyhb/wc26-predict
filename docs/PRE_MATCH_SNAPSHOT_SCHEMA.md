# PreMatchSnapshot JSON Schema v1

The `pre_match_snapshots` table captures an **immutable, timestamped record** of
everything that went into a prediction at the moment it was frozen. This schema
defines the contract for downstream consumers (audit, backtest, dashboard).

## Contract invariants

1. **Immutable**: Once written, a snapshot row is never updated. Predictions for
   the same match at different times produce *separate* snapshot rows.
2. **Tamper-evident**: `input_hash` = SHA256 of all inputs. Any change to input
   data produces a different hash.
3. **Traceable**: `code_version` + `git_commit` + `snapshot_at` uniquely identify
   the software and data state at generation time.
4. **Degradation explicit**: `degraded_reasons` and `missing_inputs` document
   what was unavailable — never silent.

## Column reference

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `id` | UUID (str) | Yes | Primary key, generated at save time |
| `match_id` | str | No | FK to matches table (name-based, not enforced) |
| `snapshot_at` | ISO 8601 | Yes | UTC timestamp when snapshot was frozen (`freeze_time`) |
| `kickoff_at` | ISO 8601 | No | Scheduled match kickoff |
| `hours_to_kickoff` | float | No | Hours from snapshot to kickoff |
| `home_team` | str | Yes | Home team name (canonical) |
| `away_team` | str | Yes | Away team name (canonical) |
| `competition` | str | Yes | Competition name |
| `is_neutral` | bool | Yes | Neutral venue flag |
| `weather_available` | bool | Yes | Weather data was available |
| `odds_available` | bool | Yes | Odds data was available |
| `lineup_available` | bool | Yes | Lineup data was available |
| `injury_data_available` | bool | Yes | Injury data was available |
| `news_signals_available` | bool | Yes | Approved news signals were available |
| `weather_snapshot` | JSON | No | Weather conditions at freeze time |
| `odds_snapshot` | JSON | No | Raw odds from providers |
| `lineup_snapshot` | JSON | No | Starting lineups if available |
| `injury_records` | JSON | No | List of injury records applied |
| `news_signal_ids` | JSON (list) | No | IDs of applied news signals |
| `component_probs` | JSON | No | Per-model probabilities before fusion |
| `final_home_prob` | float | Yes | Fused home win probability |
| `final_draw_prob` | float | Yes | Fused draw probability |
| `final_away_prob` | float | Yes | Fused away win probability |
| `home_xg` | float | No | Expected goals (home) |
| `away_xg` | float | No | Expected goals (away) |
| `top_scores` | JSON (list) | No | Most likely scorelines |
| `weight_config_label` | str | No | Which weight config was used |
| `weight_config` | JSON | No | Full weight configuration |
| `effective_weights` | JSON | No | Actual weights after fusion |
| `fusion_graph` | JSON | No | Step-by-step fusion trace |
| `model_disagreement` | float | No | Max pairwise model disagreement |
| `market_blended` | bool | No | Market odds blended into fusion |
| `market_weight_used` | float | No | Weight given to market signal |
| `market_divergence` | float | No | Model vs market probability gap |
| `confidence` | str | No | Confidence tier (high/medium/low) |
| `confidence_penalty` | float | No | Penalty applied to confidence |
| `risk_tags` | JSON (list) | No | Risk labels (e.g. "主队不利情报") |
| `pipeline_status` | str | No | "full" / "degraded" / "partial" |
| `missing_inputs` | JSON (list) | No | Input categories that were absent |
| `degraded_reasons` | JSON (list) | No | Per-source degradation reasons |
| `code_version` | str | Yes | Semantic version from `version.py` |
| `model_version` | str | No | Model artifact version |
| `data_fingerprint` | str | No | Data pipeline fingerprint |
| `git_commit` | str (40) | No | Full git commit SHA at generation |
| `input_hash` | str (64) | No | SHA256 of all input data |
| `source_timestamps` | JSON | No | Per-source fetch timestamps |
| `odds_snapshot_id` | str | No | Reference to market_consensus_snapshots.id |
| `weather_snapshot_id` | str | No | Reference to weather data row |
| `injury_snapshot_id` | str | No | Reference to injury data row |
| `prediction_mode` | str | No | "full" / "baseline" / "standard" |
| `report_markdown` | text | No | Full LLM-generated report |
| `llm_analysis` | text | No | Raw LLM analysis output |

## input_hash algorithm

```
input_payload = JSON.stringify({
    home_team, away_team, competition, is_neutral,
    weather: weather_snapshot,
    odds: odds_snapshot,
    lineup: lineup_snapshot,
    injuries: injury_records,
    news_signal_ids,
    code_version,
    weight_config_label,
    mode,
}, sort_keys=true, ensure_ascii=false)
input_hash = SHA256(input_payload)
```

## source_timestamps format

```json
{
    "weather_fetched_at": "2026-06-09T12:00:00+00:00",
    "odds_fetched_at": "2026-06-09T12:01:00+00:00",
    "lineup_fetched_at": "2026-06-09T12:02:00+00:00",
    "injuries_fetched_at": "2026-06-09T12:00:30+00:00",
    "news_signals_fetched_at": "2026-06-09T11:55:00+00:00"
}
```

## Database support

- **SQLite**: `_ensure_table()` in `snapshot_service.py` creates the table
  idempotently. This is the primary path for CLI and Dashboard usage.
- **PostgreSQL**: Alembic migration `c1e2f3a4b5c6` creates the table via SQLAlchemy.
  This is the path for production deployments.
