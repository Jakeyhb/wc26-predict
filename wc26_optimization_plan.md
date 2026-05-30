# WC26 Predict — 完整优化方案

> 核心问题：系统产出的报告"太合理了"，但可信度无法自证。
> 本方案分三个优先级，从最紧迫的数据可信度问题开始，到模型改进，再到工程基础设施。

---

## 第一层：数据可信度（立即要做）

这一层是最核心的问题，不解决它，其他所有改进都是空中楼阁。

### 1.1 为每一条数据打上溯源标签

**现状问题**：报告里的每一条结论，读者（包括你自己）无法知道它的数据来自哪里、什么时候抓取的、是机器自动还是人工录入的。

**解决方案**：在数据库层面引入统一的溯源字段。

```python
# 在 manual_events 和 market_odds 等所有关键表新增字段
ALTER TABLE manual_events ADD COLUMN source_type TEXT; -- 'auto' | 'manual' | 'inferred'
ALTER TABLE manual_events ADD COLUMN source_url TEXT;  -- 原始来源URL
ALTER TABLE manual_events ADD COLUMN fetched_at TEXT;  -- 抓取时间戳
ALTER TABLE manual_events ADD COLUMN verified_by TEXT; -- 'system' | 'operator'

ALTER TABLE market_odds ADD COLUMN fetched_at TEXT;
ALTER TABLE market_odds ADD COLUMN odds_timestamp TEXT; -- 赔率本身的时间戳（Pinnacle更新时间）
ALTER TABLE market_odds ADD COLUMN staleness_minutes INTEGER; -- 距比赛开始的分钟数
```

然后在报告生成时，强制输出一个"数据溯源面板"：

```python
def generate_data_provenance_panel(match_id):
    """
    生成每份报告附带的数据溯源面板
    让读者清楚每条信息的真实来源
    """
    panel = {
        "odds": {
            "source": "The Odds API / Pinnacle",
            "fetched_at": get_odds_timestamp(match_id),
            "age_minutes": calculate_data_age(match_id, "odds"),
            "status": "live" if age < 30 else "stale" if age < 120 else "expired"
        },
        "injury_signals": {
            "source": "manual_events 表",
            "entry_count": count_manual_events(match_id),
            "latest_entry": get_latest_manual_event_time(match_id),
            "operator_verified": True  # 因为是人工录入的
        },
        "match_history": {
            "source": "football-data.org + martj42",
            "training_samples": n_samples,
            "latest_match": get_latest_training_match_date()
        },
        "news_signals": {
            "source": "GDELT RSS",
            "count": news_signal_count,  # 当前是0，要如实显示
            "status": "inactive" if count == 0 else "active"
        }
    }
    return panel
```

**在报告末尾强制显示**：

```
数据溯源面板（自动生成）
├── 市场赔率：Pinnacle via The Odds API，抓取于 17:42 CST（距比赛 6.3h）✅ 新鲜
├── 球员情报：manual_events 表，3条记录，最新录入 16:00 CST ⚠️ 人工录入，非自动
├── 历史比赛：football-data.org，最新数据截止 2026-05-28 ✅
├── xG数据：StatsBomb，本赛季数据完整 ✅
└── 新闻信号：0条（GDELT/RSS 本次未采集到有效信号）❌ 缺失
```

---

### 1.2 赔率时效性验证

**现状问题**：market_odds 表只有 2 条记录，且没有时间戳验证。赔率随时间漂移，开球前 6 小时的盘口和开球前 30 分钟可能差很多。

**解决方案**：写一个赔率监控脚本，每 30 分钟主动验证一次，并记录漂移量。

```python
# odds_monitor.py - 新增脚本
import schedule
import time
from datetime import datetime, timedelta

def check_odds_freshness_and_drift(match_id):
    """
    主动拉取最新赔率，与上次记录比较，
    超过阈值则触发警报和重新校准
    """
    latest_odds = fetch_from_odds_api(match_id)
    previous_odds = get_latest_odds_from_db(match_id)
    
    if previous_odds is None:
        store_odds(match_id, latest_odds)
        return
    
    # 计算漂移
    drift = {
        "home_win": abs(latest_odds["home"] - previous_odds["home"]),
        "draw":     abs(latest_odds["draw"] - previous_odds["draw"]),
        "away_win": abs(latest_odds["away"] - previous_odds["away"])
    }
    
    max_drift = max(drift.values())
    
    # 赔率单方向移动超过5个百分点 → 说明市场有重要信息流入
    if max_drift > 0.05:
        log_alert(f"⚠️ 赔率重大漂移 {match_id}: {max_drift:.1%}，可能有伤情/阵容新消息")
        trigger_recalibration(match_id, latest_odds)  # 重新跑 Step 6
    
    store_odds_with_timestamp(match_id, latest_odds, drift)

# 比赛日内每30分钟执行一次
schedule.every(30).minutes.do(check_odds_freshness_and_drift, match_id=ACTIVE_MATCH_ID)
```

