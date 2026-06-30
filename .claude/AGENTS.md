# WC26 Predict — Agent 行为宪法

> "Anytime an agent makes a mistake, engineer a solution so it never makes that mistake again." — Mitchell Hashimoto

本文档的每一行都对应一个 Agent（Claude）曾经犯过的具体错误。执行任何预测、复盘、或代码修改任务前，**必须先检查本文件中的相关章节**。

---

## 1. 绝对禁止

这些是不可协商的底线。违反任何一条都会导致预测结果/报告不可用。

- **永远不猜测 Elo 评分。** 如果 DB 中 `elo_rating=1500`（系统默认值），必须标记为"数据缺失——系统不认识该球队"，不得当作真实实力使用。
  - *来源: Bug R4-? CIV Elo=1500 导致 29.7pp 市场分歧*
- **永远不跳过后融合校准步骤。** 完整 7 步序贯融合 + market boost + draw floor + calibration 必须全部执行。
  - *来源: Bug R4-C9 calibration_applied 从未设为 True*
- **永远不在无 WebSearch 确认的情况下假设比赛场地。** DB 中有过场地错误（Estadio Akron→Azteca）。
  - *来源: Bug V4.3.9 DB venue 错误*
- **永远不在无实时 API 数据的情况下编造赔率/概率数字。** 市场数据必须来自 The Odds API 或 WebSearch 聚合，不得凭"感觉"填。
  - *来源: 多起早期报告编造数据事件*
- **永远不在公众号文章中使用赔率数字或博彩术语。** 参见 `output_policy.py` 和 `wechat-article-style.md` 完整规则。
  - *来源: 公众号合规清洗*
- **永远不在 16 场 R32 全部完赛前修改核心参数。** 参数冻结期：now → R32 全部完赛。只复盘、不调参。
  - *来源: V4.3.5 路线图 Phase 3 原则*

---

## 2. 预测前检查清单（Pre-flight）

执行 `predict_match_full.py` 或人工预测前，逐项确认。每条对应一个历史 Bug。

### 数据完整性

- [ ] **两队 Elo 均不等于 1500**
  - 若等于 1500 → 降低 confidence 标记为 `degraded: elo_default`，所有组件对此队的攻防评估不可靠
  - *Bug: CIV Elo=1500 默认值 → 系统高估挪威 29.7pp*
- [ ] **比赛场地已通过 WebSearch 交叉验证**
  - 搜索 `"[venue name] 2026 World Cup"` 确认场地名称与 DB 一致
  - *Bug: DB 中 Estadio Akron 非真实场地*
- [ ] **The Odds API 返回 ≥3 家博彩商数据**
  - 1 家 → 启动 WebSearch fallback 获取 8-12 家共识
  - 0 家 → 标记 `degraded: no_market_data`，market_max 自动降为 0
  - *Bug: 单博彩商数据不可靠*
- [ ] **Weibull 组件状态已确认（成功 / 跳过 / 超时）**
  - 若跳过 → 报告必须声明"本场未纳入 Weibull"，不可静默跳过
  - *Bug: V4.3.1-fix Weibull 被静默跳过未记录*
- [ ] **`competition_weight` 匹配比赛类型**
  - WC 比赛 = 1.5，Friendly = 0.5，Default = 0.9
  - 检查代码中未硬编码 0.5（WC 场景）
  - *Bug 16/22/24: WC 比赛硬编码 0.5 而非 1.5*
- [ ] **伤病数据已加载且来自 ≥2 个独立源**
  - 单源 → 标记 `uncertain`，不写入报告正文
  - *Bug: Amoura (Jordan-Algeria)、Montiel (Argentina-Austria) 伤病错误*
- [ ] **天气数据时效性确认**
  - 比赛当日 → 使用 Open-Meteo 实时查询
  - 非当日 → 使用历史查询，标记 `weather: forecast (N days ahead)`
  - *Bug: 多起报告使用过期天气预报*

### 市场数据时效性

- [ ] **市场数据 < 30 分钟**
  - 超过 → 重新调用 The Odds API
  - API 不可用 → WebSearch 聚合
  - 标记数据时间戳在报告中

---

## 3. 预测后检查清单（Post-flight）

预测完成后、写入 DB 前，逐项确认。

### 概率质量

- [ ] **7 个组件概率全部计算（无 None/null）**
  - 缺失组件 → 报告必须声明"本场未纳入 [组件名]"
  - *Bug: Weibull None 未记录*
