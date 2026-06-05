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

WC26 Predict 是一个**完整的 AI 足球研究系统**，面向 2026 年 FIFA 世界杯。它整合了多模型融合概率引擎、实时数据增强（市场赔率 + 天气）、LLM 内容生成（DeepSeek V4 Pro）、赛后复盘闭环和赛事模拟器于统一的本地工作台。

**适用场景：**
- 足球内容创作者：一键生成数据驱动的 AI 赛前分析 + 视频口播脚本 + 社媒文案
- 数据分析师：赛后复盘 Brier/LogLoss/RPS 评估，复盘驱动权重优化
- AI 开发者：参考完整的多模型 pipeline + LLM 增强 + 优雅降级架构
- 足球爱好者：用数据理解比赛，用 AI 辅助分析而非凭感觉

**不是赌博产品。** 本项目不提供投注建议、不展示原始赔率、不承诺胜率、不包含博彩推广内容。

---

## V2.6 亮点

<p align="center">
  <b>基础预测 → 实时增强 → AI 内容 → 赛后复盘 → 模型优化</b>
</p>

| 能力 | V2.5 | V2.6 |
|---|---|---|
| 4 模型融合预测 | ✅ | ✅ |
| 市场赔率融合 | ❌ | ✅ (apifootball.com + The Odds API) |
| 实时天气 | ❌ | ✅ (Open-Meteo, 免费) |
| DeepSeek AI 分析 | ❌ | ✅ (赛前分析 + 视频脚本 + 社媒文案) |
| 赛后复盘系统 | ❌ | ✅ (Brier/RPS/LogLoss + 7 级评级) |
| AI 赛后复盘 | ❌ | ✅ (DeepSeek 偏差分析) |
| 友谊赛权重自适应 | ❌ | ✅ (赛后复盘驱动优化) |
| 事件自动过期 | ❌ | ✅ (SQL 层过滤, 无需定时任务) |
| Dashboard 页面数 | 8 | **9** (+赛后复盘) |

---

## 核心能力

### 预测引擎

- **4 模型顺序融合**：Dixon-Coles (DC) → XGBoost 增强器 → Elo 评级 → Pi 评级
- **有效权重**：分步混合参数展开为 4 模型实际权重，总和恒为 100%
- **赛事自适应权重**：世界杯 / 欧冠 / 联赛 / 友谊赛 各自独立权重配置
- **V2.6 友谊赛优化**：赛后复盘发现 Enhancer 在友谊赛正确率远高于 DC/Elo/Pi，自动调整权重（Enhancer 39.6% → 57.1%）
- **模型分歧度量**：实时计算最大主胜概率差，识别高不确定性比赛
- **Artifact 推理**：离线训练 → 本地加载 → 纯数学计算（核心概率 0 LLM token）

### 预测模式

| 模式 | 组件 | 速度 | 适用场景 |
|---|---|---|---|
| `baseline` | DC only | <1s | 快速对比基线 |
| `standard` | DC + Enhancer + Elo | ~2s | 常规分析 |
| `full` | DC + Enhancer + Elo + Pi | ~2.5s | 完整分析（推荐） |
| `research-full` | full + Weibull (可选) | ~3s | 深度研究 |

### 增强预测 (V2.6)

| 数据源 | 说明 | 状态 |
|---|---|---|
| 市场赔率 | apifootball.com + The Odds API，15% 混合权重 | 自动回退 |
| 实时天气 | Open-Meteo 免费 API，13 个 WC26 场馆 | 自动回退 |
| AI 分析 | DeepSeek V4 Pro 生成分析文章、视频脚本、社媒文案 | 自动回退 |

```
基础 artifact 预测 (2-3s)
  → 获取市场赔率 (1-2s)
  → 获取天气 (0.5s)
  → 市场-模型混合
  → DeepSeek AI 分析 (3-5s)
  → 完整增强结果
总计: ~90s, ~2K tokens
任意环节失败 → 自动回退, 不阻断基础预测
```

### 概率输出

