# WC26 Predict — 当前项目状态

> 这是项目唯一权威状态文件。所有其他文档如与本文档冲突，以本文档为准。
> 最后更新：2026-06-04 | 当前版本：V1.7 测试版

---

## 版本信息

| 项 | 值 |
|---|---|
| 当前版本 | **V1.7 测试版** |
| 最新 commit | `067c940` — Phase D: news signal extraction pipeline (5-article pilot) |
| 仓库 | github.com/AndyDu0921/wc26-predict |
| 分支 | master |

---

## 数据库统计（2026-06-04 实测）

| 表 | 数量 |
|---|---|
| matches | 16,861 |
| teams | 441 |
| players | 1,355 |
| prediction_snapshots | 234 |
| news_articles | 70 |
| news_signals | 6 (全部 PENDING, enters_model=0) |
| market_odds | 136 |
| postmatch_eval | 48 |
| manual_events | 17 |
| 赛事覆盖 | 96 competitions |
| 数据库表 | 33 |
| 数据库大小 | ~13.3 MB |

---

## 测试状态

```
pytest: 33 passed, 0 failed (33 total)
```

所有测试通过：Dixon-Coles(11/11)、权重配置(8/8)、输出策略(4/4)、市场提供商选择(5/5)、情报信号验证(4/4)。

---

## P0 能力状态

| 能力 | 状态 | 备注 |
|---|---|---|
| 统一预测管线 | ✅ | PredictionPipeline + 6 入口 |
| 权重配置唯一来源 | ✅ | weights.py，4/4 生产入口统一 |
| 市场数据暗影模式 | ✅ | 内部校准，公开隔离 |
| 输出安全过滤 | ✅ | 三模式 + 合规上下文识别 |
| 情报信号管线 | ⚠️ | 6 条 PENDING，审核工作流已建（review_signals.py + enter_manual_signal.py） |
| apifootball.com provider | ⚠️ | 基础 API 可用，odds 需 $15 addon |
| CI | ✅ | GitHub Actions (compileall + pytest + audits + ruff + secret scan + verify_env) |
| Dashboard | ✅ | FastAPI + React MVP |
| WC26 赛程数据 | ✅ | 5 表 244 条（48组+104赛程+32淘汰路径+48积分+12第三名） |
| 商业化文档 | ✅ | README + COMPLIANCE + COMMERCIAL + SECURITY + DATA_SOURCE_POLICY |

---

## 已知问题（按优先级）

| 优先级 | 问题 | 状态 |
|---|---|---|
| 🔴 P0 | news_signals 仅 6 条 PENDING，需人工录入充实 | 工具已就绪，待录入 |
| 🔴 P0 | apifootball.com odds 不可用（需 $15 addon） | 待决定 |
| 🟡 P1 | ADMIN_TOKEN=change-me + 无生产部署 | 待加固 |
| 🟢 P2 | 前端 build 验证未纳入 CI | 待扩展 |
| 🟡 P1 | CI 缺少 lint/typecheck/安全扫描 | 待扩展 |
| 🟢 P2 | ADMIN_TOKEN=change-me 默认值 | 待加固 |
| 🟢 P2 | 无秘密扫描 (gitleaks/detect-secrets) | 待添加 |

---

## 环境配置

| 项 | 值 |
|---|---|
| LLM Provider | deepseek (唯一) |
| LLM Model | deepseek-v4-pro |
| LLM Base URL | https://api.deepseek.com/v1 |
| Python | 3.11.9 |
| 数据库 | SQLite (本地) / PostgreSQL (生产配置) |
| 前端 | React + Vite + TypeScript |
| CI | GitHub Actions (ubuntu-latest) |

---

## 世界杯时间线

```
6/4   ← 今天 (V1.7)
6/11  世界杯开幕（倒计时 7 天）
7/19  世界杯决赛
```

**开幕前必须完成：**
1. news_signals 从 6 → 50+ 条真实信号
2. 手动情报录入流程建立
3. WC26 赛程数据结构（groups/bracket/schedule）
4. 3 个失败测试修复
5. penaltyblog 依赖补全
6. 文档状态统一

---

## 与过期文档的关系

以下文档可能已过期，以本文档为准：

- `docs/ARCHITECTURE.md` (V1.0, 2026-06-01)
- `docs/PRD.md` (V1.0, 2026-06-01)
- `docs/PROJECT_OVERVIEW.md` (V1.6.1)
- `docs/COMPLETION_AUDIT.md` (V1.6.1, 78%)
- `docs/BASELINE_REPORT.md` (Phase 0, 2026-06-03)
- `docs/V1_6_P0_RECHECK.md` (V1.6, 2026-06-04)
- `PROJECT_STATUS.md` (2026-05-12)
- `HANDOFF.md` (2026-05-21)