- [ ] **无 0% 或 100% 概率**
  - MIN_PROB=0.02 已全局生效，但仍需目视确认
  - *Bug: V4.3.1 校准器极端裁剪*
- [ ] **平局概率 ≥ 12%（WC 比赛）**
  - DRAW_FLOOR=0.12，如未触发则跳过
  - KO 比赛额外检查：平局 < 22% 且 Elo 差距 < 50 分 → **人工复查是否低估**
  - *Bug: GER-PAR + NED-MAR 淘汰赛平局系统性低估*
- [ ] **概率归一化和 ≈ 1.0**（±0.005 容差）

### 流程完整性

- [ ] **`market_boost` 已应用且权重正确**
  - market_applied=True，market_weight_used 在合理范围
  - *Bug: R4-C3 market_applied key 被破坏*
- [ ] **`calibration_applied=True`**
  - 校准器必须运行。若 calibrator 未就绪（样本不足）→ 显式标记 `calibration: skipped (insufficient samples)`
  - *Bug: R4-C9 calibration_applied 从未设为 True*
- [ ] **`fusion_chain_version` 对应当前代码版本**
  - 检查未使用旧版本缓存的融合结果

### 淘汰赛专项

- [ ] **KO 平局乘数已应用（×1.15-1.18）且地板已设置（18%-22%）**
- [ ] **报告包含"淘汰赛平局风险"章节**（见第 8 节）
- [ ] **KO draw tracker 已更新**（平局预测 vs 实际对比表）

---

## 4. 已知模型陷阱

### Enhancer（增强器）
- **enhancer 字段仅用于信息追踪，不控制融合权重。** 真正的 Enhancer 影响 = `1 - dc`。
- 要降低 Enhancer 影响 → 提高 `dc`，不是降低 `enhancer` 字段。
- Enhancer 17 场方向正确率仅 24%，系统性偏好弱队/客队。
- *来源: weights.py docstring + P1-4 诊断*

### Weibull（进球分布）
- 极端概率（>70%）应谨慎对待——历史 30% 失败率。
- Weibull 超时（120s）后静默跳过的 Bug 已修复，但超时仍然发生。
- *来源: project-status.md + V4.3.1-fix*

### Isotonic 校准器
- 在**淘汰赛阶段**，校准器可能学到"压低平局"——因为它在小组赛数据上训练，小组赛平局率 ~25%。
- 淘汰赛实际平局率可能显著更高。校准后的平局概率如果比 raw 低了 >3pp → 人工复查。
- *来源: NED-MAR 复盘: 校准器压低平局 4pp*

### Pi-Rating（进攻效率）
- 对"击败强敌"信号过度敏感。厄瓜多尔 2-1 击败德国后，Pi 给厄瓜多尔 56.1% 胜率——可能是高估。
- 涉及"一支弱队刚击败过强队"的场景时，对 Pi 的方向判断保持怀疑。
- *来源: MEX-ECU 预测分析*

### DC 模型（Dixon-Coles）
- 对新球队（Elo=1500、历史数据缺失）会输出严重偏差的攻防参数。
- 涉及科特迪瓦、卡塔尔、海地等 Elo 接近默认值的球队时，DC 的绝对概率不可靠。
- *来源: CIV 预测经历*

### context_adjuster（上下文调整器）
- 已知 Bug：代码查询 `recommended_home_adjustment` 列，但该列在 `context_performance_matrix` 模型定义中不存在。
- 当前 context_adjuster 输出不可信——不要依赖其建议。
- *来源: 全代码库审计*

### 序贯融合 vs 加权平均
- 融合链是**序贯的**（DC → Enhancer → NegBin → Weibull → Elo → Pi → Market），不是 7 个组件加权平均。
- DC 以 90% 入链，经 5 层衰减后有效权重仅 ~52%。早期组件的稀释效应显著。
- learning_engine 的边际贡献计算用加权平均近似，存在系统性误差（Bug 29b，Phase 4 修复）。
- *来源: Bug 29b + 序贯融合稀释分析*

---

## 5. 上下文管理规则

### 市场数据
- **超过 30 分钟 → 重新获取。** 不，API 调用配额是有限的——只在赛事当天或临场预测时才重新获取。提前预测（>24h）不强制刷新。
- 赔率/概率数据**必须来自 API 或 WebSearch 聚合**，禁止凭记忆或推测填写。

### 伤病数据
- **来源 ≥ 2 个独立源 → 采信；1 个源 → 标记 `uncertain`；0 个源 → 不写入报告。**
- 独立源可以是：Transfermarkt、ESPN、BBC Sport、队报、马卡报等主流体育媒体。

