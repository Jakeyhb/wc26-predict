# WC26 Predict — 校验后执行手册

## 已纠正的3个错误

| 错误位置 | 原内容 | 修正后 | 影响范围 |
|----------|--------|--------|----------|
| 模型扩展文档 | `BivariateWeibullGoalModel` | `WeibullCopulaGoalsModel` | 直接调用会报 AttributeError |
| auto_postmatch.py 示例 | `np.mean` 除以3 | 应除以 `(r-1)=2` | 绝对RPS值偏小2/3，优化本身不受影响 |
| injury_fetcher.py 示例 | BBC Sport URL 未验证 | 先手动浏览器确认 | URL结构可能不存在 |

---

## 第零阶段：本周内，零代码，摸清现状

### 步骤 0.1 — 查数据库现状（10分钟）

在 WSL 里执行：

```bash
cd /path/to/your/project
sqlite3 your_database.db
```

```sql
-- 确认 manual_events 的完整结构
.schema manual_events
SELECT * FROM manual_events ORDER BY id DESC LIMIT 10;

-- 确认 market_odds 里是否有时间戳
.schema market_odds
SELECT * FROM market_odds;

-- 确认 news_signals 是否真的是0条
SELECT COUNT(*) FROM news_signals;

-- 确认 prediction_learning_log 里的63条
SELECT COUNT(*) FROM prediction_learning_log;
SELECT competition, COUNT(*) FROM prediction_learning_log 
JOIN matches ON prediction_learning_log.match_id = matches.id
GROUP BY competition;
```

**预期发现**：market_odds 里的2条记录很可能没有时间戳字段；
manual_events 里的8+条记录里，source_url 字段可能是空的或不存在。
把实际情况记录下来，决定 ALTER TABLE 的具体操作。

---

### 步骤 0.2 — 手动验证 BBC Sport 伤情 URL

打开浏览器，依次尝试以下 URL，看哪个有结构化的伤情信息：

```
https://www.bbc.co.uk/sport/football/arsenal
https://www.bbc.co.uk/sport/football/teams/arsenal
https://www.skysports.com/football/arsenal/injuries
https://www.premierinjuries.com/injury-table.php
```

**如果 BBC/Sky 没有结构化的队伍伤情页**，改用以下两个替代方案（二选一）：
- 方案A：api-football（RapidAPI，免费版每天100次请求）→ 继续看步骤 1.4
- 方案B：transfermarkt 的伤情页（有稳定HTML结构，可直接爬取）

---

### 步骤 0.3 — 安装并验证 penaltyblog

```bash
# 你的系统是 Python 3.14，先确认兼容性
pip install penaltyblog --break-system-packages

# 验证安装
python3 -c "
import penaltyblog as pb
print('penaltyblog 版本:', pb.__version__)

# 验证所有我们要用的类都存在
print('Dixon-Coles:', hasattr(pb.models, 'DixonColesGoalModel'))
print('Weibull（正确类名）:', hasattr(pb.models, 'WeibullCopulaGoalsModel'))
print('Pi-Rating:', hasattr(pb.ratings, 'PiRating'))
print('RPS:', hasattr(pb.metrics, 'rps'))
print('Shin去抽水:', hasattr(pb.implied, 'shin'))
"
```

**如果 Python 3.14 出现兼容问题**（可能的 Cython 编译问题）：

```bash
# 查看具体错误
pip install penaltyblog --break-system-packages -v 2>&1 | tail -30

# 如果是 Cython 编译失败，尝试安装 wheel 版本
pip install penaltyblog --break-system-packages --only-binary :all:
```

如果 3.14 确实不兼容，回退用虚拟环境：

```bash
python3.12 -m venv venv_penaltyblog
source venv_penaltyblog/bin/activate
pip install penaltyblog
```

---

## 第一阶段：1-2周，数据可信度修复（按此顺序执行）

### 步骤 1.1 — 数据库加溯源字段

