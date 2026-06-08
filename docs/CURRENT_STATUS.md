# WC26 Predict — 当前项目状态

> 这是项目唯一权威状态文件。所有其他文档如与本文档冲突，以本文档为准。
> 最后更新：2026-06-08 | 当前发布：V2.9 Conservative

---

## 发布信息

| 字段 | 值 |
|---|---|
| Version | 2.9.0-conservative |
| Tag | v2.9-conservative |
| Build Name | V2.9 Conservative — Brier标准化 + FRIENDLY_V4 保守权重 + 版本统一 |
| 定位 | 本地 AI 增强分析工作台 — 模型预测 + 市场赔率 + 天气 + DeepSeek 内容生成 |
| 测试 | 118 passed |

## 包含范围

- 4 模型融合预测引擎（DC + Enhancer + κ-Elo + Pi-Rating）
- FusionGraph 顺序融合（DC → Enhancer → Elo → Pi → normalize）
- **市场赔率接入**（apifootball.com + The Odds API）
- **实时天气**（Open-Meteo 免费 API，13 个 WC26 场馆）
- **DeepSeek V4 Pro AI 分析**（赛前分析文章 + 视频口播脚本 + 社媒文案）
- Artifact 推理架构（离线训练 → 本地加载 → 纯数学计算）
- 48 队硬事实校验 + 104 场 WC26 赛程
- Monte Carlo 赛事模拟器
- Streamlit Dashboard（8 页面全中文）
- 赛后复盘引擎（Brier / LogLoss / RPS / 方向准确率 / 比分命中）
- 自进化引擎（per-match error attribution + signal tracking + market divergence log）
- 统一检查脚本 `scripts/run_checks.ps1`

## Phase 0 修复历史（V2.7 → V2.9）

> **注意**：以下修复均已落地到代码但 **尚未 commit**。所有变更在工作区中。

| 编号 | 版本 | 问题 | 修复 | 文件 |
|------|------|------|------|------|
| C3 | V2.9 | Brier Score 计算错误 — 所有评估值被除以 3 | 移除 `/3` 除法，重校评级阈值 (C: <0.67, D: <1.05, F: ≥1.05) | `dixon_coles.py`, `postmatch.py`, `learning_engine.py` |
| C1 | V2.9 | V2.8 权重基于单场 BEL-TUN 过拟合（Enhancer 57% 降幅，Elo 12× 增幅） | 回滚到 V2.9 保守权重 (FRIENDLY_ADJUSTED_V4: dc=0.35, enhancer=0.25, elo=0.15, pi=0.15) | `weights.py` |
| C4 | V2.9 | 版本号在 3 处硬编码（"1.0.0", "2.0.0", "1.5"）与 version.py 脱节 | 全部改为读取 `app.version.VERSION` | `main.py`, `snapshot_store.py`, `prediction_result.py` |
| H1 | V2.9 | 12 处 `except Exception: pass` 静默吞错误 | 替换为 `logger.warning("...", exc_info=True)` | `prediction_pipeline.py`, `prediction_orchestrator.py`, `elo_ratings.py`, `learning_engine.py`, `database.py` 等 |

### V2.7 — 友谊赛自进化（已 commit: `6929591`）

- 基于 3 场友谊赛赛后数据，自动调整 FRIENDLY 权重
- Enhancer 在友谊赛中权重偏高（0.42），倾向弱队过高

### V2.8 — BEL-TUN 单场适应（已 commit: `f0012ab`）

- 受 Belgium 5-0 Tunisia 比赛强烈影响
- Enhancer 从 0.42 → 0.18（-57%），Elo 从 0.02 → 0.24（×12）
- **结论：样本量不足（n=1 主导），已由 V2.9 取代**

## Phase 0 agent 基础设施（新，未 commit）

| Ticket | 内容 | 文件 |
|--------|------|------|
| 0.1A | CLAUDE.md 重写 — Claude Code ticket 执行规则 | `CLAUDE.md` |
| 0.1B | AGENTS.md 整理 — 所有 agent 通用项目规则 | `AGENTS.md` |
| 0.2 | 统一检查脚本 `run_checks.ps1`（FailFast + ReportOnly） | `scripts/run_checks.ps1` |

## 当前已知问题

| 编号 | 问题 | 状态 |
|------|------|------|
| H2 | 7 文件绕过 ORM 直连 SQLite（`prediction_core.py`, `elo_ratings.py`, `weights.py`, `skellam.py`, `tournament_simulator.py`, `routers/analysis.py`, `learning_engine.py`） | 推迟 — Phase 2 |
| H3 | 3 处 `asyncio.run()` 可能在 FastAPI 事件循环中崩溃 | 待修复 — Ticket 0.5B |
| H4 | Shin Vig 去除公式 `(1-z)/odds` 数学错误 | 待修复 — Ticket 0.4 |
| C2 | 5 个活跃 API Key 明文存储在 `.env` 文件 | 需用户自行轮换 |
| C5 | ADMIN_TOKEN = "change-me" 未更改 | 需用户自行操作 |
| M1-M7 | Dashboard 直连 service、PUBLIC_SAFE 过阻、Pi-Rating 启发式常量、PostgreSQL 密码硬编码、Celery SQLite broker、pickle 缓存过期、analysis.py 重复实现 DeepSeek | 推迟 |

## Next Planned

| Phase | 内容 | 状态 |
|-------|------|------|
| **Phase 0** | 建立可验证基线 | **进行中** — Ticket 0.1A ✅, 0.1B ✅, 0.2 ✅, 0.3 ← 当前 |
| **Phase 0+** | 剩余审计修复 (H4 Shin, H3 asyncio) | 待开始 |
| **Phase 1** | 预测入口盘点 + pipeline contract | 待开始 |
| **Phase 2** | data_sources/ 模块 + pre_match_snapshot | **未执行** |
| **Phase 3** | match_fact + 富赛后复盘 | **未执行** |
| **Phase 4** | 学习闭环 + replay harness | **未执行** |
| **Phase 5** | LLM 报告层重构 | **未执行** |

## 版本历史

| 版本 | 核心突破 | 测试数 |
|---|---|---|
| V1.8 | WC26 数据结构 + CI 扩展 | 33 |
| V1.91 | 硬事实层 + 管线接口 | 42 |
| V2.0 | Artifact 推理 (937× 提速) | 42 |
| V2.2 | FusionGraph + 回测 + 模拟器 | 84 |
| V2.4 | Streamlit Dashboard + prediction_core | 91 |
| V2.5 | Local Demo Release — 收口冻结 | 91 |
| V2.6 | Enhanced — 实时数据 + LLM 分析 | 118 |
| V2.7 | 友谊赛自进化 (3 场) | 118 |
| V2.8 | BEL-TUN 单场适应 (已回滚) | 118 |
| **V2.9** | **Conservative — Brier标准化 + FRIENDLY_V4 + 版本统一** | **118** |
