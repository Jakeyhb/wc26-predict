# ASYNCIO.RUN() 调用点盘点

> 盘点日期: 2026-06-08 | 状态: 只读分析，未修改代码
> 搜索范围: 整个仓库，匹配 `asyncio.run(`
> 下一步: Ticket 0.5B — 修复 HIGH 风险点

---

## 发现概要

| 风险等级 | 数量 | 说明 |
|----------|------|------|
| **HIGH** | 3 | `app/services/` 层 — 可能被 FastAPI async route 调用 |
| **MEDIUM** | 2 | `tests/` + `scripts/` 非标准入口 — 可能在已有事件循环上下文中执行 |
| **SAFE** | 27 | CLI 脚本 `if __name__ == "__main__"` / Celery worker |
| **NOT IN SCOPE** | 7 | `cheat-on-content/` — 独立项目，不处理 |
| **总计（WC26）** | **32** | |

---

## HIGH 风险 — `app/services/` 层

这 3 处位于 service 层函数体内，可能被 FastAPI async route、pytest-asyncio、Dashboard 或预测管线调用。

| # | 文件 | 行号 | 函数/位置 | 当前用途 | 调用场景 | 风险等级 | 建议处理 |
|---|------|------|-----------|----------|----------|----------|----------|
| 1 | `app/services/weather_service.py` | 215 | `WeatherService.get_match_weather()` | 同步 wrapper 包装 `fetch_match_weather()` 异步方法 | 被 `prediction_enhanced.py` / `prediction_orchestrator.py` 从 sync context 调用；若被 FastAPI async route 调用则崩溃 | **HIGH** | 替换为 `asyncio.get_running_loop()` 检测 + 结构化回退 |
| 2 | `app/services/prediction_enhanced.py` | 390 | `_generate_llm_analysis()` | 同步 wrapper 包装 `_generate_llm_analysis_async()` | 被增强预测流程从 sync context 调用；若被 async pipeline 调用则崩溃 | **HIGH** | 替换为事件循环检测 + `degraded_reason` |
| 3 | `app/services/market/sync_provider.py` | 48 | `MarketOddsSyncProvider.fetch_consensus()` | 同步 wrapper 包装 `_fetch_consensus_async()` | 被 sync pipeline 调用；若被 async route 调用则崩溃 | **HIGH** | 替换为事件循环检测 + `degraded_reason` |

**共同特征**: 这三处都是"同步函数体内调用异步函数"的桥接模式，为 Streamlit/Dashboard sync context 设计。问题在于它们被 `app/services/` 模块导出，任何代码（包括 FastAPI async routes）都可以 import 并调用它们。

---

## MEDIUM 风险

| # | 文件 | 行号 | 函数/位置 | 当前用途 | 调用场景 | 风险等级 | 建议处理 |
|---|------|------|-----------|----------|----------|----------|----------|
| 4 | `tests/test_market_provider_selection.py` | 30 | `test_apifootball_com_provider()` | 测试中直接调用 `asyncio.run(provider.is_available())` | pytest 可能已通过 pytest-asyncio 配置事件循环，`asyncio.run()` 在已有循环中崩溃 | **MEDIUM** | 改用 `@pytest.mark.asyncio` + `await` |
| 5 | `scripts/postmatch_review.py` | 99 | `_generate_ai_review()` | 同步 helper 包装 `_generate_ai_review_async()` | 仅在 CLI `main()` 中调用，但如果函数被外部 import 则危险 | **MEDIUM** | 添加 `if __name__ == "__main__"` guard 或移入 main 块 |

---

## SAFE — CLI 脚本 `if __name__ == "__main__"` 入口

以下 24 处均位于 `backend/scripts/*.py` 的 `if __name__ == "__main__":` 或等效顶层的脚本入口函数中。它们在独立进程中运行，不可能有预先存在的事件循环。**不需要修改**。

