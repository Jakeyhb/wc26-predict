# WC26 Predict — Phase 0 Baseline Report

> 生成日期: 2026-06-03  
> 执行版本: Phase 0 (安全检查 + 审计 + 基线)  
> 参考文档: `WC26_predict_FINAL_verified_action_plan.md`  
> 下一阶段: Phase 1 (统一预测入口)

---

## 1. 安全检查结果

### 1.1 Git 状态

| 项目 | 状态 |
|------|------|
| 分支 | `master` (clean, up-to-date with origin) |
| 最新提交 | `b9e5f87` — "Rename: 6.2社交媒体准备库 -> 6.3优化内容" |
| 未暂存修改 | `backend/data/local_stage2.db` (modified) |
| 已删除文件 | `wc26_performance_fix.md`, `wc26_session_analysis.md` |
| 未跟踪文件 | `WC26_predict_FINAL_verified_action_plan.md`, `backend/scripts/_verify_pregeneration.py`, `scripts/` |

**结论**: ✅ Git 状态正常，无意外变更。

### 1.2 数据库备份

| 项目 | 值 |
|------|-----|
| 主数据库 | `backend/data/local_stage2.db` |
| 文件大小 | 13.21 MB |
| 备份路径 | `backend/data/local_stage2_backup_20260603_231732.db` |
| 备份完成 | ✅ |

### 1.3 Python 环境

| 项目 | 值 |
|------|-----|
| Python 版本 | 3.11.9 (MSC v.1938 64-bit) |
| NumPy | 2.4.6 |
| SciPy | 1.17.1 |
| Pandas | 3.0.3 |
| SQLAlchemy | 2.0.50 |
| Pydantic | 2.13.4 |
| httpx | 0.28.1 |

**注意**: FastAPI/uvicorn 列在 `requirements.txt` 但未在 venv 中安装，说明当前项目以脚本模式运行为主，API 服务尚未常驻。

### 1.4 配置检查

| 配置项 | 当前值 | 建议值 | 状态 |
|--------|--------|--------|------|
| LLM_PROVIDER | `deepseek` | `deepseek` | ✅ |
| LLM_MODEL | `deepseek-chat` | `deepseek-v4-pro` | ⚠ 需更新 |
| LLM_BASE_URL | `https://api.deepseek.com/v1` | `https://api.deepseek.com` | ⚠ /v1 后缀需确认 |
| DATABASE | SQLite (local_stage2.db) | SQLite | ✅ |
| REDIS_URL | 已配置但未安装 Redis | — | ⚠ 未使用 |
| ODDS_API_KEY | 已配置 (`backend\.env`) | — | ✅ |
| market_calibrator | `true` (feature_flags.yaml) | `true` | ✅ |
| market_baseline | `false` | `false` | ✅ |

**⚠ 关键发现**: `LLM_MODEL=deepseek-chat` 而非文档要求的 `deepseek-v4-pro`。Phase 3 前必须更新。

---

## 2. 数据库概览

### 2.1 表统计 (29 张表)

| 类别 | 表名 | 行数 | 状态 |
|------|------|------|------|
| 核心数据 | `matches` | 16,861 | ✅ |
| | `match_results` | 16,689 | ✅ |
| | `teams` | 441 | ✅ |
| | `players` | 1,355 | ✅ |
| | `standings` | 96 | ✅ |
| 预测 | `prediction_snapshots` | 230 | ✅ 覆盖175场 |
| | `prediction_runs` | 247 | ✅ |
| 学习 | `postmatch_eval` | 48 | ⚠ 数量偏少 |
| | `prediction_learning_log` | 64 | ✅ |
| | `weekly_learning_reports` | 0 | ⚠ 空 |
| 市场 | `market_odds` | 136 | ✅ 仅覆盖1场比赛 |
| | `market_divergence_log` | 0 | ⚠ 空 |
| 情报 | `news_articles` | 70 | ✅ |
| | `news_signals` | **0** | 🚨 关键缺口 |
| | `content_articles` | 17 | ⚠ 数量偏少 |
| | `manual_events` | 17 | ⚠ 数量偏少 |
| 配置 | `model_weight_config` | 11 | ✅ |
| | `feature_flags` (yaml) | — | ✅ |
| 其他 | `team_aliases` | 457 | ✅ |
| | `source_registry` | 6 | ✅ |
| | `ingest_runs` | 8 | ✅ |

