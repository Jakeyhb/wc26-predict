# 预测入口盘点

> 盘点日期: 2026-06-08 | Ticket: 1.1 | 状态: 只读分析，未修改代码
> 搜索范围: 全仓库 `backend/` `scripts/` `dashboard/` `apps/web/` `frontend/`
> 搜索模式: `rg "predict|prediction" --glob "*.py"`, `rg "FRIENDLY|weight|weights"`, `rg "@router|FastAPI"`, `rg "streamlit|dashboard"`

---

## 1. Summary

| 维度 | 数量 |
|------|------|
| **预测入口总数** | **17** |
| API (FastAPI) | 3 (trigger via orchestrator, trigger-public, latest read) |
| CLI/Script | **9** (predict_match, fast_predict, snapshot, batch_snapshot, pregenerate_wc26, hourly_predict, daily_ops, test_prediction, simulate_wc26) |
| Service (被 Dashboard 调用) | **4** (prediction_core, prediction_pipeline, prediction_orchestrator, prediction_enhanced) |
| Dashboard/Frontend | 4 (02_Match_Prediction, 07_Tournament_Simulator, 08_Creator_Mode, apps/web) |
| **绕过统一 pipeline 的入口** | **15 / 17** — 仅 `prediction_pipeline.py` 本身和 `snapshot.py`(V2.9 部分接入) 使用 pipeline |

### 核心发现

仓库中有 **4 套独立且互不共享的预测实现**：

| # | 实现 | 文件 | 调用方 |
|---|------|------|--------|
| 1 | `PredictionPipeline` (统一管线) | `app/services/prediction_pipeline.py` | 几乎没有 caller |
| 2 | `run_artifact_pipeline` (artifact 管线) | `app/services/prediction_core.py` | predict_match.py, Dashboard, prediction_enhanced |
| 3 | `PredictionOrchestrator.run_prediction` (编排器) | `app/services/prediction_orchestrator.py` | API routers/predictions.py |
| 4 | 各脚本内联融合逻辑 | predict_match.py, fast_predict.py, snapshot.py 等 | CLI 直接调用 |

这 4 套实现的融合逻辑、权重读取、信号调整、市场校准**互相重复但细节不一致**。

---

## 2. Entrypoint Table

### 2.1 CLI/Script 入口

| # | 文件 | 函数/入口 | 类型 | 当前行为 | 调用的核心模块 | 风险 | 应收敛进 pipeline |
|---|------|-----------|------|----------|----------------|------|-------------------|
| 1 | `scripts/predict_match.py` | `main()` → `run_artifact_pipeline()` | CLI | 加载 artifacts 做 4-model 融合预测，自有 fusion 逻辑和权重组装 | `prediction_core`, `dixon_coles`, `tabular_match_model`, `elo_ratings`, `pi_ratings`, `weibull_model`, `weights`, `fusion_graph` | **HIGH** | 是 |
| 2 | `scripts/fast_predict.py` | `main()` → `fast_predict()` | CLI | 绕过 artifacts，直接 `.fit()` DC + Enhancer + Elo，自有融合 | `dixon_coles`, `tabular_match_model`, `elo_ratings`, `weights` | **HIGH** | 是 |
| 3 | `scripts/snapshot.py` | `main()` → `run_snapshot()` | CLI | 全量预测 + 报告生成，自有融合、信号调整、source_logger | `dixon_coles`, `tabular_match_model`, `elo_ratings`, `pi_ratings`, `weibull_model`, `weights`, `signal_adjuster`, `source_logger` | **HIGH** | 是 |
| 4 | `scripts/batch_snapshot.py` | `main()` → `run_batch()` → 调 `snapshot.run_snapshot()` | CLI | 批量调度 snapshot.py | `snapshot.py` (wraps) | **MEDIUM** | 间接 (改 snapshot 即可) |
| 5 | `scripts/pregenerate_wc26.py` | `main()` | CLI | 预生成所有 WC26 小组赛预测到 DB，内联预测逻辑 | `dixon_coles` (内联调用), `snapshot_store` | **HIGH** | 是 |
| 6 | `scripts/hourly_predict.py` | `main()` | CLI | 每小时调度预测任务 | 调度多个预测入口 | **MEDIUM** | 是 (调度层) |
| 7 | `scripts/daily_ops.py` | `main()` | CLI | 日常运维脚本，包含预测步骤 | 多个 service | **MEDIUM** | 部分 |
| 8 | `scripts/test_prediction.py` | `run()` | CLI | 测试/验证脚本，DC+Enhancer+Elo 自有融合 | `dixon_coles`, `tabular_match_model`, `elo_ratings` | **LOW** | 否 (测试) |
| 9 | `scripts/simulate_wc26.py` | `main()` | CLI | 全量 Monte Carlo 赛事模拟，自有一整套预测+融合逻辑 | `dixon_coles`, `tabular_match_model`, `elo_ratings`, `pi_ratings`, `weights`, `tournament_simulator` | **MEDIUM** | 是 (预测部分) |

