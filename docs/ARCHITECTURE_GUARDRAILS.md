# 架构护栏规则

> V2.5 Local Demo Release 生效。新功能和新修改必须遵守以下规则。

---

## 1. PredictionCore 是唯一单场预测入口

- 文件：`backend/app/services/prediction_core.py`
- 函数：`run_artifact_pipeline(home_team, away_team, competition, is_neutral, mode)`
- CLI (`predict_match.py`) 和 Dashboard (`02_Match_Prediction.py`) 都必须通过此入口调用
- **禁止**在任何页面或脚本中重新实现预测逻辑

## 2. Dashboard 页面不得直接写预测逻辑

- 所有 Dashboard 页面通过 `prediction_core.run_artifact_pipeline()` 获取预测结果
- 页面只负责 UI 渲染，不包含模型加载、融合、权重计算等逻辑
- 如需展示组件状态，使用 `RunQuality` 和 `FusionGraph.to_dict()` 的输出

## 3. Database Explorer 永远只读

- 文件：`backend/dashboard/db.py`
- 三层防护：
  1. SQLite URI `?mode=ro`（文件系统级）
  2. `PRAGMA query_only=ON`（SQL 层）
  3. `_validate_read_only()` 正则拦截（应用层）
- **禁止**在 Dashboard 中执行任何写操作（INSERT/UPDATE/DELETE/DROP/ALTER）
- 所有数据库写入通过独立 CLI 脚本完成

## 4. LLM 不直接调整概率

- LLM（DeepSeek）仅用于新闻情报提取（`news_signal_extractor.py`）
- LLM 输出不直接修改模型概率
- 情报信号默认 `affects_model=false`，需人工审核后才可影响模型
- 核心概率计算（DC/Enhancer/Elo/Pi）完全本地数学运算，0 LLM token

## 5. 软情报默认 display_only

- 新闻信号、伤病信息、天气数据等"软情报"默认仅展示，不进模型
- 只有经过审核、有可验证来源的硬事实（如 team_tournament_status.json）才进模型
- 信号状态机：`pending → reviewed → approved → enters_model`

## 6. 所有版本从 `backend/app/version.py` 读取

- 文件：`backend/app/version.py`
- 三个字段：`VERSION`, `TAG`, `BUILD_NAME`
- CLI、Dashboard、README、报告、smoke test 统一引用
- **禁止**在任何文件中硬编码版本号

## 7. 新功能必须有测试

- 测试目录：`backend/tests/`
- 命名规范：`test_<模块名>.py`
- 新服务/新脚本合并前必须至少有对应的测试文件
- 运行 `pytest tests/ -v` 必须全部通过

## 8. 临时脚本不得进入正式报告路径

- 临时调试脚本放 `backend/tmp/`（已在 `.gitignore` 中）
- 不得在 `backend/scripts/`、`backend/app/` 或项目根目录遗留临时脚本
- 实验性 `.py` 文件提交前必须移到 `scripts/` 并具备 CLI 接口，或者删除

## 9. 每次 release 必须更新 CURRENT_STATUS

- 文件：`docs/CURRENT_STATUS.md`
- 更新内容：版本号、commit、tag、包含范围、排除范围
- README 中的版本徽章和里程碑文字同步更新
- CHANGELOG.md 追加新版本条目

## 10. V2.5 发布后停止新增大功能

- V2.5 是 Local Demo Release，定位为可展示 MVP
- 发布后 72 小时内只允许：修启动失败、修页面崩溃、修明显文案/合规错误
- 禁止：新增模型、新增页面、新增动态情报概率调整、重构架构
- 下一阶段（V3.0）需在收集真实反馈后重新规划
