"""Compare DB 2026 WC schedule against official FIFA schedule."""
import sqlite3

DB = r"D:\hermes agent\2026世界杯分析\backend\data\local_stage2.db"
conn = sqlite3.connect(DB)

# Official schedule per FIFA (2026-06-03)
OFFICIAL = {
    "A": {
        "teams": {"Mexico", "South Africa", "South Korea", "Czechia"},
        "MD1": {("Mexico", "South Africa"), ("South Korea", "Czechia")},
        "MD2": {("Czechia", "South Africa"), ("Mexico", "South Korea")},
        "MD3": {("Czechia", "Mexico"), ("South Africa", "South Korea")},
    },
    "B": {
        "teams": {"Canada", "Bosnia and Herzegovina", "Qatar", "Switzerland"},
        "MD1": {("Canada", "Bosnia and Herzegovina"), ("Qatar", "Switzerland")},
        "MD2": {("Switzerland", "Bosnia and Herzegovina"), ("Canada", "Qatar")},
        "MD3": {("Switzerland", "Canada"), ("Bosnia and Herzegovina", "Qatar")},
    },
    "C": {
        "teams": {"Brazil", "Morocco", "Haiti", "Scotland"},
        "MD1": {("Brazil", "Morocco"), ("Haiti", "Scotland")},
        "MD2": {("Scotland", "Morocco"), ("Brazil", "Haiti")},
        "MD3": {("Scotland", "Brazil"), ("Morocco", "Haiti")},
    },
    "D": {
        "teams": {"United States", "Paraguay", "Australia", "Turkey"},
        "MD1": {("United States", "Paraguay"), ("Australia", "Turkey")},
        "MD2": {("Turkey", "Paraguay"), ("United States", "Australia")},
        "MD3": {("Turkey", "United States"), ("Paraguay", "Australia")},
    },
    "E": {
        "teams": {"Germany", "Curacao", "Ivory Coast", "Ecuador"},
        "MD1": {("Germany", "Curacao"), ("Ivory Coast", "Ecuador")},
        "MD2": {("Germany", "Ivory Coast"), ("Ecuador", "Curacao")},
        "MD3": {("Ecuador", "Germany"), ("Curacao", "Ivory Coast")},
    },
    "F": {
        "teams": {"Netherlands", "Japan", "Sweden", "Tunisia"},
        "MD1": {("Netherlands", "Japan"), ("Sweden", "Tunisia")},
        "MD2": {("Netherlands", "Sweden"), ("Tunisia", "Japan")},
        "MD3": {("Tunisia", "Netherlands"), ("Japan", "Sweden")},
    },
    "G": {
        "teams": {"Belgium", "Egypt", "Iran", "New Zealand"},
        "MD1": {("Belgium", "Egypt"), ("Iran", "New Zealand")},
        "MD2": {("Belgium", "Iran"), ("New Zealand", "Egypt")},
        "MD3": {("New Zealand", "Belgium"), ("Egypt", "Iran")},
    },
    "H": {
        "teams": {"Spain", "Cape Verde", "Saudi Arabia", "Uruguay"},
        "MD1": {("Spain", "Cape Verde"), ("Saudi Arabia", "Uruguay")},
        "MD2": {("Spain", "Saudi Arabia"), ("Uruguay", "Cape Verde")},
        "MD3": {("Uruguay", "Spain"), ("Cape Verde", "Saudi Arabia")},
    },
    "I": {
        "teams": {"France", "Senegal", "Norway", "Iraq"},
        "MD1": {("France", "Senegal"), ("Norway", "Iraq")},
        "MD2": {("France", "Norway"), ("Senegal", "Iraq")},
        "MD3": {("Norway", "France"), ("Senegal", "Iraq")},
    },
    "J": {
        "teams": {"Argentina", "Algeria", "Austria", "Jordan"},
        "MD1": {("Argentina", "Algeria"), ("Austria", "Jordan")},
        "MD2": {("Argentina", "Austria"), ("Jordan", "Algeria")},
        "MD3": {("Jordan", "Argentina"), ("Algeria", "Austria")},
    },
    "K": {
        "teams": {"Portugal", "DR Congo", "Uzbekistan", "Colombia"},
        "MD1": {("Portugal", "DR Congo"), ("Uzbekistan", "Colombia")},
        "MD2": {("Portugal", "Uzbekistan"), ("Colombia", "DR Congo")},
        "MD3": {("Colombia", "Portugal"), ("DR Congo", "Uzbekistan")},
    },
    "L": {
        "teams": {"England", "Croatia", "Ghana", "Panama"},
        "MD1": {("England", "Croatia"), ("Ghana", "Panama")},
        "MD2": {("England", "Ghana"), ("Panama", "Croatia")},
        "MD3": {("Panama", "England"), ("Croatia", "Ghana")},
    },
}

# DB name normalization
NAME_MAP = {
    "Czech Republic": "Czechia",
    "Türkiye": "Turkey",
    "Côte d'Ivoire": "Ivory Coast",
}

def normalize(name):
    return NAME_MAP.get(name, name)

issues_found = 0

for group in "ABCDEFGHIJKL":
    db_matches = conn.execute(f"""
        SELECT m.stage, ht.name, at.name
        FROM matches m
        JOIN teams ht ON m.home_team_id = ht.id
        JOIN teams at ON m.away_team_id = at.id
        WHERE m.competition = 'FIFA World Cup 2026' AND m.stage LIKE 'Group {group}%'
        ORDER BY m.stage, m.match_date
    """).fetchall()

    off = OFFICIAL[group]

    # Group by matchday
    db_md = {}
    for stage, home, away in db_matches:
        if stage and "Matchday" in stage:
            md = stage.split(" - ")[1]  # "Group A - Matchday 1" -> "Matchday 1"
        db_md.setdefault(md, set()).add((home, away))

    for md_num, md_key in [(1, "MD1"), (2, "MD2"), (3, "MD3")]:
        md = f"Matchday {md_num}"
        db_set = db_md.get(md, set())
        off_set = off[md_key]

        # Normalize both
        db_norm = {(normalize(h), normalize(a)) for h, a in db_set}
        off_norm = off_set

        if db_norm != off_norm:
            issues_found += 1
            print(f"❌ Group {group} {md}:")
            missing = off_norm - db_norm
            extra = db_norm - off_norm
            if missing:
                print(f"   Missing (should exist): {missing}")
            if extra:
                print(f"   Extra (shouldn't exist): {extra}")

if issues_found == 0:
    print("All group stage matchups match official schedule!")
else:
    print(f"\n{issues_found} issues found across all groups.")

conn.close()
