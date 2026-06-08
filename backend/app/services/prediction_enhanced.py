"""prediction_enhanced.py — Enhanced prediction orchestrator for V2.6.

Wraps prediction_core (artifact pipeline) with real-time data:
- Market odds (apifootball.com / The Odds API)
- Weather (Open-Meteo, free)
- DeepSeek V4 Pro AI analysis

Design principles:
1. prediction_core.py is NOT modified — enhanced wraps it
2. Every real-time data source has graceful degradation
3. Market blend is capped at 25% (MAX_MARKET_BLEND)
4. LLM analysis is optional and non-blocking
5. All functions are synchronous (for Streamlit compatibility)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ── Market blend constants (mirrored from market_calibrator.py) ─────────────────
MAX_MARKET_BLEND = 0.25
MIN_MARKET_BLEND = 0.05
DIVERGENCE_THRESHOLD = 0.12
BLEND_SATURATION = 2000


@dataclass
class EnhancedPredictionResult:
    """Complete enhanced prediction output.

    Contains base artifact prediction + optional market/weather/LLM data.
    """

    # ── Match info ──
    home_team: str
    away_team: str
    competition: str
    is_neutral: bool
    mode: str

    # ── Base artifact prediction ──
    base_result: dict[str, Any] = field(default_factory=dict)
    base_quality: Any = None  # RunQuality
    timings: Any = None  # PredictionTimer

    # ── Final probabilities (after market blend, if applied) ──
    final_home_prob: float = 0.333
    final_draw_prob: float = 0.334
    final_away_prob: float = 0.333

    # ── Market data ──
    market_probs: dict[str, Any] | None = None
    market_blended: bool = False
    market_weight_used: float = 0.0
    market_divergence: float | None = None
    market_divergence_triggered: bool = False

    # ── Weather ──
    weather: dict[str, Any] | None = None
    weather_impact_tags: list[str] = field(default_factory=list)

    # ── LLM analysis ──
    llm_analysis: str | None = None
    llm_video_script: str | None = None
    llm_social_copy: str | None = None
    llm_error: str | None = None

    # ── Metadata ──
    enhanced_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    components_used: list[str] = field(default_factory=list)
    risk_tags: list[str] = field(default_factory=list)
    confidence_penalty: float = 0.0
    total_seconds: float = 0.0

    @property
    def is_enhanced(self) -> bool:
        """True if any real-time data was successfully incorporated."""
        return self.market_probs is not None or self.weather is not None

    @property
    def is_ai_analyzed(self) -> bool:
        """True if LLM analysis was generated."""
        return self.llm_analysis is not None


# ── Main entry point ────────────────────────────────────────────────────────────


def run_enhanced_prediction(
    home_team: str,
    away_team: str,
    competition: str = "International Friendly",
    is_neutral: bool = True,
    mode: str = "full",
    *,
    enable_market: bool = True,
    enable_weather: bool = True,
    enable_llm: bool = True,
    market_blend_max: float = MAX_MARKET_BLEND,
) -> EnhancedPredictionResult:
    """Run enhanced prediction with real-time data enrichment.

    Flow:
    1. Base artifact prediction (prediction_core)
    2. Market odds fetch (optional)
    3. Market-model blend (if odds available)
    4. Weather fetch (optional)
    5. LLM analysis generation (optional)

    All optional steps degrade gracefully — failure in any step
    does not prevent the overall prediction from completing.

    Args:
        home_team: Home team name.
        away_team: Away team name.
        competition: Competition name.
        is_neutral: Neutral venue flag.
        mode: Prediction mode (baseline/standard/full/research-full).
        enable_market: Fetch and blend market odds.
        enable_weather: Fetch weather data.
        enable_llm: Generate AI analysis via DeepSeek.
        market_blend_max: Max market blend fraction (default 0.25).

    Returns:
        EnhancedPredictionResult with all available data.
    """
    import time as time_module

    t_start = time_module.perf_counter()

    result = EnhancedPredictionResult(
        home_team=home_team,
        away_team=away_team,
        competition=competition,
        is_neutral=is_neutral,
        mode=mode,
    )

    # ── Step 1: Base artifact prediction ────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  WC26 Predict V2.6 Enhanced — {home_team} vs {away_team}")
    print(f"  {competition} | Neutral: {is_neutral} | Mode: {mode}")
    print(f"{'='*60}\n")
    print("  [1/5] Running base artifact pipeline...")

    try:
        from app.services.prediction_core import run_artifact_pipeline

        base_result, base_quality, timings = run_artifact_pipeline(
            home_team=home_team,
            away_team=away_team,
            competition=competition,
            is_neutral=is_neutral,
            mode=mode,
        )
        result.base_result = base_result
        result.base_quality = base_quality
        result.timings = timings

        # Start with base probabilities
        result.final_home_prob = base_result["home_win_prob"]
        result.final_draw_prob = base_result["draw_prob"]
        result.final_away_prob = base_result["away_win_prob"]
        result.components_used = list(base_result.get("components_used", []))
        result.risk_tags = list(base_result.get("risk_tags", []))

    except Exception as exc:
        logger.error(f"Base artifact pipeline failed: {exc}")
        result.llm_error = f"Base prediction failed: {exc}"
        result.total_seconds = time_module.perf_counter() - t_start
        return result

    # ── Step 2: Market odds ─────────────────────────────────────────────────
    if enable_market:
        print("  [2/5] Fetching market odds...")
        try:
            market_probs = _fetch_market(home_team, away_team, competition)
            if market_probs is not None:
                result.market_probs = market_probs
                print(
                    f"  [market] {market_probs['provider']}: "
                    f"H={market_probs['home_prob']:.3f} "
                    f"D={market_probs['draw_prob']:.3f} "
                    f"A={market_probs['away_prob']:.3f}"
                )

                # Compute divergence
                mh = market_probs["home_prob"]
                md = market_probs["draw_prob"]
                ma = market_probs["away_prob"]
                div = max(
                    abs(result.final_home_prob - mh),
                    abs(result.final_draw_prob - md),
                    abs(result.final_away_prob - ma),
                )
                result.market_divergence = div
                result.market_divergence_triggered = div > DIVERGENCE_THRESHOLD

                if result.market_divergence_triggered:
                    tag = f"模型与市场存在显著分歧 ({div*100:.1f}pp)"
                    result.risk_tags.append(tag)
                    result.confidence_penalty = min(div * 0.5, 0.15)

                # Blend market into model probabilities
                result.final_home_prob, result.final_draw_prob, result.final_away_prob = (
                    _blend_market(
                        model_home=result.final_home_prob,
                        model_draw=result.final_draw_prob,
                        model_away=result.final_away_prob,
                        market_home=mh,
                        market_draw=md,
                        market_away=ma,
                        max_blend=market_blend_max,
                    )
                )
                result.market_blended = True
                # Compute blend weight for reporting
                result.market_weight_used = max(
                    MIN_MARKET_BLEND,
                    min(market_blend_max, 0.25),
                )
                print(
                    f"  [blend] After market: "
                    f"H={result.final_home_prob:.3f} "
                    f"D={result.final_draw_prob:.3f} "
                    f"A={result.final_away_prob:.3f}"
                )
            else:
                print("  [market] No odds available — using model-only probabilities")
        except Exception as exc:
            logger.warning(f"Market fetch failed, using model-only: {exc}")
            print(f"  [market] Failed: {exc} — using model-only probabilities")
    else:
        print("  [2/5] Market odds: disabled")

    # ── Step 3: Weather ─────────────────────────────────────────────────────
    if enable_weather:
        print("  [3/5] Fetching weather...")
        try:
            weather = _fetch_weather(home_team, away_team)
            if weather is not None and weather.get("forecast_available"):
                result.weather = weather
                # Get impact tags
                from app.services.weather_service import WeatherService

                ws = WeatherService()
                result.weather_impact_tags = ws.weather_impact_tags(weather)
                print(
                    f"  [weather] {weather.get('weather_description', '?')}, "
                    f"{weather.get('temperature_c', '?')}°C, "
                    f"wind {weather.get('wind_speed_kmh', '?')} km/h"
                )
                if result.weather_impact_tags:
                    result.risk_tags.extend(result.weather_impact_tags)
                    print(f"  [weather] Impact: {', '.join(result.weather_impact_tags)}")
            else:
                print("  [weather] No forecast available for this match")
        except Exception as exc:
            logger.warning(f"Weather fetch failed: {exc}")
            print(f"  [weather] Failed: {exc}")
    else:
        print("  [3/5] Weather: disabled")

    # ── Step 4: LLM Analysis ────────────────────────────────────────────────
    if enable_llm:
        print("  [4/5] Generating AI analysis via DeepSeek V4 Pro...")
        try:
            llm_result = _generate_llm_analysis(result)
            if llm_result:
                result.llm_analysis = llm_result.get("analysis")
                result.llm_video_script = llm_result.get("video_script")
                result.llm_social_copy = llm_result.get("social_copy")
                print(
                    f"  [LLM] Analysis: {len(result.llm_analysis or '')} chars, "
                    f"Script: {len(result.llm_video_script or '')} chars"
                )
            else:
                print("  [LLM] Generation returned empty — using template fallback")
        except Exception as exc:
            logger.warning(f"LLM analysis failed: {exc}")
            result.llm_error = str(exc)
            print(f"  [LLM] Failed: {exc}")
    else:
        print("  [4/5] LLM analysis: disabled")

    # ── Step 5: Finalize ────────────────────────────────────────────────────
    result.total_seconds = time_module.perf_counter() - t_start
    print(f"\n  [5/5] Enhanced prediction complete in {result.total_seconds:.1f}s")
    print(f"  Final: H={result.final_home_prob:.3f} "
          f"D={result.final_draw_prob:.3f} "
          f"A={result.final_away_prob:.3f}")
    print(f"{'='*60}\n")

    return result


# ── Internal helpers ────────────────────────────────────────────────────────────


def _fetch_market(
    home_team: str,
    away_team: str,
    competition: str,
) -> dict[str, Any] | None:
    """Fetch market consensus synchronously. Returns None on failure."""
    try:
        from app.services.market.sync_provider import fetch_market_consensus_sync

        return fetch_market_consensus_sync(home_team, away_team, competition)
    except ImportError as e:
        logger.warning("sync_provider not available: %s", e)
        return None
    except Exception as e:
        logger.warning("Market fetch error: %s", e)
        return None


def _fetch_weather(
    home_team: str,
    away_team: str,
) -> dict[str, Any] | None:
    """Fetch weather synchronously. Returns None on failure."""
    try:
        from app.services.weather_service import WeatherService

        ws = WeatherService()
        return ws.get_weather_for_match_sync(
            home_team=home_team,
            away_team=away_team,
        )
    except ImportError as e:
        logger.warning("WeatherService not available: %s", e)
        return None
    except Exception as e:
        logger.warning("Weather fetch error: %s", e)
        return None


def _blend_market(
    model_home: float,
    model_draw: float,
    model_away: float,
    market_home: float,
    market_draw: float,
    market_away: float,
    max_blend: float = MAX_MARKET_BLEND,
) -> tuple[float, float, float]:
    """Blend market implied probabilities into model probabilities.

    Uses a capped linear blend: final = (1-w)*model + w*market
    where w = max(MIN, min(MAX, max_blend)).

    Returns (home, draw, away) tuple, always normalized to sum=1.0.
    """
    weight = max(MIN_MARKET_BLEND, min(MAX_MARKET_BLEND, max_blend))
    model_weight = 1.0 - weight

    h = model_home * model_weight + market_home * weight
    d = model_draw * model_weight + market_draw * weight
    a = model_away * model_weight + market_away * weight

    # Normalize
    total = h + d + a
    if total > 0:
        h /= total
        d /= total
        a /= total

    return h, d, a


def _generate_llm_analysis(
    result: EnhancedPredictionResult,
) -> dict[str, str] | None:
    """Generate AI analysis via DeepSeek V4 Pro.

    Uses asyncio.run() to call the async DeepSeek client.
    Generates three content types: analysis article, video script, social copy.

    Returns dict with 'analysis', 'video_script', 'social_copy' keys,
    or None if all generations failed.  Returns degraded flag if called
    from within an existing event loop (e.g., FastAPI async route).
    """
    import asyncio
    import logging

    _log = logging.getLogger(__name__)

    # Check for existing event loop before calling asyncio.run()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        _log.warning(
            "LLM analysis skipped — asyncio.run() cannot be called from "
            "existing event loop. Returning degraded result."
        )
        return {
            "degraded": True,
            "source": "llm_analysis",
            "reason": "event_loop_conflict",
        }

    return asyncio.run(_generate_llm_analysis_async(result))


async def _generate_llm_analysis_async(
    result: EnhancedPredictionResult,
) -> dict[str, str] | None:
    """Async implementation of LLM analysis generation."""
    try:
        from app.services.llm.analysis_prompts import (
            MATCH_ANALYSIS_SYSTEM,
            MATCH_ANALYSIS_USER,
            VIDEO_SCRIPT_SYSTEM,
            VIDEO_SCRIPT_USER,
            SOCIAL_COPY_SYSTEM,
            SOCIAL_COPY_USER,
            build_market_section,
            build_market_summary,
            build_weather_section,
            build_team_context,
            build_key_points,
        )
        from app.services.llm.deepseek_client import DeepSeekClient
    except ImportError as e:
        logger.warning("LLM modules not available: %s", e)
        return None

    client = DeepSeekClient()

    base = result.base_result
    h = result.final_home_prob
    d = result.final_draw_prob
    a = result.final_away_prob
    home = result.home_team
    away = result.away_team
    comp = result.competition

    # Format top scores
    scores = base.get("top_scores", [])
    top_scores_str = "、".join(
        f"{s['score']} ({s['prob']:.1%})" for s in scores[:3]
    ) if scores else "暂无"

    # Build disagreement string
    fg = base.get("fusion_graph", {})
    disagreement = fg.get("model_disagreement", {})
    max_diff = disagreement.get("max_home_diff", 0)
    if max_diff > 0.3:
        disagreement_str = f"高 ({max_diff:.1%}) — 模型间存在显著方向性分歧"
    elif max_diff > 0.15:
        disagreement_str = f"中等 ({max_diff:.1%})"
    else:
        disagreement_str = f"低 ({max_diff:.1%}) — 模型方向一致"

    output: dict[str, str] = {}

    # ── 1. Match analysis article ──
    try:
        market_section = build_market_section(result.market_probs)
        weather_section = build_weather_section(result.weather)
        team_context = build_team_context(home, away)
        user_prompt = MATCH_ANALYSIS_USER.format(
            home_team=home,
            away_team=away,
            competition=comp,
            venue="中立场地" if result.is_neutral else f"{home} 主场",
            match_time="即将进行",
            home_prob=h,
            draw_prob=d,
            away_prob=a,
            home_xg=base.get("home_xg", 0),
            away_xg=base.get("away_xg", 0),
            top_scores=top_scores_str,
            disagreement=disagreement_str,
            market_section=market_section,
            weather_section=weather_section,
            team_context=team_context,
        )
        analysis = await client.chat(
            system=MATCH_ANALYSIS_SYSTEM,
            user=user_prompt,
            response_format="text",
        )
        if analysis:
            output["analysis"] = analysis
    except Exception as e:
        logger.warning(f"LLM analysis article generation failed: {e}")

    # ── 2. Video script ──
    try:
        key_points = build_key_points(base, result.market_probs)
        market_summary = build_market_summary(result.market_probs)
        script_prompt = VIDEO_SCRIPT_USER.format(
            home_team=home,
            away_team=away,
            competition=comp,
            venue="中立场地" if result.is_neutral else f"{home} 主场",
            home_prob=h,
            draw_prob=d,
            away_prob=a,
            home_xg=base.get("home_xg", 0),
            away_xg=base.get("away_xg", 0),
            top_scores=top_scores_str,
            market_summary=market_summary,
            key_points=key_points,
        )
        script = await client.chat(
            system=VIDEO_SCRIPT_SYSTEM,
            user=script_prompt,
            response_format="text",
        )
        if script:
            output["video_script"] = script
    except Exception as e:
        logger.warning(f"LLM video script generation failed: {e}")

    # ── 3. Social copy ──
    try:
        social_prompt = SOCIAL_COPY_USER.format(
            home_team=home,
            away_team=away,
            competition=comp,
            home_prob=h,
            draw_prob=d,
            away_prob=a,
            home_xg=base.get("home_xg", 0),
            away_xg=base.get("away_xg", 0),
        )
        social = await client.chat(
            system=SOCIAL_COPY_SYSTEM,
            user=social_prompt,
            response_format="text",
        )
        if social:
            output["social_copy"] = social
    except Exception as e:
        logger.warning(f"LLM social copy generation failed: {e}")

    return output if output else None


# ── Convenience: convert to Dashboard-compatible dict ───────────────────────────


def enhanced_result_to_dict(result: EnhancedPredictionResult) -> dict[str, Any]:
    """Convert EnhancedPredictionResult to a dict for st.session_state storage."""
    base = result.base_result
    return {
        "home_team": result.home_team,
        "away_team": result.away_team,
        "competition": result.competition,
        "is_neutral": result.is_neutral,
        "mode": result.mode,
        # Final probabilities (after market blend if applicable)
        "home_win_prob": result.final_home_prob,
        "draw_prob": result.final_draw_prob,
        "away_win_prob": result.final_away_prob,
        # From base
        "home_xg": base.get("home_xg", 0),
        "away_xg": base.get("away_xg", 0),
        "top_scores": base.get("top_scores", []),
        "components_used": result.components_used,
        "fusion_graph": base.get("fusion_graph", {}),
        # Enhanced data
        "market_probs": result.market_probs,
        "market_blended": result.market_blended,
        "market_divergence": result.market_divergence,
        "market_divergence_triggered": result.market_divergence_triggered,
        "weather": result.weather,
        "weather_impact_tags": result.weather_impact_tags,
        # LLM content
        "llm_analysis": result.llm_analysis,
        "llm_video_script": result.llm_video_script,
        "llm_social_copy": result.llm_social_copy,
        # Metadata
        "risk_tags": result.risk_tags,
        "confidence_penalty": result.confidence_penalty,
        "total_seconds": result.total_seconds,
        "is_enhanced": result.is_enhanced,
        "is_ai_analyzed": result.is_ai_analyzed,
        "enhanced_at": result.enhanced_at,
    }
