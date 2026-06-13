# Changelog

## V3.6.0 Data Provenance — 数据覆盖与来源审计基线 (2026-06-13)

Focus:

- **V3.6 数据补强先验门** — 新增只读 `audit_data_provenance.py`，在接入新数据前先审计真实 xG、赔率、赛前快照、伤停、阵容、情报信号的覆盖与来源
- **真实 xG 覆盖门** — 将 `match_results.home_xg/away_xg` 覆盖不足标为 critical，避免把进球 fallback 误当真实 xG 学习
- **赔率 provenance 门** — 区分 active 未绑定赔率和已 quarantine 的 legacy 赔率；active 未绑定赔率继续阻断，legacy 隔离不伪装成 benchmark 覆盖
- **赛前状态 provenance** — 审计 `pre_match_snapshots` 的 availability flags、payload、`source_timestamps` 和 snapshot id，缺失先标 warning
- **阵容/伤停/情报信号覆盖** — 审计 `lineup_probe_logs`、`lineup_available`、`injuries.json` 的 source / last_updated，以及 manual/news signal 表
- **测试覆盖** — 新增数据 provenance 单元测试：低 xG 覆盖、未绑定赔率、隔离旧赔率、缺 source timestamp、最小可追溯样例
- **版本同步** — README、CURRENT_STATUS、version.py 更新为 V3.6.0

Notes:

- 本版仍不接入新的 xG / 阵容 / 伤停 / 赔率 API。
- 本版不改模型权重，不发布 champion，不宣称预测更准。
- `audit_data_provenance.py` 对当前本地库预期会失败，核心 blocker 仍是真实 xG 覆盖不足。
- 下一步是 V3.6.1：优先补真实 xG / 射门 / 射正 / 红黄牌等可追溯赛后统计，并记录 `source_time` / `available_at`。

---

## V3.5.4 Pipeline Eval Samples — PredictionPipeline 同源评估样本 (2026-06-13)

Focus:

- **统一评估样本** — `PredictionResult.to_dict()` 输出顶层 `evaluation_sample`
- **同源候选概率** — evaluation sample 固定记录 current fusion、snapshot adjusted/baseline、DC、tabular、Elo、Pi、Weibull、market、uniform 的可用状态
- **持久化边界统一** — `prediction_snapshots.pipeline_params.evaluation_sample` 与 `prediction_runs.input_feature_snapshot.evaluation_sample` 写入同一份样本
- **market 保存修复** — market 只有完整 `{home, draw, away}` 三路概率时才进入评估，避免单字段伪样本
- **回测优先读取新样本** — walk-forward 报告优先使用 pipeline evaluation sample，没有时 fallback 到 V3.5.3 legacy 字段
- **安全回填脚本** — 新增 dry-run 默认的 `backfill_evaluation_samples.py`，只使用同一行已有数据构造样本
- **版本同步** — README、CURRENT_STATUS、version.py 更新为 V3.5.4

Notes:

- 本版不接入真实 xG / 阵容 / 伤停 / 新赔率源。
- 本版不改模型权重，不发布 champion，不宣称预测更准。
- 回填脚本默认不写库；`--apply` 会先备份本地 SQLite。
- 下一步是 V3.6 数据补强：真实 xG、阵容、伤停、赔率快照、天气与休息旅途数据。

---

## V3.5.3 Paired Benchmark — 同样本配对回测门 (2026-06-13)

Focus:

- **配对评估层** — `walk_forward_backtest.py` 现在把每条预测保存为同一条 evaluation example，只在同一场、同一预测时点、同一条样本内比较候选与基线
- **paired gate** — 新增 `--enforce-paired-gate`，默认检验 `snapshot_adjusted` vs `uniform_baseline`
- **样本不足显式标记** — `market_only`、`weibull_only` 等无足够配对样本时输出 `insufficient_samples`，不伪造通过/失败结论
- **非配对榜单隔离** — V3.5.2 的 `current_fusion` gate 保留；leaderboard 明确标记为 exploratory / unpaired
- **结构化报告扩展** — JSON 新增 `paired.cohorts`、`paired.comparisons`、`paired.gate`、`paired.insufficient_baselines`
- **测试覆盖** — 新增同样本配对、缺失候选/基线、输给 uniform、非配对假优势、样本不足等 paired benchmark 单元测试
- **版本同步** — README、CURRENT_STATUS、version.py 更新为 V3.5.3

Notes:

- 当前 `current_fusion` production gate 仍然 FAIL，不能上线新权重。
- 当前 paired gate 也 FAIL：`snapshot_adjusted` 在配对样本上整体优于 `uniform_baseline`，但存在关键分组退化。
- 当前 paired comparison 显示 `snapshot_adjusted` 没有超过 `dc_only`，所以不能把“更准”作为结论。
- 结论：V3.5.3 只提升评估可信度，不改变线上权重，不宣称预测精度提升。

---

## V3.5.2 Champion Gate — walk-forward 发布门 (2026-06-13)

Focus:

