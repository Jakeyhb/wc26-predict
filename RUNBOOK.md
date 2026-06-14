# WC26 Predict — 运维手册

> 版本：V3.5 closed-loop foundation | 最后更新：2026-06-14
> 面向：个人研究使用 | **非生产环境**

---

## 1. 环境要求

- **Python 3.11+**（推荐 3.11.9）
- **Git**
- **Windows** / macOS / Linux
- （可选）Docker + Docker Compose（生产部署用）
- 磁盘空间：~500MB（含 .venv + artifacts + SQLite 数据库）

---

## 2. 首次安装

### 2.1 克隆仓库

```bash
git clone https://github.com/AndyDu0921/wc26-predict.git
cd wc26-predict
git checkout master
```

### 2.2 创建 Python 虚拟环境

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 2.3 安装依赖

```bash
pip install -r requirements.txt
# 约 2-3 分钟（首次需要编译 numpy/scipy/scikit-learn）
```

### 2.4 配置 API 密钥

```bash
# 复制示例配置
cp .env.example .env

# 编辑 .env，填写需要的 API Key：
#   LLM_API_KEY=sk-...              # DeepSeek V4 Pro (AI 分析功能)
#   FOOTBALL_DATA_API_KEY=...       # football-data.org (数据同步)
#   ODDS_API_KEY=...                # The Odds API (市场赔率)
#   APIFOOTBALL_COM_KEY=...         # apifootball.com (赔率备用)
#   API_FOOTBALL_KEY=...            # API-Sports (赔率备用)
```

**重要**：`ADMIN_TOKEN` 必须修改为随机字符串：
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
# 将输出复制到 .env 的 ADMIN_TOKEN= 行
```

### 2.5 验证安装

```bash
# 环境验证
python scripts/verify_env.py

# 全量测试
python -m pytest tests/ -q
# 预期输出：187 passed

# 健康检查
python scripts/health_check.py
```

---

## 3. 训练模型（首次使用必须）

```bash
python scripts/train_models.py --team-type national
# 耗时：~45s-3min（取决于硬件）
# 输出：backend/artifacts/models/*.pkl + ratings/*.json + dataframes/*.pkl
```

---

## 4. 日常使用

### 4.1 CLI 预测（最常用）

```bash
# 基础预测
python scripts/predict_wc26.py \
  --home "Argentina" --away "Brazil" \
  --competition "FIFA World Cup 2026" \
  --neutral

# 友谊赛预测
python scripts/predict_wc26.py \
  --home "China PR" --away "Thailand" \
  --competition "International Friendly" \
  --neutral

# 输出 Markdown 报告并尝试保存快照
python scripts/predict_wc26.py \
  --home "Spain" --away "Germany" \
  --competition "International Friendly" \
  --neutral
```

**预测模式说明：**

| `--mode` | 包含组件 | 耗时 |
|----------|----------|------|
| `baseline` | Dixon-Coles only | <1s |
| `standard` | DC + Enhancer + Elo | ~2s |
| `full` | DC + Enhancer + Elo + Pi | ~2.5s |
| `research-full` | full + Weibull (可选) | ~3s |

### 4.2 启动 Dashboard

```powershell
# Windows PowerShell
powershell -File scripts/start_dashboard.ps1

# 或直接用 streamlit
cd backend
streamlit run dashboard/home.py --server.port 8501
```

浏览器打开 http://localhost:8501

Dashboard 页面：
1. 系统总览 — 数据库状态、版本信息
2. 单场预测 — 选择球队进行增强预测（含天气/市场/AI）
3. 比赛上下文 — 实时数据查询
4. WC26 赛程 — 104 场比赛完整赛程
5. 球队事实库 — 48 队硬事实
6. 数据库浏览器 — 只读浏览
7. 赛事模拟器 — Monte Carlo 模拟
8. 创作者模式 — AI 生成赛前分析/视频脚本/社媒文案
9. 赛后复盘 — Brier/RPS/LogLoss 评估

### 4.3 赛后复盘

```bash
python scripts/postmatch_review.py \
  --home "Spain" --away "Iraq" \
  --home-goals 1 --away-goals 1 \
  --ai-review
```

### 4.4 世界杯模拟

```bash
python scripts/simulate_wc26.py --runs 10000
```

### 4.5 数据同步

```bash
# 同步 football-data.org 比赛数据
python scripts/sync_results.py

# 同步联赛积分榜
python scripts/sync_standings.py
```

---

## 5. 启动完整后端（FastAPI + Celery）

### 5.1 本地开发模式

```bash
# 终端 1: FastAPI
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 终端 2: Celery Worker + Beat
cd backend
celery -A app.workers.celery_app worker -B --loglevel=info
```

### 5.2 Docker 部署

```bash
# 本地
docker compose up -d

# 生产（Nginx + Gunicorn）
docker compose -f docker-compose.prod.yml up -d
```

---

## 6. 健康检查与故障排查

### 6.1 统一健康检查

```powershell
# 完整检查（fail-fast — 任何失败退出非零）
.\scripts\run_checks.ps1

