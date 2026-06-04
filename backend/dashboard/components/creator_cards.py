"""creator_cards.py — Creator Mode styled components for video recording."""

from __future__ import annotations

import streamlit as st


def render_creator_card(
    title: str,
    content: str,
    *,
    accent_color: str = "#00BFFF",
) -> None:
    """Render a styled card for creator mode."""
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border-radius: 16px;
            padding: 1.5rem;
            margin: 0.5rem 0;
            box-shadow: 0 4px 16px rgba(0,0,0,0.2);
            border: 1px solid rgba(255,255,255,0.1);
        ">
            <div style="font-size:0.85rem;color:#888;text-transform:uppercase;
                        letter-spacing:0.08em;">{title}</div>
            <div style="font-size:2.5rem;font-weight:800;color:{accent_color};">
                {content}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_creator_conclusion(text: str) -> None:
    """Render a large, bold one-sentence conclusion."""
    st.markdown(
        f"""
        <div style="
            font-size:1.4rem;font-weight:600;line-height:1.6;
            color:#e0e0e0;padding:1.2rem;
            border-left:4px solid #00BFFF;margin:0.8rem 0;
            background:rgba(0,191,255,0.05);border-radius:0 8px 8px 0;
        ">{text}</div>
        """,
        unsafe_allow_html=True,
    )


def render_social_copy(text: str) -> None:
    """Render a copyable text block for social media."""
    st.code(text, language=None)
    st.caption("Copy the text above, then paste to your social media app")


def render_video_script(home_team: str, away_team: str, result: dict) -> str:
    """Generate a video voiceover script from prediction results."""
    h_prob = result.get("home_win_prob", 0) * 100
    d_prob = result.get("draw_prob", 0) * 100
    a_prob = result.get("away_win_prob", 0) * 100
    home_xg = result.get("home_xg", 0)
    away_xg = result.get("away_xg", 0)

    favored = home_team if h_prob > a_prob else away_team
    favored_pct = max(h_prob, a_prob)

    return (
        f"WC26 Predict Analysis - {home_team} vs {away_team}\n\n"
        f"[Model Probabilities]\n"
        f"{home_team} Win: {h_prob:.1f}%\n"
        f"Draw: {d_prob:.1f}%\n"
        f"{away_team} Win: {a_prob:.1f}%\n\n"
        f"[Expected Goals]\n"
        f"{home_team}: {home_xg:.2f}  |  {away_team}: {away_xg:.2f}\n\n"
        f"Four-model fusion (DC + XGBoost + Elo + Pi).\n"
        f"{favored} slightly favored at {favored_pct:.1f}%.\n\n"
        f"Base model forecast only. Lineup/injury/weather not yet integrated.\n"
        f"Not betting advice. AI football research project.\n\n"
        f"#WC26 #AIFootball #FootballAnalytics"
    )


def render_wechat_copy(home_team: str, away_team: str, result: dict) -> str:
    """Generate a WeChat/RedNote-friendly text post."""
    h_prob = result.get("home_win_prob", 0) * 100
    d_prob = result.get("draw_prob", 0) * 100
    a_prob = result.get("away_win_prob", 0) * 100

    return (
        f"WC26 Predict AI Analysis\n\n"
        f"{home_team} vs {away_team}\n"
        f"Win: {h_prob:.1f}% | Draw: {d_prob:.1f}% | Lose: {a_prob:.1f}%\n\n"
        f"Four-model fusion (Dixon-Coles + XGBoost + Elo + Pi)\n"
        f"Base model forecast. Not betting advice.\n\n"
        f"#WorldCup #AIPrediction #FootballDataScience"
    )
