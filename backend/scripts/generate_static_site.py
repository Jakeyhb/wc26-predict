#!/usr/bin/env python3
"""
generate_static_site.py — WC26 Predict 静态网页生成器 v2
- 世界杯开幕前(now → 6/10): 预览模式，突出焦点比赛
- 世界杯期间(6/11+): 工具模式，当日赛程+预测
- 2026世界杯视觉风格: 深藏蓝底 + 霓虹强调色
"""

import sqlite3
import json
from datetime import datetime, timedelta, date
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "local_stage2.db"
OUTPUT_DIR = PROJECT_ROOT.parent / "frontend" / "dist"
OUTPUT_FILE = OUTPUT_DIR / "index.html"

# ── 2026 WC visual palette ─────────────────────────────────────────────────

# Background: deep midnight blue, not pure black
BG = "#080d1f"
BG_CARD = "#0f1535"
BG_CARD_HOVER = "#151d45"
BORDER = "#1e2850"
BORDER_ACCENT = "#2a3a70"

# Text
TEXT_PRIMARY = "#e8ecff"
TEXT_SECONDARY = "#8892b8"
TEXT_DIM = "#556088"

# Accent: vibrant neon on dark
ACCENT_GREEN = "#00e5a0"
ACCENT_ORANGE = "#ff6b3d"
ACCENT_CYAN = "#00c4ff"
ACCENT_PINK = "#ff3d7f"
ACCENT_YELLOW = "#ffd740"
ACCENT_PURPLE = "#b388ff"

# Team colors
HOME_COLOR = "#00e5a0"
DRAW_COLOR = "#ffd740"
AWAY_COLOR = "#ff6b3d"

# Confidence
CONF_HIGH = "#00e5a0"
CONF_MED = "#ffd740"
CONF_LOW = "#ff6b3d"

# ── Helpers ──────────────────────────────────────────────────────────────────

def get_db():
    return sqlite3.connect(str(DB_PATH))

def get_latest_snapshot(conn, match_id):
    cur = conn.cursor()
    cur.execute("""
        SELECT baseline_probs, expected_goals, top_scores, elo_ratings,
               confidence, adjusted_probs
        FROM prediction_snapshots
        WHERE match_id = ?
        ORDER BY generated_at DESC LIMIT 1
    """, (match_id,))
    row = cur.fetchone()
    if not row:
        return None
    return {
        "baseline_probs": json.loads(row[0]) if row[0] else None,
        "expected_goals": json.loads(row[1]) if row[1] else None,
        "top_scores": json.loads(row[2]) if row[2] else None,
        "elo_ratings": json.loads(row[3]) if row[3] else None,
        "confidence": row[4],
        "adjusted_probs": json.loads(row[5]) if row[5] else None,
    }

def fetch_upcoming_matches(conn, days=14):
    """Return scheduled matches with optional snapshot data."""
    cutoff = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    cur = conn.cursor()
    cur.execute("""
        SELECT m.id, m.match_date, ht.name, ht.name_zh,
               at.name, at.name_zh, m.competition, m.stage
        FROM matches m
        JOIN teams ht ON m.home_team_id = ht.id
        JOIN teams at ON m.away_team_id = at.id
        WHERE m.status = 'scheduled'
          AND date(m.match_date) >= date('now')
          AND date(m.match_date) <= ?
        ORDER BY m.match_date
    """, (cutoff,))
    return cur.fetchall()

# ── HTML components ──────────────────────────────────────────────────────────

CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    background: """ + BG + """;
    color: """ + TEXT_PRIMARY + """;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    max-width: 640px;
    margin: 0 auto;
    padding: 24px 16px 48px;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
}

