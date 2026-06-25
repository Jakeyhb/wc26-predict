# Post-Match Review Report

> Auto-generated from memory review. System version: V4.1.x

---

## Spain vs Saudi Arabia — Post-Match Review (2026-06-22)

**Result:** Spain 4-0 Saudi Arabia (HT 3-0). Prediction: direction correct ✅.

### V3.9.6 Prediction (post-match retro)
- DC: Spain 75.3% / Draw 17.2% / Saudi 7.5% — Brier 0.0964 (best component)
- Enhancer: Spain 32.0% / Draw 30.5% / Saudi 37.5% — Brier 0.6952 (WORST — favored Saudi!)
- Elo: Spain 73.7% / Draw 9.4% / Saudi 17.0% — Brier 0.1070
- Pi: Spain 77.4% / Draw 14.7% / Saudi 7.9% — Brier 0.0788
- Market: Spain 87.7% / Draw 8.3% / Saudi 3.7% — Brier 0.0234 (would have been best)
- **Final (no market)**: Spain 57.7% — Brier 0.2691 → severe underconfidence
- **Final (with market 40%)**: Spain 65.5% — Brier 0.179 → much better
- xG: DC 2.01-0.47 → actual 1.87-0.04 (DC overestimated Saudi xG by 12x)

### Market data was critical
- Market implied Spain 87.7% — the true picture of the mismatch
- Without market: model was only 57.7% Spain (criminally conservative)
- DC-Enhancer 43.2pp divergence triggered DC weight penalty 0.70→0.55, which HURT
- **Divergence-adaptive DC weight reduction is harmful when DC is right and Enhancer is wrong**

### Component Performance
- **DC**: 75.3% Spain, 3 non-Enhancer layers all favored Spain → clear consensus
- **Enhancer**: 37.5% Saudi (reverse prediction). Overrated Saudi due to Uruguay draw
- **Elo/Pi**: Both correctly pointed to Spain, confirm DC direction
- **xG calibration 1.20**: Still overestimated Saudi xG (0.47 vs actual 0.04) but better than old 1.35

### Self-Evolution Actions
1. ✅ Generated V3.9.6 prediction snapshot (was missing)
2. ✅ Ran learning engine with marginal contributions (was manual)
3. ✅ Linked learning log to snapshot (was NULL)
4. ✅ Attempted weight optimization → degenerate (DC 3%, Enhancer 86%) → REVERTED
5. 🔴 Divergence-adaptive DC penalty should be re-evaluated: when 3/4 layers agree with DC, penalty should be on Enhancer, not DC
6. 🔴 Market data must always be fetched — without it, prediction quality collapses
7. 🔴 Run `predict_match_full.py` BEFORE matches (the prediction JSON was missing entirely)

### 19-match WC aggregate (adding Spain-Saudi)
- DC continues as most reliable component
- Enhancer now 13/19 negative marginal (68% harmful)
- Market is the most accurate layer when available
- Elo and Pi are consistent positive contributors

**Why:** Post-match analysis revealed pre-match prediction was done with V3.9.5, no DB snapshot, and prediction JSON was missing. Enhancer's systematic anti-favorite bias confirmed again. Divergence-adaptive logic penalized the WRONG component.

**How to apply:** 
1. Always generate predictions via `predict_match_full.py` before matches
2. When DC+Elo+Pi all agree and Enhancer diverges, penalty should apply to Enhancer, not DC
3. Market data is non-negotiable for WC-level predictions
4. Re-evaluate divergence logic: `if DC_dir == Elo_dir == Pi_dir and Enhancer opposes → reduce enhancer_weight, NOT dc_weight`
5. See [[brazil-haiti-postmatch-20260620]] for related Enhancer issues
6. See [[enhancer-overrate-underdog-bias]] for systemic pattern