### 2.2 世界杯赛程覆盖

| 阶段 | 场次 |
|------|------|
| 小组赛 (A-L) | 72 |
| Round of 32 | 16 |
| Round of 16 | 8 |
| Quarterfinal | 4 |
| Semifinal | 2 |
| Third Place Playoff | 1 |
| Final | 1 |
| **总计** | **104** |

✅ 全部 72 场小组赛已有预测快照。

### 2.3 日期范围

- 历史比赛: 2015-01-04 → 2026-07-19 (含未来赛程)
- 最新赛果: 2026-06-03
- 世界杯开赛: 2026-06-11 (8 天后)

---

## 3. 审计结果

### 3.1 权重一致性审计 ⚠ HIGH

**核心问题**: 6 个预测入口使用了 **不同的硬编码权重**。

| 入口点 | DC权重 | 增强器权重 | Elo权重 | Pi权重 | 来源 |
|--------|--------|-----------|---------|--------|------|
| `snapshot.py` (World Cup) | 0.55 | 0.25 | 0.05 | 0.05 | `_get_model_config()` |
| `snapshot.py` (UCL Final) | 0.42 | 0.30 | 0.08 | 0.12 | `_get_model_config()` |
| `snapshot.py` (Default) | 0.50 | 0.30 | 0.05 | 0.05 | `_get_model_config()` |
| `prediction_orchestrator.py` | **0.68** | 0.32 | **0.15** | — | 硬编码 |
| `fast_predict.py` | **0.68** | — | **0.15** | — | 硬编码 |
| `learning_engine.py` | **0.68** | 0.32 | **0.15** | — | 硬编码 |

**影响**: 
- DC 权重差异最大 0.13 (orchestrator 0.68 vs snapshot 0.55)
- Elo 权重差异最大 0.10 (orchestrator 0.15 vs snapshot 0.05)
- 同一场世界杯比赛，通过不同入口预测会得到不同概率

**推荐**: Phase 1 统一为 `PredictionPipeline` + `WeightConfig` 单源读取。

### 3.2 预测管线一致性审计 ⚠ MEDIUM

**现状**:
- 6 个预测入口点存在，但未统一
- `pregenerate_wc26.py` → 调用 `snapshot.py` → ✅ 一致
- `prediction_orchestrator.py` → 独立权重逻辑 → ⚠ 与 snapshot 不一致
- `fast_predict.py` → 独立简化流程 → ⚠ 与 snapshot 不一致
- `batch_snapshot.py` / `hourly_predict.py` → 需进一步检查

**快照运行类型**: `manual` (142个) 和 `baseline_v0` (88个)，无混合类型。

### 3.3 公开输出安全审计 ⚠ MEDIUM

**扫描范围**: 报告(16个.md)、根目录文档、article_generator.py、feature_flags.yaml

**禁止词检测**: 405 处匹配

| 类别 | 主要发现 |
|------|----------|
| 报告文件 | `xG`, `主胜`, `客胜`, `概率`, `odds` — 出现在预测报告模板中 |
| 文章生成器 | `主胜`, `客胜`, `概率`, `xG` — 出现在生成模板中 |
| 配置文件 | 赔率/博彩等 — 内部使用，预期存在 |
| 行动方案文档 | 大量合规术语 — 作为规则说明存在，非公开输出 |

**关键判断**: 
- 当前报告模板包含 `public_safe` 模式禁止的内容（概率、xG、比分预测）
- `article_generator.py` 生成的文案包含胜率、xG 等内容
- ⚠ 在启用 `public_safe` / `creator_safe` 模式前，必须实施 `output_policy.py` 过滤层

### 3.4 数据新鲜度审计 🚨 CRITICAL

