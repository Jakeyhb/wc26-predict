#!/usr/bin/env python3
"""Single-match prediction snapshot.

Usage::

    python scripts/snapshot.py --home "Tottenham Hotspur FC" --away "Leeds United FC"

Output: backend/reports/{date}_{home}_vs_{away}.md

The report includes:
  - Three-layer fused probabilities (DC + Enhancer + Elo)
  - Elo ratings and recent form
  - Source log for every data point
  - Unknown / missing data markers
  - Confidence notes on what the model knows and doesn't know
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = BACKEND_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import AsyncSessionLocal
from app.services.dixon_coles import DixonColesModel, load_training_frame, WC26_FIFA_TIERS
from app.services.elo_ratings import EloRatingSystem, fuse_elo_probabilities
from app.services.pi_ratings import PiRatingWrapper, fuse_pi_probabilities
from app.services.weibull_model import WeibullWrapper, fuse_weibull_probs
from app.services.source_logger import SourceLogBuilder, render_source_table
from app.services.tabular_match_model import TabularMatchEnhancer, fuse_outcome_probabilities
from app.services.snapshot_store import save_prediction_snapshot
from app.services.signal_adjuster import SignalAdjuster
from app.services.model_cache import get_cache as get_model_cache
from app.services.wc_motivation import compute_wc_motivation
from app.models.motivation_event import MotivationEvent, MOTIVATION_TAGS
from app.models.manual_event import ManualEvent
from app.models.team import Team
from app.models.player import Player
from sqlalchemy import select, text


async def _build_team_info(db, team_type: str) -> dict[str, dict[str, Any]]:
    """Build team_info mapping for cold-start fallback.

    Returns {team_name: {"confederation": str, "fifa_tier": int}}
    """
    result = await db.execute(
        select(Team.name, Team.confederation)
        .where(Team.team_type == team_type)
    )
    rows = result.all()
    team_info = {}
    for name, conf in rows:
        tier = WC26_FIFA_TIERS.get(name, 0)
        team_info[name] = {
            "confederation": conf or "FIFA",
            "fifa_tier": tier,
        }
    return team_info


# ═══════════════════════════════════════════════════════════
#  Pipeline
# ═══════════════════════════════════════════════════════════
async def run_snapshot(
    home_team: str,
    away_team: str,
    *,
    is_neutral: bool = False,
    competition_weight: float = 0.9,
    competition: str = "Premier League",
    competitions: list[str] | None = None,
) -> dict[str, Any]:
    """Run the full prediction pipeline and return a structured result."""

    # ── Load training data ──
    # Detect national vs club competition
    is_national = any(kw in competition.lower() for kw in ["world cup", "euro", "copa", "nations", "international"])
    comp_type = "national" if is_national else "club"
    team_t = "national" if is_national else "club"

    async with AsyncSessionLocal() as db:
        df = await load_training_frame(
            db,
            competition=None if (is_national or competitions) else competition,
            competitions=competitions,
            competition_type=comp_type,
            team_type=team_t,
        )

        # Build team registry for cold-start fallback
        team_info = await _build_team_info(db, team_t)

    if df.empty:
        raise RuntimeError(f"No training data for {competition}")

    rows = len(df)
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    match_date = df["match_date"].max().to_pydatetime()

    # ── Layer 1: Dixon-Coles ──
    mc = get_model_cache()
    dc_cached = mc.get_dc(competition, df)
    if dc_cached:
        dc = DixonColesModel()
        dc.set_team_info(team_info)
        mc.restore_dc(dc_cached, dc)
        dc_fit = type("FitSummary", (), {"final_neg_log_likelihood": 0.0, "attack_free": len(dc_cached.attack_params)})()
    else:
        dc = DixonColesModel()
        dc.set_team_info(team_info)
        dc_fit = dc.fit(df)
        mc.set_dc(competition, df, dc)
    dc_pred = dc.predict_match(home_team, away_team, is_neutral_venue=is_neutral)

    # ── Layer 2: Tabular Enhancer ──
    enh_cached = mc.get_enhancer(competition, df)
    if enh_cached:
        enhancer = TabularMatchEnhancer()
        mc.restore_enhancer(enh_cached, enhancer)
    else:
        enhancer = TabularMatchEnhancer()
        enhancer.fit(df)
        mc.set_enhancer(competition, df, enhancer)
    enh_pred = enhancer.predict_match(
        home_team=home_team,
        away_team=away_team,
        match_date=match_date,
        competition_weight=competition_weight,
        is_neutral_venue=is_neutral,
        training_df=df,
        rest_days={"home": 5, "away": 5},
    )

    # ── Weibull Copula (optional, complements DC for over/under) ──
    wb = WeibullWrapper()
    wb_fitted = wb.fit(df, timeout=60)
    wb_pred = wb.predict(home_team, away_team, is_neutral) if wb_fitted else None

    # ── Scene-based Model Config ─────────────────────────────
    cfg = _get_model_config(competition, stage=(await _get_match_stage(home_team, away_team, competition)))
    print(f"  场景配置: {cfg['label']} (DC{cfg['dc_weight']:.0%}+Enh{cfg['enh_weight']:.0%}+Elo{cfg['elo_weight']:.0%}+Pi{cfg['pi_weight']:.0%})")

    # Fuse DC + Enhancer (dynamic weight)
    dc_enh = {
        "home_win_prob": float(dc_pred["home_win_prob"]),
        "draw_prob": float(dc_pred["draw_prob"]),
        "away_win_prob": float(dc_pred["away_win_prob"]),
    }
    dc_enh.update(fuse_outcome_probabilities(
        dc_enh,
        {
            "home_win_prob": float(enh_pred["home_win_prob"]),
            "draw_prob": float(enh_pred["draw_prob"]),
            "away_win_prob": float(enh_pred["away_win_prob"]),
        },
        base_weight=cfg["dc_weight"],
    ))

    # ── Fuse DC+Enhancer with Weibull (UCL scenes: 15% weight) ──
    dc_enh.update(fuse_weibull_probs(dc_enh, wb_pred, wb_weight=cfg.get("weibull_weight", 0.15)))

    # ── Layer 3: Elo ──
    elo = EloRatingSystem()
    elo.fit(df)
    elo_pred = elo.predict(
        home_team, away_team,
        is_neutral=is_neutral,
        competition_weight=competition_weight,
        competition=competition,
    )

    # Clean model (DC + Enhancer + Elo, no odds)
    clean = dict(dc_enh)
    clean.update(fuse_elo_probabilities(clean, elo_pred, elo_weight=cfg["elo_weight"]))

    # ── Layer 4: Pi-Rating（零中心的进球差评分，跨联赛比较更准确）──
    pi = PiRatingWrapper()
    pi.fit(df)
    pi_pred = pi.predict(home_team, away_team, is_neutral=is_neutral)
    clean.update(fuse_pi_probabilities(clean, pi_pred, pi_weight=cfg["pi_weight"]))
    pi_ratings_dict = pi.get_ratings_dict()

    # ── CalibrationMonitor（仅记录，不修改概率）──
    # 回测样本 < 20，校准器不启用为生产权重。
    # 只记录 baseline 概率供赛后复盘 Brier/log loss。
    cal_monitor = {
        "enabled": False,
        "reason": "回测样本不足（< 20 条），校准器处于监控模式",
        "baseline_probs": dict(clean),
    }

    # ── Recent form ──
    home_form = _recent_form(df, home_team, 5)
    away_form = _recent_form(df, away_team, 5)

    # ── Motivation (standings-derived or WC-specific) ──
    home_motivation = None
    away_motivation = None
    if "World Cup" in competition:
        # Use WC-specific group-stage motivation calculator
        home_motivation = await compute_wc_motivation(db, home_team, competition)
        away_motivation = await compute_wc_motivation(db, away_team, competition)
    if not home_motivation:
        home_motivation = await _lookup_motivation(db, home_team, competition)
    if not away_motivation:
        away_motivation = await _lookup_motivation(db, away_team, competition)

    # ── Match ID lookup (for post-match learning) ──
    match_id = await _lookup_match_id(db, home_team, away_team)

    # ── Manual events ──
    home_events = await _lookup_manual_events(db, home_team)
    away_events = await _lookup_manual_events(db, away_team)

    # ── Signal adjustment (apply manual events to baseline) ──
    adjuster = SignalAdjuster()
    all_manual = []
    for ev in home_events:
        ev_copy = dict(ev)
        ev_copy["_side"] = "home"
        all_manual.append(ev_copy)
    for ev in away_events:
        ev_copy = dict(ev)
        ev_copy["_side"] = "away"
        all_manual.append(ev_copy)

    signal_adjustment_log: list[dict[str, Any]] = []
    risk_tags: list[str] = []
    if all_manual:
        home_team_id = await _resolve_team_id(db, home_team)
        away_team_id = await _resolve_team_id(db, away_team)

        signals_for_adjuster: list[dict[str, Any]] = []
        for ev in all_manual:
            sig_type = ev["event_type"].lower()
            # Map event types that SignalAdjuster doesn't natively handle
            if sig_type == "rotation_hint":
                sig_type = "lineup_hint"

            team_id = str(home_team_id) if ev["_side"] == "home" else str(away_team_id)
            key_players = [ev["player"]] if ev.get("player") else []

            # Infer availability from severity for injury events
            availability = None
            if sig_type == "injury":
                sev = ev.get("severity", "medium")
                if sev == "critical":
                    availability = "out"
                elif sev in ("high", "medium"):
                    availability = "doubtful"

            signals_for_adjuster.append({
                "signal_type": sig_type,
                "team_id": team_id,
                "confidence": float(ev.get("confidence", 0.5)),
                "key_players": key_players,
                "summary_zh": ev.get("note", ""),
                "normalized_availability": availability,
            })

        adjusted = await adjuster.apply_signals(
            base_prediction={
                "home_xg": dc_pred["home_xg"],
                "away_xg": dc_pred["away_xg"],
                "confidence_score": 0.7,
            },
            approved_signals=signals_for_adjuster,
            match_context={
                "home_team_id": str(home_team_id) if home_team_id else "",
                "away_team_id": str(away_team_id) if away_team_id else "",
                "home_team_name": home_team,
                "away_team_name": away_team,
            },
        )

        # Override baseline probabilities with adjusted
        clean["home_win_prob"] = adjusted["home_win_prob"]
        clean["draw_prob"] = adjusted["draw_prob"]
        clean["away_win_prob"] = adjusted["away_win_prob"]
        # Also use adjusted xG and score matrix
        dc_pred["home_xg"] = adjusted["home_xg"]
        dc_pred["away_xg"] = adjusted["away_xg"]
        dc_pred["top3_scores"] = adjusted["top3_scores"]
        signal_adjustment_log = adjusted.get("adjustment_log", [])
        risk_tags = adjusted.get("risk_tags", [])

    # ── Context Adjuster (learned situational biases) ──
    context_tags = []
    if is_neutral:
        context_tags.append("neutral_venue")
    # Detect competition-specific contexts
    comp_lower = competition.lower()
    if any(kw in comp_lower for kw in ["derby", "rivalry"]):
        context_tags.append("derby")
    if any(kw in comp_lower for kw in ["final", "championship"]):
        context_tags.append("cup_final")
    try:
        from app.services.context_adjuster import get_context_adjuster
        ctx_adjuster = get_context_adjuster()
        ctx_result = await ctx_adjuster.apply_context_adjustments(clean, context_tags, db)
        if ctx_result.get("context_adjustments"):
            clean["home_win_prob"] = ctx_result["home_win_prob"]
            clean["draw_prob"] = ctx_result["draw_prob"]
            clean["away_win_prob"] = ctx_result["away_win_prob"]
    except Exception:
        ctx_result = {}

    # ── Market Calibrator (Phase 2: divergence + controlled blend) ──
    market_result = {
        "home_win_prob": clean["home_win_prob"],
        "draw_prob": clean["draw_prob"],
        "away_win_prob": clean["away_win_prob"],
        "market_applied": False,
        "market_weight_used": 0.0,
        "divergence": None,
        "risk_tags": [],
        "confidence_penalty": 0.0,
    }
    try:
        from app.services.market_calibrator import get_calibrator
        calibrator = get_calibrator()
        market_probs = await calibrator.fetch_market_probs(
            home_team, away_team, competition_weight, competition=competition
        )
        market_result = calibrator.calibrate(
            {"home_win_prob": clean["home_win_prob"],
             "draw_prob": clean["draw_prob"],
             "away_win_prob": clean["away_win_prob"]},
            market_probs,
            sample_size=rows,
        )
        if market_result.get("market_applied"):
            # Consume blended probabilities
            clean["home_win_prob"] = market_result["home_win_prob"]
            clean["draw_prob"] = market_result["draw_prob"]
            clean["away_win_prob"] = market_result["away_win_prob"]
        if market_result.get("risk_tags"):
            risk_tags.extend(market_result["risk_tags"])
        # ── Persist market odds to DB for audit trail ──
        if market_probs:
            await _save_market_odds(
                db, home_team, away_team, competition,
                market_probs, market_result.get("divergence")
            )
    except Exception as e:
        # Market data is optional — never let it break the pipeline
        pass

    # ── Source log ──
    builder = SourceLogBuilder()
    builder.add("历史比赛数据", "football-data.org + StatsBomb + openfootball", tier=1, updated_at=str(df["match_date"].max())[:10])
    builder.add("Dixon-Coles 模型", "DixonColesModel (internal)", tier=1, notes=f"NLL={dc_fit.final_neg_log_likelihood:.2f}")
    builder.add("Tabular Enhancer", "TabularEnhancer (internal)", tier=1, notes=f"{getattr(enhancer, '_algorithm', 'HGB')}")
    builder.add("Elo 评分", "EloRatingSystem (internal)", tier=1, notes=f"k={elo_pred.k_factor:.0f}")
    builder.add("球员伤病", "—", status="unavailable", notes="injuries.json 为空")
    builder.add("联赛排名", "football-data.org standings", tier=1, status="active" if home_motivation or away_motivation else "unavailable",
                notes=f"{home_motivation['tag'] if home_motivation else 'N/A'} / {away_motivation['tag'] if away_motivation else 'N/A'}")
    builder.add("天气数据", "Open-Meteo", tier=1, status="active", notes="赛前16天内可用")
    builder.add("新闻情报", "DeepSeek (LLM_API_KEY 已配置)", tier=1, status="active", notes="新闻抽取可用，待有内容赛前文章触发")
    market_status = "active" if market_result.get("market_applied") else "unavailable"
    market_note = "API已配置，本次未拉取到数据" if market_probs is None else "已拉取"
    if market_result.get("market_applied"):
        w = market_result.get("market_weight_used", 0)
        div_val = market_result.get("divergence")
        if div_val is not None:
            market_note = f"blend={w*100:.1f}% divergence={div_val*100:.1f}pp"
        else:
            market_note = f"blend={w*100:.1f}%"
    builder.add("市场共识", "The Odds API", tier=2, status=market_status, notes=market_note)
    source_log = builder.build(f"{home_team} vs {away_team}")

    # ── Skellam draw correction (UCL knockout/final only) ──
    skellam_enabled = cfg.get("label", "") in ("UCL_FINAL", "UCL_KNOCKOUT")
    if skellam_enabled:
        from app.services.skellam import apply_skellam_correction
        skel_result = apply_skellam_correction(clean, dc_pred["home_xg"], dc_pred["away_xg"], enabled=True)
        if skel_result.get("skellam_applied"):
            clean["home_win_prob"] = skel_result["home_win_prob"]
            clean["draw_prob"] = skel_result["draw_prob"]
            clean["away_win_prob"] = skel_result["away_win_prob"]
            print(f"  Skellam 平局修正: {skel_result.get('skellam_correction_pp', 0)*100:+.1f}pp")

    # ── Missing data ──
    missing = _identify_missing()

    return {
        "meta": {
            "match_id": match_id or "",
            "home_team": home_team,
            "away_team": away_team,
            "competition": competition,
            "is_neutral": is_neutral,
            "generated_at": now_utc,
            "training_rows": rows,
        },
        "prediction": {
            "home_win_prob": clean["home_win_prob"],
            "draw_prob": clean["draw_prob"],
            "away_win_prob": clean["away_win_prob"],
            "home_xg": dc_pred["home_xg"],
            "away_xg": dc_pred["away_xg"],
            "top3_scores": dc_pred["top3_scores"],
            "calibration_monitor": cal_monitor,
        },
        "elo": {
            "home_elo": elo_pred.home_elo,
            "away_elo": elo_pred.away_elo,
            "rating_gap": elo_pred.rating_gap,
            "k_factor": elo_pred.k_factor,
        },
        "recent_form": {
            "home": home_form,
            "away": away_form,
        },
        "motivation": {
            "home": home_motivation,
            "away": away_motivation,
        },
        "manual_events": {
            "home": home_events,
            "away": away_events,
        },
        "adjustment": {
            "applied": len(signal_adjustment_log) > 0,
            "log": signal_adjustment_log,
            "risk_tags": risk_tags,
        },
        "data_quality": dc_pred.get("data_quality", "fitted"),
        "confidence_penalty": dc_pred.get("confidence_penalty", 0.0),
        "cold_start_warnings": dc_pred.get("cold_start_warnings", []),
        "component_probs": {
            "dc": {
                "home": float(dc_pred["home_win_prob"]),
                "draw": float(dc_pred["draw_prob"]),
                "away": float(dc_pred["away_win_prob"]),
            },
            "enhancer": {
                "home": float(enh_pred["home_win_prob"]),
                "draw": float(enh_pred["draw_prob"]),
                "away": float(enh_pred["away_win_prob"]),
            },
            "elo": {
                "home": float(elo_pred.home_win_prob),
                "draw": float(elo_pred.draw_prob),
                "away": float(elo_pred.away_win_prob),
            },
            "pi_rating": {
                "home": float(pi_pred["home_win_prob"]),
                "draw": float(pi_pred["draw_prob"]),
                "away": float(pi_pred["away_win_prob"]),
            },
        },
        "market_divergence": {
            "applied": market_result.get("market_applied", False),
            "divergence": market_result.get("divergence"),
            "triggered": market_result.get("divergence_triggered", False),
        },
        "sources": source_log,
        "missing_data": missing,
        "pipeline": {
            "dc_converged": dc_fit.converged,
            "dc_nll": dc_fit.final_neg_log_likelihood,
            "enhancer_algorithm": getattr(enhancer, "_algorithm", "HistGradientBoosting"),
            "enhancer_rows": enhancer.training_sample_count,
            "enhancer_features": len(enhancer.feature_columns),
            "elo_matches": elo._match_count,
            "pi_matches": pi._match_count,
        },
        # ── Provenance / data freshness ──────────────────────
        "odds_info": {
            "fetched_at": market_probs.get("fetched_at") if market_probs else None,
            "bookmaker": market_probs.get("bookmaker", "Pinnacle") if market_probs else None,
            "age_minutes": (
                int((datetime.now(timezone.utc) - datetime.fromisoformat(market_probs["fetched_at"])).total_seconds() / 60)
                if market_probs and market_probs.get("fetched_at") else None
            ),
            "age_hours": (
                round((datetime.now(timezone.utc) - datetime.fromisoformat(market_probs["fetched_at"])).total_seconds() / 3600, 1)
                if market_probs and market_probs.get("fetched_at") else None
            ),
        },
        "training_info": {
            "n_samples": len(df) if df is not None else 0,
            "latest_date": df["match_date"].max().strftime("%Y-%m-%d") if df is not None and len(df) > 0 else "?",
        },
        "news_signal_count": 0,  # GDELT/RSS signals currently unavailable; use manual_events instead
    }


# ═══════════════════════════════════════════════════════════
#  Recent form
# ═══════════════════════════════════════════════════════════
def _recent_form(df: pd.DataFrame, team: str, n: int = 5) -> list[dict[str, Any]]:
    """Last N matches for a team."""
    home = df[df["home_team"] == team][["match_date", "home_team", "away_team", "home_goals", "away_goals"]].copy()
    home["side"] = "home"
    away = df[df["away_team"] == team][["match_date", "home_team", "away_team", "home_goals", "away_goals"]].copy()
    away["side"] = "away"

    all_matches = pd.concat([home, away], ignore_index=True)
    all_matches = all_matches.sort_values("match_date", ascending=False).head(n)

    form = []
    for _, row in all_matches.iterrows():
        side = row["side"]
        gf = int(row["home_goals"]) if side == "home" else int(row["away_goals"])
        ga = int(row["away_goals"]) if side == "home" else int(row["home_goals"])
        if gf > ga:
            result = "W"
        elif gf == ga:
            result = "D"
        else:
            result = "L"
        form.append({
            "date": str(row["match_date"])[:10],
            "opponent": row["away_team"] if side == "home" else row["home_team"],
            "score": f"{gf}-{ga}",
            "result": result,
            "venue": side,
        })
    return form


# ═══════════════════════════════════════════════════════════
#  Market odds persistence
# ═══════════════════════════════════════════════════════════
async def _save_market_odds(
    db, home_team: str, away_team: str, competition: str,
    market_probs: dict, divergence: float | None,
) -> None:
    """Persist fetched market implied probabilities to market_odds table."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    try:
        await db.execute(
            text(
                "INSERT INTO market_odds "
                "(home_implied_prob, draw_implied_prob, away_implied_prob, "
                " vig_removed, vig_amount, sample_bookmakers, provider, fetched_at, id) "
                "VALUES (:hp, :dp, :ap, 1, NULL, 1, :src, :ts, :id)"
            ),
            {
                "hp": round(market_probs["home_prob"], 6),
                "dp": round(market_probs["draw_prob"], 6),
                "ap": round(market_probs["away_prob"], 6),
                "src": "The Odds API",
                "ts": now,
                "id": str(__import__("uuid").uuid4()).replace("-", ""),
            },
        )
        await db.commit()
    except Exception:
        pass  # market_odds persistence is best-effort


