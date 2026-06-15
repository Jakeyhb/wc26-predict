# Pre-Match Prediction: Iran vs New Zealand — Group G, Matchday 1

**Prediction date:** June 16, 2026 (Beijing time)  
**Match date:** June 16, 2026, 01:00 UTC (June 16, 09:00 CST)  
**Venue:** SoFi Stadium, Inglewood, CA, USA (capacity ~70,240)  
**Competition:** FIFA World Cup 2026, Group G — Matchday 1  
**Referee:** TBD (FIFA appointment)  
**Prediction system:** V3.8.0 Full Pipeline — DC -> Enhancer -> Elo -> Pi -> Market -> Signals + Weather

---

## 1. V3.8.0 Final Prediction

| Outcome | Model Only | **+ Market** | **+ Signals + Weather** |
|---------|:----------:|:-----------:|:-----------------------:|
| Iran Win | 51.9% | 51.9% | **52.2%** |
| Draw | 22.7% | 23.9% | **23.9%** |
| New Zealand Win | 25.4% | 24.2% | **23.9%** |

**Verdict:** Iran clear favorite at 52.2%, but not overwhelming. This is a match Iran *should* win, but with elevated uncertainty: Sardar Azmoun's shock squad omission removes Iran's best goalscorer, and New Zealand's Chris Wood provides a genuine aerial threat on set pieces. The market and model agree on Iran as ~52% favorite.

### Expected Goals (xG)

| Team | xG |
|------|:---:|
| Iran | 1.53 |
| New Zealand | 0.88 |

Iran's 0.65 xG edge is substantial — the 3rd widest xG gap of any WC26 match analyzed. The most likely scorelines: 2-0 Iran, 1-0 Iran, 1-1 draw.

---

## 2. Full Fusion Pipeline

| Layer | IRN Win | Draw | NZL Win | Source |
|-------|:-------:|:----:|:-------:|--------|
| **DC** | 51.19% | 29.30% | 19.51% | Disk cache (V3.8.0) |
| **Enhancer** | 62.12% | 13.29% | 24.59% | Disk cache (V3.8.0) |
| DC+Enh (70:30) | 54.47% | 24.50% | 21.04% | Fused |
| **+Elo** (10%) | 55.41% | 23.13% | 21.46% | Elo gap +161 favors Iran |
| **+Pi** (10%) | 51.88% | 22.72% | 25.40% | Pi anomaly flagged (see below) |
| **+Market** (25%) | **51.94%** | **23.88%** | **24.18%** | apifootball.com (LIVE) |
| **+Signals** | **52.19%** | **23.89%** | **23.92%** | Injury/squad news |

### Market Impact (LIVE)

The market provides only a marginal shift (+0.06pp Iran). This is unusual — in most WC26 matches, the market shifts probabilities by 5-10pp. Here, the market-implied probabilities (Iran 52.1% / Draw 27.4% / NZL 20.5%) are very close to the model-only prediction (Iran 51.9% / Draw 22.7% / NZL 25.4%). Strong **model-market convergence** increases confidence.

---

## 3. Live Market Odds

| Source | IRN | Draw | NZL |
|--------|:---:|:----:|:---:|
| **apifootball.com** (LIVE) | 1.81 | 3.45 | 4.60 |
| **Implied** (vig-removed) | 52.1% | 27.4% | 20.5% |
| **V3.8.0 adjusted** | 52.2% | 23.9% | 23.9% |
| **FanDuel** (US market) | -125 | +240 | +380 |
| **BetOnline** | -118 | +245 | +350 |

**Model-Market Gap:** < 4pp on all outcomes. This is the **closest model-market alignment** of any WC26 match analyzed so far, suggesting high consensus on Iran's edge and the competitive nature of this matchup.

---

## 4. Live Weather — SoFi Stadium, Inglewood

| Metric | Value | Impact |
|--------|-------|:------:|
| Temperature | **20.0 degC** | Ideal for football |
| Weather | **Mostly Clear** (Code 1) | No visibility issues |
| Precipitation | **0.0 mm** | Dry pitch |
| Wind | **16.6 km/h** | Light breeze — negligible |
| Humidity | **79%** | Slightly humid but comfortable |
| Forecast | Live (Open-Meteo API) | — |

**Weather impact: NONE.** Pristine Southern California evening. SoFi Stadium's roof may be open or closed — either way, conditions are optimal for both teams. No weather-based adjustments necessary.

---

## 5. News Intelligence & Signal Adjustments

