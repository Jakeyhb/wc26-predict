# Changelog

## V2.9 — Conservative: Brier 标准化 + 保守权重 + Phase 0 审计修复 (2026-06-08)

Focus:

- **Brier Score 标准化** — 移除错误的三路 `/3` 除法，重校评级阈值
- **保守权重回滚** — V2.8 BEL-TUN 单场过拟合权重回退为 FRIENDLY_ADJUSTED_V4
- **版本统一** — 3 处硬编码版本号全部改为读取 `app.version.VERSION`
- **静默异常消除** — 12 处 `except: pass` 替换为 `logger.warning(exc_info=True)`
- **Shin 公式修复** — 市场概率计算从错误线性近似改为 Shin (1993) 正确公式
- **asyncio 安全性** — 盘点所有 `asyncio.run()` 调用点，修复事件循环冲突
- **预测入口盘点** — 17 个预测入口点文档化，9 种权重组装方式分析
- **Pipeline contract 强化** — 结构化 `degraded_reasons` 契约 + 测试覆盖

Files:

- MOD: `backend/app/services/weights.py` (FRIENDLY_ADJUSTED_V4)
- MOD: `backend/app/services/market/probability.py` (Shin formula)
- MOD: `backend/app/services/prediction_result.py` (DegradedReason)
- MOD: `backend/app/services/prediction_pipeline.py` (degraded_reasons contract)
- MOD: `backend/app/version.py` (2.9.0-conservative)
- MOD: `backend/app/main.py`, `backend/app/services/snapshot_store.py` (version de-hardcode)
- MOD: `backend/app/services/dixon_coles.py`, `postmatch.py`, `learning_engine.py` (Brier fix)
- NEW: `backend/tests/test_shin_formula.py`, `test_asyncio_safety.py`
- NEW: `docs/PREDICTION_ENTRYPOINT_INVENTORY.md`, `docs/ASYNCIO_RUN_INVENTORY.md`
- NEW: `scripts/run_checks.ps1`
- MOD: `docs/CURRENT_STATUS.md`

Notes:

- 146 tests passing (V2.6: 118)
- Branch: `phase-0-baseline` → PR #1 (pending merge to master)

---

## V2.8 — BEL-TUN Single-Match Adaptation (2026-06-06)

Focus:

- Belgium vs Tunisia 友谊赛复盘驱动单场权重微调
- Enhancer 降幅 ×0.42, Elo 增幅 ×12.0
- **注意**: 这些权重已在 V2.9 回滚 — 单场过拟合风险过高

---

## V2.7 — Friendly Self-Evolution (2026-06-06)

Focus:

- 3 场友谊赛赛后数据驱动 FRIENDLY 权重自动调整
- Enhancer 在友谊赛中正确率远高于 DC/Elo/Pi
- 权重调整: Enhancer 39.6% → 57.1%

---

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
