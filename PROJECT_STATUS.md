# WC26 Predict — 项目现状与问题诊断

> 2026-05-12 | 面向接手此项目的 AI / 开发者
> 项目路径：`/mnt/e/2026世界杯分析`

---

## 一、项目是什么

**定位**：足球赛前情报分析工具（非博彩工具）

**核心功能**：输入两支球队 → 输出一份 Markdown 预测报告，包含：
- 三层融合预测概率（主胜/平局/客胜）
- Top 3 比分 + 期望进球
- Elo 评分 + 近期战绩
- 联赛排名驱动的动力因素
- 手动注入的伤病/停赛情报
- 数据来源追溯表（每个数据点标注来源、Tier、可靠性）

**明确不做**：博彩赔率、盘口、投注建议、市场赔率对比（用户明确拒绝）

---

## 二、当前架构

```
手动触发脚本层
├─ snapshot.py             单场预测快照（主要入口）
├─ batch_snapshot.py       批量预测 + 汇总
├─ sync_standings.py       同步联赛积分榜 + 生成动机标签
├─ add_manual_event.py     手动注入伤病/停赛/轮换事件
├─ seed_players.py         从 football-data.org 导入球员
├─ lineup_probe.py         探测首发阵容可用时间（脚本就绪，等新赛季）
├─ fast_predict.py         快速预测（JSON 输出）
├─ render_report.py        渲染 Markdown 报告
└─ llm_intel_extract.py    LLM 新闻信号抽取

预测引擎（3 层融合）
├─ Dixon-Coles            泊松模型，Bayesian shrinkage，权重 ≈58%
├─ Tabular Enhancer       梯度提升分类器，37 特征，权重 ≈27%
└─ Elo Ratings            1500 基分，K 按赛事分级，权重 ≈15%

事件账本（人工驱动）
├─ standings             96 行（5 大联赛 2025-26 赛季）
├─ motivation_events     492 条（从积分榜推导）
├─ manual_events         人工注入的结构化事件
├─ news_signals          **0 条（核心瓶颈）**
└─ players               306 名（12 支种子队）

数据源
├─ football-data.org     ✅ 赛程/比分/积分榜/球队 squad
├─ StatsBomb Open Data   ✅ 历史比赛 + xG
├─ Open-Meteo            ✅ 天气（16 天窗口）
├─ GDELT                 ⚠️ 免费版只返回文章元数据，无正文
├─ RSS（ESPN/BBC等）     ⚠️ 摘要约 150 字，多为赛后报道
├─ DeepSeek LLM          ✅ API key 已配置可用
└─ Event Registry        ❌ 无 API key
```

---

## 三、数据库状态

| 表 | 行数 | 说明 |
|---|---|---|
| matches | 5,989 | 5,639 完赛 + 350 待踢 |
| match_results | 5,639 | 含 xG |
| teams | 231 | 50+ 国家队，180+ 俱乐部 |
| prediction_runs | 62 | 39 俱乐部 + 23 国家队 |
| postmatch_eval | 47 | 平均 Brier 0.23，LogLoss 1.79 |
| prediction_snapshots | 40+ | 含 source_log |
| news_articles | 70 | 已入库但无有效正文 |
| news_signals | **0** | ← 情报层最大瓶颈 |
| players | 306 | 12 支种子队，4 队因 API 权限未导入 |
| standings | 96 | 5 大联赛 |
| motivation_events | 492 | 从 standings 自动生成 |
| manual_events | 1 | 测试事件 |
| source_registry | 6 | 未填充活跃源 |
| lineup_probe_logs | 13 | 全部返回"无 lineup" |

---

## 四、已交付能力（P0 + P1 + P2）

### 预测管线
- ✅ 单场快照 `snapshot.py --home "A" --away "B"`（约 39s/场）
- ✅ 批量预测 `batch_snapshot.py --limit N`（约 35s/场）
- ✅ 标准化快照表 `prediction_snapshots`（追加写入，不覆盖）
- ✅ 管线拆分：fast_predict → render_report → llm_intel_extract

### 校准与评估
- ✅ CalibrationMonitor（回测 < 20 样本时不修改概率，仅记录）
- ✅ 47 次回测评估，平均 Brier 0.23

### 情报层（P1）
- ✅ 联赛积分榜同步（standings 表 + motivation_events）
- ✅ snapshot 报告新增"赛前动力因素"板块
- ✅ 手动事件注入（manual_events 表 + add_manual_event.py CLI）
- ✅ snapshot 报告新增"手动情报事件"板块
- ✅ lineup 探测脚本（脚本完成，实测 football-data.org 不返回赛前 lineup）

### 数据基础（P2）
- ✅ 306 名球员（12 支种子队），含 importance_level + status
- ✅ 7 种固定事件类型（INJURY/SUSPENSION/LINEUP_CONFIRMED/LINEUP_RUMOR/ROTATION_HINT/MOTIVATION/WEATHER）
- ✅ feature_flags.yaml（MarketBaseline=disabled，ODDS_MOVEMENT=disabled）
- ✅ DeepSeek LLM API key 已验证可用

---

## 五、核心问题

### 问题 1：news_signals = 0，情报层不存在

这是**最大瓶颈**。70 篇新闻文章，0 条可提取的赛前信号。

原因：
- GDELT 免费版只返回文章元数据（标题+URL），无正文
- RSS 摘要约 150 字，内容为赛后报道和转会流言
- Event Registry 无 API key
- LLM 信号抽取器工作正常——它正确地返回了 0 条信号，因为输入文章没有可提取的赛前情报

影响：SignalAdjuster 永远不会运行。预测只依赖历史统计数据，完全不考虑现实赛前事件。

