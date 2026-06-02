import sqlite3
conn = sqlite3.connect('data/local_stage2.db')
for row in conn.execute("SELECT id, name, team_type FROM teams WHERE name LIKE '%urac%' OR name LIKE '%uraç%'").fetchall():
    train = conn.execute('SELECT COUNT(mr.match_id) FROM matches m JOIN match_results mr ON mr.match_id=m.id WHERE m.home_team_id=?1 OR m.away_team_id=?1', (row[0],)).fetchone()[0]
    print(f'name={row[1]} type={row[2]} train={train} id={row[0][:50]}')
conn.close()
