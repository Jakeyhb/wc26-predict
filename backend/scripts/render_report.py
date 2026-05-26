#!/usr/bin/env python3
"""Render prediction result to Markdown report.
Takes fast_predict JSON output or result dict, produces readable Markdown.
Target: <10s per report.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))



def render_report(result: dict, run_type: str = "fast_predict") -> str:
    """Convert a prediction result dict into a Markdown report."""

    home = result["home_team"]
    away = result["away_team"]
    comp = result.get("competition", "Unknown")
    elo = result.get("elo", {})
    top3 = result.get("top3_scores", [])

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [
        f"# Match Report: {home} vs {away}",
        "",
        f"> 生成时间：{now}  |  赛事：{comp}  |  run_type：{run_type}",
        "",
        "---",
        "",
        "## 1. 比赛信息",
        "",
        f"- 比赛：{home} vs {away}",
        f"- 赛事：{comp}",
        f"- 报告类型：{run_type}",
        f"- 是否中立场：{'是' if result.get('is_neutral') else '否'}",
        "",
        "---",
        "",
        "## 2. 概率概览",
        "",
        "| 来源 | 主胜 | 平局 | 客胜 |",
        "|---|---:|---:|---:|",
        f"| Baseline Model | **{result['home_win_prob']*100:.1f}%** | {result['draw_prob']*100:.1f}% | {result['away_win_prob']*100:.1f}% |",
    ]

    # Market baseline placeholder
    market = result.get("market_probs")
    if market:
        lines.append(f"| Market Baseline | {market['home']*100:.1f}% | {market['draw']*100:.1f}% | {market['away']*100:.1f}% |")
    else:
        lines.append("| Market Baseline | — | — | — |")

    lines.append(f"| Adjusted Final | **{result['home_win_prob']*100:.1f}%** | {result['draw_prob']*100:.1f}% | {result['away_win_prob']*100:.1f}% |")

    lines += [
        "",
        "---",
        "",
        "## 3. 期望进球与比分倾向",
        "",
        f"- xG：{home} **{result.get('home_xg', 0):.2f}** — **{result.get('away_xg', 0):.2f}** {away}",
    ]

    if top3:
        lines += ["", "### Top 3 比分", ""]
        for s in top3:
            lines.append(f"- {s['score']}（{s['prob']*100:.1f}%）")

    lines += [
        "",
        "---",
        "",
        "## 4. Elo 评分",
        "",
        f"- {home}：**{elo.get('home_elo', 0):.0f}**",
        f"- {away}：**{elo.get('away_elo', 0):.0f}**",
        f"- 评分差：{elo.get('rating_gap', 0):+.0f}（K={elo.get('k_factor', 0):.0f}）",
        "",
        "---",
        "",
        "## 5. 管线参数",
    ]

    pipe = result.get("pipeline", {})
    if pipe:
        lines.append(f"- Dixon-Coles：{'收敛' if pipe.get('dc_converged') else '未收敛'}（NLL={pipe.get('dc_nll', 0):.2f}）")
        lines.append(f"- 训练数据：{pipe.get('training_rows', 0)} 场")
        lines.append(f"- Enhancer：{pipe.get('enhancer_rows', 0)} 行")
        lines.append(f"- Elo：{pipe.get('elo_matches', 0)} 场")

    lines += [
        "",
        "---",
        "",
        "## 6. 缺失输入",
    ]

    missing = result.get("missing_inputs", [])
    if missing:
        for item in missing:
            lines.append(f"- ⚠️ {item}")
    else:
        lines.append("- （未记录）")

    lines += [
        "",
        "---",
        "",
        "## 7. 预测可信度",
        "",
        f"- 校准：监控模式（回测样本不足，未启用）",
        f"- 置信度：{result.get('confidence', 'low')}",
        f"- 本预测仅基于历史统计数据，未纳入伤病/首发/动机等实时因素",
    ]

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render prediction to Markdown")
    parser.add_argument("--input", help="JSON file from fast_predict.py")
    parser.add_argument("--output", help="Output Markdown file")
    parser.add_argument("--run-type", default="fast_predict")
    args = parser.parse_args()

    if args.input:
        with open(args.input) as f:
            result = json.load(f)
    else:
        result = json.loads(sys.stdin.read())

    md = render_report(result, args.run_type)

    if args.output:
        Path(args.output).write_text(md, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(md)


if __name__ == "__main__":
    main()