### 2.2 Service 层入口

| # | 文件 | 函数/入口 | 类型 | 当前行为 | 调用的核心模块 | 风险 | 应收敛进 pipeline |
|---|------|-----------|------|----------|----------------|------|-------------------|
| 10 | `app/services/prediction_core.py` | `run_artifact_pipeline()` | Service | Artifact 加载 + 4-model 融合，CLI 和 Dashboard 共用 | `dixon_coles`, `tabular_match_model`, `elo_ratings`, `pi_ratings`, `weibull_model`, `weights`, `fusion_graph` | **HIGH** | 是 (这是实际 de facto pipeline) |
| 11 | `app/services/prediction_pipeline.py` | `PredictionPipeline.predict_match()` | Service (async) | **设计的统一管线**，但几乎无 caller | `dixon_coles`, `tabular_match_model`, `elo_ratings`, `pi_ratings`, `weibull_model`, `weights`, `signal_adjuster`, `market_calibrator` | **HIGH** | 是 (本身即 pipeline) |
| 12 | `app/services/prediction_orchestrator.py` | `PredictionOrchestrator.run_prediction()` | Service (async) | API 触发预测，完整 DB 集成，自有融合+校准+信号 | `dixon_coles`, `tabular_match_model`, `elo_ratings`, `weights`, `signal_adjuster`, `market_calibrator`, `weather_service`, `injury_data` | **HIGH** | 是 |
| 13 | `app/services/prediction_enhanced.py` | `run_enhanced_prediction()` | Service (sync) | Wraps `prediction_core`，加 market/weather/LLM 增强层 | `prediction_core`, `market/sync_provider`, `weather_service`, LLM | **MEDIUM** | 部分 (增强层应保留，但基础预测应走 pipeline) |

### 2.3 API 入口

| # | 文件 | 函数/入口 | 类型 | 当前行为 | 调用的核心模块 | 风险 | 应收敛进 pipeline |
|---|------|-----------|------|----------|----------------|------|-------------------|
| 14 | `app/routers/predictions.py:192` | `trigger_prediction()` (admin) | API POST | Admin 触发预测 → `PredictionOrchestrator.run_prediction()` | `prediction_orchestrator` | **MEDIUM** | 已走 orchestrator |
| 15 | `app/routers/predictions.py:149` | `trigger_prediction_public()` | API POST | 公开触发预测(限流) → `PredictionOrchestrator.run_prediction()` | `prediction_orchestrator` | **MEDIUM** | 已走 orchestrator |
| 16 | `app/routers/predictions.py:29` | `get_latest_prediction()` | API GET | 只读，DB 查询 PredictionRun | DB | **LOW** | 否 (只读) |

### 2.4 Dashboard/Frontend 入口

