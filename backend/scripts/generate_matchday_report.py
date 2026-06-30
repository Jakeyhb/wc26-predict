#!/usr/bin/env python3
"""generate_matchday_report.py — Multi-round agent matchday prediction report.

Runs 5-round analysis per match:
  R1 Quantitative model fusion (PredictionPipeline)
  R2 Market consensus comparison
  R3 Analyst agent (LLM tactical deep-dive)
  R4 Critic agent (LLM risk/challenge review)
  R5 Synthesizer agent (LLM final consensus)

Usage:
    python scripts/generate_matchday_report.py
    python scripts/generate_matchday_report.py --output reports/wc26_2026-06-26.html
    python scripts/generate_matchday_report.py --render-only
    python scripts/generate_matchday_report.py --from-html reports/wc26_2026-06-26.verbose.html
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sqlite3
import sys

# Longer timeout for multi-agent LLM rounds (default 30s is too short)
os.environ.setdefault("LLM_TIMEOUT_SECONDS", "120")
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from report_html import (
    MatchAnalysis,
    extract_analyses_from_html,
    load_analyses_json,
    render_report,
    save_analyses_json,
)

DB_PATH = BACKEND_DIR / "data" / "local_stage2.db"
REPORTS_DIR = BACKEND_DIR / "reports"
COMPETITION = "FIFA World Cup 2026"

# User-facing kickoff times (CST / UTC+8) for 2026-06-26 matchday
MATCHDAY = [
    {"home": "Curacao", "away": "Ivory Coast", "kickoff_cst": "2026-06-26 04:00", "venue": "BC Place"},
    {"home": "Ecuador", "away": "Germany", "kickoff_cst": "2026-06-26 04:00", "venue": "MetLife Stadium"},
    {"home": "Japan", "away": "Sweden", "kickoff_cst": "2026-06-26 07:00", "venue": "AT&T Stadium, Arlington, TX"},
    {"home": "Tunisia", "away": "Netherlands", "kickoff_cst": "2026-06-26 07:00", "venue": "Arrowhead Stadium"},
    {"home": "Turkey", "away": "United States", "kickoff_cst": "2026-06-26 10:00", "venue": "MetLife Stadium"},
    {"home": "Paraguay", "away": "Australia", "kickoff_cst": "2026-06-26 10:00", "venue": "Levi's Stadium"},
]

def lookup_match_id(home: str, away: str) -> tuple[str, str]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT m.id, m.match_date
        FROM matches m
        JOIN teams ht ON m.home_team_id = ht.id
        JOIN teams at ON m.away_team_id = at.id
        WHERE ht.name = ? AND at.name = ? AND m.competition = ?
        ORDER BY m.match_date DESC LIMIT 1
        """,
        (home, away, COMPETITION),
    )
    row = cur.fetchone()
    conn.close()
    if row:
        return row["id"], row["match_date"]
    return "", ""


def run_quant_round(home: str, away: str, *, match_id: str, match_date: str, venue: str) -> dict[str, Any]:
    from app.services.prediction_pipeline import PredictionPipeline

    pipeline = PredictionPipeline.from_artifacts(mode="full")
    pred = pipeline.predict_sync(
        home,
        away,
        COMPETITION,
        is_neutral=True,
        match_id=match_id,
        match_date=match_date or None,
        venue=venue,
        save_snapshot=False,
        enable_market=False,
        enable_weather=False,
    )
    data = pred.to_dict()
    return {
        "home_win_prob": pred.home_win_prob,
        "draw_prob": pred.draw_prob,
        "away_win_prob": pred.away_win_prob,
        "home_xg": pred.home_xg,
        "away_xg": pred.away_xg,
        "top_scores": pred.top_scores,
        "components_used": list(pred.components_used),
        "component_probs": data.get("component_probs", {}),
        "fusion_graph": data.get("fusion_graph", {}),
        "market_probs": pred.market_probs,
        "market_applied": pred.market_applied,
        "divergence": pred.divergence,
        "source_status": {
            k: (v.to_dict() if hasattr(v, "to_dict") else v)
            for k, v in pred.source_status.items()
        },
        "risk_tags": list(pred.risk_tags),
        "degraded_reasons": data.get("degraded_reasons", []),
    }


