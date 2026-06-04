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

        timer = PredictionTimer()
        training_df = _load_training_df(timer)
        match_date = training_df["match_date"].max().to_pydatetime()
        wc = get_weight_config("FIFA World Cup 2026")

        dc = _load_dc(timer)
        enhancer = _load_enhancer(timer) if sim_mode in ("standard", "full") else None
        elo = _load_elo(timer) if sim_mode in ("standard", "full") else None
        pi_model = _load_pi(timer) if sim_mode == "full" else None

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

                if enhancer is not None:
                    enh_pred = enhancer.predict_match(
                        home_team=home, away_team=away, match_date=match_date,
                        competition_weight=0.5, is_neutral_venue=True, training_df=training_df,
                    )
                    fused = fuse_outcome_probabilities(fused, enh_pred, base_weight=wc.dc)

                if elo is not None:
                    elo_pred = elo.predict(home, away, is_neutral=True, competition_weight=0.5, competition="FIFA World Cup 2026")
                    fused = fuse_elo_probabilities(fused, elo_pred, elo_weight=wc.elo)

                if pi_model is not None:
                    pi_pred = pi_model.predict(home, away, is_neutral=True)
                    fused = fuse_pi_probabilities(fused, pi_pred, pi_weight=wc.pi)

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
            status_text.text(f"正在预测第 {i + 1}/{len(group_matches)} 场: {home} vs {away}")

        status_text.text("正在运行 Monte Carlo 模拟...")
        progress_bar.progress(1.0)

        import random
        random.seed(42)

        team_advance = {}
        team_group_win = {}
        team_champion = {}
        team_round16 = {}
        team_quarter = {}
        team_semi = {}
        team_final = {}

        all_teams = list(df_groups["team_name"].unique())
        for t in all_teams:
            team_advance[t] = 0
            team_group_win[t] = 0
            team_champion[t] = 0
            team_round16[t] = 0
            team_quarter[t] = 0
            team_semi[t] = 0
            team_final[t] = 0

        group_teams = {}
        for gn in GROUPS:
            gt = df_groups[df_groups["group_name"] == gn]["team_name"].tolist()
            if gt:
                group_teams[gn] = gt

        group_match_map = {}
        for m in group_matches:
            gn = m.get("group_name", "")
            if gn and gn in group_teams:
                group_match_map.setdefault(gn, []).append(m)

        for run_idx in range(runs):
            group_standings = {}
            for gn, teams in group_teams.items():
                standings = {t: {"pts": 0, "gd": 0, "gf": 0} for t in teams}
                for gm in group_match_map.get(gn, []):
                    h = gm.get("home_team", "")
                    a = gm.get("away_team", "")
                    mn = gm.get("match_number", 0)
                    probs = match_probs.get(mn, {"home": 0.33, "draw": 0.34, "away": 0.33})
                    r = random.random()
                    if r < probs["home"]:
                        home_g = random.choices([1, 2, 3], weights=[0.5, 0.3, 0.2])[0]
                        away_g = random.choices([0, 1], weights=[0.7, 0.3])[0]
                        if h in standings:
                            standings[h]["pts"] += 3
                            standings[h]["gd"] += (home_g - away_g)
                            standings[h]["gf"] += home_g
                        if a in standings:
                            standings[a]["gd"] += (away_g - home_g)
                            standings[a]["gf"] += away_g
                    elif r < probs["home"] + probs["draw"]:
                        g = random.choices([0, 1, 2, 3], weights=[0.2, 0.4, 0.3, 0.1])[0]
                        if h in standings:
                            standings[h]["pts"] += 1
                            standings[h]["gf"] += g
                        if a in standings:
                            standings[a]["pts"] += 1
                            standings[a]["gf"] += g
                    else:
                        away_g = random.choices([1, 2, 3], weights=[0.5, 0.3, 0.2])[0]
                        home_g = random.choices([0, 1], weights=[0.7, 0.3])[0]
                        if a in standings:
                            standings[a]["pts"] += 3
                            standings[a]["gd"] += (away_g - home_g)
                            standings[a]["gf"] += away_g
                        if h in standings:
                            standings[h]["gd"] += (home_g - away_g)
                            standings[h]["gf"] += home_g

                sorted_teams = sorted(
                    standings.items(),
                    key=lambda x: (x[1]["pts"], x[1]["gd"], x[1]["gf"]),
                    reverse=True,
                )
                group_standings[gn] = sorted_teams

            for gn, ranked in group_standings.items():
                if len(ranked) >= 1:
                    team_group_win[ranked[0][0]] = team_group_win.get(ranked[0][0], 0) + 1
                for i, (team, _) in enumerate(ranked[:2]):
                    team_advance[team] = team_advance.get(team, 0) + 1

            advancing = []
            for gn, ranked in group_standings.items():
                for team, _ in ranked[:2]:
                    advancing.append(team)

            if len(advancing) >= 32:
                random.shuffle(advancing)
                r16 = advancing[:16]
                for t in r16:
                    team_round16[t] = team_round16.get(t, 0) + 1
                random.shuffle(r16)
                qf = r16[:8]
                for t in qf:
                    team_quarter[t] = team_quarter.get(t, 0) + 1
                random.shuffle(qf)
                sf = qf[:4]
                for t in sf:
                    team_semi[t] = team_semi.get(t, 0) + 1
                random.shuffle(sf)
                fin = sf[:2]
                for t in fin:
                    team_final[t] = team_final.get(t, 0) + 1
                champion = fin[0]
                team_champion[champion] = team_champion.get(champion, 0) + 1

            if run_idx % max(1, runs // 10) == 0:
                progress_bar.progress(min(1.0, (run_idx + 1) / runs))

        progress_bar.progress(1.0)
        status_text.text(f"模拟完成: {runs:,} 次")

        st.subheader(f"模拟结果 ({runs:,} 次)")

        results_data = []
        for team in all_teams:
            group = df_groups[df_groups["team_name"] == team]["group_name"].values
            group_name = group[0] if len(group) > 0 else "?"
            results_data.append({
                "球队": team,
                "小组": group_name,
                "小组第一": f"{team_group_win.get(team, 0) / runs * 100:.1f}%",
                "小组出线": f"{team_advance.get(team, 0) / runs * 100:.1f}%",
                "16 强": f"{team_round16.get(team, 0) / runs * 100:.1f}%",
                "8 强": f"{team_quarter.get(team, 0) / runs * 100:.1f}%",
                "4 强": f"{team_semi.get(team, 0) / runs * 100:.1f}%",
                "决赛": f"{team_final.get(team, 0) / runs * 100:.1f}%",
                "冠军": f"{team_champion.get(team, 0) / runs * 100:.1f}%",
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
st.caption("Monte Carlo 模拟仅供研究参考。简化版淘汰赛模型 — 完整对阵模拟请使用 CLI。")
