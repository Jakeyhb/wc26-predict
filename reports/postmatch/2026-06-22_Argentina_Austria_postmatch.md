# Post-Match Review Report

> Auto-generated from memory review. System version: V4.1.x

---

Argentia 2-0 Austria (June 22, 2026, Group J MD2). Messi brace (38', 90+5') after missing 9' penalty. Became all-time WC top scorer (18 goals).

**Key findings:**

1. **Market was the HERO**: 66% Argentina implied was closest to reality (Brier 0.18). Without Market, the model would have been WRONG (pre-market favored Austria 39.0%). Dynamic market boost 0.28→0.40 was critical and validated.

2. **Enhancer 3/3 WRONG in WC group stage**: Brazil-Haiti (favored Haiti 42.9%), Spain-Saudi (favored Saudi 53.3%), Argentina-Austria (favored Austria 56.5%). Enhancer systematically overrates underdogs. Average Brier 0.92 vs uniform baseline 0.67. For WC, Enhancer should be drastically reduced: 30%→10%.

3. **Elo is consistently UNDERRATED**: 3/3 direction correct, average Brier 0.24 (best among model components). Only gets 8% weight. Should be 12%+.

4. **DC xG 2.5x underestimated Argentina**: Predicted xG 1.05 vs actual 2.63. Messi alone had 1.81 xG. DC's club-level data can't capture superstar tournament mode. WC xG calibration factor should go back to 1.35 from 1.20.

5. **Pi is a solid weak signal**: 2/3 direction correct, Brier 0.34. Low weight (2%) is fine but could go to 5%.

6. **Calibration works**: Calibrated Brier (0.36) improved over post-market (0.42).

**Weight evolution recommendations for V3.9.7 (WC-specific):**
- DC: 0.70→0.65 (direction ok but magnitude poor)
- Enhancer: 0.30→0.10 (proven toxic for WC group stage)
- Elo: 0.08→0.12 (most efficient signal, underutilized)
- Pi: 0.02→0.05 (weak but useful complement)
- Market default: 0.28→0.30
- Market dynamic max: 0.40→0.50 (trust market more when divergence >25pp)
- WC xG factor: 1.20→1.35

**Global optimizer WARNING**: 61-match Nelder-Mead returns Enhancer 86% because it dominates in friendlies. Competition-segmented optimization needed.

**Why:** Enhancer's 30+ features (recent form, squad depth, etc.) capture noise not signal in lopsided WC group matches where individual superstars (Messi, Haaland) decide the game. DC's Poisson framework is agnostic to player identity. Market implicitly prices in superstar effects.

**How to apply:** Apply WC-specific weights for remaining group stage matches. Watch for Norway-Senegal and Jordan-Algeria results to confirm or revise.