- 胜/平/负概率（精确到小数点后 4 位）
- 预期进球 (xG)
- 比分概率矩阵 (Top 5)
- FusionGraph 完整诊断（每步输入/输出/公式）
- 模型分歧度 + 置信度 + 风险标签

### 赛后复盘 (V2.6)

- **评估指标**：Brier Score / Log Loss / RPS / 方向准确率 / 比分命中
- **7 级评级**：A+ (精确命中) → F (严重偏差)
- **AI 复盘**：DeepSeek 分析预测偏差原因，提出优化建议
- **复盘驱动优化**：评估结果反馈到权重配置（如友谊赛权重调整）

### 本地 Dashboard 工作台

```
┌──────────────────────────────────────────────────────┐
│           WC26 Predict 本地工作台 (V2.6)             │
│                                                      │
│  [系统总览] [单场预测] [比赛上下文]                    │
│  [WC26赛程] [球队事实] [数据库]                       │
│  [赛事模拟] [创作者模式] [赛后复盘] ← NEW             │
│                                                      │
│  Streamlit · 全中文 · 本地运行 · AI 增强              │
└──────────────────────────────────────────────────────┘
```

一键启动：
```powershell
powershell -File scripts/start_dashboard.ps1
# 浏览器打开 http://localhost:8501
```

### 合规与安全

- **三层输出策略**：`internal_research` / `creator_safe` / `public_safe`
- **事实校验层**：48 支球队硬事实 + 禁用短语检测
- **只读数据库**：URI `mode=ro` + `PRAGMA query_only` + 正则拦截
- **事件自动过期**：SQL 层按 `expires_at` 自动过滤，无需定时清理
- **无 LLM 依赖**：核心概率完全本地数学计算，LLM 仅用于内容生成

### WC26 专属能力

- 104 场比赛完整赛程（72 场小组赛 + 32 场淘汰赛）
- 12 个小组、48 支已晋级球队的硬事实数据
- Monte Carlo 世界杯模拟器 (1,000~50,000 次)
- 小组出线 / 16 强 / 8 强 / 4 强 / 决赛 / 冠军概率分布

---

## 系统架构

```
                         ┌──────────────────────┐
                         │      数据源层          │
                         │  football-data.org    │
                         │  openfootball · RSS   │
                         │  Open-Meteo (天气)     │
                         │  apifootball.com (赔率)│
                         └──────────┬───────────┘
                                    │
       ┌────────────────────────────┼────────────────────────────┐
       ▼                            ▼                            ▼
┌─────────────────┐    ┌─────────────────────┐    ┌─────────────────┐
│  train_models   │    │  news_signal_extr   │    │   market/        │
│  离线训练        │    │  DeepSeek 情报提取   │    │   赔率校准        │
│  (~45s, 一次性)  │    │  (RSS → LLM → 信号) │    │   (影子→混合)     │
└────────┬────────┘    └────────┬────────────┘    └────────┬────────┘
         │                      │                          │
┌────────▼──────────────────────▼──────────────────────────▼────────┐
│                       Artifacts & Database                        │
│  dc.pkl · enhancer.joblib · elo.json · pi.json · weibull.pkl    │
│  model_registry.json · local_stage2.db · manual_events           │
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

核心预测不需要 API 密钥。增强功能需要：

```bash
cp .env.example .env
# 编辑 .env:
#   LLM_API_KEY=sk-...        # DeepSeek (AI 分析)
#   APIFOOTBALL_COM_KEY=...   # 市场赔率 (可选)
#   ODDS_API_KEY=...          # 市场赔率备用 (可选)
```

天气数据使用免费的 Open-Meteo API，无需密钥。

### 4. 训练模型（首次使用）

```bash
python scripts/train_models.py --team-type national
# ~45s, 保存模型到 backend/artifacts/
```

### 5. 预测 + 复盘

```bash
# 赛前预测 (增强模式)
python scripts/predict_match.py \
  --home Spain --away Iraq \
  --competition "International Friendly" \
  --mode full

# 赛后复盘
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

---

## 项目结构

