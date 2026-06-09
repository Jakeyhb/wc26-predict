# WC26 Predict

> AI 足球分析引擎 · 多模型融合预测 · 本地可视化工作台 · 2026 世界杯研究系统

<p align="center">
  <img src="https://img.shields.io/badge/version-v2.9.0--conservative-blue?style=flat-square" alt="version">
  <img src="https://img.shields.io/badge/tests-146%20passed-success?style=flat-square" alt="tests">
  <img src="https://img.shields.io/badge/python-3.11+-blue?style=flat-square" alt="python">
  <img src="https://img.shields.io/badge/license-MIT-yellow?style=flat-square" alt="license">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square" alt="platform">
  <img src="https://img.shields.io/badge/coverage-146%2F146-brightgreen?style=flat-square" alt="coverage">
</p>

---

## 项目定位

WC26 Predict 是一个**完整的 AI 足球研究系统**，面向 2026 年 FIFA 世界杯。整合多模型融合概率引擎、实时数据增强（市场赔率 + 天气）、LLM 内容生成（DeepSeek V4 Pro）、赛后复盘闭环和 Monte Carlo 赛事模拟器，统一于本地 Streamlit 工作台。

**适用场景：**

| 用户角色 | 使用方式 |
|----------|----------|
| 🎬 足球内容创作者 | 一键生成数据驱动的 AI 赛前分析 + 视频口播脚本 + 社媒文案 |
| 📊 数据分析师 | 赛后 Brier / LogLoss / RPS 复盘评估 + 复盘驱动权重优化 |
| 🔧 AI 开发者 | 参考完整的多模型 Pipeline + LLM 增强 + 优雅降级架构 |
| ⚽ 足球爱好者 | 用数据和 AI 理解比赛，替代凭感觉做判断 |

> **⚡ 不是赌博产品。** 本项目不提供投注建议、不展示原始赔率、不承诺胜率、不包含博彩推广内容。

---

## V2.9 — 核心能力全景

<p align="center">
  <b>基础预测 (Artifact) → 实时增强 (市场+天气) → AI 内容生成 → 赛后复盘 → 模型自进化</b>
</p>

### 系统能力矩阵

| 能力 | V2.5 (冻结基线) | V2.6 (增强版) | **V2.9 (保守版)** |
|------|:--:|:--:|:--:|
| 4 模型融合预测 (DC + Enhancer + Elo + Pi) | ✅ | ✅ | ✅ |
| FusionGraph 顺序融合 + 有效权重 | ✅ | ✅ | ✅ |
| 市场赔率接入 (apifootball.com + The Odds API) | — | ✅ | ✅ |
| 实时天气 (Open-Meteo, 13 场馆) | — | ✅ | ✅ |
| DeepSeek V4 Pro AI 内容生成 | — | ✅ | ✅ |
| 赛后复盘系统 (Brier / RPS / LogLoss + 7 级评级) | — | ✅ | ✅ |
| 赛后复盘驱动权重自适应 | — | ✅ | ✅ (保守回滚) |
| Shin Vig 去除 (市场概率校准) | — | — | ✅ |
| 完整事件循环安全性 | — | — | ✅ |
| 预测入口统一盘点 (17 入口) | — | — | ✅ |
| Pipeline Contract 强化 | — | — | ✅ |
| 全量 print() → logger 迁移 (73 处, 13 文件) | — | — | ✅ |
| 静默异常消除 (14 处) | — | — | ✅ |
| Brier Score 标准化 | — | — | ✅ |
| 版本号统一 (3 处硬编码消除) | — | — | ✅ |
| Dashboard 页面 | 8 | 9 | **9** |
| 测试覆盖 | 91 | 118 | **146** |
| 统一检查脚本 | — | — | ✅ `run_checks.ps1` |

### 预测引擎

- **4 模型顺序融合**：Dixon-Coles (DC) → XGBoost 增强器 → κ-Elo 评级 → Pi 评级
- **FusionGraph 诊断**：每步输入/输出/公式完整可追溯
- **赛事自适应权重**：世界杯 / 欧冠 / 联赛 / 友谊赛各自独立配置
- **Artifact 推理架构**：离线训练 → 本地加载 → 纯数学计算（核心概率 0 LLM token）
- **V2.9 保守权重**：`FRIENDLY_ADJUSTED_V4` — dc=0.35, enhancer=0.25, elo=0.15, pi=0.15（避免 V2.8 单场过拟合）
- **市场赔率融合**：Shin (1993) 正确 formula 去水分，15% 混合权重

