# WC26 Predict — 交接文档

> 生成时间：2026-05-21
> 目标读者：新会话的 WC26 Predict Agent

---

## 一、项目概览

**项目路径**：`/mnt/d/hermes agent/2026世界杯分析/`（Windows `D:\hermes agent\2026世界杯分析\`）

**一句话定位**：2026世界杯足球赛前预测系统。三层预测引擎（Dixon-Coles + Tabular Enhancer + κ-Elo），非赌博，不含赔率。

**技术栈**：Python 3.11+ / FastAPI / SQLAlchemy / Celery / React 18 + Vite / SQLite（开发）

---

## 二、当前会话完成的工作（2026-05-25）

### 完成 5 项任务。

| # | 任务 | 结果 | 变更文件 |
|---|------|------|----------|
| **12** | 欧冠决赛预测（巴黎 vs 阿森纳） | ✅ 双联赛合并预测：H=52.8% D=23.3% A=23.8%，2029行训练数据 | snapshot.py（新增--competitions参数） |
| **13** | WC 小组赛日期修复 | ✅ 72场从2天/组修复为12天跨度（MD1:6/11-14, MD2:6/15-18, MD3:6/19-22） | DB UPDATE 72条 |
| **14** | 全局健康检查 | ✅ 全部通过：DB完整性、104场赛程、6场/组、淘汰赛场次正确 | 无 |
| **15** | 赛后自动学习 cron job + 2 Bug 修复 | ✅ cron 运行正常（--days 1），2 个 runtime bug 修复 | learning_engine.py, auto_postmatch.py |
| **16** | 前端静态页面生成器 v2 | ✅ 预览模式+世界杯模式切换，深藏蓝配色，霓虹进度条 | generate_static_site.py |

### 关键代码修改
- **snapshot.py**：新增 `--competitions` 参数支持多联赛合并训练（用于跨联赛的杯赛决赛）
  - `run_snapshot()` 新增 `competitions: list[str] | None` 参数
  - 当 `competitions` 提供时，`competition` 参数不再传给 `load_training_frame`
- **learning_engine.py L320**：修复 `market_home=None` 导致 `TypeError`（JSON `{"home": null}` 是有效 dict，`not market` 不触发）
- **auto_postmatch.py L109**：修复异常处理中访问 `snapshot.home_team` 触发 `MissingGreenlet`（session rollback 后 ORM 对象不可用）

### 关键数据库修改
- **WC 2026 小组赛日期**：72条记录重新分配日期
  - 原：每个小组6场压缩到2天
  - 改：MD1/MD2/MD3各4天，每比赛日3组6场

---

## 三、项目当前状态快照

### 数据层
| 项 | 值 |
|----|-----|
| 俱乐部比赛 | 5,989场（2023-08 ~ 2026-05），日期正确 ✅ |
| 国家队比赛 | 128场：WC 2022 64场（正确）+ WC 2018 64场（已修复）|
| WC 2026 赛程 | 104场（72小组+32淘汰），日期 2026-06-11 ~ 07-19 ✅ |
| 国家队冷启动 | 15支球队无历史数据，依赖 FIFA tier + 洲际先验 |
| snapshot.py | 支持 --competitions 多联赛合并 ✅ |
| 预测快照 | 140条 |
| 学习日志 | 63条，平均 Brier=0.1703，方向正确率 47/63=74.6% |
| 手动事件 | 4条（1条活跃） |

### 模型层
| 项 | 值 |
|----|-----|
| DC/Enhancer 权重 | 0.68 / 0.32（优化未触发更新）|
| Elo 融合权重 | 0.15 |
| kappa-Elo | EPL=0.28, UCL=0.18, Default=0.24 |
| MarketCalibrator | 活跃（market_odds=2 条，divergence_log=0 条） |
| 信号跟踪 | 6类信号均 50% 初始值（无实际信号数据流入） |

### 基础设施
| 项 | 状态 |
|----|------|
| Celery worker | 未运行（cron job 直接用 Python 脚本代替） |
| Redis | 不可用（WSL），broker=SQLite |
| FOOTBALL_DATA_API_KEY | ✅ 已配置（2026-05-25） |
| LLM_API_KEY | ✅ 已配置（DeepSeek，复用 Hermes key，2026-05-25） |
| ODDS_API_KEY | ✅ 已配置，API 验证通过，72场世界杯赔率可用 |
| CLOUDFLARE_API_TOKEN | ✅ 已配置（2026-05-25） |
| EVENT_REGISTRY_API_KEY | ❌ 需公司邮箱，用户只有个人邮箱，暂不注册 |
| 赛后自动学习 cron | ✅ 已配置（--days 1，每天运行） |
| 前端静态页面 | ✅ generate_static_site.py v2，深藏蓝配色（待部署） |

---

## 四、已知限制和风险

1. **国家队数据极少** — 128场，WC 2022占64场（衰减系数 0.007），WC 2018 64场几乎完全衰减。世界杯预测置信度需明确标注弱于联赛预测。

2. **新闻情报管道空洞** — news_signals=0，免费源无产出。LLM_API_KEY 已配置（DeepSeek），待有赛前新闻文章时可触发 LLM 抽取。

3. **standings 表为空** — 世界杯动力因素已用 wc_motivation.py 替代，非世界杯场景的动力因素仍然不可用。

4. **Calibrator 未校准** — 63条学习日志，<300条无法启用自动校准。MarketCalibrator 处于活跃状态但 blend weight 样本量决定（世界杯 128 场国家队数据 → 最小 5%）。

5. **预测快照与赛后结果未关联** — `prediction_snapshots.match_id` 为空，导致 `auto_postmatch` 无法自动匹配快照到结果。当前依赖时间窗口模糊匹配。

6. **前端未上线** — 静态页面生成器可用，CLOUDFLARE_API_TOKEN 已配置，待部署。

---

## 五、常用命令（WSL 下）

```bash
# 预测单场世界杯
cd "/mnt/d/hermes agent/2026世界杯分析/backend" && python3 scripts/snapshot.py \
  --home "Argentina" --away "Brazil" \
  --competition "FIFA World Cup 2026" --neutral