| 指标 | 状态 | 详情 |
|------|------|------|
| WC26 预测覆盖 | ✅ 72/72 | 全部小组赛已预生成 |
| 快照新鲜度 | ✅ 0天 | 最新快照: 2026-06-03 |
| 原始新闻 | ✅ 70条 | 已采集但未提取信号 |
| **news_signals** | 🚨 **0** | **情报管线完全为空** |
| 手动事件 | ⚠ 17条 | 覆盖稀疏 |
| 赛后评估 | ⚠ 48场 | 学习回路数据量有限 |
| 市场赔率 | ⚠ 136条/1场 | 仅覆盖单一比赛 |
| 周报 | ⚠ 0 | 未生成 |

**最高优先级**: `news_signals = 0` — 没有伤病/停赛/阵容/动机信号进入预测模型，对于世界杯前 8 天来说这是最危险的缺口。

---

## 4. 代码规模统计

| 目录 | 文件数 | 说明 |
|------|--------|------|
| `app/services/` | 28 | 核心预测服务 |
| `app/models/` | — | ORM 模型 (24个) |
| `app/routers/` | — | API 路由 |
| `scripts/` | 37 | CLI 脚本 |
| `config/` | 1 | feature_flags.yaml |
| `reports/` | 16 | 生成的预测报告 |

---

## 5. 风险矩阵

| 风险 | 严重度 | 概率 | 影响 | 缓解措施 |
|------|--------|------|------|----------|
| 情报空洞 (news_signals=0) | 🚨 严重 | 已确认 | 预测模型盲于赛前突发 | Phase 3 DeepSeek 抽取 |
| 权重不一致 | ⚠ 高 | 已确认 | 同场比赛不同入口概率不同 | Phase 1 统一入口 |
| 公开输出含禁止词 | ⚠ 中 | 已确认 | 合规风险 | Phase 4 输出过滤 |
| 市场数据覆盖不足 | ⚠ 中 | 仅1场 | 市场校准无法全面测试 | Phase 2 API-Football |
| LLM模型名不匹配 | ⚠ 低 | 已确认 | deepseek-chat vs v4-pro | 更新 .env |
| 赛后学习数据偏少 | ⚠ 低 | 48场 | 权重优化不够稳定 | 世界杯期间积累 |
| 未安装FastAPI/uvicorn | ⚠ 低 | 已确认 | API/Dashboard不可用 | Phase 5 Dashboard |

---

## 6. 推荐行动计划

### 立即 (Phase 1–2, 今明两天)
1. **统一 PredictionPipeline** — 所有入口使用同一权重配置
2. **新增 weights.py** — 从 `model_weight_config` 表或配置文件单源读取
3. **市场共识 shadow mode** — 内部运行但不影响预测输出

### 世界杯前 (Phase 3–4, 6月11日前)
4. **DeepSeek V4 Pro 情报抽取** — 解决 news_signals=0
5. **输出安全过滤** — public_safe / creator_safe 模式
6. **API-Football 实测** — 确认世界杯赔率覆盖

### 配套修改
7. 更新 `.env` LLM_MODEL → `deepseek-v4-pro`
8. 安装 FastAPI/uvicorn → 支持 Dashboard API

---

## 7. 执行记录

| 步骤 | 脚本/操作 | 结果 |
|------|-----------|------|
| 安全检查 | Git branch, DB backup, env check | ✅ 通过 |
| 审计 1 | `audit_weights_consistency.py` | 3 issues |
| 审计 2 | `audit_prediction_pipeline_consistency.py` | 6 entry points |
| 审计 3 | `audit_public_outputs_no_odds.py` | 405 terms |
| 审计 4 | `audit_data_freshness.py` | 3 issues (1 critical) |
| 基线报告 | `docs/BASELINE_REPORT.md` | 本文档 |

---

## 附录 A: 审计脚本清单

| 脚本 | 路径 |
|------|------|
| 权重一致性 | `backend/scripts/audit_weights_consistency.py` |
| 管线一致性 | `backend/scripts/audit_prediction_pipeline_consistency.py` |
| 输出安全 | `backend/scripts/audit_public_outputs_no_odds.py` |
| 数据新鲜度 | `backend/scripts/audit_data_freshness.py` |
| 数据库审计 | `backend/scripts/_phase0_db_audit.py` |

## 附录 B: 快照数据库备份

- 主库: `backend/data/local_stage2.db` (13.21 MB)
- 备份: `backend/data/local_stage2_backup_20260603_231732.db`