### 预测模式

| 模式 | 组件 | 速度 | 适用场景 |
|------|------|------|----------|
| `baseline` | DC only | <1s | 快速基线对比 |
| `standard` | DC + Enhancer + Elo | ~2s | 常规分析 |
| `full` | DC + Enhancer + Elo + Pi | ~2.5s | 完整分析（推荐） |
| `research-full` | full + Weibull (可选) | ~3s | 深度研究 |

### 数据增强管线

```
基础 artifact 预测 (2-3s)
  → 市场赔率获取 (1-2s)
  → 天气数据获取 (0.5s)
  → 市场-模型混合 (Shin 校准)
  → DeepSeek AI 分析 (3-5s)
  → 完整增强结果

任意环节失败 → 自动优雅降级，不阻断基础预测
总耗时: ~90s, ~2K tokens
```

| 数据源 | 说明 | 密钥需求 |
|--------|------|----------|
| 市场赔率 | apifootball.com + The Odds API, Shin 去水分 | 需要 API Key |
| 实时天气 | Open-Meteo 免费 API, 13 个 WC26 场馆 | 无需密钥 |
| AI 分析 | DeepSeek V4 Pro 赛前分析/视频脚本/社媒文案 | 需要 API Key |

### 赛后复盘闭环

- **评估指标**：Brier Score / Log Loss / RPS / 方向准确率 / 比分命中
- **7 级评级**：A+ (精确命中) → F (严重偏差)
- **AI 复盘**：DeepSeek 分析预测偏差原因，提出优化建议
- **复盘驱动**：评估结果可反馈到权重配置（V2.7 已验证可行性，V2.9 保守化）

### 合规与安全

- **三层输出策略**：`internal_research` / `creator_safe` / `public_safe`
- **硬事实校验**：48 支球队事实 + 禁用词检测
- **只读数据库**：URI `mode=ro` + `PRAGMA query_only` + 正则拦截
- **优雅降级架构**：任何外部数据源不可用时自动回退，不阻断核心预测

### 本地 Dashboard 工作台

```
┌──────────────────────────────────────────────────────┐
│           WC26 Predict 本地工作台 (V2.9)             │
│                                                      │
│  [系统总览] [单场预测] [比赛上下文]                    │
│  [WC26赛程] [球队事实] [数据库]                       │
│  [赛事模拟] [创作者模式] [赛后复盘] ← 9 页全中文      │
│                                                      │
│  Streamlit · 全中文 · 本地运行 · AI 增强              │
└──────────────────────────────────────────────────────┘
```

```powershell
# 一键启动
powershell -File scripts/start_dashboard.ps1
# 浏览器打开 http://localhost:8501
```

---

## 系统架构

