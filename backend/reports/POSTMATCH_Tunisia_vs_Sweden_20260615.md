# Post-Match Review: Tunisia vs Sweden — Group F, Matchday 1

**Date:** June 15, 2026 | **Kickoff:** 02:00 UTC (10:00 CST)  
**Venue:** Estadio BBVA, Monterrey, MX (capacity ~53,500)  
**Competition:** FIFA World Cup 2026, Group F — Matchday 1  
**Result:** Tunisia 1–5 Sweden (HT: 1–2)  
**Review version:** V3.8.0 post-match retro

---

## 1. Match Summary

| Detail | Value |
|--------|-------|
| Score | Tunisia 1 – 5 Sweden |
| Half-time | 1 – 2 |
| xG (Opta/SofaScore) | Tunisia 0.28 – Sweden 1.36 |
| Possession | Tunisia 51% – Sweden 49% |
| Shots | Tunisia 6 (2 on target) – Sweden 13 (7 on target) |
| Big Chances | Tunisia 0 – Sweden 4 |
| Referee | Yael Falcon Perez (Argentina) |

### Goals

| Time | Scorer | Assist | Team |
|------|--------|--------|------|
| 7' | Yasin Ayari | Gyokeres | Sweden |
| 30' | Alexander Isak | Bergvall | Sweden |
| 43' | Omar Rekik | Hannibal Mejbri | Tunisia |
| 59' | Viktor Gyokeres | Isak | Sweden |
| 84' | Mattias Svanberg | Isak | Sweden |
| 90+6' | Yasin Ayari | Bergvall | Sweden |

### Notable
- **xG anti-record**: First-half combined xG of 0.47 is the lowest in any World Cup half with 3+ goals since 1966 (OptaJoe)
- Sweden scored 5 goals from only 1.36 xG — overperformance of +3.64
- Yasin Ayari (Brighton) scored a brace from midfield
- Alexander Isak (Liverpool): 1 goal + 2 assists, SofaScore 8.8 MOTM

---

## 2. Prediction vs Actual

### V3.8.0 Retrospective Prediction (disk cache, single source of truth)

| Model Layer | Home (TUN) | Draw | Away (SWE) | Brier |
|-------------|:----------:|:----:|:----------:|:-----:|
| **DC** | 53.58% | 27.68% | 18.75% | 0.3413 |
| **Enhancer** | 25.44% | 23.06% | **51.49%** | **0.1177** |
| **Elo** | 52.88% | 11.76% | 35.36% | 0.2371 |
| **Pi** | 44.33% | 20.56% | 35.11% | 0.2200 |
| DC+Enh | 45.14% | 26.29% | 28.57% | 0.2610 |
| DC+Enh+Elo | 45.91% | 24.84% | 29.25% | 0.2577 |
| **Final (DC+Enh+Elo+Pi)** | **45.75%** | **24.41%** | **29.83%** | **0.2538** |

**Actual outcome:** Away win (Sweden). System favored Tunisia (45.8%).

### V3.6.1 (June 14) vs V3.8.0 Comparison

| Version | TUN Win | Draw | SWE Win | Brier |
|---------|:-------:|:----:|:-------:|:-----:|
| V3.6.1 (AUTO_OPTIMIZED) | 42.02% | 24.66% | 33.32% | 0.2418 |
| V3.8.0 (DC=0.70) | 45.75% | 24.41% | 29.83% | 0.2538 |

**V3.8.0 regressed on this match.** The higher DC weight (0.55 → 0.70) amplified DC's wrong-direction bias toward Tunisia. V3.6.1's lower DC weight allowed Enhancer's Sweden-favoring signal to contribute more (45% effective vs 30%).

---

## 3. Model Layer Performance

### Best: Enhancer (Brier 0.1177)
- **Only model to correctly identify Sweden as favorite** (51.49% away win)
- Gave Sweden >50% despite DC giving Sweden only 18.75%
- Continues the pattern from NED-JPN where Enhancer was also the best single layer

### Worst: DC (Brier 0.3413)
- Heavily favored Tunisia (53.58%), completely wrong direction
- xG estimate: Tunisia 1.67 – Sweden 0.92 (actual: 0.28 – 1.36)
- Both xG and win probability were inverted

### Mixed: Elo (Brier 0.2371)
- Gap: Tunisia 1676 – Sweden 1606 = +70 favoring Tunisia
- Elo correctly identified the gap but overestimated its predictive power
- Draw probability absurdly low at 11.76% (classic Elo problem)

### Solid: Pi (Brier 0.2200)
- More balanced than DC or Elo
- Gave Sweden 35.1% — closer to reality than DC

---

## 4. Leave-One-Out Analysis

| Remove | Brier Change | Impact |
|--------|:-----------:|--------|
| -Enhancer | **+0.0875** | HURTS significantly |
| -Elo | -0.0166 | Helps slightly |
| -Pi | +0.0039 | Hurts marginally |
| -DC | **-0.1360** | **HELPS — DC made predictions worse** |