```
wc26-predict/
├── backend/
│   ├── app/
│   │   ├── main.py                          # FastAPI 入口
│   │   ├── config.py                        # 配置管理
│   │   ├── database.py                      # PostgreSQL 异步引擎
│   │   ├── routers/                         # API 路由
│   │   ├── models/                          # SQLAlchemy ORM (28 张表)
│   │   ├── schemas/                         # Pydantic 数据模型
│   │   └── services/                        # 核心服务层
│   │       ├── prediction_core.py           # ★ 基础预测入口 (CLI/Dashboard)
│   │       ├── prediction_enhanced.py       # ★ 增强编排 (市场+天气+LLM)
│   │       ├── prediction_pipeline.py       # 完整管线 (FastAPI 异步版)
│   │       ├── prediction_timer.py          # 性能计时器
│   │       ├── run_quality.py               # 管线运行质量
│   │       ├── fusion_graph.py              # 顺序融合 + 有效权重 + 分歧
│   │       ├── weights.py                   # 权重配置 (赛事自适应)
│   │       ├── postmatch.py                 # ★ 赛后评估 (Brier/RPS/LogLoss)
│   │       ├── dixon_coles.py              # Dixon-Coles 双变量泊松
│   │       ├── tabular_match_model.py       # XGBoost 增强器
│   │       ├── elo_ratings.py              # K-Elo 评级系统
│   │       ├── pi_ratings.py               # Pi 评级
│   │       ├── weibull_model.py            # Weibull Copula (可选)
│   │       ├── tournament_simulator.py     # Monte Carlo 赛事模拟
│   │       ├── output_policy.py            # 输出安全策略
│   │       ├── signal_adjuster.py           # 信号调整器
│   │       ├── weather_service.py           # 天气服务 (Open-Meteo)
│   │       ├── market/                     # 市场赔率子系统
│   │       │   ├── sync_provider.py         #   同步封装 (Dashboard)
│   │       │   ├── apifootball_com_provider.py
│   │       │   ├── api_football_provider.py
│   │       │   ├── probability.py           #   去水分方法
│   │       │   ├── consensus.py             #   共识构建
│   │       │   └── leakage_guard.py         #   时间泄漏防护
│   │       └── llm/                        # LLM 子系统
│   │           ├── deepseek_client.py       #   DeepSeek V4 Pro 客户端
│   │           ├── signal_extraction.py     #   情报信号提取
│   │           └── analysis_prompts.py      # ★ AI 分析 Prompt 模板
│   ├── dashboard/                          # ★ Streamlit 工作台
│   │   ├── app.py                          # 入口 + 侧栏导航
│   │   ├── dashboard_config.py             # 中心配置
│   │   ├── db.py                           # 只读 DB + 自动过期
│   │   ├── pages/                          # 9 个页面
│   │   │   ├── 01_Overview.py              #   系统总览
│   │   │   ├── 02_Match_Prediction.py      #   单场预测 (增强模式)
│   │   │   ├── 03_Match_Context.py         #   比赛上下文 (实时数据)
│   │   │   ├── 04_WC26_Schedule.py         #   WC26 赛程
│   │   │   ├── 05_Teams_Facts.py           #   球队事实库
│   │   │   ├── 06_Database_Explorer.py     #   数据库浏览器
│   │   │   ├── 07_Tournament_Simulator.py  #   赛事模拟器
│   │   │   ├── 08_Creator_Mode.py          #   创作者模式 (AI 生成)
│   │   │   └── 09_Postmatch_Review.py      # ★ 赛后复盘
│   │   └── components/                     # 可复用组件
│   ├── scripts/                            # CLI 工具
│   │   ├── predict_match.py               # 单场预测
│   │   ├── postmatch_review.py             # ★ 赛后复盘
│   │   ├── train_models.py                # 离线训练
│   │   ├── simulate_wc26.py               # 世界杯模拟
│   │   ├── backtest_models.py             # Walk-forward 回测
│   │   ├── news_signal_extractor.py        # RSS 情报提取
│   │   └── add_manual_event.py            # 手动事件录入
│   ├── tests/                              # 118 个测试
│   └── data/                               # SQLite 数据库
├── data/
│   └── team_tournament_status.json         # 48 队硬事实
├── docs/                                   # 项目文档
├── scripts/
│   └── start_dashboard.ps1                 # Dashboard 一键启动
├── .github/workflows/ci.yml               # CI/CD
└── README.md
```