```
                         ┌──────────────────────┐
                         │      数据源层          │
                         │  football-data.org    │
                         │  apifootball.com      │
                         │  Open-Meteo (天气)     │
                         │  RSS Feeds            │
                         │  Event Registry       │
                         │  GDELT                │
                         └──────────┬───────────┘
                                    │
       ┌────────────────────────────┼────────────────────────────┐
       ▼                            ▼                            ▼
┌─────────────────┐    ┌─────────────────────┐    ┌─────────────────┐
│  train_models   │    │  news_ingest        │    │   market/        │
│  离线训练        │    │  RSS → LLM → 信号   │    │   赔率校准        │
│  (~45s, 一次性)  │    │  情报提取管线        │    │   Shin 去水分     │
└────────┬────────┘    └────────┬────────────┘    └────────┬────────┘
         │                      │                          │
┌────────▼──────────────────────▼──────────────────────────▼────────┐
│                    Artifacts & Database                            │
│  dc.pkl · enhancer.joblib · elo.json · pi.json · weibull.pkl     │
│  model_registry.json · local_stage2.db · manual_events            │
└────────────────────────────┬─────────────────────────────────────┘
                             │
              ┌──────────────┼──────────────────┐
              ▼              ▼                  ▼
     ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐
     │ CLI 预测     │  │ Dashboard   │  │ 赛后复盘          │
     │ predict_    │  │ Streamlit   │  │ postmatch_review │
     │ match.py   │  │ 9 页面      │  │ (Brier/RPS+AI)   │
     └──────┬──────┘  └──────┬──────┘  └────────┬────────┘
            │                │                   │
            └────────────────┼───────────────────┘
                             ▼
              ┌──────────────────────────────┐
              │     prediction_core.py       │
              │     基础 artifact 管线        │
              │     (DC→Enh→Elo→Pi→Weibull)  │
              └────────────┬─────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
    ┌──────────────┐ ┌─────────────┐ ┌──────────────┐
    │ enhanced.py  │ │ FusionGraph │ │ postmatch.py │
    │ 增强编排      │ │ 融合+分歧    │ │ 赛后评估      │
    │ 市场+天气+LLM │ │ 有效权重     │ │ Brier+RPS    │
    └──────────────┘ └─────────────┘ └──────────────┘
                             │
                    ┌────────▼────────┐
                    │  学习引擎        │
                    │  learning_      │
                    │  engine.py       │
                    │  信号追踪+归因   │
                    └─────────────────┘
```

---

## 快速开始

### 环境要求

- **Python 3.11+**
- **Windows** / macOS / Linux
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

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. 配置 API 密钥（可选）

核心预测不需要任何 API 密钥。增强功能按需配置：

```bash
cp .env.example .env
# 编辑 .env，按需填写：
#   LLM_API_KEY=sk-...           # DeepSeek V4 Pro (AI 分析)
#   APIFOOTBALL_COM_KEY=...      # 市场赔率 (可选)
#   ODDS_API_KEY=...             # 市场赔率备用 (可选)
```

> 天气数据使用免费 Open-Meteo API，无需密钥。

### 4. 训练模型（首次使用）

```bash
python scripts/train_models.py --team-type national
# ~45s，保存模型到 backend/artifacts/
```

### 5. 运行预测

```bash
# 赛前预测 (完整增强模式)
python scripts/predict_match.py \
  --home Spain --away Iraq \
  --competition "International Friendly" \
  --mode full

# 赛后复盘 (含 AI 分析)
python scripts/postmatch_review.py \
  --home Spain --away Iraq \
  --home-goals 1 --away-goals 1 \
  --ai-review
```

### 6. 启动 Dashboard

```powershell
powershell -File scripts/start_dashboard.ps1
# 浏览器打开 http://localhost:8501
```

### 7. 运行健康检查

```powershell
.\scripts\run_checks.ps1
# 默认 fail-fast — 任何失败 → 非零退出码
# .\scripts\run_checks.ps1 -ReportOnly  # 只读诊断，退出码始终为 0
```

---

## 项目结构

