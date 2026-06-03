# WC26 Predict 最终核验版执行方案

> 交付对象：Claude Code  
> 生成日期：2026-06-03  
> 项目仓库：`https://github.com/AndyDu0921/wc26-predict`  
> 配套文档：`WC26预测系统_完整PRD与架构文档.md`  
> 最终目标：把 WC26 Predict 从“可运行的世界杯预测/分析脚本集合”收敛成一个可复盘、可校准、可运营、可商业化、对外合规的 AI 足球研究系统。  
> 重要更新：本最终版已加入“内部市场共识校准层”，允许后台使用赔率/市场价格做概率校准，但严禁在对外输出、宣传、视频、公开页面中展示或暗示博彩/投注内容。

---

## 0. 最终核验结论

我不能负责任地说“这个项目完全没有任何问题”。更准确的结论是：

> 在目前可访问的 PRD、GitHub 仓库页面、公开官方文档与外部资料范围内，上一版的大方向成立，但必须修正“赔率数据是否可用”“前端是否可用”“football-data.org lineup 能力”“DeepSeek 模型口径”这几处表述。本文件是收紧后的最终执行版；凡是无法通过公开资料确认的内容，均标为“必须实测”，不再当成确定事实。

### 0.1 已确认可以保留的判断

1. 项目方向正确：不是单纯脚本玩具，已经有历史比赛库、预测模型、缓存、赛后学习、权重优化、快照存储、内容生成等模块。
2. 最大短板仍然不是“模型不够多”，而是：预测入口不统一、权重口径不唯一、赛后学习闭环不严、情报输入为空、自动化未常驻、测试覆盖不足、前端几乎没有。
3. 内部加入市场赔率/市场价格数据用于概率校准，在建模逻辑上是合理的；公开输出必须彻底隔离赔率、盘口、投注建议和博彩宣传。
4. LLM 口径必须统一为：Claude Code 负责开发和编排；项目业务内所有 LLM 能力统一走 DeepSeek V4 Pro 官方 API，即 `deepseek-v4-pro`。

### 0.2 上一版必须修正的地方

| 项目 | 上一版潜在问题 | 最终修正 |
|---|---|---|
| 前端 | GitHub 有 `apps/web`，容易误判为可用前端 | 用户已确认前端“完全乱做”，最终按“几乎没有，需要重做”处理 |
| LLM | 不能泛写 DeepSeek API 或多模型任选 | 统一写 `deepseek-v4-pro` 官方 API；多模型只作为未来容灾项 |
| football-data.org lineup | 不能绝对写“不支持 lineup” | 改为“当前项目 tier/探测结果不能作为 T-60/T-40 稳定赛前首发来源” |
| 赔率数据 | 之前过度强调对外不碰，容易误伤内部校准 | 改为“内部可用，外部严禁展示” |
| 免费赔率源 | 不能承诺免费源一定覆盖 2026 世界杯 | 改为“API-Football 免费计划作为首选实时实测源；Football-Data.co.uk 用于历史训练；The Odds API 只作低频备选” |
| 合规 | 不能把平台规则写成已逐条官方核验 | 改为保守策略：公开内容避开预测、胜率、比分、赔率、盘口、投注、命中率 |

---

## 1. 项目铁律

### 1.1 对外定位

项目对外只能定位为：

- AI 足球研究系统。
- 世界杯数据分析工具。
- 赛前研究助手。
- 内容创作者数据工作台。
- 球队状态、赛程、历史趋势、战术/阵容/情报整理工具。

禁止对外定位为：

- 投注模型。
- 竞彩辅助。
- 盘口分析器。
- 赔率预测器。
- 命中率系统。
- 比分预测软件。
- 带单工具。

### 1.2 内外数据边界

最终边界如下：

