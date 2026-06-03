"""
Generate a simplified architecture diagram for social media.
Output: architecture_diagram.png — clean, dark theme, suitable for 小红书/Bilibili.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent

# ── Style Settings ─────────────────────────────────────────────────
BG = "#0d1117"
CARD_BG = "#161b22"
CARD_EDGE = "#30363d"
TEXT = "#e6edf3"
TEXT_DIM = "#8b949e"
GREEN = "#3fb950"
BLUE = "#58a6ff"
ORANGE = "#d29922"
PURPLE = "#bc8cff"
RED = "#f85149"
CYAN = "#39d353"

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]

fig, ax = plt.subplots(figsize=(16, 9))
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 16)
ax.set_ylim(0, 9)
ax.set_aspect("equal")
ax.axis("off")

# ── Helper to draw rounded rectangles ──────────────────────────────
def draw_box(x, y, w, h, color, text="", text_color=TEXT, fontsize=11, bold=False, alpha=0.9):
    rect = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.15",
                          facecolor=color, edgecolor=CARD_EDGE, linewidth=1.5,
                          alpha=alpha, zorder=2)
    ax.add_patch(rect)
    if text:
        weight = "bold" if bold else "normal"
        ax.text(x + w/2, y + h/2, text, ha="center", va="center",
                fontsize=fontsize, color=text_color, weight=weight, zorder=3)

def draw_arrow(x1, y1, x2, y2, color=CARD_EDGE, lw=2):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="->", color=color, lw=lw,
                               connectionstyle="arc3,rad=0"), zorder=1)

def draw_label(x, y, text, color=TEXT_DIM, fontsize=9):
    ax.text(x, y, text, ha="center", va="center", fontsize=fontsize, color=color, zorder=4)

# ── Title ──────────────────────────────────────────────────────────
ax.text(8, 8.5, "WC2026 比赛分析引擎 v2.0", ha="center", va="center",
        fontsize=22, color=TEXT, fontweight="bold")
ax.text(8, 8.1, "多数据源 →  分析引擎 →  结果输出", ha="center", va="center",
        fontsize=12, color=TEXT_DIM)

# ── Layer 1: Data Sources (top row) ────────────────────────────────
DATA_SOURCES = [
    (0.5, 6.7, 2.2, 1.0, BLUE, "football-data.org\nSchedule + Standings"),
    (3.0, 6.7, 2.2, 1.0, BLUE, "StatsBomb Open\nxG + Event Data"),
    (5.5, 6.7, 2.2, 1.0, BLUE, "openfootball\nInternational Results"),
    (8.0, 6.7, 2.2, 1.0, PURPLE, "Open-Meteo\nWeather API"),
    (10.5, 6.7, 2.2, 1.0, PURPLE, "Manual Events\nInjuries / Suspensions"),
    (13.0, 6.7, 2.2, 1.0, ORANGE, "LLM (DeepSeek)\nNews Extraction"),
]

for x, y, w, h, c, t in DATA_SOURCES:
    draw_box(x, y, w, h, c, t, fontsize=9, alpha=0.3)

draw_label(8, 6.3, "数据采集层  (16,000+ 场比赛 · 440+ 支球队)", TEXT_DIM, 10)

# ── Arrows down ────────────────────────────────────────────────────
for i in range(3):
    draw_arrow(1.6 + i*2.5, 6.7, 4.0, 5.3, CARD_EDGE)
    draw_arrow(9.1 + i*2.5, 6.7, 8.5 + i, 5.3, CARD_EDGE)

# ── Layer 2: Prediction Engine (middle) ────────────────────────────
ENGINES = [
    (0.5, 4.0, 3.5, 1.2, GREEN, "Dixon-Coles\nPoisson Goals Model\nWeight: 55%", True),
    (4.3, 4.0, 3.5, 1.2, GREEN, "Tabular Enhancer\nHGB Classifier (37 features)\nWeight: 30%", False),
    (8.1, 4.0, 3.5, 1.2, GREEN, "Elo Rating System\nKappa Davidson Draw\nWeight: 5%", False),
    (11.9, 4.0, 3.5, 1.2, GREEN, "Pi-Rating\nZero-mean Goal Diff\nWeight: 5%", False),
]

for x, y, w, h, c, t, bold in ENGINES:
    draw_box(x, y, w, h, c, t, fontsize=10, bold=bold)

draw_label(8, 3.6, "预测引擎层  (4层融合 · 场景自适应权重)", TEXT_DIM, 10)

# ── Arrows down ────────────────────────────────────────────────────
for x_pos in [2.25, 6.05, 9.85, 13.65]:
    draw_arrow(x_pos, 4.0, x_pos, 2.7, CARD_EDGE)

# ── Layer 3: Fusion + Adjust ───────────────────────────────────────
draw_box(5.0, 1.8, 6.0, 0.9, ORANGE,
         "Signal Adjuster  ·  Scene Weights  ·  Calibration Monitor",
         fontsize=11, bold=True, alpha=0.3)

# ── Arrows to Layer 3 ──────────────────────────────────────────────
for x_pos in [2.25, 6.05, 9.85, 13.65]:
    draw_arrow(x_pos, 2.7, x_pos, 2.25, CARD_EDGE)
# Then four arrows into the single box
draw_arrow(2.25, 2.25, 8.0, 2.35, CARD_EDGE)
draw_arrow(6.05, 2.25, 8.0, 2.35, CARD_EDGE)
draw_arrow(9.85, 2.25, 8.0, 2.35, CARD_EDGE)
draw_arrow(13.65, 2.25, 8.0, 2.35, CARD_EDGE)

# ── Layer 4: Output ────────────────────────────────────────────────
draw_box(5.0, 0.4, 6.0, 1.0, RED,
         "Match Report  ·  Win/Draw/Loss  ·  Score Distribution  ·  Elo  ·  Over/Under",
         fontsize=11, bold=True, alpha=0.3)

draw_arrow(8.0, 1.8, 8.0, 1.4, CARD_EDGE)
draw_label(8, -0.05, "  GitHub  |  Claude Code  |  DeepSeek LLM  |  React + FastAPI", TEXT_DIM, 10)

# ── Self-Evolution Loop (curved arrow on the right) ────────────────
ax.annotate("", xy=(14.5, 1.2), xytext=(14.5, 6.2),
            arrowprops=dict(arrowstyle="->", color=CYAN, lw=2.5,
                           connectionstyle="arc3,rad=-0.6", linestyle="dashed"),
            zorder=1)
ax.text(15.4, 3.7, "Self-\nEvolution\nLoop", ha="center", va="center",
        fontsize=9, color=CYAN, style="italic")

# ── Footer ─────────────────────────────────────────────────────────
ax.text(8, -0.35, "个人学习项目 · 仅供娱乐参考 · 不构成任何建议 · 享受比赛本身",
        ha="center", va="center", fontsize=8, color="#484f58", style="italic")

plt.tight_layout(pad=0.5)
output_path = OUTPUT_DIR / "architecture_diagram.png"
fig.savefig(str(output_path), dpi=200, bbox_inches="tight", facecolor=BG, edgecolor="none")
print(f"[DONE] Saved: {output_path}")
plt.close(fig)