| # | 文件 | 函数/入口 | 类型 | 当前行为 | 调用的核心模块 | 风险 | 应收敛进 pipeline |
|---|------|-----------|------|----------|----------------|------|-------------------|
| 17 | `dashboard/pages/02_Match_Prediction.py` | `_run_enhanced()` | Streamlit | 增强模式 → `prediction_enhanced`；基础模式 → `prediction_core` | `prediction_enhanced`, `prediction_core` | **HIGH** | 是 |
| 18 | `dashboard/pages/08_Creator_Mode.py` | 页面 | Streamlit | 从 `session_state.last_prediction` 读取并展示 | 无（只读 session state） | **LOW** | 否 (只读) |
| 19 | `dashboard/pages/07_Tournament_Simulator.py` | 页面 | Streamlit | 赛事模拟器 UI，调用 `tournament_simulator` | `tournament_simulator` | **MEDIUM** | 部分 |
| 20 | `apps/web/src/lib/api.ts` | `predictMatch()` 等 | React 前端 | 前端调用 FastAPI `/predictions/*` 端点 | API router | **LOW** | 否 (前端透传) |

---

## 3. Risk Classification

### HIGH — 自己组装权重、绕过 pipeline、数据缺失静默降级

| # | 文件 | 问题描述 |
|---|------|----------|
| 1 | `scripts/predict_match.py` | 在 `_run_retrain_pipeline()` 中从头组装权重和融合：`get_weight_config()` → 手工 `FusionGraph` → 手工 `fuse_outcome_probabilities()` / `fuse_elo_probabilities()` / `fuse_pi_probabilities()` / `fuse_weibull_probs()` → 手工 normalize。`run_artifact_pipeline()` 路径同样内联融合逻辑。**完全不经过 prediction_pipeline.py** |
| 2 | `scripts/fast_predict.py` | 完全独立的预测实现：`.fit()` 而非 artifact 加载，手工 3-step 融合（DC→Enhancer→Elo），手工 normalize。**不调用任何 pipeline 或 prediction_core** |
| 3 | `scripts/snapshot.py` | 最完整的"影子 pipeline"：自有 DC+Enhancer+Elo+Pi+Weibull 融合、signal_adjuster 接入、source_logger、disk cache。**逻辑与 prediction_pipeline.py 重复但细节不同** |
| 5 | `scripts/pregenerate_wc26.py` | 内联 `DixonColesModel` 训练和预测，**绕过所有 service 层和 pipeline** |
| 10 | `app/services/prediction_core.py` | 被 CLI 和 Dashboard 广泛调用的 **de facto 核心入口**，但它自己组装权重、fusion_graph、多模型融合。`prediction_pipeline.py` 标注为"统一管线"但反而无 caller |
| 11 | `app/services/prediction_pipeline.py` | **几乎没有 caller**。`snapshot.py` V2.9 版本有部分接入，但 predict_match.py / fast_predict.py / Dashboard / API 全部绕过它 |
| 12 | `app/services/prediction_orchestrator.py` | API 路径的独立实现：自有训练、融合、market_calibrator、signal_adjuster、injury_data、weather。**与 prediction_pipeline 和 prediction_core 是三套独立代码** |
| 17 | `dashboard/pages/02_Match_Prediction.py` | Dashboard 单场预测页面直接调用 `prediction_enhanced.run_enhanced_prediction()` 或 `prediction_core.run_artifact_pipeline()`。**绕过了 prediction_pipeline** |

### MEDIUM — 重复逻辑、调度层

| # | 文件 | 问题描述 |
|---|------|----------|
| 4 | `scripts/batch_snapshot.py` | Wraps `snapshot.py`，风险跟随 snapshot |
| 6 | `scripts/hourly_predict.py` | 调度器，调用多个预测入口，可能会调度到不同的 pipeline 实现 |
| 7 | `scripts/daily_ops.py` | 运维脚本内含预测逻辑，可能调用非统一入口 |
| 9 | `scripts/simulate_wc26.py` | 赛事模拟自有一整套 prediction 逻辑，但这是合理的（模拟需要不同假设） |
| 13 | `app/services/prediction_enhanced.py` | 增强层设计合理（wraps prediction_core），但 prediction_core 本身就不统一 |
| 19 | `dashboard/pages/07_Tournament_Simulator.py` | Dashboard 模拟器 UI，底层调用 tournament_simulator |

### LOW — 只读展示、测试辅助、前端透传

| # | 文件 | 问题描述 |
|---|------|----------|
| 8 | `scripts/test_prediction.py` | 测试/验证脚本，不影响生产 |
| 14-16 | `app/routers/predictions.py` | API 路由层，透传到 orchestrator，自身无预测逻辑 |
| 18 | `dashboard/pages/08_Creator_Mode.py` | 只读 session state，无预测逻辑 |
| 20 | `apps/web/src/lib/api.ts` | 前端透传到 API |

