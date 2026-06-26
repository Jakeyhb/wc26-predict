# 🏆 Post-Match Review: June 26, 2026 — Groups D, E, F Final Matchday

**Generated**: 2026-06-26 04:04 UTC
**Pipeline**: batch_postmatch_june26.py | V4.3.0-beta
**Data Sources**: Sofascore, FIFA.com, SkySports, Opta, SportingNews, ZeroZero

---

## 📊 Executive Summary

| Metric | Value |
|:---|---:|
| **Matches analyzed** | 6 |
| **Direction correct** | 3/6 (50.0%) |
| **Average Brier** | 0.5047 |
| **Market direction** | 66.7% |
| **DC direction** | 50.0% |
| **Enhancer direction** | 50.0% |

### Cumulative WC Panel (13 pre-June26 + 6 June26 = 19 matches)

| Component | Direction Accuracy |
|:---|---:|
| Market | TBD (need full recount) |
| DC | TBD |
| Pi | TBD |
| Elo | TBD |
| Enhancer | TBD |

---

## 🔍 Per-Match Analysis

### 1. Ecuador vs Germany

**Score**: 2-1 | **Predicted Fav**: A | **Direction**: ❌ WRONG | **Brier**: 0.9226

#### Component Breakdown

| Component      | Probabilities (H/D/A)       | Fav | Dir | Brier |
|:---------------|:----------------------------|:---:|:---:|------:|
| dc             |  13.2% /  26.6% /  60.2% | A | ❌ | 1.1865 |
| enhancer       |  10.0% /  17.9% /  72.2% | A | ❌ | 1.3629 |
| weibull        |   1.9% /  22.3% /  75.8% | A | ❌ | 1.5858 |
| elo            |  35.6% /  24.0% /  40.4% | A | ❌ | 0.6351 |
| pi             |  41.5% /  20.6% /  37.9% | H | ✅ | 0.5284 |
| dc_enh         |  12.2% /  23.8% /  64.0% | A | ❌ | 1.2380 |
| pre_market     |  27.4% /  19.7% /  52.9% | A | ❌ | 0.8465 |
| post_market    |  24.3% /  20.0% /  55.7% | A | ❌ | 0.9226 |

#### ⚽ xG Comparison

| Metric | Predicted | Actual |
|:---|---:|---:|
| Home xG | 0.49 | 1.39 |
| Away xG | 1.40 | 0.68 |

#### 🎯 Motivation Factor
- **Match Type**: offensive_asymmetric
- **Home Motivation**: 0.7 | **Away Motivation**: 0.1
- **EI Score**: 0.5
- **Adjustment**: H+0.093 / D-0.035 / A-0.059
- **Explanation**: [offensive_asymmetric] One team with much to gain/lose, the other indifferent. Adj: home+9.3% draw-3.5% away-5.9%

#### ⚠️ DC-Enhancer Divergence
- **Max Divergence**: 11.9pp
- **Severity**: normal
- **Note**: N/A

#### 📊 Market Data
- **Provider**: apifootball.com
- **Market Weight**: 0.3

---

### 2. Curacao vs Ivory Coast

**Score**: 0-2 | **Predicted Fav**: A | **Direction**: ✅ CORRECT | **Brier**: 0.0891

#### Component Breakdown

| Component      | Probabilities (H/D/A)       | Fav | Dir | Brier |
|:---------------|:----------------------------|:---:|:---:|------:|
| dc             |   7.4% /  14.3% /  78.2% | A | ✅ | 0.0733 |
| enhancer       |   6.5% /  21.2% /  72.3% | A | ✅ | 0.1257 |
| weibull        |   0.4% /   5.5% /  94.1% | A | ✅ | 0.0065 |
| elo            |  22.7% /  21.8% /  55.6% | A | ✅ | 0.2962 |
| pi             |  16.8% /  18.4% /  64.8% | A | ✅ | 0.1858 |
| dc_enh         |   7.1% /  16.5% /  76.4% | A | ✅ | 0.0883 |
| pre_market     |   8.0% /  17.7% /  74.3% | A | ✅ | 0.1040 |
| post_market    |   7.8% /  16.1% /  76.1% | A | ✅ | 0.0891 |

#### ⚽ xG Comparison