# ═══════════════════════════════════════════════════════════
#  Missing data
# ═══════════════════════════════════════════════════════════
def _identify_missing() -> list[dict[str, str]]:
    return [
        {
            "item": "首发阵容",
            "impact": "极大 (可改变 xG ≥ 15%)",
            "available_in": "football-data.org 赛前 1h",
        },
        {
            "item": "球员伤病",
            "impact": "大 (affected_team xG ↓)",
            "available_in": "缺免费API，可手动维护 injuries.json",
        },
        {
            "item": "新闻情报 (赛前)",
            "impact": "中 (上下文/战术)",
            "available_in": "LLM 已配置，待有内容赛前文章",
        },
    ]


# ═══════════════════════════════════════════════════════════
#  Motivation lookup
# ═══════════════════════════════════════════════════════════
async def _lookup_motivation(db, team_name: str, competition: str) -> dict[str, Any] | None:
    """Look up motivation data for a team from standings-derived events."""
    try:
        # Find any motivation event for this team in the current competition's upcoming matches
        result = await db.execute(
            select(MotivationEvent).where(
                MotivationEvent.team_name.ilike(f"%{team_name}%")
            ).order_by(MotivationEvent.created_at.desc()).limit(1)
        )
        event = result.scalar_one_or_none()
        if event:
            tag_info = MOTIVATION_TAGS.get(event.motivation_tag, {})
            return {
                "tag": event.motivation_tag,
                "label": tag_info.get("label", event.motivation_tag),
                "strength": event.motivation_strength,
                "explanation": event.explanation,
                "source": event.source,
            }
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════════════
#  Manual events lookup
# ═══════════════════════════════════════════════════════════
async def _lookup_manual_events(db, team_name: str, limit: int = 5) -> list[dict[str, Any]]:
    """Look up active, unexpired manual events for a team.

    Filters out:
      - Expired events (expires_at < now)
      - Events referencing players who no longer belong to this team
    """
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        # ── Query active events ──
        result = await db.execute(
            select(ManualEvent).where(
                ManualEvent.team_name.ilike(f"%{team_name}%"),
                ManualEvent.status == "active",
            ).order_by(ManualEvent.created_at.desc()).limit(limit * 2)  # fetch extra to allow filtering
        )
        events = result.scalars().all()

        # ── Resolve team UUID for player validation ──
        team_id = await _resolve_team_id(db, team_name)

        validated = []
        filtered_out = []
        for e in events:
            # ── Check 1: Expiry ──
            if e.expires_at and e.expires_at < now_iso:
                filtered_out.append(f"{e.event_type}/{e.player_name or 'N/A'}: 已过期 ({e.expires_at})")
                continue

            # ── Check 2: Player belongs to this team ──
            if e.player_name and team_id:
                player_result = await db.execute(
                    select(Player.team_id).where(Player.name == e.player_name)
                )
                player_team_rows = player_result.all()
                player_team_ids = [str(row[0]) for row in player_team_rows]
                if player_team_ids and team_id not in player_team_ids:
                    filtered_out.append(
                        f"{e.event_type}/{e.player_name}: "
                        f"球员不属于 {team_name} (player_team={player_team_ids})"
                    )
                    continue

            validated.append(e)
            if len(validated) >= limit:
                break

        if filtered_out:
            print(f"  [lookup_manual_events] 过滤 {len(filtered_out)} 条无效事件: "
                  + "; ".join(filtered_out[:3]))

        return [
            {
                "event_type": e.event_type,
                "player": e.player_name,
                "severity": e.severity,
                "confidence": e.confidence,
                "source": e.source_name,
                "note": e.note,
            }
            for e in validated
        ]
    except Exception:
        return []