---

## 4. 权重/融合调用分析

以下是各入口如何获取权重和使用融合逻辑的差异表：

| 入口 | 权重来源 | 融合方式 | 市场校准 | 信号调整 |
|------|----------|----------|----------|----------|
| `prediction_core.py` | `get_weight_config(competition)` | `FusionGraph` + 手工 step-by-step fuse | ❌ | ❌ |
| `prediction_pipeline.py` | `get_weight_config(competition)` | 类内 `_fuse_*` 方法 | ✅ `MarketCalibrator` | ✅ `SignalAdjuster` |
| `prediction_orchestrator.py` | `get_weight_config(competition, stage)` | 手工 `fuse_outcome_probabilities()` + `fuse_elo_probabilities()` | ✅ `MarketCalibrator` | ✅ `SignalAdjuster` |
| `prediction_enhanced.py` | 委托给 `prediction_core` | 委托给 `prediction_core` | ✅ 自有 market blend (max 25%) | ✅ 委托给 signal_adjuster |
| `predict_match.py` (retrain) | `get_weight_config(competition)` | 手工 step-by-step，与 core 相同但 .fit() 替代 artifacts | ❌ | ❌ |
| `fast_predict.py` | `get_weight_config(competition)` | 手工 3-step，无 FusionGraph | ❌ | ❌ |
| `snapshot.py` | `get_weight_config(competition)` | 手工 step-by-step，有 disk cache | ❌ (可配) | ✅ |
| `simulate_wc26.py` | `get_weight_config("FIFA World Cup 2026")` | 手工 step-by-step | ❌ | ❌ |
| `pregenerate_wc26.py` | 无（仅 DC） | 无 | ❌ | ❌ |

**关键差异**:
- `prediction_orchestrator` 传 `stage` 参数给 `get_weight_config()`，其余入口不传
- `prediction_pipeline` 有 `DEFAULT_COMPETITION_WEIGHT = 0.9`, `WORLD_CUP_COMPETITION_WEIGHT = 1.5`, `FRIENDLY_COMPETITION_WEIGHT = 0.5` 常量，但 prediction_core 和 snapshot 没有
- 市场校准仅在 `prediction_pipeline`、`prediction_orchestrator`、`prediction_enhanced` 中存在，且实现各不相同

---

## 5. No-Code-Change Guarantee

本 Ticket (1.1) **未修改任何业务代码**。仅新增此文档 `docs/PREDICTION_ENTRYPOINT_INVENTORY.md`。

所有分析均基于全局 `rg`/`grep` 搜索和文件阅读。以下搜索已执行：

```
rg "predict|prediction|Prediction" --glob "*.py" backend scripts frontend → 105 files
rg "predict|prediction|Prediction" --glob "*.{html,js,jsx,tsx,ts,css}" → 16 files
rg "prediction_core|prediction_pipeline|predict_match|predict_full|enhanced" → 42 files
rg "FRIENDLY|weight|weights|model_version" --glob "*.py" → 67 files
rg "@router\.|@app\.|FastAPI|APIRouter" --glob "*.py" → 13 files
rg "streamlit|dashboard|gradio" → 46 files
```

---

## 6. 收敛建议（供 Phase 2+ 参考，不在本 ticket 范围）

1. **立即 (Phase 1)**: 强化 `prediction_pipeline.py` 的 contract（Ticket 1.2），让所有入口至少知道 pipeline 存在
2. **短期 (Phase 2)**: 让 `prediction_core.run_artifact_pipeline()` 内部委托给 `PredictionPipeline.predict_match()`，消灭 #1 de facto 标准与 #2 设计标准的差异
3. **中期 (Phase 3)**: 将 `prediction_orchestrator` 的预测核心替换为 `PredictionPipeline`，保留 DB/信号/校准编排层
4. **长期 (Phase 4)**: 所有 CLI 脚本统一通过 `PredictionPipeline` 获取预测，消除脚本内联融合逻辑
