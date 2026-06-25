# Post-Match Review Report

> Auto-generated from memory review. System version: V4.1.x

---

Norway 3-2 Senegal (June 22/23, 2026, Group I MD2). Haaland brace (48', 58'), Sarr double (53', 90+3'). Norway advanced to Round of 32. xG: Norway 2.10 - Senegal 1.70. Norway only 42% possession but 7 shots on target vs 4, 5 big chances vs 4.

**THIS IS THE MOST IMPORTANT WC MATCH FOR SYSTEM EVOLUTION. First non-blowout, competitive fixture.**

**Key findings:**

1. **Pi was the SINGLE BEST model** (Brier 0.291, Norway 56.1%). While DC, Enhancer, Elo, and the fusion chain all pointed to Senegal, Pi alone correctly identified Norway as the favorite. Pi Rating 1.55 vs 1.08 (+0.47) captured Norway's attacking efficiency that Elo (based on historical results) missed.

2. **7/11 layers got direction WRONG**: pre-market, post-market, and final all favored Senegal. Only DC, Pi, Market, and Calibrated were direction-correct. This is the first WC match where the system's consensus was wrong.

3. **Elo got its FIRST direction wrong**: Senegal 1765 vs Norway 1643 (+121 Elo advantage). Elo based this on Senegal's stronger historical record (AFCON champion, more WC appearances). But Elo cannot see that Haaland in peak form makes Norway the current stronger team.

4. **Enhancer 5/5 wrong in WC** (Brier 1.37 this match — worst single-match Brier ever). Gave Senegal 71%. Now statistically proven: Enhancer is noise in WC group stage.

5. **Calibration SAVED the prediction**: Post-market (V3.9.6) favored Senegal 43.1%. Isotonic calibration flipped it to Norway 49.5%. Without calibration, this would have been the system's first complete prediction failure.

6. **DC stays direction-correct (5/5 WC)**: Norway 40.7% vs Senegal 33.4%. DC's Poisson framework correctly identified Norway's attacking edge.

7. **Market stays direction-correct (5/5 WC)**: 44% Norway vs 28.5% Senegal. But moderate Brier (0.47) — market wasn't as confident as in blowout matches.

8. **DC xG underestimated both teams for the first time**: Norway 1.34→2.10 (1.6x), Senegal 1.19→1.70 (1.4x). Previous 4 matches only had strong-team xG underestimation. High-scoring match (5 total goals) exceeded Poisson expectations.

**5-match WC panel (updated):**
- Market: 5/5 dir correct, avg Brier 0.162 ⭐
- DC: 5/5 dir correct, avg Brier 0.492
- Elo: 4/5 dir correct, avg Brier 0.304
- Pi: 3/5 dir correct, avg Brier 0.318
- Enhancer: 1/5 dir correct, avg Brier 0.890 🔴

**Four-quadrant insight:**
- Blowout matches (4/4): Market + Elo best, Enhancer worst
- Competitive match (1/1): Pi best, Elo + Enhancer worst
- Pi appears uniquely valuable in evenly-matched fixtures

**Weight adjustment recommendation:**
- Pi: 5%→8% (this match proved Pi's unique value in competitive fixtures)
- DC: 65%→63% (slight trim to accommodate Pi increase)
- All other V3.9.7 weights unchanged

**Why:** Elo's limitation — it's a historical-strength metric that cannot capture current tournament form. Senegal's 1765 Elo reflects past achievements, not the team that conceded 3 goals to France in MD1. Pi's multi-dimensional rating appears to weight current form more heavily, which is critical in competitive "current-form matters" fixtures.

**How to apply:** Apply Pi 5%→8% adjustment. The remaining WC group match (Jordan-Algeria) is another competitive fixture — Pi direction should be reliable there. Wait for more competitive knockout matches to decide permanent Pi weight.