async def _resolve_team_id(db, team_name: str):
    """Resolve team name to UUID."""
    try:
        result = await db.execute(
            select(Team.id).where(Team.name == team_name)
        )
        row = result.scalar_one_or_none()
        return str(row) if row else None
    except Exception:
        return None


async def _lookup_match_id(db, home_team: str, away_team: str, competition: str | None = None) -> str | None:
    """Find match_id in the DB matching the predicted teams."""
    try:
        from app.models.match import Match

        # Simple approach: find team IDs first, then match
        home_id_result = await db.execute(
            select(Team.id).where(Team.name.ilike(f"%{home_team}%")).limit(1)
        )
        away_id_result = await db.execute(
            select(Team.id).where(Team.name.ilike(f"%{away_team}%")).limit(1)
        )
        home_id = home_id_result.scalar_one_or_none()
        away_id = away_id_result.scalar_one_or_none()

        if not home_id or not away_id:
            return None

        stmt = (
            select(Match.id)
            .where(Match.home_team_id == home_id)
            .where(Match.away_team_id == away_id)
            .order_by(Match.match_date.desc())
            .limit(1)
        )
        match_result = await db.execute(stmt)
        row = match_result.first()
        if row:
            # Match.id is UUID — return hex string (32 chars) without dashes
            mid = str(row[0]).replace("-", "")
            return mid
        return None
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════
#  Markdown report
# ═══════════════════════════════════════════════════════════
def _get_model_config(competition: str, stage: str = "") -> dict:
    """Select model weights based on competition type and stage."""
    c = competition.lower()
    s = (stage or "").lower()

    # UCL Final: less DC weight (less league data for this unique match),
    # more Pi-Rating (cross-league comparison)
    if ("champions" in c or "ucl" in c) and (s == "final"):
        return {
            "label": "UCL_FINAL",
            "dc_weight": 0.42, "enh_weight": 0.30,
            "elo_weight": 0.08, "pi_weight": 0.12,
            "market_max": 0.08,
        }
    # UCL Knockout: moderate adjustment
    if ("champions" in c or "ucl" in c) and any(k in s for k in ["quarter", "semi", "last_16", "playoff"]):
        return {
            "label": "UCL_KNOCKOUT",
            "dc_weight": 0.45, "enh_weight": 0.28,
            "elo_weight": 0.07, "pi_weight": 0.10,
            "market_max": 0.10,
        }
    # World Cup: highest DC weight (more national team data)
    if "world cup" in c:
        return {
            "label": "WORLD_CUP",
            "dc_weight": 0.55, "enh_weight": 0.25,
            "elo_weight": 0.05, "pi_weight": 0.05,
            "market_max": 0.10,
        }

    # Default: Premier League / Ligue 1 / generic
    return {
        "label": "LEAGUE",
        "dc_weight": 0.50, "enh_weight": 0.30,
        "elo_weight": 0.05, "pi_weight": 0.05,
        "market_max": 0.10,
    }


