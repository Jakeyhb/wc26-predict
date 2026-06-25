# Post-Match Review Report

> Auto-generated from memory review. System version: V4.1.x

---

## Brazil vs Haiti — Post-Match Review (2026-06-20)

**Result:** Brazil 3-0 Haiti (HT 3-0). Prediction: correct direction ✅, Brier 0.2159.

### Component Performance
- **DC (🥇 best)**: 63.1%/21.3%/15.6%, Brier 0.2057, marginal +0.193 (largest positive contribution). Most balanced component.
- **Elo (🥈 2nd)**: 65.3%/10.6%/24.1%, Brier 0.1898 (lowest), marginal +0.100.
- **Enhancer (🥉 worst)**: 57.1%/11.6%/31.3%, Brier 0.2957, marginal +0.116. **Continues systematic over-rating of underdogs** — Haiti 31.3% win probability vs actual 0.28 xG.
- **Market**: 87.1%/8.7%/4.2% (extreme but correct direction). Model-market divergence 38pp triggered dynamic boost correctly.

### xG Error
- Predicted: Brazil 2.03 - Haiti 0.94 | Actual: Brazil 1.43 - Haiti 0.28
- Both overestimated significantly. Brazil "early kill" effect (3 goals in 45 min → coasted in 2H).
- WC xG calibration factor 1.35 may be too high.

### Critical Self-Evolution Actions
1. **Rejected degenerate weight optimization** — unconstrained Nelder-Mead gave DC=0%, Enhancer=95%. Reverted to WORLD_CUP_V3.9.5 defaults (DC=0.55, Enhancer=0.45). Fixed optimize_weights.py with L-BFGS-B + min bounds + fallback.
2. **Enhancer systematic bias confirmed** — see [[enhancer-overrate-underdog-bias]].
3. **DC remains most reliable component** — V3.9.5 reduction from 0.75→0.55 may be too aggressive.

**Why:** Post-match analysis of Brazil-Haiti revealed Enhancer continues to overrate weak teams, and the weight optimization script was producing degenerate solutions.
**How to apply:** When running optimize_weights.py, use bounded optimization (L-BFGS-B with min 0.03 per component). For WC predictions, consider applying additional Enhancer attenuation factor (0.85-0.90) on neutral venue matches. Review WC xG calibration factor (current 1.35 → suggest 1.15-1.25).