The LOO confirms what the Brier scores show: **DC was a net negative**, and **Enhancer was the only layer pulling in the right direction**.

---

## 5. Cross-Match Pattern (3 WC26 Group Matches)

| Match | Actual | DC Brier | Enh Brier | Best Layer | DC Marginal |
|-------|--------|:--------:|:---------:|------------|:-----------:|
| GER 7–1 CUW | Home win (expected) | **0.070** | 1.288 | DC | +0.418 |
| NED 2–2 JPN | Draw | 0.714 | 0.651 | DC | +0.254 |
| TUN 1–5 SWE | Away win | 0.341 | **0.118** | **Enhancer** | +0.088 |

**Pattern emerges:** DC is excellent on lopsided matchups (GER-CUW, Elo gap +202) but fails when the Elo gap is moderate or the Elo-favored team underperforms. Enhancer excels precisely in those moderate-gap matches.

---

## 6. Self-Evolution Actions

### 6.1 Learning Log Entry

| Field | Value |
|-------|-------|
| Error magnitude | 0.7017 |
| Error direction | `underestimate_away` |
| DC marginal | +0.0875 (wrong direction) |
| Enhancer marginal | -0.1360 (right direction, net positive) |
| Elo marginal | -0.0166 (slight help) |
| Model was right? | **No** — favored Tunisia |

### 6.2 Weight Gate Assessment

The current V3.8.0 weights (DC=0.70, Enhancer=0.20) were set based on 2-match audit (GER-CUW + NED-JPN). With the third match now showing DC negative and Enhancer positive, the 3-match cumulative evidence:

| Model | GER-CUW | NED-JPN | TUN-SWE | Cumulative |
|-------|:-------:|:-------:|:-------:|:----------:|
| DC | **Positive** | Negative | **Negative** | 1/3 positive |
| Enhancer | Negative | Negative | **Positive** | 1/3 positive |

**Recommendation:** No weight change at this time. DC is 1/3 and Enhancer is 1/3 across three very different match profiles. The current weights represent a reasonable balance. Wait for more data (target: 5+ matches) before further adjustment.

### 6.3 Parameter Provenance

| Field | Value |
|-------|-------|
| DC hash | `b244c28a0df8` |
| DC teams | 296 |
| Training rows | 10,999 |
| Training max date | 2026-06-03 |
| Weight label | `WORLD_CUP_V3.8` |

---

## 7. Data Fixes Applied

| Table | Field | Old Value | New Value |
|-------|-------|-----------|-----------|
| `match_results` | (new) | — | TUN 1–5 SWE, xG 0.28–1.36 |
| `matches` | venue | NRG Stadium | Estadio BBVA, Monterrey, MX |
| `wc26_schedule` | venue | Estadio Azteca | Estadio BBVA |
| `wc26_schedule` | city | Mexico City, MX | Monterrey, MX |
| `wc26_schedule` | home_goals | NULL | 1 |
| `wc26_schedule` | away_goals | NULL | 5 |
| `wc26_schedule` | match_status | SCHEDULED | FINISHED |

---

## 8. Group F Standings After Matchday 1

| # | Team | P | W | D | L | GF | GA | GD | Pts |
|---|------|---|---|---|---|----|----|-----|------|
| 1 | **Sweden** | 1 | 1 | 0 | 0 | 5 | 1 | +4 | 3 |
| 2 | Netherlands | 1 | 0 | 1 | 0 | 2 | 2 | 0 | 1 |
| 3 | Japan | 1 | 0 | 1 | 0 | 2 | 2 | 0 | 1 |
| 4 | Tunisia | 1 | 0 | 0 | 1 | 1 | 5 | -4 | 0 |

### Remaining Group F Fixtures

| Date | Match | Venue |
|------|-------|-------|
| June 20 | Netherlands vs Sweden | Levi's Stadium, Santa Clara |
| June 21 | Tunisia vs Japan | Gillette Stadium, Foxborough |
| June 25 | Tunisia vs Netherlands | Lumen Field, Seattle |
| June 25 | Japan vs Sweden | Hard Rock Stadium, Miami |

---

## 9. Key Takeaways

1. **Enhancer is the anti-DC**: When DC leans heavily on Elo-favored teams, Enhancer provides the necessary counterweight. This match is the clearest demonstration yet.
2. **DC weight of 0.70 may be too high**: On 2 of 3 matches, DC's marginal contribution was negative. The GER-CUW match (DC Brier 0.070) is an outlier, not the norm.
3. **Elo draw suppression is real**: Elo gave 11.76% draw probability — lower than any other model. This is a known weakness of Elo-based prediction.
4. **xG anti-record highlights model blind spot**: No model predicted 5 goals from 1.36 xG. Clinical finishing is inherently unpredictable.
5. **Venue data needs audit**: Two matches in a row had wrong venues in the database (NED-JPN: AT&T not Akron; TUN-SWE: BBVA not NRG).

---

*Generated by Hermes V3.8.0 post-match review pipeline, June 16, 2026*