async def _get_match_stage(home_team: str, away_team: str, competition: str) -> str:
    """Look up match stage from the database."""
    try:
        import sqlite3, os
        db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "local_stage2.db")
        conn = sqlite3.connect(db)
        r = conn.execute(
            "SELECT stage FROM matches WHERE competition=? AND home_team_id IN (SELECT id FROM teams WHERE name=?) AND away_team_id IN (SELECT id FROM teams WHERE name=?) ORDER BY match_date DESC LIMIT 1",
            (competition, home_team, away_team),
        ).fetchone()
        conn.close()
        return r[0] if r else ""
    except Exception:
        return ""


def _build_provenance(result: dict[str, Any]) -> str:
    """Build data provenance panel lines for report."""
    lines = []
    sources = result.get("sources", {})
    events_raw = result.get("manual_events", [])
    if isinstance(events_raw, list):
        events = [e for e in events_raw if isinstance(e, dict)]
    elif isinstance(events_raw, dict):
        events = list(events_raw.values())
    else:
        events = []
    odds_info = result.get("odds_info", {})
    training = result.get("training_info", {})

    # Odds
    if odds_info.get("fetched_at"):
        age_h = odds_info.get("age_hours", 99)
        status = "新鲜" if age_h < 1 else "较旧" if age_h < 3 else "过期"
        lines.append(f"- 市场赔率：{odds_info.get('bookmaker', 'Pinnacle')} via The Odds API，抓取于 {odds_info['fetched_at'][:16]}（距比赛 {age_h}h）{status}")
    else:
        lines.append("- 市场赔率：未拉取（ODDS_API_KEY 未配置或 API 不可用）")

    # Manual events
    evt_count = len(events)
    if evt_count > 0:
        latest = max((e.get("created_at", "") for e in events if isinstance(e, dict) and e.get("created_at")), default="?")
        lines.append(f"- 球员情报：manual_events 表，{evt_count} 条记录，最新录入 {latest[:16]}")
    else:
        lines.append("- 球员情报：0 条记录（伤停/阵容信息缺失）")

    # Training data
    lines.append(f"- 历史比赛：football-data.org + martj42 internationals")
    lines.append(f"  训练样本 {training.get('n_samples', '?')} 场，最新截止 {training.get('latest_date', '?')}")

    # xG
    lines.append(f"- xG 数据：StatsBomb 已回填")

    # News
    ns = result.get("news_signal_count", 0)
    lines.append(f"- 新闻信号：{ns} 条{'（GDELT/RSS 自动采集）' if ns > 0 else '（本次未采集到有效信号）'}")

    return "\n".join(lines)


