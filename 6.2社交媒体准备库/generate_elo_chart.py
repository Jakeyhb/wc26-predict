"""
Generate a 48-team Elo ranking visualization for social media.
Output: elo_ranking_48.png — a beautiful color-coded chart suitable for 小红书/Douyin/Bilibili.
"""
import sys
sys.path.insert(0, "../backend")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
import sqlite3
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────
OUTPUT_DIR = Path(__file__).resolve().parent
DB_PATH = Path(__file__).resolve().parents[1] / "backend" / "data" / "local_stage2.db"

# 48 WC 2026 teams with Chinese names, FIFA codes, confederations
WC_TEAMS = [
    # Group A
    ("United States", "美国", "USA", "CONCACAF", "A"),
    ("Canada", "加拿大", "CAN", "CONCACAF", "A"),
    ("Qatar", "卡塔尔", "QAT", "AFC", "A"),
    ("Costa Rica", "哥斯达黎加", "CRC", "CONCACAF", "A"),
    # Group B
    ("Mexico", "墨西哥", "MEX", "CONCACAF", "B"),
    ("Panama", "巴拿马", "PAN", "CONCACAF", "B"),
    ("New Zealand", "新西兰", "NZL", "OFC", "B"),
    ("Chile", "智利", "CHI", "CONMEBOL", "B"),
    # Group C
    ("Argentina", "阿根廷", "ARG", "CONMEBOL", "C"),
    ("Peru", "秘鲁", "PER", "CONMEBOL", "C"),
    ("Saudi Arabia", "沙特阿拉伯", "KSA", "AFC", "C"),
    ("Nigeria", "尼日利亚", "NGA", "CAF", "C"),
    # Group D
    ("Brazil", "巴西", "BRA", "CONMEBOL", "D"),
    ("Japan", "日本", "JPN", "AFC", "D"),
    ("Australia", "澳大利亚", "AUS", "AFC", "D"),
    ("Morocco", "摩洛哥", "MAR", "CAF", "D"),
    # Group E
    ("France", "法国", "FRA", "UEFA", "E"),
    ("Senegal", "塞内加尔", "SEN", "CAF", "E"),
    ("Ecuador", "厄瓜多尔", "ECU", "CONMEBOL", "E"),
    ("Iran", "伊朗", "IRN", "AFC", "E"),
    # Group F
    ("England", "英格兰", "ENG", "UEFA", "F"),
    ("Denmark", "丹麦", "DEN", "UEFA", "F"),
    ("Serbia", "塞尔维亚", "SRB", "UEFA", "F"),
    ("South Korea", "韩国", "KOR", "AFC", "F"),
    # Group G
    ("Spain", "西班牙", "ESP", "UEFA", "G"),
    ("Uruguay", "乌拉圭", "URU", "CONMEBOL", "G"),
    ("Poland", "波兰", "POL", "UEFA", "G"),
    ("Austria", "奥地利", "AUT", "UEFA", "G"),
    # Group H
    ("Portugal", "葡萄牙", "POR", "UEFA", "H"),
    ("Switzerland", "瑞士", "SUI", "UEFA", "H"),
    ("Croatia", "克罗地亚", "CRO", "UEFA", "H"),
    ("Turkey", "土耳其", "TUR", "UEFA", "H"),
    # Group I
    ("Germany", "德国", "GER", "UEFA", "I"),
    ("Netherlands", "荷兰", "NED", "UEFA", "I"),
    ("Belgium", "比利时", "BEL", "UEFA", "I"),
    ("Czechia", "捷克", "CZE", "UEFA", "I"),
    # Group J
    ("Italy", "意大利", "ITA", "UEFA", "J"),
    ("Colombia", "哥伦比亚", "COL", "CONMEBOL", "J"),
    ("Hungary", "匈牙利", "HUN", "UEFA", "J"),
    ("Slovakia", "斯洛伐克", "SVK", "UEFA", "J"),
    # Group K
    ("Sweden", "瑞典", "SWE", "UEFA", "K"),
    ("Norway", "挪威", "NOR", "UEFA", "K"),
    ("Romania", "罗马尼亚", "ROU", "UEFA", "K"),
    ("Greece", "希腊", "GRE", "UEFA", "K"),
    # Group L
    ("Cote d'Ivoire", "科特迪瓦", "CIV", "CAF", "L"),
    ("Egypt", "埃及", "EGY", "CAF", "L"),
    ("Algeria", "阿尔及利亚", "ALG", "CAF", "L"),
    ("Cameroon", "喀麦隆", "CMR", "CAF", "L"),
]

# Confederation colors (中文 + hex)
CONFED_COLORS = {
    "UEFA":       ("欧洲", "#1a5276"),
    "CONMEBOL":   ("南美", "#229954"),
    "CAF":        ("非洲", "#d4ac0d"),
    "AFC":        ("亚洲", "#e74c3c"),
    "CONCACAF":   ("北美", "#884ea0"),
    "OFC":        ("大洋", "#17a589"),
}

# ── Load match results & compute Elo ───────────────────────────────
conn = sqlite3.connect(str(DB_PATH))
df = pd.read_sql_query("""
    SELECT m.match_date, ht.name as home_team, at.name as away_team,
           mr.home_goals, mr.away_goals,
           COALESCE(m.competition_weight, 1.0) as competition_weight
    FROM match_results mr
    JOIN matches m ON mr.match_id = m.id
    JOIN teams ht ON m.home_team_id = ht.id
    JOIN teams at ON m.away_team_id = at.id
    WHERE mr.home_goals IS NOT NULL AND mr.away_goals IS NOT NULL
    ORDER BY m.match_date
""", conn)
conn.close()

