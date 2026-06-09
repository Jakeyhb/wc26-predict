# WC26 Predict

> AI 足球预测研究系统 · 多模型融合 · 赛后自学习闭环 · 2026 世界杯开放研究平台

<p align="center">
  <img src="https://img.shields.io/badge/version-v3.2-blue?style=flat-square" alt="version">
  <img src="https://img.shields.io/badge/tests-146%20passed-success?style=flat-square" alt="tests">
  <img src="https://img.shields.io/badge/python-3.11+-blue?style=flat-square" alt="python">
  <img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" alt="license">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square" alt="platform">
</p>

---

## 这是什么？

WC26 Predict 是一个**开放研究的 AI 足球比赛预测系统**，专为 2026 年 FIFA 世界杯设计。它将统计建模（Dixon-Coles）、机器学习（梯度提升树）、评分系统（κ-Elo、Pi-Rating）和实时数据增强融合为一个可复现、可审计的预测管线。

**核心理念**：用数据和模型理解足球比赛的不确定性，而非"预测胜负"。

> ⚠️ **本项目是研究工具，不是赌博产品。** 不提供投注建议、不展示原始赔率、不承诺预测准确率。详见[合规声明](#合规声明)。

---

## 系统架构

```
                        ┌──────────────────────┐
                        │      数据源层          │
                        │  football-data.org    │
                        │  Open-Meteo (天气)     │
                        │  Event Registry / RSS │
                        │  apifootball.com       │
                        └──────────┬───────────┘
                                   │
     ┌─────────────────────────────┼─────────────────────────┐
     ▼                             ▼                         ▼
┌──────────────┐    ┌──────────────────────┐    ┌──────────────────┐
│  离线训练      │    │  情报提取管线          │    │  市场赔率校准      │
│  Dixon-Coles  │    │  RSS → LLM → 结构化信号│    │  Shin 去水分      │
│  Enhancer     │    │  人工审核 Gate         │    │  共识构建         │
│  Elo / Pi     │    │  evidence_id 门控      │    │  泄漏防护         │
└──────┬───────┘    └──────────┬───────────┘    └────────┬─────────┘
       │                       │                         │
       └───────────────────────┼─────────────────────────┘
                               ▼
              ┌────────────────────────────────┐
              │        PredictionPipeline      │
              │   DC → Enhancer → Elo → Pi     │
              │   + 信号调整 + 等渗校准         │
              │   + 优雅降级 (任意源不可用)     │
              └────────────┬───────────────────┘
                           │
         ┌─────────────────┼──────────────────┐
         ▼                 ▼                  ▼
  ┌──────────────┐  ┌─────────────┐  ┌────────────────┐
  │  CLI 预测     │  │  Dashboard   │  │  赛后复盘        │
  │  predict_    │  │  Streamlit   │  │  Brier / RPS    │
  │  match.py   │  │  9 页工作台   │  │  学习引擎        │
  └──────────────┘  └─────────────┘  └────────────────┘
```

---

## 核心特性

- **5 模型顺序融合** — Dixon-Coles (双变量泊松) → HistGradientBoosting (37 维特征工程) → κ-Elo (三结果评分) → Pi-Rating (零中心评分) → Weibull Copula (比分分布)。每步输入/输出完整可追溯
- **数据增强管线** — 实时天气（Open-Meteo，13 个 WC26 场馆）、市场赔率共识（Shin 去水分）、LLM 情报提取（结构化信号 + 人工审核 gate）
- **赛后自学习闭环** — Brier Score / Log Loss / RPS 三指标评估 + 等渗校准 + 逐组件错误归因，反馈到权重优化候选
- **优雅降级架构** — 任意外部数据源不可用时自动回退，不阻断核心预测。缺失数据显式记录在 `degraded_reasons` 字段
- **三层输出安全** — `internal_research` / `creator_safe` / `public_safe` 输出策略，自动过滤博彩术语和赔率信息
- **Monte Carlo 赛事模拟** — 完整世界杯小组赛 + 淘汰赛模拟器，支持自定义权重配置

---

## 快速开始

### 环境要求

- Python 3.11+
- Git

### 1. 克隆仓库

```bash
git clone https://github.com/AndyDu0921/wc26-predict.git
cd wc26-predict
```

### 2. 安装依赖

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows

pip install -r requirements.txt
```

### 3. 配置 API 密钥（可选）

核心预测不需要任何 API 密钥。增强功能按需配置：

```bash
cp .env.example .env
# 编辑 .env，按需填写：
#   LLM_API_KEY=sk-...        # DeepSeek (AI 分析/情报提取)
#   APIFOOTBALL_COM_KEY=...   # 市场赔率 (可选)
#   FOOTBALL_DATA_API_KEY=... # 比赛数据同步 (可选)
```

### 4. 训练模型（首次使用）

```bash
python scripts/train_models.py --team-type national
# ~45s，模型保存到 backend/artifacts/
```

### 5. 运行预测

```bash
# 完整增强预测
python scripts/predict_match.py \
  --home Spain --away Argentina \
  --competition "World Cup" \
  --mode full

# 赛后复盘
python scripts/postmatch_review.py \
  --home Spain --away Argentina \
  --home-goals 1 --away-goals 2 \
  --ai-review
```

### 6. 启动 Dashboard

```bash
streamlit run backend/dashboard/app.py
# 浏览器打开 http://localhost:8501
```

---

## 预测引擎详解

### 模型组件

| 组件 | 方法 | 核心思路 | 权重 |
|------|------|----------|:----:|
| **Dixon-Coles** | 双变量泊松 + L-BFGS-B 优化 | 攻防参数 + 主场效应 + Bayesian 先验收缩 | 0.35 |
| **Tabular Enhancer** | HistGradientBoosting 分类器 | 37 维特征工程（形态、xG、休息日、积分、胜率） | 0.25 |
| **κ-Elo** | Elo-Davidson 三结果模型 | 赛事自适应 K 因子（世界杯=32，欧冠=28，联赛=20） | 0.15 |
| **Pi-Rating** | 零中心评分系统 | 目标差分响应 + 主场优势 | 0.15 |
| **Weibull Copula** | 双变量 Weibull + Frank Copula | 比分分布建模（可选，权重 0.10） | 0.10 |

### 融合策略

模型通过 `FusionGraph` 顺序融合，每个步骤记录有效权重和模型分歧度。权重根据赛事类型自适应调整（世界杯/欧冠/联赛/友谊赛各自独立配置）。最终概率经过等渗校准（Isotonic Regression）输出。

### 信号调整

经人工审核批准的结构化信号（伤病、阵容、教练声明等）通过 `SignalAdjuster` 作用在预期进球（xG）层面，附带动态置信度乘数。所有入模信号必须有 `evidence_id` 审计追踪。

---

## 项目结构

```
wc26-predict/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── config.py            # 配置管理
│   │   ├── models/              # SQLAlchemy ORM (28 张表)
│   │   ├── routers/             # API 路由 (9 个模块)
│   │   ├── schemas/             # Pydantic 数据模型
│   │   └── services/            # 核心服务层
│   │       ├── dixon_coles.py   # Dixon-Coles 模型
│   │       ├── tabular_match_model.py  # XGBoost 增强器
│   │       ├── elo_ratings.py   # κ-Elo 评分
│   │       ├── pi_ratings.py    # Pi 评分
│   │       ├── fusion_graph.py  # 融合引擎
│   │       ├── calibration.py   # 等渗校准
│   │       ├── weights.py       # 权重配置
│   │       ├── signal_adjuster.py    # 信号调整
│   │       ├── learning_engine.py    # 学习引擎
│   │       ├── output_policy.py # 输出安全策略
│   │       └── market/          # 市场赔率子系统
│   ├── dashboard/               # Streamlit 工作台 (9 页)
│   ├── scripts/                 # CLI 工具 (46 个)
│   ├── tests/                   # 146 个测试
│   └── alembic/                 # 数据库迁移 (6 个版本)
├── apps/web/                    # React 前端 (Vite + Tailwind)
├── packages/shared/             # 前后端共享 Zod Contract
├── docs/                        # 项目文档
├── data/                        # 静态数据
├── docker-compose.yml           # 本地开发编排
├── docker-compose.prod.yml      # 生产部署编排
└── .github/workflows/           # CI/CD
```

---

## API 概览

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/matches/upcoming` | GET | 未来 14 天比赛 + 最新预测 |
| `/api/matches/{id}` | GET | 单场比赛详情 |
| `/api/matches/{id}/review` | GET | 赛后复盘摘要 |
| `/api/predictions/{id}/latest` | GET | 最新预测结果 |
| `/api/predictions/{id}/trigger` | POST | 触发新预测 (需 Admin) |
| `/api/stats/accuracy` | GET | 准确率统计 (Redis 缓存) |
| `/api/analysis/generate` | POST | AI 生成比赛分析 |
| `/api/dashboard/overview` | GET | Dashboard 总览数据 |
| `/api/admin/dashboard` | GET | 管理后台 (需 Bearer Token) |

> 完整 API 文档见 `docs/ARCHITECTURE.md`。

---

## 技术栈

| 层 | 技术 | 说明 |
|:-----|:-----|:-----|
| 概率模型 | scipy, numpy, scikit-learn, penaltyblog | Dixon-Coles, HGB, Elo, Pi, Weibull |
| Web API | FastAPI + SQLAlchemy 2.0 + Pydantic | 异步 REST API |
| 数据库 | SQLite (开发) / PostgreSQL (生产) | 16,861 场比赛, 441 支球队 |
| 任务队列 | Celery + Redis | 异步预测触发 + 定时调度 |
| Dashboard | Streamlit + Plotly | 本地 9 页全中文工作台 |
| LLM | DeepSeek V4 Pro | AI 分析 + 情报提取 |
| 前端 | React 18 + TypeScript + Vite + Tailwind | 公开页面 + Admin 后台 |
| CI/CD | GitHub Actions | lint + pytest + 安全扫描 |
| 部署 | Docker Compose + Nginx + Gunicorn | 容器化生产部署 |

---

## 数据来源

| 数据 | 来源 | 需要密钥 |
|------|------|:--------:|
| 比赛数据 | [football-data.org](https://www.football-data.org/) | 是 |
| 世界杯赛程 | [openfootball/worldcup.json](https://github.com/openfootball/worldcup.json) | 否 |
| 实时天气 | [Open-Meteo](https://open-meteo.com/) (免费) | 否 |
| 市场赔率 | apifootball.com / The Odds API | 是 |
| 新闻情报 | Event Registry / GDELT / RSS | 部分 |

---

## 赛后复盘闭环

每场比赛赛后自动触发评估流程：

1. **指标计算** — Brier Score, Log Loss, Ranked Probability Score (RPS), 方向准确率, 比分命中
2. **组件归因** — 逐模型计算边际误差贡献，定位哪个组件最需要调整
3. **信号评估** — 每条入模信号标记为 ACCURATE / MISLEADING / NEUTRAL
4. **校准更新** — 等渗校准器从赛后记录中重新拟合
5. **权重候选** — 优化器产出候选权重，需人工审核后通过 backtest gate 才能合入

---

## 合规声明

本项目严格遵守以下硬边界：

- ❌ **不提供投注建议** — 所有输出是概率估计，不是投注推荐
- ❌ **不展示原始赔率** — 市场数据仅用于内部校准，不出现在公开输出中
- ❌ **不承诺预测准确率** — 足球比赛固有不确定性，概率校准优于"命中率"
- ✅ **研究透明** — 模型架构、权重策略、数据来源完整公开
- ✅ **输出安全** — 三层过滤策略确保公开内容不含博彩术语和赔率信息
- ✅ **数据可审计** — `evidence_id` 追踪每条入模信号的决策链

---

## 测试

```bash
cd backend
pytest tests/ -v
# 146 passed in ~12s
```

覆盖：Dixon-Coles 矩阵运算、FusionGraph 融合逻辑、WC26 闭包完整性、Dashboard 只读防护、权重配置矩阵、Market Provider 选择、输出安全过滤、Shin 公式验证、asyncio 安全性。

---

## 贡献

欢迎 Issue 和 PR。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

贡献方向：
- 模型改进（新的概率模型或特征工程）
- 数据源适配器
- Dashboard 可视化增强
- 文档翻译和完善
- Bug 修复和测试覆盖

---

## 许可证

[MIT License](LICENSE) © 2026 AndyDu0921

---

*Built with Python, scikit-learn, FastAPI, and a lot of football data.* ⚽