**数据库新增表**：

```sql
CREATE TABLE odds_history (
    id INTEGER PRIMARY KEY,
    match_id INTEGER,
    home_prob REAL,
    draw_prob REAL,
    away_prob REAL,
    bookmaker TEXT,
    fetched_at TEXT,
    drift_from_previous REAL,  -- 与上次相比最大漂移
    FOREIGN KEY (match_id) REFERENCES matches(id)
);
```

这样你就有了赔率的完整变化曲线，可以判断当前赔率是"稳定共识"还是"刚刚发生了市场变动"。

---

### 1.3 手动情报的结构化核实流程

**现状问题**：`add_manual_event.py` 直接写入数据库，没有核实机制。一条错误的伤情信息会通过 Step 7 影响最终 xG，进而影响所有概率输出。

**解决方案**：引入一个两步核实流程，不需要复杂实现。

```python
# add_manual_event.py 改造版本
def add_event_with_verification(team, event_type, magnitude, source_url, notes):
    """
    录入前要求提供：
    1. 原始来源URL（必填）
    2. 来源媒体可信度评分（自动查找）
    3. 是否有第二来源佐证（选填）
    """
    
    # 自动检查来源可信度
    source_credibility = assess_source(source_url)
    # sky sports/bbc/官方队媒 → HIGH
    # twitter/reddit → LOW
    # 无来源 → UNVERIFIED
    
    # 检查是否有相互矛盾的已有记录
    conflicts = check_conflicting_events(team, event_type)
    
    if conflicts:
        print(f"⚠️ 警告：存在冲突记录 {conflicts}")
        print("是否覆盖？(y/n)")
        confirm = input()
        if confirm != 'y':
            return
    
    # 低可信度来源 → 自动降低 magnitude 50%，并标记
    if source_credibility == "LOW":
        magnitude *= 0.5
        status = "unverified"
        print(f"⚠️ 低可信度来源，magnitude 自动调整至 {magnitude}")
    else:
        status = "verified"
    
    store_event(team, event_type, magnitude, source_url, source_credibility, status)
    print(f"✅ 已录入，可信度: {source_credibility}，状态: {status}")

# 可信来源白名单
CREDIBLE_SOURCES = {
    "HIGH": ["skysports.com", "bbc.co.uk", "espn.com", "lequipe.fr",
             "arsenal.com", "psg.fr", "uefa.com", "bild.de"],
    "MEDIUM": ["goal.com", "guardian.com", "telegraph.co.uk", "marca.com"],
    "LOW": ["twitter.com", "reddit.com", "forums"]
}
```

---

## 第二层：自动化数据采集（修复空洞）

### 2.1 修复 injuries.json — 接入真实伤情数据

injuries.json 目前是空的，但这是报告里"感觉最像人话"的部分，恰恰是自动化程度最低的。

**方案一：接入 API-Football 伤情端点（最推荐）**

```python
# injury_fetcher.py - 新增脚本
import requests

API_FOOTBALL_KEY = "your_key"  # rapidapi上的api-football，免费版每天100次

def fetch_injuries_before_match(home_team_id, away_team_id, match_date):
    """
    在比赛前48小时自动拉取双方伤情名单
    """
    url = "https://api-football-v1.p.rapidapi.com/v3/injuries"
    
    for team_id in [home_team_id, away_team_id]:
        response = requests.get(url, 
            headers={"x-rapidapi-key": API_FOOTBALL_KEY},
            params={"team": team_id, "date": match_date}
        )
        injuries = response.json()["response"]
        
        for injury in injuries:
            store_injury_event(
                player_name=injury["player"]["name"],
                team_id=team_id,
                injury_type=injury["player"]["reason"],  # "Knee Injury", "Suspended" etc
                status=injury["player"]["type"],          # "Questionable", "Out"
                source="api-football",
                source_url=f"api-football/injuries/team/{team_id}",
                fetched_at=datetime.now().isoformat()
            )
```