```sql
-- 在 SQLite 里执行（直接修改生产库之前先备份）
.backup /tmp/wc26_backup_before_provenance.db

-- manual_events 表加字段
ALTER TABLE manual_events ADD COLUMN source_url TEXT;
ALTER TABLE manual_events ADD COLUMN source_type TEXT DEFAULT 'manual';
ALTER TABLE manual_events ADD COLUMN fetched_at TEXT;
ALTER TABLE manual_events ADD COLUMN source_credibility TEXT DEFAULT 'unverified';

-- market_odds 表加字段
ALTER TABLE market_odds ADD COLUMN fetched_at TEXT;
ALTER TABLE market_odds ADD COLUMN odds_age_minutes INTEGER;

-- 新建 odds_history 表（记录赔率变化曲线）
CREATE TABLE IF NOT EXISTS odds_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER,
    home_prob REAL,
    draw_prob REAL,
    away_prob REAL,
    bookmaker TEXT,
    fetched_at TEXT,
    drift_from_previous REAL,
    FOREIGN KEY (match_id) REFERENCES matches(id)
);

-- 新建 pending_signals 表（低置信度信号等待确认）
CREATE TABLE IF NOT EXISTS pending_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER,
    signal_type TEXT,
    team TEXT,
    player TEXT,
    description TEXT,
    raw_confidence REAL,
    source_url TEXT,
    source_headline TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    status TEXT DEFAULT 'pending'
);
```

---

### 步骤 1.2 — 修复 add_manual_event.py

找到你的 `add_manual_event.py`，在写入数据库之前加入验证逻辑：

```python
# add_manual_event.py 改造版（在现有代码基础上修改）
from datetime import datetime

# 可信来源白名单
CREDIBLE_SOURCES = {
    "HIGH":   ["skysports.com", "bbc.co.uk", "espn.com", "lequipe.fr",
               "arsenal.com", "psg.fr", "uefa.com", "bild.de", "guardian.com"],
    "MEDIUM": ["goal.com", "telegraph.co.uk", "marca.com", "mirror.co.uk"],
    "LOW":    ["twitter.com", "reddit.com", "tiktok.com"]
}

def assess_credibility(source_url):
    if not source_url:
        return "unverified"
    for level, domains in CREDIBLE_SOURCES.items():
        if any(d in source_url for d in domains):
            return level
    return "unknown"

def add_event_with_verification(team, event_type, magnitude, source_url, notes=""):
    """
    改造后的录入函数：source_url 必填，低可信度自动降 magnitude
    """
    if not source_url:
        print("❌ source_url 是必填项，请提供原始新闻链接")
        return False
    
    credibility = assess_credibility(source_url)
    original_magnitude = magnitude
    
    if credibility == "LOW":
        magnitude = magnitude * 0.5
        print(f"⚠️ 低可信度来源，magnitude 从 {original_magnitude} 调整为 {magnitude}")
    elif credibility == "unverified":
        magnitude = magnitude * 0.3
        print(f"⚠️ 未知来源，magnitude 从 {original_magnitude} 调整为 {magnitude}")
    
    # 检查是否存在冲突记录
    # （在此调用你现有的数据库写入函数，加入新字段）
    conn = get_db_connection()
    conn.execute("""
        INSERT INTO manual_events 
        (team, event_type, magnitude, source_url, source_type, 
         source_credibility, fetched_at, notes)
        VALUES (?, ?, ?, ?, 'manual', ?, ?, ?)
    """, (team, event_type, magnitude, source_url, credibility,
          datetime.now().isoformat(), notes))
    conn.commit()
    
    print(f"✅ 已录入：{event_type} | 来源可信度: {credibility} | magnitude: {magnitude}")
    return True
```

---

### 步骤 1.3 — 修复 RPS 公式（auto_postmatch.py）

找到你现有的 Brier Score 计算，加入正确的 RPS 计算：

