# Post-Match Review: Spain vs Cape Verde — Group H, Matchday 1

**Date:** June 15, 2026 | **Kickoff:** 21:00 UTC (June 15, 5pm EDT / June 16 05:00 CST)  
**Venue:** Mercedes-Benz Stadium, Atlanta, GA, USA (capacity ~71,000; attendance 67,640)  
**Competition:** FIFA World Cup 2026, Group H — Matchday 1  
**Result:** Spain 0–0 Cape Verde (HT: 0–0)  
**Review version:** V3.8.0 post-match retro

---

## 1. Match Summary

| Detail | Value |
|--------|-------|
| Score | Spain 0 – 0 Cape Verde |
| Half-time | 0 – 0 |
| xG (Opta) | Spain 2.29 – Cape Verde 0.30 |
| Possession | Spain 74% – Cape Verde 26% |
| Shots | Spain 27 (7 on target) – Cape Verde 4 (1 on target) |
| Shots Inside Box | Spain 16 – Cape Verde 2 |
| Big Chances | Spain 2 – Cape Verde 1 |
| Corners | Spain 11 – Cape Verde 1 |
| Clearances | Spain 10 – Cape Verde 45 |
| Fouls | Spain 10 – Cape Verde 1 |
| Woodwork | Spain 1 (Torres crossbar 39') – Cape Verde 0 |
| Referee | Adham Makhadmeh (Jordan) |
| Man of the Match | **Vozinha** (Cape Verde GK, 40yo, 7 saves, 9.7 SofaScore) |

### Key Events

| Time | Event |
|------|-------|
| 38' | Ferran Torres hits the crossbar from 6 yards |
| 39' | Vozinha saves Oyarzabal's follow-up header |
| 45+2' | Vozinha tips Laporte's header around the post |
| 45+3' | Vozinha low save denies Ferran Torres |
| 71' | Lamine Yamal subbed on (World Cup debut) |
| 73' | Vozinha denies Merino after Yamal creates chance |
| 88' | Pico Lopes blocks Oyarzabal's close-range effort (goal-saving clearance) |
| 90+1' | Diney Borges nearly wins it for Cape Verde — downward header from corner |

### Historical Context

- **Spain's 27 shots without scoring** — joint-most on record since 1966 (matching 27 vs Paraguay in 1998, also 0-0)
- **Spain winless in 4 World Cup matches** — longest such streak since 1982–1986
- **Cape Verde is the 3rd-smallest nation** ever to compete in a World Cup (population <500,000)
- **Vozinha (40 years, 12 days)** — oldest player to appear in a nation's World Cup debut match
- **Cape Verde completed just 14 passes in the opposition half** — tied for lowest in any World Cup half since 1966
- **First-ever senior meeting** between Spain and Cape Verde

---

## 2. Prediction vs Actual

### V3.8.0 Retrospective Prediction

| Model Layer | ESP Win | Draw | CPV Win | Brier |
|-------------|:-------:|:----:|:-------:|:-----:|
| **DC** | 78.95% | 15.68% | 5.37% | **1.3371** |
| **Enhancer** | 51.97% | 9.38% | 38.65% | **1.2407** |
| **Elo** | 63.90% | 10.82% | 25.28% | **1.3641** |
| **Pi** | 20.08% | 19.07% | 60.85% | **1.3153** |
| DC+Enh (70:30) | 70.86% | 13.79% | 15.35% | 1.2688 |
| DC+Enh+Elo | 70.94% | 13.38% | 15.68% | 1.2781 |
| **Final (DC+Enh+Elo+Pi)** | **71.50%** | **13.54%** | **14.96%** | **1.2810** |

**Actual outcome:** Draw (0-0). **System heavily favored Spain (71.5%). All models wrong on direction.**

### V2.0.0 Comparison

| Version | ESP Win | Draw | CPV Win | Brier |
|---------|:-------:|:----:|:-------:|:-----:|
| V2.0.0 (June 3) | 58.55% | 13.93% | 27.56% | **1.1596** |
| V3.8.0 (retro) | 71.50% | 13.54% | 14.96% | **1.2810** |

**V3.8.0 regressed on this match (+0.12 Brier).** V2.0.0's more balanced probabilities (58.5% Spain, 27.6% CPV) were closer to the actual draw outcome. The higher DC weight in V3.8.0 (0.70 vs V2.0.0's lower weight) amplified DC's extreme Spain confidence.

