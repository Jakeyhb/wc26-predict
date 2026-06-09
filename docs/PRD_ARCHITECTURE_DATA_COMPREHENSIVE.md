# WC26 Predict — 完整项目文档

> ⚠️ **本文档可能已过时。** 版本 V2.8.0-selfevolved 中描述的权重值（FRIENDLY_V3、BEL-TUN 单场适应）已在 V2.9.0-conservative 中回滚。当前权威状态见 [`CURRENT_STATUS.md`](CURRENT_STATUS.md)。

## PRD · 系统架构 · 预测方法论 · 数据源

**版本**: V2.8.0-selfevolved（已过时）  
**当前版本**: V2.9.0-conservative  
**生成日期**: 2026-06-07  
**用途**: 项目移交、AI 审查、技术尽调

---

## 目录

1. [项目概述](#1-项目概述)
2. [产品需求文档 (PRD)](#2-产品需求文档-prd)
3. [系统架构](#3-系统架构)
4. [预测方法论](#4-预测方法论)
5. [数据源完整清单](#5-数据源完整清单)
6. [自进化学习系统](#6-自进化学习系统)
7. [技术栈](#7-技术栈)
8. [部署与运维](#8-部署与运维)
9. [测试与质量保障](#9-测试与质量保障)
10. [附录：关键文件索引](#10-附录关键文件索引)

---

## 1. 项目概述

### 1.1 项目定位

**WC26 Predict** 是一个面向 2026 年 FIFA 世界杯的专业足球比赛预测系统。它融合了四种独立的统计模型（Dixon-Coles 双变量泊松、XGBoost 增强器、Elo 评级、Pi 评级），通过顺序融合图（FusionGraph）将多模型输出合成为单一概率预测，并可选地引入实时市场赔率校正、天气数据、DeepSeek V4 Pro 大语言模型 AI 分析。

### 1.2 核心价值主张

| 维度 | 描述 |
|------|------|
| **多模型融合** | 4 模型顺序融合，非简单投票，带有效权重推导 |
| **0-token 基础推理** | 纯统计模型推理（artifact pipeline），不依赖 LLM 即可产出概率预测 |
| **竞争感知权重** | 自动检测赛事类型（世界杯/欧冠/联赛/友谊赛），使用对应优化的模型权重 |
| **影子市场模式** | 市场赔率默认仅记录不融合，防止早期模型被市场噪声污染 |
| **三层安全合规** | 内部研究 / 创作者安全 / 公开发布，自动过滤博彩敏感内容 |
| **赛后自进化** | 每场比赛后自动归因各模型误差，优化未来预测权重 |

### 1.3 适用场景

1. **足球内容创作者** — 生成赛前分析、视频脚本、社交媒体文案
2. **足球数据分析师** — 概率校准评估、模型性能追踪
3. **教练团队** — 对手实力评估、xG 预期进球分析
4. **学术研究** — 多模型融合方法论、预测市场对比研究

---

## 2. 产品需求文档 (PRD)

### 2.1 功能需求

#### F1: 比赛预测引擎

- **F1.1** 单场预测: 输入主队、客队、赛事、场地信息，输出胜平负概率、xG、最可能比分
- **F1.2** 增强预测: 自动拉取市场赔率、天气、生成 AI 分析
- **F1.3** 批量预测: 支持批量运行多场比赛预测
- **F1.4** 预测模式: baseline (仅DC) / standard (DC+Enhancer+Elo) / full (全模型) / research-full (含 Weibull)

#### F2: Dashboard 可视化

- **F2.1** 概率仪表盘: 交互式概率展示，含模型分歧诊断
- **F2.2** 模型分解: 各模型独立预测可视化对比
- **F2.3** 融合图: 每一步融合步骤的前后概率变化
- **F2.4** 管线状态: 模型加载状态、性能耗时、风险标签
- **F2.5** WC26 赛程: 完整 48 队赛程表 + 球队硬事实
- **F2.6** 数据库浏览器: 浏览所有 DB 表内容
- **F2.7** 锦标赛模拟器: 蒙特卡洛模拟 WC26 淘汰赛
- **F2.8** 创作者模式: 安全合规的内容输出

#### F3: 赛后复盘

- **F3.1** 预测质量评估: Brier Score / Log Loss / RPS / 方向准确度
- **F3.2** 7 级评级: A+ (精确命中) 到 F (严重偏差)
- **F3.3** 模型误差归因: 每模型的边际贡献 (Leave-One-Out)
- **F3.4** AI 复盘: DeepSeek V4 Pro 生成赛后分析

#### F4: 自进化

- **F4.1** 赛后模型误差归因
- **F4.2** 信号准确性追踪
- **F4.3** 市场分歧记录
- **F4.4** 上下文性能矩阵更新
- **F4.5** 权重自动优化

#### F5: 内容生成

- **F5.1** 赛前分析文章 (300-400 字中文)
- **F5.2** 视频脚本 (含开场、数据分析、战术要点、结语)
- **F5.3** 社交媒体文案

#### F6: 安全合规

- **F6.1** 三层输出策略: internal_research / creator_safe / public_safe
- **F6.2** 博彩禁词过滤: 自动扫描替换投注相关术语
- **F6.3** 概率隐藏模式: public_safe 模式隐藏所有概率值和 xG

### 2.2 非功能需求

| 类别 | 需求 |
|------|------|
| **性能** | 单场预测 < 10s（不含 LLM），< 30s（含 LLM） |
| **可用性** | Dashboard 9 页全部正常工作，118 测试通过 |
| **可扩展性** | 新模型插入到 FusionGraph 仅需添加一个 fusion step |
| **可靠性** | 市场/天气/LLM 失败时优雅降级，不影响核心预测 |
| **安全** | API Key 零泄露，.env 不入版本控制，凭证不出现于输出 |

### 2.3 用户角色

| 角色 | 权限 | 主要功能 |
|------|------|----------|
| **内部研究者** | 完整访问 | 所有概率、权重、市场数据、DB 查询 |
| **内容创作者** | 中等访问 | 概率 + AI 分析，无博彩术语，无原始赔率 |
| **普通观众** | 受限访问 | 仅方向性分析，无概率数字，无 xG |

---

## 3. 系统架构

### 3.1 架构总览图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         数据源层                                      │
│                                                                      │
│  football-data.org   StatsBomb    OpenFootball    Open-Meteo         │
│  The Odds API        apifootball.com   API-Sports                   │
│  Event Registry      GDELT           RSS Feeds                       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ ETL / Ingestion
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      数据存储层                                       │
│                                                                      │
│  ┌─────────────────────┐   ┌─────────────────────┐                  │
│  │  SQLite (开发)       │   │  PostgreSQL (生产)   │                  │
│  │  local_stage2.db     │   │  + pgvector          │                  │
│  └─────────────────────┘   └─────────────────────┘                  │
│                                                                      │
│  模型表: matches, teams, match_results, players                      │
│  预测表: prediction_runs, prediction_snapshots                       │
│  信号表: news_articles, news_signals, manual_events                  │
│  学习表: prediction_learning_log, signal_track_record                │
│  权重表: model_weight_config, context_performance_matrix             │
│  市场表: market_odds, market_divergence_log                          │
│  反馈表: feedback                                                    │
│  内容表: content_articles, article_evidence                          │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      离线训练层                                       │
│                                                                      │
│  train_models.py                                                     │
│  ├── Dixon-Coles MLE 拟合 → dc.pkl                                   │
│  ├── TabularMatchEnhancer (HistGradientBoosting) → enhancer.joblib   │
│  ├── Elo 历史回测 → elo.json                                         │
│  ├── Pi Rating 计算 → pi.json                                        │
│  ├── Weibull Copula (可选) → weibull.pkl                             │
│  └── 训练 DataFrame → national_finished_matches.pkl                  │
│                                                                      │
│  输出目录: backend/artifacts/                                         │
│    ├── model_registry.json                                           │
│    ├── models/     (dc.pkl, enhancer.joblib, weibull.pkl)            │
│    ├── ratings/    (elo.json, pi.json)                               │
│    └── dataframes/ (national_finished_matches.pkl)                   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ 加载预训练模型 (无 .fit() 调用)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       推理引擎层                                      │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              prediction_core.py (Artifact Pipeline)            │   │
│  │                                                                │   │
│  │  输入: home_team, away_team, competition, is_neutral, mode    │   │
│  │                                                                │   │
│  │  Step 1: 加载 Artifacts (dc.pkl, enhancer.joblib, ...)        │   │
│  │  Step 2: 加载 WeightConfig (竞争感知权重)                      │   │
│  │  Step 3: Dixon-Coles 预测                                     │   │
│  │  Step 4: TabularMatchEnhancer 预测 → fuse DC+Enhancer          │   │
│  │  Step 5: Elo 预测 → fuse +Elo                                  │   │
│  │  Step 6: Pi-Rating 预测 → fuse +Pi                             │   │
│  │  Step 7: (可选) Weibull → fuse +Weibull                       │   │
│  │  Step 8: FusionGraph 诊断 + Renormalize                        │   │
│  │                                                                │   │
│  │  输出: {home_win_prob, draw_prob, away_win_prob,               │   │
│  │          home_xg, away_xg, top_scores, fusion_graph, ...}     │   │
│  └──────────────────────────┬───────────────────────────────────┘   │
│                             │                                        │
│                             ▼                                        │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │          prediction_enhanced.py (增强预测包装器)                │   │
│  │                                                                │   │
│  │  Step 1: 运行 artifact pipeline (以上)                         │   │
│  │  Step 2: 拉取市场赔率 → 计算分歧 → 混合 (max 25%)             │   │
│  │  Step 3: 拉取天气 → 影响标签                                  │   │
│  │  Step 4: DeepSeek V4 Pro → 赛前分析+视频脚本+社交媒体文案     │   │
│  │  Step 5: 组装 EnhancedPredictionResult                         │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  prediction_orchestrator.py (生产级异步编排)                    │   │
│  │  - Celery Beat 定时触发                                        │   │
│  │  - T-24h / T-3h / lineup_confirmed 三级运行                    │   │
│  │  - 含信号调整、伤病、阵容探针                                   │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        合规过滤层                                     │
│                                                                      │
│  output_policy.py                                                    │
│  ├── Policy.INTERNAL_RESEARCH  → 全量输出                           │
│  ├── Policy.CREATOR_SAFE       → 无博彩术语, 无原始赔率              │
│  └── Policy.PUBLIC_SAFE        → 无概率, 无xG, 无比分预测            │
│                                                                      │
│  public_safety_filter.py → 禁词扫描 + 替换                           │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │  FastAPI      │  │  Streamlit   │  │  CLI Scripts │
    │  (8 Routers)  │  │  Dashboard   │  │  (48 scripts)│
    │              │  │  (9 Pages)   │  │              │
    └──────┬───────┘  └──────────────┘  └──────────────┘
           │
           ▼
    ┌──────────────┐
    │  React 18     │
    │  Frontend     │
    │  (TypeScript) │
    └──────────────┘
```

### 3.2 核心组件说明

#### 3.2.1 统计模型层 (4+1 模型)

| 序号 | 模型 | 文件 | 类型 | 数学基础 |
|------|------|------|------|----------|
| 1 | **Dixon-Coles** | `dixon_coles.py` | 双变量泊松 | MLE 估计 attack/defense + rho (进球相关性) |
| 2 | **TabularMatchEnhancer** | `tabular_match_model.py` | 梯度提升机 | HistGradientBoosting 分类器, 特征: 近期进球/状态/休息天数/主客场 |
| 3 | **Elo Rating** | `elo_ratings.py` | 评级系统 | K-Factor + 主场优势 + 竞争权重 + logistic 平局概率 |
| 4 | **Pi Rating** | `pi_ratings.py` | 评级系统 | 替代评级系统, 独立于 Elo |
| 5 | **Weibull Copula** | `weibull_model.py` | Copula 模型 | Weibull 分布对进球分布建模 (可选/研究模式) |

#### 3.2.2 融合引擎

- **FusionGraph** (`fusion_graph.py`): 顺序融合图, 记录每步变换
- **融合链路**: DC → +Enhancer (1-dc) → +Elo → +Pi → 归一化
- **有效权重推导**: 
  ```
  dc_effective       = dc × (1-elo) × (1-pi)
  enhancer_effective = (1-dc) × (1-elo) × (1-pi)
  elo_effective      = elo × (1-pi)
  pi_effective       = pi
  ```
- **模型分歧**: 所有模型对的主场胜率绝对差的最大值

#### 3.2.3 权重管理 (`weights.py`)

单一真相源。4 级优先级:

1. **友谊赛强制**: 检测到 "friendly" → 使用 FRIENDLY 权重 (V2.8)
2. **数据库自动优化**: 从 `model_weight_config` 表读取 RPS 优化权重
3. **赛事感知默认**: 世界杯 0.55/0.25/0.05/0.05, 欧冠决赛 0.42/0.30/0.08/0.12
4. **通用默认**: 联赛默认 0.50/0.30/0.05/0.05

当前 V2.8 权重配置:

| 赛事 | DC | Enhancer | Elo | Pi | Weibull | Market Max |
|------|-----|----------|-----|-----|---------|------------|
| 世界杯 | 0.55 | 0.25 | 0.05 | 0.05 | 0.10 | 0.10 |
| 欧冠决赛 | 0.42 | 0.30 | 0.08 | 0.12 | 0.08 | 0.08 |
| 欧冠淘汰赛 | 0.45 | 0.28 | 0.07 | 0.10 | 0.10 | 0.10 |
| 联赛 | 0.50 | 0.30 | 0.05 | 0.05 | 0.10 | 0.10 |
| **友谊赛 V3** | **0.18** | **0.18** | **0.24** | **0.28** | **0.12** | **0.10** |

> 友谊赛 V3 权重依据: 赛后复盘显示 Enhancer 在友谊赛中过度拟合 (BEL-TUN: 突尼斯 65.4% → 实际比利时 5-0), Elo 和 Pi 对方向判断更准确。

#### 3.2.4 市场数据层

- **提供商**: The Odds API / apifootball.com / API-Sports (Football API)
- **Vig 去除**: 比例归一化 / Shin / Power 三种方法可选
- **共识聚合**: 多提供商加权平均
- **影子模式**: 默认仅记录分歧, 不混合到预测中 (防早期污染)
- **触发条件**: 模型-市场分歧 > 12pp 时发出风险标签
- **混合上限**: 最大 25% 市场权重, 最小 5%

#### 3.2.5 LLM 智能层

- **模型**: DeepSeek V4 Pro
- **生成内容**: 赛前分析文章 (300-400 字) + 视频脚本 + 社交媒体文案
- **信号提取**: 从新闻文章中提取结构化信号 (伤病/阵容/教练/士气)
- **失败容错**: LLM 调用失败不影响核心预测, 使用模板备选

### 3.3 模块目录结构

```
backend/
├── app/
│   ├── main.py                  # FastAPI 入口
│   ├── config.py                # Pydantic Settings (.env 加载)
│   ├── database.py              # Async SQLAlchemy + pgvector
│   ├── routers/                 # 8 个 API 路由
│   ├── models/                  # 28 个 SQLAlchemy 模型
│   ├── schemas/                 # Pydantic 请求/响应模式
│   ├── services/                # 核心服务层 (见下方)
│   │   ├── prediction_core.py   # Artifact 推理核心
│   │   ├── prediction_enhanced.py # 增强预测包装
│   │   ├── prediction_pipeline.py # 可训练管线
│   │   ├── prediction_orchestrator.py # Celery 编排
│   │   ├── dixon_coles.py       # Dixon-Coles 模型
│   │   ├── tabular_match_model.py # XGBoost 增强器
│   │   ├── elo_ratings.py       # Elo 评级系统
│   │   ├── pi_ratings.py        # Pi 评级系统
│   │   ├── weibull_model.py     # Weibull Copula
│   │   ├── fusion_graph.py      # 顺序融合图
│   │   ├── weights.py           # 权重配置 (单一来源)
│   │   ├── postmatch.py         # 赛后评估引擎
│   │   ├── learning_engine.py   # 自进化引擎
│   │   ├── market/              # 市场数据子包
│   │   ├── llm/                 # LLM 子包 (DeepSeek)
│   │   ├── weather_service.py   # Open-Meteo 天气
│   │   ├── signal_adjuster.py   # 信号调整
│   │   ├── context_adjuster.py  # 上下文调整
│   │   ├── calibration.py       # Isotonic 概率校准
│   │   ├── output_policy.py     # 三层输出策略
│   │   └── ...
│   ├── utils/                   # 工具函数
│   └── workers/                 # Celery 任务
├── dashboard/                   # Streamlit Dashboard
│   ├── home.py                  # 入口页 (原名 app.py, 改名解决命名冲突)
│   ├── pages/                   # 9 个子页面
│   │   ├── 01_Overview.py
│   │   ├── 02_Match_Prediction.py
│   │   ├── 03_Match_Context.py
│   │   ├── 04_WC26_Schedule.py
│   │   ├── 05_Teams_Facts.py
│   │   ├── 06_Database_Explorer.py
│   │   ├── 07_Tournament_Simulator.py
│   │   ├── 08_Creator_Mode.py
│   │   └── 09_Postmatch_Review.py
│   ├── components/              # 可视化组件
│   ├── db.py                    # 只读数据库层
│   └── dashboard_config.py      # Dashboard 配置
├── scripts/                     # 48 个 CLI 脚本
├── tests/                       # 11 个测试文件 (118 tests)
├── artifacts/                   # 预训练模型存储
│   ├── model_registry.json
│   ├── models/
│   ├── ratings/
│   └── dataframes/
├── data/
│   └── local_stage2.db          # SQLite 开发数据库
└── alembic/                     # DB 迁移
```

### 3.4 前端架构 (`apps/web/`)

- **框架**: React 18 + TypeScript + Vite + Tailwind CSS
- **路由**: React Router
- **状态管理**: React Query (服务端状态) + Context (UI 状态)
- **API 通信**: 通过 `src/lib/api.ts` 调用 FastAPI 后端
- **构建工具**: Vite (HMR 开发, Rollup 生产打包)

---

## 4. 预测方法论

### 4.1 模型详解

#### 4.1.1 Dixon-Coles 模型

**类别**: 双变量泊松回归模型  
**用途**: 基线概率预测, 产出胜平负概率 + xG + 比分分布

**数学原理**:

Dixon-Coles (1997) 模型假定主客队进球数服从双变量泊松分布:

```
P(X=x, Y=y) = τ_{λ,μ,ρ}(x,y) × Poisson(x|λ) × Poisson(y|μ)
```

其中:
- `λ = exp(attack_home + defense_away + home_advantage)` (主队进球强度)
- `μ = exp(attack_away + defense_home)` (客队进球强度)
- `τ` 是低比分修正项 (rho 参数捕捉 0-0, 1-0, 0-1, 1-1 的依赖结构)

**参数估计**: 通过 MLE (最大似然估计) 拟合历史比赛数据, 估计每个球队的 attack/defense 参数和全局 rho。

**输出**:
- 胜平负概率 (通过双变量泊松 PMF 累加)
- xG (预期进球) = λ 和 μ
- 比分矩阵 (全部分数的概率分布)
- Top-N 最可能比分

#### 4.1.2 TabularMatchEnhancer (表格匹配增强器)

**类别**: 梯度提升树分类器 (HistGradientBoosting)  
**用途**: 第二层预测, 基于表格特征的机器学习模型

**特征工程** (输入特征):

| 特征类别 | 具体特征 |
|----------|----------|
| **近期状态** | 过去 5/10 场比赛的进球数、失球数、胜率 |
| **实力差距** | Elo 差值、FIFA 排名差、attack/defense 强度差 |
| **休息因素** | 距离上一场比赛的天数 |
| **场地因素** | 是否中立场地 |
| **赛事权重** | 比赛重要性 (世界杯 > 友谊赛) |
| **对阵历史** | 历史交锋记录统计 |

**输出**: 胜平负概率 — 作为 DC 输出的**校正层**, 而非独立预测。

#### 4.1.3 Elo 评级系统

**类别**: 动态评级系统  
**用途**: 基于历史战绩的球队实力估计

**数学原理**:

标准 Elo 扩展 (K-factor + 竞争权重 + 主场调整):

```
P(home_win) = 1 / (1 + exp(-(ΔElo + home_advantage) / σ))
P(draw) = f(P(home_win))  // logistic-based draw prob (kappa-Davidson)
```

**更新规则**:
```
Elo_new = Elo_old + K × competition_weight × (Actual - Expected)
```

其中 K 值根据比赛重要性动态调整 (世界杯 > 欧冠 > 联赛 > 友谊赛)。

#### 4.1.4 Pi 评级系统

**类别**: 独立评级系统  
**用途**: Elo 的替代/补充视角

基于不同方法论计算球队实力的独立评级系统, 避免单一评级系统的系统性偏差。

#### 4.1.5 Weibull Copula 模型 (可选/研究用)

**类别**: Copula 依赖模型  
**用途**: 对主客队进球相关性进行更精细的建模

仅在 `research-full` 模式下启用。Weibull 分布对各队进球边缘分布单独建模, 再通过 copula 连接。

### 4.2 融合算法

#### 顺序融合 (非简单加权平均)

```
# Step 1: DC + Enhancer
fused = DC × dc_weight + Enhancer × (1 - dc_weight)

# Step 2: + Elo
fused = fused × (1 - elo_weight) + Elo × elo_weight

# Step 3: + Pi
fused = fused × (1 - pi_weight) + Pi × pi_weight

# Step 4: (可选) + Weibull
fused = fused × (1 - wb_weight) + Weibull × wb_weight

# 归一化
fused = fused / sum(fused)
```

#### 有效权重推导

展开顺序融合链, 得到每个模型的**实际贡献权重**:

| 模型 | 有效权重公式 | 世界杯示例 |
|------|-------------|-----------|
| DC | `dc × (1-elo) × (1-pi)` | 0.55 × 0.95 × 0.95 = 0.496 |
| Enhancer | `(1-dc) × (1-elo) × (1-pi)` | 0.45 × 0.95 × 0.95 = 0.406 |
| Elo | `elo × (1-pi)` | 0.05 × 0.95 = 0.048 |
| Pi | `pi` | 0.05 |

**关键性质**: 四个有效权重之和始终为 1.0。

### 4.3 市场赔率融合

#### Vig 去除

博彩公司赔率包含 "vig" (抽水), 需要先去除:

1. **比例归一化**: `p_i = (1/o_i) / Σ(1/o_j)` (最简单)
2. **Shin 方法**: 迭代估计内部交易者比例 z (较准确)
3. **Power 方法**: `p_i = (1/o_i)^k / Σ(1/o_j)^k` (k < 1)

#### 融合策略

- **触发**: 仅当模型-市场分歧 > 12pp 时报警, 不强制混合
- **混合**: `final = (1-w) × model + w × market`, 其中 `w ∈ [0.05, 0.25]`
- **默认影子模式**: 市场数据仅记录, 不参与预测

### 4.4 天气数据

- **数据源**: Open-Meteo 免费 API (无需 API Key)
- **获取内容**: 温度 (°C), 风速 (km/h), 湿度 (%), 天气描述, 降水量
- **影响评估**:
  - 高温 (>30°C): 比赛节奏下降
  - 强风 (>30 km/h): 长传准确度下降
  - 降雨: 场地湿滑, 进球可能减少
  - 极端天气: 触发 confidence_penalty

### 4.5 LLM 分析生成

#### 提示工程

三种独立的系统提示模板:

1. **赛前分析**: 专业足球分析师视角, 含市场数据、天气、球队背景
2. **视频脚本**: 适合短视频口播, 含开场白、数据段落、战术要点、结语
3. **社交媒体文案**: 简短的微博/小红书风格, 含概率亮点

#### 安全设计

- LLM 提示中不包含原始 API Key
- 输出经过 `output_policy.py` 二次过滤
- 所有概率在上屏前重新验证范围 [0,1]

---

## 5. 数据源完整清单

### 5.1 历史比赛数据 (模型训练)

| 数据源 | 接入方式 | 数据类型 | 用途 |
|--------|----------|----------|------|
| **football-data.org** | REST API (API Key) | 国际/俱乐部比赛结果、球队信息 | 主要训练数据 |
| **StatsBomb Open Data** | 公开数据集 (GitHub) | 历史 xG、传球、射门位置 | xG 校准、基础率 |
| **OpenFootball** | CSV 文件导入 | 国际比赛历史 (1872-至今) | Elo/Pi 回测 |

### 5.2 实时数据 (预测增强)

| 数据源 | 接入方式 | 数据类型 | 用途 |
|--------|----------|----------|------|
| **The Odds API** | REST API (API Key) | 赛前赔率 (1X2, 多家博彩公司) | 市场共识概率 |
| **apifootball.com** | REST API (API Key) | 赔率 + 比赛数据 | 备用市场数据 |
| **API-Sports** | REST API (API Key) | 赔率 + 阵容 + 伤病 | 第三来源 |
| **Open-Meteo** | REST API (免费) | 天气预报 (7 天) | 天气影响评估 |

### 5.3 新闻与情报 (信号提取)

| 数据源 | 接入方式 | 数据类型 | 用途 |
|--------|----------|----------|------|
| **Event Registry** | REST API (API Key) | 结构化新闻 | 伤病/阵容/教练信号 |
| **GDELT Project** | REST API (免费) | 全球事件数据库 | 补充新闻信号 |
| **RSS Feeds** | RSS 解析 | 体育新闻源 | 新闻监控 |

### 5.4 硬事实数据 (预置)

| 数据 | 来源 | 内容 |
|------|------|------|
| **WC26 赛程** | FIFA 官方公告 → 脚本导入 | 48 队分组、赛程、开球时间 |
| **球队信息** | FIFA + 公开数据 | 48 队名称、FIFA 代码、所属洲联合会 |
| **球队实力事实** | `data/team_tournament_status.json` | 排名、预选赛成绩、阵容价值 |
| **球员数据** | 公开转会市场数据 | 关键球员、历史数据 |

### 5.5 数据管道 (ETL)

```
Historical data (CSV/API)
        │
        ▼
  import_openfootball_internationals.py  ← OpenFootball CSV
  football_data_service.py               ← football-data.org API
  statsbomb_service.py                   ← StatsBomb GitHub
        │
        ▼
  ┌──────────────────┐
  │  matches 表       │
  │  match_results 表 │
  │  teams 表         │
  └──────┬───────────┘
         │
         ▼
  train_models.py
  ├── 读取所有 finished 比赛
  ├── 拟合 DC 参数 (MLE)
  ├── 训练 Enhancer (HistGradientBoosting)
  ├── 回测 Elo 评级
  ├── 计算 Pi 评级
  └── 保存 artifacts/
         │
         ▼
  artifacts/
  ├── models/dc.pkl
  ├── models/enhancer.joblib
  ├── ratings/elo.json
  ├── ratings/pi.json
  └── dataframes/national_finished_matches.pkl
```

---

## 6. 自进化学习系统

### 6.1 赛后评估指标

每场比赛后计算以下指标:

| 指标 | 公式 | 范围 | 说明 |
|------|------|------|------|
| **Brier Score** | `Σ(p_i - o_i)² / 3` | [0, 1] | 概率校准综合评分, 0=完美 |
| **Log Loss** | `-log(p_outcome)` | [0, ∞) | 对数评分规则, 越接近 0 越好 |
| **RPS** | `Σ(CumPred - CumActual)² / 2` | [0, 1] | 排序概率评分 (3 类有序) |
| **方向准确度** | 最高概率项 = 实际结果? | {0, 1} | 胜平负方向是否正确 |
| **比分命中** | 最可能比分包含实际比分? | {0, 1} | 精确比分预测 |
| **xG 误差** | `\|ΔxG - ΔGoals\|` | [0, ∞) | 进球差预测误差 |

### 6.2 7 级评级体系

| 评级 | 条件 | 含义 |
|------|------|------|
| **A+** | 精确命中比分 + 高置信度 | 模型完美预测 |
| **A** | 方向正确 + 比分在 Top-3 | 模型表现优秀 |
| **B+** | 方向正确但比分未命中 | 方向判断准确 |
| **B** | 方向错误但比分在 Top-3 | 概率校准仍有参考价值 |
| **C** | 方向错误, Brier < 0.25 | 概率分布保守但可接受 |
| **D** | Brier ≥ 0.25 | 明显偏差 |
| **F** | Brier ≥ 0.35 + 高置信错误方向 | 严重偏差 |

### 6.3 模型误差归因

使用 **Leave-One-Out (留一法)** 计算每个模型的边际贡献:

```
对于每个模型 M ∈ {DC, Enhancer, Elo}:
  Brier_without_M = 融合(所有模型 \ {M}) 预测的 Brier
  M_marginal = Brier_without_M - Brier_final

  正值 = 模型有帮助 (移除后预测变差)
  负值 = 模型有损害 (移除后预测变好)
```

### 6.4 权重自进化

**触发**: 每次赛后复盘完成后

**流程**:
1. 计算每模型 Brier Score
2. 计算边际贡献
3. 网格搜索最优权重组合
4. 更新 `weights.py` 中对应赛事类型的权重
5. 递增版本号
6. 记录进化日志到 `prediction_learning_log` 表

**V2.7 → V2.8 实战案例 (BEL-TUN 友谊赛)**:

| 模型 | 比利时预测 | 突尼斯预测 | Brier | 旧权重 | 新权重 |
|------|-----------|-----------|------|--------|--------|
| Pi | 55.8% | 24.4% | 0.098 🏆 | 0.16 | **0.28** ↑ |
| Elo | 50.6% | 37.6% | 0.133 🥈 | 0.02 | **0.24** ↑ |
| DC | 42.0% | 26.5% | 0.169 🥉 | 0.28 | **0.18** ↓ |
| Enhancer | 18.9% | 65.4% | 0.370 ❌ | 0.42 | **0.18** ↓ |

**进化逻辑**: Enhancer 权重从 0.42 降至 0.18 — 因为它以 65.4% 错误地预测突尼斯胜, 实际比利时 5-0 大胜。Elo 和 Pi 正确识别了比利时优势, 权重相应提升。

### 6.5 持续学习组件

| 组件 | 文件 | 功能 |
|------|------|------|
| **LearningEngine** | `learning_engine.py` | 赛后学习主引擎, 协调误差归因+信号追踪+市场日志+上下文矩阵 |
| **SignalTrackRecord** | 模型: `signal_track_record.py` | 追踪每种信号的准确/误判次数, 计算当前权重乘数 |
| **ContextPerformanceMatrix** | 模型: `context_performance_matrix.py` | 按赛事/阶段/场地追踪 Brier 性能 |
| **MarketDivergenceLog** | 模型: `market_divergence_log.py` | 记录模型-市场分歧时的胜负方 |
| **PredictionLearningLog** | 模型: `prediction_learning_log.py` | 每次预测的学习日志 (含边际贡献) |

### 6.6 信号权重动态调整

信号 (伤病/阵容/战术) 的权重随准确性动态变化:

```
weight_multiplier = 0.4 + 0.6 × accuracy_rate
accuracy_rate = accurate / (accurate + misleading)

范围: [0.4, 1.0]
- 完美信号 (100%): multiplier = 1.0 (全权重)
- 完全失败 (0%): multiplier = 0.4 (60% 削减)
- 最少 5 次评分后才更新
```

---

## 7. 技术栈

### 7.1 后端

| 技术 | 版本 | 用途 |
|------|------|------|
| **Python** | 3.11+ | 主语言 |
| **FastAPI** | latest | REST API 框架 |
| **SQLAlchemy** | 2.0+ (async) | ORM |
| **Pydantic** | 2.x | 数据校验 / Settings |
| **SQLite** | 3 | 开发数据库 |
| **PostgreSQL** | 15+ | 生产数据库 (含 pgvector) |
| **Redis** | 7+ | 缓存 / Celery Broker |
| **Celery** | 5.x | 异步任务队列 |
| **Streamlit** | latest | Dashboard |

### 7.2 机器学习

| 库 | 用途 |
|----|------|
| **scikit-learn** | HistGradientBoosting 分类器 |
| **NumPy** | 数值计算 |
| **pandas** | 数据操作 |
| **SciPy** | MLE 优化 (Dixon-Coles) |
| **joblib** | 模型序列化 |
| **pickle** | 模型序列化 |

### 7.3 前端

| 技术 | 用途 |
|------|------|
| **React 18** | UI 框架 |
| **TypeScript** | 类型安全 |
| **Vite** | 构建工具 |
| **Tailwind CSS** | 样式 |
| **React Query** | 服务端状态 |

### 7.4 外部 API

| 服务 | 类型 |
|------|------|
| **DeepSeek V4 Pro** | LLM (AI 分析 + 信号提取) |
| **Open-Meteo** | 免费天气 API |
| **The Odds API** | 博彩赔率 |
| **apifootball.com** | 博彩赔率 + 比赛数据 |
| **API-Sports (Football API)** | 赔率 + 阵容 + 伤病 |
| **football-data.org** | 历史比赛数据 |
| **Event Registry** | 结构化新闻 |
| **GDELT** | 全球事件 |

---

## 8. 部署与运维

### 8.1 部署模式

| 环境 | 配置 |
|------|------|
| **开发** | SQLite + `uvicorn` 单进程 + Streamlit `streamlit run` |
| **生产** | PostgreSQL + Redis + Celery Worker + Celery Beat + Nginx + Docker Compose |

### 8.2 Docker Compose 服务

```yaml
services:
  postgres:   # PostgreSQL 15 + pgvector
  redis:      # Redis 7 (broker + cache)
  celery:     # Celery Worker (异步预测)
  backend:    # FastAPI (uvicorn)
```

### 8.3 Dashboard 运行

```bash
cd backend
streamlit run dashboard/home.py
```

Dashboard 入口是 `home.py` (原名 `app.py`, 重命名解决了与 `backend/app/` 包的命名冲突)。

### 8.4 模型训练

```bash
cd backend
python scripts/train_models.py
```

产出物: `backend/artifacts/models/`, `backend/artifacts/ratings/`, `backend/artifacts/dataframes/`

### 8.5 预测脚本

```bash
# 单场 artifact 预测
python scripts/predict_match.py --home Belgium --away Tunisia --competition "International Friendly" --neutral

# 增强预测 (含市场+天气+LLM)
python -c "from app.services.prediction_enhanced import run_enhanced_prediction; ..."

# 赛后复盘
python scripts/postmatch_review.py --home Belgium --away Tunisia --home-goals 5 --away-goals 0 --ai-review
```

---

## 9. 测试与质量保障

### 9.1 测试覆盖

11 个测试文件, 118 个测试用例:

| 测试文件 | 覆盖内容 |
|----------|----------|
| `test_prediction_pipeline.py` | 管线集成测试 |
| `test_dixon_coles.py` | DC 模型数学正确性 |
| `test_fusion_graph.py` | 融合图正确性 |
| `test_market_provider_selection.py` | 提供商选择逻辑 |
| `test_news_signal_validation.py` | 信号验证 |
| `test_weights_config.py` | 权重配置 |
| `test_output_policy.py` | 输出过滤 |
| `test_fact_check.py` | 事实核查 |
| `test_wc26_closure.py` | WC26 闭包检查 |
| `test_dashboard_db.py` | Dashboard 数据库层 |
| `test_dashboard_prediction.py` | Dashboard 预测流 |

### 9.2 审计脚本

| 脚本 | 检查内容 |
|------|----------|
| `audit_data_freshness.py` | 数据时效性 |
| `audit_prediction_pipeline_consistency.py` | 管线一致性 |
| `audit_public_outputs_no_odds.py` | 公共输出合规 |
| `audit_weights_consistency.py` | 权重一致性 |
| `health_check.py` | 17 项健康检查 |
| `verify_env.py` | 环境变量验证 |
| `check_market_providers.py` | 市场提供商可用性 |

---

## 10. 附录：关键文件索引

### 10.1 核心预测链路

| 文件 | 行数 | 核心功能 |
|------|------|----------|
| `prediction_core.py` | 583 | Artifact 推理引擎 (4 模型加载 + 融合) |
| `prediction_enhanced.py` | 571 | 增强预测 (市场 + 天气 + LLM) |
| `prediction_pipeline.py` | - | 全管线 (含训练能力 + 3 级缓存) |
| `prediction_orchestrator.py` | - | Celery 异步编排 (T-24h/T-3h/lineup) |
| `fusion_graph.py` | 206 | 顺序融合图 (有效权重 + 模型分歧) |
| `weights.py` | 277 | 权重配置 (单一真相源) |

### 10.2 模型文件

| 文件 | 核心功能 |
|------|----------|
| `dixon_coles.py` | DC 双变量泊松: MLE 拟合 + 预测 |
| `tabular_match_model.py` | HistGradientBoosting 增强器 |
| `elo_ratings.py` | K-Factor Elo 评级 |
| `pi_ratings.py` | Pi 评级 |
| `weibull_model.py` | Weibull Copula |

### 10.3 评估与学习

| 文件 | 核心功能 |
|------|----------|
| `postmatch.py` | Brier/LogLoss/RPS + 7 级评级 |
| `learning_engine.py` | 误差归因 + 信号追踪 + 上下文矩阵 |
| `calibration.py` | Isotonic 概率校准 |

### 10.4 市场数据

| 文件 | 核心功能 |
|------|----------|
| `market/consensus.py` | 多提供商共识聚合 |
| `market/probability.py` | Vig 去除 (比例/Shin/Power) |
| `market/sync_provider.py` | 同步市场数据拉取 |
| `market/leakage_guard.py` | 数据泄露防护 |

### 10.5 安全合规

| 文件 | 核心功能 |
|------|----------|
| `output_policy.py` | 三层输出策略 |
| `public_safety_filter.py` | 禁词扫描 + 替换 |

### 10.6 Dashboard

| 文件 | 核心功能 |
|------|----------|
| `home.py` | Dashboard 入口 |
| `pages/02_Match_Prediction.py` | 单场预测页面 |
| `pages/07_Tournament_Simulator.py` | 蒙特卡洛锦标赛模拟 |
| `pages/08_Creator_Mode.py` | 创作者安全输出 |
| `pages/09_Postmatch_Review.py` | 赛后复盘 Dashboard |
| `components/probability_charts.py` | 概率可视化组件 |
| `components/fusion_graph_view.py` | 融合图可视化 |

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| V2.6.0-enhanced | 2026-06 | 增强预测上线 (市场+天气+LLM) |
| V2.7.0 | 2026-06-06 | 基于 3 场友谊赛复盘的权重进化 |
| V2.8.0-selfevolved | 2026-06-07 | BEL-TUN 5-0 赛后复盘 + FRIENDLY_V3 权重 |

---

*本文档由 Claude Code (DeepSeek V4 Pro) 生成于 2026-06-07。  
项目路径: `D:\hermes agent\2026世界杯分析\`*
