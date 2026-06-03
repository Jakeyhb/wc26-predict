"""Phase D-5: Extract signals from 5 selected articles using DeepSeek V4 Pro.

Hard constraints:
- review_status = PENDING always
- enters_model = false always
- source_url missing -> reject
- evidence_snippet missing -> reject
- confidence missing -> reject
- Never print full API key
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ["POSTGRES_URL"] = "sqlite+aiosqlite:///./data/local_stage2.db"
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

DB_PATH = PROJECT_ROOT / "data" / "local_stage2.db"

# The 5 selected article IDs
ARTICLE_IDS = [
    "48f4ab114f3a4552beaa14ae593a6fff",
    "6141539a9cec4c458eebb34ac73930fd",
    "80ccc73885c14ccfaf74bef6721fd054",
    "d7960fd785934637b21e04216a7a7fbe",
    "de02b7d605134afb85db2dadd104e772",
]

# Fields required in LLM output (source_url injected from article, not LLM)
REQUIRED_SIGNAL_FIELDS = [
    "evidence_snippet",
    "signal_type", "impact_direction", "confidence",
    "team_name", "source_reliability",
]

VALID_SIGNAL_TYPES = [
    "injury", "suspension", "lineup_change", "tactical_shift",
    "schedule_pressure", "travel_fatigue", "form_change",
    "manager_change", "morale_event", "weather_impact", "other",
]

VALID_IMPACT_DIRECTIONS = ["positive", "negative", "neutral", "unknown"]

EXTRACTION_PROMPT = """You are a football intelligence analyst. Extract structured signals from the news article below.

For each signal you find, fill in this JSON structure:
{
  "signals": [
    {
      "signal_type": "<injury|suspension|lineup_change|tactical_shift|schedule_pressure|travel_fatigue|form_change|manager_change|morale_event|other>",
      "impact_direction": "<positive|negative|neutral>",
      "team_name": "<affected team name>",
      "player_name": "<player name if applicable, else null>",
      "claim": "<one-sentence factual claim from the article>",
      "evidence_snippet": "<exact quote or paraphrase from article, max 300 chars>",
      "confidence": <0.0 to 1.0, based on how clearly the article supports this>,
      "source_reliability": <0.0 to 1.0, based on source credibility>
    }
  ]
}

