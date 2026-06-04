# 架构护栏规则

> V2.6 Enhanced 生效。新功能和新修改必须遵守以下规则。

---

## 1. PredictionCore 是基础预测唯一入口

- 文件：`backend/app/services/prediction_core.py`
- 函数：`run_artifact_pipeline(home_team, away_team, competition, is_neutral, mode)`
- CLI (`predict_match.py`) 使用此入口获取基础概率
- **禁止**在其他页面或脚本中重新实现 artifact 预测逻辑

## 2. PredictionEnhanced 是增强预测唯一入口

- 文件：`backend/app/services/prediction_enhanced.py`
- 函数：`run_enhanced_prediction(home_team, away_team, competition, is_neutral, mode, ...)`
- Dashboard 增强模式必须通过此入口
- 内部调用 prediction_core + market sync + weather + LLM
- **禁止**在 Dashboard 页面中直接调用 market/weather/LLM API

## 3. Dashboard 页面不得直接写预测逻辑

- 页面只负责 UI 渲染，调用 prediction_core 或 prediction_enhanced 获取数据
- 不包含模型加载、融合、权重计算等逻辑

## 4. Database Explorer 永远只读

- 文件：`backend/dashboard/db.py`
- 三层防护：URI `?mode=ro` + `PRAGMA query_only=ON` + 正则拦截
- **禁止**在 Dashboard 中执行任何写操作

## 5. LLM 用于分析和内容生成，不直接调整概率

- LLM（DeepSeek V4 Pro）用于：赛前分析文章、视频口播脚本、社交媒体文案
- 核心概率计算（DC/Enhancer/Elo/Pi）完全本地数学运算，0 LLM token
- 概率调整仅通过市场赔率混合（数学运算，非 LLM）
- LLM 不参与概率调整决策

## 6. 市场赔率混合有上限

- 文件：`backend/app/services/prediction_enhanced.py`
- 最大市场混合权重：25%（MAX_MARKET_BLEND）
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
