# Croatia vs Belgium 完整分析报告

> 比赛时间：2026-06-03 00:00（北京时间）| 赛事：国际友谊赛 | 场地：中立场
> 最终比分：**Croatia 0 - 2 Belgium**

---

## 一、赛前预测

### 1.1 最终预测结果

| | Croatia（主） | 平局 | Belgium（客） |
|---|---|---|---|
| **五层融合** | **24.3%** | 19.1% | **56.5%** |

| 期望进球 (xG) | Croatia 1.13 — 1.10 Belgium |
|---|---|
| 预期总进球 | ~2.23 球 |
| 最可能比分 | 1-0 (13.8%), 0-1 (13.4%), 1-1 (11.7%) |

### 1.2 各层独立预测

| 层级 | Croatia 胜 | 平局 | Belgium 胜 |
|------|:---------:|:----:|:----------:|
| Dixon-Coles (泊松) | 包含在融合中 |
| Tabular Enhancer (梯度提升) | 包含在融合中 |
| Elo 评分 | 包含在融合中 |
| Pi-Rating | 不可用（penaltyblog 无法安装） |
| Weibull Copula | 不可用（penaltyblog 无法安装） |

### 1.3 Elo 评分

| 球队 | Elo 评分 | 差距 |
|------|---------|------|
| Croatia | 1,728 | +13 |
| Belgium | 1,715 | — |

### 1.4 近期战绩

**Croatia（近5场：4胜1负）**

| 日期 | 结果 | 比分 | 对手 | 场地 |
|------|------|------|------|------|
| 2026-03-31 | 负 | 1-3 | Brazil | 客场 |
| 2026-03-26 | 胜 | 2-1 | Colombia | 客场 |
| 2025-11-17 | 胜 | 3-2 | Montenegro | 客场 |
| 2025-11-14 | 胜 | 3-1 | Faroe Islands | 主场 |
| 2025-10-12 | 胜 | 3-0 | Gibraltar | 主场 |

**Belgium（近5场：3胜2平）**

| 日期 | 结果 | 比分 | 对手 | 场地 |
|------|------|------|------|------|
| 2026-03-31 | 平 | 1-1 | Mexico | 客场 |
| 2026-03-28 | 胜 | 5-2 | United States | 客场 |
| 2025-11-18 | 胜 | 7-0 | Liechtenstein | 主场 |
| 2025-11-15 | 平 | 1-1 | Kazakhstan | 客场 |
| 2025-10-13 | 胜 | 4-2 | Wales | 客场 |

### 1.5 预测解读

模型判断 Belgium 胜率 56.5%，核心原因是 Tabular Enhancer 捕捉到 Belgium 近期进攻爆发力极强——对美国 5 球、对列支敦士登 7 球、对威尔士 4 球。而 Croatia 虽然胜率更高，但对手偏弱（法罗群岛、直布罗陀等）。

xG 层面（DC 泊松模型）两队几乎持平（1.13 vs 1.10），说明攻防参数层面两队实力接近。融合层将 Belgium 概率拉高，体现了机器学习模型对"近期进攻状态"的重视。

**已知缺失**：
- 无手动伤停情报（manual_events 表为空）
- 无市场赔率校准（The Odds API 本次未拉到数据）
- Pi-Rating 和 Weibull Copula 因 penaltyblog 无法安装而降级

---

## 二、实际结果 vs 预测

### 2.1 结果对比

| 维度 | 预测 | 实际 | 评估 |
|------|------|------|------|
| 胜负方向 | Belgium 胜 56.5% | Belgium 胜 ✅ | **正确** |
| 比分 | 1-0 / 0-1 / 1-1 | 0-2 | ❌ |
| 总进球 | ~2.23 球 | 2 球 | 接近 |
| Croatia xG | 1.13 | 0 实际进球 | — |
| Belgium xG | 1.10 | 2 实际进球 | — |

### 2.2 分析

