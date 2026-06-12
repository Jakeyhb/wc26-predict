#!/usr/bin/env python3
"""Call DeepSeek API directly for match analysis — bypasses FastAPI server."""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

DB_PATH = BACKEND_DIR / "data" / "local_stage2.db"
MATCH_ID = "77382b67668e4d1a966a5fb88af6e408"


def load_env() -> tuple[str, str, str]:
    """Load LLM config from .env.local or .env."""
    key = ""
    model = "deepseek-v4-pro"
    base = "https://api.deepseek.com"

    for env_name in [".env.local", ".env"]:
        env_path = BACKEND_DIR / env_name
        if env_path.exists():
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    v = v.strip().strip('"').strip("'")
                    if k == "LLM_API_KEY":
                        key = v
                    elif k == "LLM_MODEL":
                        model = v
                    elif k == "LLM_BASE_URL":
                        base = v.rstrip("/")

    return key, model, base


def read_match_data() -> dict | None:
    """Read match + prediction + recent form from SQLite."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    try:
        match = conn.execute(
            """SELECT m.*, ht.name AS home_name, at.name AS away_name
               FROM matches m
               JOIN teams ht ON m.home_team_id = ht.id
               JOIN teams at ON m.away_team_id = at.id
               WHERE m.id = ?""",
            (MATCH_ID,),
        ).fetchone()

        if not match:
            return None

        # Try prediction_runs first, fallback to prediction_snapshots
        pred = conn.execute(
            """SELECT * FROM prediction_runs
               WHERE match_id = ?
               ORDER BY created_at DESC LIMIT 1""",
            (MATCH_ID,),
        ).fetchone()

        if not pred:
            pred = conn.execute(
                """SELECT * FROM prediction_snapshots
                   WHERE match_id LIKE ?
                   ORDER BY generated_at DESC LIMIT 1""",
                (MATCH_ID + "%",),
            ).fetchone()

        home_name = match["home_name"]
        away_name = match["away_name"]
        match_date = match["match_date"]

        def get_recent_form(team_name: str, before_date: str) -> list[str]:
            rows = conn.execute(
                """SELECT ht.name AS home_name, at.name AS away_name,
                          m.match_date, m.competition,
                          r.home_goals, r.away_goals
                   FROM matches m
                   JOIN match_results r ON m.id = r.match_id
                   JOIN teams ht ON m.home_team_id = ht.id
                   JOIN teams at ON m.away_team_id = at.id
                   WHERE (ht.name = ? OR at.name = ?)
                     AND m.match_date < ?
                     AND m.status = 'finished'
                   ORDER BY m.match_date DESC
                   LIMIT 5""",
                (team_name, team_name, before_date),
            ).fetchall()

            form_lines = []
            for r in rows:
                if r["home_name"] == team_name:
                    result = "W" if r["home_goals"] > r["away_goals"] else ("D" if r["home_goals"] == r["away_goals"] else "L")
                    form_lines.append(f"  {r['match_date'][:10]} {result} {r['home_goals']}-{r['away_goals']} vs {r['away_name']} ({r['competition']})")
                else:
                    result = "W" if r["away_goals"] > r["home_goals"] else ("D" if r["home_goals"] == r["away_goals"] else "L")
                    form_lines.append(f"  {r['match_date'][:10]} {result} {r['away_goals']}-{r['home_goals']} vs {r['home_name']} ({r['competition']})")
            return form_lines

        home_form = get_recent_form(home_name, match_date)
        away_form = get_recent_form(away_name, match_date)

        def row_get(row, key, default=None):
            """Safe get from sqlite3.Row (no .get() method)."""
            try:
                return row[key]
            except (IndexError, KeyError):
                return default

        pred_dict = None
        if pred is not None:
            # Parse JSON columns from sqlite3.Row
            baseline_str = row_get(pred, "baseline_probs")
            xg_str = row_get(pred, "expected_goals")

            if baseline_str and isinstance(baseline_str, str):
                bp = json.loads(baseline_str)
            elif baseline_str and isinstance(baseline_str, dict):
                bp = baseline_str
            else:
                bp = {"home": 0.33, "draw": 0.33, "away": 0.33}

            if xg_str and isinstance(xg_str, str):
                xg = json.loads(xg_str)
            elif xg_str and isinstance(xg_str, dict):
                xg = xg_str
            else:
                xg = {"home": 1.0, "away": 0.5}

            pred_dict = {
                "home_win_prob": float(bp.get("home", 0.33)),
                "draw_prob": float(bp.get("draw", 0.33)),
                "away_win_prob": float(bp.get("away", 0.33)),
                "home_xg": float(xg.get("home", 1.0)),
                "away_xg": float(xg.get("away", 0.5)),
                "model_version": row_get(pred, "model_version", "V3.4"),
                "confidence_score": row_get(pred, "confidence", "medium"),
            }

        return {
            "home_name": home_name,
            "away_name": away_name,
            "match_date": match_date,
            "competition": match["competition"],
            "is_neutral_venue": match["is_neutral_venue"],
            "prediction": pred_dict,
            "home_form": home_form,
            "away_form": away_form,
        }
    finally:
        conn.close()


ANALYSIS_SYSTEM_PROMPT = """You are a professional football analyst. Your task is to write a pre-match analysis report based on provided match data, model predictions, and recent form.