### Iran — Azmoun Shock Omission

| # | Type | Player | Status | Impact | Note |
|---|------|--------|--------|:------:|------|
| 1 | Squad | Sardar Azmoun | **DROPPED** | -1.5% | Star striker (53 intl goals) excluded from final squad. Bold decision by Ghalenoei. |
| 2 | Injury | Alireza Jahanbakhsh | Doubtful | -0.5% | Likely to miss out — experienced winger with 80+ caps |
| 3 | Recovery | Mehdi Torabi | FIT | +0.3% | Calf recovered, back in full training |
| 4 | Recovery | Saeid Ezatolahi | FIT | +0.3% | Foot recovered — expected to start as holding mid |
| 5 | Recovery | Roozbeh Cheshmi | FIT | +0.2% | Hamstring recovered, back in full training |
| 6 | Strength | Mehdi Taremi (C) | FULLY FIT | +0.8% | 60 goals in 105 caps, Olympiacos star. Captain and focal point. |
| 7 | Form | Team | W-W-W | +0.5% | Beat Mali 2-0, Gambia 3-1, Costa Rica 5-0 in last 3 friendlies |

### New Zealand — Wood Carries All Hopes

| # | Type | Player | Status | Impact | Note |
|---|------|--------|--------|:------:|------|
| 8 | Injury | Ryan Thomas | OUT | -0.5% | Experienced midfielder (hamstring) — key creative outlet missing |
| 9 | Strength | Chris Wood (C) | FULLY FIT | +0.8% | All-time NZL top scorer (45+ goals). Recovered from knee injury. |
| 10 | Fitness | Joe Bell | Doubtful | -0.3% | Working back from injury — may not start |
| 11 | Form | Team | L-L-L-L-W | -1.0% | Lost 4 of last 5: Haiti 4-0, England 1-0, Finland 2-0, Ecuador |
| 12 | History | Team | 0W-3D-3L | -0.5% | Never won a World Cup match. First WC appearance since 2010. |

**Net adjustment:** Iran -0.7% / NZL -0.7%. Signals broadly cancel out — Azmoun's absence hurts Iran, NZL's poor form and WC inexperience offset.

### Predicted Lineups

**Iran (4-3-3):** Beiranvand; Rezaeian, Khalilzadeh, Kanaanizadegan, Hajsafi; Ezatolahi, Razzaghinia; Mohebi, Ghoddos, Ghayedi; Taremi (C).
*Coach: Amir Ghalenoei — 7th World Cup appearance for Iran, most experienced Asian side.*

**New Zealand (4-2-3-1):** Crocombe; Payne, Boxall, Surman, Cacace; Bell/Stamenic, Rufer; Just, Garbett, Singh; Wood (C).
*Coach: Darren Bazeley — NZL's first World Cup since South Africa 2010.*

---

## 6. Team Profiles

### Iran

| Metric | Value |
|--------|-------|
| Elo Rating | 1,729 |
| Pi Rating | 1.01 |
| DC Attack | 2.1064 |
| DC Defense | 0.4654 |
| Manager | Amir Ghalenoei |
| Recent Form | W-W-W-L-W (3 straight wins) |
| FIFA Rank | ~20th |
| WC Appearances | 7 (1978, 1998, 2006, 2014, 2018, 2022, 2026) |
| Best WC Result | Group Stage (all 6 previous) |
| Key Strength | Mehdi Taremi — 60 goals, WC experience, Olympiacos form |
| Key Weakness | Azmoun omission removes proven goalscorer; attacking depth reduced |

### New Zealand

| Metric | Value |
|--------|-------|
| Elo Rating | 1,568 |
| Pi Rating | 1.64 |
| DC Attack | 1.8955 |
| DC Defense | 0.7408 |
| Manager | Darren Bazeley |
| Recent Form | L-L-L-L-W (4 losses in last 5) |
| FIFA Rank | ~85th |
| WC Appearances | 3 (1982, 2010, 2026) |
| Best WC Result | Group Stage (all previous) |
| Key Strength | Chris Wood — aerial threat, physical presence, all-time top scorer |
| Key Weakness | Never won a WC match; 16-year gap since last appearance; poor results vs non-OFC opponents |

---

## 7. Model Layer Deep Dive

### DC: Moderate Iran Favorite

DC gives Iran 51.2% — not overwhelming but clear. DC's draw probability (29.3%) is high, as expected from its structural draw bias. The xG gap (1.53 vs 0.88) is the 3rd widest of any WC26 match, suggesting Iran's attacking advantage is real.

