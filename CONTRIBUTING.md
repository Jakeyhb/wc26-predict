# Contributing to WC26 Predict

Thank you for your interest in contributing! This project is a football prediction research system focused on transparency, auditability, and reproducible evaluation.

## Contribution Areas

We welcome contributions in these directions:

- **Leak-free historical datasets** — building clean, timestamped match datasets for training and evaluation
- **Player-level modeling** — national-team player data, squad strength, availability modeling
- **Walk-forward benchmarks** — rigorous backtesting frameworks and calibration evaluation
- **Post-match error attribution** — automated analysis of prediction errors and component performance
- **Compliance & safe output** — policy enforcement, output filtering, public communication guidelines
- **Documentation** — improving docs, translations, examples

## Scope Boundaries

This is a **research project**, not a tipping service. Please do not submit:

- Betting advice, odds comparison, or gambling-related features
- Commercial promotions or referral links
- Real-money wagering integrations of any kind

See [`docs/COMPLIANCE_AND_OUTPUT_POLICY.md`](docs/COMPLIANCE_AND_OUTPUT_POLICY.md) for the full policy.

## Pull Request Process

1. **Open an issue first** for significant changes — discuss the approach before writing code
2. **Fork the repo** and create a feature branch from `master`
3. **Keep changes focused** — one PR should address one concern
4. **Add tests** — new functionality should include test coverage
5. **Run the full test suite** — `cd backend && python -m pytest tests/ -q`
6. **Update documentation** if your change affects user-facing behavior
7. **Use the PR template** — it includes a compliance checklist

## Code Standards

- Python 3.11+. Follow existing patterns in the codebase.
- Type hints are encouraged but not required everywhere.
- Log at appropriate levels — don't spam INFO, use WARNING/ERROR for real issues.
- Docstrings for public functions.
- Keep files under ~800 lines where possible; extract to new modules rather than growing existing ones.

## Development Setup

```bash
git clone https://github.com/AndyDu0921/wc26-predict.git
cd wc26-predict/backend
python -m venv .venv
source .venv/bin/activate  # or .\.venv\Scripts\Activate.ps1 on Windows
pip install -r requirements.txt
cp ../.env.example ../.env  # edit with your keys
python -m pytest tests/ -q  # verify everything works
```

## Architecture Notes

- `backend/app/core/engine.py` — pure fusion functions, zero IO. This is the single source of truth for the probability fusion chain. All prediction paths (CLI, API, Dashboard) should use these functions.
- `backend/app/services/prediction_pipeline.py` — the main PredictionPipeline class. Handles IO (DB, API calls) and delegates fusion math to engine.py.
- `backend/app/services/prediction_core.py` — model-loading helpers (disk cache, artifact loading).
- `backend/scripts/predict_match_full.py` — CLI entry point for full predictions.

## Questions?

Open an issue with the `question` label or use the Documentation template.

---

Thanks for contributing to transparent football prediction research.