Rules:
- Professional tone, like an analyst not a gambler
- Use specific numbers, avoid vague descriptions
- Do NOT mention any betting platforms or odds
- If data is limited, explicitly state lower confidence
- Output in Chinese, approximately 400 characters"""


async def main():
    key, model, base = load_env()

    if not key:
        print("ERROR: LLM_API_KEY not configured")
        return

    print(f"DeepSeek: model={model}")
    print()

    match_data = read_match_data()
    if not match_data:
        print("ERROR: Match not found")
        return

    home_name = match_data["home_name"]
    away_name = match_data["away_name"]
    pred = match_data["prediction"]
    home_form = match_data["home_form"]
    away_form = match_data["away_form"]

    print(f"Match: {home_name} vs {away_name}")
    print(f"Date: {match_data['match_date']}")
    print(f"Comp: {match_data['competition']}")
    print(f"Prediction: {'YES' if pred else 'NO'}")
    print()

    # Build prompt
    if pred:
        home_pct = f"{pred['home_win_prob'] * 100:.1f}%"
        draw_pct = f"{pred['draw_prob'] * 100:.1f}%"
        away_pct = f"{pred['away_win_prob'] * 100:.1f}%"
        prediction_section = f"""Model prediction:
- Home win: {home_pct}
- Draw: {draw_pct}
- Away win: {away_pct}
- Home xG: {pred['home_xg']:.2f}
- Away xG: {pred['away_xg']:.2f}
- Model: {pred['model_version']}
- Confidence: {pred['confidence_score']}"""
    else:
        prediction_section = "(No model prediction available)"

    home_form_str = "\n".join(home_form) if home_form else "  No data"
    away_form_str = "\n".join(away_form) if away_form else "  No data"

    form_section = f"""{home_name} recent form:
{home_form_str}

{away_name} recent form:
{away_form_str}"""

    user_prompt = f"""Please write a pre-match analysis report based on the following data.

Match info:
- Home: {home_name}
- Away: {away_name}
- Date: {match_data['match_date'][:16]}
- Competition: {match_data['competition']}
- Venue: {'Neutral' if match_data['is_neutral_venue'] else 'Home advantage'}

{prediction_section}

{form_section}

Please write an analysis of about 400 words, structured as:
1. Core judgment (2-3 sentences, direct prediction conclusion with key evidence)
2. Data analysis (interpret model data, analyze both teams' form)
3. Key factors (2-3 most important factors for this match)
4. Risk warnings (what could make the prediction wrong)
5. Match outlook (most likely game flow and score range)"""

    print("Calling DeepSeek API...")
    print()

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{base}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 1024,
                "temperature": 0.7,
            },
        )
        response.raise_for_status()
        data = response.json()

    analysis_text = data["choices"][0]["message"]["content"]

    print("=" * 60)
    print("DEEPSEEK ANALYSIS REPORT")
    print("=" * 60)
    print(analysis_text)
    print("=" * 60)
    print()

    # Save to file
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    report_path = BACKEND_DIR / "reports" / f"{ts}_DeepSeek_Analysis_{home_name}_vs_{away_name}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# DeepSeek AI Analysis: {home_name} vs {away_name}\n\n")
        f.write(f"> {match_data['competition']} | {match_data['match_date'][:16]}\n")
        f.write(f"> Generated: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"> Model: {model}\n\n")
        f.write("---\n\n")
        f.write(analysis_text)
        f.write("\n\n---\n")
        f.write(f"> Generated by WC26 Predict V3.4 + {model}\n")

    print(f"Report saved: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