### Enhancer: Stronger Iran Signal

Enhancer gives Iran 62.1% — notably higher than DC. The 10.9pp DC-Enhancer gap is moderate (nowhere near the 33.9pp BEL-EGY divergence). Both models agree on direction; they disagree only on magnitude.

### Elo: Gap +161 Favors Iran

Iran's 161-point Elo advantage (1729 vs 1568) is significant but not enormous — equivalent to ~60% win probability on neutral ground. Elo gives NZL 25.3%, which is notably higher than DC's 19.5%, suggesting Elo detects something in NZL's favor that DC misses.

### Pi: **ANOMALY FLAGGED**

**Pi raw probabilities: Iran 20.1% / Draw 19.1% / NZL 60.8%.** This is completely inverted from every other model layer, the market, and common sense. Pi ratings (IRN 1.01, NZL 1.64) appear to have a data quality issue for New Zealand. Possible causes:
- NZL's OFC qualifying campaign produced inflated Pi ratings against weak opposition
- Small sample size of NZL vs non-OFC opponents in Pi's training window
- Pi may heavily weight recent results where NZL's heavy defeats (Haiti 4-0, Ecuador) weren't yet in the dataset

**The Pi anomaly is noted but has limited impact due to its 10% weight.** The final prediction is not meaningfully distorted.

---

## 8. Tactical Matchup

### Iran Attack vs NZL Defense
- **Taremi vs Boxall/Surman:** Taremi's movement, hold-up play, and finishing are several levels above anything NZL's CB pairing faces in OFC. Boxall (36) and Surman (22) are an odd couple — aging veteran vs inexperienced youngster.
- **Wide overloads:** Mohebi and Ghayedi will stretch NZL's full-backs wide, creating space for Ghoddos to operate between the lines.
- **Set pieces:** Kanaanizadegan and Khalilzadeh are aerial threats from corners — NZL concedes heavily from set pieces vs quality opposition.

### NZL Attack vs Iran Defense ⚠️ WOOD FACTOR
- **Chris Wood aerial duels:** This is NZL's only viable route to goal — direct balls and crosses targeting Wood's head. Iran's CBs (Khalilzadeh 36, Kanaanizadegan 32) are experienced but not dominant aerially.
- **Counter-attacks:** With 16.6 km/h wind and long balls to Wood, NZL can bypass Iran's midfield press entirely. Iran's high line under Ghalenoei is vulnerable to direct play.
- **Sarpreet Singh:** The creative wildcard — if NZL can get Singh on the ball between Iran's midfield and defense, he has the technical quality to create chances.

---

## 9. Group G Context

| # | Team | P | W | D | L | Pts |
|---|------|---|---|---|---|-----|
| 1 | Belgium | 0 | 0 | 0 | 0 | 0 |
| 2 | Egypt | 0 | 0 | 0 | 0 | 0 |
| 3 | Iran | 0 | 0 | 0 | 0 | 0 |
| 4 | New Zealand | 0 | 0 | 0 | 0 | 0 |

**Earlier today:** Belgium vs Egypt (June 15, 19:00 UTC at Lumen Field). This match sets the Group G context — if Belgium win, pressure on Iran to secure 3 points against the group's weakest team.

### Remaining Group G Fixtures

| Date | Match | Venue |
|------|-------|-------|
| June 21 | Belgium vs Iran | AT&T Stadium, Arlington |
| June 22 | New Zealand vs Egypt | Mercedes-Benz Stadium, Atlanta |
| June 27 | New Zealand vs Belgium | NRG Stadium, Houston |
| June 27 | Egypt vs Iran | BC Place, Vancouver |

---

## 10. Prediction Confidence

| Factor | Assessment | Confidence |
|--------|-----------|:----------:|
| Model-Market alignment | Exceptional: <4pp gap on all outcomes | High |
| DC-Enhancer agreement | Same direction, moderate magnitude gap | High |
| Recent form | Iran W-W-W vs NZL L-L-L-L | High |
| Pi anomaly | NZL rated 60.9% favorite — data issue | Flag |
| Azmoun absence | Star striker dropped — significant | Flag |
| WC experience gap | Iran 7th WC vs NZL 3rd, 16yr gap | Medium |
| H2H | First-ever meeting — no data | Low |
| Weather | Benign — no impact | High |