# 只读诊断模式（输出全部结果但不中断）
.\scripts\run_checks.ps1 -ReportOnly
```

### 6.2 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `KeyError: Unknown team in fitted model` | 模型未训练该球队 | 重新运行 `train_models.py`，或确认球队名拼写正确 |
| `FileNotFoundError: dc.pkl` | Artifacts 未生成 | 运行 `python scripts/train_models.py --team-type national` |
| `pipeline_status: degraded` | 某个模型加载失败 | 查看 `degraded_reasons` 字段了解详情 |
| `ADMIN_TOKEN is still "change-me"` | 未修改默认令牌 | 见 §2.4 生成随机令牌 |
| `Odds API unreachable` | API Key 未配置或无效 | 检查 `.env` 中的 `ODDS_API_KEY` 是否正确 |
| `LLM API key not configured` | DeepSeek Key 缺失 | 检查 `.env` 中的 `LLM_API_KEY` |
| `Database unavailable` | SQLite 文件不存在 | 确认 `backend/data/local_stage2.db` 存在 |
| legacy rows show missing `match_id` | 旧预测缺少可验证比赛上下文 | 运行 `python scripts/audit_closed_loop_integrity.py`，确认已进入 `closed_loop_resolution_ledger`；不要伪造 `match_id` |
| active learning traceability fails | 学习日志外键缺失或 UUID 格式不一致 | 先 dry-run `python scripts/repair_closed_loop_integrity.py`，确认后再加 `--apply` |

### 6.3 数据库备份

```bash
# 备份 SQLite 数据库
cp backend/data/local_stage2.db "backend/data/local_stage2.db.bak.$(date +%Y%m%d_%H%M)"
```

### 6.4 日志位置

```bash
# 应用日志
backend/logs/

# Celery 日志（Docker）
docker logs wc26-celery-1

# FastAPI 日志（Docker）
docker logs wc26-backend-1
```

### 6.5 闭环完整性

```bash
cd backend

# 只读审计：检查 prediction -> result -> learning 是否可追溯
python scripts/audit_closed_loop_integrity.py

# 修复预览：只规范化可证明等价的 prediction_run_id，并隔离旧学习日志
python scripts/repair_closed_loop_integrity.py

# 执行修复：执行前建议备份 backend/data/local_stage2.db
python scripts/repair_closed_loop_integrity.py --apply
```

规则：

- 不为旧样本生成虚假 `match_id`。
- 无法唯一解析的旧数据必须记录在 `closed_loop_resolution_ledger`。
- `legacy_untraceable` / `legacy_ambiguous` 学习日志不得参与 active learning。
- 真实 xG 覆盖不足是数据质量风险，不应用估算值伪装为实测数据。

### 6.6 完整预测契约

Dashboard 单场预测页提供两种实际使用方式：

- 普通增强：尝试实时源，失败时返回降级结果。
- 严格完整：勾选“严格完整”，并填写 `match_id`、场地、开球时间；系统会强制启用天气与市场数据。

每次预测都应检查 `source_status`：

- `used`：已实际使用或纳入 shadow telemetry。
- `unavailable`：已尝试，但该场无可用数据。
- `failed`：已尝试，但调用失败。
- `skipped`：未尝试，不能在分析里声称使用过。

AI 内容生成只能引用 `status=used` 的数据源。若严格完整模式缺少上下文或关闭实时源，系统会直接拒绝运行。

---

## 7. CI/CD

GitHub Actions 在每次 push/PR 到 `master` 时自动运行：

- Python 语法编译检查
- pytest 187 个测试
- 审计脚本（权重一致性、公开输出、闭环完整性）
- Ruff lint (E, F, W)
- 依赖完整性检查 (`pip check`)
- 环境变量验证
- 密钥泄露扫描

---

## 8. 项目关键路径速查

| 用途 | 命令 |
|------|------|
| 安装依赖 | `cd backend && pip install -r requirements.txt` |
| 训练模型 | `cd backend && python scripts/train_models.py --team-type national` |
| 预测比赛 | `cd backend && python scripts/predict_wc26.py --home "A" --away "B" --competition "C" --neutral` |
| Dashboard | `powershell -File scripts/start_dashboard.ps1` |
| 全量测试 | `cd backend && python -m pytest tests/ -q` |
| 健康检查 | `cd backend && python scripts/health_check.py` |
| 环境验证 | `cd backend && python scripts/verify_env.py` |
| 闭环审计 | `cd backend && python scripts/audit_closed_loop_integrity.py` |
| 闭环修复 | `cd backend && python scripts/repair_closed_loop_integrity.py --apply` |
| 世界杯模拟 | `cd backend && python scripts/simulate_wc26.py --runs 10000` |
| 赛后复盘 | `cd backend && python scripts/postmatch_review.py --home "A" --away "B" --home-goals X --away-goals Y` |

---

## 9. 安全提醒

- ❌ 永远不要提交 `.env` 文件到 Git
- ❌ 永远不要在代码中硬编码 API Key
- ✅ 每月轮换一次 API Key
- ✅ `ADMIN_TOKEN` 必须修改为非默认值
- ✅ 生产环境使用 `docker-compose.prod.yml`（不含 --reload）
- ✅ 公开部署前确认 `output_policy` 为 `public_safe` 模式