**方案二（免费备选）**：爬取 BBC Sport 的 injury 页面

```python
def scrape_bbc_injuries(team_name):
    """
    BBC Sport 有专门的球队伤情页，结构稳定，适合爬取
    """
    url = f"https://www.bbc.co.uk/sport/football/teams/{team_name}/injuries"
    # 解析 .injury-player 元素
    # 字段: player_name, injury_type, expected_return
```

**在 hourly_predict.py 中集成**：

```python
# hourly_predict.py 修改
def hourly_predict_pipeline(match_id):
    # 原有步骤...
    
    # 新增：比赛前48小时开始自动拉伤情
    hours_to_kickoff = get_hours_to_kickoff(match_id)
    if hours_to_kickoff <= 48:
        fetch_injuries_before_match(home_id, away_id, match_date)
        print(f"✅ 伤情数据已更新，{hours_to_kickoff:.0f}h 距开球")
    
    # 原有预测步骤...
```

---

### 2.2 修复 news_signals — 用 Claude API 做新闻结构化

Event Registry 需要付费 key，GDELT 正文拿不到。但有一个你已经有条件做到的方案：用 BBC/Sky Sports RSS 拿标题，再用 Claude API 做结构化提取。

```python
# news_signal_extractor.py - 新增脚本
import feedparser
import anthropic

RSS_FEEDS = {
    "sky_sports": "https://www.skysports.com/rss/12040",
    "bbc_football": "https://feeds.bbci.co.uk/sport/football/rss.xml",
    "espn_soccer": "https://www.espn.com/espn/rss/soccer/news"
}

def extract_signals_from_rss(home_team, away_team, match_date):
    """
    从 RSS 拉取标题，用 Claude 提取结构化伤情/阵容信号
    """
    client = anthropic.Anthropic()
    
    # 收集过去 48 小时的相关标题
    relevant_headlines = []
    for source, url in RSS_FEEDS.items():
        feed = feedparser.parse(url)
        for entry in feed.entries:
            # 过滤：包含球队名且在过去48h
            if (home_team.lower() in entry.title.lower() or 
                away_team.lower() in entry.title.lower()):
                relevant_headlines.append({
                    "title": entry.title,
                    "summary": entry.get("summary", ""),
                    "published": entry.published,
                    "source": source,
                    "url": entry.link
                })
    
    if not relevant_headlines:
        return []
    
    # 用 Claude 结构化提取
    prompt = f"""
    以下是关于 {home_team} vs {away_team}（{match_date}）的新闻标题和摘要。
    请提取所有与以下类别相关的信息，以 JSON 数组返回：
    - INJURY: 球员受伤或缺阵
    - RETURN: 球员伤愈复出
    - SUSPENSION: 停赛
    - ROTATION: 主帅暗示轮换
    - LINEUP: 首发阵容信息
    
    每条记录包含字段：
    - signal_type: 上述类别之一
    - team: 涉及球队
    - player: 涉及球员（如有）
    - description: 一句话描述
    - confidence: "high"/"medium"/"low"（基于信息确定性）
    - source_headline: 原始标题
    - source_url: 原始链接
    
    新闻内容：
    {json.dumps(relevant_headlines, ensure_ascii=False, indent=2)}
    
    只返回 JSON 数组，不要其他文字。
    """
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    signals = json.loads(response.content[0].text)
    
    # 写入数据库，附带来源
    for signal in signals:
        store_news_signal(signal, fetched_at=datetime.now().isoformat())
    
    return signals
```

这个方案完全用你已有的 RSS 源，不需要新 API Key，而且每次提取都有原始标题作为证据链。

---

### 2.3 阵容数据补全

赛前 2 小时官方阵容公布后，这是最有价值的信号，但当前系统完全没有处理。

