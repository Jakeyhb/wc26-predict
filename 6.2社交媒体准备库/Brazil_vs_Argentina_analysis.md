# 预测快照：Brazil vs Argentina（Group C）

> 生成时间：2026-06-03T05:11:29Z  |  赛事：World Cup 2026  |  训练数据：10999 场

> 🏟️ 世界杯比赛  |  中立场  |  赛事权重: 1.5×

---

## 预测结果（三层融合）

| 来源 | 主胜 | 平局 | 客胜 |
|---|---:|---:|---:|
| 模型预测 | **20.6%** | 18.8% | 60.6% |

> 期望进球：Brazil **1.01** — **1.26** Argentina

> 校准：监控模式（回测样本不足，未启用）

> ⚠️ 世界杯预测使用的国家队训练数据有限（10999 场），预测仅供参考

### Top 3 比分

- 0:1（14.6%）
- 1:0（12.0%）
- 1:1（11.5%）

### 各层独立预测

下表展示每层模型在融合前的独立判断，帮助理解最终概率的来源：

| 层级 | 主胜 | 平局 | 客胜 |
|---|---:|---:|---:|
| Dixon-Coles (泊松) | 31.3% | 25.0% | 43.7% |
| Tabular Enhancer | 5.7% | 12.1% | 82.2% |
| Elo 评分 | 35.8% | 11.8% | 52.4% |
| Pi-Rating | — | — | — |

> 融合配置：WORLD_CUP (DC55%+Enh25%+Elo5%+Pi5%)
> 最终概率由各层按动态权重加权融合，非简单平均。Enhancer 对近期状态敏感，DC 偏重长期攻防参数，Elo 反映历史实力。

### 总进球分布（Over/Under）

由 Dixon-Coles 泊松模型 xG（Brazil 1.01 + Argentina 1.26）直接推导：

| 总进球 | 概率 |
|---|---:|
| 0 球 | 10.3% |
| 1 球 | 23.4% |
| 2 球 | 26.6% |
| 3 球 | 20.2% |
| 4 球 | 11.5% |
| 5 球 | 5.2% |
| 6+ 球 | 2.9% |

> 总进球 ≤ 1：**33.7%** | ≤ 2：**60.3%** | ≥ 3：**39.7%**

---

## 数据来源与质量

| 数据 | 来源 | Tier | 可靠性 | 状态 | 备注 |
|---|---|---|---|---|---|
| 历史比赛数据 | football-data.org + StatsBomb + openfootball | T1 | 0.70 | ✓ |  |
| Dixon-Coles 模型 | DixonColesModel (internal) | T1 | 0.85 | ✓ | NLL=1178.22 |
| Tabular Enhancer | TabularEnhancer (internal) | T1 | 0.82 | ✓ | HistGradientBoostingClassifier |
| Elo 评分 | EloRatingSystem (internal) | T1 | 0.80 | ✓ | k=32 |
| 球员伤病 | — | T4 | 0.70 | ⚠ 不可用 | injuries.json 为空 |
| 联赛排名 | football-data.org standings | T1 | 0.70 | ✓ | HIGH_MOTIVATION / HIGH_MOTIVATION |
| 天气数据 | Open-Meteo | T1 | 0.85 | ✓ | 赛前16天内可用 |
| 新闻情报 | DeepSeek (LLM_API_KEY 已配置) | T1 | 0.70 | ✓ | 新闻抽取可用，待有内容赛前文章触发 |
| 市场共识 | The Odds API | T2 | 0.70 | ⚠ 不可用 | API已配置，本次未拉取到数据 |

> 数据质量: Tier avg=1.0  Reliability avg=0.77  活跃源=7 陈旧=0 缺失=2

### Elo 评分
- Brazil：**1754**
- Argentina：**1820**
- 评分差：-66（K=32）

---

## 赛前动力因素

### 世界杯小组动力

- Brazil（Group C，0场0分）：**首战** — 小组赛首轮，双方全力争胜
- Argentina（Group J，0场0分）：**首战** — 小组赛首轮，双方全力争胜

> 世界杯动力因素基于小组赛实际积分动态计算，非联赛 standings 表

---

## 手动情报事件

- 无手动注入事件（使用 `python scripts/add_manual_event.py` 添加）

---

## 近期战绩

### Brazil（近 5 场）

- 2026-05-31 W 6-2 vs Panama (home)
- 2026-03-31 W 3-1 vs Croatia (home)
- 2026-03-26 L 1-2 vs France (home)
- 2025-11-18 D 1-1 vs Tunisia (home)
- 2025-11-15 W 2-0 vs Senegal (home)

### Argentina（近 5 场）

- 2026-03-31 W 5-0 vs Zambia (home)
- 2026-03-27 W 2-1 vs Mauritania (home)
- 2025-11-14 W 2-0 vs Angola (away)
- 2025-10-14 W 6-0 vs Puerto Rico (away)
- 2025-10-10 W 1-0 vs Venezuela (home)

---

## 未知 / 缺失数据

| 数据项 | 影响 | 获取方式 |
|---|---|---|
| 首发阵容 | 极大 (可改变 xG ≥ 15%) | football-data.org 赛前 1h |
| 球员伤病 | 大 (affected_team xG ↓) | 缺免费API，可手动维护 injuries.json |
| 新闻情报 (赛前) | 中 (上下文/战术) | LLM 已配置，待有内容赛前文章 |

---

## 管线技术参数

- Dixon-Coles 收敛：否（NLL=1178.22）
- Enhancer：HistGradientBoostingClassifier，10999 行 x 37 特征
- Elo 比赛数：10999
---

## 预测可信度说明

- 本预测基于 5,000+ 场历史比赛训练
- 三层模型融合：Dixon-Coles (泊松) + Enhancer (梯度提升) + Elo
- 已纳入：联赛排名/动力因素（standings 驱动）
- 未纳入参数：首发阵容、球员伤病、赛前新闻情报
- 以上缺失因素可能显著改变预测结果，仅供个人参考
- 市场赔率：未拉取（ODDS_API_KEY 未配置或 API 不可用）
- 球员情报：manual_events 表，2 条记录，最新录入 ?
- 历史比赛：football-data.org + martj42 internationals
  训练样本 10999 场，最新截止 2026-06-03
- xG 数据：StatsBomb 已回填
- 新闻信号：0 条（本次未采集到有效信号）

---

## 预测不确定性来源

1. 球员情报：仅 2 条手动记录（人工录入，非自动采集），可能遗漏重要信息
2. 赔率数据：本次未成功拉取，模型缺少市场校准
4. 新闻信号：0 条自动采集，赛前情报依赖纯手动注入
