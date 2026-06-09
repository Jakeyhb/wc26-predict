# Design Decision: Unified Prediction Entry Point

**Status:** ACCEPTED
**Date:** 2026-06-09
**Author:** WC26 Predict team (Ticket 8)
**Version:** V3.1

---

## 1. Problem Statement

WC26 Predict currently has **three separate prediction "universes"** with 15+ call sites, each using subtly different model loading, fusion, and result formats.

### 1.1 The Three Universes

| Universe | Core File | Model Source | Callers | Issues |
|----------|----------|-------------|---------|--------|
| **Artifact** | `prediction_core.py`, `prediction_enhanced.py` | Pre-trained from `artifacts/` | `predict_match.py`, dashboard, `postmatch_review.py` | Sync-only, no DB awareness, no snapshot |
| **Fit** | `snapshot.py`, `fast_predict.py` | `.fit()` every call | `batch_snapshot.py`, `pregenerate_wc26.py`, `hourly_predict.py` | Inline fusion logic, duplicated code |
| **Orchestrator** | `prediction_orchestrator.py` | DB-smart filter + disk cache | API (`admin.py`, `predictions.py`), Celery tasks | Different training strategy, different result format |

### 1.2 Consequences

1. **Duplicated fusion logic** — `fuse_outcome_probabilities`, `fuse_elo_probabilities`, `fuse_pi_probabilities`, `fuse_weibull_probs` are re-implemented in each universe
2. **Inconsistent weight loading** — `get_weight_config()` is called differently in each universe
3. **Six different result containers** — plain dict, `EnhancedPredictionResult`, `PredictionResult`, UUID, nested dict from `snapshot.py`, minimal dict from `fast_predict.py`
4. **No shared error handling** — each universe catches and logs exceptions differently
5. **`degraded_reasons` contract violated** — only `PredictionPipeline` (unused) returns structured `DegradedReason` objects

### 1.3 Discovery

`PredictionPipeline` (`backend/app/services/prediction_pipeline.py`) was designed as the unified entry point in V2.8 but was **never connected to any caller**. It supports:

- 3-tier model caching (memory → disk → fit)
- Full component pipeline: DC → Enhancer → Weibull → Elo → Pi → Calibrator → SignalAdjuster → Market
- Standardized `PredictionResult` output with `to_dict()` backward compatibility
- Structured `degraded_reasons` accumulation
- Callback-injected DB operations (testable, swappable)

But it has **zero callers** — every prediction path still goes through the old universes.

---

## 2. Decision

### 2.1 Core Decision

**`PredictionPipeline.predict_match()` becomes the single entry point for all new prediction calls.**

All existing entry points continue to work but are marked `@deprecated` with migration guidance. They will be removed after 2 full release cycles (V3.3).

### 2.2 Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    CALLERS (future state)                     │
│  CLI scripts │ API routers │ Celery tasks │ Dashboard │ Tests │
└───────────────────────┬──────────────────────────────────────┘
                        │   predict_match(home, away, comp, ...)
                        ▼