---

## 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 概率模型 | scikit-learn, numpy, scipy, penaltyblog | Dixon-Coles, XGBoost, Elo, Pi |
| 可视化 | Streamlit 1.58, Plotly 6.8 | 本地 Dashboard (9 页) |
| Web API | FastAPI, uvicorn, SQLAlchemy 2.0 | REST API 服务 |
| 数据库 | SQLite (本地), PostgreSQL (生产) | 16,689 场比赛, 441 支球队 |
| LLM | DeepSeek V4 Pro | AI 分析 + 情报提取 |
| 市场数据 | apifootball.com + The Odds API | 实时赔率共识 |
| 天气 | Open-Meteo (免费) | 13 个 WC26 场馆 |
| 前端 | React 18 + TypeScript + Vite + Tailwind | 公开演示页面 |
| CI/CD | GitHub Actions | lint + pytest + 安全扫描 |

---

## 测试

```bash
cd backend
pytest tests/ -v
```

```
118 passed in ~12s
├── 12  Dixon-Coles
├── 24  FusionGraph
├── 18  WC26 Closure
├──  3  Fact Check
├── 24  Dashboard DB (含 SQL 注入检测 + 自动过期)
├── 10  Dashboard Prediction (含确定性验证)
├──  7  Weight Config
├──  8  Prediction Pipeline + RunQuality
├──  5  Market Provider Selection
├──  4  Output Policy + Safety Filter
└──  3  News Signal Validation
```

---

## 赛后复盘案例

| 比赛 | 预测 | 实际 | 评级 | AI 核心发现 |
|---|---|---|---|---|
| 法国 vs 科特迪瓦 | 法国胜 41.8% | 1-2 客胜 | **B+** (优化后) | Enhancer 正确预警，友谊赛轮换是关键变量 |
| 西班牙 vs 伊拉克 | 西班牙胜 52.8% | 1-1 平局 | F | DC/Elo/Pi 三模型一致性过强，即使 Enhancer 权重翻倍也无法覆盖 |

西班牙 vs 伊拉克的 F 评级说明：当三个统计模型一致给出 75%+ 胜率时，单靠权重调整无法纠正——需要引入新的信号类型（如阵容轮换幅度、比赛重要性折扣因子）。

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
- [x] V2.0: Artifact 推理架构 (42 tests)
- [x] V2.2: FusionGraph + 回测优化 + 48 队 + 模拟器 (84 tests)
- [x] V2.4: Streamlit Dashboard + prediction_core + 全中文化 (91 tests)
- [x] V2.5: Local Demo Release — 收口冻结 (91 tests)
- [x] **V2.6: Enhanced — 实时数据 + LLM 分析 + 赛后复盘闭环**

### V2.6 详细

- [x] 市场赔率融合 (apifootball.com + The Odds API, 15% 混合)
- [x] 实时天气 (Open-Meteo, 免费)
- [x] DeepSeek V4 Pro AI 赛前分析 + 视频脚本 + 社媒文案
- [x] 赛后复盘引擎 (Brier/LogLoss/RPS + 7 级评级)
- [x] AI 赛后复盘 (DeepSeek 偏差分析)
- [x] 友谊赛权重自适应 (Enhancer 39.6% → 57.1%)
- [x] 事件自动过期 (SQL 层过滤)
- [x] Dashboard 第 9 页：赛后复盘

### 展望

- [ ] V2.7: 实时首发阵容接入 + 伤病/轮换信号自动提取闭环
- [ ] V3.0: 公开演示版

---

## 安全

- 无 API 密钥提交至 Git（`.env` 由 `.gitignore` 排除）
- CI 自动扫描密钥模式（`sk-`, `ghp_`, `x-apisports-` 等）
- Dashboard 数据库三层只读防护
- 所有默认配置使用占位符

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
  <sub>Built with ❤️ by a football fan · Powered by Python + Streamlit + DeepSeek + Claude Code</sub>
</p>