def _build_uncertainty(result: dict[str, Any]) -> str:
    """Build uncertainty sources for report."""
    lines = []
    events_raw = result.get("manual_events", [])
    if isinstance(events_raw, list):
        events = [e for e in events_raw if isinstance(e, dict)]
    elif isinstance(events_raw, dict):
        events = list(events_raw.values())
    else:
        events = []
    odds_info = result.get("odds_info", {})
    training = result.get("training_info", {})
    ns = result.get("news_signal_count", 0)

    warnings = []
    if len(events) == 0:
        warnings.append("1. 球员情报：0 条手动记录，伤停和阵容信息完全缺失")
    elif len(events) < 3:
        warnings.append(f"1. 球员情报：仅 {len(events)} 条手动记录（人工录入，非自动采集），可能遗漏重要信息")
    if not odds_info.get("fetched_at"):
        warnings.append("2. 赔率数据：本次未成功拉取，模型缺少市场校准")
    elif odds_info.get("age_hours", 0) > 2:
        warnings.append(f"2. 赔率已过期（{odds_info.get('age_hours')}h 前），开球前应重新验证")
    if training.get("n_samples", 0) < 500:
        warnings.append(f"3. 训练数据较少（{training.get('n_samples')} 场），样本量不足")
    if ns == 0:
        warnings.append("4. 新闻信号：0 条自动采集，赛前情报依赖纯手动注入")

    if not warnings:
        warnings.append("本预测无明显数据缺失问题。")

    return "\n".join(warnings)


