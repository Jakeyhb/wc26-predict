"""Generate 48-team Elo ranking chart with Chinese team names."""
import sqlite3, math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import matplotlib.font_manager as fm
import numpy as np

# Font
for f in fm.fontManager.ttflist:
    if 'YaHei' in f.name or 'SimHei' in f.name:
        plt.rcParams['font.family'] = f.name; break

CN = {
    "Mexico":"墨西哥","South Africa":"南非","South Korea":"韩国",
    "Czech Republic":"捷克","Canada":"加拿大","Bosnia and Herzegovina":"波黑",
    "Qatar":"卡塔尔","Switzerland":"瑞士","Brazil":"巴西",
    "Morocco":"摩洛哥","Haiti":"海地","Scotland":"苏格兰",
    "United States":"美国","Paraguay":"巴拉圭","Australia":"澳大利亚",
    "Turkey":"土耳其","Germany":"德国","Curacao":"库拉索",
    "Ivory Coast":"科特迪瓦","Ecuador":"厄瓜多尔","Netherlands":"荷兰",
    "Japan":"日本","Sweden":"瑞典","Tunisia":"突尼斯",
    "Belgium":"比利时","Egypt":"埃及","Iran":"伊朗",
    "New Zealand":"新西兰","Spain":"西班牙","Cape Verde":"佛得角",
    "Saudi Arabia":"沙特","Uruguay":"乌拉圭","France":"法国",
    "Senegal":"塞内加尔","Iraq":"伊拉克","Norway":"挪威",
    "Argentina":"阿根廷","Algeria":"阿尔及利亚","Austria":"奥地利",
    "Jordan":"约旦","Portugal":"葡萄牙","DR Congo":"刚果(金)",
    "Uzbekistan":"乌兹别克斯坦","Colombia":"哥伦比亚",
    "England":"英格兰","Croatia":"克罗地亚","Ghana":"加纳","Panama":"巴拿马",
}

DB = r"D:\hermes agent\2026世界杯分析\backend\data\local_stage2.db"
conn = sqlite3.connect(DB)
rows = conn.execute("""
    SELECT DISTINCT t.name FROM matches m JOIN teams t ON t.id = m.home_team_id
    WHERE m.competition='FIFA World Cup 2026' AND m.stage LIKE 'Group%'
    UNION SELECT DISTINCT t.name FROM matches m JOIN teams t ON t.id = m.away_team_id
    WHERE m.competition='FIFA World Cup 2026' AND m.stage LIKE 'Group%'
""").fetchall()
wc_teams = {r[0] for r in rows}

matches = conn.execute("""
    SELECT ht.name, at.name, mr.home_goals, mr.away_goals,
           m.is_neutral_venue, m.competition_weight
    FROM matches m JOIN teams ht ON m.home_team_id=ht.id
    JOIN teams at ON m.away_team_id=at.id
    JOIN match_results mr ON mr.match_id=m.id
    WHERE m.competition_type='national' ORDER BY m.match_date ASC
""").fetchall()

K = 20; elo = {}
for home, away, hg, ag, neutral, weight in matches:
    rh, ra = elo.get(home,1500), elo.get(away,1500)
    eh = 1.0/(1.0+math.pow(10,(ra-rh)/400.0))
    if hg>ag: sh,sa=1.0,0.0
    elif hg==ag: sh,sa=0.5,0.5
    else: sh,sa=0.0,1.0
    w = float(weight or 0.5)
    elo[home]=rh+K*w*(sh-eh); elo[away]=ra+K*w*(sa-(1-eh))

wc_elo = {t:round(elo.get(t,1500)) for t in wc_teams}
sorted_teams = sorted(wc_elo.items(), key=lambda x:x[1], reverse=True)

# Build chart with Chinese names
names = [CN.get(t[0], t[0]) for t in reversed(sorted_teams)]
values = [t[1] for t in reversed(sorted_teams)]

colors = []
for i in range(len(values)):
    rank = len(values) - i
    if rank <= 5: colors.append('#FFD700')
    elif rank <= 15: colors.append('#C0C0C0')
    elif rank <= 30: colors.append('#CD7F32')
    else: colors.append('#555555')

fig, ax = plt.subplots(figsize=(10, 22))
fig.patch.set_facecolor('#0b0b0b')
ax.set_facecolor('#0b0b0b')

bars = ax.barh(range(len(names)), values, color=colors, height=0.7)

for i, (name, val) in enumerate(zip(names, values)):
    rank = len(names) - i
    label = f"#{rank}  {name}"
    ax.text(val+5, i, f"{label}  {val}",
            va='center', fontsize=11, color='white')

ax.set_xlim(min(values)-80, max(values)+100)
ax.set_yticks([])
for sp in ['top','right','left']: ax.spines[sp].set_visible(False)
ax.spines['bottom'].set_color('#333')
ax.tick_params(colors='#888', labelsize=10)

ax.set_title('2026 世界杯 · 48 队 Elo 排名', fontsize=22, color='white', pad=20)
fig.text(0.5, 0.02, '数据: football-data.org + openfootball  |  Elo K=20  |  2026-06-01',
         ha='center', fontsize=9, color='#666')

out = r"D:\hermes agent\2026世界杯分析\6.2社交媒体准备库\elo_ranking_48.png"
plt.tight_layout()
plt.savefig(out, dpi=150, bbox_inches='tight', facecolor='#0b0b0b')
plt.close()
print(f"Saved: {out}")
conn.close()