### 问题 2：项目没有自我进化能力

当前项目是**手动操作的脚本集合**，不是自主运行的 Agent：

- 模型参数每次跑脚本时现场 fit，不持久化，不版本化
- 融合权重（68:32:15）硬编码，无人调优
- postmatch_eval 有 47 条记录但只存着，不用于改进模型
- 没有 A/B 测试不同参数的能力
- 没有自动重训练/模型更新机制
- Celery Beat 定义了 7 个定时任务但进程不跑

### 问题 3：WC26 baseline 不完整

baseline_v0 只有 38/72 场预测落库。34 支国家队（Greece、Hungary、Slovakia、Chile 等）因为缺乏训练数据，Dixon-Coles 模型直接报 `KeyError: Unknown team in fitted model`。

对这些球队没有 fallback 路径，无法输出预测。

### 问题 4：数据空窗期

- 五大联赛 2025-26 赛季已于 2026 年 5 月结束
- 2026-27 赛季赛程预计 6-7 月发布
- 世界杯 6 月 11 日开始
- 目前无新数据流入，standings 是最终积分榜，不再变化

### 问题 5：lineup 数据不可用

实测 football-data.org 在比赛 TIMED 状态下不返回 lineup 数据（13 场探测，全部 0 lineup）。首发阵容只能在赛后获取。T-1h/T-60m 的实时 lineup 探测在当前 API tier 下不可行。

---

## 六、如果要加自我进化，需要什么

### 最小闭环（ROI 最高，改动最小）

1. **赛后复盘自动运行**
   - 每次比赛结束后自动对比预测 vs 实际
   - 更新 Brier/LogLoss，按球队/联赛分组
   - 积累到 ≥300 条后自动启用校准器修正概率

2. **定时自主运行**
   - Celery worker + beat 真正跑起来
   - T-24h 自动触发所有 upcoming 比赛的预测
   - 赛后自动抓取比分 → 写入 postmatch_eval
   - 每天自动同步 standings（新赛季开始后）

3. **模型参数版本化**
   - 模型 fit 结果持久化到 model_artifacts/
   - 融合权重可配置（不从代码硬编码读取）
   - 支持 A/B 对比不同参数组合的回测表现

4. **情报输入闭环**
   - 路线 A：手动注入（已实现）← 当前唯一可行路径
   - 路线 B：Event Registry 付费 API → 自动新闻采集 → LLM 抽取
   - 路线 C：爬取官方足协/球队公告页面

---

## 七、技术约束

| 约束 | 说明 |
|---|---|
| 数据库 | SQLite（开发），PostgreSQL（可选生产） |
| 路径 | WSL 环境，所有路径必须 `/mnt/e/...` 格式，不能用 `E:/...` |
| LLM | DeepSeek v1 API，key 已验证可用 |
| football-data.org | API key 已有，免费 tier，有速率限制 |
| Python | 3.11+，依赖在 `backend/requirements.txt` |
| 前端 | React 18 + Vite，但当前只做后端脚本开发 |

---

## 八、关键文件索引

| 文件 | 作用 |
|---|---|
| `HANDOFF.md` | 最新交接文档 |
| `AGENTS.md` | 项目技术栈和常用命令 |
| `backend/config/feature_flags.yaml` | 功能开关 |
| `backend/scripts/snapshot.py` | **主入口**：单场预测快照 |
| `backend/scripts/sync_standings.py` | 积分榜同步 + 动机生成 |
| `backend/scripts/add_manual_event.py` | 手动事件注入 CLI |
| `backend/scripts/seed_players.py` | 球员库导入 |
| `backend/scripts/lineup_probe.py` | 首发探测 |
| `backend/app/services/dixon_coles.py` | Dixon-Coles 模型 |
| `backend/app/services/tabular_match_model.py` | Tabular Enhancer |
| `backend/app/services/elo_ratings.py` | Elo 评分系统 |
| `backend/app/services/snapshot_store.py` | 快照入库 |
| `backend/app/services/source_logger.py` | 数据来源追踪 |
| `backend/app/models/standings.py` | 积分榜模型 |
| `backend/app/models/motivation_event.py` | 动机事件模型 |
| `backend/app/models/manual_event.py` | 手动事件模型 |
| `backend/app/models/player.py` | 球员模型 |
| `backend/data/local_stage2.db` | SQLite 数据库 |
| `.env.local` | 本地环境变量（含 API keys） |

---

## 九、给接手 AI 的建议

1. **先读 `HANDOFF.md` 和 `AGENTS.md`**，里面有完整的命令和架构
2. **数据库操作前先备份**：`cp backend/data/local_stage2.db backend/data/local_stage2.db.bak.$(date +%Y%m%d_%H%M)`
3. **跑一条预测验证环境**：`cd backend && python scripts/snapshot.py --home "Arsenal FC" --away "Chelsea FC" --competition "Premier League"`
4. **WSL 注意**：不要用 `read_file` + `write_file` 编辑 .py 文件（会嵌入行号前缀导致 SyntaxError），用 `patch` 工具或 `terminal` + Python heredoc
5. **不要恢复博彩赔率代码**——用户已明确拒绝
6. **路径必须是 `/mnt/e/...` 格式**

---

## 十、待推进（优先级排序）

1. **赛后复盘闭环** — 让 postmatch_eval 驱动模型改进
2. **WC26 baseline 完整化** — 104 场预测 + 缺数据球队 fallback
3. **情报输入闭环** — 解决 news_signals=0
4. **Celery 自动化** — 让定时任务跑起来
5. **轻量前端** — 报告可在 Web 端查看