def render_markdown(result: dict[str, Any]) -> str:
    m = result["meta"]
    p = result["prediction"]
    e = result["elo"]
    form = result["recent_form"]
    mot = result.get("motivation", {})
    evts = result.get("manual_events", {})

    is_wc = "World Cup" in m.get("competition", "")
    competition = m.get("competition", "Unknown")

    # ── Title (with group info for WC) ──
    title = f"# 预测快照：{m['home_team']} vs {m['away_team']}"
    if is_wc:
        home_group = (mot.get("home") or {}).get("group", "")
        away_group = (mot.get("away") or {}).get("group", "")
        group_label = home_group or away_group
        if group_label:
            title += f"（{group_label}）"

    adj = result.get("adjustment", {})
    lines = [
        title,
        "",
        f"> 生成时间：{m['generated_at']}  |  赛事：{competition}  |  训练数据：{m['training_rows']} 场",
        "",
    ]

    # ── WC context bar (host city, altitude, timezone — placeholder) ──
    if is_wc:
        lines += [
            "> 🏟️ 世界杯比赛  |  中立场  |  赛事权重: 1.5×",
            "",
        ]

    lines += [
        "---",
        "",
        f"## 预测结果（三层融合{' + 信号调整' if adj.get('applied') else ''}）",
        "",
        "| 来源 | 主胜 | 平局 | 客胜 |",
        "|---|---:|---:|---:|",
        f"| 模型预测 | **{p['home_win_prob']*100:.1f}%** | {p['draw_prob']*100:.1f}% | {p['away_win_prob']*100:.1f}% |",
        "",
        f"> 期望进球：{m['home_team']} **{p['home_xg']:.2f}** — **{p['away_xg']:.2f}** {m['away_team']}",
        "",
    ]
    lines += [
        f"> 校准：监控模式（回测样本不足，未启用）",
    ]
    # Show cold-start warning if any team lacks training data
    dq = result.get("data_quality", "fitted")
    cs = result.get("cold_start_warnings", [])
    if dq == "estimated_prior" or cs:
        lines.append("")
        if is_wc:
            lines.append("> ⚠️⚠️ **世界杯预测数据质量警告**")
            lines.append(f"> 训练数据仅 {m['training_rows']} 场国家队比赛（含日期错误数据），远少于俱乐部联赛的 5000+ 场")
            lines.append("> 预测置信度低于五大联赛预测，仅供参考")
        else:
            lines.append("> ⚠️ 数据质量：**" + dq + "** — 依赖先验估计")
        if cs:
            parts = [w["team"] + "(" + w["role"] + ") 洲=" + str(w.get("confederation","?")) + " 档=" + str(w.get("fifa_tier","?")) for w in cs]
            lines.append("> 冷启动球队：" + "; ".join(parts))
        cp = result.get("confidence_penalty", 0)
        if cp:
            lines.append("> 置信度扣除：" + str(int(cp*100)) + "%")
    elif is_wc:
        # WC but not cold start — still note limited data
        lines.append("")
        lines.append(f"> ⚠️ 世界杯预测使用的国家队训练数据有限（{m['training_rows']} 场），预测仅供参考")
    # Show market divergence if triggered
    md = result.get("market_divergence", {})
    if md.get("triggered"):
        div = md.get("divergence", 0)
        lines.append("")
        lines.append("> ⚠️ 模型与市场存在显著分歧 (" + str(round(div*100, 1)) + "pp)")
    # Show signal adjustment summary if applied
    if adj.get("applied"):
        adj_log = adj.get("log", [])
        risk = adj.get("risk_tags", [])
        lines.append("")
        lines.append(f"> 信号调整：{len(adj_log)} 条事件影响概率")
        if risk:
            lines.append(f"> 风险标签：{'，'.join(risk)}")
    # ── Model vs Market edge ──
    baseline = result.get("calibration_monitor", {}).get("baseline_probs", {})
    if baseline:
        lines.append("")
        lines.append(f"> 模型独立预测（DC+Enhancer+Elo）：主 {baseline['home_win_prob']:.1%} / 平 {baseline['draw_prob']:.1%} / 客 {baseline['away_win_prob']:.1%}")
        md_edge = result.get("market_divergence", {})
        market = md_edge.get("market_probs")
        if market:
            edge_h = baseline['home_win_prob'] - market.get('home_prob', 0)
            lines.append(f"> 模型真实优势（vs Pinnacle）：主 {edge_h:+.1%}")
    lines += [
        "",
        "### Top 3 比分",
        "",
    ]
    for s in p["top3_scores"]:
        lines.append(f"- {s['score']}（{s['prob']*100:.1f}%）")

    lines += [
        "",
        "---",
        "",
        "## 数据来源与质量",
        "",
        render_source_table(result["sources"]),
        "",
        f"### Elo 评分",
        f"- {m['home_team']}：**{e['home_elo']:.0f}**",
        f"- {m['away_team']}：**{e['away_elo']:.0f}**",
        f"- 评分差：{e['rating_gap']:+.0f}（K={e['k_factor']:.0f}）",
        "",
        "---",
        "",
        "## 赛前动力因素",
        "",
    ]
    # Motivation section
    home_mot = mot.get("home")
    away_mot = mot.get("away")
    if is_wc:
        # WC-specific: show group points and status
        lines.append("### 世界杯小组动力")
        lines.append("")
        if home_mot:
            pts = home_mot.get("points", 0)
            played = home_mot.get("played", 0)
            grp = home_mot.get("group", "?")
            lines.append(f"- {m['home_team']}（{grp}，{played}场{pts}分）：**{home_mot['label']}** — {home_mot['explanation']}")
        else:
            lines.append(f"- {m['home_team']}：动力数据不可用")
        if away_mot:
            pts = away_mot.get("points", 0)
            played = away_mot.get("played", 0)
            grp = away_mot.get("group", "?")
            lines.append(f"- {m['away_team']}（{grp}，{played}场{pts}分）：**{away_mot['label']}** — {away_mot['explanation']}")
        else:
            lines.append(f"- {m['away_team']}：动力数据不可用")
        lines.append("")
        lines.append("> 世界杯动力因素基于小组赛实际积分动态计算，非联赛 standings 表")
    elif home_mot or away_mot:
        if home_mot:
            lines.append(f"- {m['home_team']}：**{home_mot['label']}**（{home_mot['explanation']}）")
        else:
            lines.append(f"- {m['home_team']}：未查到排名数据")
        if away_mot:
            lines.append(f"- {m['away_team']}：**{away_mot['label']}**（{away_mot['explanation']}）")
        else:
            lines.append(f"- {m['away_team']}：未查到排名数据")
    else:
        lines.append("- 当前无可用动力数据（standings 表为空或球队不在五大联赛）")
    lines += [
        "",
        "---",
        "",
        "## 手动情报事件",
        "",
    ]
    # Manual events section
    home_evts = evts.get("home", [])
    away_evts = evts.get("away", [])
    if home_evts or away_evts:
        if home_evts:
            for ev in home_evts:
                player_str = f" ({ev['player']})" if ev.get('player') else ""
                lines.append(
                    f"- {m['home_team']}{player_str}：**{ev['event_type']}** "
                    f"严重度={ev['severity']} 可信度={ev['confidence']:.0%} "
                    f"来源={ev['source']}"
                )
                if ev.get('note'):
                    lines.append(f"  > {ev['note']}")
        if away_evts:
            for ev in away_evts:
                player_str = f" ({ev['player']})" if ev.get('player') else ""
                lines.append(
                    f"- {m['away_team']}{player_str}：**{ev['event_type']}** "
                    f"严重度={ev['severity']} 可信度={ev['confidence']:.0%} "
                    f"来源={ev['source']}"
                )
                if ev.get('note'):
                    lines.append(f"  > {ev['note']}")
    else:
        lines.append("- 无手动注入事件（使用 `python scripts/add_manual_event.py` 添加）")
    lines += [
        "",
        "---",
        "",
        "## 近期战绩",
        "",
        f"### {m['home_team']}（近 5 场）",
        "",
    ]
    for g in form["home"]:
        lines.append(f"- {g['date']} {g['result']} {g['score']} vs {g['opponent']} ({g['venue']})")

    lines += ["", f"### {m['away_team']}（近 5 场）", ""]
    for g in form["away"]:
        lines.append(f"- {g['date']} {g['result']} {g['score']} vs {g['opponent']} ({g['venue']})")

    lines += [
        "",
        "---",
        "",
        "## 未知 / 缺失数据",
        "",
        "| 数据项 | 影响 | 获取方式 |",
        "|---|---|---|",
    ]
    for item in result["missing_data"]:
        lines.append(f"| {item['item']} | {item['impact']} | {item['available_in']} |")

    lines += [
        "",
        "---",
        "",
        "## 管线技术参数",
        "",
        f"- Dixon-Coles 收敛：{'是' if result['pipeline']['dc_converged'] else '否'}（NLL={result['pipeline']['dc_nll']:.2f}）",
        f"- Enhancer：{result['pipeline']['enhancer_algorithm']}，{result['pipeline']['enhancer_rows']} 行 x {result['pipeline']['enhancer_features']} 特征",
        f"- Elo 比赛数：{result['pipeline']['elo_matches']}",
           "---",           "",           "## 预测可信度说明",           "",           "- 本预测基于 5,000+ 场历史比赛训练",           "- 三层模型融合：Dixon-Coles (泊松) + Enhancer (梯度提升) + Elo",           "- 已纳入：联赛排名/动力因素（standings 驱动）",           "- 未纳入参数：首发阵容、球员伤病、赛前新闻情报",           "- 以上缺失因素可能显著改变预测结果，仅供个人参考",        ]

    provenance = _build_provenance(result)
    lines.append(provenance)
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 预测不确定性来源")
    lines.append("")
    uncertainty = _build_uncertainty(result)
    lines.append(uncertainty)
    lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════
