#!/usr/bin/env python3
"""Extract structured injury/lineup signals from RSS feeds using DeepSeek.

Fixes news_signals=0 by scraping BBC/Sky Sports/ESPN RSS headlines,
then asking DeepSeek to extract structured signals (injuries, returns,
suspensions, rotation hints, lineup info).

Usage:
    python scripts/news_signal_extractor.py \\
        --home "Paris Saint-Germain FC" --away "Arsenal FC"

Requires: LLM_API_KEY in environment.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

RSS_FEEDS = {
    "sky_sports": "https://www.skysports.com/rss/12040",
    "bbc_football": "https://feeds.bbci.co.uk/sport/football/rss.xml",
    "espn_soccer": "https://www.espn.com/espn/rss/soccer/news",
}

LLM_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-v4-pro")


async def fetch_rss_headlines(home_team: str, away_team: str, hours_back: int = 72) -> list[dict]:
    """Fetch recent headlines mentioning either team from RSS feeds."""
    try:
        import feedparser
    except ImportError:
        print("⚠️  feedparser not installed. Install with: pip install feedparser")
        return []

    headlines = []
    for source, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = entry.get("title", "")
                summary = entry.get("summary", "")

                # Check if headline mentions either team
                home_match = any(part.lower() in title.lower() for part in home_team.split())
                away_match = any(part.lower() in title.lower() for part in away_team.split())

                if home_match or away_match:
                    published = entry.get("published", "")
                    headlines.append({
                        "title": title,
                        "summary": summary[:300],
                        "published": published,
                        "source": source,
                        "url": entry.get("link", ""),
                    })
        except Exception as e:
            print(f"  ⚠️  {source} fetch error: {e}")

    print(f"  从 RSS 获取 {len(headlines)} 条相关标题")
    return headlines


async def extract_signals_llm(headlines: list[dict], home_team: str, away_team: str) -> list[dict]:
    """Use DeepSeek to extract structured signals from headlines."""
    if not headlines:
        return []
    if not LLM_KEY:
        print("  ⚠️  LLM_API_KEY not set, skipping LLM extraction")
        return []

    import httpx

    prompt = f"""你是一名足球情报分析师。以下是关于 {home_team} vs {away_team} 的新闻标题和摘要。

提取所有与以下类别相关的信息，以 JSON 数组返回：
- INJURY: 球员受伤或缺阵
- RETURN: 伤愈复出
- SUSPENSION: 停赛
- ROTATION: 轮换暗示
- LINEUP: 首发阵容信息

每条记录包含：signal_type, team(球队名), player(球员名,可选), description(一句话), confidence(high/medium/low), source_headline(原标题)

只返回 JSON 数组，不要其他文字。如果没有相关信号，返回 []。

新闻内容：
{json.dumps(headlines[:20], ensure_ascii=False)}"""

    async with httpx.AsyncClient(timeout=45.0) as client:
        try:
            resp = await client.post(
                f"{LLM_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {LLM_KEY}"},
                json={
                    "model": LLM_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1500,
                    "temperature": 0.3,
                },
            )
            data = resp.json()
            content = data["choices"][0]["message"]["content"]

            # Parse JSON from response (may have markdown code fences)
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            signals = json.loads(content.strip())
            print(f"  LLM 提取 {len(signals)} 条信号")
            return signals
        except Exception as e:
            print(f"  ❌ LLM extraction failed: {e}")
            return []


def store_signals(signals: list[dict], home_team: str, away_team: str) -> int:
    """Store extracted signals into the manual_events table."""
    import sqlite3

    db_path = BACKEND_DIR / "data" / "local_stage2.db"
    conn = sqlite3.connect(str(db_path))

    stored = 0
    for sig in signals:
        try:
            conn.execute(
                """INSERT INTO manual_events
                   (id, event_type, team_name, player_name, severity, confidence,
                    source_name, source_url, note, status, created_by, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 'auto-rss', ?, ?)""",
                (
                    f"rss_{sig.get('signal_type', '?')}_{int(datetime.now(timezone.utc).timestamp())}_{stored}",
                    sig.get("signal_type", "OTHER").upper(),
                    sig.get("team", ""),
                    sig.get("player", ""),
                    "medium",
                    {"high": 0.90, "medium": 0.70, "low": 0.50}.get(
                        sig.get("confidence", "medium"), 0.70
                    ),
                    sig.get("source_headline", "RSS Auto")[:100],
                    sig.get("url", ""),
                    sig.get("description", "")[:500],
                    datetime.now(timezone.utc).isoformat(),
                    (datetime.now(timezone.utc).isoformat()),
                ),
            )
            stored += 1
        except Exception as e:
            print(f"  ⚠️  Failed to store signal: {e}")

    conn.commit()
    conn.close()
    return stored


async def main():
    parser = argparse.ArgumentParser(description="Extract news signals from RSS")
    parser.add_argument("--home", required=True)
    parser.add_argument("--away", required=True)
    args = parser.parse_args()

    print(f"\n🔍 扫描新闻信号: {args.home} vs {args.away}")
    print("=" * 50)

    headlines = await fetch_rss_headlines(args.home, args.away)
    signals = await extract_signals_llm(headlines, args.home, args.away)

    if signals:
        stored = store_signals(signals, args.home, args.away)
        print(f"\n✅ 已存储 {stored} 条新闻信号")
        for s in signals:
            print(f"   [{s.get('signal_type', '?')}] {s.get('description', '?')[:80]}")
    else:
        print("\n⚠️  本次未提取到有效信号")

    print(f"\n共 {len(signals)} 条信号，已写入 manual_events 表")


if __name__ == "__main__":
    asyncio.run(main())
