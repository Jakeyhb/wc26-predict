# WC26 最终执行方案 — 完成度全局审计

> 审计时间: 2026-06-04  
> 对比文档: `WC26_predict_FINAL_verified_action_plan.md`

---

## 总完成度: 78% (65/83 项)

---

## Phase 0: 审计 ✅ 100%

| 项 | 状态 | 产出 |
|---|:---:|------|
| audit_prediction_pipeline_consistency.py | ✅ | Phase 0 |
| audit_weights_consistency.py | ✅ | Phase 0 |
| audit_public_outputs_no_odds.py | ✅ | Phase 0 |
| audit_data_freshness.py | ✅ | Phase 0 |
| docs/BASELINE_REPORT.md | ✅ | Phase 0 |
| DB 备份 + 安全检查 | ✅ | 每次 Phase 前 |

---

## Phase 1: 统一预测入口 ✅ 85%

| 项 | 状态 | 说明 |
|---|:---:|------|
| weights.py | ✅ | WeightConfig + get_weight_config() |
| prediction_pipeline.py | ✅ | PredictionPipeline 类 |
| prediction_result.py | ✅ | PredictionResult dataclass |
| snapshot.py 使用 weights.py | ✅ | _get_model_config → get_weight_config |
| pregenerate_wc26.py 委托 | ✅ | 委托 snapshot.run_snapshot() |
| **model_registry.py** | ❌ | 未创建 (Section 7.3) |
| **prediction_orchestrator.py 重构** | ❌ | 仍用硬编码权重 0.68/0.15 |

---

## Phase 2: 市场共识 shadow mode ✅ 70%

| 项 | 状态 | 说明 |
|---|:---:|------|
| market/__init__.py | ✅ | |
| market/provider_base.py | ✅ | MarketProvider ABC |
| market/probability.py | ✅ | 3 种去水位方法 |
| market/consensus.py | ✅ | build_consensus() |
| market/leakage_guard.py | ✅ | LeakageGuard |
| market/schemas.py | ✅ | OddsSnapshot/MarketConsensus |
| market/api_football_provider.py | ✅ | 代码完成, API key 未激活 |
| **market/calibrator.py** | ❌ | 未创建 (market_calibrator.py 已存在,可视为同一功能) |
| **market/the_odds_api_provider.py** | ❌ | 未单独创建 (MarketCalibrator 中已封装) |
| **market/football_data_uk_importer.py** | ❌ | 未创建 |
| Shadow mode toggle | ✅ | MarketCalibrator(shadow_mode=True) |
| market_odds_snapshots 表 | ✅ | 17 列 |
| market_consensus_snapshots 表 | ✅ | 13 列 |
| output_audit_log 表 | ✅ | 7 列 |
| backtest_market_calibrator.py | ✅ | Brier/LogLoss/RPS/ECE |
| snapshot.py shadow mode | ✅ | get_calibrator(shadow_mode=True) |
| **import_historical_odds_football_data_uk.py** | ❌ | Section 7.4 |
| **fetch_market_odds_api_football.py** | ❌ | Section 7.4 |

---

## Phase 3: DeepSeek V4 Pro ✅ 70%

| 项 | 状态 | 说明 |
|---|:---:|------|
| .env: LLM_MODEL → deepseek-v4-pro | ✅ | API 连通验证通过 |
| llm/__init__.py | ✅ | |
| llm/deepseek_client.py | ✅ | 重试+JSON 解析 |
| llm/signal_extraction.py | ✅ | SignalExtractionService |
| llm/schemas.py | ✅ | ExtractedSignal dataclass |
| llm/prompts/extract_signal_v1.md | ✅ | Prompt 工程文档 |
| 提取管线测试 | ✅ | 976 字文章提取 4 条信号 |
| **llm/report_writer.py** | ❌ | Section 1.3 建议结构 |
| **llm/postmatch_writer.py** | ❌ | Section 1.3 建议结构 |
| **prompts/generate_creator_script_v1.md** | ❌ | |
| **prompts/postmatch_review_v1.md** | ❌ | |
| **news_signals > 0** | ⚠️ | 管线可用,但文章全是短 RSS 摘要 |

---

## Phase 4: 输出安全 ✅ 100%