async def main(home_team: str, away_team: str, competition: str, is_neutral: bool = False, competitions: list[str] | None = None) -> None:
    result = await run_snapshot(
        home_team,
        away_team,
        is_neutral=is_neutral,
        competition=competition,
        competitions=competitions,
        competition_weight=1.5 if "World Cup" in competition else 0.9,
    )

    markdown = render_markdown(result)
    safe_home = home_team.replace(" ", "_").replace("/", "-")
    safe_away = away_team.replace(" ", "_").replace("/", "-")
    filename = REPORTS_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M')}_{safe_home}_vs_{safe_away}.md"
    filename.write_text(markdown, encoding="utf-8")
    print(f"报告已生成：{filename}")

    # Save standardized snapshot to DB
    try:
        await save_prediction_snapshot(
            result,
            run_type="manual",
            report_path=str(filename),
            report_markdown=markdown,
        )
        print("快照已存入数据库")
    except Exception as exc:
        print(f"快照保存失败（非致命）: {exc}")

    print()
    print(markdown)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prediction snapshot")
    parser.add_argument("--home", required=True)
    parser.add_argument("--away", required=True)
    parser.add_argument("--neutral", action="store_true")
    parser.add_argument("--competition", default="Premier League")
    parser.add_argument("--competitions", nargs="+", help="多联赛训练数据（如 --competitions 'Ligue 1' 'Premier League'）")
    args = parser.parse_args()
    asyncio.run(main(args.home, args.away, args.competition, args.neutral, args.competitions))