/* ── Header ── */
header {
    text-align: center;
    padding: 24px 0 16px;
}
.header-logo {
    font-size: 28px;
    font-weight: 900;
    letter-spacing: 1px;
    background: linear-gradient(135deg, """ + ACCENT_GREEN + """, """ + ACCENT_CYAN + """, """ + ACCENT_PINK + """);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.header-sub {
    font-size: 12px;
    color: """ + TEXT_SECONDARY + """;
    margin-top: 4px;
}
.mode-badge {
    display: inline-block;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 2px;
    padding: 3px 12px;
    border-radius: 20px;
    margin-top: 8px;
}
.mode-preview {
    background: """ + ACCENT_PINK + """22;
    color: """ + ACCENT_PINK + """;
    border: 1px solid """ + ACCENT_PINK + """44;
}
.mode-live {
    background: """ + ACCENT_GREEN + """22;
    color: """ + ACCENT_GREEN + """;
    border: 1px solid """ + ACCENT_GREEN + """44;
}

/* ── Countdown ── */
.countdown {
    text-align: center;
    padding: 20px 16px;
    margin: 20px 0;
    background: linear-gradient(135deg, """ + BG_CARD + """, """ + BG_CARD_HOVER + """);
    border: 1px solid """ + BORDER + """;
    border-radius: 16px;
}
.countdown-title {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 3px;
    color: """ + ACCENT_ORANGE + """;
    margin-bottom: 8px;
}
.countdown-timer {
    font-size: 42px;
    font-weight: 900;
    letter-spacing: 2px;
    color: """ + TEXT_PRIMARY + """;
}
.countdown-small {
    font-size: 13px;
    color: """ + TEXT_SECONDARY + """;
}

/* ── Date header ── */
.date-header {
    font-size: 12px;
    font-weight: 700;
    color: """ + ACCENT_CYAN + """;
    margin: 28px 0 12px;
    padding: 6px 0;
    border-bottom: 2px solid """ + ACCENT_CYAN + """33;
    letter-spacing: 1px;
}

/* ── Match card ── */
.match-card {
    background: """ + BG_CARD + """;
    border: 1px solid """ + BORDER + """;
    border-radius: 14px;
    padding: 18px;
    margin-bottom: 12px;
    transition: border-color 0.2s;
}
.match-card.featured {
    border: 2px solid """ + ACCENT_PINK + """55;
    background: linear-gradient(135deg, """ + BG_CARD + """, """ + ACCENT_PINK + """0a);
}
.match-card-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 14px;
}
.match-comp {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: """ + TEXT_SECONDARY + """;
}
.match-time {
    font-size: 11px;
    color: """ + TEXT_DIM + """;
}
.match-teams {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 14px;
}
.team-name {
    font-size: 17px;
    font-weight: 800;
    max-width: 42%;
    word-wrap: break-word;
    color: """ + TEXT_PRIMARY + """;
}
.team-vs {
    font-size: 13px;
    font-weight: 700;
    color: """ + TEXT_DIM + """;
    padding: 0 6px;
}
.match-xg {
    font-size: 12px;
    font-weight: 600;
    color: """ + TEXT_SECONDARY + """;
    text-align: center;
    margin-bottom: 12px;
}
.match-xg span {
    color: """ + ACCENT_GREEN + """;
    font-weight: 800;
    font-size: 15px;
}

/* ── Probability bar ── */
.prob-row {
    display: flex;
    align-items: center;
    margin: 5px 0;
    gap: 8px;
}
.prob-label {
    width: 36px;
    font-size: 11px;
    font-weight: 600;
    text-align: right;
    flex-shrink: 0;
}
.prob-value {
    width: 48px;
    font-size: 13px;
    font-weight: 700;
    flex-shrink: 0;
}
.prob-track {
    flex: 1;
    height: 10px;
    background: """ + BORDER + """;
    border-radius: 5px;
    overflow: hidden;
}
.prob-fill {
    height: 100%;
    border-radius: 5px;
    min-width: 3px;
    transition: width 0.3s;
}
.prob-fill.home { background: """ + HOME_COLOR + """; }
.prob-fill.draw { background: """ + DRAW_COLOR + """; }
.prob-fill.away { background: """ + AWAY_COLOR + """; }

