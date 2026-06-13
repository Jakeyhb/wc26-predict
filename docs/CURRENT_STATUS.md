# WC26 Predict — 当前项目状态

> 这是项目的状态总览。若 README、CHANGELOG 与本文档冲突，以 `backend/app/version.py` 和最新 CHANGELOG 为准。
> 最后更新：2026-06-13 | 当前发布：V3.5.3 Paired Benchmark

## 发布信息

| 字段 | 值 |
|---|---|
| Version | `3.5.3-paired-benchmark` |
| Tag | `v3.5.3-paired-benchmark` |
| Build Name | `V3.5.3 Paired Benchmark — 同样本配对回测门 + 非配对leaderboard隔离` |
| 当前阶段 | Phase 1B：paired benchmark 已落地，但 paired gate 未通过；out-of-fold stacking 仍待后续实现 |
| 当前定位 | 可审计的世界杯概率预测研究系统，不是博彩工具 |

## 当前阶段判断

系统已经从 Phase 0B 进入 Phase 1B：闭环 active 追溯缺口已处理，walk-forward champion gate 和同样本 paired gate 都已经可以拒绝不合格模型。out-of-fold stacking 训练门还没有完成。

已完成：

- `closed_loop_resolution_ledger` 隔离旧快照、旧赔率和旧学习日志。
- `prediction_snapshots` / `pre_match_snapshots` active `match_id` 缺口清零。
- `prediction_learning_log` active `prediction_run_id` 缺口清零。
- `postmatch_eval` 达到 `48/48` 可追溯。
- `walk_forward_backtest.py` 输出 JSON + Markdown 报告。
- `--enforce-gate` 可作为发布门，失败时返回非零。
- gate 按 log loss、Brier、RPS、leaderboard 和关键分组退化判定 champion。
- `--enforce-paired-gate` 已落地；默认比较 `snapshot_adjusted` 与同一条样本内的 `uniform_baseline`、DC、Elo、Pi、tabular、market、Weibull。
- 非配对 leaderboard 被明确标记为 exploratory，不能再被当作模型优劣结论。

当前 production gate 结果：

| 项目 | 结果 |
|---|---|
| Gate status | FAIL |
| Candidate champion | `current_fusion` |
| Leader by log loss | `dc_only` |
| `current_fusion` log loss | 2.2370 |
| `uniform_baseline` log loss | 1.0986 |
| `current_fusion` Brier | 0.6689 |
| `uniform_baseline` Brier | 0.6667 |
| 关键分组退化 | 7 个 |

结论：发布门已经能工作，但当前 champion 不能发布，不能上线新权重。

当前 paired gate 结果：

| 项目 | 结果 |
|---|---|
| Paired gate status | FAIL |
| Candidate champion | `snapshot_adjusted` |
| Paired samples vs uniform | 36 |
| `snapshot_adjusted` vs `uniform_baseline` | log loss / Brier / RPS 全部更好 |
| `snapshot_adjusted` vs `dc_only` | 0/3 proper scoring 指标更好 |
| 样本不足 baseline | `market_only`, `weibull_only` |
| 关键分组退化 | 2 个 |

结论：paired gate 已经能防止非配对误判，但当前 paired champion 仍不能作为新权重发布依据。

## 仍未完成

- 真实 xG 覆盖极低：`62/16691`。
- 市场基准覆盖仍稀疏：`market_odds` 只有 1 个已绑定比赛，135 条旧赔率已隔离但不能用于 benchmark。
- `manual_events` 为 0，人工情报输入仍为空。
- postmatch eval 只有 48 条，学习样本仍少。
- `current_fusion` 仍来自 `prediction_runs`，还没有进入完全统一的 `PredictionPipeline` 配对输出。
- paired benchmark 已覆盖 `prediction_snapshots`，但还不是完整 out-of-fold stacking 训练框架。
- 系统仍不能称为可信自进化；学习只能生成候选方向，不能自动覆盖线上模型。

## 当前审计结论

| 项目 | 状态 |
|---|---|
| prediction snapshots 缺 `match_id` | active 0，total 25，quarantined 25 |
| pre-match snapshots 缺 `match_id` | active 0，total 213，quarantined 213 |
| learning logs 缺 `prediction_run_id` | active 0，total 65，quarantined 65 |
| market odds 未绑定 | active 0，total 135，quarantined 135 |
| postmatch eval 可追溯 | 48/48 |
| active learning | traceable 1/66，quarantined 65，unresolved 0 |
| 真实 xG 覆盖 | 62/16691 |

## 当前优先级

1. Phase 1C：统一 `PredictionPipeline` 输出评估样本，让 `current_fusion` 也进入完整 paired comparison。
2. Phase 2A：接入真实 xG、射门、射正、红黄牌等赛后统计。
3. Phase 2B：接入可追溯的阵容、伤停、赔率快照、天气、休息和旅途数据。
4. 扩展 walk-forward out-of-fold stacking 训练门。
5. 修 tabular 泄漏并重建校准。
6. 建立候选权重发布门，禁止未经回测的线上权重更新。
7. 做自动复盘和候选学习报告。

## 验收命令

```powershell
cd backend
python -m pytest tests/ -q
python scripts/audit_data_freshness.py
python scripts/audit_closed_loop_integrity.py
python scripts/walk_forward_backtest.py --min-sample 5
python scripts/walk_forward_backtest.py --min-sample 5 --enforce-gate
python scripts/walk_forward_backtest.py --min-sample 5 --enforce-paired-gate
```

注意：当前 `--enforce-gate` 和 `--enforce-paired-gate` 都预期失败；这是正确行为，说明当前 champion 和 paired champion 尚未通过发布门。

```powershell
npm ci
npm run build
```

## 版本历史

| 版本 | 核心突破 | 状态 |
|---|---|---|
| V3.5.3 | paired benchmark、同样本比较、paired gate、非配对榜单隔离 | 当前主版本 |
| V3.5.2 | walk-forward champion gate、结构化回测报告、强制发布门 | 已取代 |
| V3.5.1 | resolution ledger、legacy 隔离、postmatch 48/48 可追溯 | 已取代 |
| V3.5测试版 gpt5.5 | 闭环门禁、match_id 绑定、proper scoring、walk-forward scaffold、仓库清理 | 已取代 |
| V2.9 | Brier 标准化、FRIENDLY_V4 保守权重、版本统一 | 已取代 |
