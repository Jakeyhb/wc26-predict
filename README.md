# WC26 Predict ⚽

> 一个人，三个月，从零构建的 AI 世界杯预测引擎。
> 16359 行 Python · 16861 场比赛训练 · 5 模型融合 · 赛后自学习闭环

<p align="center">
  <img src="https://img.shields.io/badge/version-v3.2-blue?style=flat-square" alt="version">
  <img src="https://img.shields.io/badge/tests-146%20passed-success?style=flat-square" alt="tests">
  <img src="https://img.shields.io/badge/python-3.11+-blue?style=flat-square" alt="python">
  <img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" alt="license">
  <img src="https://img.shields.io/badge/lines-16359%20Python-informational?style=flat-square" alt="lines">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square" alt="platform">
</p>

---

## 👋 关于作者

Hi，我是 **Andy**，一名独立开发者 + 足球爱好者。

2026 年 3 月，世界杯临近，我决定做一件事：**用代码和数据，构建一个能真正理解足球比赛不确定性的 AI 系统。** 不是赌球工具，不是营销噱头——是一个透明、可审计、可复现的概率预测研究平台。

三个月，每周 40+ 小时的投入，从零开始：

- 啃完了 Dixon & Coles (1997) 论文，实现了双变量泊松模型的矩阵向量化版本
- 通读了 Elo 评级系统、Pi-Rating、Shin (1993) 市场概率去水分公式
- 搭建了完整的 FastAPI + React + Streamlit 全栈架构
- 写下了 16359 行 Python 代码和 146 个测试用例
- 积累了 16861 场历史比赛的训练数据

这是 WC26 Predict，一个**开放研究的 AI 足球预测系统**。我希望它能帮助数据分析师、内容创作者和足球爱好者，用数据和模型来理解比赛，而不是凭感觉下判断。

> 📬 **合作 / 交流 / 反馈**：微信 `AndyDu10`
>
> 如果你对足球数据分析、概率建模或 AI 体育应用感兴趣，欢迎加我聊聊。

---

## 💡 这是什么？

WC26 Predict 专为 **2026 年 FIFA 世界杯**设计，将统计建模、机器学习和实时数据增强融合为一个端到端的预测管线。

```
你的问题：                       系统的回答：
┌─────────────────────┐         ┌──────────────────────────────┐
│ "西班牙 vs 阿根廷     │         │  胜: 38.2%  平: 28.7%  负: 33.1% │
│  谁更可能赢？"        │  ────▶  │  xG: 1.42 / 1.18              │
│                      │         │  最可能比分: 1-1 (12.3%)       │
│ "为什么？"            │  ────▶  │  │
│                      │         │  Dixon-Coles 攻防参数:         │
│ "数据来源可信吗？"     │  ────▶  │    西班牙进攻 0.82 vs 阿根廷防守 -0.15 │
│                      │         │  κ-Elo 评分差: +42 (西班牙优)  │
│ "有没有伤病影响？"     │  ────▶  │  Enhancer 37 维特征综合判断    │
│                      │         │  信号调整: 无重大伤病/阵容信号  │
│ "这个预测准吗？"       │  ────▶  │  等渗校准后置信区间           │
│                      │         │  历史 Brier Score: 0.215      │
└─────────────────────┘         └──────────────────────────────┘
```

**核心理念**：用数据和模型理解足球比赛的不确定性，而非"预测胜负"。