def run_market_round(home: str, away: str, quant: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    market = quant.get("market_probs")
    if market:
        mh, md, ma = market.get("home_prob", 0), market.get("draw_prob", 0), market.get("away_prob", 0)
        qh, qd, qa = quant["home_win_prob"], quant["draw_prob"], quant["away_win_prob"]
        max_diff = max(abs(qh - mh), abs(qd - md), abs(qa - ma))
        note = f"模型与市场最大分歧 {max_diff:.1%}（来源: {market.get('provider', 'unknown')}）"
        if max_diff > 0.10:
            note += " — 显著分歧，需审慎解读"
        return market, note
    try:
        from app.services.market.sync_provider import fetch_market_consensus_sync

        fetched = fetch_market_consensus_sync(home, away, COMPETITION)
        if fetched:
            return fetched, "独立拉取市场共识成功"
    except Exception as exc:
        return None, f"市场数据不可用: {exc}"
    return None, "暂无市场赔率参考数据"


def _format_scores(scores: list[dict]) -> str:
    if not scores:
        return "暂无"
    return "、".join(f"{s['score']}({s['prob']:.1%})" for s in scores[:3])


def _format_components(component_probs: dict) -> str:
    lines = []
    for name, probs in component_probs.items():
        if isinstance(probs, dict) and "home" in probs:
            lines.append(
                f"  {name}: 主{probs['home']:.1%} / 平{probs.get('draw', 0):.1%} / 客{probs.get('away', 0):.1%}"
            )
    return "\n".join(lines) if lines else "  (组件概率未记录)"


def _build_context_block(ma: MatchAnalysis) -> str:
    q = ma.quant
    market_lines = "暂无市场数据"
    if ma.market:
        m = ma.market
        market_lines = (
            f"主胜 {m.get('home_prob', 0):.1%} | 平 {m.get('draw_prob', 0):.1%} | "
            f"客胜 {m.get('away_prob', 0):.1%} ({m.get('provider', 'unknown')})"
        )
    fg = q.get("fusion_graph", {})
    disagreement = fg.get("model_disagreement", {})
    max_diff = disagreement.get("max_home_diff", 0)
    return f"""比赛: {ma.home} vs {ma.away}
赛事: {COMPETITION} | 中立场地 | {ma.venue}
开球(北京时间): {ma.kickoff_cst}

【R1 量化模型融合】
主胜 {q['home_win_prob']:.1%} | 平局 {q['draw_prob']:.1%} | 客胜 {q['away_win_prob']:.1%}
xG: {ma.home} {q['home_xg']:.2f} vs {ma.away} {q['away_xg']:.2f}
最可能比分: {_format_scores(q.get('top_scores', []))}
使用组件: {', '.join(q.get('components_used', []))}
组件概率:
{_format_components(q.get('component_probs', {}))}
模型分歧度: {max_diff:.1%}

【R2 市场共识】
{market_lines}
{ma.market_note}

风险标签: {', '.join(q.get('risk_tags', [])) or '无'}
"""


async def run_llm_rounds(ma: MatchAnalysis) -> None:
    from app.services.llm.deepseek_client import DeepSeekClient

    client = DeepSeekClient()
    ctx = _build_context_block(ma)

    analyst_system = """你是 WC26 Predict 量化足球研究系统的「战术分析师 Agent」。
基于提供的多模型融合数据，撰写深度赛前战术分析（250-350字中文）。
规则: 数据驱动、不编造、不用博彩用语、标注不确定性。"""

    critic_system = """你是 WC26 Predict 的「批判审查 Agent」。
挑战分析师的隐含假设，找出模型遗漏因素和数据局限。
输出 180-280 字中文，语气审慎。"""

    synth_system = """你是 WC26 Predict 的「综合裁决 Agent」。
综合 R1-R4 意见给出最终赛前研判（220-320字中文）:
1. 核心结论（最可能结果 + 置信度: 高/中/低）
2. 支持论据（2-3条）
3. 主要风险（1-2条）
4. 模型局限性声明
不得使用博彩用语，不得承诺胜率。"""

    try:
        ma.analyst = await client.chat(
            system=analyst_system,
            user=f"请对以下比赛进行 R3 战术分析:\n\n{ctx}",
        )
    except Exception as exc:
        ma.errors.append(f"R3 Analyst: {exc}")

    critic_input = ctx
    if ma.analyst:
        critic_input += f"\n\n【R3 分析师输出摘要】\n{ma.analyst[:800]}"

    try:
        ma.critic = await client.chat(
            system=critic_system,
            user=f"请对以下比赛进行 R4 批判审查:\n\n{critic_input}",
        )
    except Exception as exc:
        ma.errors.append(f"R4 Critic: {exc}")

    synth_input = critic_input
    if ma.critic:
        synth_input += f"\n\n【R4 批判审查输出】\n{ma.critic[:600]}"

    try:
        ma.synthesis = await client.chat(
            system=synth_system,
            user=f"请给出 R5 综合裁决:\n\n{synth_input}",
        )
    except Exception as exc:
        ma.errors.append(f"R5 Synthesizer: {exc}")


async def run_all_llm_rounds(analyses: list[MatchAnalysis]) -> None:
    """Run LLM rounds for all matches in one event loop."""
    for ma in analyses:
        print(f"  [{ma.home} vs {ma.away}] R3-R5 LLM Agents...")
        await run_llm_rounds(ma)


def _pick_favorite(q: dict) -> tuple[str, float]:
    opts = [
        ("主胜", q["home_win_prob"]),
        ("平局", q["draw_prob"]),
        ("客胜", q["away_win_prob"]),
    ]
    return max(opts, key=lambda x: x[1])


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate multi-agent matchday HTML report")
    parser.add_argument(
        "--output",
        default=str(REPORTS_DIR / "wc26_2026-06-26.html"),
        help="Output HTML path",
    )
    parser.add_argument(
        "--date",
        default="2026-06-26",
        help="Report date label",
    )
    parser.add_argument(
        "--render-only",
        action="store_true",
        help="Re-render HTML from saved JSON (skip prediction + LLM)",
    )
    parser.add_argument(
        "--from-html",
        type=str,
        default="",
        help="Re-render from legacy verbose HTML (skip prediction + LLM)",
    )
    parser.add_argument(
        "--json",
        type=str,
        default="",
        help="JSON cache path (default: same stem as --output)",
    )
    args = parser.parse_args()
    output = Path(args.output)
    json_path = Path(args.json) if args.json else output.with_suffix(".json")
    report_date = args.date

    if args.from_html:
        print(f"  Re-rendering from legacy HTML: {args.from_html}")
        analyses = extract_analyses_from_html(Path(args.from_html))
        if not analyses:
            raise SystemExit("Could not parse any matches from HTML")
    elif args.render_only:
        if not json_path.exists():
            raise SystemExit(f"JSON cache not found: {json_path}")
        print(f"  Re-rendering from JSON: {json_path}")
        analyses = load_analyses_json(json_path)
    else:
        print("=" * 60)
        print("  WC26 Predict - Multi-Agent Matchday Report")
        print(f"  Matches: {len(MATCHDAY)}")
        print("=" * 60)

        analyses = []
        for spec in MATCHDAY:
            home, away = spec["home"], spec["away"]
            match_id, match_date = lookup_match_id(home, away)
            ma = MatchAnalysis(
                home=home,
                away=away,
                kickoff_cst=spec["kickoff_cst"],
                venue=spec["venue"],
                match_id=match_id,
                match_date_utc=match_date,
            )
            print(f"  [{home} vs {away}] R1 quant...")
            ma.quant = run_quant_round(
                home, away, match_id=match_id, match_date=match_date, venue=spec["venue"]
            )
            print(f"  [{home} vs {away}] R2 market...")
            ma.market, ma.market_note = run_market_round(home, away, ma.quant)
            analyses.append(ma)

        print("\n  Running LLM agents (R3-R5)...")
        asyncio.run(run_all_llm_rounds(analyses))

        for ma in analyses:
            fav, p = _pick_favorite(ma.quant)
            print(f"  ok {ma.home} vs {ma.away} -> {fav} {p:.1%}")

        save_analyses_json(analyses, json_path)
        print(f"  JSON saved: {json_path}")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    html_content = render_report(analyses, report_date, db_path=DB_PATH)
    output.write_text(html_content, encoding="utf-8")
    print(f"\n  Report saved: {output}")
    print(f"  Open: file://{output.resolve()}")


if __name__ == "__main__":
    main()
