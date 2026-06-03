# WC26 Predict — 产品需求文档 (PRD)

> **⚠ 本文档可能已过期（V1.0 / 2026-06-01）。** 最新权威状态以 [`CURRENT_STATUS.md`](CURRENT_STATUS.md) 为准。

> V1.0 测试版 | 2026-06-01  
> 仓库: github.com/AndyDu0921/wc26-predict

---

## 一、产品概述

### 1.1 产品定位

WC26 Predict 是一款面向 2026 年 FIFA 世界杯的**足球赛前情报分析工具**。输入两支球队，输出一份包含预测概率、比分预测、球队状态和情报分析的结构化 Markdown 报告。

**这不是博彩工具**——不提供赔率对比、盘口分析或投注建议。

### 1.2 目标用户

| 用户类型 | 使用场景 | 使用方式 |
|----------|----------|----------|
| 足球分析师 | 赛前了解球队状态和胜负概率 | Web 前端 / CLI 脚本 |
| 数据工程师 | 批量预测、回测、模型调优 | CLI 脚本 + Python API |
| 普通球迷 | 浏览比赛预测 | Web 前端 |

### 1.3 产品价值

- **量化不确定性**：用数学模型将主观判断转化为可验证的概率
- **透明可追溯**：每个数据点标注来源、Tier 和可靠性，用户可判断信息可信度
- **持续进化**：赛后自动复盘，系统预测能力随时间提升

---

## 二、功能需求

### 2.1 核心功能：单场预测（P0）

**用户故事**：作为分析师，我输入 A 队 vs B 队，得到一份完整的预测报告。

**输入**：
- 主队名称（如 "Argentina"）
- 客队名称（如 "Brazil"）
- 赛事名称（如 "FIFA World Cup 2026"）
- 可选：是否中立场

**输出**（Markdown 报告）：
- 三层融合预测概率（主胜/平局/客胜，百分比）
- Top 3 最可能比分 + 期望进球
- Elo 评分 + 近期 5 场战绩
- 赛前动力因素（联赛排名驱动 / 世界杯小组动力）
- 手动情报事件（伤病、停赛、轮换）
- 数据来源追溯表（每项标注来源、Tier、可靠性）
- 预测不确定性来源

**验收标准**：
- 单场预测时间 ≤ 60 秒
- 预测结果自动入库（prediction_snapshots + prediction_runs）
- 报告保存为 Markdown 文件

**CLI 命令**：
```bash
python scripts/snapshot.py --home "Argentina" --away "Brazil" \
  --competition "FIFA World Cup 2026" --neutral
```

### 2.2 批量预测（P1）

**用户故事**：作为数据工程师，我需要一次性生成所有 upcoming 比赛的预测。

**功能**：
- 按赛事、日期范围筛选比赛
- 批量生成预测 + 汇总统计
- 并发处理以加快速度

**CLI 命令**：
```bash
python scripts/batch_snapshot.py --limit 50 --competition-type national
```

### 2.3 手动情报注入（P0）

**用户故事**：作为分析师，我得知某队核心球员受伤，需要在预测中反映这个信息。

**支持的事件类型**：
- INJURY（伤病）
- SUSPENSION（停赛）
- RETURN（复出）
- LINEUP_CONFIRMED（首发确认）
- LINEUP_RUMOR（首发传闻）
- ROTATION_HINT（轮换信号）
- MOTIVATION（动力因素）
- WEATHER（天气影响）

**CLI 命令**：
```bash
python scripts/add_manual_event.py --team "England" \
  --type INJURY --player "Harry Kane" --severity critical
```

### 2.4 赛后复盘（P0）

**用户故事**：作为系统，每场比赛结束后自动对比预测 vs 实际，更新模型评估。

**功能**：
- 自动查找昨日完赛的比赛
- 匹配对应的预测快照
- 计算 Brier Score / LogLoss
- 按球队、联赛分组统计
- 错误归因到各模型层（DC/Enhancer/Elo/Pi）

**CLI 命令**：
```bash
python scripts/auto_postmatch.py           # 昨天
python scripts/auto_postmatch.py --days 3  # 最近 3 天
```

### 2.5 权重优化（P1）

**用户故事**：作为系统，基于历史预测表现自动调整各模型层的融合权重。

**功能**：
- 读取 postmatch_eval 数据
- 用 Nelder-Mead 优化 RPS (Ranked Probability Score)
- 输出最优权重配置

**CLI 命令**：
```bash
python scripts/optimize_weights.py --dry-run   # 预览
python scripts/optimize_weights.py             # 应用
```

### 2.6 联赛积分榜同步（P1）

**功能**：自动从 football-data.org 拉取五大联赛积分榜，生成 motivation_events（球队动力标签）。

**CLI 命令**：
```bash
python scripts/sync_standings.py
```

### 2.7 球员库管理（P2）

**功能**：
- 从 football-data.org 导入国家队 squad
- 自动分类 importance_level（key/starter/rotation/backup）
- 球员关联校验修复

**CLI 命令**：
```bash
python scripts/seed_players.py           # 导入 16 支种子队
python scripts/_fix_players.py --dry-run # 审计
python scripts/_fix_players.py --fix     # 修复
```

---

## 三、非功能需求

### 3.1 性能

| 指标 | 目标 | 当前 |
|------|------|------|
| 单场预测时间 | ≤ 60s | ~39s |
| 批量预测速度 | ≤ 40s/场 | ~35s/场 |
| 模型训练时间 | ≤ 30s | ~15s (DC + Enhancer) |

