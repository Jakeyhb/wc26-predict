# WC26 Predict — 2026世界杯分析与预测平台

你是 WC26 Predict 项目的专属 AI 助手。你的职责是协助开发、运维、数据分析，以及回答关于 2026 世界杯的一切问题。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11+, FastAPI, SQLAlchemy, Celery |
| 前端 | React 18, Vite, TypeScript, Tailwind |
| 数据库 | PostgreSQL + pgvector（向量检索），SQLite（本地开发） |
| 缓存/队列 | Redis |
| 预测引擎 | Dixon-Coles + tabular enhancer + IsotonicCalibrator |
| 情报层 | Event Registry + GDELT + RSS → LLM 抽取 |
| 文章生成 | embedding → article_evidence → RAG |
| 调度 | Celery Beat（7 个定时任务） |
| LLM | Qwen / DeepSeek / Zhipu（OpenAI 兼容接口） |

## 目录结构

```
backend/          FastAPI 后端、SQLAlchemy 模型、Celery worker、数据管线、脚本
  scripts/        工具脚本（健康检查、数据初始化、预测测试）
  data/           SQLite 数据库、模型文件
apps/web/         React + Vite 前端（唯一正式前端）
packages/shared/  共享 Zod schema 和类型
nginx/            生产 Nginx 配置和静态资源
apps/api/         已停用的 Cloudflare 原型（仅作参考）
```

## 常用命令

### 开发环境启动（SQLite 模式，推荐）

```bash
# 后端（端口 8000）
cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8000

# 前端（端口 5173）
cd apps/web && npm run dev -- --host 127.0.0.1

# Celery worker + beat（需要时）
cd backend && celery -A app.workers.celery_app worker -B --loglevel=info

# 访问
# 前台: http://127.0.0.1:5173
# 健康检查: http://127.0.0.1:8000/api/health
# 管理后台: http://127.0.0.1:5173/admin/dashboard
```

### 完整环境（PostgreSQL + Redis）

```bash
docker-compose up -d postgres redis
cd backend && alembic upgrade head
cd backend && python scripts/seed_2026_schedule.py
cd backend && python scripts/init_data.py
cd backend && uvicorn app.main:app --reload
cd backend && celery -A app.workers.celery_app worker -B --loglevel=info
cd apps/web && npm run dev
```

### 工具脚本

```bash
cd backend
python scripts/health_check.py              # 17 项健康检查
python scripts/fast_predict.py --home "Argentina" --away "Brazil" --competition "FIFA World Cup 2026"  # 快速预测(JSON)
python scripts/render_report.py --input result.json --output report.md    # 渲染Markdown报告
python scripts/llm_intel_extract.py          # LLM情报抽取(仅在新文章时)
python scripts/snapshot.py --home "A" --away "B"   # 单场完整快照(预测+报告+入库)
python scripts/batch_snapshot.py --limit 10  # 批量预测
python scripts/init_data.py                 # 导入历史数据
python scripts/seed_2026_schedule.py        # 写入 2026 赛程
python scripts/pregenerate_predictions.py   # 批量预生成预测
python scripts/test_prediction.py           # 单场预测测试
python scripts/sync_league_upcoming.py      # 同步联赛赛程
```

### 生产部署

```bash
./deploy.sh  # 自动 git pull → 构建 → 启动全栈
```

## 三次预测更新流程

1. **T-24h** — 赛前 24 小时，拉取最新数据，运行 Dixon-Coles
2. **T-3h** — 赛前 3 小时，重新运行，拉取最新情报/天气/发布会信息，可能阵容调整
3. **首发确认后** — 管理员手动触发第三次更新

## 数据源与免费回退

- 历史比赛/xG：StatsBomb Open Data
- 历史/赛程兜底：openfootball
- 结构化赛程/比分：football-data.org（需要 API key 但免费注册）
- 天气：Open-Meteo
- 新闻发现：GDELT + RSS
- 没有 LLM API key 时，新闻抽取跳过，文章退回模板生成
- 没有 FOOTBALL_DATA_API_KEY 时，仍可用免费回退链路

## 环境变量

- `.env.example` — 模板
- `.env` — 主配置
- `.env.local` — 本地覆盖（优先级最高），当前默认使用 SQLite
- `.env.production.example` — 生产模板

## 常见问题处理

| 问题 | 修复 |
|---|---|
| 前端无数据 | 检查 `apps/web/.env.development` 的 `VITE_API_BASE_URL` |
| `not enough rows` | 先跑 `init_data.py` → `seed_2026_schedule.py` |
| 文章一直 `generating` | 检查 Celery 是否启动，`generate_article_task` |
| 没有证据来源 | 检查 `embed_articles_task`，或手动跑 EmbeddingService |

## 工作约定

- 所有命令在 `/mnt/e/2026世界杯分析` 项目根目录或相应子目录下执行
- 修改代码后优先检查是否破坏健康检查（`python scripts/health_check.py`）
- 数据库变更前先备份 `backend/data/local_stage2.db`
- 优先使用 SQLite 开发模式，除非明确需要 PostgreSQL 功能
- 回答用户问题时用中文，简洁直接
- **WSL 注意**：`.env.local` 中的路径必须是 `/mnt/e/...` 格式，不能是 `E:/...`
- **联赛赛程**：五大联赛 2025-26 赛季于 2026 年 5 月结束，2026-27 赛程预计 6-7 月发布，届时运行 `sync_league_upcoming.py` + `pregenerate_predictions.py --competition-type club` 即可批量生成预测
