# WC26 Predict — 当前项目状态

> 这是项目的状态总览。若 README、CHANGELOG 与本文档冲突，以 `backend/app/version.py` 和最新 CHANGELOG 为准。
> 最后更新：2026-06-13 | 当前发布：V3.5测试版 gpt5.5

## 发布信息

| 字段 | 值 |
|---|---|
| Version | `3.5.0-test-gpt5.5` |
| Tag | `v3.5-test-gpt5.5` |
| Build Name | `V3.5测试版 gpt5.5 — 闭环门禁 + match_id绑定 + walk-forward评估 + 仓库清理` |
| 当前阶段 | Phase 0B：闭环数据链路修复 |
| 后端验证 | 184 passed（仓库清理前完整运行） |
| 前端验证 | production build passed（仓库清理前完整运行） |
| 当前定位 | 可审计的世界杯概率预测研究系统，不是博彩工具 |

## 当前阶段判断

系统已经具备闭环门禁雏形，但还不是完整闭环，也不能称为可信自进化系统。

已完成：

- 独立赛果验证收紧：至少两个可信独立来源一致才进入自动学习。
- `user_provided` 降级为人工备注，不参与 consensus。
- 快照字段标准化，新增 `match_id` 强约束。
- 无真实 `match_id` 的预测不允许进入复盘和学习。
- 新增 proper scoring 指标：log loss、Brier、RPS。
- 新增 walk-forward 回测脚手架。
- 新增闭环完整性审计脚本。
- WC26 小组赛 72/72 场绑定内部 team id。
- 完成仓库清理，删除可再生成依赖、缓存、构建产物和重复旧库。

仍未完成：

- 大量历史 `pre_match_snapshots`、`prediction_snapshots` 仍缺少 `match_id`。
- 赔率数据大部分尚未绑定真实比赛。
- xG 大量依赖 fallback 或缺少可信 provenance。
- Phase 1 评估工具已存在，但 champion/challenger 决策门尚未真正落地。
- 自学习只能生成候选方向，不能自动覆盖线上模型。

## 当前数据审计结论

最近一次本地审计显示：

| 项目 | 状态 |
|---|---|
| WC26 小组赛绑定 | 72/72 |
| WC26 全赛程绑定 | 72/104，淘汰赛 TBD |
| prediction snapshots 缺 `match_id` | 25 |
| pre-match snapshots 缺 `match_id` | 213 |
| 赔率绑定 | 仅少量样本绑定真实比赛 |
| active learning traceability | 仍需补 `prediction_run_id` / `match_id` 链路 |

这些问题不会阻塞代码开发，但会阻塞“系统已经更准”的结论。

## 当前优先级

1. 回填和强制 `match_id` 绑定。
2. 补齐 WC26 赛程、球队、比赛映射。
3. 扩展 walk-forward baseline 对比。
4. 统一预测入口到 `PredictionPipeline`。
5. 接入真实 xG、阵容、伤停、赔率快照。
6. 修 tabular 泄漏并重建校准。
7. 做 champion/challenger 发布门。
8. 做自动复盘和候选学习报告。

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
| V3.5测试版 gpt5.5 | 闭环门禁、match_id 绑定、proper scoring、walk-forward scaffold、仓库清理 | 当前主版本 |
| V2.9 | Brier 标准化、FRIENDLY_V4 保守权重、版本统一 | 已取代 |
| V2.8 | BEL-TUN 单场适应 | 已回滚，单场过拟合 |
| V2.7 | 友谊赛自进化雏形 | 已收敛到保守门禁 |
| V2.6 | 实时数据 + LLM 分析 | 基础能力保留 |