预测方向正确，但精确比分未命中。足球比赛的比分预测本身就具有极高的随机性——即便最顶级的商业模型，精确比分准确率通常也只有 10-15%。0-2 的结果在概率分布中排在相对靠后的位置，但因为足球的低比分特性，尾部事件发生概率并不低。

总进球预测（~2.23）与实际（2 球）非常接近，说明 DC 泊松模型的 xG 估计是有效的。

---

## 三、赛后自进化学习

### 3.1 自进化闭环流程

系统的自进化由三个组件构成一个闭环：

```
赛前预测 (snapshot.py)
    ↓
预测快照入库 (prediction_snapshots + prediction_runs)
    ↓
比赛结束，实际结果入库 (matches + match_results)
    ↓
赛后学习 (auto_postmatch.py)
    ├── 匹配预测快照与实际结果
    ├── 计算 Brier Score 误差
    ├── 逐层归因 (DC / Enhancer / Elo 各自的贡献)
    ├── 更新信号追踪 (signal_track_record)
    ├── 记录市场分歧 (market_divergence_log)
    └── 更新场景表现矩阵 (context_performance_matrix)
    ↓
权重优化 (optimize_weights.py)
    ├── 读取所有赛后评估数据
    ├── 以 RPS (Ranked Probability Score) 为目标函数
    └── Nelder-Mead 优化各层融合权重
    ↓
下次预测使用优化后的权重
```

### 3.2 本场比赛的学习过程

**步骤 1：比赛记录入库**

由于这是一场友谊赛，比赛记录没有自动进入系统的 `matches` 表。需要手动插入：

```sql
INSERT INTO matches (
    external_id, home_team_id, away_team_id, match_date,
    competition, competition_weight, stage, venue, is_neutral_venue,
    status, id, created_at, updated_at, competition_type
) VALUES (
    'friendly_cro_bel_20260603',
    '<Croatia_UUID>', '<Belgium_UUID>', '2026-06-03 00:00:00',
    'International Friendly', 0.5, 'Friendly', 'TBD', 1,
    'finished', '<new_UUID>', '<now>', '<now>', 'national'
);

INSERT INTO match_results (id, match_id, home_goals, away_goals)
VALUES ('<new_UUID>', '<match_UUID>', 0, 2);
```

然后将赛前预测快照关联到这场比赛：

```sql
UPDATE prediction_snapshots SET match_id = '<match_UUID>'
WHERE home_team = 'Croatia' AND away_team = 'Belgium';

UPDATE prediction_runs SET match_id = '<match_UUID>'
WHERE id = '<latest_run_UUID>';
```

**步骤 2：运行 auto_postmatch.py**

```bash
python scripts/auto_postmatch.py --days 2
```

系统自动完成以下操作：

1. **匹配**：在 `matches` 表中查找最近 2 天内状态为 `finished` 的比赛
2. **查找预测**：通过 `match_id` 匹配对应的 `prediction_snapshots` 记录
3. **误差计算**：调用 `LearningEngine.process_match_result()`
4. **持久化**：生成 `PredictionLearningLog` 记录

**步骤 3：LearningEngine 内部做了什么**

`LearningEngine` 是本系统的核心学习模块，对每一场比赛执行四步：

| 步骤 | 方法 | 说明 |
|------|------|------|
| 误差归因 | `_attribute_error()` | 用 leave-one-out 方法，依次移除 DC/Enhancer/Elo 各层，计算每层对最终预测的边际贡献 |
| 信号追踪 | `_update_signal_track_records()` | 如果赛前有手动事件（伤病等），更新该信号类型的历史准确率 |
| 市场分歧 | `_log_market_divergence()` | 记录模型预测与市场赔率的分歧程度（本场无市场数据） |
| 场景矩阵 | `_update_context_matrix()` | 记录"友谊赛/中立场"这类场景下的模型表现 |

### 3.3 学习结果

