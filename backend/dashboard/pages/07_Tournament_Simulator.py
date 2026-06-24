"""07_Tournament_Simulator.py — 赛事 Monte Carlo 模拟器页面"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import streamlit as st
import pandas as pd

from dashboard.db import db
from dashboard.dashboard_config import (
    SIMULATION_RUNS_OPTIONS,
    DEFAULT_SIMULATION_RUNS,
    PREDICTION_MODES,
    GROUPS,
)

st.title("赛事模拟器")
st.caption("FIFA World Cup 2026 全量 Monte Carlo 模拟")

# ── 控件 ──────────────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    runs = st.selectbox(
        "模拟次数",
        SIMULATION_RUNS_OPTIONS,
        index=SIMULATION_RUNS_OPTIONS.index(DEFAULT_SIMULATION_RUNS),
        key="sim_runs",
        help="次数越多越准确，但耗时更长",
    )
with col2:
    sim_mode = st.selectbox(
        "模型模式",
        ["standard", "full"],
        index=1,
        key="sim_mode",
        format_func=lambda m: PREDICTION_MODES.get(m, m),
    )

# ── 运行模拟 ──────────────────────────────────────────────────────────────────
if st.button("开始模拟", type="primary", key="sim_run"):
    try:
        from app.services.artifact_registry import load_registry, validate_bundle
        registry = load_registry()
        ok, missing = validate_bundle(registry, sim_mode)
        if not ok:
            st.error(f"缺少模型文件 ({sim_mode} 模式): {missing}。请先运行 train_models.py。")
            st.stop()
    except Exception as e:
        st.error(f"无法校验模型文件: {e}")
        st.stop()

    groups_data = db.get_wc26_groups()
    schedule = db.get_wc26_schedule()

    if not groups_data:
        st.error("未找到 WC26 小组数据。请先运行 seed_wc26_schedule.py。")
        st.stop()
    if not schedule:
        st.error("未找到 WC26 赛程数据。")
        st.stop()

    df_groups = pd.DataFrame(groups_data)
    group_matches = [
        m for m in schedule
        if m.get("stage") == "Group Stage" or m.get("stage", "").startswith("Group")
    ]
    if not group_matches:
        st.warning("未找到小组赛比赛，使用前 72 场赛程。")
        group_matches = schedule[:72]

    st.info(f"正在预测 {len(group_matches)} 场小组赛，然后运行 {runs:,} 次 Monte Carlo 模拟...")

    progress_bar = st.progress(0)
    status_text = st.empty()
    match_probs: dict[int, dict] = {}

    try:
        from app.services.prediction_core import (
            _load_dc, _load_enhancer, _load_elo, _load_pi, _load_training_df,
        )
        from app.services.prediction_timer import PredictionTimer
        from app.services.weights import get_weight_config
        from app.services.tabular_match_model import fuse_outcome_probabilities
        from app.services.elo_ratings import fuse_elo_probabilities
        from app.services.pi_ratings import fuse_pi_probabilities
        from app.services.weibull_model import WeibullWrapper, fuse_weibull_probs
        from app.services.tournament_simulator import TournamentSimulator
        from app.services.market.sync_provider import fetch_market_consensus_sync

        timer = PredictionTimer()
        training_df = _load_training_df(timer)
        match_date = training_df["match_date"].max().to_pydatetime()
        wc = get_weight_config("FIFA World Cup 2026", "Group Stage")

        # Fit Weibull once for all matches (best-effort)
        weibull = None
        try:
            wb = WeibullWrapper()
            if wb.fit(training_df):
                weibull = wb
        except Exception:
            pass

        dc = _load_dc(timer)
        enhancer = _load_enhancer(timer) if sim_mode in ("standard", "full") else None
        elo = _load_elo(timer) if sim_mode in ("standard", "full") else None
        pi_model = _load_pi(timer) if sim_mode == "full" else None

        market_count = 0
        for i, match in enumerate(group_matches):
            home = match.get("home_team", "")
            away = match.get("away_team", "")
            match_num = match.get("match_number", i + 1)

            if not home or not away:
                match_probs[match_num] = {"home": 0.33, "draw": 0.34, "away": 0.33}
                continue

            try:
                dc_pred = dc.predict_match(home, away, is_neutral_venue=True)
                fused = dict(dc_pred)

                # V4.0.5: Adaptive DC weight on divergence > 20pp
                if enhancer is not None:
                    enh_pred = enhancer.predict_match(
                        home_team=home, away_team=away, match_date=match_date,
                        competition_weight=1.0, is_neutral_venue=True, training_df=training_df,
                    )
                    dc_w_ef = float(wc.dc)
                    max_div_sim = max(
                        abs(dc_pred["home_win_prob"] - enh_pred["home_win_prob"]),
                        abs(dc_pred["draw_prob"] - enh_pred["draw_prob"]),
                        abs(dc_pred["away_win_prob"] - enh_pred["away_win_prob"]),
                    ) * 100
                    if max_div_sim > 20:
                        shift = min(0.15, (max_div_sim - 20) * 0.015)
                        dc_w_ef = max(0.30, wc.dc - shift)
                        enh_w_ef = 1.0 - dc_w_ef
                        fused = {
                            "home_win_prob": dc_pred["home_win_prob"] * dc_w_ef + enh_pred["home_win_prob"] * enh_w_ef,
                            "draw_prob": dc_pred["draw_prob"] * dc_w_ef + enh_pred["draw_prob"] * enh_w_ef,
                            "away_win_prob": dc_pred["away_win_prob"] * dc_w_ef + enh_pred["away_win_prob"] * enh_w_ef,
                        }
                    else:
                        fused = fuse_outcome_probabilities(fused, enh_pred, base_weight=wc.dc)

                if weibull is not None and weibull._fitted:
                    wb_pred = weibull.predict(home, away, True)
                    if wb_pred is not None:
                        fused = fuse_weibull_probs(fused, wb_pred, wb_weight=wc.weibull)

                if elo is not None:
                    elo_pred = elo.predict(home, away, is_neutral=True, competition_weight=1.0, competition="FIFA World Cup 2026")
                    fused = fuse_elo_probabilities(fused, elo_pred, elo_weight=wc.elo)

                if pi_model is not None:
                    pi_pred = pi_model.predict(home, away, is_neutral=True)
                    fused = fuse_pi_probabilities(fused, pi_pred, pi_weight=wc.pi)

                # ── Market consensus (R5-5: was missing from dashboard simulator) ──
                try:
                    market_raw = fetch_market_consensus_sync(home, away, "FIFA World Cup 2026", timeout=8.0)
                    if market_raw and not market_raw.get("degraded"):
                        market_home = market_raw["home_prob"]
                        market_draw = market_raw["draw_prob"]
                        market_away = market_raw["away_prob"]
                        model_market_div = max(
                            abs(fused["home_win_prob"] - market_home),
                            abs(fused["draw_prob"] - market_draw),
                            abs(fused["away_win_prob"] - market_away),
                        )
                        market_weight = wc.market_max
                        if model_market_div > 0.15:
                            boost = min(0.20, (model_market_div - 0.15) * 1.0)
                            market_weight = min(0.50, wc.market_max + boost)
                        fused_market = {
                            "home_win_prob": fused["home_win_prob"] * (1 - market_weight) + market_home * market_weight,
                            "draw_prob": fused["draw_prob"] * (1 - market_weight) + market_draw * market_weight,
                            "away_win_prob": fused["away_win_prob"] * (1 - market_weight) + market_away * market_weight,
                        }
                        total_m = sum(fused_market.values())
                        fused = {k: v / total_m for k, v in fused_market.items()}
                        market_count += 1
                except Exception:
                    pass  # Market is best-effort — continue without it

                total = fused["home_win_prob"] + fused["draw_prob"] + fused["away_win_prob"]
                if abs(total - 1.0) > 0.001:
                    fused["home_win_prob"] /= total
                    fused["draw_prob"] /= total
                    fused["away_win_prob"] /= total

                match_probs[match_num] = {
                    "home": fused["home_win_prob"],
                    "draw": fused["draw_prob"],
                    "away": fused["away_win_prob"],
                }
            except Exception:
                match_probs[match_num] = {"home": 0.33, "draw": 0.34, "away": 0.33}

            progress_bar.progress((i + 1) / len(group_matches))
            status_text.text(f"正在预测第 {i + 1}/{len(group_matches)} 场: {home} vs {away}  [市场: {market_count}/{i+1}]")

        status_text.text(f"预测完成 ({market_count}/{len(group_matches)} 场有市场数据). 正在运行 Monte Carlo 模拟...")
        progress_bar.progress(1.0)

        # ── R5-4 fix: Use TournamentSimulator (proper bracket-based knockout)
        # instead of random.shuffle() which made knockout stages pure-luck.
        # TournamentSimulator uses probability-weighted Poisson scoring for both
        # group and knockout stages, and follows the real WC26 bracket structure.
        group_teams = {}
        for gn in GROUPS:
            gt = df_groups[df_groups["group_name"] == gn]["team_name"].tolist()
            if gt:
                group_teams[gn] = gt

        all_teams = sorted(df_groups["team_name"].unique())

        sim = TournamentSimulator(runs=runs, seed=42)
        sim.load_teams(group_teams)
        # Minimal schedule — only needed for validation; group/knockout stages
        # use hardcoded GROUP_MATCHUPS and R32_SPECS internally.
        sim.schedule = {0: {"stage": "Group Stage"}}

        # Set match probabilities for all 72 group matches from predictions
        for gm in group_matches:
            h = gm.get("home_team", "")
            a = gm.get("away_team", "")
            mn = gm.get("match_number", 0)
            if h and a and mn in match_probs:
                try:
                    sim.set_match_probability(h, a, {
                        "home_win": match_probs[mn]["home"],
                        "draw": match_probs[mn]["draw"],
                        "away_win": match_probs[mn]["away"],
                    })
                except ValueError:
                    pass  # Already set or probabilities don't sum to 1

        results = sim.run()
        status_text.text(f"模拟完成: {runs:,} 次")

        st.subheader(f"模拟结果 ({runs:,} 次 — 含概率对阵淘汰赛)")

        results_data = []
        for team in all_teams:
            group = df_groups[df_groups["team_name"] == team]["group_name"].values
            group_name = group[0] if len(group) > 0 else "?"
            tp = results.get(team)
            if tp is None:
                results_data.append({
                    "球队": team,
                    "小组": group_name,
                    "小组第一": "0.0%",
                    "小组出线": "0.0%",
                    "16 强": "0.0%",
                    "8 强": "0.0%",
                    "4 强": "0.0%",
                    "决赛": "0.0%",
                    "冠军": "0.0%",
                })
                continue
            results_data.append({
                "球队": team,
                "小组": group_name,
                "小组第一": f"{tp.group_win_prob * 100:.1f}%",
                "小组出线": f"{tp.advance_prob * 100:.1f}%",
                "16 强": f"{tp.round_of_32_prob * 100:.1f}%",
                "8 强": f"{tp.round_of_16_prob * 100:.1f}%",
                "4 强": f"{tp.quarter_final_prob * 100:.1f}%",
                "决赛": f"{tp.semi_final_prob * 100:.1f}%",
                "冠军": f"{tp.champion_prob * 100:.1f}%",
            })

        df_results = pd.DataFrame(results_data)
        df_results["_排序"] = df_results["冠军"].str.rstrip("%").astype(float)
        df_results = df_results.sort_values("_排序", ascending=False).drop(columns=["_排序"])

        st.subheader("夺冠热门 Top 10")
        st.dataframe(df_results.head(10), use_container_width=True, hide_index=True)

        st.subheader("全部球队")
        st.dataframe(df_results, use_container_width=True, hide_index=True, height=600)

        st.session_state["cached_sim_results"] = df_results
        st.session_state["cached_sim_runs_count"] = runs

    except Exception as e:
        st.error(f"模拟失败: {e}")
        import traceback
        st.code(traceback.format_exc())

else:
    if "cached_sim_results" in st.session_state:
        st.info(f"显示缓存结果 ({st.session_state.get('cached_sim_runs_count', '?')} 次模拟)")
        st.dataframe(st.session_state["cached_sim_results"], use_container_width=True, hide_index=True, height=600)
    else:
        st.info("选择参数后点击「开始模拟」")

st.divider()
st.caption("Monte Carlo 模拟 — 概率对阵淘汰赛。完整对阵模拟请使用 CLI: python scripts/simulate_wc26.py")