```python
# lineup_fetcher.py - 新增脚本
def fetch_confirmed_lineups(match_id, football_data_match_id):
    """
    通过 football-data.org 获取官方公布阵容
    开球前 1-2 小时通常可以拿到
    """
    url = f"https://api.football-data.org/v4/matches/{football_data_match_id}"
    response = requests.get(url, headers={"X-Auth-Token": FOOTBALL_DATA_KEY})
    
    match_data = response.json()
    
    if match_data.get("homeTeam", {}).get("lineup"):
        # 阵容已公布
        home_lineup = match_data["homeTeam"]["lineup"]
        away_lineup = match_data["awayTeam"]["lineup"]
        
        # 检查关键球员是否在首发
        home_key_players = get_key_players(home_team_id)
        missing_key_players = [p for p in home_key_players if p not in home_lineup]
        
        if missing_key_players:
            # 自动触发 INJURY/ROTATION 信号
            for player in missing_key_players:
                add_auto_signal(
                    team=home_team_id,
                    signal_type="ROTATION",
                    player=player,
                    magnitude=0.05,
                    source="official_lineup",
                    confidence="high"
                )
        
        return True
    
    return False  # 阵容未公布
```

---

## 第三层：模型与报告质量改进

### 3.1 解决"市场校准让模型变得没有观点"的问题

**现状问题**：市场校准（Step 6）把模型概率向市场拉拢，导致"模型与市场高度一致"几乎是被设计保证的，没有信息含量。

**方案**：把模型"独立输出"和"校准后输出"分开展示，让读者看到两者的差距。

```python
def generate_prediction_with_transparency(match_id):
    """
    分层输出，而不是只输出最终混合值
    """
    # 各层独立输出（在混合之前）
    dc_raw = run_dixon_coles(match_id)
    enhancer_raw = run_tabular_enhancer(match_id)
    elo_raw = run_kappa_elo(match_id)
    market_fair = get_market_fair_odds(match_id)  # 去抽水后的市场概率
    
    # 最终混合
    final = blend_all(dc_raw, enhancer_raw, elo_raw, market_fair)
    
    return {
        "model_independent": {
            "home": (0.578 * dc_raw["home"] + 0.272 * enhancer_raw["home"] + 0.15 * elo_raw["home"]),
            # 不含市场校准的纯模型输出
        },
        "market_consensus": market_fair,
        "final_blended": final,
        "model_vs_market_edge": {
            "home": final["home"] - market_fair["home"],
            "draw": final["draw"] - market_fair["draw"],
            "away": final["away"] - market_fair["away"]
        },
        "has_meaningful_edge": abs(final["home"] - market_fair["home"]) > 0.03
        # 只有当模型与市场分歧>3%时，才有真正的"观点"
    }
```

报告里应该显示：

```
模型独立预测（不含市场）：PSG 44.1% / 平 27.2% / 阿森纳 28.7%
市场共识（Pinnacle去抽水）：PSG 41.0% / 平 30.0% / 阿森纳 31.0%
模型真实优势：PSG +3.1pp ← 这才是模型实际"有观点"的地方
```

---

### 3.2 置信度应该反映数据缺失，而不是掩盖它

**现状问题**：当前置信度公式 `confidence = min(0.95, 0.45 + ...)` 是基于样本量和概率差值的，但它没有惩罚数据缺失。news_signals=0、injuries.json 为空，置信度依然可以输出 0.78。

**方案**：引入数据完整性惩罚项。

```python
def calculate_confidence_with_data_penalty(match_id, n_matches, home_prob, away_prob):
    # 原有基础置信度
    base_confidence = min(0.95, 0.45 + min(0.25, n_matches/300) + abs(home_prob - away_prob) * 0.2)
    
    # 数据完整性检查
    data_penalties = []
    
    # 1. 赔率数据是否新鲜
    odds_age_hours = get_odds_age_hours(match_id)
    if odds_age_hours > 6:
        data_penalties.append(("stale_odds", 0.05))
    elif odds_age_hours > 24:
        data_penalties.append(("very_stale_odds", 0.10))
    
    # 2. 是否有任何球员情报
    signal_count = count_signals(match_id)  # manual + news
    if signal_count == 0:
        data_penalties.append(("no_injury_signals", 0.03))
    
    # 3. 训练数据是否足够针对这两队
    club_specific_matches = count_club_specific_matches(home_team, away_team)
    if club_specific_matches < 50:
        data_penalties.append(("sparse_club_data", 0.08))
    
    # 4. 赔率与模型分歧过大（说明有我们不知道的信息）
    market_divergence = get_model_market_divergence(match_id)
    if market_divergence > 0.08:
        data_penalties.append(("large_market_divergence", 0.05))
    
    total_penalty = sum(p for _, p in data_penalties)
    final_confidence = max(0.30, base_confidence - total_penalty)
    
    return {
        "confidence": final_confidence,
        "penalties": data_penalties,  # 向报告使用者展示扣分原因
        "data_completeness": 1 - (total_penalty / 0.30)
    }
```