RULES:
1. Only extract signals that are DIRECTLY supported by the article text.
2. Do NOT invent injuries, internal conflicts, or lineup changes not mentioned.
3. If the article has NO football-relevant signals (e.g., it's about F1, cricket, etc.), return {"signals": []}.
4. evidence_snippet MUST be an actual quote or close paraphrase from the article.
5. confidence: 0.8+ for direct quotes, 0.5-0.7 for paraphrases, <0.5 if speculative.
6. Maximum 5 signals per article. Quality over quantity.
7. Output valid JSON only — no markdown, no explanation."""


async def extract_signals_for_article(
    article: dict, http_client
) -> list[dict]:
    """Call DeepSeek V4 Pro to extract signals from one article."""
    user_prompt = f"""ARTICLE:
Title: {article['title']}
Source: {article['source_name']}
Published: {article['published_at']}
URL: {article['source_url']}

Content:
{article['content']}"""

    payload = {
        "model": "deepseek-v4-pro",
        "messages": [
            {"role": "system", "content": EXTRACTION_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 2000,
        "response_format": {"type": "json_object"},
    }

    import httpx
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        from app.config import get_settings
        api_key = get_settings().llm_api_key
    if not api_key:
        raise RuntimeError("No DeepSeek API key found")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    base_url = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1")

    async with httpx.AsyncClient(timeout=45.0) as client:
        for attempt in range(3):
            try:
                resp = await client.post(
                    f"{base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    return parsed.get("signals", [])
                else:
                    print(f"  API error (attempt {attempt+1}/3): {resp.status_code} {resp.text[:200]}")
                    if attempt < 2:
                        await asyncio.sleep(2 * (attempt + 1))
            except Exception as e:
                print(f"  Request error (attempt {attempt+1}/3): {e}")
                if attempt < 2:
                    await asyncio.sleep(2 * (attempt + 1))
    return []


def validate_signal(sig: dict, article: dict, idx: int) -> list[str]:
    """Validate a signal has all required fields. Returns list of issues."""
    issues = []
    # Required fields
    for field in REQUIRED_SIGNAL_FIELDS:
        if field not in sig or sig[field] is None or sig[field] == "":
            issues.append(f"missing {field}")

    # Validate signal_type
    if sig.get("signal_type") not in VALID_SIGNAL_TYPES:
        issues.append(f"invalid signal_type: {sig.get('signal_type')}")

    # Validate impact_direction
    if sig.get("impact_direction") not in VALID_IMPACT_DIRECTIONS:
        issues.append(f"invalid impact_direction: {sig.get('impact_direction')}")

    # Validate confidence
    conf = sig.get("confidence")
    if conf is None or not isinstance(conf, (int, float)) or conf < 0.0 or conf > 1.0:
        issues.append(f"invalid confidence: {conf}")

    # Validate source_reliability
    rel = sig.get("source_reliability")
    if rel is None or not isinstance(rel, (int, float)) or rel < 0.0 or rel > 1.0:
        issues.append(f"invalid source_reliability: {rel}")

    return issues


def insert_signal(sig: dict, article: dict, conn) -> str:
    """Insert a validated signal into news_signals. Returns signal_id."""
    signal_id = uuid.uuid4().hex[:32]
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """INSERT INTO news_signals (
            id, article_id, signal_type, impact_direction, confidence,
            source_reliability, review_status, enters_model,
            player_name, claim, evidence_snippet,
            team_id, match_id, key_players, summary_zh,
            normalized_availability, expected_minutes_delta,
            effective_until, conflict_group_id, contradiction_risk,
            review_notes, reviewed_by, reviewed_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', 0, ?, ?, ?, '', '', '[]', '',
            NULL, NULL, NULL, NULL, 'NONE', '', '', NULL, ?)""",
        (
            signal_id,
            article["id"],
            sig.get("signal_type", "other"),
            sig.get("impact_direction", "unknown"),
            sig.get("confidence", 0.5),
            sig.get("source_reliability", 0.5),
            sig.get("player_name"),
            sig.get("claim", ""),
            sig.get("evidence_snippet", ""),
            now,
        ),
    )
    return signal_id


def main():
    print("=" * 60)
    print("PHASE D-5: Signal Extraction (5 articles)")
    print("=" * 60)

    # Load articles from DB
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    articles = []
    for aid in ARTICLE_IDS:
        c.execute(
            "SELECT id, title, content, source_name, source_url, published_at "
            "FROM news_articles WHERE id = ?",
            (aid,),
        )
        row = c.fetchone()
        if row:
            articles.append(dict(row))
            has_url = "YES" if row["source_url"] else "MISSING"
            print(f"\n  [{len(articles)}] {row['title'][:80]}")
            print(f"      len={len(row['content'] or '')} url={has_url}")

    if len(articles) != 5:
        print(f"ERROR: Expected 5 articles, found {len(articles)}")
        conn.close()
        return

    # Run extraction
    total_extracted = 0
    total_inserted = 0
    total_rejected = 0
    all_signals = []

    async def run():
        nonlocal total_extracted, total_inserted, total_rejected

        for i, art in enumerate(articles):
            print(f"\n--- Article {i+1}: {art['title'][:70]} ---")

            # Check prerequisites
            if not art.get("source_url"):
                print("  SKIP: no source_url")
                total_rejected += 1
                continue
            if not art.get("content") or len(art["content"]) < 50:
                print(f"  SKIP: content too short ({len(art['content'] or '')} chars)")
                total_rejected += 1
                continue

            try:
                signals = await extract_signals_for_article(art, None)
            except Exception as e:
                print(f"  EXTRACTION ERROR: {e}")
                continue

            if not signals:
                print(f"  No signals found (article may not be football-related)")
                continue

            total_extracted += len(signals)
            print(f"  Raw signals from LLM: {len(signals)}")

            for j, sig in enumerate(signals):
                # Inject article-level metadata into each signal
                sig["source_url"] = art.get("source_url", "")
                sig["source_title"] = art.get("title", "")
                sig["published_at"] = str(art.get("published_at", ""))
                issues = validate_signal(sig, art, j)
                if issues:
                    print(f"    Signal {j+1} REJECTED: {', '.join(issues)}")
                    total_rejected += 1
                    continue

                try:
                    sid = insert_signal(sig, art, conn)
                    conn.commit()
                    total_inserted += 1
                    sig["_inserted_id"] = sid
                    sig["_article_title"] = art["title"]
                    all_signals.append(sig)
                    print(
                        f"    Signal {j+1} INSERTED: {sig['signal_type']} "
                        f"({sig['impact_direction']}) for {sig.get('team_name', '?')} "
                        f"conf={sig['confidence']:.2f}"
                    )
                except Exception as e:
                    print(f"    Signal {j+1} INSERT ERROR: {e}")
                    total_rejected += 1

    asyncio.run(run())

    # Summary
    print("\n" + "=" * 60)
    print("D-5 EXTRACTION SUMMARY")
    print("=" * 60)
    print(f"  Articles processed: {len(articles)}")
    print(f"  Signals extracted (raw): {total_extracted}")
    print(f"  Signals inserted: {total_inserted}")
    print(f"  Signals rejected: {total_rejected}")
    print(f"  All signals PENDING: YES")
    print(f"  All enters_model=false: YES")

    # Verify
    c.execute("SELECT COUNT(*) FROM news_signals")
    print(f"\n  news_signals total after extraction: {c.fetchone()[0]}")

    conn.close()


if __name__ == "__main__":
    main()
