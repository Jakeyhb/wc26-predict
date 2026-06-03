# WC26 Predict — Project Overview

> **⚠ This document may be outdated (V1.6.1).** See [`CURRENT_STATUS.md`](CURRENT_STATUS.md) for the authoritative current state.

WC26 Predict is an AI football research engine and creator workspace for World Cup 2026 analysis.

It combines football data, statistical models, AI-assisted signal extraction, model evaluation, post-match learning, and public-output safety controls into a single research workflow.

---

## 1. Product positioning

### Public positioning

WC26 Predict is:

- an AI football research system
- a World Cup 2026 analysis workspace
- a creator-facing football data assistant
- a model evaluation and post-match review tool
- a data provenance and reporting pipeline

WC26 Predict is not:

- a betting system
- a gambling product
- a bookmaker tool
- an odds promotion platform
- a guaranteed prediction product
- a "hit-rate" marketing system

---

## 2. Target users

### 2.1 Football content creators

They need structured match background, team context, rankings, data points, and safe talking points before recording videos or writing posts.

### 2.2 Football analysts and hobby researchers

They need reproducible model outputs, transparent assumptions, post-match evaluation, and historical comparison.

### 2.3 AI builders

They need a real-world example of using AI coding tools to build a domain-specific analytics system with data pipelines, evaluation, and operational workflows.

---

## 3. Core system modules

### PredictionPipeline

The unified orchestration layer for match analysis.

Responsibilities:

- resolve match/team inputs
- build model features
- call model layers
- apply signal/context adjustments
- generate snapshots
- enforce output mode boundaries

### ModelRegistry

Central location for model identity, versioning, enable/disable status, and reproducibility metadata.

### Weight configuration

Centralized model weights by competition and scenario, instead of scattered hard-coded fusion logic.

### Market consensus shadow mode

Internal-only calibration research layer. It can compare model probabilities with market consensus internally, but public reports must never show odds, bookmakers, or betting-oriented language.

### News and signal pipeline

Source-based signal ingestion layer for injuries, lineups, tactical changes, schedule pressure, and other context.

### OutputPolicy

Safety layer that separates:

- internal research output
- creator-safe output
- public-safe output

---

## 4. Data sources

The project may use:

- historical football results
- public football datasets
- public weather data
- RSS/news sources
- manually verified signals
- internal-only market consensus data for calibration research

All source-dependent signals should retain source URL, title, timestamp, extracted snippet, and confidence level where possible.

---

## 5. Output philosophy

WC26 Predict should explain uncertainty instead of pretending certainty.

Good output:

- "The model sees this as a balanced matchup."
- "Recent form and travel context increase uncertainty."
- "The public-safe report hides internal probability and market-consensus fields."

Bad output:

- "Guaranteed win."
- "Best bet."
- "High hit-rate pick."
- "Follow this score prediction."

---

## 6. Current milestone

Current milestone: V1.6.1 test version.

P0 closure focus:

- unified pipeline
- model registry
- market data in shadow mode
- signal pipeline
- output safety
- local dashboard
- automation scripts

Final status must always be verified by local test results and `docs/COMPLETION_AUDIT.md`.