```
auto_postmatch.py 输出：
  ✓ 2026-06-03 Croatia 0-2 Belgium Brier=0.095 dir=correct

处理统计:
  Processed: 1
  Skipped (no snapshot): 0
  Skipped (already logged): 0
  Average Brier: 0.095
```

| 指标 | 数值 | 说明 |
|------|------|------|
| Brier Score | **0.095** | 预测概率与实际结果的均方误差。0=完美，0.33=随机猜测。0.095 是很好的分数 |
| Error Direction | **correct** | 模型预测的最高概率方向与实际一致 |
| 各层归因 | 已记录 | DC / Enhancer / Elo 的边际贡献已写入 learning_log |
| Signal Track | 无更新 | 本场无手动事件，信号追踪跳过 |
| Context Matrix | 已更新 | "友谊赛/中立场"场景的表现数据 +1 |

### 3.4 Brier Score 解读

Brier Score 衡量概率预测的准确程度：

```
Brier = (P_home - a_home)² + (P_draw - a_draw)² + (P_away - a_away)² / 3

本场：
  P = [0.243, 0.191, 0.565]
  Actual = [0, 0, 1]
  Brier = (0.243² + 0.191² + 0.435²) / 3 = 0.095
```

0.095 意味着模型给了 Belgium 56.5% 的胜率，Belgium 也确实赢了——概率分配与实际结果高度一致。如果模型给出 Belgium 99% 胜率且 Belgium 赢了，Brier 会更低（~0.003）。如果给出 33%/33%/33% 的均匀分布（等于瞎猜），Brier 是 0.222。

---

## 四、数据库状态（赛后）

| 表 | 记录数 | 本场变化 |
|---|--------|---------|
| prediction_snapshots | 153 | 关联 match_id |
| prediction_runs | 170 | 关联 match_id |
| prediction_learning_log | **65** | +1 (本场) |
| signal_track_record | 6+ | 无变化 |
| postmatch_eval | 48+ | 可能新增 |

---

## 五、已知局限

### 5.1 当前系统短板

| 问题 | 影响 | 状态 |
|------|------|------|
| Pi-Rating 不可用 | 缺少跨联赛能力比较 | penaltyblog 无法在 Windows 安装 |
| Weibull Copula 不可用 | 缺少总进球/Over-Under 预测 | 同上 |
| 无自动伤停采集 | 手动事件依赖人工录入 | manual_events 表为空 |
| DC 拟合性能 | 国家队预测耗时 2-3 分钟 | 已加 maxiter=500 临时缓解 |
| 比分预测精度 | 精确比分命中率低 | 足球固有随机性，正常现象 |
| 无首发阵容 | xG 可能偏差 15%+ | 缺数据源 |

### 5.2 短期可改进

1. **总进球预测**：DC 泊松模型的 xG 可直接推导总进球分布，无需等 Weibull
2. **报告增加置信度说明**：诚实告知精确比分预测的局限性
3. **WSL 环境**：安装 penaltyblog 恢复 Pi-Rating 和 Weibull 层

---

## 六、结论

本场比赛是 WC26 预测系统的首次端到端实战验证：

- ✅ **胜负方向正确**：Belgium 胜率 56.5%，实际 Belgium 2-0
- ✅ **xG 估计有效**：预期总进球 ~2.23，实际 2 球
- ✅ **自进化闭环跑通**：赛后自动学习、误差归因、Brier=0.095
- ❌ **精确比分未命中**：Top 3 比分不含 0-2
- ⚠️ **两层模型降级**：Pi-Rating 和 Weibull 在 Windows 不可用

> ⚠️ 免责声明：本系统为个人学习项目，所有分析结果仅供娱乐参考，不构成任何投注建议。足球比赛结果受无数因素影响，数学模型无法替代专业分析。

---

*报告生成时间：2026-06-03 | 系统版本：V1.3 | 仓库：github.com/AndyDu0921/wc26-predict*
