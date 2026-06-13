# WC26 Predict — 当前项目状态

> 这是项目的状态总览。若 README、CHANGELOG 与本文档冲突，以 `backend/app/version.py` 和最新 CHANGELOG 为准。
> 最后更新：2026-06-13 | 当前发布：V3.6.1 Postmatch Stats

## 发布信息

| 字段 | 值 |
|---|---|
| Version | `3.6.1-postmatch-stats` |
| Tag | `v3.6.1-postmatch-stats` |
| Build Name | `V3.6.1 Postmatch Stats — StatsBomb真实赛后统计层` |
| 当前阶段 | Phase 2A：真实赛后统计与 provenance |
| 当前定位 | 可审计的世界杯概率预测研究系统，不是博彩工具 |

## 当前阶段判断

系统已经完成 Phase 0B / Phase 1C 的主要工程门禁：active 闭环追溯缺口已处理，walk-forward champion gate、同样本 paired gate、PredictionPipeline 同源 evaluation sample 都已经落地。

V3.6.0 开始进入 Phase 2A，先建立数据 provenance 审计基线。V3.6.1 继续补上真实赛后统计层：新增 `postmatch_team_stats`，并提供 StatsBomb open-data 的 dry-run/apply 回填路径。

重要边界：本轮提交的是代码、migration、脚本和测试，不提交本地 SQLite。只有运行 `backfill_statsbomb_postmatch_stats.py --apply` 后，本地库才会写入 `postmatch_team_stats` 并同步 `match_results` xG。

已完成：

- `closed_loop_resolution_ledger` 隔离旧快照、旧赔率和旧学习日志。
- `prediction_snapshots` / `pre_match_snapshots` active `match_id` 缺口清零。
- `prediction_learning_log` active `prediction_run_id` 缺口清零。
- `postmatch_eval` 达到 `48/48` 可追溯。
- `walk_forward_backtest.py` 输出 JSON + Markdown 报告。
- `--enforce-gate` 和 `--enforce-paired-gate` 已作为发布门，失败时返回非零。
- `PredictionResult.to_dict()` 输出顶层 `evaluation_sample`。
- 新预测会把同一份 `evaluation_sample` 写入 `prediction_snapshots.pipeline_params` 和 `prediction_runs.input_feature_snapshot`。
- walk-forward 回测优先读取 `evaluation_sample`，旧数据无该字段时 fallback 到 V3.5.3 字段。
- 新增安全 dry-run 回填脚本 `backfill_evaluation_samples.py`。
- 新增只读 `audit_data_provenance.py`，统一审计真实 xG、赔率、赛前快照、伤停、阵容探针、manual/news signal 的覆盖与来源。
- 新增 provenance 单测，覆盖低 xG、未绑定赔率、隔离旧赔率、缺 source timestamp、最小可追溯样例。
- 新增 `postmatch_team_stats` ORM model 与 Alembic migration。
- 新增 `postmatch_stats.py`，从 StatsBomb event feed 提取真实 xG、射门、射正、角球、红黄牌。
- 新增 `backfill_statsbomb_postmatch_stats.py`，默认 dry-run，`--apply` 前备份 DB，只接受精确 StatsBomb external id 或唯一日期+主客队匹配。
- `audit_data_provenance.py` 新增 `postmatch_stats_provenance` 检查。

## 当前 gate 结果

production gate 仍失败：

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

paired gate 仍失败：

| 项目 | 结果 |
|---|---|
| Paired gate status | FAIL |
| Candidate champion | `snapshot_adjusted` |
| Paired samples vs uniform | 36 |
| `snapshot_adjusted` vs `uniform_baseline` | log loss / Brier / RPS 全部更好 |
| `snapshot_adjusted` vs `dc_only` | 0/3 proper scoring 指标更好 |
| 样本不足 baseline | `market_only`, `weibull_only` |
| 关键分组退化 | 2 个 |

结论：发布门已经能工作，但当前 champion 和 paired champion 都不能作为新权重发布依据。

## V3.6.1 数据 provenance 审计

`python scripts/audit_data_provenance.py` 当前对本地库返回 FAIL，这是预期结果。

