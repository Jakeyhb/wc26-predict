import sqlite3, os
db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "local_stage2.db")
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
matches = conn.execute("""
SELECT m.id, ht.name as home, at.name as away, m.match_date, m.competition, m.stage
FROM matches m
JOIN teams ht ON m.home_team_id = ht.id
JOIN teams at ON m.away_team_id = at.id
WHERE m.competition = 'Champions League'
ORDER BY m.match_date DESC LIMIT 5
""").fetchall()
for m in matches:
    print(f"{m['id']} | {m['home']} vs {m['away']} | {m['match_date']} | {m['stage']}")
conn.close()