### 3.2 可靠性

- 预测失败不应阻断管线（优雅降级）
- 模型依赖缺失时使用 fallback（Pi-Rating → penaltyblog 可选）
- 数据库写入失败不影响预测报告生成
- 市场数据拉取失败不影响基线预测

### 3.3 可维护性

- 所有预测入库，事后可追溯
- 模型参数可版本化（model_artifacts/）
- 功能可通过 feature_flags 开关
- 健康检查命令覆盖 17 项指标

### 3.4 数据质量

- 每个数据点标注来源和可靠度（Tier 1-3）
- 未知/缺失数据显式标记，不静默跳过
- 冷启动球队输出置信度扣除

### 3.5 合规

- **禁止**显示任何赔率数字
- **禁止**提供投注建议
- **禁止**提及博彩平台名称
- 所有 LLM 调用使用 DeepSeek API（中国合规）

---

## 四、用户流程

### 4.1 赛前预测流程

```
管理员获知伤停情报
    │
    ▼
add_manual_event.py 注入事件
    │
    ▼
snapshot.py 运行预测
    │
    ▼
生成 Markdown 报告
    │
    ├── 预测概率 + 比分
    ├── Elo 评分 + 近期战绩
    ├── 动力因素
    ├── 情报事件 (手动注入)
    ├── 数据来源追溯表
    └── 不确定性说明
    │
    ▼
Web 前端查看 / 分享报告
```

### 4.2 赛后复盘流程

```
比赛结束
    │
    ▼
match_results 表写入赛果
    │
    ▼
auto_postmatch.py 自动匹配
    │
    ▼
LearningEngine 错误归因
    │
    ├── prediction_learning_log (Brier + 边际贡献)
    ├── signal_track_record (信号准确率更新)
    ├── market_divergence_log (市场分歧记录)
    └── context_performance_matrix (上下文矩阵)
    │
    ▼
数据累积 ≥ 5 条 → 权重重算
    │
    ▼
optimize_weights.py 优化融合权重
```

### 4.3 三次预测更新

| 时间 | 操作 |
|------|------|
| T-24h | 拉取最新数据，运行 Dawson-Coles |
| T-3h | 重新运行，拉取最新情报/天气/发布会信息 |
| 首发后 | 管理员手动触发第三次更新 |

---

## 五、数据源

### 5.1 已接入

| 来源 | 数据 | 接口 | 限制 |
|------|------|------|------|
| football-data.org | 赛程/比分/积分榜/球队 squad | REST API | 免费 tier, 10 req/min |
| StatsBomb Open Data | 历史比赛 + xG | 一次性导入 | 数据截止 2020 |
| Open-Meteo | 天气预测 | REST API | 免费, 16 天窗口 |
| DeepSeek | LLM 推理 | OpenAI 兼容 API | API key 已配置 |

### 5.2 待接入

| 来源 | 数据 | 原因 |
|------|------|------|
| openfootball | 国家队历史比赛 2000+ 场 | WC26 baseline 需要 |
| Event Registry | 新闻全文 | 无 API key |

---

## 六、版本规划

| 版本 | 目标 | 状态 |
|------|------|------|
| **V1.0 测试版** | 稳定性修复 + 自进化闭环打通 | ✅ 已发布 (2026-06-01) |
| V1.1 | WC26 baseline 完整化 + 34 支弱队 fallback | 📋 计划中 |
| V1.2 | Celery 自动化 + 定时预测 | 📋 计划中 |
| V2.0 | 情报输入闭环 (Event Registry / 爬虫) | 🔮 远期 |

### V1.0 测试版交付清单

- [x] 预测管线（5 层融合）稳定运行
- [x] SignalAdjuster 正确响应手动事件
- [x] 高海拔场馆自动调整
- [x] 赛后自动复盘（64 条学习日志）
- [x] RPS 权重优化（47 条记录）
- [x] snapshot→prediction_runs 双写桥接
- [x] DeepSeek 全链路切换
- [x] 球员关联审计修复
- [x] 架构文档 + PRD

---

## 七、技术约束

| 约束 | 说明 |
|------|------|
| LLM 提供商 | 仅 DeepSeek（不使用 OpenAI/Anthropic/Qwen/Zhipu） |
| 数据库 | SQLite（开发），PostgreSQL（生产可选） |
| Python 版本 | 3.11+ |
| 路径 | Windows 直接路径 或 WSL `/mnt/...` 格式 |
| 前端 | React 18 + Vite，当前重点后端 |

---

## 八、术语表

| 术语 | 全称 | 说明 |
|------|------|------|
| DC | Dixon-Coles | 泊松足球预测模型 (1997) |
| Enhancer | Tabular Match Enhancer | 梯度提升校正模型 (37 特征) |
| Elo | Elo Rating System | 评分系统 (Arpad Elo, 1960) |
| Pi | Pi-Rating | 零中心进球差评分 (Constantinou & Fenton, 2012) |
| RPS | Ranked Probability Score | 排序概率评分 (尊重序数性质) |
| Brier | Brier Score | 概率预测准确度度量 |
| xG | Expected Goals | 期望进球 |
| NLL | Negative Log-Likelihood | 负对数似然 |
| HGB | HistGradientBoosting | 梯度提升分类器 |
| WC26 | World Cup 2026 | 2026 年 FIFA 世界杯 |
