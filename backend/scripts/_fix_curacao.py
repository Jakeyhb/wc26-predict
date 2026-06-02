import sqlite3
conn = sqlite3.connect('data/local_stage2.db')
# Find Curacao/Curacao IDs
c1 = [r[0] for r in conn.execute("SELECT id FROM teams WHERE name = 'Curacao'").fetchall()]
c2 = [r[0] for r in conn.execute("SELECT id FROM teams WHERE name = 'Curacao'").fetchall()]
best = [r[0] for r in conn.execute("SELECT id FROM teams WHERE name = 'Curacao' ORDER BY LENGTH(id) DESC").fetchall()][0]
for old in c1 + c2:
    if old == best: continue
    conn.execute('UPDATE matches SET home_team_id=? WHERE home_team_id=?',(best,old))
    conn.execute('UPDATE matches SET away_team_id=? WHERE away_team_id=?',(best,old))
    conn.execute('DELETE FROM teams WHERE id=?',(old,))
conn.execute("UPDATE teams SET name='Curacao' WHERE id=?",(best,))
conn.commit()
t = conn.execute("SELECT COUNT(mr.match_id) FROM matches m JOIN match_results mr ON mr.match_id=m.id JOIN teams t ON (m.home_team_id=t.id OR m.away_team_id=t.id) WHERE t.name='Curacao'").fetchone()[0]
print(f'Curacao training matches: {t}')
conn.close()