┌──────────────────────────────────────────────────────────────┐
│                    PredictionPipeline                          │
│                                                               │
│  Factory Methods:                                             │
│  ├─ from_artifacts(mode) → sync, pre-trained models          │
│  └─ from_snapshot_env(...)  → async, auto-injects DB callbacks│
│                                                               │
│  Pipeline Steps (predict_match):                              │
│  1. Load training data (via callback or artifact)             │
│  2. Weight config (competition + stage aware)                 │
│  3. Dixon-Coles (3-tier cache: memory → disk → fit)           │
│  4. Tabular Enhancer (3-tier cache)                           │
│  5. Weibull Copula (optional)                                 │
│  6. DC+Enhancer fusion                                       │
│  7. Weibull fusion                                           │
│  8. Elo fit + predict + fusion                               │
│  9. Pi-Rating fit + predict + fusion                         │
│  10. Calibration monitor (record-only)                       │
│  11. Signal adjustment (venue + manual events)               │
│  12. Context adjustment                                      │
│  13. Market calibration (shadow mode)                        │
│                                                               │
│  Output: PredictionResult (dataclass with .to_dict())        │
└──────────────────────────────────────────────────────────────┘
```

### 2.3 Backward Compatibility

`PredictionResult.to_dict()` produces a dict matching the snapshot.py format, so existing consumers (`save_prediction_snapshot()`, `render_markdown()`, etc.) can consume `PredictionResult` without changes.

### 2.4 Degraded Reasons Contract (from Ticket 4)

Every failure in an optional data source produces a `DegradedReason(source, reason, severity, detail)` that is accumulated and returned in the result. No silent degradation.

---

## 3. Migration Roadmap

### 3.1 Ticket 8 (this ticket): Foundation

- [x] Write this design doc
- [ ] Add `from_artifacts()` and `from_snapshot_env()` factory methods to `PredictionPipeline`
- [ ] Create `@deprecated` utility decorator
- [ ] Mark 4 core old entry points as deprecated

### 3.2 Ticket 8a: CLI Migration

Migrate one script at a time, run regression tests after each:

| Script | Migration | Risk |
|--------|-----------|------|
| `predict_match.py` | Replace `run_artifact_pipeline()` with `PredictionPipeline.from_artifacts()` | Low |
| `snapshot.py` | Replace inline pipeline with `PredictionPipeline.from_snapshot_env()` | Medium |
| `fast_predict.py` | Replace inline pipeline with `PredictionPipeline.from_snapshot_env()` | Low |
| `pregenerate_wc26.py` | Already calls `snapshot.run_snapshot()` — migrate to `PredictionPipeline` directly | Medium |
| `batch_snapshot.py` | Same as pregenerate | Medium |
| `postmatch_review.py` | Switch to `PredictionPipeline.from_artifacts()` | Low |

### 3.3 Ticket 8b: Dashboard Migration

| Component | Migration |
|-----------|-----------|
| `02_Match_Prediction.py` | Replace `run_enhanced_prediction()` and `run_artifact_pipeline()` with `PredictionPipeline` |

### 3.4 Ticket 8c: API & Celery Migration

| Component | Migration |
|-----------|-----------|
| `admin.py` trigger endpoint | Redirect to `PredictionPipeline` |
| `predictions.py` endpoints | Redirect to `PredictionPipeline` |
| `tasks.py` Celery tasks | Redirect to `PredictionPipeline` |
| `prediction_orchestrator.py` | Eventually replace with `PredictionPipeline` |

### 3.5 Deprecation Timeline

| Version | Action |
|---------|--------|
| V3.1 (current) | `@deprecated` warnings added, old entry points still work |
| V3.2 | Warnings upgraded to `FutureWarning` |
| V3.3 | Old entry points removed |

---

## 4. Alternatives Considered

### 4.1 Keep Three Universes, Just Document

**Rejected.** Documentation alone won't prevent new code from calling the wrong universe. The duplication cost (15+ call sites, 6 result formats) grows with every new feature.

### 4.2 Rewrite from Scratch

**Rejected.** `PredictionPipeline` already exists and is well-designed. Rewriting would discard working code and introduce regressions.

### 4.3 Force Immediate Migration of All Callers

**Rejected.** Too risky. The plan's hard rule #3 says "不跨 phase". Incremental migration with deprecation windows is safer.

---

## 5. Migration Guide for Callers

### Before (Artifact universe)

```python
from app.services.prediction_core import run_artifact_pipeline

result, quality, timer = run_artifact_pipeline(
    home_team="France", away_team="Brazil",
    competition="FIFA World Cup 2026",
    is_neutral=True, mode="full",
)
print(result["home_win_prob"])  # dict access
```

### After

```python
from app.services.prediction_pipeline import PredictionPipeline

pipeline = PredictionPipeline.from_artifacts(mode="full")
result = await pipeline.predict_match(
    home_team="France", away_team="Brazil",
    competition="FIFA World Cup 2026",
    is_neutral=True,
)
print(result.home_win_prob)  # attribute access
# or: print(result.to_dict()["prediction"]["home_win_prob"])
```

### Before (Fit universe — snapshot.py)

```python
from scripts.snapshot import run_snapshot

result = await run_snapshot(
    home_team="France", away_team="Brazil",
    is_neutral=True, competition="FIFA World Cup 2026",
)
print(result["meta"]["home_team"])
```

### After

```python
from app.services.prediction_pipeline import PredictionPipeline

pipeline = await PredictionPipeline.from_snapshot_env()
result = await pipeline.predict_match(
    home_team="France", away_team="Brazil",
    competition="FIFA World Cup 2026",
    is_neutral=True,
)
print(result.to_dict()["meta"]["home_team"])
```

---

## 6. Verification

After each migration ticket (8a/8b/8c):

1. `pytest backend/tests/ -x -q` — all tests pass
2. Run the migrated script with real data — output matches previous version
3. Check `degraded_reasons` are preserved in `PredictionResult`
4. Verify no silent exceptions were introduced

---

## 7. References

- `backend/app/services/prediction_pipeline.py` — Unified entry point (existing, needs factory methods)
- `backend/app/services/prediction_result.py` — Standardized output dataclass
- `backend/app/services/prediction_core.py` — Artifact universe (to be deprecated)
- `backend/app/services/prediction_enhanced.py` — Enhanced wrapper (to be deprecated)
- `backend/scripts/snapshot.py` — Fit universe (to be deprecated)
- `backend/scripts/fast_predict.py` — Minimal fit (to be deprecated)
- `docs/CURRENT_STATUS.md` — System overview