```python
# auto_postmatch.py 中的修复

def ranked_probability_score(predicted_probs, actual_outcome):
    """
    标准 RPS 公式。
    predicted_probs: [P(home_win), P(draw), P(away_win)]，必须和为1
    actual_outcome: 0=主队胜, 1=平局, 2=客队胜
    
    ⚠️ 修正说明：原版用 np.mean 除以3，这里改为除以(r-1)=2
    """
    import numpy as np
    
    cumulative_pred = np.cumsum(predicted_probs)
    actual_vector = np.zeros(3)
    actual_vector[actual_outcome] = 1
    cumulative_actual = np.cumsum(actual_vector)
    
    # 关键修正：只取前 r-1=2 项，再除以 r-1=2
    diffs_sq = (cumulative_pred[:-1] - cumulative_actual[:-1]) ** 2
    return float(np.mean(diffs_sq))  # 现在是 (term1 + term2) / 2，正确

# 验证：RPS 边界值检查
# 完美预测：P=[1,0,0], actual=0 → RPS 应该 = 0
# 最差情况：P=[1,0,0], actual=2 → RPS 应该 = 1
assert ranked_probability_score([1,0,0], 0) == 0.0
assert ranked_probability_score([1,0,0], 2) == 1.0
print("✅ RPS 公式验证通过")
```

---

### 步骤 1.4 — 在 health_check.py 加入赔率时效检查

在你现有的17项检查基础上追加：

```python
# health_check.py 新增检查

def check_odds_freshness(match_id):
    """检查当前比赛的赔率是否新鲜"""
    conn = get_db_connection()
    odds = conn.execute("""
        SELECT fetched_at FROM market_odds 
        WHERE match_id = ? ORDER BY id DESC LIMIT 1
    """, (match_id,)).fetchone()
    
    if not odds or not odds['fetched_at']:
        return False, "赔率数据不存在或无时间戳"
    
    from datetime import datetime, timezone
    fetched = datetime.fromisoformat(odds['fetched_at'])
    age_hours = (datetime.now() - fetched).total_seconds() / 3600
    
    if age_hours > 24:
        return False, f"赔率过期 {age_hours:.1f}h，请重新抓取"
    elif age_hours > 6:
        return True, f"⚠️ 赔率较旧 {age_hours:.1f}h，建议更新"
    else:
        return True, f"✅ 赔率新鲜 {age_hours:.1f}h"
```

---

### 步骤 1.5 — 在 snapshot.py 末尾追加溯源面板

在你的 `render_markdown` 函数输出末尾加入：

```python
def render_data_provenance_panel(match_id, signals_used, odds_data):
    """生成溯源面板，强制写入每份报告末尾"""
    from datetime import datetime
    
    now = datetime.now()
    
    lines = [
        "\n---",
        "## 数据溯源面板（自动生成）",
        ""
    ]
    
    # 赔率状态
    if odds_data and odds_data.get('fetched_at'):
        age_h = (now - datetime.fromisoformat(odds_data['fetched_at'])).total_seconds() / 3600
        status = "✅ 新鲜" if age_h < 2 else ("⚠️ 较旧" if age_h < 12 else "❌ 过期")
        lines.append(f"- **市场赔率**：Pinnacle via The Odds API，"
                    f"抓取于 {odds_data['fetched_at'][:16]}（距现在 {age_h:.1f}h）{status}")
    else:
        lines.append("- **市场赔率**：❌ 无时间戳，无法判断新鲜度")
    
    # 情报信号状态
    manual_count = len([s for s in signals_used if s.get('source_type') == 'manual'])
    auto_count = len([s for s in signals_used if s.get('source_type') == 'auto-rss'])
    
    if manual_count > 0:
        lines.append(f"- **球员情报**：{manual_count} 条人工录入，"
                    f"{auto_count} 条自动提取 ⚠️ 人工部分需核对原始来源链接")
    elif auto_count > 0:
        lines.append(f"- **球员情报**：{auto_count} 条自动提取自 RSS ✅")
    else:
        lines.append("- **球员情报**：❌ 0 条信号，本次预测未使用任何情报调整")
    
    # news_signals 状态
    news_count = get_news_signal_count(match_id)
    if news_count == 0:
        lines.append("- **新闻信号**：❌ 0 条（GDELT/RSS 本次未采集到有效信号）")
    else:
        lines.append(f"- **新闻信号**：{news_count} 条 ✅")
    
    # 模型版本
    lines.append(f"- **模型版本**：{get_current_git_hash()[:8]}")
    
    return "\n".join(lines)
```

---

## 第二阶段：3-4周，模型扩展（第一阶段完成后执行）

### 步骤 2.1 — 接入 Pi-Rating