---

### 3.3 比分矩阵可视化验证

当前报告只给出 Top 3 比分概率，但没有完整矩阵。加入完整的 5×5 矩阵输出，让人可以手工交叉验证。

```python
def output_score_matrix(lambda_home, mu_away):
    """
    输出完整比分矩阵，供人工核查
    """
    from scipy.stats import poisson
    
    print("完整比分概率矩阵（主场横轴，客场纵轴）")
    print("     " + "  ".join([f"客{i}" for i in range(6)]))
    
    total = 0
    for h in range(6):
        row = []
        for a in range(6):
            prob = poisson.pmf(h, lambda_home) * poisson.pmf(a, mu_away)
            row.append(f"{prob:.3f}")
            total += prob
        print(f"主{h}:  " + "  ".join(row))
    
    print(f"\n矩阵求和（应≈1.0）: {total:.4f}")
    # 如果求和偏离1太多，说明截断误差大，需要用更大的矩阵
```

---

### 3.4 历史预测准确率追踪面板

你有 63 场赛后评估数据，Brier 0.17，但报告里没有分情境的准确率。

```python
def generate_accuracy_breakdown():
    """
    按情境分组统计准确率，找出模型的盲点
    """
    breakdowns = {
        "by_competition": {
            "UCL": calculate_accuracy(filter="ucl"),
            "PL": calculate_accuracy(filter="pl"),
            "Ligue1": calculate_accuracy(filter="ligue1")
        },
        "by_favorite_status": {
            "heavy_favorite_won": ...,   # 模型>60%胜率方赢
            "upset": ...,                # 模型<40%方赢
            "close_call": ...            # 27%-40%区间
        },
        "by_market_alignment": {
            "model_agreed_with_market": ...,
            "model_disagreed": ...       # 这组的准确率最关键
        },
        "by_signal_availability": {
            "had_injury_signals": ...,
            "no_signals": ...
        }
    }
    return breakdowns
```

这能告诉你：**模型在哪类比赛上真正有超越市场的能力，在哪类比赛上应该直接使用市场赔率。**

---

## 第四层：工程基础设施

### 4.1 数据验证测试套件

在 `health_check.py` 基础上新增 17 项检查：

```python
# 在 health_check.py 中新增以下检查
DATA_VALIDATION_CHECKS = [
    # 赔率检查
    ("odds_freshness", lambda: check_odds_age() < 120),           # 赔率不超过2小时
    ("odds_sum_to_one", lambda: abs(sum_fair_odds() - 1.0) < 0.01), # 去抽水后归一化
    ("odds_not_null", lambda: check_market_odds_not_null()),
    
    # 伤情信号检查（比赛前24h）
    ("injury_signals_present", lambda: count_active_signals() > 0),
    ("no_conflicting_signals", lambda: check_no_signal_conflicts()),
    ("signal_source_verified", lambda: all_signals_have_source()),
    
    # 模型输出检查
    ("probabilities_sum_to_one", lambda: abs(sum_probs() - 1.0) < 0.001),
    ("xg_in_range", lambda: 0.3 < predicted_xg < 4.0),
    ("model_market_divergence_ok", lambda: max_divergence() < 0.15),
    
    # 训练数据检查
    ("sufficient_training_data", lambda: n_training_matches() >= 100),
    ("data_not_stale", lambda: latest_match_date() > (today - 30_days)),
]

def run_all_checks():
    results = []
    for name, check_fn in DATA_VALIDATION_CHECKS:
        try:
            passed = check_fn()
            results.append({"check": name, "passed": passed, "time": datetime.now()})
        except Exception as e:
            results.append({"check": name, "passed": False, "error": str(e)})
    
    fail_count = sum(1 for r in results if not r["passed"])
    if fail_count > 0:
        print(f"⚠️ {fail_count} 项数据验证失败，预测置信度自动下调")
    
    return results
```

---

### 4.2 完整的审计日志