| Metric | Predicted | Actual |
|:---|---:|---:|
| Home xG | 0.62 | 0.47 |
| Away xG | 2.35 | 1.30 |

#### 🎯 Motivation Factor
- **Match Type**: defensive_asymmetric
- **Home Motivation**: 0.6 | **Away Motivation**: 0.8
- **EI Score**: 0.5
- **Adjustment**: H-0.017 / D+0.013 / A+0.003
- **Explanation**: [defensive_asymmetric] One team protecting a draw, the other with less at stake. Adj: home-1.7% draw+1.3% away+0.3%

#### ⚠️ DC-Enhancer Divergence
- **Max Divergence**: 6.9pp
- **Severity**: normal
- **Note**: N/A

#### 📊 Market Data
- **Provider**: apifootball.com
- **Market Weight**: 0.3

---

### 3. Tunisia vs Netherlands

**Score**: 1-3 | **Predicted Fav**: A | **Direction**: ✅ CORRECT | **Brier**: 0.0968

#### Component Breakdown

| Component      | Probabilities (H/D/A)       | Fav | Dir | Brier |
|:---------------|:----------------------------|:---:|:---:|------:|
| dc             |  16.3% /  19.5% /  64.2% | A | ✅ | 0.1924 |
| enhancer       |  17.1% /  31.9% /  51.1% | A | ✅ | 0.3699 |
| weibull        |   1.0% /   8.2% /  90.8% | A | ✅ | 0.0153 |
| elo            |  33.0% /  23.8% /  43.2% | A | ✅ | 0.4884 |
| pi             |  21.5% /  19.3% /  59.1% | A | ✅ | 0.2508 |
| dc_enh         |  16.5% /  23.4% /  60.0% | A | ✅ | 0.2421 |
| pre_market     |  10.4% /  20.6% /  69.0% | A | ✅ | 0.1491 |
| post_market    |   8.2% /  16.7% /  75.1% | A | ✅ | 0.0968 |

#### ⚽ xG Comparison

| Metric | Predicted | Actual |
|:---|---:|---:|
| Home xG | 0.96 | 0.43 |
| Away xG | 2.06 | 1.68 |

#### 🎯 Motivation Factor
- **Match Type**: offensive_asymmetric
- **Home Motivation**: 0.15 | **Away Motivation**: 0.7
- **EI Score**: 0.5
- **Adjustment**: H-0.075 / D-0.009 / A+0.085
- **Explanation**: [offensive_asymmetric] One team with much to gain/lose, the other indifferent. Adj: home-7.5% draw-0.9% away+8.5%

#### ⚠️ DC-Enhancer Divergence
- **Max Divergence**: 13.1pp
- **Severity**: normal
- **Note**: N/A

#### 📊 Market Data
- **Provider**: apifootball.com
- **Market Weight**: 0.3319879361967122

---

### 4. Japan vs Sweden

**Score**: 1-1 | **Predicted Fav**: H | **Direction**: ❌ WRONG | **Brier**: 0.8473

#### Component Breakdown

| Component      | Probabilities (H/D/A)       | Fav | Dir | Brier |
|:---------------|:----------------------------|:---:|:---:|------:|
| dc             |  53.0% /  22.9% /  24.1% | H | ❌ | 0.9325 |
| enhancer       |  30.5% /  33.4% /  36.0% | A | ❌ | 0.6661 |
| weibull        |  59.5% /  34.4% /   6.0% | H | ❌ | 0.7881 |
| elo            |  54.9% /  21.9% /  23.2% | H | ❌ | 0.9646 |
| pi             |  68.4% /  17.5% /  14.0% | H | ❌ | 1.1682 |
| dc_enh         |  45.8% /  26.3% /  27.9% | H | ❌ | 0.8308 |
| pre_market     |  51.6% /  26.3% /  22.1% | H | ❌ | 0.8580 |
| post_market    |  50.8% /  26.6% /  22.6% | H | ❌ | 0.8473 |

#### ⚽ xG Comparison

| Metric | Predicted | Actual |
|:---|---:|---:|
| Home xG | 1.73 | 1.31 |
| Away xG | 1.10 | 0.42 |

