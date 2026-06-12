# Post-Match 复盘标准操作流程 (SOP)

> 版本: 1.0 | 最后更新: 2026-06-12  
> 适用范围: WC26 Predict V3.4+ 赛后复盘与自进化学习

---

## ⚠️ 致命错误警示

以下错误在历史复盘中出现过，**严禁再次发生**：

| # | 错误 | 后果 | 预防措施 |
|---|------|------|---------|
| 1 | 使用**半场比分**作为最终赛果（如韩国vs捷克用了 0-0） | 学习引擎学到错误信号，Brier 和边际贡献全错 | 必须多源验证 + 确认比赛状态为 FT/Finished/Final |
| 2 | 仅用**单一来源**确认赛果 | 无法交叉验证，错误比分无法被发现 | 至少 2 个独立来源达成共识 |
| 3 | 复盘时**只有比分、没有完整数据** | 学习不完整，无法发现模型系统性问题 | 必须收集完整 Opta 数据后再运行学习引擎 |
| 4 | 两个来源**使用同一个输入**（假共识） | 验真闸形同虚设 | 第二来源必须独立获取 |
| 5 | 搜索时命中 **live blog** 而非赛后报道 | 拿到比赛进行中的临时比分 | 搜索时加 "full time" / "final score" / "match report" |

---

## 复盘前检查清单

每次执行复盘前，逐项确认：

### 阶段 A: 赛果确认

- [ ] A1. 比赛状态确认为 `FT` / `Finished` / `Final`
- [ ] A2. 至少从 **2 个独立来源** 确认比分一致
- [ ] A3. 来源不包含 live blog、实时比分、半场报道
- [ ] A4. 优先来源顺序：FIFA.com > 权威媒体(ESPN/BBC/Sky) > 通讯社 > 聚合器
- [ ] A5. 两个来源的比分必须**完全一致**

**常见陷阱：**
- Google 搜索结果第一条可能是实时博客（标题不含 "live" 但内容是）
- X/Twitter 上的比分可能是调侃或虚假信息
- 中文媒体（新浪、腾讯）可能转载延迟或有翻译错误
- **搜索时明确加 "full time" 或 "final score" 或 "match report"**

### 阶段 B: 数据收集

- [ ] B1. 获取双方 xG（预期进球）
- [ ] B2. 获取射门/射正数据
- [ ] B3. 获取控球率
- [ ] B4. 获取传球完成数
- [ ] B5. 获取角球数
- [ ] B6. 获取进球时间线和进球球员 + 助攻球员
- [ ] B7. 获取红黄牌数据
- [ ] B8. 获取首发阵容和阵型
- [ ] B9. 标注数据来源（Opta / FIFA / Sofascore / 其他）

**数据来源优先级：**
1. Opta (via API-Football paid tier) — 最权威
2. FIFA.com 官方赛后报告
3. Sofascore / FlashScore — 免费且更新快
4. ESPN / BBC 赛后报道中的统计

### 阶段 C: 学习引擎执行

- [ ] C1. 确认验真闸已通过（`is_verified=True`）
- [ ] C2. 确认有预测快照（`prediction_snapshot`）
- [ ] C3. 删除旧的 learning_log（如有）
- [ ] C4. 运行 `process_match_result` 并传入 `verified_result_id`
- [ ] C5. 确认 `learning_log.status = "active"`
- [ ] C6. 记录 Brier、边际贡献、方向判断

### 阶段 D: 报告生成

- [ ] D1. 生成预测 vs 实际对比表
- [ ] D2. 逐层分解模型表现
- [ ] D3. 标注数据完整性（full / partial）
- [ ] D4. 记录关键发现和模型偏误
- [ ] D5. 如有跨场次模式，记录自进化建议

---

## 标准执行命令

### 方式 1: 使用完整流水线（推荐）

```bash
cd backend

python scripts/run_postmatch_complete.py \
    --match-id <MATCH_UUID> \
    --home-score <HOME_GOALS> \
    --away-score <AWAY_GOALS> \
    --verify-url "<SPORTS_SITE_URL>" \
    --verify-source-name "<SOURCE_LABEL>" \
    --home-xg <HOME_XG> \
    --away-xg <AWAY_XG> \
    --possession-home <HOME_POSSESSION> \
    --possession-away <AWAY_POSSESSION> \
    --shots-home <HOME_SHOTS> \
    --shots-away <AWAY_SHOTS> \
    --sot-home <HOME_SOT> \
    --sot-away <AWAY_SOT> \
    --data-source "<SOURCE>"
```

### 方式 2: 手动单步执行（调试用）

