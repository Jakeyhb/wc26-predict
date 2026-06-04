# WC26 Predict

> AI 足球分析引擎 · 本地可视化工作台 · 世界杯 2026 研究系统

<p align="center">
  <img src="https://img.shields.io/badge/version-v2.6--enhanced-blue" alt="version">
  <img src="https://img.shields.io/badge/tests-118%20passed-green" alt="tests">
  <img src="https://img.shields.io/badge/license-MIT-yellow" alt="license">
  <img src="https://img.shields.io/badge/python-3.11+-blue" alt="python">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey" alt="platform">
</p>

---

## 项目定位

WC26 Predict 是一个**完整的 AI 足球研究系统**，面向 2026 年 FIFA 世界杯。它将历史比赛数据、多模型融合概率引擎、赛事模拟器、事实校验层和输出安全策略整合为统一的本地工作台。

**适用场景：**
- 足球内容创作者：快速生成数据驱动的赛前分析素材
- 数据分析师：研究模型融合、权重优化、概率校准
- AI 开发者：参考完整的多模型 pipeline 架构设计
- 足球爱好者：用数据理解比赛，而非凭感觉下判断

**不是赌博产品。** 本项目不提供投注建议、不展示赔率、不承诺胜率、不包含任何博彩推广内容。

---

## 核心能力

### 预测引擎
- **4 模型顺序融合**：Dixon-Coles 双变量泊松 (49.6%) → XGBoost 增强器 (39.6%) → Elo 评级 (5.3%) → Pi 评级 (5.6%)
- **有效权重自动计算**：分步混合参数 → 展开为 4 个模型的实际有效权重，永保证总和为 100%
- **模型分歧度量**：实时计算任意两个模型之间的最大主胜概率差，识别高分歧比赛
- **Artifact 推理架构**：离线训练 → 保存模型文件 → 在线加载 → 纯本地数学计算（**0 LLM token**）

### 预测模式

| 模式 | 组件 | 速度 | 适用场景 |
|---|---|---|---|
| `baseline` | DC only | <1s | 快速对比基线 |
| `standard` | DC + Enhancer + Elo | ~2s | 常规分析 |
| `full` | DC + Enhancer + Elo + Pi | ~2.5s | 完整分析（推荐） |
| `research-full` | full + Weibull (可选) | ~3s | 深度研究 |

### 概率输出
- 胜/平/负概率（精确到小数点后 4 位）
- 预期进球 (xG)
- 比分概率矩阵 (Top 5)
- FusionGraph 完整诊断（每步的输入/输出/公式）
- 模型分歧度 + 置信度

### 本地 Dashboard 工作台 (v2.5-local-demo)

```
┌──────────────────────────────────────────────┐
│         WC26 Predict 本地工作台               │
│                                              │
│  [系统总览] [单场预测] [比赛上下文]            │
│  [WC26赛程] [球队事实] [数据库]               │
│  [赛事模拟] [创作者模式]                       │
│                                              │
│  Streamlit · 全中文 · 本地运行 · 录屏就绪      │
└──────────────────────────────────────────────┘
```

一键启动：
```powershell
powershell -File scripts/start_dashboard.ps1
# 浏览器打开 http://localhost:8501
```

### 合规与安全
- **三层输出策略**：`internal_research` / `creator_safe` / `public_safe`
- **事实校验层**：48 支球队硬事实 + 18 条中文禁用短语 + 6 条英文禁用短语
- **只读数据库**：Dashboard 三层防护（URI `mode=ro` + `PRAGMA query_only` + 正则拦截）
- **无 LLM 依赖**：核心概率计算不使用任何 LLM API，完全本地可复现

### WC26 专属能力
- 104 场比赛完整赛程（72 场小组赛 + 32 场淘汰赛）
- 12 个小组、48 支已晋级球队的硬事实数据
- Monte Carlo 世界杯模拟器 (1,000~50,000 次)
- 小组出线 / 16 强 / 8 强 / 4 强 / 决赛 / 冠军概率分布
- 赛后复盘 + Brier Score / Log Loss / RPS / 校准 ECE 回测

---

## 系统架构

