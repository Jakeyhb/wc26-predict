# WC26 Predict — 项目全面评估报告

> 生成日期：2026-06-04 | 版本：V1.7 测试版 | 仓库：github.com/AndyDu0921/wc26-predict

---

## 一、项目概述

WC26 Predict 是一个面向 2026 年 FIFA 世界杯的 AI 足球研究引擎与内容创作工作台。它从零开始，由一个球迷借助 AI 编程工具（Claude Code）构建，历时约 3 个月迭代至 V1.7。

### 定位

**是：** AI 足球研究系统 | 赛前分析工作台 | 模型评估工具 | 数据溯源与报告管线 | 创作者内容助手

**不是：** 博彩系统 | 投注工具 | 赔率平台 | 命中率营销产品 | 比分预测软件

---

## 二、数据规模

| 数据 | 数量 |
|---|---|
| 历史比赛 | 16,861 场 |
| 球队 | 441 支 |
| 球员 | 1,355 名 |
| 预测快照 | 234 次 |
| 新闻文章 | 70 篇 |
| 情报信号 | 6 条（V1.7 新增） |
| 市场赔率记录 | 136 条（The Odds API） |
| 手动事件 | 17 条 |
| 赛后评估 | 48 次 |
| 世界杯小组赛预生成 | 72/72 场 |
| 数据库表 | 33 张 |
| 数据库大小 | 13.3 MB |

---

## 三、系统架构

### 3.1 技术栈

| 层 | 技术 |
|---|---|
| 后端框架 | FastAPI (Python 3.11) |
| 数据库 | SQLite (本地) / PostgreSQL (生产配置存在) |
| LLM | DeepSeek V4 Pro (信号提取 + AI 分析) |
| 前端 | React + Vite + TypeScript |
| 定时任务 | Windows Task Scheduler |
| CI | GitHub Actions |

### 3.2 预测管线

```
数据源 → Dixon-Coles(55%) + TabularEnhancer(25%) → Weibull(10%) → Elo(5%) → Pi-Rating(5%)
                                                                          ↓
                                                                  信号调整层
                                                                          ↓
                                                             市场共识暗影校准
                                                                          ↓
                                                           输出安全过滤 → 报告
```

### 3.3 核心服务模块（47 个 Python 文件）

| 模块 | 行数 | 职责 |
|---|---|---|
| `prediction_orchestrator.py` | 651 | API 驱动预测编排 |
| `dixon_coles.py` | 634 | Dixon-Coles 双变量泊松模型 |
| `tabular_match_model.py` | 539 | TabularMatchEnhancer (HGB) |
| `prediction_pipeline.py` | 490 | 统一预测入口 (Class) |
| `market_calibrator.py` | 471 | 市场共识校准 + 分歧检测 |
| `llm_service.py` | 366 | DeepSeek 适配层 |
| `learning_engine.py` | 336 | 赛后学习 + 权重自动优化 |
| `news_ingest_service.py` | 290 | RSS 新闻摄入 |
| `signal_adjuster.py` | 282 | 信号 → 概率调整 |
| `weights.py` | 206 | 权重配置唯一真相来源 |

### 3.4 脚本工具（38 个 Python 文件）

| 类别 | 关键脚本 |
|---|---|
| 预测生成 | `snapshot.py` (1257行), `fast_predict.py`, `pregenerate_wc26.py` |
| 数据管理 | `seed_2026_schedule.py`, `seed_players.py`, `sync_results.py` |
| 运维 | `daily_ops.py`, `health_check.py`, `auto_postmatch.py` |
| 诊断审计 | `check_market_providers.py`, `audit_weights_consistency.py`, `audit_public_outputs_no_odds.py`, `audit_data_freshness.py` |
| 情报 | `phase_d_extract_5.py`, `news_signal_extractor.py`, `llm_intel_extract.py` |
| 市场 | `fetch_market_odds_api_football.py`, `import_historical_odds_football_data_uk.py` |

### 3.5 数据库核心表

```
matches (16,861) ──── prediction_snapshots (234)
  │                        │
teams (441)          news_articles (70) ── news_signals (6)
  │                        │
players (1,355)     market_odds (136)
                      │
               postmatch_eval (48) ── prediction_learning_log (64)
```

---

## 四、合规与安全架构

### 4.1 三模式输出过滤

| 模式 | 用户 | 允许 | 禁止 |
|---|---|---|---|
| `internal_research` | 维护者/分析师 | 模型概率、校准诊断、市场共识对比 | 公开营销宣称 |
| `creator_safe` | 内容创作者 | 球队背景、数据溯源、不确定性说明 | 赔率、博彩公司、投注语言 |
| `public_safe` | 公众 | 教育性分析、排名、历史趋势 | 赔率、投注、概率宣称、命中率 |