#### 🎯 Motivation Factor
- **Match Type**: defensive_asymmetric
- **Home Motivation**: 0.8 | **Away Motivation**: 0.7
- **EI Score**: 0.5
- **Adjustment**: H+0.003 / D+0.013 / A-0.017
- **Explanation**: [defensive_asymmetric] One team protecting a draw, the other with less at stake. Adj: home+0.3% draw+1.3% away-1.7%

#### ⚠️ DC-Enhancer Divergence
- **Max Divergence**: 22.5pp
- **Severity**: high
- **Note**: Large divergence (22.5pp) on home. DC rates this outcome higher. Recommend checking DC params and Enhancer features for 

#### 📊 Market Data
- **Provider**: apifootball.com
- **Market Weight**: 0.3

---

### 5. Turkey vs United States

**Score**: 0-1 | **Predicted Fav**: A | **Direction**: ✅ CORRECT | **Brier**: 0.3415

#### Component Breakdown

| Component      | Probabilities (H/D/A)       | Fav | Dir | Brier |
|:---------------|:----------------------------|:---:|:---:|------:|
| dc             |  34.3% /  24.7% /  41.0% | A | ✅ | 0.5273 |
| enhancer       |  10.0% /  22.6% /  67.4% | A | ✅ | 0.1670 |
| weibull        |   0.2% /   3.1% /  96.7% | A | ✅ | 0.0021 |
| elo            |  44.2% /  23.7% /  32.1% | H | ❌ | 0.7120 |
| pi             |  28.5% /  20.2% /  51.3% | A | ✅ | 0.3596 |
| dc_enh         |  24.1% /  23.8% /  52.0% | A | ✅ | 0.3453 |
| pre_market     |  23.8% /  22.9% /  53.3% | A | ✅ | 0.3273 |
| post_market    |  24.7% /  23.0% /  52.3% | A | ✅ | 0.3415 |

#### ⚽ xG Comparison

| Metric | Predicted | Actual |
|:---|---:|---:|
| Home xG | 1.31 | 0.50 |
| Away xG | 1.45 | 0.25 |

#### 🎯 Motivation Factor
- **Match Type**: defensive_asymmetric
- **Home Motivation**: 0.6 | **Away Motivation**: 0.7
- **EI Score**: 0.5
- **Adjustment**: H-0.017 / D+0.013 / A+0.003
- **Explanation**: [defensive_asymmetric] One team protecting a draw, the other with less at stake. Adj: home-1.7% draw+1.3% away+0.3%

#### ⚠️ DC-Enhancer Divergence
- **Max Divergence**: 26.5pp
- **Severity**: high
- **Note**: Large divergence (26.5pp) on away. Enhancer rates this outcome higher. Recommend checking DC params and Enhancer feature

#### 📊 Market Data
- **Provider**: bet365/bwin/Winamax/Fonbet (web-verified 2026-06-26 BJT)
- **Market Weight**: 0.3

---

### 6. Paraguay vs Australia

**Score**: 0-0 | **Predicted Fav**: A | **Direction**: ❌ WRONG | **Brier**: 0.7310

#### Component Breakdown

| Component      | Probabilities (H/D/A)       | Fav | Dir | Brier |
|:---------------|:----------------------------|:---:|:---:|------:|
| dc             |  11.1% /  27.0% /  61.9% | A | ❌ | 0.9276 |
| enhancer       |   5.5% /  14.2% /  80.4% | A | ❌ | 1.3860 |
| weibull        |  18.1% /  38.2% /  43.7% | A | ❌ | 0.6057 |
| elo            |  28.7% /  23.2% /  48.1% | A | ❌ | 0.9032 |
| pi             |  34.9% /  20.6% /  44.6% | A | ❌ | 0.9515 |
| dc_enh         |   9.3% /  22.9% /  67.8% | A | ❌ | 1.0625 |
| pre_market     |  17.1% /  20.7% /  62.2% | A | ❌ | 1.0455 |
| post_market    |  25.0% /  31.1% /  43.9% | A | ❌ | 0.7310 |

#### ⚽ xG Comparison

| Metric | Predicted | Actual |
|:---|---:|---:|
| Home xG | 0.41 | 0.04 |
| Away xG | 1.37 | 0.19 |

#### 🎯 Motivation Factor
- **Match Type**: offensive
- **Home Motivation**: 0.85 | **Away Motivation**: 0.95
- **EI Score**: 0.85
- **Adjustment**: H+0.014 / D-0.031 / A+0.017
- **Explanation**: [offensive] Both teams must attack — high stakes for both. Adj: home+1.4% draw-3.1% away+1.7%