在 `snapshot.py` 的 Step 4.4（κ-Elo混合）之前，加入 Pi-Rating 计算：

```python
# snapshot.py Step 4.4 改造

import penaltyblog as pb
from datetime import datetime, timedelta

def compute_pi_rating(home_team, away_team, training_df, is_neutral=True):
    """
    用历史数据训练 Pi-Rating，返回胜平负概率
    注意：训练时按时间顺序喂数据，不能打乱顺序
    """
    pi = pb.ratings.PiRating()
    
    # 按日期排序（重要：Pi-Rating是动态系统，顺序不能乱）
    sorted_df = training_df.sort_values("date")
    
    for _, row in sorted_df.iterrows():
        pi.update(
            home_team=row["home_team"],
            away_team=row["away_team"],
            home_goals=int(row["home_goals"]),
            away_goals=int(row["away_goals"])
        )
    
    # 预测
    try:
        result = pi.predict(home_team, away_team, neutral=is_neutral)
        return {
            "home_win": result.home_win,
            "draw":     result.draw,
            "away_win": result.away_win
        }
    except KeyError:
        # 球队不在 Pi-Rating 系统中（训练数据不足）
        print(f"⚠️ Pi-Rating: {home_team} 或 {away_team} 不在训练集中，跳过")
        return None

# 在融合步骤中：
pi_pred = compute_pi_rating(home, away, training_df, is_neutral=True)
if pi_pred:
    # 原有：clean = 0.85 × dc_enh + 0.15 × elo_pred
    # 改为：
    clean = (0.79 * dc_enh + 
             0.15 * elo_pred + 
             0.06 * pi_pred)
    # ↑ Pi-Rating 占 6%，暂时从 Elo 那里划拨，总权重保持100%
```

---

### 步骤 2.2 — 接入 WeibullCopulaGoalsModel

这个模型和 Dixon-Coles 并行运行，互相校验：

```python
# snapshot.py Step 4.2 改造，在 Dixon-Coles 之后添加

def fit_weibull_model(training_df, timeout=60):
    """
    WeibullCopulaGoalsModel：正确的类名（不是 BivariateWeibullGoalModel）
    """
    try:
        wc = pb.models.WeibullCopulaGoalsModel(
            goals_home=training_df["home_goals"],
            goals_away=training_df["away_goals"],
            teams_home=training_df["home_team"],
            teams_away=training_df["away_team"],
            weights=training_df["weight"]
        )
        wc.fit()
        return wc
    except Exception as e:
        print(f"⚠️ Weibull 模型拟合失败: {e}，跳过")
        return None

# 预测并融合
wc_model = fit_weibull_model(training_df)
if wc_model:
    try:
        wc_pred_grid = wc_model.predict(home, away, neutral=True)
        wc_pred = {
            "home_win": float(wc_pred_grid.home_win),
            "draw":     float(wc_pred_grid.draw),
            "away_win": float(wc_pred_grid.away_win)
        }
    except Exception as e:
        print(f"⚠️ Weibull 预测失败: {e}，跳过")
        wc_pred = None

# 融合时：
# 原来 Step 4.2 的 dc_pred 基础上，加入 Weibull
if wc_pred:
    dc_wc_blend = {
        "home_win": 0.75 * dc_pred["home_win"] + 0.25 * wc_pred["home_win"],
        "draw":     0.75 * dc_pred["draw"]     + 0.25 * wc_pred["draw"],
        "away_win": 0.75 * dc_pred["away_win"] + 0.25 * wc_pred["away_win"]
    }
else:
    dc_wc_blend = dc_pred  # Weibull 失败时退回纯 DC
```

---

### 步骤 2.3 — Skellam 平局修正（欧冠淘汰赛专用）

