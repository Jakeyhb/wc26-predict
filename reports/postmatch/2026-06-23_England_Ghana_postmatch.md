# Post-Match Review Report

> Auto-generated from memory review. System version: V4.1.x

---

# England vs Ghana — Post-Match Review (June 24, 2026)

## Match Result
- **Score**: England 0-0 Ghana (Gillette Stadium, Foxborough, June 23)
- **xG**: England 1.28 — Ghana 0.29
- **Possession**: 79% — 21% (highest possession by a team failing to score in WC in 60 years)
- **Shots/SOT**: 19/3 — 2/1
- **Key moment**: Harry Kane missed 0.33 xG chance (86'), Nico O'Reilly hit crossbar
- **Tactical**: Ghana 4-5-1 low block, 39 clearances, Queiroz masterclass

## Prediction vs Actual
- **Predicted final**: England 66.9% / Draw 22.5% / Ghana 10.6%
- **Direction**: WRONG (predicted England, actual draw) — Grade **B** (top-3 score: 0-0 was #3 at 8.2%)
- **Brier**: 1.059 — severe miss, worst in WC set
- **Log Loss**: 1.491
- **RPS**: 0.229
- **O/U 2.5**: WRONG (predicted Over 54.8%, actual 0 goals)

## ALL COMPONENTS WRONG — First Time

| Component | Brier | Direction | Notes |
|-----------|-------|-----------|-------|
| **DC** | 1.035 | WRONG | Favored England 64.5%, highest draw at 22.4% |
| **Enhancer** | 0.922 | WRONG | Favored Ghana 42.3% — IRONICALLY best pre-market Brier |
| **Elo** | 1.294 | WRONG | Favored England 66.3%, only 10.5% draw |
| **Pi** | 1.109 | WRONG | Favored England 64.4% |
| **Market** | 1.410 | WRONG | Favored England 80.2% — WORST of all (extreme confidence) |
| **Calibrated** | 1.059 | WRONG | Calibration couldn't save this |

## Structural Crisis: Draw Underestimation

This match exposes a FUNDAMENTAL weakness:
- **No component gave draw > 22.5%** — not DC, not Enhancer, not calibration
- **Market was the worst** (Brier 1.41) — extreme favorite confidence = extreme penalty
- **Divergence protection backfired**: DC-Enhancer divergence triggered adaptive shift (dc 0.49), which HELPED (lowered England confidence), BUT the market boost (0.30→0.42, 35.2% divergence) made things WORSE because market was also wrong
- **WC draw rate**: 1/7 = 14.3% (vs historical ~25%)
- **Pi 2.68x advantage** completely misleading when team can't finish

## Enhancer Irony
- 0/6 WC direction correct — but this match had Enhancer as "least bad" (Brier 0.922 vs DC 1.035)
- Reason: Enhancer's systematic underdog bias (favored Ghana 42.3%) accidentally produced lower confidence in England than any other component
- This does NOT vindicate Enhancer — it was still wrong — but it shows high confidence on favorites is risky

## Self-Evolution: V4.0.5 Proposal (NO WEIGHT CHANGES)

**Why**: Failure mode is structural (draw underestimation), not weight-imbalance. Architecture changes needed:

1. **Draw probability floor (15%)**: Prevent calibration from pushing draws to 10.6% (as here) or 11.3% (Portugal-UZ)
2. **Refine divergence penalty**: When DC-Enhancer AND market-model divergence both fire same direction, reduce (not increase) market boost — prevents double-counting favorite bias
3. **ElO/Pi updated**: England 1743→1732 (-11), Ghana 1560→1571 (+11)

## System Audit Findings

**Global post-match audit revealed:**
- 2/7 WC matches with known results have DB evaluations (Portugal-UZ, England-GH) — 5 earlier matches only have JSON/reports
- Calibrator stale: 30 pre-WC samples, ECE=0.128, no WC data → rebuild when ≥3 WC samples
- All 14/14 Enhancer WC predictions favor away team — 100% systematic bias
- postmatch_eval table has 53 entries but all from earlier eras — only our 2 new entries cover 2026 WC
- model_weight_config auto_optimized keys contain RPS-optimized values (dc=0.026!) that are overridden by code — potential DB-code inconsistency

**Why**: Earlier post-match reviews ran in "JSON-only" mode without writing structured DB evaluations. Fixed for Portugal-UZ and England-GH.

**How to apply**: 
- No weight changes this round (structural issue, not weight issue)
- Add draw probability floor in calibration code
- Refine divergence penalty logic
- Plan calibrator rebuild at ≥3 WC samples accumulated

## Files Modified
- `backend/data/local_stage2.db` — match result, xG, snapshot, learning log, eval
- `backend/app/services/weights.py` — V4.0.4 unchanged (no weight changes justified)

[[enhancer-wc-systematic-failure]] [[draw-underestimation-crisis]] [[market-anchor-broken]] [[postmatch-db-integrity-gap]]