- **正式发布门** — `walk_forward_backtest.py` 输出 champion/challenger gate decision
- **结构化报告** — 每次回测生成 JSON + Markdown 报告到 ignored `backend/reports/`
- **强制门禁** — 新增 `--enforce-gate`，当前 champion 不合格时返回非零
- **分组退化检查** — 按 horizon、competition、run_type 对比 `current_fusion` vs `uniform_baseline`
- **基线对比** — leaderboard 覆盖 uniform、DC、Elo、Pi、tabular、market、Weibull 可用样本
- **版本同步** — README、CURRENT_STATUS、version.py 更新为 V3.5.2

Notes:

- 当前 gate 结果：FAIL
- 失败原因：`current_fusion` 不是 log loss leader，且 log loss / Brier 未超过 `uniform_baseline`
- 当前 leader：`dc_only`（非配对 benchmark，仍需 Phase 1B 做 paired/out-of-fold 对比）
- 结论：发布门已落地，但不能上线新权重；下一步是数据补强与配对回测

---

## V3.5.1 闭环追溯修复版 — resolution ledger + legacy 隔离 (2026-06-13)

Focus:

- **Resolution ledger** — 新增 `closed_loop_resolution_ledger`，记录旧数据能否安全绑定到 `match_id` / `prediction_run_id`
- **Backfill 扩展** — `backfill_match_ids.py` 覆盖 `prediction_snapshots`、`pre_match_snapshots`、`prediction_learning_log`、`postmatch_eval`、`market_odds`
- **Legacy 隔离** — 无法唯一解析的旧快照/旧赔率不再阻塞 active 闭环，但明确标记为 `unresolvable_legacy` / `ambiguous`
- **Postmatch 修复** — 修复 1 条 `postmatch_eval` 的旧伪 `prediction_run_id`，闭环审计达到 `48/48` traceable
- **未来赔率止血** — `scripts/snapshot.py` 保存 `market_odds` 时写入真实 `match_id`
- **审计口径升级** — 审计脚本区分 active 缺口、total 缺口和 quarantined legacy

Files:

- NEW: `backend/app/models/closed_loop_resolution.py`
- NEW: `backend/app/services/closed_loop_resolution.py`
- NEW: `backend/alembic/versions/a8b9c0d1e2f3_add_closed_loop_resolution_ledger.py`
- MOD: `backend/scripts/backfill_match_ids.py`, `audit_closed_loop_integrity.py`, `audit_data_freshness.py`, `snapshot.py`
- NEW/MOD: `backend/tests/test_closed_loop_resolution.py`, `test_backfill_match_ids.py`
- MOD: `backend/app/version.py`, `README.md`, `docs/CURRENT_STATUS.md`

Notes:

- Local DB backfill applied after backup: `local_stage2_pre_v351_closed_loop_20260613_082356.db`
- Closed-loop audit after apply: active missing snapshot/learning/odds defects = 0, `postmatch_eval_traceable=48/48`
- Remaining blocker: real xG coverage is still only `62/16691`

---

## V3.5测试版 gpt5.5 — 闭环门禁 + 数据绑定 + 回测基线 + 仓库清理 (2026-06-13)

Focus:

- **独立赛果验证** — `user_provided` 只做人工备注，不再和单一来源组成自动学习 consensus
- **快照契约收紧** — 标准化 prediction snapshot 字段；无真实 `match_id` 不进入复盘和学习
- **match resolver / backfill** — 新增保守比赛解析器和历史快照回填脚本
- **proper scoring 指标** — 新增 log loss、Brier、RPS 统一评估工具
- **walk-forward scaffold** — 支持 current fusion、DC、Elo、Pi、Weibull、tabular、market、uniform baseline 对比
- **闭环审计** — 新增 closed-loop integrity audit，暴露快照、赔率、学习日志的可追溯缺口
- **WC26 绑定** — 小组赛 72/72 场已绑定内部 team id；淘汰赛保持动态 TBD
- **仓库大扫除** — 删除可再生成缓存、依赖目录、构建产物和重复旧库；非核心素材归档到 `_archive/`
- **README 重写** — GitHub 首页改为 V3.5 测试版状态，明确当前不是完整闭环/自进化系统

Files:

- MOD: `backend/app/version.py` (3.5.0-test-gpt5.5)
- MOD: `backend/app/services/result_verification.py`, `snapshot_store.py`, `snapshot_service.py`, `learning_engine.py`, `prediction_result.py`
- NEW: `backend/app/services/evaluation_metrics.py`, `match_resolver.py`
- NEW: `backend/scripts/audit_closed_loop_integrity.py`, `backfill_match_ids.py`, `bind_wc26_group_slots.py`, `walk_forward_backtest.py`
- MOD: `backend/scripts/audit_data_freshness.py`
- NEW: `backend/tests/test_evaluation_metrics.py`, `test_match_resolver.py`, `test_snapshot_store_contract.py`
- MOD: `apps/web/src/lib/api.ts`
- MOD: `README.md`, `docs/CURRENT_STATUS.md`, `scripts/start_dashboard.ps1`

Notes:

- Backend validation before dependency cleanup: 184 passed
- Frontend production build before dependency cleanup: passed
- Local dependency directories are intentionally not committed; run `pip install -r backend/requirements.txt` and `npm ci` after clone
- Remaining data debt is explicit: legacy snapshots without `match_id`, sparse odds binding, and incomplete xG provenance

---

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