```
wc26-predict/
├── backend/                                   # Python 后端
│   ├── app/
│   │   ├── main.py                            # FastAPI 入口
│   │   ├── config.py                          # 配置管理
│   │   ├── database.py                        # PostgreSQL 异步引擎
│   │   ├── version.py                         # ★ 唯一版本源 (2.9.0-conservative)
│   │   ├── routers/                           # API 路由
│   │   │   ├── admin.py                       #   管理接口
│   │   │   ├── predictions.py                 #   预测接口
│   │   │   └── analysis.py                    #   分析接口
│   │   ├── models/                            # SQLAlchemy ORM (28 张表)
│   │   ├── schemas/                           # Pydantic 数据模型
│   │   └── services/                          # ★ 核心服务层
│   │       ├── prediction_core.py             #   基础预测入口 (CLI/Dashboard)
│   │       ├── prediction_enhanced.py         #   增强编排 (市场+天气+LLM)
│   │       ├── prediction_pipeline.py         #   完整管线 (FastAPI 异步版)
│   │       ├── prediction_timer.py            #   性能计时器
│   │       ├── prediction_result.py           #   预测结果数据类
│   │       ├── run_quality.py                 #   管线运行质量
│   │       ├── fusion_graph.py                #   顺序融合 + 有效权重 + 分歧
│   │       ├── weights.py                     #   权重配置 (赛事自适应, FRIENDLY_ADJUSTED_V4)
│   │       ├── postmatch.py                   #   赛后评估 (Brier/RPS/LogLoss)
│   │       ├── learning_engine.py             #   学习引擎 (信号追踪+错误归因)
│   │       ├── dixon_coles.py                 #   Dixon-Coles 双变量泊松
│   │       ├── tabular_match_model.py         #   XGBoost 增强器
│   │       ├── elo_ratings.py                 #   κ-Elo 评级系统
│   │       ├── pi_ratings.py                  #   Pi 评级
│   │       ├── weibull_model.py              #   Weibull Copula (可选)
│   │       ├── tournament_simulator.py        #   Monte Carlo 赛事模拟
│   │       ├── skellam.py                     #   Skellam 淘汰赛平局修正
│   │       ├── output_policy.py               #   输出安全策略
│   │       ├── public_safety_filter.py        #   公开内容安全过滤
│   │       ├── signal_adjuster.py             #   信号调整器
│   │       ├── calibration.py                 #   概率校准 (Isotonic)
│   │       ├── market_calibrator.py           #   市场赔率校准器
│   │       ├── weather_service.py             #   天气服务 (Open-Meteo)
│   │       ├── sync_provider.py               #   同步数据封装
│   │       ├── model_registry.py              #   模型注册表
│   │       ├── model_cache_disk.py            #   磁盘缓存
│   │       ├── news_ingest_service.py         #   新闻采集 (Event Registry + GDELT + RSS)
│   │       ├── football_data_service.py       #   football-data.org 同步
│   │       ├── team_resolver.py               #   球队名称解析
│   │       ├── market/                        #   市场赔率子系统
│   │       │   ├── sync_provider.py           #     同步封装 (Dashboard)
│   │       │   ├── apifootball_com_provider.py
│   │       │   ├── api_football_provider.py
│   │       │   ├── probability.py             #     Shin 去水分 (Shin 1993)
│   │       │   ├── consensus.py               #     共识构建
│   │       │   └── leakage_guard.py           #     时间泄漏防护
│   │       └── llm/                           #   LLM 子系统
│   │           ├── deepseek_client.py         #     DeepSeek V4 Pro 客户端
│   │           ├── signal_extraction.py       #     情报信号提取
│   │           └── analysis_prompts.py        #     AI 分析 Prompt 模板
│   ├── dashboard/                             # ★ Streamlit 工作台
│   │   ├── app.py                             #   入口 + 侧栏导航
│   │   ├── dashboard_config.py                #   中心配置
│   │   ├── db.py                              #   只读 DB + 自动过期
│   │   ├── pages/                             #   9 个页面
│   │   │   ├── 01_Overview.py                 #     系统总览
│   │   │   ├── 02_Match_Prediction.py         #     单场预测 (增强模式)
│   │   │   ├── 03_Match_Context.py            #     比赛上下文 (实时数据)
│   │   │   ├── 04_WC26_Schedule.py            #     WC26 赛程
│   │   │   ├── 05_Teams_Facts.py              #     球队事实库
│   │   │   ├── 06_Database_Explorer.py        #     数据库浏览器
│   │   │   ├── 07_Tournament_Simulator.py     #     赛事模拟器
│   │   │   ├── 08_Creator_Mode.py             #     创作者模式 (AI 生成)
│   │   │   └── 09_Postmatch_Review.py         #     赛后复盘
│   │   └── components/                        #   可复用组件
│   ├── scripts/                               # CLI 工具
│   │   ├── predict_match.py                   #   单场预测
│   │   ├── postmatch_review.py                #   赛后复盘
│   │   ├── train_models.py                    #   离线训练
│   │   ├── simulate_wc26.py                   #   世界杯模拟
│   │   ├── backtest_models.py                 #   Walk-forward 回测
│   │   ├── news_signal_extractor.py           #   RSS 情报提取
│   │   └── add_manual_event.py                #   手动事件录入
│   ├── tests/                                 # 146 个测试
│   │   ├── test_dixon_coles.py                #   12 个 — Dixon-Coles 模型
│   │   ├── test_fusion_graph.py               #   24 个 — FusionGraph 融合
│   │   ├── test_wc26_closure.py               #   18 个 — WC26 闭环
│   │   ├── test_dashboard_db.py               #   24 个 — Dashboard DB (含 SQL 注入检测)
│   │   ├── test_dashboard_prediction.py       #   10 个 — Dashboard 预测 (含确定性验证)
│   │   ├── test_weights_config.py             #   7 个 — 权重配置
│   │   ├── test_prediction_pipeline.py        #   8 个 — Pipeline + RunQuality
│   │   ├── test_market_provider_selection.py  #   5 个 — 市场 Provider 选择
│   │   ├── test_output_policy.py              #   4 个 — 输出策略 + 安全过滤
│   │   ├── test_news_signal_validation.py     #   3 个 — 情报信号验证
│   │   ├── test_fact_check.py                 #   3 个 — 事实校验
│   │   ├── test_shin_formula.py               #   ★ V2.9 新增 — Shin 公式验证
│   │   └── test_asyncio_safety.py             #   ★ V2.9 新增 — 事件循环安全
│   └── data/                                  # SQLite 数据库
├── apps/web/                                  # React 前端 (公开页面 + Admin)
├── packages/shared/                           # 前后端共享 Zod Contract
├── data/
│   └── team_tournament_status.json            # 48 队硬事实
├── docs/                                      # 项目文档 (14 份)
│   ├── CURRENT_STATUS.md                      #   ★ 权威状态文件
│   ├── CHANGELOG.md                           #   版本历史
│   ├── ARCHITECTURE.md                        #   架构说明
│   ├── PRD.md                                 #   产品需求文档
│   ├── PREDICTION_ENTRYPOINT_INVENTORY.md     #   预测入口盘点
│   ├── ASYNCIO_RUN_INVENTORY.md               #   asyncio 安全性审计
│   └── COMPLIANCE_AND_OUTPUT_POLICY.md         #   输出合规政策
├── scripts/
│   ├── start_dashboard.ps1                    # Dashboard 一键启动
│   └── run_checks.ps1                         # ★ 统一健康检查
├── .github/workflows/ci.yml                   # CI/CD (lint + pytest + 安全扫描)
├── nginx/                                     # 生产 Nginx 配置
├── docker-compose.yml                         # 本地开发编排
├── docker-compose.prod.yml                    # 生产部署编排
└── README.md
```