```python
# skellam_correction.py — 新建文件
import numpy as np
from scipy.special import iv  # Modified Bessel function of first kind

def skellam_pmf(k, mu1, mu2):
    """
    Skellam 分布 PMF：P(X_home - X_away = k)
    mu1：主队期望进球（来自 DC 模型的 lambda_home）
    mu2：客队期望进球（来自 DC 模型的 mu_away）
    """
    return float(
        np.exp(-(mu1 + mu2)) * 
        (mu1 / mu2) ** (k / 2) * 
        iv(abs(k), 2 * np.sqrt(mu1 * mu2))
    )

def apply_skellam_draw_correction(dc_probs, lambda_home, mu_away, competition, stage):
    """
    只在欧冠淘汰赛阶段激活，修正平局概率
    其他情况直接返回原概率不做修改
    """
    is_knockout = (
        competition in ["Champions League", "Europa League"] and
        stage in ["R16", "QF", "SF", "Final", "Knockout"]
    )
    
    if not is_knockout:
        return dc_probs  # 不修正，原样返回
    
    # 计算 Skellam 平局概率（进球差=0）
    skellam_draw = skellam_pmf(0, lambda_home, mu_away)
    
    # 混合：60% 原始 DC 平局 + 40% Skellam 平局
    corrected_draw = 0.6 * dc_probs["draw"] + 0.4 * skellam_draw
    
    # 重新归一化（平局变了，胜负按比例压缩）
    delta = corrected_draw - dc_probs["draw"]
    corrected_home = dc_probs["home_win"] - delta * 0.5
    corrected_away = dc_probs["away_win"] - delta * 0.5
    
    total = corrected_home + corrected_draw + corrected_away
    
    return {
        "home_win": corrected_home / total,
        "draw":     corrected_draw / total,
        "away_win": corrected_away / total
    }

# 在 snapshot.py 的融合之后调用：
final_probs = apply_skellam_draw_correction(
    clean, lambda_home, mu_away, competition, stage
)
```

---

### 步骤 2.4 — 分场景权重配置

新建 `model_configs.py`：

```python
# model_configs.py — 新建文件
MODEL_CONFIGS = {
    "UCL_FINAL": {
        "dc_weight": 0.40, "wc_weight": 0.15, "enhancer_weight": 0.25,
        "pi_weight": 0.12, "elo_weight": 0.08,
        "skellam_correction": True,
        "dynamic_window_days": 180,
        "market_weight_max": 0.10  # 欧冠决赛减少市场依赖
    },
    "UCL_KNOCKOUT": {
        "dc_weight": 0.43, "wc_weight": 0.15, "enhancer_weight": 0.25,
        "pi_weight": 0.10, "elo_weight": 0.07,
        "skellam_correction": True,
        "dynamic_window_days": 120,
        "market_weight_max": 0.15
    },
    "PREMIER_LEAGUE": {
        "dc_weight": 0.48, "wc_weight": 0.10, "enhancer_weight": 0.30,
        "pi_weight": 0.07, "elo_weight": 0.05,
        "skellam_correction": False,
        "dynamic_window_days": 90,
        "market_weight_max": 0.20
    },
    "LIGUE_1": {
        "dc_weight": 0.50, "wc_weight": 0.10, "enhancer_weight": 0.28,
        "pi_weight": 0.07, "elo_weight": 0.05,
        "skellam_correction": False,
        "dynamic_window_days": 90,
        "market_weight_max": 0.20
    }
}

def get_config(competition, stage=None):
    """
    根据赛事和阶段返回配置
    """
    key = f"{competition}_{stage}".upper().replace(" ", "_") if stage else competition.upper()
    return MODEL_CONFIGS.get(key, MODEL_CONFIGS["PREMIER_LEAGUE"])
```

---

### 步骤 2.5 — RPS 权重优化器（每月运行一次）

新建 `optimize_weights.py`：

