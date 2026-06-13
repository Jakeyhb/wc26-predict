# WC26 Predict — 当前项目状态

> 这是项目的状态总览。若 README、CHANGELOG 与本文档冲突，以 `backend/app/version.py` 和最新 CHANGELOG 为准。
> 最后更新：2026-06-13 | 当前发布：V3.5.1 闭环追溯修复版

## 发布信息

| 字段 | 值 |
|---|---|
| Version | `3.5.1-closed-loop` |
| Tag | `v3.5.1-closed-loop` |
| Build Name | `V3.5.1 闭环追溯修复版 — resolution ledger + legacy隔离 + postmatch修复` |
| 当前阶段 | Phase 0B：闭环数据链路修复，active 追溯缺口已清零 |
| 当前定位 | 可审计的世界杯概率预测研究系统，不是博彩工具 |

## 当前阶段判断

系统已经完成 Phase 0B 的第一层目标：旧数据不再被混入学习链路，能修的安全回填，不能修的明确隔离。

已完成：

- 独立赛果验证收紧：至少两个可信独立来源一致才进入自动学习。
- `user_provided` 降级为人工备注，不参与 consensus。
- 快照字段标准化，新增 `match_id` 强约束。
- 新增 `closed_loop_resolution_ledger`，记录旧数据解析结果。
- `prediction_snapshots` / `pre_match_snapshots` active `match_id` 缺口清零，旧债保留为 quarantined legacy。
- `prediction_learning_log` active `prediction_run_id` 缺口清零，旧债保留为 resolved / ambiguous / unresolvable。
- `postmatch_eval` 修复到 `48/48` 可追溯。
- 未来 `market_odds` 保存时写入真实 `match_id`，旧赔率因缺少上下文被隔离。
- 新增 proper scoring 指标和 walk-forward 回测脚手架。
- WC26 小组赛 72/72 场绑定内部 team id。

仍未完成：

- 真实 xG 覆盖极低：`62/16691`。
- 市场基准覆盖仍稀疏：`market_odds` 只有 1 个已绑定比赛，135 条旧赔率已隔离但不能用于 benchmark。
- `manual_events` 为 0，人工情报输入仍为空。
- postmatch eval 只有 48 条，学习样本仍少。
- Phase 1 评估工具已存在，但 champion/challenger 决策门尚未真正落地。
- 系统仍不能称为可信自进化；学习只能生成候选方向，不能自动覆盖线上模型。

## 当前审计结论

最近一次本地审计显示：

| 项目 | 状态 |
|---|---|
| prediction snapshots 缺 `match_id` | active 0，total 25，quarantined 25 |
| pre-match snapshots 缺 `match_id` | active 0，total 213，quarantined 213 |
| learning logs 缺 `prediction_run_id` | active 0，total 65，quarantined 65 |
| market odds 未绑定 | active 0，total 135，quarantined 135 |
| postmatch eval 可追溯 | 48/48 |
| active learning | traceable 1/66，quarantined 65，unresolved 0 |
| 真实 xG 覆盖 | 62/16691 |

结论：闭环追溯 active 缺口已经处理完；下一步应进入 Phase 1 回测门和 Phase 2 数据补强。

## 当前优先级

1. 把 walk-forward 输出升级为正式 champion/challenger gate。
2. 接入真实 xG、射门、射正、红黄牌等赛后统计。
3. 接入可追溯的阵容、伤停、赔率快照、天气、休息和旅途数据。
4. 统一预测入口到 `PredictionPipeline`。
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
```

```powershell
npm ci
npm run build
```

## 版本历史

| 版本 | 核心突破 | 状态 |
|---|---|---|
| V3.5.1 | resolution ledger、legacy 隔离、postmatch 48/48 可追溯 | 当前主版本 |
| V3.5测试版 gpt5.5 | 闭环门禁、match_id 绑定、proper scoring、walk-forward scaffold、仓库清理 | 已取代 |
| V2.9 | Brier 标准化、FRIENDLY_V4 保守权重、版本统一 | 已取代 |
| V2.8 | BEL-TUN 单场适应 | 已回滚，单场过拟合 |
| V2.7 | 友谊赛自进化雏形 | 已收敛到保守门禁 |
| V2.6 | 实时数据 + LLM 分析 | 基础能力保留 |