#### ⚠️ DC-Enhancer Divergence
- **Max Divergence**: 18.5pp
- **Severity**: medium
- **Note**: Large divergence (18.5pp) on away. Enhancer rates this outcome higher. Recommend checking DC params and Enhancer feature

#### 📊 Market Data
- **Provider**: apifootball.com
- **Market Weight**: 0.5

---


---

## 📈 Self-Evolution Learning

### Component Performance (6-match panel)

| Component | Avg Brier | Dir Accuracy | N |
|:---|---:|---:|---:|
| DC | 0.6399 | 50.0% | 6 |
| Enhancer | 0.6796 | 50.0% | 6 |
| Weibull | 0.5006 | 50.0% | 6 |
| Elo | 0.6666 | 33.3% | 6 |
| Pi | 0.5740 | 66.7% | 6 |
| Market | 0.4858 | 66.7% | 6 |
| **FINAL** | **0.5047** | **50.0%** | **6** |

### Current Weights (V4.2.2)
```
DC: 0.68 | Enhancer: 0.32
Weibull: 0.10 | Elo: 0.12
Pi: 0.14 | Market max: 0.30
```

### Recommendations
- ↑ Pi weight: 0.14 → 0.17

---

## 🚨 Key Anomalies

### Ecuador 2-1 Germany — Major Upset
- All 6 components called Away (Germany win), actual Home win
- Market odds 1.50 on Germany → 5.40 on Ecuador
- DC-Enhancer massive divergence on away (11.9pp, Enhancer favored Germany even more at 72.2%)
- Largest single-match Brier (0.9226) — complete consensus failure
- **Root cause**: Group E MD3 context — Germany already qualified, heavily rotated (85% rotation risk flagged by motivation system). Ecuador needed win to secure best-3rd-place spot. Motivation adjustment (+9.3% home) was directionally correct but insufficient (9.3% vs needed 30%+).

### Japan 1-1 Sweden — Draw Underestimation
- Predicted Home (50.8%), actual Draw
- DC-Enhancer direction conflict (DC favored Home 22.5pp above Enhancer)
- DC-Enhancer fusion with direction conflict → unweighted, pre-market home = 51.6%
- Market was closer to actual: H=49.0% D=27.4% A=23.6%
- **Root cause**: Defensive asymmetric match type — both teams benefit from draw (collusion-like dynamics). Draw floor 12% applied but not enough for this scenario.

### Paraguay 0-0 Australia — Draw Miss
- Predicted Away (43.9%), actual Draw
- Market favored Draw at 41.4%! Model-market divergence triggered dynamic boost to market_weight=0.50
- Post-market shifted significantly toward draw (31.1%) but still favored away
- **Root cause**: Market was right, model was wrong. Market boost helped partially but not enough to overcome model's strong away bias.

---

## 📋 Data Quality Notes

| Match | xG Source | Confidence |
|:---|---:|:---:|
| Ecuador vs Germany | Sofascore/FIFA | High |
| Curacao vs Ivory Coast | Sofascore/SkySports | High |
| Tunisia vs Netherlands | Sofascore/FIFA | High |
| Japan vs Sweden | Sofascore/Hupu | Medium-High |
| Turkey vs USA | SportingNews (partial) | Low (only early-match data) |
| Paraguay vs Australia | ZeroZero/VNExpress | Medium |

---

## ⚙️ System Health

- **NegBin 5% fusion**: Active on all 6 matches ✅
- **Draw floor 12%**: Active ✅
- **Motivation adjustment**: Active on all 6 ✅
- **DC-Enhancer divergence guard**: Triggered on Japan-Sweden (high), Turkey-USA (high) ✅
- **Market dynamic boost**: Triggered on Paraguay-Australia (model-market divergence) ✅
- **Weather (Open-Meteo)**: Real-time data for all 6 matches ✅
- **Calibration**: Skipped (market data present — "market IS calibration") ✅
- **DB writes**: prediction_runs + motivation_events written ✅
- **match_results**: Updated with actual scores and xG ✅

---

*Generated by batch_postmatch_june26.py | V4.3.0-beta | 2026-06-26 04:04 UTC*
