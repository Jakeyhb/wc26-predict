#!/usr/bin/env python3
"""Batch prediction snapshots for upcoming matches.

Usage::

    # All upcoming matches (limit 10 for quick test)
    python scripts/batch_snapshot.py --limit 10

    # Specific competition only
    python scripts/batch_snapshot.py --competition "FIFA World Cup 2026" --limit 20

    # All upcoming World Cup matches
    python scripts/batch_snapshot.py --competition "FIFA World Cup 2026"

Output:
    backend/reports_batch/{timestamp}/
        summary.md           # Summary table + top picks
        {match_n}.md         # Individual reports (same as snapshot.py format)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = BACKEND_DIR / "reports_batch"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import sqlalchemy as sa
from app.database import AsyncSessionLocal


async def get_upcoming_matches(
    competition: str | None = None,
    limit: int = 0,
) -> list[dict]:
    """Fetch scheduled matches from DB, ordered by match_date."""
    async with AsyncSessionLocal() as db:
        sql = sa.text("""
            SELECT m.match_date, ht.name AS home_team, at.name AS away_team,
                   m.competition, m.is_neutral_venue
            FROM matches m
            JOIN teams ht ON m.home_team_id = ht.id
            JOIN teams at ON m.away_team_id = at.id
            WHERE m.status = 'scheduled'
              AND m.match_date > CURRENT_TIMESTAMP
            {}
            ORDER BY m.match_date
            {}
        """.format(
            "AND m.competition = :comp" if competition else "",
            "LIMIT :limit" if int(limit) > 0 else "",
        ))
        params = {}
        if competition:
            params["comp"] = competition
        if limit > 0:
            params["limit"] = limit

        result = await db.execute(sql, params)
        rows = result.fetchall()

    return [
        {
            "match_date": row[0] if isinstance(row[0], str) else str(row[0])[:16],
            "home_team": row[1],
            "away_team": row[2],
            "competition": row[3],
            "is_neutral": bool(row[4]),
        }
        for row in rows
    ]


async def run_batch(
    matches: list[dict],
    output_dir: Path,
) -> dict:
    """Run snapshots for all matches, write individual + summary reports."""
    from scripts.snapshot import run_snapshot, render_markdown
    from app.services.snapshot_store import save_prediction_snapshot

    results = []
    start_time = time.time()

    for i, match in enumerate(matches):
        t0 = time.time()
        home = match["home_team"]
        away = match["away_team"]
        comp = match["competition"]
        neutral = match["is_neutral"]
        match_date = match["match_date"]

        print(f"[{i+1}/{len(matches)}] {home} vs {away} ({comp}) … ", end="", flush=True)

        try:
            result = await run_snapshot(
                home, away,
                is_neutral=neutral,
                competition=comp,
                competition_weight=1.5 if "World Cup" in comp else 0.9,
            )
            elapsed = time.time() - t0
            print(f"OK ({elapsed:.1f}s)")

            # Write individual report
            safe_home = home.replace(" ", "_").replace("/", "-")
            safe_away = away.replace(" ", "_").replace("/", "-")
            report_path = output_dir / f"{i+1:03d}_{safe_home}_vs_{safe_away}.md"
            md = render_markdown(result)
            report_path.write_text(md, encoding="utf-8")

            # Save standardized snapshot
            try:
                result["meta"]["match_date"] = match_date
                result["meta"]["match_id"] = f"{home}_{away}_{match_date}"
                await save_prediction_snapshot(
                    result,
                    run_type="baseline_v0",
                    report_path=str(report_path),
                    report_markdown=md,
                )
            except Exception:
                pass  # Non-fatal

            results.append({
                "home_team": home,
                "away_team": away,
                "competition": comp,
                "match_date": match_date,
                "home_win": result["prediction"]["home_win_prob"],
                "draw": result["prediction"]["draw_prob"],
                "away_win": result["prediction"]["away_win_prob"],
                "home_xg": result["prediction"]["home_xg"],
                "away_xg": result["prediction"]["away_xg"],
                "elo_gap": result["elo"]["rating_gap"],
                "elapsed": elapsed,
                "ok": True,
            })

        except Exception as exc:
            elapsed = time.time() - t0
            print(f"FAIL ({elapsed:.1f}s): {exc}")
            results.append({
                "home_team": home,
                "away_team": away,
                "competition": comp,
                "match_date": match_date,
                "home_win": 0, "draw": 0, "away_win": 0,
                "home_xg": 0, "away_xg": 0,
                "elo_gap": 0,
                "elapsed": elapsed,
                "ok": False,
                "error": str(exc),
            })

    total_time = time.time() - start_time
    return {
        "total": len(matches),
        "ok": sum(1 for r in results if r["ok"]),
        "failed": sum(1 for r in results if not r["ok"]),
        "total_time": total_time,
        "matches": results,
    }


def render_summary(batch: dict, output_dir: Path) -> str:
    """Generate a summary markdown with table of all predictions."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    matches = batch["matches"]

    lines = [
        "# 批量预测汇总",
        "",
        f"> 生成时间：{now}  |  共 {batch['total']} 场  |  "
        f"成功 {batch['ok']}  |  失败 {batch['failed']}  |  "
        f"总耗时 {batch['total_time']:.0f}s",
        "",
        "---",
        "",
        "## 全部预测",
        "",
        "| # | 日期 | 主队 | 客队 | 联赛 | 主胜% | 平% | 客胜% | xG | Elo差 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]

    ok_matches = [m for m in matches if m["ok"]]
    for i, m in enumerate(ok_matches):
        winner = max(
            ("主", m["home_win"]),
            ("平", m["draw"]),
            ("客", m["away_win"]),
            key=lambda x: x[1],
        )
        emoji = "🏠" if winner[0] == "主" else ("🤝" if winner[0] == "平" else "✈️")
        lines.append(
            f"| {i+1} | {m['match_date']} | {m['home_team']} | {m['away_team']} | "
            f"{m['competition']} | "
            f"**{m['home_win']*100:.1f}%**{emoji if winner[0]=='主' else ''} | "
            f"{m['draw']*100:.1f}% | "
            f"**{m['away_win']*100:.1f}%**{emoji if winner[0]=='客' else ''} | "
            f"{m['home_xg']:.2f}-{m['away_xg']:.2f} | "
            f"{m['elo_gap']:+.0f} |"
        )

    if batch["failed"]:
        lines += ["", "## 失败", ""]
        failed = [m for m in matches if not m["ok"]]
        for m in failed:
            lines.append(f"- ❌ {m['home_team']} vs {m['away_team']}：{m.get('error', '未知错误')}")

    # Top confident picks
    if ok_matches:
        lines += [
            "",
            "---",
            "",
            "## 🔥 高置信度场次（主胜概率 > 60%）",
            "",
        ]
        confident = [m for m in ok_matches if m["home_win"] > 0.6]
        confident.sort(key=lambda x: x["home_win"], reverse=True)
        if confident:
            for m in confident[:10]:
                lines.append(
                    f"- **{m['home_team']}** vs {m['away_team']} — "
                    f"{m['home_win']*100:.1f}% 主胜 | "
                    f"xG {m['home_xg']:.2f}-{m['away_xg']:.2f} | "
                    f"Elo差 {m['elo_gap']:+.0f}"
                )
        else:
            lines.append("（无满足条件的场次）")

        lines += [
            "",
            "## 🚀 高比分场次（总 xG > 2.8）",
            "",
        ]
        high_xg = [m for m in ok_matches if m["home_xg"] + m["away_xg"] > 2.8]
        high_xg.sort(key=lambda x: x["home_xg"] + x["away_xg"], reverse=True)
        if high_xg:
            for m in high_xg[:10]:
                total = m["home_xg"] + m["away_xg"]
                lines.append(
                    f"- {m['home_team']} vs **{m['away_team']}** — "
                    f"总xG {total:.2f} | "
                    f"({m['home_xg']:.2f}-{m['away_xg']:.2f})"
                )
        else:
            lines.append("（无满足条件的场次）")

    md = "\n".join(lines)
    (output_dir / "summary.md").write_text(md, encoding="utf-8")
    return md


async def main(
    competition: str | None = None,
    limit: int = 0,
) -> None:
    print(f"🔍 查询待比赛…")
    matches = await get_upcoming_matches(competition=competition, limit=limit)
    if not matches:
        print("没有找到待比赛！")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    out_dir = REPORTS_DIR / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"📋 找到 {len(matches)} 场，输出到 {out_dir}")
    print()

    batch = await run_batch(matches, out_dir)

    print()
    print("=" * 60)
    print(f"✅ 完成：{batch['ok']}/{batch['total']} 成功  "
          f"总耗时 {batch['total_time']:.0f}s  "
          f"平均 {batch['total_time']/batch['total']:.1f}s/场")
    print()

    summary = render_summary(batch, out_dir)
    print(summary)

    # Write batch metadata
    meta = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": batch["ok"],
        "failed": batch["failed"],
        "total": batch["total"],
        "total_time_s": batch["total_time"],
        "competition_filter": competition,
    }
    (out_dir / "batch_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch prediction snapshots")
    parser.add_argument("--limit", type=int, default=0, help="Max matches (0=all)")
    parser.add_argument("--competition", default=None, help="Filter by competition name")
    args = parser.parse_args()
    asyncio.run(main(args.competition, args.limit))
