# AGENTS.md — WC26 Predict (所有 Agent 通用项目规则)

## 1. Project Invariant

本项目是 **足球比赛预测系统**，核心闭环不变：

```
pre-match data → prediction → post-match facts → review → replay-based learning
```

1. **赛前多源数据融合** — 历史比赛、球队/球员状态、新闻信号、天气、赔率
2. **概率预测引擎** — Dixon-Coles + Enhancer + κ-Elo + Pi-Rating
3. **赛后富数据复盘** — 技术统计、比赛事实、预测偏差、信号归因
4. **Replay-based learning** — 权重调整必须通过 replay/backtest gate

## 2. Universal Rules for All Agents

所有 agent（Claude Code、Hermes、及未来新增 agent）必须遵守：

- **不提交 secrets** — `.env`、API key、token、credentials 不得出现在任何 commit 中
- **不硬编码 API key** — 所有密钥通过环境变量或 `.env` 读取
- **不删除未知文件** — 任何文件删除前必须先确认其用途
- **不一次性重构多个 phase** — 每次只完成一个 ticket 的范围
- **不伪造测试结果** — 不把 "看起来正常" 当作验证通过
- **不编造仓库中不存在的文件或模块** — 引用前必须先搜索确认
- **如果不确定，必须先搜索仓库再回答** — 不在不确定的状态下给建议

## 3. Engineering Rules

- **一个 PR 对应一个 ticket** — 不混入其他改动
- **每个 ticket 必须有验证命令** — 验收标准在 ticket 中写清楚，执行后用命令输出证明
- **业务逻辑变更必须有测试或 smoke check** — 纯文档/配置变更除外
- **数据缺失必须显式记录** — 不允许静默降级（silent fallback），缺失原因写入 `degraded_reasons` 或 `missing_data` 字段

## 4. Technical Stack

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11+, FastAPI, SQLAlchemy, Celery |
| 前端 | React 18, Vite, TypeScript, Tailwind |
| 数据库 | PostgreSQL + pgvector（向量检索），SQLite（本地开发） |
| 缓存/队列 | Redis |
| 预测引擎 | Dixon-Coles + Tabular Enhancer + κ-Elo + Pi-Rating |
| 情报层 | GDELT + RSS → LLM 抽取 |
| LLM | DeepSeek / Qwen（OpenAI 兼容接口） |

## 5. Directory Structure

```
backend/              FastAPI 后端、SQLAlchemy 模型、服务层、脚本
  app/
    services/         预测引擎、赛后复盘、学习引擎
    models/           ORM 模型
    routers/          API 路由
  scripts/            工具脚本（预测、快照、数据同步、健康检查）
  data/               SQLite 数据库、模型文件
  tests/              测试
apps/web/             React + Vite 前端
docs/                 项目文档
scripts/              Repo-root 级脚本（检查、启动）
```

## 6. Common Commands

### 开发环境

```bash
# 后端
cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8000

# 前端
cd apps/web && npm run dev -- --host 127.0.0.1

# 全量测试
cd backend && python -m pytest -q

# 健康检查
cd backend && python scripts/health_check.py
```

### 常用脚本

```bash
cd backend
python scripts/fast_predict.py --home "Argentina" --away "Brazil" --competition "FIFA World Cup 2026"
python scripts/snapshot.py --home "A" --away "B"
python scripts/batch_snapshot.py --limit 10
python scripts/init_data.py
python scripts/seed_2026_schedule.py
```

## 7. Data Sources

- 历史比赛/xG：StatsBomb Open Data
- 历史/赛程兜底：openfootball
- 结构化赛程/比分：football-data.org（需 API key）
- 天气：Open-Meteo
- 新闻发现：GDELT + RSS
- 赔率：API-Football / The Odds API

## 8. Boundaries

不同 agent 指令文件有明确边界，不得混用：

| 文件 | 受众 | 内容 |
|------|------|------|
| `CLAUDE.md` | Claude Code | Claude Code 的 ticket 执行规则、验证规则、停止条件 |
| `AGENTS.md` | 所有 Agent | 通用项目规则、工程约定、技术栈、常用命令 |
| Hermes 监督流程 | Hermes Agent | PR 审查流程、监督协议 — 应放在 Hermes skill 或 `docs/agent_workflow/hermes_agent_supervision_playbook_wc26.md` |

- **AGENTS.md 不放** Hermes 的具体 PR 审查 check-list
- **AGENTS.md 不放** GitHub PR 审查模板
- **CLAUDE.md 不放** Hermes 的监督职责