> ⚠️ **本项目是研究工具，不是赌博产品。** 不提供投注建议、不展示博彩赔率、不承诺预测准确率。详见[合规声明](#-合规声明)。

---

## 🏗️ 系统架构

```
                         ┌──────────────────────────┐
                         │        数据源层             │
                         │  ┌──────────────────────┐ │
                         │  │ football-data.org    │ │  比赛数据 (5 大联赛 + 世界杯)
                         │  │ Open-Meteo           │ │  实时天气 (13 个 WC26 场馆)
                         │  │ Event Registry/GDELT │ │  新闻情报 (>70 篇文章)
                         │  │ apifootball.com      │ │  市场赔率共识
                         │  │ openfootball         │ │  世界杯赛程 + 阵容
                         │  └──────────────────────┘ │
                         └──────────┬───────────────┘
                                    │
     ┌──────────────────────────────┼──────────────────────────────┐
     ▼                              ▼                              ▼
┌─────────────────┐    ┌────────────────────────┐    ┌──────────────────┐
│  离线训练工厂     │    │  情报提取管线            │    │  市场赔率校准      │
│                 │    │                        │    │                  │
│  Dixon-Coles    │    │  RSS/API → 文章采集     │    │  3 Provider      │
│  双变量泊松      │    │  DeepSeek → 信号提取    │    │  Shin 去水分      │
│  Bayesian 先验  │    │  人工审核 Gate          │    │  共识构建         │
│                 │    │  evidence_id 审计链     │    │  泄漏防护         │
│  Tabular Enhancer│   │  signal_review_log     │    │  分歧日志         │
│  HGB 分类器      │    │                        │    │                  │
│  37 维特征工程   │    │  入模条件 (3 门控):     │    │                  │
│                 │    │  APPROVED              │    │                  │
│  κ-Elo 评级      │    │  + enters_model=True  │    │                  │
│  K 因子自适应    │    │  + evidence_id NOT NULL│    │                  │
│                 │    │                        │    │                  │
│  Pi-Rating      │    └────────────────────────┘    └──────────────────┘
│  零中心评分      │
│                 │
│  Weibull Copula │
│  比分分布 (可选)  │
└────────┬────────┘
         │
         ├─── 训练产出 ───▶  backend/artifacts/
         │                   ├── models/dc.pkl
         │                   ├── models/enhancer.joblib
         │                   ├── ratings/elo.json
         │                   ├── ratings/pi.json
         │                   └── calibrator.json
         │
         ▼
┌──────────────────────────────────────────────────┐
│              PredictionPipeline                   │
│                                                  │
│   DC ──▶ Enhancer ──▶ Elo ──▶ Pi ──▶ Weibull   │
│   │        │          │       │         │        │
│   └────────┴──────────┴───────┴─────────┘        │
│                    │                             │
│            FusionGraph                           │
│     (每步输入/输出/有效权重完整可追溯)               │
│                    │                             │
│     ┌──────────────┼──────────────┐              │
│     ▼              ▼              ▼              │
│  信号调整      等渗校准        市场融合             │
│  (xG 层面)    (Isotonic)   (Shin 15%)           │
│                                                  │
│  任一外部数据源不可用 → 显式 degraded_reasons     │
│  绝不静默降级                                     │
└──────────────────────┬───────────────────────────┘
                       │
     ┌─────────────────┼──────────────────┐
     ▼                 ▼                  ▼
┌──────────┐  ┌──────────────┐  ┌────────────────┐
│ CLI 预测  │  │  Dashboard    │  │  赛后复盘        │
│          │  │              │  │                  │
│ predict_ │  │ Streamlit    │  │ Brier Score     │
│ match.py │  │ 9 页全中文    │  │ Log Loss        │
│ snapshot │  │ 本地运行      │  │ RPS             │
│ fast_    │  │ 数据库只读     │  │ 方向准确率       │
│ predict  │  │              │  │ 比分命中         │
│ batch    │  │              │  │ 组件归因         │
└──────────┘  └──────────────┘  │ 信号评估         │
                                │ 学习引擎         │
                                │ 权重优化候选      │
                                └────────────────┘
```

---

## ✨ 核心特性

### 🎯 五模型顺序融合

| # | 模型 | 方法 | 核心思路 | 默认权重 |
|:--:|------|------|----------|:-------:|
| 1 | **Dixon-Coles** | 双变量泊松 + L-BFGS-B | 攻防参数 + 主场效应 + Bayesian 先验收缩 | 35% |
| 2 | **Tabular Enhancer** | HistGradientBoosting | 37 维特征工程 (形态/xG/休息日/积分/胜率) | 25% |
| 3 | **κ-Elo** | Elo-Davidson 三结果 | 赛事自适应 K 因子 (世界杯=32/欧冠=28/联赛=20) | 15% |
| 4 | **Pi-Rating** | 零中心评分系统 | 净胜球响应 + 主场优势 | 15% |
| 5 | **Weibull Copula** | 双变量 Weibull + Frank Copula | 比分分布建模 (可选) | 10% |

融合引擎 `FusionGraph` 记录每一步的输入概率、输出概率、有效权重和模型分歧度，确保完整可追溯。

### 🔄 赛后自学习闭环

```
比赛结束 → 结果录入 → 自动触发评估
                          │
     ┌────────────────────┼────────────────────┐
     ▼                    ▼                    ▼
  Brier Score         组件归因              信号评估
  Log Loss           各模型边际贡献         ACCURATE/
  RPS                定位最需调整的组件      MISLEADING/
  方向准确率                               NEUTRAL
  比分命中
     │                    │                    │
     └────────────────────┼────────────────────┘
                          ▼
                  ┌──────────────┐
                  │  学习引擎      │
                  │  权重优化候选  │
                  │  等渗校准更新  │
                  │  上下文矩阵    │
                  └──────┬───────┘
                         ▼
                  ┌──────────────┐
                  │  Backtest Gate│
                  │  候选权重必须  │
                  │  在回测上验证  │
                  │  才能合入生产  │
                  └──────────────┘
```

### 🛡️ 优雅降级架构

```
完整模式:   DC + Enhancer + Elo + Pi + 天气 + 赔率 + LLM 分析
              │
              │ 天气 API 挂了
              ▼
降级模式 1:  DC + Enhancer + Elo + Pi + 赔率 + LLM
              │
              │ 赔率 API 也挂了
              ▼
降级模式 2:  DC + Enhancer + Elo + Pi + LLM
              │
              │ DeepSeek 也挂了
              ▼
最小模式:    DC + Enhancer + Elo + Pi  ← 核心概率永远可用
```

每次降级都显式记录 `degraded_reasons: ["weather_unavailable", "odds_timeout"]`，不静默丢弃。

### 🔒 三层输出安全

| 模式 | 目标用户 | 允许内容 | 过滤内容 |
|------|----------|----------|----------|
| `internal_research` | 开发者/分析师 | 模型概率、校准诊断、市场数据 | 公开投注建议 |
| `creator_safe` | 内容创作者 | 球队背景、数据来源、不确定性声明 | 赔率、博彩术语 |
| `public_safe` | 公众 | 教育性分析、历史对比、可解释趋势 | 概率数值、赔率、比分预测 |

---

## 🚀 快速开始

### 环境要求

- **Python 3.11+**
- Git
- (可选) Docker — 生产部署

### 三步跑起来

```bash
# 1. 克隆
git clone https://github.com/AndyDu0921/wc26-predict.git
cd wc26-predict/backend

# 2. 安装
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows
pip install -r requirements.txt

# 3. 训练 + 预测
python scripts/train_models.py --team-type national
python scripts/predict_match.py --home Spain --away Argentina --competition "World Cup" --mode full
```

### 启动完整服务

```bash
# Dashboard (本地工作台)
streamlit run backend/dashboard/app.py
# → http://localhost:8501

# FastAPI 后端
cd backend && uvicorn app.main:app --reload
# → http://localhost:8000/docs

# 前端 (React)
cd apps/web && npm install && npm run dev
# → http://localhost:5173
```

### Docker 一键部署

```bash
# 开发环境
docker-compose up -d

# 生产环境 (含 Nginx + Celery + PostgreSQL)
docker-compose -f docker-compose.prod.yml up -d
```

---

## 📊 预测引擎详解

### 各模型做了什么

**Dixon-Coles (第 1 层 — 统计基础)**
基于 Dixon & Coles (1997) 论文，将每支球队建模为攻防两个参数，通过双变量泊松分布计算比分概率。使用 L-BFGS-B 数值优化最大化对数似然，加入 Bayesian 先验收缩防止过拟合。对数据稀疏的球队使用 FIFA 排名分层冷启动。

**Tabular Enhancer (第 2 层 — 机器学习增强)**
HistGradientBoostingClassifier 处理 Dixon-Coles 无法捕捉的非线性模式。输入 37 个工程特征：近期形态（6 场）、xG 趋势、休息天数、积分排名、历史交锋胜率等。在 Dixon-Coles 概率基础上输出校正后的三结果概率。

**κ-Elo (第 3 层 — 评分系统)**
Elo-Davidson 三结果扩展，引入了赛事自适应的 K 因子：世界杯淘汰赛 = 32、欧冠 = 28、普通联赛 = 20。包含主场优势参数和比赛重要性权重。

**Pi-Rating (第 4 层 — 零中心评分)**
Pi-Rating 以净胜球而非胜负来更新评分，对"1-0 险胜"和"5-0 大胜"给予不同权重。零中心设计确保评分体系稳定。

**Weibull Copula (第 5 层 — 比分分布)**
可选的深度模式，通过 Frank Copula 连接两支球队的边际进球分布，输出完整比分概率矩阵。用于需要精确比分概率的场景。

### 权重策略

权重按赛事类型独立配置，存储在 `model_weight_config` 数据库表中：

| 赛事类型 | DC 权重 | Enhancer | Elo | Pi | Weibull |
|----------|:-------:|:--------:|:---:|:--:|:-------:|
| 世界杯 | 0.35 | 0.25 | 0.15 | 0.15 | 0.10 |
| 欧冠 | 0.33 | 0.27 | 0.18 | 0.12 | 0.10 |
| 五大联赛 | 0.38 | 0.30 | 0.12 | 0.10 | 0.10 |
| 友谊赛 | 0.28 | 0.42 | 0.02 | 0.16 | 0.12 |

> ⚙️ 友谊赛权重来自 V2.7 自进化实验（3 场复盘驱动），已在 V2.9 保守化。

---

## 📈 回测与校准

### Walk-Forward 回测 (16,689 场比赛)

```
模式: 扩展窗口 (训练 N → 预测 N+1)
快速模式: 100 场预测 ~6min

关键发现 (v3.2):
┌─────────────────┬──────────┬──────────┬──────┐
│ 指标            │ 融合模型  │ Pi-Only  │ 判定  │
├─────────────────┼──────────┼──────────┼──────┤
│ Brier Score     │ 0.244    │ 0.215    │ 需要优化 │
│ Log Loss        │ 1.254    │ 0.987    │ 需要优化 │
│ RPS             │ 0.236    │ 0.189    │ 需要优化 │
│ ECE             │ 0.194    │ 0.102    │ 需要优化 │
│ Directional Acc │ 42%      │ 48%      │ 需要优化 │
└─────────────────┴──────────┴──────────┴──────┘

⚠️ 结论: DC 融合权重 (0.50) 偏高，Pi-only 表现更优。
   等渗校准器已拟合，候选权重待 Backtest Gate 审核。
```

### 等渗校准

使用 scikit-learn `IsotonicRegression` 对预测概率进行保序校准，校准器保存至 `backend/artifacts/calibrator.json`。每次赛后复盘自动重新拟合。

---

## 🖥️ Dashboard 工作台

Streamlit 9 页全中文本地工作台，一键启动：

| 页面 | 功能 |
|------|------|
| **系统总览** | 数据库行数、最近预测量、校准状态、Beats 任务健康度 |
| **单场预测** | 增强模式预测 (DC+Enh+Elo+Pi + 天气 + 赔率 + LLM 分析) |
| **比赛上下文** | 球队事实、近期形态、阵容探针、天气、新闻信号 |
| **WC26 赛程** | 48 队 104 场小组赛 + 淘汰赛，实时预测状态 |
| **球队事实** | 48 支世界杯球队的硬事实库 (FIFA 排名、历史战绩、阵容) |
| **数据库浏览器** | 只读 SQL 浏览器，支持自定义查询 + 自动过期保护 |
| **赛事模拟器** | Monte Carlo 完整世界杯模拟 (10,000 次迭代) |
| **创作者模式** | AI 生成赛前分析 + 视频口播脚本 + 社媒文案 |
| **赛后复盘** | Brier/RPS/LogLoss 评估 + 7 级评级 + 组件错误归因 |

```bash
# 一键启动
streamlit run backend/dashboard/app.py
# 浏览器打开 http://localhost:8501
```

---

## 🗄️ 数据库规模

| 表 | 行数 | 说明 |
|----|------|------|
| `matches` | 16,861 | 历史比赛 + WC26 赛程 |
| `match_results` | 16,689 | 已完成比赛的结果和 xG |
| `teams` | 441 | 国家队 + 俱乐部，含 FIFA 排名 |
| `players` | 1,355 | 球员信息 (含关键球员标记) |
| `prediction_runs` | 252 | 预测记录 (含概率、信号、置信度) |
| `pre_match_snapshots` | 151 | 不可变赛前快照 (完整合同) |
| `postmatch_eval` | 48 | 赛后评估 (Brier/RPS/LogLoss) |
| `market_odds` | 136 | 市场赔率 (Shin 去水分后) |
| `news_articles` | 70 | 新闻文章 (含 embedding) |
| `news_signals` | 6 | 结构化信号 (待人工审核) |

SQLite 开发库 ~13MB，生产使用 PostgreSQL。

---

## 🌐 API 概览

FastAPI 自动生成 Swagger 文档：`http://localhost:8000/docs`

| 端点 | 方法 | Auth | 说明 |
|------|------|------|------|
| `/api/matches/upcoming` | GET | - | 未来 14 天比赛 + 最新预测 |
| `/api/matches/schedule` | GET | - | 分页赛程 (60 天，按日期分组) |
| `/api/matches/{id}` | GET | - | 单场详情 (含概率/信号/文章) |
| `/api/matches/{id}/review` | GET | - | 赛后复盘 (所有预测运行 + 信号评估) |
| `/api/predictions/{id}/latest` | GET | - | 最新预测结果 |
| `/api/predictions/{id}/trigger` | POST | Admin | 手动触发预测 |
| `/api/predictions/{id}/trigger-public` | POST | Rate Limit | 公开异步触发 (3/min) |
| `/api/stats/accuracy` | GET | - | 准确率统计 (Redis 缓存 5min) |
| `/api/stats/recent-predictions` | GET | - | 最近预测结果列表 |
| `/api/analysis/generate` | POST | - | AI 生成 ~400 字比赛分析 |
| `/api/signals/matches/{id}/approved` | GET | - | 已批准信号 |
| `/api/feedback` | POST | Rate Limit | 提交反馈 (20/min) |
| `/api/dashboard/overview` | GET | - | Dashboard 总览数据 |
| `/api/dashboard/market` | GET | - | 市场共识 (仅 internal_research) |
| `/api/admin/dashboard` | GET | Bearer | 管理后台总览 |
| `/api/admin/signals/pending` | GET | Bearer | 待审核信号列表 |
| `/api/admin/signals/{id}/review` | PATCH | Bearer | 单条信号审核 (含 evidence_id) |
| `/api/admin/hermes/digest` | GET | Bearer | 系统健康度监控摘要 |

---

## 🛠️ 技术栈

| 层 | 技术 | 用途 |
|:---|:-----|:-----|
| **概率模型** | scipy, numpy, scikit-learn, penaltyblog | Dixon-Coles, HGB, Elo, Pi, Weibull |
| **Web API** | FastAPI + SQLAlchemy 2.0 + Pydantic v2 | 异步 REST API (自动 OpenAPI 文档) |
| **数据库** | SQLite (dev) / PostgreSQL (prod) + Alembic | 16,861 场比赛, 28 张表, 6 个迁移版本 |
| **任务队列** | Celery + Redis | 异步预测触发 + 定时 Beat 调度 |
| **Dashboard** | Streamlit + Plotly | 9 页全中文工作台 |
| **LLM** | DeepSeek V4 Pro (OpenAI-compatible API) | AI 比赛分析 + 新闻信号提取 |
| **前端** | React 18 + TypeScript + Vite + Tailwind | PWA + Admin 后台 |
| **类型共享** | Zod Contract (`packages/shared`) | 前后端类型安全 |
| **CI/CD** | GitHub Actions | lint + pytest + 安全审计 + 密钥扫描 |
| **部署** | Docker Compose + Nginx + Gunicorn | 4-worker 生产部署 + 健康检查 |

---

## 📡 数据来源

| 数据 | 来源 | 需要密钥 | 覆盖 |
|------|------|:--------:|------|
| 历史比赛 | [football-data.org](https://www.football-data.org/) v4 API | 是 | 5 大联赛 + 世界杯 + 预选赛 |
| 世界杯赛程 | [openfootball/worldcup.json](https://github.com/openfootball/worldcup.json) | 否 | 48 队 104 场完整赛程 |
| 实时天气 | [Open-Meteo](https://open-meteo.com/) 免费 API | 否 | 13 个 WC26 场馆 |
| 市场赔率 | apifootball.com / The Odds API | 是 | 赛前 1x2 赔率 |
| 新闻情报 | Event Registry / GDELT / RSS | 部分 | 足球相关新闻 |
| StatsBomb | [statsbomb/open-data](https://github.com/statsbomb/open-data) | 否 | xG/事件数据 (历史比赛) |

---

## 📋 项目结构

```
wc26-predict/
├── backend/
│   ├── app/
│   │   ├── main.py                   # FastAPI 入口 (middleware + lifespan)
│   │   ├── config.py                 # 配置管理 (.env → Pydantic Settings)
│   │   ├── database.py               # SQLAlchemy 2.0 异步引擎
│   │   ├── version.py                # 单一版本源
│   │   ├── models/                   # ORM 模型 (28 张表)
│   │   ├── routers/                  # API 路由 (9 个模块, 30+ 端点)
│   │   ├── schemas/                  # Pydantic 请求/响应模型
│   │   └── services/                 # 核心服务层 (~54 个文件)
│   │       ├── dixon_coles.py        #   Dixon-Coles 双变量泊松
│   │       ├── tabular_match_model.py #  Tabular Enhancer (HGB)
│   │       ├── elo_ratings.py        #   κ-Elo 三结果评分
│   │       ├── pi_ratings.py         #   Pi-Rating 零中心评分
│   │       ├── weibull_model.py      #   Weibull Copula 比分分布
│   │       ├── fusion_graph.py       #   顺序融合 + 有效权重
│   │       ├── calibration.py        #   等渗校准 (IsotonicRegression)
│   │       ├── weights.py            #   赛事自适应权重配置
│   │       ├── signal_adjuster.py    #   信号调整器 (xG 层面)
│   │       ├── signal_adjuster_sync.py # 同步版 (SQLite 直读)
│   │       ├── prediction_pipeline.py #  统一预测入口 (工厂方法)
│   │       ├── prediction_core.py    #   Artifact 管线 (基础)
│   │       ├── prediction_enhanced.py #  增强编排 (市场+天气+LLM)
│   │       ├── prediction_orchestrator.py # DB-smart 编排器
│   │       ├── postmatch.py          #   赛后评估 (Brier/RPS/LogLoss)
│   │       ├── learning_engine.py    #   学习引擎 (归因+权重)
│   │       ├── output_policy.py      #   三层输出安全策略
│   │       ├── public_safety_filter.py # 中英文禁用词检测
│   │       ├── weather_service.py    #   天气服务 (Open-Meteo)
│   │       ├── injury_data.py        #   伤病数据服务
│   │       ├── team_resolver.py      #   球队名称解析 (别名匹配)
│   │       ├── tournament_simulator.py # Monte Carlo 赛事模拟
│   │       ├── skellam.py            #   Skellam 淘汰赛平局修正
│   │       ├── deprecated.py         #   @deprecated 装饰器
│   │       ├── model_registry.py     #   模型注册表 (JSONLines)
│   │       ├── model_cache_disk.py   #   磁盘模型缓存
│   │       ├── snapshot_service.py   #   快照服务
│   │       ├── snapshot_store.py     #   快照存储 CRUD
│   │       ├── source_logger.py      #   数据源日志
│   │       ├── run_quality.py        #   管线运行质量评估
│   │       ├── market/               #   市场赔率子系统 (10 个文件)
│   │       │   ├── apifootball_com_provider.py
│   │       │   ├── api_football_provider.py
│   │       │   ├── consensus.py      #     共识构建
│   │       │   ├── probability.py    #     Shin 去水分
│   │       │   ├── leakage_guard.py  #     时间泄漏防护
│   │       │   └── consensus_save.py #     共识持久化
│   │       └── llm/                  #   LLM 子系统
│   │           ├── deepseek_client.py
│   │           ├── signal_extraction.py
│   │           └── analysis_prompts.py
│   ├── dashboard/                    # Streamlit 工作台 (9 页 + 6 组件)
│   ├── scripts/                      # CLI 工具 (46 个脚本)
│   │   ├── predict_match.py          #   单场预测
│   │   ├── train_models.py           #   离线训练
│   │   ├── simulate_wc26.py          #   世界杯模拟
│   │   ├── backtest_models.py        #   Walk-forward 回测
│   │   ├── backtest_report.py        #   综合回测报告 (三模式)
│   │   ├── postmatch_review.py       #   赛后复盘
│   │   ├── review_signals_cli.py     #   信号审核 CLI
│   │   ├── market_baseline_report.py #   市场基准报告
│   │   ├── injury_provider_probe.py  #   伤病探针
│   │   ├── manage_injuries.py        #   伤病数据管理
│   │   ├── extract_news_signals.py   #   新闻信号提取
│   │   └── daily_ops.py              #   每日运维任务
│   ├── tests/                        # 146 个测试 (13 个文件)
│   ├── alembic/                      # 数据库迁移 (6 个版本)
│   ├── artifacts/                    # 预训练模型 + 校准器
│   └── data/                         # SQLite 数据库 + 备份
├── apps/web/                         # React 前端 (11 页 + 9 组件)
├── packages/shared/                  # Zod Contract (前后端共享)
├── docs/                             # 项目文档 (8 份核心文档)
├── data/                             # 静态数据 (48 队事实)
├── nginx/                            # 生产 Nginx 配置
├── scripts/                          # 运维脚本 (run_checks.ps1 等)
├── docker-compose.yml                # 本地开发编排
├── docker-compose.prod.yml           # 生产部署编排
├── .github/workflows/ci.yml          # CI/CD
└── deploy.sh                         # 一键部署脚本
```

---

## 🗺️ 路线图

### ✅ 已完成 (v3.2)

- [x] Dixon-Coles + Enhancer + Elo + Pi + Weibull 五模型融合
- [x] FusionGraph 顺序融合 + 有效权重追踪
- [x] 市场赔率接入 (Shin 去水分 + 共识构建)
- [x] 实时天气 (Open-Meteo, 13 个 WC26 场馆)
- [x] DeepSeek V4 Pro AI 分析 + 信号提取
- [x] 赛后复盘系统 (Brier/RPS/LogLoss + 7 级评级)
- [x] 学习引擎 (组件归因 + 信号追踪 + 权重优化候选)
- [x] Walk-forward 回测 + 等渗校准
- [x] Monte Carlo 世界杯赛事模拟
- [x] 新闻信号审核 Gate (单条审核 + evidence_id 门控)
- [x] 不可变赛前快照 (完整合同: input_hash + degraded_reasons)
- [x] 统一预测入口 (PredictionPipeline + 工厂方法)
- [x] 三层输出安全策略 (internal/creator/public)
- [x] 优雅降级架构 (任意源不可用 → 显式记录)
- [x] CI/CD (lint + pytest + 安全审计 + 密钥扫描)
- [x] Docker Compose 生产部署 (Nginx + Gunicorn + Celery)

### 🔜 计划中

- [ ] 伤病数据真实接入 (API-Football injuries endpoint)
- [ ] 赛后复盘自动触发 + 报告生成硬化
- [ ] 预测入口完全统一 (CLI/Dashboard/API 全迁移到 PredictionPipeline)
- [ ] 前端公开页面上线 (WC26 赛程 + 实时预测展示)
- [ ] 回测驱动的权重自动优化 (Backtest Gate 全自动化)
- [ ] 多语言支持 (English / 中文 / 日本語)

---

## ❓ FAQ

<details>
<summary><b>Q: 这个项目能"预测准确"世界杯结果吗？</b></summary>

不能。足球比赛有固有的不可预测性——这是它的魅力所在。WC26 Predict 做的是**概率校准**：告诉你"西班牙有 38% 概率赢球"，而不是"西班牙会赢"。一个好的概率系统，在它说"38% 概率"的 100 场比赛中，实际赢球次数应该接近 38 场——这才是我们追求的。
</details>

<details>
<summary><b>Q: 和博彩公司的赔率有什么区别？</b></summary>

本质区别：博彩赔率包含利润率（vig/overround），目的是让庄家盈利。我们的概率是学术模型对"真实概率"的估计，不含利润率。市场赔率在本项目中只作为校准参考，不出现在公开输出中。
</details>

<details>
<summary><b>Q: 需要什么配置才能跑？</b></summary>

最低配置：Python 3.11+，4GB 内存，无需 GPU。核心预测不需要任何 API key。增强功能（AI 分析、赔率）需要对应的 API key 和网络。
</details>

<details>
<summary><b>Q: 可以用于其他比赛吗？</b></summary>

可以。系统支持俱乐部比赛（英超、欧冠等）和国家队比赛。只需在预测时指定 `--competition` 参数。不过训练数据以五大联赛 + 世界杯为主，其他赛事需要自行积累数据。
</details>

<details>
<summary><b>Q: 为什么叫"WC26"？</b></summary>

World Cup 2026 的缩写。项目最初为 2026 世界杯设计，但架构是通用的。
</details>

---

## 🤝 贡献

欢迎 Issue 和 PR！详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

**特别欢迎的贡献方向：**

- 🧠 **新模型** — 新的概率模型或特征工程方法
- 📡 **数据适配器** — 新的比赛数据源或新闻源适配器
- 📊 **可视化** — Dashboard 图表或前端 UI 改进
- 📖 **文档** — 翻译、教程、使用案例
- 🐛 **Bug 修复** — 任何发现的问题

---

## ⚠️ 合规声明

本项目严格遵守以下硬边界：

- ❌ **不提供投注建议** — 所有输出是概率估计和数据分析，不是投注推荐
- ❌ **不展示原始赔率** — 市场数据仅用于内部校准研究，不出现在公开输出中
- ❌ **不承诺预测准确率** — 足球比赛固有不确定性，概率校准优于"命中率"
- ❌ **不包含博彩推广** — 代码、文档和输出中不出现博彩平台链接或推广内容
- ✅ **研究透明** — 模型架构、权重策略、数据来源完整公开
- ✅ **输出安全** — 三层过滤策略确保公开内容不含博彩术语和赔率信息
- ✅ **数据可审计** — `evidence_id` 追踪每条入模信号从采集到预测的完整决策链
- ✅ **错误可追溯** — 所有降级和缺失数据显式记录在 `degraded_reasons` 和 `missing_inputs` 字段

> 详见 [SECURITY.md](SECURITY.md) 和 [docs/COMPLIANCE_AND_OUTPUT_POLICY.md](docs/COMPLIANCE_AND_OUTPUT_POLICY.md)。

---

## 📄 许可证

[MIT License](LICENSE) © 2026 AndyDu0921

---

## 📬 联系我

- 💬 **微信**: `AndyDu10` (合作 / 交流 / 反馈)
- 🐛 **Bug / 建议**: [GitHub Issues](https://github.com/AndyDu0921/wc26-predict/issues)
- ⭐ **如果这个项目对你有帮助**，给个 Star 吧！

---

<p align="center">
  <i>一个人，三个月，16359 行代码。<br>
  不是赌球工具，是一次对足球不确定性的认真探索。<br>
  如果你也在做类似的事——欢迎加入。</i>
</p>