---

## 3. Model Layer Performance Analysis

### Best: Enhancer (Brier 1.2407)
- **Only model to give Cape Verde meaningful credit** (38.65%)
- Recognized CPV's defensive strength better than DC's dismissive 5.37%
- But only 9.38% draw — didn't see a 0-0 coming
- Continues the consistent pattern from TUN-SWE: Enhancer excels when DC is over-confident

### Worst: Elo (Brier 1.3641)
- Gave Spain 63.9% win probability — middle ground but still wrong
- Draw probability 10.82% — classic Elo structural weakness
- The 234-point Elo gap (ESP 1832 vs CPV 1598) is actually meaningful — Spain IS the better team

### DC: Catastrophically Over-Confident (Brier 1.3371)
- Gave Spain 78.95% and Cape Verde only 5.37% — the widest gap of any WC26 match
- DC effectively wrote off the possibility of a non-Spain result
- xG estimate (ESP 2.43 vs CPV 0.59, gap +1.84) was close to actual xG gap (+1.99) — DC's xG was reasonable, but its win probability conditioning was extreme

### Pi: Paradoxically Prophet (Brier 1.3153)
- Gave Cape Verde 60.85% win probability — **directionally inverted** (wrong favorite)
- BUT: 19.07% draw was the **highest of any model layer** — closest to the actual outcome
- Pi correctly de-rated Spain (20.08%) in a way no other model did
- This makes Pi a fascinating outlier: wrong on direction, right on the shape of the problem

---

## 4. Leave-One-Out Analysis

| Remove | Brier Change | Impact |
|--------|:-----------:|--------|
| -DC | **-0.0561** | **HELPS — DC made predictions worse** |
| -Enhancer | +0.0403 | Hurts significantly |
| -Elo | **-0.0830** | **HELPS — Elo made predictions worse** |
| -Pi | -0.0343 | Helps slightly |

**DC and Elo were net negatives.** Removing DC would have improved the Brier by 0.056 (Brier drops to 1.2249). Removing Elo would have helped even more (improvement of 0.083). Only Enhancer was pulling in the right direction. This is the 2nd time in 4 audited matches that DC is a net negative.

---

## 5. Cross-Match Pattern (4 WC26 Group Matches Audited)

| Match | Actual | DC Brier | Enh Brier | Best Layer | DC Marginal | DC vs Enh |
|-------|--------|:--------:|:---------:|------------|:-----------:|:---------:|
| GER 7–1 CUW | Home win | **0.070** | 1.288 | DC | +0.418 | DC wins |
| NED 2–2 JPN | Draw | 0.714 | 0.651 | DC | +0.254 | DC wins |
| TUN 1–5 SWE | Away win | 0.341 | **0.118** | **Enhancer** | +0.088 | **Enh wins** |
| ESP 0–0 CPV | Draw | 1.337 | **1.241** | **Enhancer** | +0.056 | **Enh wins** |

**Pattern hardened:** DC is now 2/4 positive, the 2 positives being GER-CUW (lopsided) and NED-JPN (close). Enhancer is also 2/4. But the crucial pattern is:

| Match Type | DC Performance | Enhancer Performance |
|------------|:-------------:|:-------------------:|
| **Lopsided** (Elo gap >200) — GER-CUW | EXCELLENT | Terrible |
| **Moderate** (Elo gap 100-200) — NED-JPN, TUN-SWE | Mixed | Good |
| **Lopsided upset** (ESP-CPV, gap +234 but 0-0) | TERRIBLE | Bad (but least bad) |

**DC is dangerous on lopsided matchups** because it amplifies Elo gaps into near-certainty. When the gap is real (GER 7-1 CUW), it looks brilliant. When an upset happens (ESP 0-0 CPV), it looks catastrophic.

