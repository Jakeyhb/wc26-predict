# WC26 Predict — 技术方案与系统架构

> **⚠ 本文档可能已过期（V1.0 / 2026-06-01）。** 最新权威状态以 [`CURRENT_STATUS.md`](CURRENT_STATUS.md) 为准。

> V1.0 测试版 | 2026-06-01  
> 仓库: github.com/AndyDu0921/wc26-predict

---

## 一、项目定位

**WC26 Predict** 是一个面向 2026 年 FIFA 世界杯的足球比赛预测分析系统。它不是博彩工具——不显示赔率、不提供投注建议。核心价值在于：用数学模型量化比赛概率，用情报系统注入现实事件影响，赛后自动复盘驱动模型改进。

### 核心原则

- **透明**：每个数据点标注来源、Tier、可靠性
- **可审计**：所有预测落库，事后可追溯
- **自我进化**：赛后自动对比预测 vs 实际，累积经验改进模型
- **合规**：不显示赔率数字、不提供投注建议、不提博彩平台名称

---

## 二、系统架构

```
┌─────────────────────────────────────────────────────────┐
│                      用户层                              │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────┐    │
│  │ Web 前端  │  │ CLI 脚本  │  │ Admin 管理后台      │    │
│  │ React 18  │  │ snapshot │  │ 信号审核/预测触发    │    │
│  └─────┬─────┘  └────┬─────┘  └────────┬───────────┘    │
├────────┼─────────────┼─────────────────┼────────────────┤
│        │         API 层 (FastAPI)        │                │
│        └─────────────┬───────────────────┘                │
├──────────────────────┼────────────────────────────────────┤
│              服务层 (Services)                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐  │
│  │ Dixon-   │ │ Tabular  │ │ Elo      │ │ Pi-Rating  │  │
│  │ Coles    │ │ Enhancer │ │ Ratings  │ │            │  │
│  │ (泊松)   │ │ (HGB 37f)│ │ (评分)   │ │ (进球差)   │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬─────┘  │
│       └─────────────┼────────────┼──────────────┘        │
│                     ▼                                    │
│            ┌────────────────┐                            │
│            │  五层融合引擎   │                            │
│            │  DC+Enh+Elo+   │                            │
│            │  Pi+Weibull    │                            │
│            └───────┬────────┘                            │
│                    ▼                                     │
│  ┌──────────────────────────────────────────┐           │
│  │           信号调整层                       │           │
│  │  SignalAdjuster: 手动事件 + 海拔 + 天气   │           │
│  │  ContextAdjuster: 中立场地/德比/决赛       │           │
│  │  MarketCalibrator: 市场共识校准            │           │
│  └──────────────────┬───────────────────────┘           │
│                     ▼                                     │
│  ┌──────────────────────────────────────────┐           │
│  │           学习引擎 (LearningEngine)        │           │
│  │  错误归因 | 信号追踪 | 市场分歧 | 上下文   │           │
│  └──────────────────────────────────────────┘           │
├──────────────────────────────────────────────────────────┤
│              数据层                                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐  │
│  │ SQLite   │ │ football │ │ StatsBomb│ │ DeepSeek    │  │
│  │ (本地)   │ │ data.org │ │ OpenData │ │ LLM API     │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## 三、预测引擎 — 五层融合

### 第 1 层：Dixon-Coles 泊松模型（权重 ~50%）

基于 Dixon & Coles (1997) 论文的标准足球预测模型。用 Bayesian shrinkage 估计每支球队的攻击/防守参数，生成进球概率矩阵。

- 输入：历史比赛 DataFrame（5000+ 场俱乐部赛 / 2000+ 场国家队比赛）
- 输出：home_xg, away_xg, 6×6 进球概率矩阵, Top 3 比分
- 特点：冷启动时自动降级为先验估计，不会报错崩溃
- 文件：`backend/app/services/dixon_coles.py`

### 第 2 层：Tabular Enhancer 梯度提升（权重 ~30%）

用 37 维特征训练 HistGradientBoostingClassifier，学习 Dixon-Coles 系统性偏差的修正。

- 特征：Elo 评分、近期进球、排名差、xG 效率、休息天数等
- 输出：校正后的三类概率
- 文件：`backend/app/services/tabular_match_model.py`

### 第 3 层：Elo 评分系统（权重 ~5%）

经典的国际象棋评分算法迁移到足球。起点 1500，K 值按赛事重要性分级（世界杯 1.5×）。

- 文件：`backend/app/services/elo_ratings.py`

### 第 4 层：Pi-Rating（权重 ~5%）

Constantinou & Fenton (2012) 的零中心进球差评分。相比 Elo，对比分差距更敏感（5-0 和 1-0 产生不同的评分变化）。

- 依赖：penaltyblog 库（可选，缺失时优雅降级）
- 文件：`backend/app/services/pi_ratings.py`

### 第 5 层：Weibull Copula（权重 ~15%，UCL 场景）

补充 Dixon-Coles 的边际分布，对总进球数建模更准确。仅在欧冠淘汰赛/决赛场景启用。

- 文件：`backend/app/services/weibull_model.py`

### 场景化权重配置

| 场景 | DC 权重 | Enhancer | Elo | Pi | 说明 |
|------|---------|----------|-----|----|------|
| LEAGUE (默认) | 50% | 30% | 5% | 5% | 五大联赛 |
| WORLD_CUP | 55% | 25% | 5% | 5% | 世界杯 |
| UCL_KNOCKOUT | 45% | 28% | 7% | 10% | 欧冠淘汰赛 |
| UCL_FINAL | 42% | 30% | 8% | 12% | 欧冠决赛 |

---

## 四、信号调整系统

### 手动事件注入（当前唯一有效情报入口）

```bash
python scripts/add_manual_event.py --team "Arsenal FC" \
  --type INJURY --player "Bukayo Saka" --severity critical