```python
# audit_log.py - 新增
import logging

audit_logger = logging.getLogger("wc26.audit")
audit_logger.setLevel(logging.INFO)
handler = logging.FileHandler("audit.log")
handler.setFormatter(logging.Formatter('%(asctime)s | %(message)s'))
audit_logger.addHandler(handler)

# 在关键节点自动记录
def log_prediction_run(match_id, final_probs, data_sources_used, warnings):
    audit_logger.info(json.dumps({
        "event": "prediction_run",
        "match_id": match_id,
        "probabilities": final_probs,
        "data_sources": data_sources_used,
        "warnings": warnings,
        "operator": os.getenv("USER", "unknown"),
        "git_commit": get_current_git_hash()  # 记录代码版本
    }))

def log_manual_event(team, event_type, source_url, operator):
    audit_logger.info(json.dumps({
        "event": "manual_event_added",
        "team": team,
        "event_type": event_type,
        "source_url": source_url,
        "operator": operator
    }))
```

---

### 4.3 赛后自动比对流程改进

当前 `auto_postmatch.py` 已有基础，但缺少信号有效性追踪。

```python
# auto_postmatch.py 新增
def evaluate_signal_effectiveness(match_id, actual_result):
    """
    赛后评估每条信号是否真的影响了预测准确性
    """
    signals_used = get_signals_for_match(match_id)
    
    for signal in signals_used:
        # 反事实推断：如果没有这条信号，预测会是什么？
        counterfactual_probs = run_prediction_without_signal(match_id, signal["id"])
        actual_probs = get_final_prediction(match_id)
        
        # 哪个更接近真实结果？
        signal_helped = brier_score(counterfactual_probs, actual_result) > \
                        brier_score(actual_probs, actual_result)
        
        update_signal_accuracy_ema(signal["signal_type"], signal_helped)
        
        print(f"信号 [{signal['signal_type']}] {'✅ 有效' if signal_helped else '❌ 无效或反效'}")
```

---

## 实施路线图

以下按优先级排列，不需要全部同时做。

| 优先级 | 任务 | 预计工时 | 收益 |
|--------|------|----------|------|
| 🔴 P0 | 数据溯源标签 + 报告里的溯源面板 | 4h | 立即解决"信息来源不透明"问题 |
| 🔴 P0 | 赔率时间戳验证 + 新鲜度显示 | 2h | 消除赔率过期风险 |
| 🔴 P0 | add_manual_event.py 改造（来源必填） | 2h | 防止无来源信息录入 |
| 🟡 P1 | injuries.json 接入 API-Football 或 BBC 爬虫 | 8h | 关键空洞，最高优先级自动化 |
| 🟡 P1 | RSS + Claude 新闻信号提取 | 6h | 修复 news_signals=0 |
| 🟡 P1 | 置信度加入数据完整性惩罚 | 3h | 不再掩盖数据缺失 |
| 🟡 P1 | 模型独立输出 vs 市场分开展示 | 3h | 让"观点"有信息含量 |
| 🟢 P2 | 阵容自动采集（football-data.org） | 4h | 开球前2h最高价值信号 |
| 🟢 P2 | 准确率情境分组面板 | 5h | 找出模型真正的优势区域 |
| 🟢 P2 | 数据验证测试套件 | 4h | 防止静默错误 |
| 🟢 P2 | 赛后信号有效性评估 | 4h | 量化手动情报的实际贡献 |
| ⚪ P3 | 审计日志 | 2h | 完整记录，长期价值 |
| ⚪ P3 | 完整比分矩阵可视化 | 2h | 辅助人工核查 |
| ⚪ P3 | 前端数据溯源面板展示 | 6h | 面向用户的透明度 |

---

## 一个关于系统定位的根本性建议

你问"怎么知道数据是准确的"，这背后有一个更大的问题：**你的系统应该告诉用户它不知道什么，而不只是展示它知道什么。**

优秀的预测系统有一个特征：它会主动暴露自己的不确定性。每份报告都应该有一个"这份预测的主要风险点"板块，例如：

```
⚠️ 本次预测的主要不确定性来源
1. 球员情报来源：3条记录均为人工录入（非自动），请核对原始来源链接
2. 赔率数据：上次抓取于 3.2 小时前，开球前应重新验证
3. 俱乐部专项数据：训练集以国家队为主，欧冠俱乐部专项仅 2,039 场
4. 模型与市场的真实分歧：仅在 PSG 胜率上有 +1.9pp 的非平凡差异
```

这四行字，比把报告做得更"完美"更有价值。

---

*最后更新：2026-05-30 | 适用版本：WC26 Predict v当前*
