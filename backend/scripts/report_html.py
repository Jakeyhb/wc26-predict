"""report_html.py - Minimal editorial HTML for WC26 matchday reports.

Design read (taste-skill / minimalist-skill):
  Editorial data report for research readers, warm monochrome palette,
  native CSS, no gradients, no neon, no emoji, hyphen not em-dash.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# WC26 国家队中文名（DB name_zh 为空时的兜底）
TEAM_NAME_ZH: dict[str, str] = {
    "Curacao": "库拉索",
    "Ivory Coast": "科特迪瓦",
    "Ecuador": "厄瓜多尔",
    "Germany": "德国",
    "Japan": "日本",
    "Sweden": "瑞典",
    "Tunisia": "突尼斯",
    "Netherlands": "荷兰",
    "Turkey": "土耳其",
    "United States": "美国",
    "Paraguay": "巴拉圭",
    "Australia": "澳大利亚",
}

_db_team_zh: dict[str, str] | None = None


def load_team_zh_from_db(db_path: Path) -> dict[str, str]:
    """Load name -> name_zh from SQLite when available."""
    import sqlite3

    mapping: dict[str, str] = {}
    if not db_path.exists():
        return mapping
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name, name_zh FROM teams WHERE name_zh IS NOT NULL AND name_zh != ''")
        for name, name_zh in cur.fetchall():
            mapping[name] = name_zh
    finally:
        conn.close()
    return mapping


def team_display(name: str, *, db_path: Path | None = None) -> str:
    """Return Chinese team name for display; fallback to English."""
    global _db_team_zh
    if db_path is not None:
        _db_team_zh = load_team_zh_from_db(db_path)
    if _db_team_zh and name in _db_team_zh:
        return _db_team_zh[name]
    return TEAM_NAME_ZH.get(name, name)


def matchup_label(home: str, away: str, *, db_path: Path | None = None) -> str:
    return f"{team_display(home, db_path=db_path)} 对 {team_display(away, db_path=db_path)}"


@dataclass
class MatchAnalysis:
    home: str
    away: str
    kickoff_cst: str
    venue: str
    match_id: str = ""
    match_date_utc: str = ""
    quant: dict[str, Any] = field(default_factory=dict)
    market: dict[str, Any] | None = None
    market_note: str = ""
    analyst: str = ""
    critic: str = ""
    synthesis: str = ""
    errors: list[str] = field(default_factory=list)


def analysis_to_dict(ma: MatchAnalysis) -> dict[str, Any]:
    return asdict(ma)


def dict_to_analysis(data: dict[str, Any]) -> MatchAnalysis:
    return MatchAnalysis(**data)


def save_analyses_json(analyses: list[MatchAnalysis], path: Path) -> None:
    path.write_text(
        json.dumps([analysis_to_dict(a) for a in analyses], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_analyses_json(path: Path) -> list[MatchAnalysis]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [dict_to_analysis(item) for item in raw]


def _pick_favorite(q: dict) -> tuple[str, float]:
    opts = [
        ("主胜", q["home_win_prob"]),
        ("平局", q["draw_prob"]),
        ("客胜", q["away_win_prob"]),
    ]
    return max(opts, key=lambda x: x[1])


def _format_scores(scores: list[dict]) -> str:
    if not scores:
        return "-"
    return " / ".join(f"{s['score']} {s['prob']:.0%}" for s in scores[:3])


def _format_top_score(scores: list[dict]) -> str:
    """Compact top score for summary table."""
    if not scores:
        return "-"
    top = scores[0]
    return f"{top['score']} ({top['prob']:.0%})"


def _text_block(text: str) -> str:
    if not text:
        return "<p class=\"empty\">未生成</p>"
    paras = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
    return "".join(f"<p>{html.escape(p)}</p>" for p in paras)


def _prob_table(
    home: str,
    away: str,
    qh: float,
    qd: float,
    qa: float,
    market: dict[str, Any] | None,
) -> str:
    rows = [
        ("模型", home, f"{qh:.1%}", "平", f"{qd:.1%}", away, f"{qa:.1%}"),
    ]
    if market:
        rows.append(
            (
                "市场",
                home,
                f"{market.get('home_prob', 0):.1%}",
                "平",
                f"{market.get('draw_prob', 0):.1%}",
                away,
                f"{market.get('away_prob', 0):.1%}",
            )
        )
    body = ""
    for label, h_label, h_val, d_label, d_val, a_label, a_val in rows:
        body += f"""
        <tr>
          <th scope="row">{html.escape(label)}</th>
          <td>{html.escape(h_label)} {h_val}</td>
          <td>{d_label} {d_val}</td>
          <td>{html.escape(a_label)} {a_val}</td>
        </tr>"""
    return f"""
    <table class="probs">
      <thead>
        <tr><th></th><th>主胜</th><th>平局</th><th>客胜</th></tr>
      </thead>
      <tbody>{body}
      </tbody>
    </table>"""


def render_report(
    analyses: list[MatchAnalysis],
    report_date: str,
    *,
    db_path: Path | None = None,
) -> str:
    """Render a minimal taste-skill styled HTML report."""
    if db_path is not None:
        global _db_team_zh
        _db_team_zh = load_team_zh_from_db(db_path)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    summary_rows = ""
    for ma in analyses:
        q = ma.quant
        fav, fav_p = _pick_favorite(q)
        home_zh = team_display(ma.home, db_path=db_path)
        away_zh = team_display(ma.away, db_path=db_path)
        top_score = _format_top_score(q.get("top_scores", []))
        summary_rows += f"""
        <tr>
          <td>{html.escape(ma.kickoff_cst.split()[1] if " " in ma.kickoff_cst else ma.kickoff_cst)}</td>
          <td>{html.escape(home_zh)} 对 {html.escape(away_zh)}</td>
          <td>{fav} {fav_p:.1%}</td>
          <td>{html.escape(top_score)}</td>
          <td>{q['home_xg']:.2f} - {q['away_xg']:.2f}</td>
        </tr>"""

    articles = ""
    for i, ma in enumerate(analyses, 1):
        q = ma.quant
        fav, fav_p = _pick_favorite(q)
        scores = _format_scores(q.get("top_scores", []))
        home_zh = team_display(ma.home, db_path=db_path)
        away_zh = team_display(ma.away, db_path=db_path)
        prob_table = _prob_table(
            home_zh,
            away_zh,
            q["home_win_prob"],
            q["draw_prob"],
            q["away_win_prob"],
            ma.market,
        )
        market_note = (
            f"<p class=\"note\">{html.escape(ma.market_note)}</p>" if ma.market_note else ""
        )
        articles += f"""
    <article class="match" id="m{i}">
      <header class="match-head">
        <p class="index">第 {i:02d} 场</p>
        <h2>{html.escape(home_zh)} <span class="sep">对</span> {html.escape(away_zh)}</h2>
        <p class="meta">{html.escape(ma.kickoff_cst)} · {html.escape(ma.venue)} · 未开始</p>
        <p class="pick">模型倾向: {html.escape(fav)} {fav_p:.1%}</p>
      </header>

      {prob_table}
      {market_note}
      <p class="stats">预期进球(xG) {q['home_xg']:.2f} - {q['away_xg']:.2f} · 最可能比分 {html.escape(scores)}</p>

      <section class="verdict">
        <h3>综合结论</h3>
        <div class="body">{_text_block(ma.synthesis)}</div>
      </section>

      <details class="fold">
        <summary>战术分析</summary>
        <div class="body">{_text_block(ma.analyst)}</div>
      </details>

      <details class="fold">
        <summary>批判审查</summary>
        <div class="body">{_text_block(ma.critic)}</div>
      </details>
    </article>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>WC26 Predict · {html.escape(report_date)} 比赛日报告</title>
  <style>
    :root {{
      --bg: #F7F6F3;
      --surface: #FFFFFF;
      --text: #2F3437;
      --muted: #787774;
      --border: #EAEAEA;
      --accent: #346538;
      --accent-bg: #EDF3EC;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: "SF Pro Display", "Helvetica Neue", "PingFang SC", sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.65;
      padding: 48px 20px 80px;
    }}
    .wrap {{ max-width: 720px; margin: 0 auto; }}
    .masthead {{ margin-bottom: 40px; padding-bottom: 24px; border-bottom: 1px solid var(--border); }}
    .masthead h1 {{
      font-family: "Newsreader", "Songti SC", Georgia, serif;
      font-size: 1.75rem;
      font-weight: 600;
      letter-spacing: -0.02em;
      line-height: 1.2;
    }}
    .masthead .sub {{ color: var(--muted); font-size: 0.875rem; margin-top: 8px; }}
    .disclaimer {{
      font-size: 0.8125rem;
      color: var(--muted);
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px 16px;
      margin-bottom: 36px;
    }}
    .summary-note {{
      font-size: 0.75rem;
      color: var(--muted);
      margin-top: 10px;
      line-height: 1.5;
    }}
    .summary h2 {{
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      margin-bottom: 12px;
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.875rem; background: var(--surface); }}
    th, td {{ border: 1px solid var(--border); padding: 10px 12px; text-align: left; }}
    th {{ font-weight: 600; background: #FAFAF9; }}
    .match {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 28px 24px;
      margin-bottom: 24px;
    }}
    .match-head {{ margin-bottom: 20px; }}
    .index {{ font-size: 0.6875rem; text-transform: uppercase; letter-spacing: 0.1em; color: var(--muted); }}
    .match h2 {{
      font-family: "Newsreader", "Songti SC", Georgia, serif;
      font-size: 1.375rem;
      font-weight: 600;
      letter-spacing: -0.02em;
      margin: 6px 0 4px;
    }}
    .sep {{ color: var(--muted); font-weight: 400; }}
    .meta, .stats, .note {{ font-size: 0.8125rem; color: var(--muted); }}
    .pick {{
      display: inline-block;
      margin-top: 10px;
      font-size: 0.8125rem;
      font-weight: 600;
      color: var(--accent);
      background: var(--accent-bg);
      padding: 4px 10px;
      border-radius: 4px;
    }}
    .probs {{ margin: 16px 0 8px; font-size: 0.8125rem; }}
    .probs th[scope="row"] {{ width: 56px; color: var(--muted); font-weight: 500; }}
    .verdict {{
      margin-top: 20px;
      padding-top: 16px;
      border-top: 1px solid var(--border);
    }}
    .verdict h3, .fold summary {{
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--muted);
      margin-bottom: 10px;
    }}
    .body p {{ font-size: 0.9375rem; margin-bottom: 10px; }}
    .body p:last-child {{ margin-bottom: 0; }}
    .empty {{ color: var(--muted); font-style: italic; }}
    .fold {{ margin-top: 12px; border-top: 1px solid var(--border); padding-top: 12px; }}
    .fold summary {{ cursor: pointer; list-style: none; }}
    .fold summary::-webkit-details-marker {{ display: none; }}
    .fold[open] summary {{ margin-bottom: 10px; }}
    footer {{
      margin-top: 48px;
      padding-top: 20px;
      border-top: 1px solid var(--border);
      font-size: 0.75rem;
      color: var(--muted);
      text-align: center;
    }}
    @media (max-width: 560px) {{
      .summary table {{ font-size: 0.75rem; }}
      th, td {{ padding: 8px; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header class="masthead">
      <h1>WC26 Predict 比赛日报告</h1>
      <p class="sub">{html.escape(report_date)} · {len(analyses)} 场 · 生成于 {now}</p>
    </header>

    <p class="disclaimer">
      本报告由 WC26 Predict 研究系统自动生成，仅供数据分析参考，不构成任何投注建议。
    </p>

    <section class="summary">
      <h2>一览</h2>
      <table>
        <thead>
          <tr><th>开球</th><th>对阵</th><th>模型倾向</th><th>最可能比分</th><th>预期进球(xG)</th></tr>
        </thead>
        <tbody>{summary_rows}
        </tbody>
      </table>
      <p class="summary-note">
        预期进球(xG)：根据射门位置与质量估算的进球期望值，主-客格式，数值越高表示该队进攻威胁越大。
      </p>
    </section>

    {articles}

    <footer>WC26 Predict · Multi-Agent Report · {now}</footer>
  </div>
</body>
</html>"""


def extract_analyses_from_html(html_path: Path) -> list[MatchAnalysis]:
    """Best-effort parse of legacy verbose HTML report into MatchAnalysis list."""
    text = html_path.read_text(encoding="utf-8")
    sections = re.split(r'<section class="match-card"', text)[1:]
    out: list[MatchAnalysis] = []

    for block in sections:
        home_m = re.search(r"<h2>(.+?) <span class=\"vs\">vs</span> (.+?)</h2>", block)
        meta_m = re.search(r"<p class=\"meta\">(.+?) CST · (.+?) ·", block)
        fav_m = re.search(r'class="fav-badge">(.+?)</div>', block)
        xg_m = re.search(r"xG: ([\d.]+) — ([\d.]+) · 最可能比分: (.+?)</p>", block)
        probs = re.findall(r'class="prob-val">([\d.]+%)</span>', block)

        def agent_text(role: str) -> str:
            pat = rf'<h3>R\d · {role}.*?</h3>\s*<div class="agent-text">(.*?)</div>'
            m = re.search(pat, block, re.DOTALL)
            if not m:
                return ""
            raw = m.group(1)
            paras = re.findall(r"<p>(.*?)</p>", raw, re.DOTALL)
            return "\n".join(html.unescape(p.strip()) for p in paras if p.strip())

        if not home_m or len(probs) < 3:
            continue

        home, away = home_m.group(1), home_m.group(2)
        kickoff = meta_m.group(1) + " CST" if meta_m else ""
        venue = meta_m.group(2) if meta_m else ""

        def pct(s: str) -> float:
            return float(s.rstrip("%")) / 100

        qh, qd, qa = pct(probs[0]), pct(probs[1]), pct(probs[2])
        market = None
        market_note = ""
        if len(probs) >= 6:
            market = {
                "home_prob": pct(probs[3]),
                "draw_prob": pct(probs[4]),
                "away_prob": pct(probs[5]),
            }
        note_m = re.search(r"<h3>R2 · 市场共识</h3>\s*<p>(.+?)</p>", block)
        if note_m:
            market_note = html.unescape(note_m.group(1))

        scores_raw = xg_m.group(3) if xg_m else ""
        top_scores = []
        for sm in re.finditer(r"([\d:]+)\(([\d.]+%)\)", scores_raw):
            top_scores.append({"score": sm.group(1), "prob": pct(sm.group(2))})

        ma = MatchAnalysis(
            home=home,
            away=away,
            kickoff_cst=kickoff,
            venue=venue,
            quant={
                "home_win_prob": qh,
                "draw_prob": qd,
                "away_win_prob": qa,
                "home_xg": float(xg_m.group(1)) if xg_m else 0,
                "away_xg": float(xg_m.group(2)) if xg_m else 0,
                "top_scores": top_scores,
            },
            market=market,
            market_note=market_note,
            analyst=agent_text("战术分析师 Agent"),
            critic=agent_text("批判审查 Agent"),
            synthesis=agent_text("综合裁决 Agent"),
        )
        out.append(ma)

    return out