---

## 技术栈

| 层 | 技术 | 说明 |
|------|------|------|
| 概率模型 | scikit-learn, numpy, scipy, penaltyblog | Dixon-Coles, XGBoost, Elo, Pi, Weibull |
| Web API | FastAPI + uvicorn + SQLAlchemy 2.0 | 异步 REST API |
| 数据库 | SQLite (本地开发) + PostgreSQL (生产) | 16,689 场比赛, 441 支球队 |
| 任务队列 | Celery + Redis | 异步任务 + 定时调度 |
| 可视化 | Streamlit 1.58 + Plotly 6.8 | 本地 9 页 Dashboard |
| LLM | DeepSeek V4 Pro | AI 分析文章 + 情报提取 |
| 市场数据 | apifootball.com + The Odds API | 实时赔率共识 |
| 天气 | Open-Meteo (免费, 无需密钥) | 13 个 WC26 场馆 |
| 前端 | React 18 + TypeScript + Vite + Tailwind | 公开演示页面 + Admin |
| 共享 | Zod Contract (`packages/shared`) | 前后端类型安全 |
| CI/CD | GitHub Actions | lint + pytest + 安全扫描 |
| 部署 | Docker Compose + Nginx + Gunicorn | 容器化生产部署 |

---

## 测试

```bash
cd backend
pytest tests/ -v
```