print(f"Loaded {len(df)} matches for Elo computation")

# Elo parameters
DEFAULT_RATING = 1500.0
HOME_ADVANTAGE = 100.0
K_LEAGUE = 20
K_KNOCKOUT = 32

ratings = {}

def get_rating(team):
    return ratings.get(team, DEFAULT_RATING)

def expected_score(r_home, r_away):
    return 1.0 / (1.0 + 10.0 ** ((r_away - r_home) / 400.0))

for _, row in df.iterrows():
    home = row["home_team"]
    away = row["away_team"]
    home_goals = int(row["home_goals"])
    away_goals = int(row["away_goals"])
    weight = float(row["competition_weight"])

    r_home = get_rating(home)
    r_away = get_rating(away)
    k = K_KNOCKOUT if weight >= 1.5 else (28.0 if weight >= 1.2 else K_LEAGUE)

    exp_home = expected_score(r_home + HOME_ADVANTAGE, r_away)

    if home_goals > away_goals:
        result = 1.0
    elif home_goals == away_goals:
        result = 0.5
    else:
        result = 0.0

    delta = k * (result - exp_home)
    ratings[home] = r_home + delta
    ratings[away] = r_away - delta

print(f"Computed Elo ratings for {len(ratings)} teams")

# ── Extract WC team ratings ────────────────────────────────────────
team_data = []
for en_name, zh_name, code, confed, group in WC_TEAMS:
    elo = ratings.get(en_name, DEFAULT_RATING)
    team_data.append((elo, zh_name, code, confed, group, en_name))

team_data.sort(key=lambda x: x[0], reverse=True)

print("Top 10 Elo ratings:")
for i, (elo, zh, code, confed, group, en) in enumerate(team_data[:10]):
    print(f"  #{i+1}: {zh} ({en}) = {elo:.0f} [{confed}]")

# ── Generate Visualization ─────────────────────────────────────────
# Style: dark background for terminal/tech aesthetic, green accent
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]

# Figure dimensions — tall chart for scrolling
fig, ax = plt.subplots(figsize=(10, 28))
fig.patch.set_facecolor("#0d1117")
ax.set_facecolor("#0d1117")

n = len(team_data)
y_pos = range(n)

# Reverse for top-to-bottom ranking
ratings_list = [t[0] for t in team_data][::-1]
names_list = [f"{t[1]}  {t[2]}" for t in team_data][::-1]
confeds_list = [t[3] for t in team_data][::-1]
groups_list = [t[4] for t in team_data][::-1]
en_names_list = [t[5] for t in team_data][::-1]

bars = ax.barh(y_pos, ratings_list, height=0.7, color=[CONFED_COLORS[c][1] for c in confeds_list],
               edgecolor="none", alpha=0.85)

# Add Elo value at end of each bar
for i, (elo, name, confed) in enumerate(zip(ratings_list, names_list, confeds_list)):
    color = CONFED_COLORS[confed][1]
    ax.text(elo + 22, i, f"{elo:.0f}", va="center", fontsize=9,
            color="#c9d1d9", fontweight="bold")

# Group separators
prev_group = None
group_labels = {}
for i, (_, _, _, _, group, _) in enumerate(reversed(team_data)):
    if group != prev_group:
        if prev_group is not None:
            ax.axhline(y=i - 0.5, color="#30363d", linewidth=0.5, linestyle="--")
        group_labels[i] = f"Group {group}"
        prev_group = group

# Style
ax.set_xlim(min(ratings_list) - 50, max(ratings_list) + 120)
ax.set_yticks(y_pos)
ax.set_yticklabels(names_list, fontsize=10)
ax.tick_params(colors="#8b949e", labelsize=10)
ax.tick_params(axis="y", colors="#8b949e")
ax.xaxis.set_visible(False)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.spines["bottom"].set_visible(False)
ax.spines["left"].set_color("#21262d")

# Title
fig.text(0.5, 0.985, "WC2026 — 48 Nations Elo Power Rankings",
         ha="center", va="top", fontsize=18, fontweight="bold", color="#e6edf3")
fig.text(0.5, 0.97, "Algorithm: κ-Elo (Szczecinski & Djebbi 2020)  ·  Historical matches only  ·  For reference only",
         ha="center", va="top", fontsize=9, color="#8b949e")

# Legend for confederations
legend_patches = []
for confed_key in ["UEFA", "CONMEBOL", "CAF", "AFC", "CONCACAF", "OFC"]:
    zh, color = CONFED_COLORS[confed_key]
    legend_patches.append(mpatches.Patch(color=color, label=f"{zh} ({confed_key})"))
ax.legend(handles=legend_patches, loc="lower right", fontsize=9,
          facecolor="#161b22", edgecolor="#30363d", labelcolor="#c9d1d9")

# Disclaimer
fig.text(0.5, -0.005, "个人学习项目 · 仅供娱乐参考 · 不构成任何建议 · 享受比赛本身",
         ha="center", va="top", fontsize=8, color="#484f58", style="italic")

plt.tight_layout(pad=1.5)
output_path = OUTPUT_DIR / "elo_ranking_48.png"
fig.savefig(str(output_path), dpi=200, bbox_inches="tight", facecolor="#0d1117", edgecolor="none")
print(f"\n[DONE] Saved: {output_path}")
plt.close(fig)
