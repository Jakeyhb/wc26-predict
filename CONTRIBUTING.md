# Contributing to WC26 Predict

Thanks for your interest in WC26 Predict.

This project is currently maintained as an AI-assisted football research system and creator workspace for World Cup 2026 analysis.

---

## Project boundaries

Contributions should support:

- football analytics
- model evaluation
- data provenance
- public-safe report generation
- creator workflows
- reproducible research
- dashboard usability

Contributions should not turn the project into:

- a betting recommendation product
- a gambling affiliate funnel
- an odds promotion tool
- a paid-picks system

---

## Development setup

```bash
git clone https://github.com/AndyDu0921/wc26-predict.git
cd wc26-predict

cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS / Linux
pip install -r requirements.txt
```

Run tests:

```bash
pytest
```

Run audits:

```bash
python scripts/audit_prediction_pipeline_consistency.py
python scripts/audit_weights_consistency.py
python scripts/audit_public_outputs_no_odds.py
python scripts/audit_data_freshness.py
```

---

## Pull request checklist

Before submitting a PR:

- [ ] The change does not expose secrets or API keys.
- [ ] Public-facing output does not include odds, bookmakers, betting language, or gambling prompts.
- [ ] README/docs are updated if behavior changed.
- [ ] Relevant tests or audit scripts were run.
- [ ] New data sources include source notes and usage constraints.
- [ ] New model logic includes evaluation or clear assumptions.

---

## Documentation style

Use clear, verifiable language.

Prefer:

- "model-based analysis"
- "research output"
- "uncertainty"
- "evaluation metric"
- "source-based signal"

Avoid:

- "guaranteed prediction"
- "best bet"
- "hit rate"
- "sure win"
- "betting pick"

---

## License

By contributing, you agree that your contributions will be licensed under the project license.