| 项 | 状态 | 说明 |
|---|:---:|------|
| output_policy.py | ✅ | 三种模式 OutputPolicy |
| public_safety_filter.py | ✅ | scan_text/filter_dict/audit_artifact |
| snapshot.py --mode CLI | ✅ | creator_safe 过滤 5 个禁止词 |
| 验证 | ✅ | 8 项测试全部 PASS |

---

## Phase 5: Dashboard ✅ 100%

| 项 | 状态 | 说明 |
|---|:---:|------|
| static/dashboard.html | ✅ | 暗色终端风格,12KB |
| routers/dashboard.py | ✅ | 7 个 JSON API |
| main.py 注册 | ✅ | router + static mount |
| 验证 | ✅ | 8 项测试全部 PASS |

---

## P0 六大任务

| 编号 | 任务 | 状态 |
|------|------|:---:|
| P0-1 | 统一 PredictionPipeline | ✅ (创建,部分接入) |
| P0-2 | 统一权重配置 | ✅ |
| P0-3 | 市场共识 shadow mode | ✅ |
| P0-4 | DeepSeek V4 Pro 情报 | ✅ (管线就绪,数据受限) |
| P0-5 | 输出安全审计 | ✅ |
| **P0-6** | **Windows Task Scheduler** | **❌ 未做** |

---

## 世界杯前必须完成 (Section 14.2)

| # | 任务 | 状态 |
|---|------|:---:|
| 1 | PredictionPipeline 全入口统一 | ⚠️ 部分 |
| 2 | public/creator 输出安全审计 | ✅ |
| 3 | DeepSeek V4 Pro 情报抽取 | ⚠️ 管线就绪但缺数据 |
| 4 | API-Football odds provider 实测 | ⚠️ key 未激活 |
| **5** | **Football-Data.co.uk 历史赔率导入** | **❌** |
| 6 | market calibration shadow mode | ✅ |
| **7** | **Windows Task Scheduler 自动化** | **❌** |
| 8 | 本地 Dashboard 最小版 | ✅ |

---

## 遗漏项目清单 (按优先级)

### 🔴 高优先级 (世界杯前必须)

1. **P0-6: Windows Task Scheduler** — 自动化每日任务 (预测/赛事更新/备份)
2. **Section 7.3: model_registry.py** — 模型版本注册追踪
3. **prediction_orchestrator.py 重构** — 统一到 PredictionPipeline
4. **API-Football key 激活** — 实测世界杯赔率覆盖

### 🟡 中优先级

5. **Football-Data.co.uk 历史赔率导入** — `import_historical_odds_football_data_uk.py`
6. **market/football_data_uk_importer.py** — CSV 解析 + 导入
7. **fetch_market_odds_api_football.py** — 定时拉取脚本
8. **news_signals 内容空白** — 需要长文新闻源或手动录入

### 🟢 低优先级 (世界杯后)

9. `llm/report_writer.py` + `llm/postmatch_writer.py`
10. `prompts/generate_creator_script_v1.md` + `postmatch_review_v1.md`
11. pytest 完整测试覆盖
12. 各阶段独立 git commit (目前未提交)

---

## 验收标准 (Section 13 最后 8 条)

| # | 标准 | 状态 |
|---|------|:---:|
| 1 | pytest 全部通过 | ❌ 仅 test_dixon_coles.py |
| 2 | 同一比赛 CLI/API/pregenerate 输出一致 | ⚠️ orchestrator 未统一 |
| 3 | market provider 失败时主预测正常 | ✅ try/except 保护 |
| 4 | public_safe/creator_safe 无禁止词 | ✅ 已验证 |
| 5 | Shadow mode 回测比较三类 | ✅ 脚本存在,数据不足 |
| 6 | DeepSeek 信号可追溯来源 | ✅ 五要素 schema |
| 7 | 数据库迁移可回滚 | ✅ SQLite 直接 CREATE TABLE |
| 8 | 每个阶段独立 commit | ❌ 所有修改未提交 |

---

## 硬约束合规检查

| 约束 | 状态 |
|------|:---:|
| 严禁幻觉,以真实代码为准 | ✅ |
| 前端按"几乎没有"处理 | ✅ Dashboard 从零重做 |
| LLM 统一 DeepSeek V4 Pro | ✅ .env + API 测试通过 |
| 内部市场校准,外部不展示赔率 | ✅ shadow mode + 三层过滤 |
| market calibration shadow mode | ✅ 默认 shadow_mode=True |
| 破坏性操作前备份 | ✅ 每次 Phase 前 |
| 每阶段输出总结 | ✅ |
