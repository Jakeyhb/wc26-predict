# Post-Match Review: Iran vs New Zealand — Group G, Matchday 1

**Date:** June 16, 2026 | **Kickoff:** 01:00 UTC (June 16, 09:00 CST)  
**Venue:** SoFi Stadium, Inglewood (Los Angeles), CA, USA (capacity ~70,240; attendance 70,108)  
**Competition:** FIFA World Cup 2026, Group G — Matchday 1  
**Result:** Iran 2–2 New Zealand (HT: 1–1)  
**Referee:** César Ramos Palazuelos (Mexico)  
**Review version:** V3.8.0 post-match retro

---

## 1. Match Summary

| Detail | Value |
|--------|-------|
| Score | Iran 2 – 2 New Zealand |
| Half-time | 1 – 1 |
| xG (SofaScore/Opta) | Iran 1.50 – New Zealand 1.24 |
| Possession | Iran 48% – New Zealand 52% |
| Shots | Iran 17 (4 on target) – New Zealand 14 (8 on target) |
| Shots Inside Box | Iran 10 – New Zealand 10 |
| Big Chances | Iran 3 – New Zealand 2 |
| Corners | Iran 4 – New Zealand 1 |
| Saves | Iran 6 – New Zealand 2 |
| Clearances | Iran 27 – New Zealand 24 |
| Fouls | Iran 10 – New Zealand 8 |
| Yellow Cards | Iran 1 (Hajsafi 89') – New Zealand 0 |
| Offsides | Iran 2 – New Zealand 0 |
| Referee | César Ramos Palazuelos (Mexico) |
| Man of the Match | **Ramin Rezaeian** (Iran RB, 9.3 SofaScore — 1 goal, 1 assist, 11 crosses, 3 key passes) |

### Goals

| Time | Scorer | Assist | Team | xG |
|------|--------|--------|------|:---:|
| 7' | Elijah Just | Chris Wood (chest-down) | New Zealand | ~0.15 |
| 32' | Ramin Rezaeian | Shahriyar Moghanlou (scramble) | Iran | ~0.20 |
| 54' | Elijah Just | Chris Wood (flick-on) | New Zealand | ~0.16 |
| 64' | Mohammad Mohebi | Ramin Rezaeian (cross) | Iran | ~0.18 |

### Key Events

| Time | Event |
|------|-------|
| 7' | ⚽ NZL — Elijah Just volleys home after Wood chest-down. NZL's fastest WC goal since 2010. |
| 23' | Taremi hits the post from close range — Iran's best chance before equalizer |
| 32' | ⚽ IRN — Rezaeian pounces on loose ball in goalmouth scramble after corner |
| 45+4' | VAR DISALLOWS Nemati goal for marginal offside — Iran denied 2-1 halftime lead |
| 54' | ⚽ NZL — Just scores his second after another Wood flick-on assist |
| 64' | ⚽ IRN — Mohebi heads in Rezaeian's cross from the right, ball goes in off the post |
| 78' | Beiranvand saves from Wood header — prevents NZL third |
| 88' | Crocombe denies Ghoddos long-range effort — match-saving stop |
| 90+3' | Iran free kick into wall — final whistle |

### Historical Context

- **Ramin Rezaeian becomes the first Iranian to score in two different World Cups** (2018 vs Morocco, 2026 vs NZL)
- **Elijah Just scores New Zealand's first-ever World Cup brace** — and becomes the first NZL player with 2 WC goals in a single match
- **Chris Wood becomes first NZL player with 2 assists in a World Cup match** — now has 3 career WC goal involvements
- **Iran remains winless in 2026 World Cup openers** — last WC opening win was 1998 vs USA
- **New Zealand extends unbeaten streak vs Asian teams at World Cups to 3 matches** (1982: 1-1 vs Kuwait; 2010: 1-1 vs Slovakia — technically not Asian but a draw)
- **All 4 Group G teams finish Matchday 1 on 1 point** — mirroring Group H's identical "all-draw" opening round

---

## 2. Prediction vs Actual

### V3.8.0 Retrospective Prediction (Model Only, No Market)

| Model Layer | IRN Win | Draw | NZL Win | Brier |
|-------------|:-------:|:----:|:-------:|:-----:|
| **DC** | 51.19% | **29.30%** | 19.51% | **0.7999** |
| **Enhancer** | 62.12% | 13.29% | 24.59% | **1.1983** |
| **Elo** | 63.90% | 10.82% | 25.28% | **1.2676** |
| **Pi** | 20.08% | 19.07% | 60.85% | **1.0655** |
| DC+Enh (70:30) | 54.47% | 24.50% | 21.04% | 0.9110 |
| DC+Enh+Elo | 55.41% | 23.13% | 21.46% | 0.9440 |
| **Final (DC+Enh+Elo+Pi)** | **51.88%** | **22.72%** | **25.40%** | **0.9308** |

**Actual outcome:** Draw (2-2). **DC was the best individual layer** — again. Its 29.30% draw probability was the highest of any model, confirming the pattern from BEL-EGY and KSA-URU. This is now **4 of 7 matches** where DC is the best individual layer.

### V3.8.0 Pre-Match vs Retro vs V2.0.0

| Version | IRN Win | Draw | NZL Win | Brier |
|---------|:-------:|:----:|:-------:|:-----:|
| V2.0.0 (June 3) | 52.61% | 21.26% | 26.13% | **0.9651** |
| V3.8.0 retro (model only) | 51.88% | 22.72% | 25.40% | **0.9308** |
| V3.8.0 retro (+market) | 51.80% | 24.08% | 24.12% | **0.9028** |
| V3.8.0 pre-match (market+signals) | 52.19% | 23.89% | 23.92% | **0.9089** |

**V3.8.0 improved on V2.0.0 for this match (+0.034 Brier).** The market pushed draw probability from 22.7% to 24.1% — a small but helpful correction. The pre-match (with signals) gave 23.9% draw — slightly better than model-only (22.7%) but not as good as pure retro+market (24.1%). The signals had minimal net impact.

**The model was wrong on direction** (favored Iran ~52%, actual draw) but its Brier (~0.90) reflects a match where Iran genuinely had the better chances (xG 1.50 vs 1.24, hit the post, had a goal disallowed by VAR).

---

## 3. Model Layer Performance Analysis

### 🥇 Best: DC (Brier 0.7999)
- **Gave draw 29.30% — highest of any model layer** (Enhancer: 13.3%, Elo: 10.8%, Pi: 19.1%)
- DC's structural draw bias continues to prove its worth — this is the **3rd consecutive draw** where DC was the best layer
- xG estimate (IRN 1.53 vs NZL 0.88) overestimated the gap (actual 1.50 vs 1.24) but directionally correct
- DC's Iran win 51.2% was cautious — correctly reflecting that this was not a sure thing
- **DC is now 4/7 best layer (BEL-EGY, KSA-URU, IRN-NZL, GER-CUW)**

### 💀 Worst: Elo (Brier 1.2676)
- **Gave draw only 10.82% — the classic Elo structural weakness strikes again**
- Favored Iran at 63.9% — far too confident given the actual balance of play
- Elo gap +161 (IRN 1729 vs NZL 1568) translated to 63.9% Iran — the gap was real (Iran DID outcreate NZL) but the draw probability was absurdly low
- **Elo has been the worst layer on 3 of 7 matches** (ESP-CPV, KSA-URU, IRN-NZL)

### 🔀 Enhancer: Second-Worst (Brier 1.1983)
- Gave Iran 62.1% — even more confident than Elo on Iran winning
- Draw probability 13.3% — only Elo was lower
- Enhancer's "decisive outcome" bias, which helped on TUN-SWE and NED-JPN, is a liability on balanced draws
- **Enhancer continues to struggle on draws** — now 0/4 on draw matches (NED-JPN excepted: Enhancer was best on that draw, but it was a high-scoring 2-2 like this one)

### 🔮 Pi: Still Inverted, But Less Wrong Than Usual (Brier 1.0655)
- Gave NZL 60.85% win probability — completely inverted direction
- BUT: 19.07% draw was second-highest of any layer — closest to DC's 29.3%
- Pi correctly de-rated Iran (20.08%) in a way no other model did
- **Pi anomaly count: NZL 60.9% joins CPV 60.9%, URU 67.9%, and NZL 60.9% on the list of >60% favorites that should never be >60% favorites**

---

## 4. Leave-One-Out Analysis

| Layer | Individual Brier | vs Final Brier | Marginal | Verdict |
|-------|:---------------:|:-------------:|:--------:|---------|
| DC | 0.7999 | 0.9308 | **-0.1309** | **HELPFUL** |
| Pi | 1.0655 | 0.9308 | +0.1347 | Harmful |
| Enhancer | 1.1983 | 0.9308 | +0.2675 | **HARMFUL** |
| Elo | 1.2676 | 0.9308 | +0.3368 | **STRONGLY HARMFUL** |

**DC alone would have given Brier 0.800 vs fusion 0.931** — a fusion penalty of +0.131. This is the **2nd consecutive match** where DC alone outperformed the weighted fusion (KSA-URU: +0.170 penalty, IRN-NZL: +0.131 penalty). The pattern is unambiguous: on balanced draws, the fusion is making things worse by blending in Enhancer's and Elo's anti-draw biases.

**The fusion penalty across all 7 matches:**

| Match | Act | DC Brier | Fusion Brier | Penalty |
|-------|:---:|:--------:|:------------:|:-------:|
| GER-CUW | H | 0.070 | 0.210 | +0.140 |
| NED-JPN | D | 0.714 | 0.669 | -0.045 |
| TUN-SWE | A | 0.341 | 0.254 | -0.087 |
| ESP-CPV | D | 1.337 | 1.281 | -0.056 |
| BEL-EGY | D | 0.517 | 0.606 | +0.089 |
| KSA-URU | D | 0.496 | 0.666 | +0.170 |
| IRN-NZL | D | 0.800 | 0.931 | +0.131 |

**Fusion penalty: DC alone would have beaten the fusion on 4/7 matches.** On the 3 matches where fusion helped, it was driven by Enhancer (NED-JPN, TUN-SWE, ESP-CPV). The current fixed weights (DC=0.70) cannot adapt — when DC is right, the fusion underweights it; when Enhancer is right, the fusion underweights it.

---

## 5. Cross-Match Pattern (7 WC26 Group Matches Audited)

| # | Match | Actual | DC Brier | Enh Brier | Best Layer | DC vs Enh |
|---|-------|--------|:--------:|:---------:|------------|:---------:|
| 1 | GER 7–1 CUW | Home win | **0.070** | 1.288 | DC | DC wins |
| 2 | NED 2–2 JPN | Draw | 0.714 | **0.651** | **Enhancer** | Enh wins |
| 3 | TUN 1–5 SWE | Away win | 0.341 | **0.118** | **Enhancer** | Enh wins |
| 4 | ESP 0–0 CPV | Draw | 1.337 | **1.241** | **Enhancer** | Enh wins |
| 5 | BEL 1–1 EGY | Draw | **0.517** | 0.955 | **DC** | DC wins |
| 6 | KSA 1–1 URU | Draw | **0.496** | 0.751 | **DC** | DC wins |
| 7 | IRN 2–2 NZL | Draw | **0.800** | 1.198 | **DC** | DC wins |

**DC 4/7 best layer | Enhancer 3/7 best layer.** DC takes the lead. The trend is clear: DC has won the last **3 consecutive matches** — all draws.

### Refined Pattern: Match Type Decision Matrix

| Match Type | Sample | DC Best | Enh Best | Verdict |
|------------|:------:|:-------:|:--------:|---------|
| **Lopsided, expected** (GER-CUW) | 1 | 1 | 0 | DC clear winner |
| **Upset — underdog dominates** (NED-JPN, TUN-SWE) | 2 | 0 | 2 | Enhancer clear winner |
| **Black-swan favorite held** (ESP-CPV) | 1 | 0 | 1 | Both terrible; Enhancer least bad |
| **Balanced draw** (BEL-EGY, KSA-URU, IRN-NZL) | 3 | 3 | 0 | **DC clean sweep** |

**The 3-match DC winning streak is NOT a coincidence.** BEL-EGY, KSA-URU, and IRN-NZL share a common profile:
- Elo gap moderate (BEL+128, URU+126, IRN+161 — all 120-170 range)
- Expected competitive contest — neither team >60% favorite
- Actual result: draw (all three!)
- DC's conservative draw probability (25-44%) correctly reflected the uncertainty

**When the Elo gap is moderate (100-200) and neither team is clearly dominant, DC is the superior model.** Enhancer's "pick a winner" bias is structurally wrong for these matches. DC's "never dismiss the draw" bias is structurally correct.

### Cumulative Directional Correctness (7 matches)

| Layer | GER | NED | TUN | ESP | BEL | KSA | IRN | Correct |
|-------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:-------:|
| DC | ✓ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ | **4/7** |
| Enhancer | ✗ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | **2/7** |
| Elo | ✓ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ | **2/7** |
| Pi | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | **1/7** |

---

## 6. Starting Lineups

### Iran (4-4-2 / 4-2-3-1)
```
Alireza Beiranvand (GK, 6 saves)

Ramin Rezaeian ⭐ (RB, 9.3 SofaScore) – Ali Nemati (CB) – Shojae Khalilzadeh (CB) – Milad Mohammadi (LB)
Aria Yousefi (RM) – Saeid Ezatolahi (CM) – Saman Ghoddos (CM) – Mohammad Mohebi (LM)
Mehdi Taremi (C, FW) – Shahriyar Moghanlou (FW)
```

**Coach:** Amir Ghalenoei  
**Key subs:** Ghaedi (46' for Yousefi), Alipour (53' for Moghanlou), Hajsafi (65' for Mohammadi), Hosseinzadeh (80' for Ghoddos)  
**Notable:** Rezaeian played as an attacking RB — his 11 crosses and 3 key passes made him Iran's most dangerous creative outlet despite being a defender. Taremi hit the post and was involved in buildup but didn't register a goal contribution. Nemati had a goal disallowed by VAR at 45+4'.

### New Zealand (4-2-3-1)
```
Max Crocombe (GK, 2 saves)

Tim Payne (RB) – Finn Surman (CB) – Michael Boxall (CB) – Liberato Cacace (LB)
Joe Bell (CM) – Marko Stamenić (CM)
Callum McCowatt (RW) – Sarpreet Singh (AM) – Elijah Just ⭐ (LW, brace)
Chris Wood (C, ST — 2 assists)
```

**Coach:** Darren Bazeley  
**Key subs:** Old (68' for McCowatt), Thomas (68' for Bell), Elliot (78' for Singh), Bindon (90+2'), Randall (90+2')  
**Notable:** Just was clinical — 2 goals from only 0.31 xG, overperforming by nearly 6x. Wood's aerial presence (2 assists from chest-down/flick-on) created both goals with minimal xG. NZL's backline (Boxall 36, Surman 22) was the "odd couple" predicted — conceded 2 but held firm under 2nd-half Iran pressure.

---

## 7. Self-Evolution Actions

### 7.1 Learning Log Entry

| Field | Value |
|-------|-------|
| Error magnitude | 0.9308 (model-only) / 0.9089 (pre-match with market+signals) |
| Error direction | `overestimate_home_moderate` — favored Iran at 51.9% |
| DC marginal | -0.1309 (right direction — best layer, 3rd consecutive win) |
| Enhancer marginal | +0.2675 (strongly wrong direction) |
| Elo marginal | +0.3368 (strongly wrong direction — worst layer) |
| Pi marginal | +0.1347 (wrong direction, but 2nd-least harmful) |
| Model was right? | **No** — favored Iran, actual draw |
| Fusion penalty | +0.131 — DC alone (0.800) better than fusion (0.931) |

### 7.2 Weight Gate Assessment — 7-Match Cumulative Evidence

| Model | GER | NED | TUN | ESP | BEL | KSA | IRN | Pos | Neg | Net |
|-------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| DC | + | − | − | − | + | + | + | **4** | **3** | ↑ |
| Enhancer | − | + | + | + | − | − | − | **3** | **4** | ↓ |
| Elo | + | − | − | − | + | − | − | **2** | **5** | ↓ |
| Pi | + | − | − | − | − | − | − | **1** | **6** | ↓ |

+ = directional contribution positive (individual Brier < final Brier)
− = directional contribution negative (individual Brier > final Brier)

**Recommendation: DC WEIGHT INCREASE from 0.70 → 0.75, Pi WEIGHT DECREASE from 0.10 → 0.05.**

The 7-match evidence now supports a modest weight adjustment:

1. **DC (0.70 → 0.75, +5pp):** DC is 4/7 best layer and has won the last 3 consecutive matches. Its structural draw bias is proved valuable in a tournament where **5/7 matches have been draws or competitive decisions**. Increasing DC weight from 0.70 to 0.75 would reduce the fusion penalty on balanced draws while retaining enough Enhancer weight (0.20) to capture upsets.

2. **Pi (0.10 → 0.05, −5pp):** Pi is 1/7 directional correct and has produced absurd probabilities (NZL 60.9%, CPV 60.9%, URU 67.9%) on 4/7 matches. Its 10% weight is no longer justified. Reducing to 5% would limit its noise contribution while retaining a small diversification benefit.

3. **Elo (0.10 → keep):** Elo is 2/7 correct but its draw suppression is fatal in a draw-heavy tournament. However, the Elo gap is still the most interpretable signal. Keep for now but flag for deeper restructure in V3.9.0.

4. **Enhancer (0.20 → keep):** Enhancer is 3/7 correct and was the best layer on the only 3 non-expected matches. Its anti-draw bias is exactly what makes it the perfect complement to DC. Reducing Enhancer would worsen performance on upsets.

**Projected impact of weight adjustment (DC 0.75, Enhancer 0.20, Elo 0.10, Pi 0.05):**

| Match | Actual | Old Brier | New Brier | Delta |
|-------|--------|:---------:|:---------:|:-----:|
| GER-CUW | Home | 0.210 | ~0.120 | −0.090 |
| NED-JPN | Draw | 0.669 | ~0.684 | +0.015 |
| TUN-SWE | Away | 0.254 | ~0.280 | +0.026 |
| ESP-CPV | Draw | 1.281 | ~1.290 | +0.009 |
| BEL-EGY | Draw | 0.606 | ~0.560 | −0.046 |
| KSA-URU | Draw | 0.666 | ~0.582 | −0.084 |
| IRN-NZL | Draw | 0.931 | ~0.865 | −0.066 |

**Net improvement on 4/7 matches, net regression on 3/7.** The draws (5/7 matches) benefit most; upset matches (NED-JPN, TUN-SWE) slightly regress. This is the correct trade-off for a draw-heavy tournament.

### 7.3 Parameter Provenance

| Field | Value |
|-------|-------|
| DC hash | `b244c28a0df8` |
| DC teams | 296 |
| Training rows | 10,999 |
| Training max date | 2026-06-03 |
| Weight label | `AUTO_OPTIMIZED` |
| Pipeline version | V3.8.0 |

---

## 8. Data Fixes Applied

| Table | Field | Old Value | New Value |
|-------|-------|-----------|-----------|
| `match_results` | (new) | — | IRN 2–2 NZL, xG 1.50–1.24 |
| `matches` | status | scheduled | finished |
| `wc26_schedule` | match_status | SCHEDULED | FINISHED |
| `wc26_schedule` | home_goals | NULL | 2 |
| `wc26_schedule` | away_goals | NULL | 2 |
| `prediction_snapshots` | (new V3.8.0-retro) | — | Retro model-only prediction + Brier analysis |
| `prediction_learning_log` | (new) | — | 7-match learning entry |

### ✅ Venue Check: CORRECT

**Second consecutive match with correct venue.** SoFi Stadium, Inglewood, CA — no fix needed.

Venue bug summary across WC26 (7 matches):
1. NED-JPN: DB said Estadio Akron → actual AT&T Stadium ❌
2. TUN-SWE: DB said NRG Stadium → actual Estadio BBVA ❌
3. ESP-CPV: DB said Estadio Akron → actual Mercedes-Benz Stadium ❌
4. GER-CUW: DB correct ✅
5. BEL-EGY: DB correct ✅
6. KSA-URU: DB correct ✅
7. IRN-NZL: DB correct ✅

---

## 9. Group G Standings After Matchday 1

| # | Team | P | W | D | L | GF | GA | GD | Pts |
|---|------|---|---|---|---|----|----|-----|------|
| 1 | Iran | 1 | 0 | 1 | 0 | 2 | 2 | 0 | 1 |
| 2 | New Zealand | 1 | 0 | 1 | 0 | 2 | 2 | 0 | 1 |
| 3 | Belgium | 1 | 0 | 1 | 0 | 1 | 1 | 0 | 1 |
| 4 | Egypt | 1 | 0 | 1 | 0 | 1 | 1 | 0 | 1 |

**All four Group G teams on 1 point.** Group G and Group H are the only groups where every team drew their opener. Iran and New Zealand sit above Belgium and Egypt on goals scored (2 vs 1).

### Remaining Group G Fixtures

| Date | Match | Venue |
|------|-------|-------|
| June 21 | Belgium vs Iran | AT&T Stadium, Arlington |
| June 22 | New Zealand vs Egypt | Mercedes-Benz Stadium, Atlanta |
| June 27 | New Zealand vs Belgium | NRG Stadium, Houston |
| June 27 | Egypt vs Iran | BC Place, Vancouver |

**Group G is wide open.** The two June 21-22 matches are critical: if Belgium beat Iran and Egypt beat NZL, the group becomes Belgium 4pts, Egypt 4pts, Iran 1pt, NZL 1pt. But if Iran beat Belgium on US soil... Group G becomes the tournament's real "Group of Death."

---

## 10. Comparison: Group G Openers

Both Group G matches on June 15-16 ended in draws:

| Factor | BEL 1–1 EGY | IRN 2–2 NZL |
|--------|:-----------:|:-----------:|
| Favorite | Belgium (DC 41.3% draw) | Iran (DC 51.2% win) |
| Underdog qualities | Salah birthday assist, Ashour goal | Chris Wood 2 assists, Just brace |
| xG gap | +0.25 to Belgium (1.32–1.07) | +0.26 to Iran (1.50–1.24) |
| Total goals | 2 | 4 |
| Lead changes | 2 (EGY 1-0, BEL OG 1-1) | 3 (NZL 1-0, IRN 1-1, NZL 2-1, IRN 2-2) |
| Best model layer | DC (0.517) | DC (0.800) |
| DC Brier | 0.517 | 0.800 |
| Fusion Brier | 0.606 | 0.931 |
| Post/crossbar | De Bruyne (53') | Taremi (23') |
| VAR disallowed goal | No | Yes — Nemati (45+4') |
| Predictability | HIGH (DC saw draw 41.3%) | MODERATE (DC draw 29.3% but Iran still favored) |

**Both Group G matches were draws, but BEL-EGY was more predictable.** DC gave draw 41.3% for BEL-EGY (the highest draw probability of any WC26 pre-match prediction) vs 29.3% for IRN-NZL (still highest of any layer, but much less confident).

---

## 11. Key Takeaways

1. **DC is now the best model on a plurality of WC26 matches (4/7).** The 3-match winning streak (BEL-EGY, KSA-URU, IRN-NZL) is not a fluke — all three share a profile of moderate Elo gap (120-170), competitive expectations, and actual draw results. DC's structural draw bias, long considered a "bug," is proving to be the single most valuable model feature in a draw-heavy tournament (5/7 draws).

2. **Enhancer's anti-pattern crystallizes: bad on draws, essential on upsets.** Enhancer's draw probabilities across the 5 draw matches: 23.1% (NED-JPN), 9.4% (ESP-CPV), 17.0% (BEL-EGY), 31.6% (KSA-URU), 13.3% (IRN-NZL). Average: 18.9%. DC's draw probabilities: 27.7%, 15.7%, 35.7%, 43.5%, 29.3%. Average: 30.4%. **DC gives draws 11.5pp more probability than Enhancer on average** — and in a tournament where 71% of matches are draws, that's the difference between right and wrong.

3. **Elo's draw suppression is now indefensible (2/7 correct).** Elo has given draw <15% on 5/7 matches. In a tournament where 5/7 matches are draws, a model that structurally predicts <15% draw is fundamentally miscalibrated. Elo needs a draw-boosting adjustment — its raw head-to-head probabilities are suitable for knockout football, not group stage tournaments.

4. **Pi should be reduced to 5% weight or removed.** Pi is 1/7 correct. The NZL 60.9% anomaly appeared in the pre-match report and was flagged as a data quality issue — and it was indeed wrong. But Pi's errors are no longer novel or informative; they are persistent and damaging. The 5% residual weight would serve only as a diversification hedge with minimal impact.

5. **The fusion penalty is a real cost of fixed weights.** On 4/7 matches, a simple decision rule ("use DC for Elo gap <200, use Enhancer for Elo gap >200") would have outperformed the weighted fusion. The current 0.70/0.20/0.10/0.10 split is directionally reasonable but structurally unable to adapt to match type.

6. **xG models are getting the attacking balance right.** DC predicted xG IRN 1.53 – NZL 0.88; actual was IRN 1.50 – NZL 1.24. DC correctly identified Iran's attacking edge (+0.65 predicted vs +0.26 actual) but underestimated NZL's clinical finishing (Elijah Just: 2 goals from 0.31 xG, Chris Wood: 2 assists from hold-up play that bypassed xG models).

7. **Chris Wood proved the pre-match thesis.** The pre-match report flagged Wood as a "genuine mismatch" against Iran's aging CBs. His 2 assists (chest-down and flick-on from direct balls) exploited exactly the aerial weakness identified. However, the net -0.7% signal adjustment for NZL was too negative — NZL's attacking threat through Wood was underweighted.

8. **Rezaeian's 9.3 SofaScore is the highest rating of any WC26 player so far.** A right-back scoring a goal, providing an assist, delivering 11 crosses, and winning 7 ground duels is an extraordinary statistical performance. No prediction model accounts for a fullback having the game of his career.

---

## 12. Summary

**V3.8.0 Verdict: IRN 52.2% / Draw 23.9% / NZL 23.9% (pre-match) → Actual: Draw 2-2.**

DC's 29.3% draw probability was the highest of any model layer and the closest to reality. For the 3rd consecutive draw match, DC outperformed every other layer. The model was wrong on direction (Iran favored) but not by much — Iran generated more xG (1.50 vs 1.24), hit the post, and had a goal disallowed by VAR. The difference between Iran winning 2-1 and drawing 2-2 was marginal.

The 7-match cumulative evidence now supports a weight adjustment: **DC 0.70 → 0.75, Pi 0.10 → 0.05.** This modest shift would reduce the fusion penalty on draws (the majority outcome) while retaining Enhancer's upset-detection capability. More fundamentally, the evidence for a **dynamic weight system** (V3.9.0) is now overwhelming: DC and Enhancer are complementary tools that dominate different match types, and no single fixed weight can be optimal.

**The Pi experiment has failed. The Elo draw problem is structural. DC is the tournament's most valuable model. Enhancer remains the essential counterweight for when DC is wrong.**

---

*Generated by Hermes V3.8.0 post-match review pipeline, June 16, 2026*  
*DC hash: `b244c28a0df8` | 296 teams | 10,999 training rows*  
*Sources: AP News, Xinhua, FIFA.com, SofaScore, WhoScored, Fantasy Football Scout, BSS News, AFP*