```text
内部后台：
  可以使用赔率/市场价格作为 Market Consensus Calibration 数据源。
  可以保存 raw odds、去水位概率、市场变化、bookmaker_count、overround。
  可以在 internal_research_mode 查看 BaseProb、MarketProb、FinalProb 的差异。

创作者安全模式：
  不展示赔率、不展示博彩公司、不展示盘口、不展示投注含义。
  可以展示“模型综合分析”“不确定性提示”“球队状态”“赛程压力”“情报变化”。

公开安全模式：
  不展示概率、胜率、比分预测、赔率、盘口、xG、投注、命中率。
  只展示排名、历史趋势、球队看点、球员信息、赛程背景。
```

### 1.3 LLM 硬约束

所有 LLM 功能统一配置：

```env
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-v4-pro
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=...
```

使用原则：

- DeepSeek V4 Pro 负责新闻理解、信号抽取、报告草稿、赛后复盘摘要。
- DeepSeek V4 Pro 不直接决定最终概率。
- 所有 LLM 抽取必须有原文 URL、标题、发布时间、原文片段、抽取置信度。
- 没有来源的内容不能进入 `news_signals`。
- LLM 不能生成“内部消息”“疑似伤病”“更衣室矛盾”等无来源结论。

建议结构：

```text
backend/app/services/llm/
  deepseek_client.py
  signal_extraction.py
  report_writer.py
  postmatch_writer.py
  schemas.py
  prompts/
    extract_signal_v1.md
    generate_creator_script_v1.md
    postmatch_review_v1.md
```

---

## 2. 当前真实现状

### 2.1 根据上传 PRD 确认的项目现状

PRD 记录的 V1.5 现状：

- 比赛数据：16,868 场。
- 球员：1,248 名。
- 世界杯赛程：104 场。
- 预测快照：226 条。
- 赛后学习：65 场评估，平均 Brier 约 0.17，方向正确率约 74.6%。
- 模型服务：29 个 Python 文件。
- ORM 模型：24 个。
- 五层融合：Dixon-Coles、TabularMatchEnhancer、Elo、Pi-Rating、Weibull Copula。
- 数据库已有 `market_odds` 表，链路中已有 `market_calibrator()`。
- `news_signals = 0` 是核心瓶颈。
- Celery 配置了但没有常驻运行。
- 前端按用户补充视为几乎没有。

### 2.2 GitHub 与 PRD 冲突时的处理原则

GitHub README 显示仓库里有 `apps/web`，并写了 React/Vite/Tailwind 前端，但用户已确认那部分不能作为可用前端。因此：

- 不把 GitHub 前端当作现成产品。
- 不在计划中写“完善现有前端”作为主线。
- 正确表述是：重做一个极简、本地优先、只服务运营与视频素材的 Dashboard。

---

## 3. 一句话总诊断

WC26 Predict 的核心问题不是“再加一个模型”，而是要把系统从“多个脚本各自跑”收敛成一个严格闭环：

```text
统一预测入口
  → 统一权重配置
  → 统一数据快照
  → 统一市场共识校准
  → 统一输出过滤
  → 赛后评估
  → 候选权重
  → 回测验证
  → 人工批准发布
  → 下一轮预测
```

最终应该形成两个系统身份：

```text
内部身份：AI Football Research Engine
外部身份：AI Football Content & Research Workspace
```

内部可以研究概率、误差、市场共识、模型偏差；外部只展示合规足球分析。

---

## 4. 最终架构方案

### 4.1 唯一预测入口：PredictionPipeline

新增唯一预测入口：

```text
backend/app/services/prediction_pipeline.py
```

所有入口必须调用它：

```text
scripts/snapshot.py
scripts/pregenerate_wc26.py
routers/predictions.py
auto_postmatch.py
backtest scripts
Dashboard API
```

禁止在 `snapshot.py`、`prediction_orchestrator.py`、`learning_engine.py` 中各自写融合逻辑。

建议接口：

```python
class PredictionPipeline:
    def predict_match(
        self,
        home_team: str,
        away_team: str,
        competition: str,
        kickoff_at: datetime | None,
        neutral: bool,
        mode: Literal[
            "internal_research",
            "creator_safe",
            "public_safe"
        ] = "internal_research",
        as_of: datetime | None = None,
    ) -> PredictionResult:
        ...
```