```python
# optimize_weights.py — 新建文件
import numpy as np
from scipy.optimize import minimize

def ranked_probability_score(predicted_probs, actual_outcome):
    """已修正的 RPS 公式（÷2不是÷3）"""
    cumulative_pred = np.cumsum(predicted_probs)
    actual_vector = np.zeros(3)
    actual_vector[actual_outcome] = 1
    cumulative_actual = np.cumsum(actual_vector)
    diffs_sq = (cumulative_pred[:-1] - cumulative_actual[:-1]) ** 2
    return float(np.mean(diffs_sq))

def optimize_ensemble_weights():
    """
    从 prediction_learning_log 读取历史预测，
    找到最优混合权重，写入 model_weight_config 表
    """
    conn = get_db_connection()
    
    logs = conn.execute("""
        SELECT dc_probs, enhancer_probs, elo_probs, pi_probs, wc_probs,
               actual_outcome
        FROM prediction_learning_log
        WHERE actual_outcome IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 100  -- 用最近100场
    """).fetchall()
    
    if len(logs) < 20:
        print(f"⚠️ 数据不足（{len(logs)}条 < 20条），跳过权重优化")
        return None
    
    def objective(weights):
        w = np.abs(weights) / np.sum(np.abs(weights))
        total_rps = 0
        for log in logs:
            blended = (w[0] * np.array(log["dc_probs"]) + 
                      w[1] * np.array(log["enhancer_probs"]) +
                      w[2] * np.array(log["elo_probs"]) +
                      w[3] * np.array(log["pi_probs"] or [0.33, 0.33, 0.34]) +
                      w[4] * np.array(log["wc_probs"] or [0.33, 0.33, 0.34]))
            blended = blended / blended.sum()
            total_rps += ranked_probability_score(blended, log["actual_outcome"])
        return total_rps / len(logs)
    
    x0 = np.array([0.40, 0.25, 0.08, 0.12, 0.15])  # 初始权重（阶段2目标配置）
    result = minimize(objective, x0, method="Nelder-Mead",
                     options={"maxiter": 2000, "xatol": 1e-4})
    
    optimal = np.abs(result.x) / np.sum(np.abs(result.x))
    
    print(f"优化前 RPS: {objective(x0):.4f}")
    print(f"优化后 RPS: {result.fun:.4f}")
    print(f"最优权重: DC={optimal[0]:.3f} Enh={optimal[1]:.3f} "
          f"Elo={optimal[2]:.3f} Pi={optimal[3]:.3f} WC={optimal[4]:.3f}")
    
    # 写入数据库
    conn.execute("""
        INSERT INTO model_weight_config 
        (dc_weight, enhancer_weight, elo_weight, pi_weight, wc_weight, 
         created_at, n_samples, rps_before, rps_after)
        VALUES (?, ?, ?, ?, ?, datetime('now'), ?, ?, ?)
    """, (*optimal.tolist(), len(logs), objective(x0), result.fun))
    conn.commit()
    
    return optimal

if __name__ == "__main__":
    optimize_ensemble_weights()
```

---

## 第三阶段：1-2月（第二阶段稳定后执行）

### 步骤 3.1 — RSS + Claude API 自动新闻信号

```python
# news_signal_extractor.py — 新建文件
import feedparser
import json
import anthropic

RSS_FEEDS = {
    "sky_sports": "https://www.skysports.com/rss/12040",
    "bbc_football": "https://feeds.bbci.co.uk/sport/football/rss.xml",
    "espn_soccer":  "https://www.espn.com/espn/rss/soccer/news"
}

def extract_signals(home_team, away_team, match_date):
    client = anthropic.Anthropic()  # 从环境变量读 ANTHROPIC_API_KEY
    
    headlines = []
    for source, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:50]:
                title = entry.get("title", "")
                if (home_team.lower() in title.lower() or 
                    away_team.lower() in title.lower() or
                    any(alias in title.lower() for alias in get_aliases(home_team, away_team))):
                    headlines.append({
                        "title": title,
                        "summary": entry.get("summary", "")[:200],
                        "source": source,
                        "url": entry.get("link", ""),
                        "published": str(entry.get("published", ""))
                    })
        except Exception as e:
            print(f"⚠️ RSS 抓取失败 {source}: {e}")
    
    if not headlines:
        print("ℹ️ 无相关新闻标题")
        return []
    
    prompt = f"""你是一名足球情报分析师。以下是关于 {home_team} vs {away_team}（{match_date}）的新闻标题和摘要。

提取所有与以下类别相关的信息，以 JSON 数组返回（无其他文字）：
- INJURY: 球员受伤或缺阵
- RETURN: 伤愈复出
- SUSPENSION: 停赛
- ROTATION: 主帅暗示轮换
- LINEUP: 首发阵容信息

每条记录格式：
{{"signal_type": "...", "team": "...", "player": "（可选）", 
  "description": "一句话", "confidence": "high/medium/low",
  "source_headline": "原标题", "source_url": "链接"}}

如无相关信号，返回 []。

新闻内容：
{json.dumps(headlines, ensure_ascii=False)}"""
    
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",  # 注意：使用正确的模型字符串
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()
        signals = json.loads(text)
        print(f"✅ 提取到 {len(signals)} 条信号")
        return signals
    except (json.JSONDecodeError, Exception) as e:
        print(f"⚠️ 信号提取失败: {e}")
        return []

def get_aliases(home_team, away_team):
    """返回常用缩写和别名"""
    aliases = {
        "Paris Saint-Germain": ["PSG", "Paris"],
        "Arsenal": ["Arsenal", "Gunners"],
        "Manchester City": ["Man City", "City"],
    }
    result = []
    for team in [home_team, away_team]:
        result.extend(aliases.get(team, []))
    return [a.lower() for a in result]
```