/* ── Top 3 scores ── */
.top-scores {
    margin-top: 10px;
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}
.score-chip {
    font-size: 10px;
    padding: 3px 10px;
    background: """ + BORDER + """;
    border-radius: 10px;
    color: """ + TEXT_SECONDARY + """;
}
.score-chip .score {
    font-weight: 700;
    color: """ + TEXT_PRIMARY + """;
}
.score-chip .pct {
    color: """ + ACCENT_GREEN + """;
    font-weight: 600;
}

/* ── Badge ── */
.badge {
    font-size: 10px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 8px;
    white-space: nowrap;
}
.badge-low { color: """ + CONF_LOW + """; background: """ + CONF_LOW + """18; }
.badge-med { color: """ + CONF_MED + """; background: """ + CONF_MED + """18; }
.badge-high { color: """ + CONF_HIGH + """; background: """ + CONF_HIGH + """18; }
.badge-featured {
    display: inline-block;
    font-size: 9px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 2px;
    padding: 4px 10px;
    border-radius: 12px;
    margin-bottom: 10px;
    background: """ + ACCENT_PINK + """22;
    color: """ + ACCENT_PINK + """;
    border: 1px solid """ + ACCENT_PINK + """44;
}

/* ── Footer ── */
footer {
    text-align: center;
    font-size: 11px;
    color: """ + TEXT_DIM + """;
    margin-top: 40px;
    padding-top: 20px;
    border-top: 1px solid """ + BORDER + """;
}
footer a { color: """ + ACCENT_CYAN + """; text-decoration: none; }

/* ── Section header ── */
.section-title {
    font-size: 14px;
    font-weight: 800;
    color: """ + TEXT_PRIMARY + """;
    margin: 8px 0 12px;
    letter-spacing: 0.5px;
}
.section-title span {
    font-size: 11px;
    font-weight: 400;
    color: """ + TEXT_SECONDARY + """;
}

/* ── Responsive ── */
@media (max-width: 400px) {
    body { padding: 16px 12px 32px; }
    .team-name { font-size: 15px; }
}