### 天气数据
- **比赛当日 → 用 Open-Meteo API 实时查询。**
- **非当日 → 标记为预报数据，注明预报日期。**

### 场地数据
- **必须通过 WebSearch 确认。** DB 中的场地字段不可盲信。
- 搜索模式：`"[stadium name] 2026 World Cup venue"` 确保场地确实承办该场比赛。

### 比赛时间
- 确认北京时间的正确转换。DB 中的 UTC 时间可能直接搬运，需验证。
- 淘汰赛比赛时间可能有变动——以 FIFA 官方赛程为准。

---

## 6. 复盘流程标准

### 7 步标准流程（必须全部执行）

| 步骤 | 内容 | 关键产出 |
|:---|:---|:---|
| 1. 结果验证 | ≥2 独立源确认比分（EFE + 新华网 + 央视等） | `match_results` DB 写入 |
| 2. 逐组件评估 | 每个组件的方向 + Brier + LogLoss + RPS | 组件成绩表 |
| 3. 指标计算 | 整体 Brier / LogLoss / RPS / 方向 / 比分命中 | `postmatch_eval` DB 写入 |
| 4. 边际贡献 | LearningEngine.process_match_result() | `prediction_learning_log` DB 写入 |
| 5. DB 更新 | 快照状态 + 比分 + 评估记录 | 双 DB 同步 |
| 6. 报告生成 | Markdown 复盘报告 → `reports/postmatch/` | 报告文件 |
| 7. Memory 更新 | 更新 project-status.md 累计面板 + 淘汰赛平局率 | memory 文件 |

### 淘汰赛平局率追踪

- **每场淘汰赛复盘 → 必须更新淘汰赛平局率：** 实际平局场次/总淘汰赛场次 vs 预测平局概率均值。
- 当前基线：**2/4 = 50%**（GER-PAR 1-1, NED-MOR 1-1），预测均值 ~20%。
- Phase 3（16 场 R32 全部完赛）统一评估是否需要结构性提升 draw floor。

### 异常场景处理

- **如果所有 7 个组件方向错误（0/7）：** 触发深度诊断——检查赛前是否有重大信息缺失（关键伤病、天气突变、阵容轮换），不急于调参。
- **如果 Brier > 0.40：** 标记为 "poor"，分析原因（极端偏差 vs 信息不足 vs 黑天鹅）。
- **如果单个组件连续 3 场方向错误：** 记录到 project-status.md，在 Phase 3 重新评估其权重。

---

## 7. 预测报告格式标准

### 公众号文章（`articles/` 目录）

**必须遵守 `wechat-article-style.md` 完整规范。** 关键规则摘要：

- **没有赔率数字**（1.20, 7.00 等）
- **没有博彩黑话**（盘口、下盘、胜平负、精算师、博彩公司）
- **替代术语**: "外部参考数据" / "公开交易数据" / "信息公开市场" 替代 "赔率/盘口"
- **"模拟推演" / "AI 系统模拟分析"** 替代 "预测"（标题和关键句中）
- **"概率最高的方向区间" / "模型共识方向"** 替代 "最稳/最值得"
- **末尾必须有三段声明**: 研究性质 + 微信合规 + 数据来源
- **长度**: 第一部分 5000-7000 字，第二部分 3000-5000 字，总长 8000-12000 字
- **叙事风格**: 第一人称（"我"的主视角），模型拟人化，"内部打架"叙事
- **数据呈现**: 概率表 + 融合链逐层推演 + DC 底层参数

### 技术报告（`reports/predictions/` 目录）

- 完整 7 组件概率面板
- 融合链逐层推演表
- Bootstrap CI（或 WCP）
- Over/Under 分析
- 比分分布表（Top 10）
- 关键变量风险分析

---

## 8. 淘汰赛专项规则

### 淘汰赛预测必须包含
1. **"淘汰赛平局风险"章节** — 分析本场平局概率是否可能被低估
2. **与外部数据的分歧评估** — 特别关注模型说 A 但市场说 B 的场景
3. **关键伤停影响分析** — 淘汰赛关键球员缺失影响远大于小组赛
4. **加时/点球概率提示** — 弱队拖延战术在淘汰赛更常见

### 淘汰赛融合特殊规则
- **不压制平局**：小组赛校准器学到"压低平局"模式在淘汰赛不适用
- **市场分歧度高 → 动态提升 market_max 至 30%**
- **Bootstrap CI 宽度 > 40pp → 显式标注"高不确定性"**