```
                        ┌──────────────────────┐
                        │   数据源层             │
                        │  football-data.org    │
                        │  openfootball         │
                        │  StatsBomb Open Data  │
                        │  RSS / 公开新闻       │
                        │  手动验证信号          │
                        └──────────┬───────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
    ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
    │  train_models.py │  │  news_signal_   │  │  market data    │
    │  离线训练        │  │  extractor.py   │  │  shadow mode    │
    │  (一次性, ~45s)  │  │  情报提取       │  │  市场校准       │
    └────────┬────────┘  └────────┬────────┘  └────────┬────────┘
             │                    │                    │
    ┌────────▼────────────────────▼────────────────────▼────────┐
    │                  Artifacts & Database                      │
    │  dc.pkl · enhancer.joblib · elo.json · pi.json           │
    │  model_registry.json · local_stage2.db                   │
    └────────────────────────┬──────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
    ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
    │ CLI 预测     │  │ Dashboard   │  │ 模拟器       │
    │ predict_    │  │ Streamlit   │  │ simulate_   │
    │ match.py   │  │ localhost   │  │ wc26.py     │
    └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
           │                │                │
           └────────────────┼────────────────┘
                            ▼
              ┌─────────────────────────┐
              │   prediction_core.py     │
              │   统一预测入口（共享）     │
              │   run_artifact_pipeline  │
              └─────────────────────────┘
                            │
                            ▼
              ┌─────────────────────────┐
              │   FusionGraph            │
              │   顺序融合 + 有效权重     │
              │   + 模型分歧 + 步骤记录   │
              └────────────┬────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
    ┌─────────────┐ ┌──────────┐ ┌──────────────┐
    │ RunQuality   │ │ Output   │ │ Team Facts   │
    │ 管线状态      │ │ Policy   │ │ 硬事实校验    │
    └─────────────┘ └──────────┘ └──────────────┘
```

---

## 快速开始

### 环境要求

- Python 3.11+
- Windows / macOS / Linux
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

预测核心不需要任何 API 密钥。仅在启用新闻情报提取时需要 DeepSeek API：

```bash
cp .env.example .env
# 编辑 .env 填入你的 DeepSeek API Key
```

### 4. 训练模型（首次使用，一次性）

```bash
python scripts/train_models.py --team-type national
# 输出: ~45s, 保存 4 个模型文件到 backend/artifacts/
```

### 5. 运行预测

```bash
# 完整模式（4 模型融合）
python scripts/predict_match.py \
  --home France --away "Ivory Coast" \
  --competition "International Friendly" \
  --neutral --mode full

# JSON 输出
python scripts/predict_match.py \
  --home Brazil --away Argentina \
  --competition "FIFA World Cup 2026" \
  --neutral --mode full --output json
```

### 6. 启动 Dashboard

```powershell
powershell -File scripts/start_dashboard.ps1
```

浏览器打开 `http://localhost:8501`，开始使用可视化工作台。

---

## 项目结构

```
wc26-predict/
├── backend/
│   ├── app/
│   │   ├── main.py                          # FastAPI 入口
│   │   ├── config.py                        # 配置管理
│   │   ├── database.py                      # PostgreSQL 异步引擎
│   │   ├── routers/                         # API 路由 (9 个模块)
│   │   ├── models/                          # SQLAlchemy ORM (28 张表)
│   │   ├── schemas/                         # Pydantic 数据模型
│   │   └── services/                        # 核心服务层
│   │       ├── prediction_core.py           # ★ 统一预测入口 (CLI/Dashboard 共享)
│   │       ├── prediction_pipeline.py       # 完整管线 (FastAPI 异步版)
│   │       ├── dixon_coles.py              # Dixon-Coles 双变量泊松模型
│   │       ├── tabular_match_model.py       # XGBoost 增强器
│   │       ├── elo_ratings.py              # K-Elo 评级系统
│   │       ├── pi_ratings.py               # Pi 评级 (泊松强度)
│   │       ├── weibull_model.py            # Weibull Copula (可选)
│   │       ├── fusion_graph.py             # 顺序融合图 + 有效权重
│   │       ├── weights.py                  # 融合权重配置
│   │       ├── artifact_registry.py        # 模型文件注册表
│   │       ├── run_quality.py              # 管线运行质量
│   │       ├── prediction_timer.py         # 性能计时器
│   │       ├── output_policy.py            # 输出安全策略
│   │       ├── tournament_simulator.py     # Monte Carlo 赛事模拟
│   │       ├── market/                     # 市场数据校准 (shadow mode)
│   │       └── llm/                        # DeepSeek 情报提取
│   ├── dashboard/                          # ★ Streamlit 本地工作台 (v2.4)
│   │   ├── app.py                          # 入口 + 首页
│   │   ├── dashboard_config.py             # 配置
│   │   ├── db.py                           # 只读 SQLite 连接器
│   │   ├── pages/                          # 8 个页面
│   │   │   ├── 01_Overview.py              #   系统总览
│   │   │   ├── 02_Match_Prediction.py      #   单场预测
│   │   │   ├── 03_Match_Context.py         #   比赛上下文
│   │   │   ├── 04_WC26_Schedule.py         #   WC26 赛程
│   │   │   ├── 05_Teams_Facts.py           #   球队事实库
│   │   │   ├── 06_Database_Explorer.py     #   数据库浏览器
│   │   │   ├── 07_Tournament_Simulator.py  #   赛事模拟器
│   │   │   └── 08_Creator_Mode.py          #   创作者模式
│   │   └── components/                     # 6 个可复用组件
│   ├── scripts/                            # CLI 脚本
│   │   ├── predict_match.py               # 单场预测 CLI
│   │   ├── train_models.py                # 离线模型训练
│   │   ├── simulate_wc26.py               # 世界杯模拟 CLI
│   │   ├── backtest_models.py             # Walk-forward 回测
│   │   ├── optimize_fusion_weights.py      # 权重网格搜索
│   │   └── audit_team_facts.py            # 事实校验审计
│   ├── tests/                              # 91 个测试
│   └── data/
├── apps/web/                               # React 前端 (Vite + TypeScript)
├── data/
│   └── team_tournament_status.json         # 48 队硬事实
├── docs/                                   # 项目文档
├── scripts/
│   └── start_dashboard.ps1                 # Dashboard 一键启动
├── docker-compose.yml                      # 本地开发环境
├── docker-compose.prod.yml                 # 生产部署配置
├── .github/workflows/ci.yml               # CI/CD (lint + 测试 + 安全扫描)
├── README.md
├── SECURITY.md
├── CONTRIBUTING.md
└── LICENSE
```