/* ── Empty state ── */
.empty-state {
    text-align: center;
    padding: 48px 24px;
    color: """ + TEXT_DIM + """;
}
.empty-state h3 {
    font-size: 18px;
    color: """ + TEXT_SECONDARY + """;
    margin-bottom: 8px;
}
"""

def render_match_card(match, snapshot, featured=False):
    m_id, m_date, home, home_zh, away, away_zh, comp, stage = match

    h_name = home_zh or home
    a_name = away_zh or away

    try:
        dt = datetime.fromisoformat(str(m_date).replace("Z", ""))
        date_str = dt.strftime("%m/%d %H:%M")
    except:
        date_str = str(m_date)[:16]

    # Competition badge
    is_wc = "World Cup" in comp
    if is_wc:
        comp_short = "🏆 WC26"
    elif "Champions League" in comp:
        comp_short = "⭐ 欧冠"
    elif "Premier League" in comp:
        comp_short = "英超"
    elif "Ligue 1" in comp:
        comp_short = "法甲"
    elif "Serie A" in comp:
        comp_short = "意甲"
    elif "Primera" in comp:
        comp_short = "西甲"
    elif "Bundesliga" in comp:
        comp_short = "德甲"
    else:
        comp_short = comp[:20]

    card_class = "match-card featured" if featured else "match-card"

    if not snapshot:
        return f"""
    <div class="{card_class}" style="opacity:0.45;">
        <div class="match-card-top">
            <span class="match-comp">{comp_short}</span>
            <span class="match-time">{date_str}</span>
        </div>
        <div class="match-teams">
            <span class="team-name" style="color:{TEXT_DIM};">{h_name}</span>
            <span class="team-vs">vs</span>
            <span class="team-name" style="color:{TEXT_DIM};text-align:right;">{a_name}</span>
        </div>
        <div class="match-xg" style="color:{TEXT_DIM};">预测待生成</div>
    </div>"""

    probs = snapshot.get("adjusted_probs") or snapshot.get("baseline_probs")
    xg = snapshot.get("expected_goals")
    top3 = snapshot.get("top_scores")
    elo = snapshot.get("elo_ratings")
    conf = snapshot.get("confidence", "low")

    if not probs:
        return f'<div class="{card_class}" style="opacity:0.5;"><div class="match-xg" style="color:{TEXT_DIM};">数据不可用</div></div>'

    conf_class = f"badge-{conf}" if conf in ("high","medium","low") else "badge-low"
    conf_text = {"high":"高置信度","medium":"中置信度","low":"低置信度"}.get(conf, conf)

    # Elo gap
    elo_html = ""
    if elo and elo.get("gap") is not None:
        gap = elo["gap"]
        if abs(gap) > 0:
            elo_dir = "↑" if gap > 0 else "↓"
            elo_color = HOME_COLOR if gap > 0 else AWAY_COLOR
            elo_html = f'<span style="color:{elo_color};font-size:10px;margin-left:6px;">Elo{elo_dir}{abs(gap):.0f}</span>'

    # Featured badge
    featured_html = '<div class="badge-featured">🏆 焦点赛事</div>' if featured else ''

    # Top 3
    top3_html = ""
    if top3:
        chips = []
        for s in top3[:3]:
            chips.append(f'<span class="score-chip"><span class="score">{s["score"]}</span> <span class="pct">{s["prob"]*100:.1f}%</span></span>')
        top3_html = '<div class="top-scores">' + "".join(chips) + "</div>"

    return f"""
    <div class="{card_class}">
        {featured_html}
        <div class="match-card-top">
            <span class="match-comp">{comp_short}{' · '+stage if stage and 'Matchday' in str(stage) else ''}{elo_html}</span>
            <span class="match-time" style="display:flex;align-items:center;gap:6px;">{date_str}<span class="badge {conf_class}">{conf_text}</span></span>
        </div>
        <div class="match-teams">
            <span class="team-name">{h_name}</span>
            <span class="team-vs">vs</span>
            <span class="team-name" style="text-align:right;">{a_name}</span>
        </div>
        <div class="match-xg">
            预期进球 <span>{xg["home"]:.2f}</span> — <span>{xg["away"]:.2f}</span>
        </div>
        <div class="prob-row">
            <span class="prob-label" style="color:{HOME_COLOR};">主</span>
            <span class="prob-value" style="color:{HOME_COLOR};">{probs["home"]*100:.1f}%</span>
            <div class="prob-track"><div class="prob-fill home" style="width:{probs["home"]*100:.2f}%;"></div></div>
        </div>
        <div class="prob-row">
            <span class="prob-label" style="color:{DRAW_COLOR};">平</span>
            <span class="prob-value" style="color:{DRAW_COLOR};">{probs["draw"]*100:.1f}%</span>
            <div class="prob-track"><div class="prob-fill draw" style="width:{probs["draw"]*100:.2f}%;"></div></div>
        </div>
        <div class="prob-row">
            <span class="prob-label" style="color:{AWAY_COLOR};">客</span>
            <span class="prob-value" style="color:{AWAY_COLOR};">{probs["away"]*100:.1f}%</span>
            <div class="prob-track"><div class="prob-fill away" style="width:{probs["away"]*100:.2f}%;"></div></div>
        </div>
        {top3_html}
    </div>"""

def render_countdown(target_date, label):
    """Render countdown to target date."""
    days_left = (target_date - date.today()).days
    if days_left < 0:
        return ""
    return f"""
    <div class="countdown">
        <div class="countdown-title">{label}</div>
        <div class="countdown-timer">{days_left}</div>
        <div class="countdown-small">天</div>
    </div>"""

# ── Main ─────────────────────────────────────────────────────────────────────

def generate(days=14):
    conn = get_db()
    matches = fetch_upcoming_matches(conn, days)

    # Determine mode
    today = date.today()
    wc_start = date(2026, 6, 11)
    is_wc_mode = today >= wc_start

    # Enrich with snapshots
    enriched = []
    for m in matches:
        snap = get_latest_snapshot(conn, m[0])
        enriched.append((m, snap))

    conn.close()

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M UTC")

    # ── Build HTML ──
    html = [f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0">
<meta name="description" content="WC26 Predict — 2026世界杯足球预测 · 纯统计模型 · 不含博彩">
<meta name="theme-color" content="{BG}">
<title>WC26 Predict — 2026世界杯预测</title>
<style>{CSS}</style>
</head>
<body>
<header>
    <div class="header-logo">WC26 PREDICT</div>
    <div class="header-sub">足球赛前统计分析 · 三层模型融合预测</div>
</header>"""]

    # ── Preview mode (before WC) ──
    if not is_wc_mode:
        html.append(render_countdown(wc_start, "距离世界杯开幕"))
        html.append(f'<div class="mode-badge mode-preview">预览模式</div>')

        # Find featured matches (those with predictions, sorted by importance)
        featured = [(m, s) for m, s in enriched if s is not None]
        # Sort: CL final > WC > others
        def sort_key(item):
            m, s = item
            comp = m[6]
            if "Champions League" in comp and "FINAL" in (m[7] or ""):
                return 0
            if "World Cup" in comp:
                return 1
            return 2
        featured.sort(key=sort_key)

        if featured:
            html.append(f'<div class="section-title">聚焦赛事 <span>· 已生成预测</span></div>')
            for m, s in featured[:5]:  # max 5 featured
                is_featured = sort_key((m, s)) <= 1
                html.append(render_match_card(m, s, featured=is_featured))

        # Upcoming WC matches (placeholder)
        wc_matches = [(m, s) for m, s in enriched if "World Cup" in m[6]]
        if wc_matches:
            first_wc = wc_matches[0]
            html.append(f'<div class="section-title">世界杯赛程预览 <span>· {len(wc_matches)} 场待预测</span></div>')
            # Show first 4 WC matches as preview
            for m, s in wc_matches[:4]:
                html.append(render_match_card(m, s))
            if len(wc_matches) > 4:
                html.append(f'<div style="text-align:center;padding:12px;color:{TEXT_DIM};font-size:12px;">还有 {len(wc_matches) - 4} 场比赛 · 开幕后每日更新</div>')

        # Other upcoming (collapsed hint)
        other = [(m, s) for m, s in enriched if "World Cup" not in m[6] and s is None and sort_key((m, s)) > 1]
        if not featured:
            html.append(f'<div class="empty-state"><h3>暂无预测数据</h3><p>运行 snapshot.py 生成预测后刷新页面</p></div>')

    # ── World Cup mode ──
    else:
        html.append(f'<div class="mode-badge mode-live">世界杯模式</div>')
        # Group by date
        by_date = defaultdict(list)
        for m, s in enriched:
            by_date[str(m[1])[:10]].append((m, s))

        for dk in sorted(by_date.keys()):
            dt = datetime.fromisoformat(dk)
            date_display = dt.strftime("%m月%d日")
            weekday = ["周一","周二","周三","周四","周五","周六","周日"][dt.weekday()]
            html.append(f'<div class="date-header">{date_display} {weekday}</div>')

            for m, s in by_date[dk]:
                is_wc = "World Cup" in m[6]
                html.append(render_match_card(m, s, featured=is_wc))

    # ── Footer ──
    match_count = len([1 for m, s in enriched if s is not None])
    total = len(enriched)
    html.append(f"""
<footer>
    <p>生成时间 {now_str} · {match_count}/{total} 场有预测数据</p>
    <p>Dixon-Coles 泊松 + Tabular Enhancer + κ-Elo 三层融合</p>
    <p style="margin-top:4px;">数据: football-data.org · StatsBomb · Open-Meteo</p>
    <p style="margin-top:10px;font-size:10px;color:{TEXT_DIM};">个人统计工具 · 不含博彩建议 · 不展示赔率数字</p>
</footer>
</body>
</html>""")

    result = "\n".join(html)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(result)

    fsize = OUTPUT_FILE.stat().st_size
    print(f"✅ HTML 已生成: {OUTPUT_FILE} ({fsize:,} bytes)")
    print(f"   模式: {'世界杯' if is_wc_mode else '预览'} · {match_count}/{total} 场有预测")
    return OUTPUT_FILE

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=14)
    args = p.parse_args()
    generate(args.days)