### 4.2 市场数据策略

- 市场共识校准仅用于 **内部研究暗影模式**（shadow mode）
- 公开输出不得出现赔率数字、博彩公司名称、投注术语
- apifootball.com：基础 API 可用，赔率需 $15 addon
- The Odds API：当前唯一可用的市场校准数据源

---

## 五、当前完成度

### 5.1 P0 技术闭环

| 能力 | 状态 | 备注 |
|---|---|---|
| 统一预测管线 | ✅ | PredictionPipeline + 6 入口 |
| 模型注册表 | ✅ | model_registry.py + JSONL |
| 权重配置 | ✅ | weights.py 唯一来源，4/4 入口统一 |
| 市场数据暗影模式 | ✅ | 内部校准，公开隔离 |
| 情报信号管线 | ✅ | 6 条试运行信号 (PENDING) |
| 输出安全过滤 | ✅ | 三模式 + 合规上下文识别 |
| 本地仪表盘 | ✅ | FastAPI + React 前端 |
| 自动化脚本 | ✅ | Windows Task Scheduler 5 任务 |
| CI | ✅ | GitHub Actions (compileall + pytest + audits) |
| 测试 | ✅ | 21 新测试通过 |
| 商业化文档 | ✅ | README + 合规 + 商业 + 安全 + 贡献 |

### 5.2 已知短板

| 优先级 | 问题 | 影响 |
|---|---|---|
| 🔴 P0 | news_signals 仅有 6 条 PENDING | 情报管线数据不足 |
| 🔴 P0 | apifootball.com odds 不可用 | 缺少第二市场数据源 |
| 🟡 P1 | pytest 3 个预存失败 | 测试覆盖不全 |
| 🟡 P1 | venv 缺少部分依赖 | 环境一致性 |
| 🟢 P2 | Dashboard UX 简陋 | 可用但不够好 |
| 🟢 P2 | GBK 编码问题 | 中文 Windows 终端输出乱码 |

---

## 六、版本历史

| 版本 | 日期 | 核心变化 |
|---|---|---|
| V1.5 | 5月底 | DC 性能优化 + 磁盘缓存 + 预生成 |
| V1.6 | 6月初 | 统一入口 + 市场暗影 + 安全过滤 + Dashboard |
| V1.6.1 | 6/4 | P0 闭环 + 模型注册表 + 情报管线 + 自动化 |
| **V1.7** | **6/4** | **Provider 诊断 + 权重审计重写 + CI + 信号试运行** |

---

## 七、后续规划

### Phase F（当前下一步）— 公开演示就绪

- 生成 public-safe 示例报告（3 份）
- 添加 Dashboard 截图
- 准备 GitHub Pages landing page
- 录制 demo 视频素材

### Phase G — Dashboard 与创作者工具

- Dashboard 从 MVP → 可用工具
- 一键生成 creator-safe 报告
- 报告模板库
- Markdown/JSON 导出

### Phase H — 世界杯实战运营

- 注册 Windows 定时任务
- 新闻源扩展（更多 RSS + API）
- 手动情报录入 SOP
- 赛后复盘自动化

### Phase I — 商业化产品化

- 用户认证
- 托管部署
- API 封装
- 付费创作者套餐

---

## 八、2026 世界杯时间线

```
6/4  ← 今天 (V1.7)
6/11 世界杯开幕（倒计时 7 天）
7/19 世界杯决赛
```

**开幕前必须完成：**
1. news_signals 从 6 → 50+ 条真实信号
2. 手动情报录入流程建立
3. 定时任务注册并测试
4. Dashboard 可用性达标

---

## 九、风险与建议

### 核心风险

1. **情报数据不足**：70 篇文章但仅 6 条短信号，赛前情报覆盖不够。建议立即扩展新闻源（FIFA 官方 RSS + 各队官网 + 中文体育媒体）
2. **市场数据源单一**：仅 The Odds API 可用，apifootball.com odds 需付费。建议评估是否购买 $15 addon
3. **测试覆盖不完整**：3 个预存 pytest 失败未修复，无集成测试
4. **环境依赖**：部分 pip 包缺失（penaltyblog, aiohttp），venv 环境需整理

### 建议优先做

1. 手动录入 20+ 条高质量情报信号（伤病、阵容、战术）——数据闭环最重要
2. 修复 3 个 failing tests
3. 补全 venv 依赖
4. 注册 Windows 定时任务
5. 生成 public-safe 示例报告