| 项目 | 状态 | 当前结果 |
|---|---|---|
| 真实 xG 覆盖 | CRITICAL | `62/16691`，低于阈值 `1669` |
| 扩展赛后统计 provenance | WARN | 新表/数据需要执行 StatsBomb backfill 后才会有覆盖 |
| 市场赔率 provenance | WARN | `136` 行，只有 `1` 个 linked match，`135` 行 legacy 已 quarantine |
| 赛前快照 provenance | WARN | `218` 条快照，`source_timestamps=0`，3 条 available flag 缺完整 payload/provenance |
| 伤停文件 provenance | WARN | `injuries.json` 当前 0 条记录 |
| 阵容 provenance | WARN | `lineup_probe_logs=11`，可用阵容 0；pre-match lineup payload 0 |
| 情报信号覆盖 | OK | `news_signals=6`，`news_articles=70`，`manual_events=0` |

这个结果说明：下一步不能直接训练新融合权重，必须先补可追溯数据。

## 仍未完成

- 真实 xG 覆盖极低，且很多联赛/赛事为 0；V3.6.1 已提供导入路径，但还没有把本地 DB 作为版本内容提交。
- `postmatch_team_stats` 需要对目标赛事执行 dry-run/apply 后才有真实覆盖。
- 市场基准覆盖仍稀疏，当前不能进入融合，只能作为 shadow benchmark 方向。
- `injuries.json` 为空，球员可用性信号仍不可用。
- 阵容探针已有日志，但还没有任何可用 lineup payload。
- `pre_match_snapshots.source_timestamps` 仍为空，赛前信息状态库还不完整。
- `manual_events` 为 0，人工情报输入仍为空。
- postmatch eval 只有 48 条，学习样本仍少。
- paired benchmark 已覆盖 `prediction_snapshots`，但还不是完整 out-of-fold stacking 训练框架。
- 系统仍不能称为可信自进化；学习只能生成候选方向，不能自动覆盖线上模型。

## 当前优先级

1. V3.6.2：对 StatsBomb World Cup 2018/2022 执行 dry-run/apply，确认 `postmatch_team_stats` 覆盖和 xG 同步结果。
2. V3.6.3：把赔率快照从 shadow source 统一到可追溯 `match_id + fetched_at + provider` 口径。
3. V3.6.4：接入阵容、伤停、停赛、球员出场分钟和可用性数据。
4. V3.6.5：把 `pre_match_snapshots.source_timestamps` 做实，形成真正的赛前信息状态库。
5. V3.7：扩展 walk-forward out-of-fold stacking 训练门。
6. V3.8：修 tabular 泄漏并重建校准。
7. V3.9：做 champion/challenger 发布报告、人工批准流和自动复盘。

## 验收命令

```powershell
cd backend
python -m pytest tests/ -q
python scripts/audit_data_freshness.py
python scripts/audit_closed_loop_integrity.py
python scripts/audit_data_provenance.py
python scripts/backfill_statsbomb_postmatch_stats.py --seasons 2018,2022
python scripts/walk_forward_backtest.py --min-sample 5
python scripts/walk_forward_backtest.py --min-sample 5 --enforce-gate
python scripts/walk_forward_backtest.py --min-sample 5 --enforce-paired-gate
python scripts/backfill_evaluation_samples.py
```

注意：当前 `audit_closed_loop_integrity.py`、`audit_data_provenance.py`、`--enforce-gate`、`--enforce-paired-gate` 都可能返回非零；这是正确行为，说明真实 xG 覆盖和模型发布门仍未通过。

```powershell
npm ci
npm run build
```

## 版本历史

| 版本 | 核心突破 | 状态 |
|---|---|---|
| V3.6.1 | `postmatch_team_stats`、StatsBomb 真实赛后统计回填、provenance 审计扩展 | 当前主版本 |
| V3.6.0 | 数据 provenance 审计、真实 xG/赔率/赛前快照/阵容/伤停覆盖门 | 已取代 |
| V3.5.4 | PredictionPipeline evaluation sample、同源候选概率、回测优先读取新样本 | 已取代 |
| V3.5.3 | paired benchmark、同样本比较、paired gate、非配对榜单隔离 | 已取代 |
| V3.5.2 | walk-forward champion gate、结构化回测报告、强制发布门 | 已取代 |
| V3.5.1 | resolution ledger、legacy 隔离、postmatch 48/48 可追溯 | 已取代 |
| V3.5测试版 gpt5.5 | 闭环门禁、match_id 绑定、proper scoring、walk-forward scaffold、仓库清理 | 已取代 |
| V2.9 | Brier 标准化、FRIENDLY_V4 保守权重、版本统一 | 已取代 |