| # | 文件 | 行号 | 调用形式 |
|---|------|------|----------|
| 6 | `scripts/fast_predict.py` | 134 | `asyncio.run(main(...))` |
| 7 | `scripts/auto_postmatch.py` | 135 | `asyncio.run(auto_postmatch(...))` |
| 8 | `scripts/extract_news_signals.py` | 108 | `asyncio.run(main())` |
| 9 | `scripts/daily_ops.py` | 208 | `asyncio.run(main())` |
| 10 | `scripts/add_manual_event.py` | 323 | `asyncio.run(main())` |
| 11 | `scripts/check_market_providers.py` | 232 | `asyncio.run(main())` |
| 12 | `scripts/batch_snapshot.py` | 312 | `asyncio.run(main(...))` |
| 13 | `scripts/test_prediction.py` | 110 | `asyncio.run(run())` |
| 14 | `scripts/seed_predictions.py` | 355 | `asyncio.run(run())` |
| 15 | `scripts/sync_standings.py` | 291 | `asyncio.run(main(...))` |
| 16 | `scripts/phase_d_extract_5.py` | 295 | `asyncio.run(run())` |
| 17 | `scripts/seed_players.py` | 235 | `asyncio.run(main(...))` |
| 18 | `scripts/sync_results.py` | 188 | `asyncio.run(main())` |
| 19 | `scripts/seed_2026_schedule.py` | 270 | `asyncio.run(run())` |
| 20 | `scripts/sync_league_upcoming.py` | 28 | `asyncio.run(run())` |
| 21 | `scripts/news_signal_extractor.py` | 194 | `asyncio.run(main())` |
| 22 | `scripts/review_news_signals.py` | 126 | `asyncio.run(main())` |
| 23 | `scripts/snapshot.py` | 1387 | `asyncio.run(main(...))` |
| 24 | `scripts/llm_intel_extract.py` | 55 | `asyncio.run(main(...))` |
| 25 | `scripts/health_check.py` | 410 | `asyncio.run(main(...))` |
| 26 | `scripts/lineup_probe.py` | 236 | `asyncio.run(main())` |
| 27 | `scripts/pregenerate_wc26.py` | 112 | `asyncio.run(main())` |
| 28 | `scripts/init_data.py` | 87 | `asyncio.run(run_init(...))` |
| 29 | `scripts/fetch_market_odds_api_football.py` | 98 | `asyncio.run(main())` |

---

## SAFE — Celery Worker

| # | 文件 | 行号 | 函数/位置 | 当前用途 | 调用场景 | 风险等级 | 建议处理 |
|---|------|------|-----------|----------|----------|----------|----------|
| 30 | `app/workers/tasks.py` | 33 | `_run_async(coro)` | Celery 任务桥接 — 同步 task 调用异步业务函数 | Celery worker 独立进程运行，拥有独立事件循环 | **SAFE** | 不需要修改 |

---

## SAFE — 脚本内 sync wrapper（仅被 CLI 调用）

| # | 文件 | 行号 | 函数/位置 | 当前用途 | 调用场景 | 风险等级 | 建议处理 |
|---|------|------|-----------|----------|----------|----------|----------|
| 31 | `scripts/import_historical_odds_football_data_uk.py` | 83 | `main()` | 同步入口调用异步主逻辑 | CLI 脚本入口，独立进程 | **SAFE** | 不需要修改 |

---

## NOT IN SCOPE — cheat-on-content 项目

以下 7 处位于 `cheat-on-content/adapters/`，是与 WC26 Predict 无关的独立项目。

| # | 文件 | 行号 |
|---|------|------|
| - | `cheat-on-content/adapters/perf-data/xhs-explore/crawler.py` | 426 |
| - | `cheat-on-content/adapters/perf-data/douyin-session/crawler.py` | 405 |
| - | `cheat-on-content/adapters/perf-data/douyin-session/review.py` | 118 |
| - | `cheat-on-content/adapters/perf-data/douyin-session/review.py` | 123 |
| - | `cheat-on-content/adapters/perf-data/douyin-session/review.py` | 136 |
| - | `cheat-on-content/adapters/perf-data/xhs-explore/review.py` | 115, 120, 133 |
| - | `cheat-on-content/adapters/perf-data/xhs-explore/review.py` | 135 |

---

## 修复优先级

| 优先级 | 调用点 | 理由 |
|--------|--------|------|
| **1 (Ticket 0.5B)** | `weather_service.py:215` | 天气是最常用的外部数据源 |
| **2 (Ticket 0.5B)** | `prediction_enhanced.py:390` | LLM 分析被批量预测频繁调用 |
| **3 (Ticket 0.5B)** | `market/sync_provider.py:48` | 赔率同步是关键数据输入 |
| **4 (后续 cleanup)** | `test_market_provider_selection.py:30` | 测试改进，非生产风险 |
| **5 (后续 cleanup)** | `postmatch_review.py:99` | 添加 guard 或内联到 main |