# 健康检查
cd "/mnt/d/hermes agent/2026世界杯分析/backend" && python3 scripts/health_check.py

# 数据库备份
cp "/mnt/d/hermes agent/2026世界杯分析/backend/data/local_stage2.db" \
   "/mnt/d/hermes agent/2026世界杯分析/backend/data/local_stage2_backup_$(date -u +%Y%m%d_%H%M%S).db"

# 查询数据
python3 -c "
import sqlite3
conn = sqlite3.connect('/mnt/d/hermes agent/2026世界杯分析/backend/data/local_stage2.db')
conn.row_factory = sqlite3.Row
# 你的 SQL...
"
```

---

## 六、数据库字段陷阱 + 已知 Bug 修复记录

- `matches.status` 是小写 `'finished'`，不是 `'FINISHED'`
- `match_results` 列是 `home_goals` / `away_goals`，不是 `home_score` / `away_score`
- `match_results` 表**没有 `updated_at` 列**，INSERT 时不要包含
- WC report motivation 字段：`group`, `points`, `played` 是 wc_motivation.py 特有字段，standings 模式不带这些

### 已修复 Bug（5/25 会话）
- **learning_engine.py L320**：`market_home=None` → `TypeError`。`market_probs={"home": null}` 是有效 dict，`not market` 不触发。修复：`market.get("home") is None` 提前返回
- **auto_postmatch.py L109**：异常处理访问 `snapshot.home_team` → `MissingGreenlet`（session 已 rollback）。修复：用 `getattr(obj, 'attr', '?')` 安全取值

---

## 七、下一步计划（按用户优先级）

1. **6/1-6/3** — 48队全压测：所有 WC26 球队无 crash 验证
2. **6/6-6/10** — 生产上线检查清单：Cloudflare API Token 获取、前端部署、每日 cron 确认
3. **6/11 开幕日** — 首场墨西哥 vs 待定，T-24h 运行第一份正式世界杯预测报告
4. **持续** — 手动情报注入：每日为当天比赛创建 2-4 条 manual_events（伤病/首发/动机）

---

## 八、Agent 操作约定

- 新会话 **必须先加载** `wc26-predict` skill，然后读此文档
- 数据库变更前先备份
- `.py` 文件修改用 `patch` 工具，不要 read_file → write_file
- WSL 下路径是 `/mnt/d/hermes agent/...` 格式
- 命令用 `python3` 而非 `python`
- 窗口路径含中文时 terminal 工具可能被拦截，用 execute_code 代替
- 所有回答用中文，简洁直接
