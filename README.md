# WC26 Predict

> AI football research engine and creator workspace for World Cup 2026 analysis.

WC26 Predict is an AI-assisted football research system built for World Cup 2026. It combines historical match data, statistical models, model evaluation, post-match learning, data provenance, and safe public-output controls into one reproducible research workflow.

It is designed for football analysts, creators, and builders who want to study matches with structured data instead of relying on isolated opinions.

> **Positioning:** football research, data analysis, content preparation, and model evaluation.  
> **Not positioning:** betting advice, gambling products, odds promotion, or guaranteed score prediction.

---

## What it does

WC26 Predict can generate match research reports from structured football data and model outputs.

Core capabilities:

- **Unified prediction pipeline** for match analysis and snapshot generation
- **Multi-model ensemble** including Dixon-Coles, tabular features, Elo, Pi-Rating, and optional extensions
- **Model registry and weight configuration** for reproducible model versions
- **Post-match evaluation loop** using scoring metrics such as Brier score and RPS
- **Internal-only market consensus shadow mode** for calibration research without public odds exposure
- **News and signal ingestion pipeline** for source-based context signals
- **Output safety policy** to separate internal research outputs from creator-safe and public-safe reports
- **Local dashboard workspace** for operations, review, and content preparation

---

## Why this project exists

The project started as a personal AI-coding experiment: one football fan using AI development tools to build a complete World Cup analysis system from scratch.

It has evolved into a structured football research engine with:

- historical match storage
- model-based match analysis
- automated snapshots
- post-match feedback
- calibration research
- data provenance
- public-output safety boundaries
- creator workflow support

The long-term goal is to turn WC26 Predict into a transparent, reproducible, and commercially usable football analytics workspace.

---

## System overview

```text
Data Sources
  ├─ football-data.org / football-data.co.uk
  ├─ openfootball
  ├─ StatsBomb Open Data
  ├─ Open-Meteo
  ├─ RSS / public news sources
  └─ Manual verified signals

Research Engine
  ├─ PredictionPipeline
  ├─ ModelRegistry
  ├─ Dixon-Coles model
  ├─ Tabular match enhancer
  ├─ Elo / Pi-Rating layers
  ├─ Signal and context adjustment
  ├─ Market consensus shadow calibration
  └─ Post-match learning and evaluation

Output Layer
  ├─ Internal research report
  ├─ Creator-safe report
  ├─ Public-safe report
  ├─ Markdown / JSON snapshots
  └─ Local dashboard
```

---

## Current status

Current public milestone: **V1.6.1 test version**

The current system is focused on P0 closure:

- unified prediction entry point
- centralized model registry
- market-data research pipeline in shadow mode
- source-based news/signal pipeline
- output-safety filtering
- local dashboard workflow
- automation scripts for recurring operations

See:

- [`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md)
- [`docs/COMPLETION_AUDIT.md`](docs/COMPLETION_AUDIT.md)
- [`docs/COMPLIANCE_AND_OUTPUT_POLICY.md`](docs/COMPLIANCE_AND_OUTPUT_POLICY.md)
- [`docs/COMMERCIAL_READINESS.md`](docs/COMMERCIAL_READINESS.md)

---

## Quick start

### 1. Clone the repository

```bash
git clone https://github.com/AndyDu0921/wc26-predict.git
cd wc26-predict
```

### 2. Install backend dependencies

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Configure environment variables

Copy the example env file and fill in your own keys.

```bash
cp ../.env.example ../.env
```

Required or optional variables depend on which modules you run. For LLM features, use DeepSeek official API settings:

```env
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-v4-pro
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=your_key_here
```

### 4. Run the API service

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 5. Generate a match snapshot

```bash
python scripts/snapshot.py --home "Brazil" --away "Argentina" --competition "FIFA World Cup 2026" --neutral
```

### 6. Run the local dashboard

```bash
cd ../apps/web
npm install
npm run dev
```

Then open:

```text
http://127.0.0.1:5173
```

---

## Repository structure

```text
wc26-predict/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── routers/
│   │   ├── models/
│   │   ├── schemas/
│   │   └── services/
│   │       ├── prediction_pipeline.py
│   │       ├── model_registry.py
│   │       ├── weights.py
│   │       ├── output_policy.py
│   │       ├── dixon_coles.py
│   │       ├── tabular_match_model.py
│   │       ├── elo_ratings.py
│   │       ├── pi_ratings.py
│   │       └── market / news / evaluation services
│   ├── scripts/
│   └── data/
├── apps/web/
│   └── local dashboard frontend
├── docs/
│   ├── PROJECT_OVERVIEW.md
│   ├── COMMERCIAL_READINESS.md
│   ├── COMPLIANCE_AND_OUTPUT_POLICY.md
│   └── COMPLETION_AUDIT.md
├── reports/
├── README.md
├── SECURITY.md
├── CONTRIBUTING.md
└── LICENSE
```

---

## Output modes

WC26 Predict separates internal research from public-facing content.

| Mode | Intended user | Can include | Must not include |
|---|---|---|---|
| `internal_research` | maintainer / analyst | model probabilities, calibration diagnostics, error metrics, internal market-consensus research | public marketing claims or betting advice |
| `creator_safe` | content creator | team context, form, data provenance, uncertainty notes, safe summaries | odds, bookmakers, betting language, gambling prompts |
| `public_safe` | public audience | educational analysis, historical context, rankings, explainable trends | odds, betting, bookmakers, guaranteed predictions, hit-rate marketing |

---

## Compliance boundary

WC26 Predict is not a gambling product.

The project does **not** provide:

- betting advice
- bookmaker promotion
- gambling recommendations
- odds display in public reports
- guaranteed score predictions
- paid betting signals
- "hit rate" marketing claims

Internal market-consensus calibration, if used, is strictly a research and evaluation layer. It must remain separated from public outputs.

See [`docs/COMPLIANCE_AND_OUTPUT_POLICY.md`](docs/COMPLIANCE_AND_OUTPUT_POLICY.md).

---

## Commercialization direction

WC26 Predict can support commercial use cases such as:

- football content creator workflow
- pre-match research assistant
- model evaluation and post-match review dashboard
- data provenance and report generation
- team / tournament monitoring workspace
- AI-assisted sports analysis education

It should not be commercialized as a betting product.

See [`docs/COMMERCIAL_READINESS.md`](docs/COMMERCIAL_READINESS.md).

---

## Development notes

Run backend tests:

```bash
cd backend
pytest
```

Run selected audit scripts:

```bash
python scripts/audit_weights_consistency.py
python scripts/audit_prediction_pipeline_consistency.py
python scripts/audit_public_outputs_no_odds.py
python scripts/audit_data_freshness.py
```

Run frontend:

```bash
cd apps/web
npm install
npm run dev
```

---

## Roadmap

Near-term priorities:

- keep all prediction entry points routed through `PredictionPipeline`
- maintain public-output safety filters
- keep completion audit up to date
- improve dashboard usability for creator workflows
- add reproducible demo datasets and screenshots
- prepare a public landing page and demo video

Mid-term priorities:

- API packaging
- hosted demo environment
- report template marketplace
- creator-facing workflow automation
- multilingual public-safe reports

---

## Disclaimer

WC26 Predict is an AI-assisted football research and analytics project. Outputs are based on available data, model assumptions, and system configuration. They are uncertain by nature and should not be treated as factual forecasts, financial advice, betting advice, or guaranteed outcomes.

Football is complex. Models can be wrong. Use the system for research, learning, and content preparation.

---

## License

MIT License. See [`LICENSE`](LICENSE).
