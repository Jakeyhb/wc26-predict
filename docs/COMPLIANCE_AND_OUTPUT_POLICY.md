# WC26 Predict — Compliance and Output Policy

WC26 Predict must maintain a strict boundary between internal research and public-facing content.

---

## 1. Core rule

WC26 Predict is a football research system, not a gambling product.

The system may run internal model evaluation and calibration research, but public output must never become betting advice, odds promotion, or gambling content.

---

## 2. Output modes

### 2.1 internal_research

Allowed:

- model probabilities
- calibration diagnostics
- Brier score / RPS / log loss
- internal market consensus comparison
- feature importance notes
- raw debugging information

Not allowed:

- public marketing claims
- betting advice
- bookmaker promotion

### 2.2 creator_safe

Allowed:

- team context
- form summaries
- historical comparisons
- uncertainty notes
- safe talking points
- data source references

Not allowed:

- odds
- bookmaker names
- betting language
- "pick" or "best bet" phrasing
- hit-rate claims

### 2.3 public_safe

Allowed:

- educational football analysis
- rankings
- historical trends
- schedule context
- public-safe charts
- explainable uncertainty

Not allowed:

- raw probabilities if they are framed as betting/prediction claims
- score guarantees
- odds
- bookmakers
- betting-related calls to action
- gambling terms

---

## 3. Forbidden public terms

Public-facing pages, reports, README marketing sections, and social content should avoid:

```text
投注
博彩
盘口
赔率推荐
竞彩
带单
命中率
稳赚
爆单
必胜
推单
best bet
betting tips
bookmaker
sportsbook
odds pick
guaranteed prediction
sure win
```

Technical docs may mention these terms only when describing compliance restrictions.

---

## 4. Market consensus data policy

Market consensus data can be used only as an internal research signal.

Allowed internal uses:

- compare model probability with market consensus
- estimate calibration gaps
- run shadow-mode evaluation
- study uncertainty

Forbidden public uses:

- display bookmaker names
- display odds tables
- encourage betting
- monetize betting signals
- imply profitable betting recommendations

---

## 5. Safe report language

Recommended wording:

- "model-based analysis"
- "uncertainty remains high"
- "historical data suggests"
- "the system currently rates this matchup as balanced"
- "creator-safe summary"

Avoid:

- "guaranteed win"
- "best bet"
- "high hit-rate pick"
- "odds value"
- "bet this side"

---

## 6. Required checks before public release

Before publishing any report or demo:

```bash
cd backend
python scripts/audit_public_outputs_no_odds.py
```

Also manually inspect:

- README
- docs
- dashboard UI
- generated reports
- social media screenshots
- landing page copy

---

## 7. Disclaimer template

Use this disclaimer in public pages:

> WC26 Predict is an AI-assisted football research and analytics project. Outputs are uncertain and based on available data, model assumptions, and system configuration. They are provided for research, education, and content preparation only. They are not betting advice, financial advice, or guaranteed predictions.