**Overall confidence: MEDIUM-HIGH.** This is a cleaner prediction than BEL-EGY or KSA-URU. Iran's edge is substantial and consistently measured across models, market, and form. The main risks are: (1) Azmoun's absence hurting more than expected, (2) Chris Wood single-handedly keeping NZL competitive via set pieces, and (3) the Pi anomaly signaling something we're missing about NZL.

---

## 11. Comparison with External Predictions

| Source | Prediction |
|--------|-----------|
| MARCA Elo Model | Iran 54-62% |
| CBS Sports (Jon Eimer) | Under 2.5 Goals |
| CBS Sports (Martin Green) | Iran to Win (-110) |
| The Sports Rush | Iran Win + Over 2.0 Goals |
| Total Football Analysis | Iran Win 5/6 |
| Sports Mole | Iran 2-0 |
| BetOnline / FanDuel | Iran ~53% implied |
| **V3.8.0 (full fusion)** | **Iran 52.2% / Draw 23.9% / NZL 23.9%** |

Broad consensus: Iran win, likely by 1-2 goals, NZL competitive but outmatched.

---

## 12. Key Scenarios & Expected Outcomes

| Outcome | V3.8.0 Prob | Implication |
|----------|:----------:|-------------|
| Iran win | 52.2% | Iran on track for R16; must beat NZL as the "easiest" Group G match |
| Draw | 23.9% | Frustrating for Iran — pressure mounts before Belgium; NZL delighted |
| New Zealand win | 23.9% | Historic first WC win; Group G thrown wide open; Iran in crisis |

**Most likely scorelines:** Iran 2-0, Iran 1-0, 1-1 draw.

---

## 13. Betting Value Assessment

| Market | Line | Assessment |
|--------|------|-----------|
| Iran Win | 1.81 (-123) | Fair value — model at 52%, market at 52% |
| Draw | 3.45 (+245) | Slightly undervalued — model at 23.9% vs market 27.4% |
| NZL Win | 4.60 (+360) | Overvalued by market — model sees NZL at 23.9% vs market 20.5% |
| Under 2.5 Goals | ~1.83 (-120) | Value — Iran 2-0 or 1-0 most likely; NZL unlikely to score multiples |

**Best value:** NZL +1.5 Asian Handicap. The model gives NZL a combined 47.8% chance of win or draw — significantly more respect than the betting market's 20.5% win probability for NZL.

---

## 14. Summary

**V3.8.0 Full Fusion Verdict: Iran 52.2% / Draw 23.9% / New Zealand 23.9%.**

This is the first-ever meeting between Iran and New Zealand, and the pattern is clear: Iran is the better team across every metric — Elo (+161), DC xG (+0.65), FIFA ranking (~65 places higher), and recent form (3 straight wins vs 4 losses in 5). The market and model are in unusually close agreement, which increases confidence.

However, three factors prevent this from being a "sure thing":

1. **Sardar Azmoun's shock omission.** Dropping a 53-goal striker from the World Cup squad is a seismic decision. Taremi is world-class but the attacking depth behind him is unproven. If NZL successfully neutralize Taremi, Iran's Plan B is unclear.

2. **Chris Wood is a genuine mismatch.** At 6'3", Wood against Iran's aging CB pairing is a physical problem that doesn't appear in Elo or DC data. One set piece, one cross — NZL can score without playing well.

3. **First-game uncertainty.** Iran has never played New Zealand. NZL's OFC isolation means their true quality is hard to calibrate. The Pi anomaly (NZL 60.9%!) may be noise, but it could also be detecting something the other models miss.

On balance, Iran should win. But "should" is different from "will." The 23.9% draw probability is real — if Iran fail to score early, NZL's defensive block + Wood's aerial threat can produce a frustrating stalemate. This is a 2-0 game on paper that could easily become 1-1 if Iran's finishing is off.

---

*Generated by Hermes V3.8.0 Full Prediction Pipeline*  
*Model: disk cache single source (DC hash `b244c28a0df8`, 296 teams, 10,999 rows)*  
*Market: apifootball.com (LIVE), odds H1.81/D3.45/A4.60*  
*Weather: Open-Meteo API (LIVE) — SoFi Stadium, Inglewood @ 01:00 UTC*  
*News: OneFootball, Yahoo Sports, CBS Sports, RotoWire, Sports Mole — June 15, 2026*  
*Weights: WORLD_CUP_V3.8 (DC=0.70, Enhancer=0.20, Elo=0.10, Pi=0.10, Market=0.25)*