```
146 passed in ~12s

├── 12  Dixon-Coles (矩阵向量化 + 对数似然)
├── 24  FusionGraph (顺序融合 + 有效权重 + 一致性)
├── 18  WC26 Closure (48 队 + 104 场 + 赛程完整性)
├── 24  Dashboard DB (只读防护 + SQL 注入检测 + 自动过期)
├── 10  Dashboard Prediction (确定性验证 + 端到端)
├──  7  Weight Config (赛事自适应权重 + 模式组合)
├──  8  Prediction Pipeline (degraded_reasons contract + RunQuality)
├──  5  Market Provider Selection (API-Football + apifootball.com)
├──  4  Output Policy + Safety Filter (三层策略 + 禁用词)
├──  3  News Signal Validation (信号提取 + 审核流程)
├──  3  Fact Check (48 队硬事实 + 球队别名)
├── 14  ★ V2.9 新增 — Shin Formula (5.0b) + asyncio Safety (3.6a)
│       + Brier 标准化 + Pipeline contract + 权重保守化
└── 14  ★ V2.9 新增 — print→logger + 静默异常回归测试
```

---

## 版本演进

| 版本 | 日期 | 核心突破 | 测试 | 状态 |
|------|------|----------|:----:|:----:|
| V1.8 | 2026-05 | WC26 数据结构 + CI 扩展 | 33 | ✅ |
| V1.91 | 2026-05 | 硬事实层 + 管线接口 | 42 | ✅ |
| V2.0 | 2026-05 | Artifact 推理 (937× 提速) | 42 | ✅ |
| V2.2 | 2026-05 | FusionGraph + 回测 + 模拟器 | 84 | ✅ |
| V2.4 | 2026-05 | Streamlit Dashboard + prediction_core | 91 | ✅ |
| V2.5 | 2026-06 | Local Demo Release — 收口冻结 | 91 | ✅ |
| V2.6 | 2026-06 | Enhanced — 实时数据 + LLM 分析 + 复盘 | 118 | ✅ |
| V2.7 | 2026-06 | 友谊赛自进化 (3 场复盘驱动) | 118 | ✅ |
| V2.8 | 2026-06 | BEL-TUN 单场适应 (已回滚) | 118 | ⚠️ 回滚 |
| **V2.9** | **2026-06** | **Conservative — Brier 标准化 + 保守权重 + Phase 0 审计** | **146** | ✅ **当前** |

### V2.9 核心修复

| 修复项 | 说明 |
|--------|------|
| **Brier Score 标准化** | 移除错误的三路 `/3` 除法，重校 7 级评级阈值 |
| **保守权重回滚** | V2.8 单场过拟合权重 → `FRIENDLY_ADJUSTED_V4` |
| **版本号统一** | 3 处硬编码 → 统一读取 `app.version.VERSION` |
| **Shin 公式修复** | 错误线性近似 → Shin (1993) 正确公式 |
| **asyncio 安全性** | 事件循环检测 + degraded flag，不抛 RuntimeError |
| **73 处 print() → logger** | 13 个 service 文件全部迁移为标准 logging |
| **14 处静默异常消除** | `except: pass` → `logger.warning/debug` |
| **Pipeline Contract** | 结构化 `degraded_reasons`，降级信息可追溯 |
| **统一检查脚本** | `run_checks.ps1` — fail-fast + ReportOnly 双模式 |

---

## 赛后复盘案例

| 比赛 | 预测 | 实际 | 评级 | AI 分析核心发现 |
|------|------|------|:--:|------|
| France vs Ivory Coast | 法国胜 41.8% | 1-2 客胜 | **B+** | Enhancer 正确预警 — 友谊赛大轮换是关键变量 |
| Spain vs Iraq | 西班牙胜 52.8% | 1-1 平局 | **F** | DC/Elo/Pi 三模型一致性过强，需引入阵容轮换信号 |
| Belgium vs Tunisia | 比利时胜 76.2% | 5-0 主胜 | **A-** | 单一强信号主导 — 过度依赖导致 V2.8 过拟合（已回滚） |

> V2.9 的关键教训：单场比赛不应主导权重调整。V2.8 的 BEL-TUN 单场适应已被回滚，保守权重在回测中表现更稳定。

---

## 输出策略

WC26 Predict 严格区分内部研究和公开内容：

| 模式 | 目标用户 | 允许包含 | 必须排除 |
|------|----------|----------|----------|
| `internal_research` | 维护者 / 分析师 | 模型概率、校准诊断、市场研究 | 公开投注建议 |
| `creator_safe` | 内容创作者 | 球队背景、数据来源、不确定性声明 | 赔率、博彩术语 |
| `public_safe` | 公众 | 教育性分析、历史对比、可解释趋势 | 概率、赔率、预测承诺 |