### 4.2 分层结构

```text
InputResolver
  解析球队、比赛、赛程、match_id、kickoff_at、neutral

FeatureBuilder
  构造历史、近期状态、Elo、赛程、上下文、手动情报、新闻信号、市场共识特征

BaseModelEnsemble
  Dixon-Coles + Tabular + Elo + Pi-Rating + Weibull optional

MarketConsensusCalibration
  只在内部使用赔率/市场价格做概率校准

SignalAndContextAdjuster
  应用伤病、轮换、战意、赛程压力、比赛阶段、天气等结构化信号

ProbabilityCalibrator
  isotonic / temperature / Platt / multinomial calibration

SnapshotStore
  保存输入版本、模型版本、权重版本、数据版本、输出版本

OutputPolicyFilter
  internal_research / creator_safe / public_safe 三种输出过滤
```

---

## 5. 内部市场共识校准层

### 5.1 为什么要加入赔率/市场价格

从建模角度看，赔率可以看作市场对大量信息的压缩：球队实力、伤病、首发预期、赛程动机、天气、舆论、资金流、临场消息。学术研究长期把博彩公司赔率作为足球结果概率预测的重要基准；但赔率不能直接裸用，必须先去水位、处理偏差、防止数据泄漏。

本项目应该把这层命名为：

```text
Market Consensus Calibration
```

不要命名为：

```text
Odds Model
Betting Model
Bookmaker Model
```

### 5.2 数据源最终选择

| 数据源 | 最终定位 | 免费/无信用卡判断 | 适合用途 | 不能承诺的事 |
|---|---|---|---|---|
| API-Football | 首选实时赛前 odds provider | 官方页面显示 Free $0、100 requests/day、Pre-match Odds、In-play Odds，并写明 free plan no credit card | 世界杯期间低频抓 T-24h/T-6h/T-90m 市场快照 | 不能承诺一定覆盖 2026 世界杯所有比赛赔率，必须实测 fixture/league/odds endpoint |
| Football-Data.co.uk | 首选历史训练数据 | 页面写明历史结果、赔率、比赛统计 All FREE | 导入欧洲联赛历史赔率，训练去水位、校准、基准模型 | 不是实时世界杯赔率源；历史欧洲联赛与国家队世界杯存在 domain shift |
| The Odds API | 低频备选/对照源 | 官方页面显示 Starter Free 500 credits/month；历史赔率在免费层划线，不应依赖免费历史 | 小规模实时对照，验证 API-Football 异常 | 免费额度小；不承诺 2026 世界杯覆盖；免费层不能当主力 |
| 直接爬博彩网站 | 禁止作为主线 | 技术和合规风险高 | 不采用 | 反爬、账号、条款、稳定性风险高 |

### 5.3 API-Football 使用策略

免费计划每天 100 requests，不适合高频轮询。世界杯期间建议：

```text
T-24h：每场抓一次
T-6h：每场抓一次
T-90m：每场抓一次
T-40m：只有额度充足时抓一次
```

如果一天 4 场比赛：

```text
4 场 × 3 次 = 12 次核心 odds 请求
再加 fixture 匹配、错误重试、lineup/injury 检查，仍有机会控制在 100/day 内
```

必须实现 request budget：

```text
daily_limit = 100
hard_stop_at = 90
reserve_for_manual_debug = 10
```

### 5.4 Football-Data.co.uk 使用策略

用于历史训练和回测：

- 读取历史 CSV。
- 导入 `B365H/B365D/B365A`、`PSH/PSD/PSA`、`AvgH/AvgD/AvgA`、`MaxH/MaxD/MaxA`。
- 读取 closing odds 字段，如 `B365CH/B365CD/B365CA`、`AvgCH/AvgCD/AvgCA`。
- closing odds 只用于 benchmark 和 T-close 模型，不得混入 T-24h/T-6h 训练，避免数据泄漏。

### 5.5 去水位计算

最基础版本：

