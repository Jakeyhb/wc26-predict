# 架构说明

本项目当前正式技术栈为：

- `backend/`：Python + FastAPI + SQLAlchemy + PostgreSQL + Redis + Celery
- `apps/web/`：React + Vite 前端，包含公开页面与 `/admin` 管理后台
- `packages/shared/`：前后端共享的 Zod contract 和类型定义

以下目录已停止维护，仅保留作参考：

- `apps/api/`：早期 Cloudflare Workers 原型
- `frontend/`：更早期的前端实现

## 当前运行链路

1. `football-data.org` 同步历史/未来比赛
2. `StatsBomb Open Data` 补充历史赛事 xG
3. `Dixon-Coles` 模型训练并生成预测
4. `news_ingest_service` 抓取新闻
5. `llm_service` 提取结构化信号
6. 管理员在 `/admin` 审核信号、手动触发预测、发布文章
7. Celery 定时任务驱动赛程刷新、新闻采集、预测触发、赛后复盘

## 生产部署

- `apps/web` 先构建为静态资源
- 构建产物复制到 `nginx/html/`
- `nginx` 负责静态文件服务与 `/api/` 反向代理
- `backend` 通过 `gunicorn + uvicorn worker` 提供 API
- `celery` 负责异步任务与 Beat 定时调度

生产静态文件采用“构建后打进 nginx 镜像”的方式，不使用运行时 volume 挂载前端 `dist`。
