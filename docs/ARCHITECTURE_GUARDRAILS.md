# 架构护栏规则

> V3.5 生效。新功能和新修改必须遵守以下规则。

---

## 1. PredictionPipeline 是基础预测唯一入口

- 文件：`backend/app/services/prediction_pipeline.py`
- 同步 artifact 入口：`PredictionPipeline.from_artifacts(mode).predict_sync(...)`
- 异步 DB-aware 入口：`await PredictionPipeline.from_snapshot_env(...); await pipeline.predict_match(...)`
- CLI (`scripts/predict_wc26.py`) 和 Dashboard 基础模式必须通过此入口获取基础概率
- **禁止**在其他页面或脚本中重新实现 artifact 预测逻辑

## 2. PredictionEnhanced 是 Dashboard/Creator 兼容包装层

- 文件：`backend/app/services/prediction_enhanced.py`
- 函数：`run_enhanced_prediction(home_team, away_team, competition, is_neutral, mode, ...)`
- Dashboard 增强模式必须通过此入口
- 内部调用 PredictionPipeline + weather + LLM；市场数据保持 shadow-mode，不直接改写概率
- **禁止**在 Dashboard 页面中直接调用 market/weather/LLM API

## 3. Dashboard 页面不得直接写预测逻辑

- 页面只负责 UI 渲染，调用 PredictionPipeline 或 prediction_enhanced 获取数据
- 不包含模型加载、融合、权重计算等逻辑

## 4. Database Explorer 永远只读

- 文件：`backend/dashboard/db.py`
- 三层防护：URI `?mode=ro` + `PRAGMA query_only=ON` + 正则拦截
- **禁止**在 Dashboard 中执行任何写操作

## 5. LLM 用于分析和内容生成，不直接调整概率

- LLM（DeepSeek V4 Pro）用于：赛前分析文章、视频口播脚本、社交媒体文案
- 核心概率计算（DC/Enhancer/Elo/Pi）完全本地数学运算，0 LLM token
- 市场数据默认只作为 shadow benchmark / risk telemetry；显式研究配置允许时才可做有上限的数学融合
- LLM 不参与概率调整决策

## 6. 市场数据默认 shadow-mode

- 文件：`backend/app/services/prediction_pipeline.py`
- 默认路径：记录市场分歧、可用性、风险标签，不直接改写基础模型概率
- 如研究配置显式启用融合，最大市场混合权重必须有上限
- 分歧 > 12pp 触发风险标签和置信度惩罚
- 市场数据不可用时自动回退到纯模型概率
- **禁止**展示原始赔率数字（合规）

## 7. 所有版本从 `backend/app/version.py` 读取

- 文件：`backend/app/version.py`
- CLI、Dashboard、README、报告统一引用
- **禁止**在任何文件中硬编码版本号

## 8. 新功能必须有测试

- 测试目录：`backend/tests/`
- 运行 `pytest tests/ -v` 必须全部通过

## 9. 每次 release 必须更新 CURRENT_STATUS

- 文件：`docs/CURRENT_STATUS.md`
- README 中的版本徽章同步更新
- CHANGELOG.md 追加新版本条目

## 10. 优雅降级 > 强制依赖

- 市场赔率不可用 → 回退到纯模型预测
- 天气不可用 → 跳过天气展示
- LLM 不可用 → 回退到模板内容
- 任何实时数据源的失败不得阻止基础预测完成

## 11. 旧闭环数据必须隔离，不得伪造绑定

- 文件：`backend/scripts/audit_closed_loop_integrity.py`
- 文件：`backend/scripts/repair_closed_loop_integrity.py`
- 可唯一解析的旧数据才允许回填真实 `match_id` / `prediction_run_id`
- 无法唯一解析的旧数据必须进入 `closed_loop_resolution_ledger`
- `legacy_untraceable` / `legacy_ambiguous` 学习日志不得参与 active learning
- 真实 xG 覆盖不足只能作为数据质量警告，不得用估算值伪装为实测值

## 12. 完整预测必须公开数据源状态

- 文件：`backend/app/services/prediction_result.py`
- 文件：`backend/app/services/prediction_pipeline.py`
- 每次预测必须输出 `source_status`
- 实时源状态只允许：`used` / `unavailable` / `failed` / `skipped`
- `require_full_context=True` 必须提供真实 `match_id`、`match_date`、`venue`，并启用天气与市场数据
- AI 内容只能引用 `source_status[*].status == "used"` 的数据源
- Dashboard 不得把 `source_status` 缺失或 required source 未使用的结果展示成完整预测