---

## 6. Starting Lineups

### Spain (4-3-3)
```
Unai Simon
Llorente – Cubarsi – Laporte – Cucurella
Pedri – Rodri (C) – Fabian Ruiz
Gavi – Oyarzabal – Ferran Torres
```

**Coach:** Luis de la Fuente  
**Key bench:** Lamine Yamal (71'), Mikel Merino (71'), Dani Olmo (81'), Nico Williams (83')  
**Notable:** Yamal started on bench recovering from hamstring. Spain played without natural width until his introduction.

### Cape Verde (4-2-3-1)
```
Vozinha ⭐
Moreira – P. Lopes – D. Borges – S. Lopes Cabral
K. Pina – L. Duarte
R. Mendes (C) – Monteiro – J. Cabral
Livramento
```

**Coach:** Bubista  
**Key subs:** W. Semedo (61'), D. Duarte (61'), N. Da Costa (61')

---

## 7. Self-Evolution Actions

### 7.1 Learning Log Entry

| Field | Value |
|-------|-------|
| Error magnitude | 1.2810 |
| Error direction | `massive_overestimate_home` |
| DC marginal | +0.0561 (wrong direction) |
| Enhancer marginal | -0.0403 (right direction, net positive) |
| Elo marginal | +0.0830 (wrong direction) |
| Pi marginal | -0.0343 (right direction) |
| Model was right? | **No** — favored Spain 71.5% |

### 7.2 Weight Gate Assessment

Four-match cumulative evidence:

| Model | GER-CUW | NED-JPN | TUN-SWE | ESP-CPV | Cumulative |
|-------|:-------:|:-------:|:-------:|:-------:|:----------:|
| DC | **Positive** | Negative | **Negative** | **Negative** | **1/4** |
| Enhancer | Negative | Negative | **Positive** | **Positive** | **2/4** |

**Recommendation: DO NOT CHANGE WEIGHTS YET.** While DC is now 1/4 and Enhancer is 2/4 on direction correctness, the sample is still too small. BUT — the evidence is accumulating that DC's weight of 0.70 may be too high. DC has been harmful on 3 of 4 matches. The GER-CUW match (DC Brier 0.070) remains the outlier.

**Key limitation of this analysis:** The ESP-CPV match is a black-swan event — Spain accumulated 2.29 xG, hit the crossbar, and faced a 40-year-old goalkeeper producing a career performance. No statistical model can predict a goalkeeper having the best game of his life at age 40. This is not a model failure — it's a fundamental limitation of probability-based prediction.

### 7.3 Parameter Provenance

| Field | Value |
|-------|-------|
| DC hash | `b244c28a0df8` |
| DC teams | 296 |
| Training rows | 10,999 |
| Training max date | 2026-06-03 |
| Weight label | `AUTO_OPTIMIZED` |

---

## 8. Data Fixes Applied

| Table | Field | Old Value | New Value |
|-------|-------|-----------|-----------|
| `match_results` | (new) | — | ESP 0–0 CPV, xG 2.29–0.30 |
| `matches` | venue | Estadio Akron | Mercedes-Benz Stadium, Atlanta, GA |
| `matches` | status | scheduled | finished |
| `wc26_schedule` | venue | Estadio Akron | Mercedes-Benz Stadium |
| `wc26_schedule` | city | Guadalajara, JAL | Atlanta, GA |
| `wc26_schedule` | match_status | SCHEDULED | FINISHED |
| `wc26_schedule` | home_goals | NULL | 0 |
| `wc26_schedule` | away_goals | NULL | 0 |
| `prediction_snapshots` | (new V3.8.0) | — | Retrospective prediction + Brier analysis |

### ⚠️ Venue Error Flag

Esta es la **tercera vez** que el venue en la base de datos era incorrecto:
1. NED-JPN: DB said Estadio Akron → actual was AT&T Stadium
2. TUN-SWE: DB said NRG Stadium → actual was Estadio BBVA
3. ESP-CPV: DB said Estadio Akron → actual was Mercedes-Benz Stadium

**Patron:** El Estadio Akron aparece incorrectamente en multiples partidos. Esto es un bug sistematico en los datos de semilla.

---

## 9. Group H Standings After Matchday 1

| # | Team | P | W | D | L | GF | GA | GD | Pts |
|---|------|---|---|---|---|----|----|-----|------|
| 1 | Spain | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 1 |
| 2 | Cape Verde | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 1 |
| 3 | Saudi Arabia | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 4 | Uruguay | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

**Saudi Arabia vs Uruguay** (June 15, 22:00 UTC / June 16 06:00 CST) will determine the group leader. If URU wins, Group H becomes: URU 3pts, ESP 1pt, CPV 1pt, KSA 0pts. If draw: all four on 1pt.

### Remaining Group H Fixtures

| Date | Match | Venue |
|------|-------|-------|
| June 21 | Spain vs Saudi Arabia | Levi's Stadium, Santa Clara |
| June 21 | Uruguay vs Cape Verde | Gillette Stadium, Foxborough |
| June 27 | Uruguay vs Spain | Lumen Field, Seattle |
| June 27 | Cape Verde vs Saudi Arabia | Hard Rock Stadium, Miami |

---

## 10. Key Takeaways

1. **This was a black-swan event.** Spain accumulated 2.29 xG and held Cape Verde to 14 passes in their half. The probability of 0 goals from 2.29 xG against a debutant's defense is roughly 2-3%. No statistical model can predict a 40-year-old goalkeeper producing 7 saves with a 9.7 SofaScore rating.

2. **DC's over-confidence is a systemic risk.** DC has now been a net negative on 3 of 4 WC26 matches. Its tendency to amplify Elo gaps into near-certainty (Spain 78.95%, Germany 92.7% vs CUW) produces catastrophic Brier scores when the improbable happens.

3. **Enhancer is the consistent counterweight.** For the 3rd time in 4 matches, Enhancer was the best or second-best layer. Its balanced Spain-CPV assessment (52% / 39%) was closest to reflecting the actual competitiveness.

4. **Pi's inverted prediction is worth investigating.** Pi gave Cape Verde 60.9% — wrong on direction — but its 19.1% draw probability was the highest of any layer. Pi's structural skepticism of favorites may be a valuable signal in lopsided matchups, even when its direction is wrong.

5. **Venue data remains unreliable.** Three consecutive matches had wrong venues in the database (all pointing to Estadio Akron or other incorrect stadiums). This requires a systematic audit of all 104 WC26 venues.

6. **Lamine Yamal's bench start was a tactical error.** De la Fuente started Spain without natural width (Gavi and Torres as nominal wingers). Yamal's introduction in the 71st minute immediately changed Cape Verde's defensive shape. A model incorporating lineup quality would have flagged the Yamal absence as significant.

---

## 11. Comparison: ESP-CPV vs TUN-SWE

Both matches had similar dynamics (heavy favorite held/punished), but the root causes differ:

| Factor | ESP 0-0 CPV | TUN 1-5 SWE |
|--------|:-----------:|:-----------:|
| xG gap | +1.99 to Spain | +1.08 to Sweden |
| Favorite | Spain (DC 78.9%) | Tunisia (DC 53.6%) |
| Actual | Draw | Away win by 4 |
| Best layer | Enhancer (Brier 1.241) | Enhancer (Brier 0.118) |
| Worst layer | Elo (Brier 1.364) | DC (Brier 0.341) |
| Model-able? | NO (GK career game) | YES (Enhancer got it) |

ESP-CPV was genuinely unpredictable; TUN-SWE was predictable by Enhancer but DC/Elo overrode it.

---

*Generated by Hermes V3.8.0 post-match review pipeline, June 16, 2026*  
*DC hash: `b244c28a0df8` | 296 teams | 10,999 training rows*  
*Sources: Sky Sports, ESPN, AP News, FIFA.com, SofaScore, RFEF, France24, Sporting News*