```python
def normalize_1x2_odds(home_odds: float, draw_odds: float, away_odds: float) -> dict:
    raw_home = 1.0 / home_odds
    raw_draw = 1.0 / draw_odds
    raw_away = 1.0 / away_odds
    total = raw_home + raw_draw + raw_away
    return {
        "home": raw_home / total,
        "draw": raw_draw / total,
        "away": raw_away / total,
        "overround": total - 1.0,
    }
```

后续可加入：

- Shin method。
- Power method。
- Favorite-longshot bias correction。
- bookmaker reliability weighting。

### 5.6 融合策略

不要让赔率压死自有模型。建议初始策略：

```text
BaseProb = DC + Tabular + Elo + Pi + Signal + Context
MarketProb = 去水位后的市场共识概率
FinalProb = blend(BaseProb, MarketProb, market_confidence)
```

初始权重：

```text
无市场数据：
  Final = 1.00 * BaseProb

单一 provider 或低置信市场：
  Final = 0.90 * BaseProb + 0.10 * MarketProb

多 bookmaker + T-24h/T-6h 稳定市场：
  Final = 0.75 * BaseProb + 0.25 * MarketProb

临场强市场 + 数据完整：
  Final = 0.65 * BaseProb + 0.35 * MarketProb
```

这只是初始值，最终必须通过 rolling backtest 优化。

### 5.7 数据泄漏规则

必须遵守：

```text
T-24h 预测只能使用 captured_at <= kickoff_at - 24h 的赔率快照。
T-6h 预测只能使用 captured_at <= kickoff_at - 6h 的赔率快照。
T-90m 预测只能使用 captured_at <= kickoff_at - 90m 的赔率快照。
Closing odds 只能用于 benchmark，不能训练早期预测。
训练集、验证集、测试集按时间切分，不能随机打散。
```

---

## 6. 数据库变更

### 6.1 新增表：market_odds_snapshots