---

### 步骤 3.2 — 蒙特卡洛锦标赛模拟

```python
# monte_carlo_tournament.py — 新建文件
import numpy as np
from scipy.stats import poisson

def simulate_knockout_tournament(bracket, dc_model, n_simulations=100_000):
    """
    bracket 格式：{"QF": [("PSG","Arsenal"), ("Dortmund","Barca"),...], "SF":..., "Final":...}
    dc_model：已拟合的 DixonColesGoalModel 实例
    """
    all_teams = list(set(
        t for matches in bracket.values() for pair in matches for t in pair
    ))
    results = {t: {"reach_SF": 0, "reach_Final": 0, "Champion": 0} for t in all_teams}
    
    for _ in range(n_simulations):
        qf_winners = []
        for home, away in bracket.get("QF", []):
            winner = simulate_single_match(home, away, dc_model)
            qf_winners.append(winner)
        
        sf_winners = []
        for i in range(0, len(qf_winners), 2):
            home, away = qf_winners[i], qf_winners[i+1]
            winner = simulate_single_match(home, away, dc_model)
            sf_winners.append(winner)
            results[home]["reach_SF"] += 1
            results[away]["reach_SF"] += 1
        
        finalist1 = simulate_single_match(sf_winners[0], sf_winners[1], dc_model)
        finalist2 = [t for t in sf_winners if t != finalist1][0]
        champion = simulate_single_match(finalist1, finalist2, dc_model)
        
        results[finalist1]["reach_Final"] += 1
        results[finalist2]["reach_Final"] += 1
        results[champion]["Champion"] += 1
    
    # 归一化
    for team in results:
        for key in results[team]:
            results[team][key] /= n_simulations
    
    return results

def simulate_single_match(home, away, dc_model):
    """模拟一场比赛，平局进点球（50/50）"""
    try:
        grid = dc_model.predict(home, away, neutral=True)
        lam = grid.home_goals_expectation
        mu  = grid.away_goals_expectation
    except:
        lam, mu = 1.2, 1.0  # fallback
    
    h = poisson.rvs(lam)
    a = poisson.rvs(mu)
    
    if h > a: return home
    if a > h: return away
    return home if np.random.random() > 0.5 else away  # 平局随机（50/50点球）
```

---

## 总结：执行前的必做检查清单

```
第零阶段开始前：
□ sqlite3 确认3张表的实际结构
□ 浏览器验证BBC/Sky伤情URL是否存在
□ pip install penaltyblog 并运行验证脚本

第一阶段开始前：
□ 备份数据库：.backup /tmp/wc26_backup_YYYYMMDD.db
□ 在测试库上先执行 ALTER TABLE，确认无误再操作生产库

第二阶段开始前：
□ 第一阶段所有步骤运行无报错
□ penaltyblog 验证脚本所有项目输出 True
□ 至少有3场比赛的完整赛后评估数据（用于验证Pi-Rating输出是否合理）

第三阶段开始前：
□ 第二阶段模型在至少10场比赛上运行过
□ Brier/RPS 指标没有明显变差（与第一阶段基线比较）
□ 准备好 ANTHROPIC_API_KEY（用于 news_signal_extractor.py）
```
