# WC26 Predict

WC26 Predict 是一个面向 2026 世界杯的预测与情报分析平台，当前正式主线为 `backend/`（Python/FastAPI）+ `apps/web/`（React/Vite）+ `packages/shared`（共享 contract）。

`apps/api/` 是早期 Cloudflare Workers 原型，**已停用，仅保留作架构参考**。

## 系统架构
- 预测引擎：`Dixon-Coles + tabular enhancer + IsotonicCalibrator`
- 情报层：`Event Registry + GDELT + RSS -> LLM 抽取 -> richer signal schema`
- 证据链：`embedding -> article_evidence -> RAG article generation`
- 数据源：`football-data.org + StatsBomb Open Data + openfootball + Open-Meteo`
- 任务调度：`Celery Beat`，当前包含 7 个定时任务
- 向量检索：`pgvector`（Postgres）+ 本地 `sentence-transformers` 兜底
- LLM：支持 `Qwen / DeepSeek / Zhipu` 的 OpenAI 兼容接口切换

## 快速开始（开发环境）
1. 复制 [`.env.example`](/E:/2026世界杯分析/.env.example:1) 为 `.env`，填入可用配置。
2. 本机默认覆盖配置写在 [`.env.local`](/E:/2026世界杯分析/.env.local:1)：
   - 当前默认使用本地 SQLite 数据库 `backend/data/local_stage2.db`
   - 后端默认地址 `http://127.0.0.1:8000`
   - 这份文件优先级高于 `.env`，适合直接本机启动
3. 安装后端依赖：
   `cd backend && pip install -r requirements.txt`
4. 启动 FastAPI：
   `uvicorn app.main:app --host 127.0.0.1 --port 8000`
5. 启动前端：
   `cd ../apps/web && npm install && npm run dev -- --host 127.0.0.1`

## 本机验证版（当前推荐）
1. 2026 赛程和五大联赛/UCL 数据已经预写入 [backend/data/local_stage2.db](/E:/2026世界杯分析/backend/data/local_stage2.db:1)。
2. 直接启动后端：
   `cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8000`
3. 直接启动前端：
   `cd apps/web && npm run dev -- --host 127.0.0.1`
4. 访问：
   - 前台：`http://127.0.0.1:5173`
   - 后端健康检查：`http://127.0.0.1:8000/api/health`
   - 管理后台：`http://127.0.0.1:5173/admin/dashboard`

## 使用 PostgreSQL / Redis 的完整开发环境
1. 复制 [`.env.example`](/E:/2026世界杯分析/.env.example:1) 为 `.env`
2. 启动依赖：
   `docker-compose up -d postgres redis`
3. 安装后端依赖：
   `cd backend && pip install -r requirements.txt`
4. 执行数据库迁移：
   `alembic upgrade head`
5. 写入 2026 赛程种子：
   `python scripts/seed_2026_schedule.py`
6. 导入历史数据：
   `python scripts/init_data.py`
7. 启动 FastAPI：
   `uvicorn app.main:app --reload`
8. 另一个终端启动 Celery：
   `celery -A app.workers.celery_app worker -B --loglevel=info`
9. 启动前端：
   `cd ../apps/web && npm install && npm run dev`

说明：
- 没有 `FOOTBALL_DATA_API_KEY` 时，`init_data.py` 仍可走 `openfootball + StatsBomb` 免费链路。
- 没有 `LLM_API_KEY` 时，新闻抽取会跳过，文章会退回模板生成，但主流程仍可运行。

## 生产部署
1. 复制 [`.env.production.example`](/E:/2026世界杯分析/.env.production.example:1) 为 `.env`
2. 填入生产数据库、Redis、API key、`ADMIN_TOKEN`
3. 执行：

```bash
./deploy.sh
```

部署脚本会完成：
- `git pull origin main`
- `apps/web` 构建
- 复制前端静态文件到 `nginx/html`
- 构建 `backend / celery / nginx` 镜像
- 启动 `postgres / redis / backend / celery / nginx`
- 执行 `alembic upgrade head`

## 三次预测更新流程
1. `T-24h`
2. `T-3h`
3. `首发确认后`

第三次更新默认仍由管理员手动触发，免费数据路线下不依赖自动首发抓取。

## 健康检查

```bash
cd backend
python scripts/health_check.py
```

当前健康检查会验证 17 项，包括：
- PostgreSQL / Redis
- football-data / GDELT / LLM 可达性
- Dixon-Coles 训练与预测
- FastAPI 核心接口
- Celery worker 与 7 个 Beat 任务
- 2026 赛程种子
- IsotonicCalibrator
- EmbeddingService
- 前端 build、联赛数据加载、模型分类型 artifact

## API Keys 获取
- `FOOTBALL_DATA_API_KEY`：
  [football-data.org 免费注册](https://www.football-data.org/client/register)
- `EVENT_REGISTRY_API_KEY`：
  [Event Registry 注册](https://eventregistry.org/register)
- `Qwen`：
  [DashScope](https://dashscope.aliyuncs.com)
- `DeepSeek`：
  [DeepSeek Platform](https://platform.deepseek.com)

## 免费优先数据路线
- 历史比赛与 xG：
  [StatsBomb Open Data](https://github.com/statsbomb/open-data)
- 历史/赛程兜底：
  `openfootball + openfootball/worldcup.json`
- 结构化赛程 / 比分：
  [football-data.org](https://www.football-data.org/)
- 天气：
  [Open-Meteo](https://open-meteo.com/en/docs)
- 新闻发现：
  `GDELT + RSS`

## 目录结构
- [backend](/E:/2026世界杯分析/backend): FastAPI、SQLAlchemy、Celery、数据管道、脚本
- [apps/web](/E:/2026世界杯分析/apps/web): 唯一正式前端代码，React + Vite 用户站点与管理后台
- [packages/shared](/E:/2026世界杯分析/packages/shared): Zod schema 与共享类型
- [nginx](/E:/2026世界杯分析/nginx): 生产静态资源与反代配置
- [apps/api](/E:/2026世界杯分析/apps/api): 已停用的 Cloudflare 原型

说明：
- 前端代码位于 `apps/web/`
- 使用 `npm run build --workspace @wc26/web` 构建
- 构建产物复制到 `nginx/html`，由 Nginx 统一服务

## 常见问题
- 前端打开没有数据：
  检查 `apps/web/.env.development` 里的 `VITE_API_BASE_URL`
- `Prediction model not enough rows`：
  先跑 `init_data.py` 和 `seed_2026_schedule.py`
- 文章一直是 `generating`：
  检查 Celery 是否已启动，`generate_article_task` 是否在跑
- 没有证据来源：
  检查 `embed_articles_task` 是否执行，或手动跑一次 `EmbeddingService.batch_embed_articles`
- `FOOTBALL_DATA_API_KEY` 暂时没有：
  系统仍可用免费回退链路运行，但未来赛程和终场比分同步会弱一些