详见 [`docs/COMPLIANCE_AND_OUTPUT_POLICY.md`](docs/COMPLIANCE_AND_OUTPUT_POLICY.md)

---

## 路线图

### 已完成 ✅

- [x] V1.8 → V2.5：核心架构搭建（Artifact 推理 + FusionGraph + Dashboard）
- [x] V2.6：实时数据增强 + LLM 分析 + 赛后复盘闭环
- [x] V2.7 → V2.8：自进化探索（V2.8 已回滚，经验并入 V2.9）
- [x] **V2.9 Conservative**：Brier 标准化 + 保守权重 + 全量审计修复
- [x] **Phase 0**：验证基线（CLAUDE.md + AGENTS.md + run_checks.ps1）
- [x] **Phase 0+**：审计修复（Shin 公式 + asyncio 安全 + print→logger + 静默异常）
- [x] **Phase 1**：预测入口盘点（17 入口文档化）+ Pipeline Contract 强化

### 进行中 🔄

- [ ] **Phase 2**：`data_sources/` 模块 + `pre_match_snapshot`（数据层统一）
- [ ] **Phase 3**：`match_fact` 数据模型 + 富赛后复盘（process review）
- [ ] **Phase 4**：学习闭环（replay harness + 真实 signal tracking 更新）
- [ ] **Phase 5**：LLM 报告层重构

### 展望 🔮

- [ ] **V3.0**：公开演示版 — 安全合规审核 + 公开部署
- [ ] 回测驱动权重优化（需多场比赛数据积累）
- [ ] 比分概率矩阵 (score probability matrix) 可视化增强

---

## 文档导航

| 文档 | 说明 |
|------|------|
| [`CURRENT_STATUS.md`](docs/CURRENT_STATUS.md) | ★ 项目权威状态文件（版本、已知问题、修复历史） |
| [`CHANGELOG.md`](CHANGELOG.md) | 完整版本变更日志 |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | 系统架构说明 |
| [`PRD.md`](docs/PRD.md) | 产品需求文档 |
| [`PREDICTION_ENTRYPOINT_INVENTORY.md`](docs/PREDICTION_ENTRYPOINT_INVENTORY.md) | 17 个预测入口详细盘点 |
| [`ASYNCIO_RUN_INVENTORY.md`](docs/ASYNCIO_RUN_INVENTORY.md) | asyncio 安全性审计 |
| [`COMPLIANCE_AND_OUTPUT_POLICY.md`](docs/COMPLIANCE_AND_OUTPUT_POLICY.md) | 输出合规政策 |
| [`SECURITY.md`](SECURITY.md) | 安全策略 |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | 贡献指南 |

---

## 安全

- 无 API 密钥提交至 Git（`.env` 由 `.gitignore` 排除）
- CI 自动扫描密钥模式（`sk-`, `ghp_`, `x-apisports-` 等）
- Dashboard 数据库三层只读防护（URI + PRAGMA + 正则）
- 所有默认配置使用占位符（`change-me`）
- 安全漏洞请通过 GitHub Issue 私密报告

详见 [`SECURITY.md`](SECURITY.md)

---

## 贡献

欢迎提交 Issue 和 Pull Request。请先阅读：

- [`CONTRIBUTING.md`](CONTRIBUTING.md) — 贡献流程和代码规范
- [`CLAUDE.md`](CLAUDE.md) — Claude Code Agent 编码执行规则
- [`AGENTS.md`](AGENTS.md) — 多 Agent 通用项目规则

---

## 免责声明

WC26 Predict 是一个 AI 辅助足球研究和分析系统。所有输出基于可用数据、模型假设和系统配置，具有内在不确定性。**不应将其视为事实预测、金融建议、投注建议或保证结果。**

足球是复杂的。模型可能出错。请将本系统用于研究、学习和内容创作。

---

## 许可证

MIT License. 详见 [`LICENSE`](LICENSE).

---

<p align="center">
  <sub>Built with ❤️ by a football fan · Powered by Python + Streamlit + DeepSeek + Claude Code</sub>
  <br>
  <sub>© 2026 WC26 Predict · V2.9 Conservative · 146 tests · All systems green</sub>
</p>