---

## 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 概率模型 | scikit-learn, numpy, scipy, penaltyblog | Dixon-Coles, XGBoost, Elo, Pi |
| 可视化 | Streamlit 1.58, Plotly 6.8 | 本地 Dashboard 工作台 |
| Web API | FastAPI, uvicorn, SQLAlchemy 2.0 | REST API 服务 |
| 数据库 | SQLite (本地), PostgreSQL (生产) | 16,689 场比赛, 441 支球队 |
| 前端 | React 18 + TypeScript + Vite + Tailwind | 公开演示页面 |
| LLM | DeepSeek V4 Pro | 新闻情报提取（可选） |
| 任务调度 | Celery + Redis | 定时数据同步 |
| 部署 | Docker + Nginx | 容器化部署 |
| CI/CD | GitHub Actions | lint + pytest + 安全扫描 |

---

## 测试

```bash
cd backend
pytest tests/ -v
```

```
91 passed in 5.79s
├── 12  Dixon-Coles
├── 24  FusionGraph
├── 18  WC26 Closure
├──  3  Fact Check
├── 24  Dashboard DB (含 SQL 注入检测)
└── 10  Dashboard Prediction (含确定性验证)
```

---

## 输出策略

WC26 Predict 严格区分内部研究和公开内容：

| 模式 | 目标用户 | 允许包含 | 必须排除 |
|---|---|---|---|
| `internal_research` | 维护者 / 分析师 | 模型概率、校准诊断、市场研究 | 公开投注建议 |
| `creator_safe` | 内容创作者 | 球队背景、数据来源、不确定性声明 | 赔率、博彩术语 |
| `public_safe` | 公众 | 教育性分析、历史对比、可解释趋势 | 概率、赔率、预测承诺 |

详见 [`docs/COMPLIANCE_AND_OUTPUT_POLICY.md`](docs/COMPLIANCE_AND_OUTPUT_POLICY.md)

---

## 项目路线图

### 已完成

- [x] V1.8: WC26 数据结构 + 信号审核 + CI 扩展 (33 tests)
- [x] V1.91: 硬事实层 + 编码修复 + 管线接口 (42 tests)
- [x] V2.0: Artifact 推理架构 — 训练/推理分离, 2.2s 全量预测 (42 tests)
- [x] V2.2: FusionGraph + 回测优化 + 48 队 + 赛事模拟器 (84 tests)
- [x] V2.4: Streamlit Dashboard + prediction_core + 全中文化 (91 tests)
- [x] **V2.5: Local Demo Release — 最终收口冻结版**

### 进行中

- [ ] V3.0: 公开演示版（在收集真实反馈后重新规划）

---

## 安全

- 无 API 密钥提交至 Git（`.env` 全部由 `.gitignore` 排除）
- CI 自动扫描密钥模式（`sk-`, `ghp_`, `x-apisports-` 等）
- Dashboard 数据库三层只读防护
- 所有默认配置使用占位符，无真实凭证硬编码

详见 [`SECURITY.md`](SECURITY.md)

---

## 贡献

欢迎提交 Issue 和 Pull Request。请阅读 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

---

## 免责声明

WC26 Predict 是一个 AI 辅助足球研究和分析项目。所有输出基于可用数据、模型假设和系统配置，具有内在不确定性。不应将其视为事实预测、金融建议、投注建议或保证结果。

足球是复杂的。模型可能出错。请将本系统用于研究、学习和内容创作。

---

## 许可证

MIT License. 详见 [`LICENSE`](LICENSE).

---

<p align="center">
  <sub>Built with ❤️ by a football fan · Powered by Python + Streamlit + Claude Code</sub>
</p>
