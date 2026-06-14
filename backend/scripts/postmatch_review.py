#!/usr/bin/env python3
"""postmatch_review.py — Post-match prediction evaluation and AI review.

Evaluates a past prediction against actual match result, computes accuracy
metrics (Brier/LogLoss/RPS), and optionally generates a DeepSeek AI review.

Usage:
    python scripts/postmatch_review.py \
        --home Spain --away Iraq \
        --home-goals 1 --away-goals 1 \
        --competition "International Friendly" \
        --neutral

    python scripts/postmatch_review.py \
        --home Spain --away Iraq \
        --home-goals 1 --away-goals 1 \
        --ai-review   # Generate DeepSeek post-match analysis
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


def main():
    p = argparse.ArgumentParser(
        description="Post-match prediction evaluation and AI review"
    )
    p.add_argument("--home", required=True, help="Home team name")
    p.add_argument("--away", required=True, help="Away team name")
    p.add_argument("--home-goals", type=int, required=True, help="Actual home goals")
    p.add_argument("--away-goals", type=int, required=True, help="Actual away goals")
    p.add_argument("--competition", default="International Friendly")
    p.add_argument("--neutral", action="store_true", help="Neutral venue")
    p.add_argument("--mode", default="full", help="Prediction mode")
    p.add_argument("--ai-review", action="store_true", help="Generate DeepSeek AI review")
    p.add_argument("--output", choices=["text", "json"], default="text")
    args = p.parse_args()

    # ── Step 1: Run artifact prediction ───────────────────────────────────
    print(f"  Running prediction for {args.home} vs {args.away}...")
    from app.services.prediction_pipeline import PredictionPipeline

    pipeline = PredictionPipeline.from_artifacts(mode=args.mode)
    pred_result = pipeline.predict_sync(
        args.home, args.away, args.competition, is_neutral=args.neutral
    )
    # Build backward-compatible dict for evaluate_prediction()
    result = pred_result.to_dict()["prediction"]
    result["home_team"] = pred_result.home_team
    result["away_team"] = pred_result.away_team
    result["competition"] = pred_result.competition
    result["is_neutral"] = pred_result.is_neutral
    result["home_xg"] = pred_result.home_xg
    result["away_xg"] = pred_result.away_xg
    result["top_scores"] = pred_result.top_scores
    result["components_used"] = pred_result.components_used
    result["mode"] = args.mode

    # ── Step 2: Evaluate ──────────────────────────────────────────────────
    from app.services.postmatch import (
        MatchReview,
        evaluate_prediction,
        generate_comparison_text,
    )

    review = evaluate_prediction(result, args.home_goals, args.away_goals)

    # ── Step 3: AI review (optional) ──────────────────────────────────────
    if args.ai_review:
        print("  Generating AI post-match review via DeepSeek V4 Pro...")
        review.ai_review = _generate_ai_review(review)
        if review.ai_review:
            print(f"  AI review: {len(review.ai_review)} chars")

    # ── Step 4: Output ────────────────────────────────────────────────────
    if args.output == "json":
        print(json.dumps(review.to_dict(), indent=2, ensure_ascii=False))
    else:
        print()
        print("=" * 60)
        print(f"  POST-MATCH REVIEW: {args.home} vs {args.away}")
        print("=" * 60)
        print()
        print(generate_comparison_text(review))
        print()
        if review.ai_review:
            print("─" * 60)
            print("  AI 赛后复盘 (DeepSeek V4 Pro)")
            print("─" * 60)
            print(review.ai_review)
            print()
        print("=" * 60)


def _generate_ai_review(review: MatchReview) -> str | None:
    """Generate AI post-match review using DeepSeek V4 Pro."""
    import asyncio
    return asyncio.run(_generate_ai_review_async(review))


async def _generate_ai_review_async(review: MatchReview) -> str | None:
    """Async implementation."""
    try:
        from app.services.llm.deepseek_client import DeepSeekClient
    except ImportError:
        return None

    system_prompt = """你是一名专业的足球分析师和球评人。
你的任务是对比赛前预测和实际比赛结果，撰写赛后复盘分析。

规则:
- 客观分析预测偏差的原因
- 不使用博彩/投注相关术语
- 承认模型局限性和足球的不确定性
- 如果预测准确，分析为什么准确
- 如果预测偏差，诚实分析哪里出了问题
- 字数: 300-400字"""

    direction_label = {
        "home": f"{review.home_team} 胜",
        "draw": "平局",
        "away": f"{review.away_team} 胜",
    }

    user_prompt = f"""请复盘以下比赛:

## 比赛信息
{review.home_team} vs {review.away_team} | {review.competition}
实际比分: {review.actual_score_str} ({direction_label.get(review.actual_outcome, review.actual_outcome)})

## 赛前预测
- {review.home_team} 胜: {review.pred_home_prob*100:.1f}%
- 平局: {review.pred_draw_prob*100:.1f}%
- {review.away_team} 胜: {review.pred_away_prob*100:.1f}%
- 最可能比分: {', '.join(f"{s['score']}({s['prob']*100:.1f}%)" for s in review.pred_top_scores[:3]) if review.pred_top_scores else 'N/A'}
- xG: {review.home_team} {review.pred_home_xg:.2f} vs {review.away_team} {review.pred_away_xg:.2f}

## 评估指标
- Brier Score: {review.brier_score:.4f} (0=完美)
- 方向正确: {'是' if review.directional_correct else '否'}
- 比分命中: {'是' if review.exact_score_hit else '否'}
- 综合评级: {review.grade}

请从以下角度分析:
1. 预测与实际结果的核心偏差是什么?
2. 哪些赛前因素模型没有捕捉到?
3. 这个偏差对未来类似比赛的预测有什么启示?
4. 模型的概率输出在什么意义上仍然有用(或无用)?

请撰写300-400字的赛后复盘分析。"""

    try:
        client = DeepSeekClient()
        result = await client.chat(
            system=system_prompt,
            user=user_prompt,
            response_format="text",
        )
        return result if result else None
    except Exception as e:
        print(f"  [AI review failed: {e}]")
        return None


if __name__ == "__main__":
    main()