### 淘汰赛复盘必须更新
- 淘汰赛平局实际率（平局场次 / 总淘汰赛场次）
- KO draw tracker 视图（SQL 查询：`SELECT stage, actual_outcome, pred_draw_prob FROM ... WHERE stage LIKE '%knockout%'`）

---

## 9. 代码修改规则

### 任何时候修改代码
- [ ] **测试通过**: `cd backend && python -m pytest tests/ -x --tb=short`
- [ ] **Golden fixtures 更新**: 若输出格式或数值有变 → `python scripts/regenerate_golden.py`
- [ ] **版本号更新**: 按 `MAJOR.MINOR.PATCH-beta` 规则 → README + `weights.py` 版本注释 + VERSION 文件
- [ ] **Magic Number 注册表更新**: 若新增/修改任何硬编码常量 → 更新 `backend/docs/MAGIC_NUMBERS.md`
- [ ] **Bug 编号注册**: 若修复新 Bug → 按 `Bug-XX` 递增编号，记录到本文件

### 版本号规则
- **PATCH** (V4.3.x): Bug 修复、文档更新、测试补充
- **MINOR** (V4.x.0): 新功能、参数调整、组件增强
- **MAJOR** (Vx.0.0): 架构重构、融合链重设计

### Git 提交格式
```
V4.3.X-beta: <简短描述> (#PR编号)

<详细说明>

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

## 10. 项目文件索引

Agent 执行任务时优先查阅以下文件：

| 文件 | 用途 | 触发条件 |
|:---|:---|:---|
| `backend/docs/MAGIC_NUMBERS.md` | 所有硬编码参数的含义和历史 | 需要理解/修改参数时 |
| `D:\NodejsGlobal\...\memory\project-status.md` | 组件成绩单、API 配额、权重历史 | 每次预测/复盘前 |
| `D:\NodejsGlobal\...\memory\wechat-article-style.md` | 公众号写作规范 | 写公众号文章前 |
| `reports/postmatch/` | 历史复盘报告 | 复盘前参考 |
| `memory/wc-postmatch-*.md` | 逐场比赛 memory 文件（33 个） | 涉及特定比赛时 |
| `backend/app/core/engine.py` | 融合链纯数学引擎 | 修改融合逻辑时 |
| `backend/app/services/weights.py` | 权重配置和加载 | 修改权重时 |
| `backend/app/services/calibration.py` | Isotonic 校准器 | 修改校准时 |
| `backend/docs/` | 项目文档 | 需要了解架构/参数时 |

---

## 附录：已修复 Bug 编号索引

| Bug ID | 描述 | 修复版本 | 对应规则 |
|:---|:---|:---|:---|
| Bug 15 | `dc_provenance` NameError in predict_match() | V4.1 | §2 |
| Bug 16 | `competition_weight` inconsistent in predict_sync() | V4.1-fix | §2 |
| Bug 17 | Dead WC code in weights.py | V4.1-fix | §9 |
| Bug 18 | Weibull step missing in predict_match_full.py | V4.1-fix | §2 |
| Bug 22 | `competition_weight=0.5` hardcoded in 5 WC callers | V4.1-fix | §2 |
| Bug 29a | Learning engine 留一法边际计算修复 | V4.3.0 | §4 |
| Bug 29b | Learning engine 序贯融合边际计算（**未修复**） | Phase 4 | §4 |
| Bug 30 | predict_match() passes timeout to WeibullWrapper.fit() | V4.1-fix | §2 |
| R4-C1 | Logger undefined in dixon_coles.py | V4.0.9 | — |
| R4-C2 | Calibrator path `model_artifacts/`→`artifacts/` | V4.0.9 | §3 |
| R4-C3 | `market_applied` key destroyed in orchestrator | V4.0.9 | §3 |
| R4-C9 | `calibration_applied` never set to True | V4.0.9 | §1,§3 |
| R4-C10 | auto_postmatch.py verification gate never passes | V4.0.9 | §6 |
| R4-H8 | DB auto-optimized weights sanity checks missing | V4.0.9 | §4 |
| V4.3.9 | DB venue 错误（Estadio Akron→Azteca） | V4.3.9 | §1,§5 |
| — | CIV Elo=1500 默认值导致 29.7pp 市场分歧 | V4.3.7 | §1,§2 |
| — | Weibull 被静默跳过未记录 | V4.3.1-fix | §2,§3 |
| — | 淘汰赛平局系统性低估 | 跟踪中 | §3,§6,§8 |
| — | context_adjuster 查询不存在的列 | 跟踪中 | §4 |