```sql
CREATE TABLE market_odds_snapshots (
    id TEXT PRIMARY KEY,
    match_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    external_fixture_id TEXT,
    bookmaker TEXT,
    market_type TEXT NOT NULL,
    captured_at TIMESTAMP NOT NULL,
    kickoff_at TIMESTAMP,
    home_team_name TEXT,
    away_team_name TEXT,
    home_odds REAL,
    draw_odds REAL,
    away_odds REAL,
    implied_home REAL,
    implied_draw REAL,
    implied_away REAL,
    overround REAL,
    is_closing BOOLEAN DEFAULT FALSE,
    source_payload_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 6.2 新增表：market_consensus_snapshots

```sql
CREATE TABLE market_consensus_snapshots (
    id TEXT PRIMARY KEY,
    match_id TEXT NOT NULL,
    captured_at TIMESTAMP NOT NULL,
    kickoff_at TIMESTAMP,
    consensus_home REAL,
    consensus_draw REAL,
    consensus_away REAL,
    bookmaker_count INTEGER,
    provider_count INTEGER,
    overround_avg REAL,
    overround_min REAL,
    confidence REAL,
    source_snapshot_ids TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 6.3 新增表：output_audit_log

```sql
CREATE TABLE output_audit_log (
    id TEXT PRIMARY KEY,
    artifact_type TEXT NOT NULL,
    artifact_path TEXT,
    mode TEXT NOT NULL,
    passed BOOLEAN NOT NULL,
    blocked_terms TEXT,
    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 7. 新增文件清单

### 7.1 市场共识层

```text
backend/app/services/market/
  __init__.py
  provider_base.py
  api_football_provider.py
  football_data_uk_importer.py
  the_odds_api_provider.py
  probability.py
  consensus.py
  calibrator.py
  leakage_guard.py
  schemas.py
```

### 7.2 输出安全层

```text
backend/app/services/output_policy.py
backend/app/services/public_safety_filter.py
backend/scripts/audit_public_outputs_no_odds.py
```

### 7.3 统一预测入口

```text
backend/app/services/prediction_pipeline.py
backend/app/services/prediction_result.py
backend/app/services/weights.py
backend/app/services/model_registry.py
```

### 7.4 脚本

```text
backend/scripts/import_historical_odds_football_data_uk.py
backend/scripts/fetch_market_odds_api_football.py
backend/scripts/backtest_market_calibrator.py
backend/scripts/audit_prediction_pipeline_consistency.py
backend/scripts/audit_weights_consistency.py
backend/scripts/audit_data_freshness.py
```

---

## 8. 输出过滤规则

### 8.1 禁止词

`creator_safe` 和 `public_safe` 输出中，必须过滤：

```text
赔率
盘口
博彩
投注
竞彩
下注
庄家
博彩公司
betting
odds
bookmaker
handicap
spread
over/under
moneyline
wager
stake
payout
ROI
盈利
稳赚
必中
命中率
带单
```

### 8.2 public_safe 更严格

`public_safe` 还要过滤：

```text
胜率
概率
比分预测
预计比分
xG
expected goals
主胜
平局概率
客胜
```

公开内容可以保留：

```text
球队实力对比
近期状态
历史交锋
赛程背景
球员看点
战术看点
不确定性提示
```

### 8.3 验收标准

任何公开报告、视频脚本、Dashboard public 页面、导出的 Markdown、API public response，如果出现禁止词，CI 或脚本必须失败。

---

## 9. 模型评估体系

### 9.1 必须同时评估四类指标

```text
Brier Score：概率误差，越低越好
LogLoss：惩罚过度自信，越低越好
RPS：适合三分类有序结果，越低越好
ECE：概率校准误差，越低越好
```

### 9.2 必须比较三套输出

```text
BaseOnly：不使用市场数据
MarketOnly：只用去水位市场概率
FinalBlend：Base + Market calibrated blend
```

如果 `FinalBlend` 在 rolling backtest 中没有稳定优于 `BaseOnly`，不能上线市场校准权重，只能保留为 shadow mode。

### 9.3 Shadow Mode

市场共识层第一阶段必须 shadow mode：

```text
保存 MarketProb
保存 FinalBlend_candidate
但正式输出仍用 BaseProb
赛后记录 BaseOnly vs FinalBlend_candidate
连续 N 场/滚动窗口证明提升后，再启用 active_market_weight
```

建议条件：

```text
rolling_30_matches:
  FinalBlend Brier <= BaseOnly Brier - 0.005
  FinalBlend LogLoss <= BaseOnly LogLoss
  no severe calibration regression
```

---

## 10. P0 执行任务

### P0-1：统一 PredictionPipeline

目标：CLI、API、预生成、赛后学习、Dashboard 全部使用同一个预测入口。

验收标准：

```text
同一场比赛、同一 as_of、同一 mode：
  snapshot.py 输出概率 == API 输出概率 == pregenerate 输出概率
允许误差 <= 1e-6
```

### P0-2：统一权重配置

新增 `weights.py`：

```python
@dataclass
class WeightConfig:
    version: str
    dc: float
    tabular: float
    elo: float
    pi: float
    weibull: float
    market: float
    signal: float
    context: float
    active: bool
```

权重只能从数据库 active config 或唯一配置文件读取，不能散落在多个脚本。

### P0-3：市场共识层 shadow mode

先实现：

```text
fetch odds → normalize → save raw → build consensus → save candidate blend → 不影响正式输出
```

验收标准：

```text
odds provider 失败时，主预测不失败。
market 数据缺失时，Final = Base。
所有 raw odds 只在 internal_research_mode 可见。
creator_safe/public_safe 永不出现赔率字段。
```

### P0-4：DeepSeek V4 Pro 情报抽取

目标：解决 `news_signals = 0`。

流程：

```text
news_articles/manual source
  → DeepSeek V4 Pro extract_signal_v1
  → schema validation
  → evidence check
  → write news_signals
  → SignalAdjuster consumes news_signals
```

建议 schema：

```json
{
  "team": "string",
  "player": "string|null",
  "signal_type": "injury|suspension|lineup|rotation|motivation|weather|travel|coach|morale|other",
  "direction": "positive|negative|neutral",
  "severity": "low|medium|high",
  "confidence": 0.0,
  "effective_from": "datetime|null",
  "effective_until": "datetime|null",
  "source_url": "string",
  "source_title": "string",
  "evidence_quote": "string"
}
```

### P0-5：输出安全审计

新增脚本：

```bash
python backend/scripts/audit_public_outputs_no_odds.py --path reports/
```

验收标准：

```text
public_safe 和 creator_safe 输出中不得出现禁止词。
发现禁止词则退出码非 0。
CI/本地检查失败。
```

### P0-6：自动化先用 Windows Task Scheduler

先不要强行上 Celery。世界杯期间更重要的是稳定。

建议任务：

```text
每天 06:00：fetch fixtures / update match statuses
每天 08:00：fetch odds T-24h/T-6h candidates
比赛前 90m：fetch odds + manual checklist reminder
比赛后 30m：auto_postmatch.py
每天 23:30：backup db + export health report
```

---

## 11. Dashboard 最小版

前端按“几乎没有”重做。

### 11.1 只做本地运营后台

不要先做公开视频站。

页面：

```text
/admin/dashboard
  今日比赛
  预测状态
  数据新鲜度
  odds 快照状态 internal only
  news_signals 数量
  manual_events 数量
  学习日志
  输出安全审计结果
```

### 11.2 三种显示模式

```text
internal_research：显示完整模型、市场共识、误差、调试信息
creator_safe：隐藏赔率/盘口/投注，只保留内容创作可用信息
public_safe：只保留公开合规信息
```

验收标准：

```text
切换 creator_safe/public_safe 后，页面 DOM 文本中不得包含禁止词。
```

---

## 12. 商业化方向

### 12.1 不卖“预测”

不要卖：

```text
胜率
命中率
比分预测
投注建议
盘口分析
赔率套利
```

### 12.2 可以卖什么

可以卖：

```text
AI 足球内容工作台
世界杯数据素材库
球队赛前研究报告
创作者视频脚本生成器
球员/球队知识卡片
赛后复盘报告
数据可视化图表
本地私有研究系统部署
```

### 12.3 产品分层

```text
个人版：本地 Dashboard + 手动生成报告
创作者版：批量生成视频脚本/图表/赛前看点
研究版：内部概率、回测、模型误差、市场共识校准，但不对外传播赔率
机构版：私有部署、数据接入、报告模板定制
```

---

## 13. Claude Code 最终执行 Prompt

把下面整段交给 Claude Code：

```markdown
# 任务：WC26 Predict 最终核验版重构与市场共识校准层

你要在现有 wc26-predict 项目中执行一次保守、可回滚、可测试的重构。不要大爆炸重写。必须先审计，再小步提交。

## 硬约束
1. 项目对外不展示、不宣传、不解释赔率、盘口、博彩、投注建议。
2. 后台 internal_research_mode 可以使用市场赔率/市场价格作为 Market Consensus Calibration 数据源。
3. 所有 LLM 功能统一使用 DeepSeek V4 Pro 官方 API，模型名 `deepseek-v4-pro`。
4. DeepSeek V4 Pro 只做文本抽取、信号整理、报告草稿，不直接决定比赛概率。
5. GitHub 中 `apps/web` 不作为可用前端，按“前端几乎没有”处理。
6. football-data.org 当前 tier/探测结果不能作为 T-60/T-40 稳定赛前首发来源。
7. 不允许数据泄漏：T-24h 预测不能使用 T-24h 之后的 odds 或 closing odds。
8. 所有公开输出必须通过 forbidden terms 审计。

## Phase 0：只审计，不改业务逻辑
新增脚本：
- backend/scripts/audit_prediction_pipeline_consistency.py
- backend/scripts/audit_weights_consistency.py
- backend/scripts/audit_public_outputs_no_odds.py
- backend/scripts/audit_data_freshness.py

输出：
- reports/audit/pipeline_consistency.md
- reports/audit/weights_consistency.md
- reports/audit/public_output_safety.md
- reports/audit/data_freshness.md

## Phase 1：统一预测入口
新增：
- backend/app/services/prediction_pipeline.py
- backend/app/services/prediction_result.py
- backend/app/services/weights.py

要求：
- snapshot.py、pregenerate_wc26.py、prediction_orchestrator.py 逐步改为调用 PredictionPipeline。
- 同一 match/as_of/mode 输出一致。

## Phase 2：新增市场共识校准层，先 shadow mode
新增：
- backend/app/services/market/provider_base.py
- backend/app/services/market/api_football_provider.py
- backend/app/services/market/football_data_uk_importer.py
- backend/app/services/market/the_odds_api_provider.py
- backend/app/services/market/probability.py
- backend/app/services/market/consensus.py
- backend/app/services/market/calibrator.py
- backend/app/services/market/leakage_guard.py
- backend/scripts/import_historical_odds_football_data_uk.py
- backend/scripts/fetch_market_odds_api_football.py
- backend/scripts/backtest_market_calibrator.py

要求：
- API-Football 作为首选实时 odds provider，但必须实测 2026 世界杯覆盖。
- Football-Data.co.uk 用于历史训练和回测。
- The Odds API 只做低频备选，不作为主依赖。
- provider 失败不能影响主预测。
- shadow mode 下只记录候选结果，不替换正式概率。

## Phase 3：DeepSeek V4 Pro 信号抽取
新增：
- backend/app/services/llm/deepseek_client.py
- backend/app/services/llm/signal_extraction.py
- backend/app/services/llm/schemas.py
- backend/app/services/llm/prompts/extract_signal_v1.md

要求：
- 所有信号必须有 source_url、source_title、evidence_quote。
- 结构化写入 news_signals。
- confidence 低于阈值不进入模型，只进入人工复核队列。

## Phase 4：输出安全层
新增：
- backend/app/services/output_policy.py
- backend/app/services/public_safety_filter.py

要求：
- internal_research 可见 odds/market debug。
- creator_safe/public_safe 必须隐藏并过滤赔率相关字段和词汇。
- audit_public_outputs_no_odds.py 必须能扫描 reports、Dashboard build、API sample responses。

## Phase 5：本地 Dashboard 最小版
重做而不是修补旧前端。
页面只做：
- 今日比赛
- 数据新鲜度
- 预测状态
- market snapshot internal only
- news_signals/manual_events
- 学习日志
- 输出安全审计

## 验收标准
1. pytest 全部通过。
2. 同一比赛 CLI/API/pregenerate 输出一致。
3. market provider 失败时主预测正常。
4. public_safe/creator_safe 无赔率、盘口、博彩、投注等禁止词。
5. Shadow mode 回测报告能比较 BaseOnly、MarketOnly、FinalBlendCandidate。
6. DeepSeek V4 Pro 抽取信号必须可追溯来源。
7. 数据库迁移可回滚。
8. 每个阶段都有独立 commit。
```

---

## 14. 最终优先级路线图

### 14.1 立即执行：1-2 天

```text
1. audit scripts
2. weights consistency
3. PredictionPipeline skeleton
4. output safety filter
5. market tables migration
```

### 14.2 世界杯前必须完成

```text
1. PredictionPipeline 全入口统一
2. public/creator 输出安全审计
3. DeepSeek V4 Pro 手动/半自动情报抽取
4. API-Football odds provider 实测
5. Football-Data.co.uk 历史赔率导入
6. market calibration shadow mode
7. Windows Task Scheduler 自动化
8. 本地 Dashboard 最小版
```

### 14.3 世界杯期间运行方式

```text
每天：
  检查今日比赛
  检查数据新鲜度
  抓取 odds snapshot internal only
  人工录入/确认关键情报
  生成 creator_safe 内容
  发布前跑 public/creator safety audit
  赛后 auto_postmatch
  更新学习日志
  备份数据库
```

### 14.4 世界杯后长期方向

```text
1. 市场共识校准从 shadow mode 转 active mode，前提是回测证明有效。
2. 情报管道从人工录入升级为 DeepSeek V4 Pro + 多来源核验。
3. 建立长期国家队数据库和滚动状态空间模型。
4. Dashboard 从本地工具升级为创作者工作台。
5. 商业化聚焦内容工具、研究报告、私有部署，不碰博彩导流。
```

---

## 15. 事实来源与核验说明

### 15.1 已核验来源

- FIFA 官方赛程页：2026 世界杯为 48 队、104 场比赛。  
  URL: `https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/articles/match-schedule-fixtures-results-teams-stadiums`

- FIFA 官方赛事页：2026 世界杯为首次 48 队、三主办国赛事。  
  URL: `https://www.fifa.com/tournaments/mens/worldcup/canadamexicousa2026`

- DeepSeek 官方更新日志：DeepSeek API 支持 V4-Pro 和 V4-Flash，可通过 OpenAI ChatCompletions 与 Anthropic interface 使用，模型名为 `deepseek-v4-pro` / `deepseek-v4-flash`。  
  URL: `https://api-docs.deepseek.com/updates`

- DeepSeek Claude Code 集成文档：DeepSeek 官方提供 Claude Code 集成说明。  
  URL: `https://api-docs.deepseek.com/guides/coding_agents`

- API-Football 官方页面：Free plan $0、100 requests/day，列出 Pre-match Odds / In-play Odds，并写明 free plan no credit card。  
  URL: `https://www.api-football.com/`

- Football-Data.co.uk 官方数据页：历史结果、赔率、比赛统计 All FREE。  
  URL: `https://www.football-data.co.uk/data.php`

- Football-Data.co.uk notes：说明 closing odds 字段以 `C` 标识，例如 `B365CH`。  
  URL: `https://www.football-data.co.uk/notes.txt`

- The Odds API 官方页面：Starter Free 500 credits/month；free 层不包含 Historical Odds；支持 h2h、spreads、totals 等市场。  
  URL: `https://the-odds-api.com/`

- GitHub 仓库页面：仓库存在 `apps/web`，README 中写了前端和 DeepSeek，但用户已确认前端不可作为真实可用状态。  
  URL: `https://github.com/AndyDu0921/wc26-predict`

- 学术参考：Štrumbelj & Robnik Šikonja, 2010, Online bookmakers' odds as forecasts: The case of European soccer leagues。研究分析 10,699 场欧洲足球比赛和 10 家线上博彩公司赔率，支持“赔率可作为概率预测基准”的判断。  
  URL: `https://www.sciencedirect.com/science/article/abs/pii/S0169207009001733`

### 15.2 必须实测，不能当作确定事实

以下内容不能直接写死，必须由 Claude Code 新增脚本实测：

```text
API-Football 是否覆盖 2026 世界杯所有 fixture。
API-Football 免费计划是否实际返回 WC26 的 pre-match odds。
The Odds API 是否覆盖 2026 World Cup sport key 和 h2h odds。
免费 odds 源在比赛临近 T-24h/T-6h/T-90m 的可用性。
现有数据库 market_odds 字段是否足够，不足则迁移。
现有 snapshot.py/orchestrator 权重是否完全一致。
旧 apps/web 中哪些代码可复用，默认先不要复用。
```

---

## 16. 最终结论

本项目最终路线应调整为：

```text
内部：
  历史数据 + 数学模型 + DeepSeek V4 Pro 情报抽取 + 市场共识校准 + 赛后回测学习

外部：
  足球研究报告 + 内容创作素材 + 球队/球员/赛程分析 + 合规可视化
```

最重要的产品边界：

```text
后台可以用赔率提升校准。
前台不能显示赔率。
宣传不能提投注。
商业化不能卖命中率。
```

最重要的技术边界：

```text
统一预测入口。
统一权重配置。
防止数据泄漏。
市场校准先 shadow mode。
所有公开输出必须安全过滤。
所有 LLM 能力使用 DeepSeek V4 Pro 官方 API。
```

这才是 WC26 Predict 后续最稳的方向。
