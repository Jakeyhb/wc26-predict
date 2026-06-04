# Changelog

## V2.6 — Enhanced: 实时数据 + LLM 分析 (2026-06-05)

Focus:

- **打破 V2.5 冻结** — 接通已实现的 70% 后端代码
- **prediction_enhanced.py** — 新编排层，包装 artifact 管线 + 实时数据源
- **市场赔率接入** — 同步封装 apifootball.com + The Odds API，15% 混合权重
- **实时天气** — Open-Meteo 免费 API，13 个 WC26 场馆 + 智能猜测
- **DeepSeek V4 Pro 内容生成** — 赛前分析 + 视频口播脚本 + 多平台社交媒体文案
- **Dashboard 升级** — 增强模式开关、市场对比面板、天气展示、AI 分析卡片
- **Creator Mode 重写** — 从模板到 AI 实时生成，保留模板回退
- **优雅降级架构** — 任何数据源不可用自动回退，不阻断基础预测

Files:

- NEW: `backend/app/services/prediction_enhanced.py`
- NEW: `backend/app/services/market/sync_provider.py`
- NEW: `backend/app/services/llm/analysis_prompts.py`
- MOD: `backend/app/services/weather_service.py` (sync wrapper)
- MOD: `backend/dashboard/pages/02_Match_Prediction.py`
- MOD: `backend/dashboard/pages/03_Match_Context.py`
- MOD: `backend/dashboard/pages/08_Creator_Mode.py`
- MOD: `backend/app/version.py` → 2.6.0-enhanced
- MOD: `docs/CURRENT_STATUS.md`
- MOD: `docs/ARCHITECTURE_GUARDRAILS.md`

Notes:

- 118/118 tests passing, 0 regressions
- apifootball.com odds unavailable for friendly matches (expected — graceful degradation verified)
- DeepSeek content generation: ~30s per content type, ~2K tokens total
- Total enhanced prediction: ~90s (dominated by 3 LLM calls)

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