```

支持的 7 种事件类型：

| 类型 | 最大调整幅度 | 说明 |
|------|-------------|------|
| INJURY | 15% xG↓ | 关键前锋缺阵影响最大 |
| SUSPENSION | 10% | 停赛 |
| RETURN | 8% xG↑ | 关键球员复出 |
| LINEUP_CONFIRMED | 3% | 首发确认 |
| ROTATION_HINT | 12% | 轮换信号 |
| MOTIVATION | 3% | 动力因素 |
| WEATHER | 4% | 天气影响 |

### 场馆海拔调整（V1.0 新增）

高海拔场馆（≥1500m）双方 xG 自动乘以 0.95：

| 场馆 | 海拔 | 所在城市 |
|------|------|----------|
| Estadio Azteca | 2,240m | 墨西哥城 |
| Estadio Akron | 1,560m | 瓜达拉哈拉 |

### 动态信号权重

`signal_track_record` 表追踪每种信号的历史准确率。当某种信号的累计评分 ≥5 条时，自动重新计算权重乘数（accuracy_rate > 80% → 满权重 1.0, < 50% → 降权 0.5）。

---

## 五、自进化闭环

```
┌─────────────────────────────────────────────────────────┐
│  赛前                                                     │
│  snapshot.py ──→ prediction_snapshots (155条)             │
│              ──→ prediction_runs (170条, 双写桥接)        │
│                         │                                │
│                         ▼                                │
│  赛后                                                     │
│  auto_postmatch.py ──→ learning_engine                    │
│                     ──→ prediction_learning_log (64条)    │
│                     ──→ signal_track_record               │
│                         │                                │
│                         ▼                                │
│  优化                                                     │
│  optimize_weights.py ──→ RPS 优化 (47条)                  │
│                       ──→ model_weight_config             │
└─────────────────────────────────────────────────────────┘
```

### 当前指标

| 指标 | 值 | 说明 |
|------|-----|------|
| 赛后评估数 | 48 | 平均 Brier 0.2302 |
| 学习日志 | 64 | 平均 error_magnitude 0.1715 |
| RPS 优化 | 47 条 | 当前 RPS 0.2487 |
| 信号追踪 | 6 种 | 各 0-2 条评分，<5 条未触发重算 |

---

## 六、技术栈

| 层 | 技术 | 用途 |
|---|------|------|
| **后端** | Python 3.11+ / FastAPI | API 服务 |
| **ORM** | SQLAlchemy 2.0 (async) | 数据库访问 |
| **数据库** | SQLite (开发) / PostgreSQL (生产) | 主存储 |
| **队列** | Celery + Redis | 异步任务 + 定时调度 |
| **前端** | React 18 / Vite / TypeScript / Tailwind | Web 界面 |
| **LLM** | DeepSeek (OpenAI 兼容接口) | 新闻信号抽取 / 文章生成 |
| **数据源** | football-data.org / StatsBomb / Open-Meteo | 比赛数据 / xG / 天气 |
| **数值计算** | NumPy / SciPy / scikit-learn / pandas | 模型训练 |

---

## 七、数据库设计

### 核心表

| 表名 | 记录数 | 用途 |
|------|--------|------|
| matches | 16,836 | 比赛（16,662 完赛 + 173 待踢） |
| match_results | 16,662 | 赛果 + xG |
| teams | 581 | 球队（国家队 + 俱乐部） |
| players | 306 | 球员（16 支种子队） |
| prediction_runs | 170 | 预测运行记录（API 侧） |
| prediction_snapshots | 152 | 预测快照（脚本侧，含 component_probs） |
| postmatch_eval | 48 | 赛后评估 |
| prediction_learning_log | 64 | 学习日志（错误归因） |
| manual_events | 17 | 手动注入事件 |
| motivation_events | 492 | 联赛排名驱动的动力标签 |
| standings | 96 | 五大联赛积分榜 |
| signal_track_record | 6 | 信号准确率追踪 |
| news_articles | 70 | 新闻文章（无有效正文） |
| news_signals | **0** | 自动抽取信号 (瓶颈) |
| model_weight_config | 11 | 模型权重配置 |
| context_performance_matrix | 2 | 上下文表现矩阵 |
| market_divergence_log | 0 | 市场分歧日志 |

### 双存储架构（V1.0 桥接）

`prediction_runs`（API 侧）和 `prediction_snapshots`（脚本侧）是两个独立的预测存储表。V1.0 新增了桥接代码：`snapshot.py` 现在同时写入两表，确保 `optimize_weights.py`（依赖 prediction_runs）和 `auto_postmatch.py`（读取 prediction_snapshots）都能正常工作。

---

## 八、数据源

| 来源 | 状态 | 用途 | 限制 |
|------|------|------|------|
| football-data.org | ✅ | 赛程/比分/积分榜/球队 squad | 免费 tier，速率限制 |
| StatsBomb Open Data | ✅ | 历史比赛 + xG | 一次性导入 |
| Open-Meteo | ✅ | 天气（16 天预测窗口） | 免费 |
| DeepSeek LLM API | ✅ | 新闻信号抽取 / 文章生成 | API key 已配置 |
| GDELT | ⚠️ | 新闻文章发现 | 免费版只返回元数据，无正文 |
| RSS (ESPN/BBC) | ⚠️ | 新闻标题+摘要 | ~150 字，多为赛后报道 |
| Event Registry | ❌ | 新闻全文 | 无 API key |

---

## 九、目录结构

```
wc26-predict/
├── backend/                    # Python 后端
│   ├── app/
│   │   ├── main.py             # FastAPI 入口
│   │   ├── config.py           # 配置（Pydantic Settings）
│   │   ├── database.py         # 数据库连接
│   │   ├── models/             # SQLAlchemy 模型 (28 个)
│   │   ├── routers/            # API 路由 (matches/stats/admin/signals/feedback)
│   │   ├── services/           # 核心服务
│   │   │   ├── dixon_coles.py       # Dixon-Coles 泊松模型
│   │   │   ├── tabular_match_model.py # Tabular Enhancer
│   │   │   ├── elo_ratings.py       # Elo 评分
│   │   │   ├── pi_ratings.py        # Pi-Rating
│   │   │   ├── weibull_model.py     # Weibull Copula
│   │   │   ├── signal_adjuster.py   # 信号调整 + 海拔
│   │   │   ├── context_adjuster.py  # 上下文调整
│   │   │   ├── market_calibrator.py # 市场校准
│   │   │   ├── learning_engine.py   # 学习引擎
│   │   │   ├── snapshot_store.py    # 快照入库 + 双写
│   │   │   ├── llm_service.py       # LLM 适配器
│   │   │   └── model_cache.py       # 模型缓存
│   │   ├── schemas/            # Pydantic schemas
│   │   ├── workers/            # Celery 任务 (7 个定时任务)
│   │   └── utils/              # 工具函数
│   ├── scripts/                # CLI 脚本
│   │   ├── snapshot.py         # ★ 主入口：单场预测快照
│   │   ├── batch_snapshot.py   # 批量预测
│   │   ├── auto_postmatch.py   # 赛后自动复盘
│   │   ├── optimize_weights.py # RPS 权重优化
│   │   ├── add_manual_event.py # 手动事件注入
│   │   ├── _fix_players.py     # 球员关联审计修复
│   │   └── ...
│   ├── data/
│   │   └── local_stage2.db     # SQLite 数据库
│   ├── model_artifacts/        # 模型持久化文件
│   └── requirements.txt
├── apps/web/                   # React 前端
├── packages/shared/            # 共享类型
├── nginx/                      # 生产 Nginx
├── docs/                       # 文档
├── docker-compose.yml
└── deploy.sh
```

---

## 十、开发环境

### 启动（SQLite 模式，推荐）

```bash
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000   # API 服务
cd apps/web && npm run dev                            # 前端
```

### 运行预测

```bash
cd backend
python scripts/snapshot.py --home "Argentina" --away "Brazil" \
  --competition "FIFA World Cup 2026" --neutral
```

### 手动注入赛前情报

```bash
python scripts/add_manual_event.py --team "England" \
  --type INJURY --player "Harry Kane" --severity critical
```

### 赛后复盘

```bash
python scripts/auto_postmatch.py --days 1     # 昨天完赛的比赛
python scripts/optimize_weights.py --dry-run  # 权重优化预览
```

---

## 十一、已知限制

1. **news_signals = 0** — 自动新闻情报采集链路不通（GDELT/RSS 无正文），当前仅靠手动注入
2. **WC26 baseline 不完整** — 34 支国家队缺训练数据，预测时可能报 KeyError
3. **lineup 不可用** — football-data.org 免费 tier 不返回赛前首发
4. **Celery 未运行** — 7 个定时任务代码就绪但进程未启动
5. **数据空窗期** — 五大联赛 2025-26 赛季已结束，新赛季赛程尚未发布
