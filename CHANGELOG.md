# Changelog

## V1.7 — Provider Fix + Quality Gates + Signal Pilot

Focus:

- apifootball.com market provider (separate from API-Sports)
- multi-provider selection logic in market_calibrator
- weight configuration audit rewrite (dynamic detection)
- output safety audit with compliance-context awareness
- P0 quality gates enforcement (weights, output safety, tests/CI)
- 5-article signal extraction pilot (DeepSeek V4 Pro)
- market data provider diagnostic script
- GitHub Actions CI (compileall + pytest + audits)
- DeepSeek V4 Pro config unification

Notes:

- apifootball.com basic API available; odds endpoint requires $15 addon.
- All 6 extracted signals remain PENDING with enters_model=false.
- 30/33 tests passing; 3 Dixon-Coles tests need method signature updates.
- `penaltyblog` package pending addition to requirements.txt.

## V1.6.1 — P0 Closure Test Version

Focus:

- unified prediction entry flow
- model registry
- market data research pipeline
- signal pipeline
- automation workflow
- public-output safety boundary
- repository cleanup

Notes:

- Market consensus calibration remains internal-only and shadow-mode oriented.
- Public outputs must not expose odds, bookmakers, or betting-oriented language.
- Commercialization should focus on football research and creator workflows.

## V1.6 — System Refactor Test Version

Focus:

- unified prediction entrance
- market consensus shadow mode
- news/signal pipeline
- output safety filter
- local dashboard

## V1.5 — Performance Test Version

Focus:

- Dixon-Coles performance optimization
- disk cache
- pre-generation workflow
- faster snapshot generation
