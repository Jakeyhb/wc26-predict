"""Match statistics services — data providers, normalizers, process evaluators.

Package structure:
  provider_base.py       — Abstract base classes (MatchStatsProvider, RawMatchStats, TeamMatchStats)
  fbref_provider.py      — FBref data via soccerdata library
  normalizer.py          — Field alias resolution
  quality.py             — Data quality scoring
  process_evaluator.py   — Predicted vs actual xG comparison
  failure_classifier.py  — Failure taxonomy + learning weight assignment
"""