```bash
# Step 1: 先确认赛果
python scripts/run_postmatch.py \
    --match-id <MATCH_UUID> \
    --home-score <HOME_GOALS> \
    --away-score <AWAY_GOALS> \
    --verify-url "<URL>"

# Step 2: 再补全 Opta 数据
python scripts/complete_postmatch.py
```

### 方式 3: 自动化每日复盘

```bash
python scripts/auto_postmatch.py --days 1
```

注意：`auto_postmatch.py` 仅在有 **2+ 独立来源** 时才会写入学习日志。如果没有足够来源，它会跳过并提示手动运行。

---

## 复盘后验证

执行完成后，检查数据库：

```sql
-- 检查学习日志状态
SELECT id, snapshot_id, error_magnitude, error_direction, status, created_at
FROM prediction_learning_log
ORDER BY created_at DESC
LIMIT 5;

-- 检查验证记录
SELECT mrv.match_id, mrv.home_goals, mrv.away_goals,
       mrv.source_name, mrv.source_tier, mrv.is_consensus
FROM match_result_verification mrv
ORDER BY mrv.created_at DESC
LIMIT 10;

-- 检查 match_results xG 是否已更新
SELECT match_id, home_goals, away_goals, home_xg, away_xg
FROM match_results
ORDER BY rowid DESC
LIMIT 5;
```

**验收标准：**
- [ ] `learning_log.status = "active"`（不是 `pending_review`）
- [ ] `match_result_verification` 至少有 2 条 source + 1 条 consensus
- [ ] `match_results.home_xg / away_xg` 已填充（如数据可用）
- [ ] Brier 分数在合理范围（0.15-0.85 之间）
- [ ] 如果有组件边际贡献 > 0.5 或 < -0.5，检查是否有计算异常

---

## 错误恢复流程

如果发现复盘使用了错误数据：

### 1. 标记错误记录

```sql
UPDATE prediction_learning_log
SET status = 'invalidated',
    notes = notes || ' | INVALIDATED: wrong score used (actual was X-Y)'
WHERE id = '<LEARNING_LOG_ID>';
```

### 2. 删除错误的验证记录

```sql
DELETE FROM match_result_verification
WHERE match_id = '<MATCH_UUID>'
  AND is_consensus = FALSE;
```

### 3. 检查是否有级联影响

```sql
-- 检查 signal_track_record 是否被错误更新
SELECT * FROM signal_track_record
WHERE updated_at > '<ERROR_TIMESTAMP>';

-- 检查 context_performance_matrix 是否受影响
SELECT * FROM context_performance_matrix
WHERE updated_at > '<ERROR_TIMESTAMP>';
```

### 4. 重新执行正确复盘

使用正确的比分和完整数据，按上述标准流程重新执行。

---

## 跨场次自进化流程

当积累了 ≥3 场复盘数据后：

1. **运行跨场次分析**：
   ```bash
   python scripts/complete_postmatch.py
   ```

2. **检查模型层可靠性排名**：
   - 每层的方向命中率
   - 平均 Brier 分数
   - 平均边际贡献

3. **生成自进化建议**（不自动执行）：
   - 权重调整建议
   - 参数调整建议
   - 新特征建议

4. **审批流程**（参考 Ticket 7）：
   - 样本数 N ≥ 20 场才能改生产权重
   - rolling backtest 必须优于当前权重
   - 至少两个指标改善（Brier、LogLoss、RPS）

---

## 附录：常见数据来源

| 来源 | URL 模式 | 可靠性 | 速度 |
|------|---------|:---:|:---:|
| FIFA.com | `fifa.com/en/match-centre/match/...` | ⭐⭐⭐⭐⭐ | 赛后 1-2h |
| ESPN | `espn.com/soccer/match/_/id/...` | ⭐⭐⭐⭐ | 赛后 15-30min |
| Sky Sports | `skysports.com/football/...` | ⭐⭐⭐⭐ | 赛后 15-30min |
| BBC Sport | `bbc.com/sport/football/...` | ⭐⭐⭐⭐ | 赛后 15-30min |
| Sofascore | `sofascore.com/...` | ⭐⭐⭐ | 实时 |
| FlashScore | `flashscore.com/match/...` | ⭐⭐⭐ | 实时 |
| Google 搜索 | `[team] vs [team] final score` | ⭐⭐ | 实时但不可靠 |

**警告**：Google 搜索和社交媒体**不能**作为唯一来源。实时比分网站可能在比赛结束后仍显示错误比分（缓存问题）。

---

> 最后更新: 2026-06-12 | WC26 Predict V3.5 | 基于实战复盘错误总结
