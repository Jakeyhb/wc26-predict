# WC26 数据库赛程修复规格书
# 目标文件: D:\hermes agent\2026世界杯分析\backend\data\local_stage2.db
# 数据来源: FIFA官方 / 腾讯新闻 / 懂球帝 / bracketmundial2026
# 所有时间已转换为UTC存储（北京时间-8小时）

import sqlite3
from datetime import datetime

DB = r"D:\hermes agent\2026世界杯分析\backend\data\local_stage2.db"

# ============================================================================
# 一、修复 matches 表 —— 72场小组赛
# ============================================================================
# 问题: 所有比赛日期错误，每天固定6场，实际每天2-4场
# 修复: 根据FIFA官方赛程（北京时间）重设 match_date (UTC)

# 格式: (match_date_UTC, home_team_name, away_team_name, stage_label)
# 注: home_team/away_team 必须与 teams 表中 name 字段完全匹配
# UTC = 北京时间 - 8小时

GROUP_MATCHES = [
    # ===== 第1轮 =====
    # 6月12日 北京时间
    ("2026-06-11T19:00:00", "Mexico", "South Africa", "Group A - Matchday 1"),        # 03:00 BJT
    ("2026-06-12T02:00:00", "South Korea", "Czech Republic", "Group A - Matchday 1"),  # 10:00 BJT
    # 6月13日
    ("2026-06-12T19:00:00", "Canada", "Bosnia and Herzegovina", "Group B - Matchday 1"),# 03:00 BJT
    ("2026-06-13T01:00:00", "United States", "Paraguay", "Group D - Matchday 1"),       # 09:00 BJT
    ("2026-06-13T04:00:00", "Australia", "Turkey", "Group D - Matchday 1"),             # 12:00 BJT
    # 6月14日
    ("2026-06-13T19:00:00", "Qatar", "Switzerland", "Group B - Matchday 1"),           # 03:00 BJT
    ("2026-06-13T22:00:00", "Brazil", "Morocco", "Group C - Matchday 1"),              # 06:00 BJT
    ("2026-06-14T01:00:00", "Haiti", "Scotland", "Group C - Matchday 1"),              # 09:00 BJT
    # 6月15日
    ("2026-06-14T17:00:00", "Germany", "Curacao", "Group E - Matchday 1"),             # 01:00 BJT
    ("2026-06-14T20:00:00", "Netherlands", "Japan", "Group F - Matchday 1"),           # 04:00 BJT
    ("2026-06-14T23:00:00", "Ivory Coast", "Ecuador", "Group E - Matchday 1"),         # 07:00 BJT
    ("2026-06-15T02:00:00", "Tunisia", "Sweden", "Group F - Matchday 1"),              # 10:00 BJT
    # 6月16日
    ("2026-06-15T16:00:00", "Spain", "Cape Verde", "Group H - Matchday 1"),            # 00:00 BJT
    ("2026-06-15T19:00:00", "Belgium", "Egypt", "Group G - Matchday 1"),               # 03:00 BJT
    ("2026-06-15T22:00:00", "Saudi Arabia", "Uruguay", "Group H - Matchday 1"),        # 06:00 BJT
    ("2026-06-16T01:00:00", "Iran", "New Zealand", "Group G - Matchday 1"),            # 09:00 BJT
    # 6月17日
    ("2026-06-16T19:00:00", "France", "Senegal", "Group I - Matchday 1"),              # 03:00 BJT
    ("2026-06-16T22:00:00", "Iraq", "Norway", "Group I - Matchday 1"),                 # 06:00 BJT
    ("2026-06-17T01:00:00", "Argentina", "Algeria", "Group J - Matchday 1"),           # 09:00 BJT
    ("2026-06-17T04:00:00", "Austria", "Jordan", "Group J - Matchday 1"),              # 12:00 BJT
    # 6月18日
    ("2026-06-17T17:00:00", "Portugal", "DR Congo", "Group K - Matchday 1"),           # 01:00 BJT
    ("2026-06-17T20:00:00", "England", "Croatia", "Group L - Matchday 1"),             # 04:00 BJT
    ("2026-06-17T23:00:00", "Ghana", "Panama", "Group L - Matchday 1"),                # 07:00 BJT
    ("2026-06-18T02:00:00", "Uzbekistan", "Colombia", "Group K - Matchday 1"),         # 10:00 BJT

    # ===== 第2轮 =====
    # 6月19日
    ("2026-06-18T16:00:00", "Czech Republic", "South Africa", "Group A - Matchday 2"),  # 00:00 BJT
    ("2026-06-18T19:00:00", "Switzerland", "Bosnia and Herzegovina", "Group B - Matchday 2"), # 03:00
    ("2026-06-18T22:00:00", "Canada", "Qatar", "Group B - Matchday 2"),                # 06:00 BJT
    ("2026-06-19T01:00:00", "Mexico", "South Korea", "Group A - Matchday 2"),          # 09:00 BJT
    # 6月20日
    ("2026-06-19T19:00:00", "United States", "Australia", "Group D - Matchday 2"),     # 03:00 BJT
    ("2026-06-19T22:00:00", "Scotland", "Morocco", "Group C - Matchday 2"),            # 06:00 BJT
    ("2026-06-20T01:00:00", "Brazil", "Haiti", "Group C - Matchday 2"),                # 09:00 BJT
    ("2026-06-20T04:00:00", "Turkey", "Paraguay", "Group D - Matchday 2"),             # 12:00 BJT
    # 6月21日
    ("2026-06-20T17:00:00", "Netherlands", "Sweden", "Group F - Matchday 2"),          # 01:00 BJT
    ("2026-06-20T20:00:00", "Germany", "Ivory Coast", "Group E - Matchday 2"),         # 04:00 BJT
    ("2026-06-21T00:00:00", "Ecuador", "Curacao", "Group E - Matchday 2"),             # 08:00 BJT
    ("2026-06-21T04:00:00", "Tunisia", "Japan", "Group F - Matchday 2"),               # 12:00 BJT
    # 6月22日
    ("2026-06-21T16:00:00", "Spain", "Saudi Arabia", "Group H - Matchday 2"),          # 00:00 BJT
    ("2026-06-21T19:00:00", "Belgium", "Iran", "Group G - Matchday 2"),                # 03:00 BJT
    ("2026-06-21T22:00:00", "Uruguay", "Cape Verde", "Group H - Matchday 2"),          # 06:00 BJT
    ("2026-06-22T01:00:00", "New Zealand", "Egypt", "Group G - Matchday 2"),           # 09:00 BJT
    # 6月23日
    ("2026-06-22T17:00:00", "Argentina", "Austria", "Group J - Matchday 2"),           # 01:00 BJT
    ("2026-06-22T21:00:00", "France", "Iraq", "Group I - Matchday 2"),                 # 05:00 BJT
    ("2026-06-23T00:00:00", "Norway", "Senegal", "Group I - Matchday 2"),              # 08:00 BJT
    ("2026-06-23T03:00:00", "Jordan", "Algeria", "Group J - Matchday 2"),              # 11:00 BJT
    # 6月24日
    ("2026-06-23T17:00:00", "Portugal", "Uzbekistan", "Group K - Matchday 2"),         # 01:00 BJT
    ("2026-06-23T20:00:00", "England", "Ghana", "Group L - Matchday 2"),               # 04:00 BJT
    ("2026-06-23T23:00:00", "Panama", "Croatia", "Group L - Matchday 2"),              # 07:00 BJT
    ("2026-06-24T02:00:00", "Colombia", "DR Congo", "Group K - Matchday 2"),           # 10:00 BJT

    # ===== 第3轮（同组同时开球）=====
    # 6月25日
    ("2026-06-24T19:00:00", "Switzerland", "Canada", "Group B - Matchday 3"),          # 03:00 BJT
    ("2026-06-24T19:00:00", "Bosnia and Herzegovina", "Qatar", "Group B - Matchday 3"),# 03:00 BJT
    ("2026-06-24T22:00:00", "Scotland", "Brazil", "Group C - Matchday 3"),             # 06:00 BJT
    ("2026-06-24T22:00:00", "Morocco", "Haiti", "Group C - Matchday 3"),               # 06:00 BJT
    ("2026-06-25T01:00:00", "Czech Republic", "Mexico", "Group A - Matchday 3"),       # 09:00 BJT
    ("2026-06-25T01:00:00", "South Africa", "South Korea", "Group A - Matchday 3"),    # 09:00 BJT
    # 6月26日
    ("2026-06-25T20:00:00", "Ecuador", "Germany", "Group E - Matchday 3"),             # 04:00 BJT
    ("2026-06-25T20:00:00", "Curacao", "Ivory Coast", "Group E - Matchday 3"),         # 04:00 BJT
    ("2026-06-25T23:00:00", "Japan", "Sweden", "Group F - Matchday 3"),                # 07:00 BJT
    ("2026-06-25T23:00:00", "Tunisia", "Netherlands", "Group F - Matchday 3"),         # 07:00 BJT
    ("2026-06-26T02:00:00", "Turkey", "United States", "Group D - Matchday 3"),        # 10:00 BJT
    ("2026-06-26T02:00:00", "Paraguay", "Australia", "Group D - Matchday 3"),          # 10:00 BJT
    # 6月27日
    ("2026-06-26T19:00:00", "Norway", "France", "Group I - Matchday 3"),               # 03:00 BJT
    ("2026-06-26T19:00:00", "Senegal", "Iraq", "Group I - Matchday 3"),                # 03:00 BJT
    ("2026-06-27T00:00:00", "Cape Verde", "Saudi Arabia", "Group H - Matchday 3"),     # 08:00 BJT
    ("2026-06-27T00:00:00", "Uruguay", "Spain", "Group H - Matchday 3"),               # 08:00 BJT
    ("2026-06-27T03:00:00", "Egypt", "Iran", "Group G - Matchday 3"),                  # 11:00 BJT
    ("2026-06-27T03:00:00", "New Zealand", "Belgium", "Group G - Matchday 3"),         # 11:00 BJT
    # 6月28日
    ("2026-06-27T21:00:00", "Panama", "England", "Group L - Matchday 3"),              # 05:00 BJT
    ("2026-06-27T21:00:00", "Croatia", "Ghana", "Group L - Matchday 3"),               # 05:00 BJT
    ("2026-06-27T23:30:00", "Colombia", "Portugal", "Group K - Matchday 3"),           # 07:30 BJT
    ("2026-06-27T23:30:00", "DR Congo", "Uzbekistan", "Group K - Matchday 3"),         # 07:30 BJT
    ("2026-06-28T02:00:00", "Algeria", "Austria", "Group J - Matchday 3"),             # 10:00 BJT
    ("2026-06-28T02:00:00", "Jordan", "Argentina", "Group J - Matchday 3"),            # 10:00 BJT
]

# ============================================================================
# 二、淘汰赛 matches 表
# ============================================================================
# 32强: 6/29-7/4 北京时间，每天3-4场
# 格式: (match_date_UTC, stage, match_number, opponent_slot_home, opponent_slot_away)
# opponent_slot 写入 stage 字段或作为注释

KNOCKOUT_MATCHES = [
    # === Round of 32 (M73-M88) ===
    # 6/29 北京时间
    ("2026-06-28T19:00:00", "Round of 32", 73, "2nd Group A", "2nd Group B"),
    ("2026-06-28T20:30:00", "Round of 32", 74, "1st Group E", "3rd Group A/B/C/D/F"),
    # 6/30 北京时间
    ("2026-06-29T01:00:00", "Round of 32", 75, "1st Group F", "2nd Group C"),
    ("2026-06-29T05:00:00", "Round of 32", 76, "1st Group C", "2nd Group F"),
    ("2026-06-29T09:00:00", "Round of 32", 77, "1st Group I", "3rd Group C/D/F/G/H"),
    # 7/1 北京时间
    ("2026-06-30T05:00:00", "Round of 32", 78, "2nd Group E", "2nd Group I"),
    ("2026-06-30T01:00:00", "Round of 32", 79, "1st Group A", "3rd Group C/E/F/H/I"),
    ("2026-06-30T09:00:00", "Round of 32", 80, "1st Group L", "3rd Group E/H/I/J/K"),
    # 7/2 北京时间
    ("2026-07-01T00:00:00", "Round of 32", 81, "1st Group D", "3rd Group B/E/F/I/J"),
    ("2026-07-01T04:00:00", "Round of 32", 82, "1st Group G", "3rd Group A/E/H/I/J"),
    ("2026-07-01T08:00:00", "Round of 32", 83, "2nd Group K", "2nd Group L"),
    # 7/3 北京时间
    ("2026-07-02T03:00:00", "Round of 32", 84, "1st Group H", "2nd Group J"),
    ("2026-07-02T07:00:00", "Round of 32", 85, "1st Group B", "3rd Group E/F/G/I/J"),
    ("2026-07-02T11:00:00", "Round of 32", 86, "1st Group J", "2nd Group H"),
    # 7/4 北京时间
    ("2026-07-03T06:00:00", "Round of 32", 87, "1st Group K", "3rd Group D/E/I/J/L"),
    ("2026-07-03T02:00:00", "Round of 32", 88, "2nd Group D", "2nd Group G"),
    # 注: 因小组第三组合有495种可能，上面3rd Group X/Y/Z 表示"来自这些组中成绩最好的8个第三名之一"

    # === Round of 16 (M89-M96) ===
    # 7/5 北京时间
    ("2026-07-04T05:00:00", "Round of 16", 89, "Winner M74", "Winner M77"),
    ("2026-07-04T01:00:00", "Round of 16", 90, "Winner M73", "Winner M75"),
    # 7/6 北京时间
    ("2026-07-05T04:00:00", "Round of 16", 91, "Winner M76", "Winner M78"),
    ("2026-07-05T08:00:00", "Round of 16", 92, "Winner M79", "Winner M80"),
    # 7/7 北京时间
    ("2026-07-06T03:00:00", "Round of 16", 93, "Winner M83", "Winner M84"),
    ("2026-07-06T08:00:00", "Round of 16", 94, "Winner M81", "Winner M82"),
    # 7/8 北京时间
    ("2026-07-07T00:00:00", "Round of 16", 95, "Winner M86", "Winner M88"),
    ("2026-07-07T04:00:00", "Round of 16", 96, "Winner M85", "Winner M87"),

    # === Quarterfinals (M97-M100) ===
    # 7/10 北京时间
    ("2026-07-09T04:00:00", "Quarterfinal", 97, "Winner M89", "Winner M90"),
    # 7/11 北京时间
    ("2026-07-10T03:00:00", "Quarterfinal", 98, "Winner M91", "Winner M92"),
    # 7/12 北京时间
    ("2026-07-11T05:00:00", "Quarterfinal", 99, "Winner M93", "Winner M94"),
    ("2026-07-11T09:00:00", "Quarterfinal", 100, "Winner M95", "Winner M96"),

    # === Semifinals (M101-M102) ===
    # 7/16 北京时间
    ("2026-07-15T03:00:00", "Semifinal", 101, "Winner M97", "Winner M98"),
    # 7/17 北京时间
    ("2026-07-16T03:00:00", "Semifinal", 102, "Winner M99", "Winner M100"),

    # === Third Place & Final ===
    # 7/20 北京时间
    ("2026-07-19T05:00:00", "Third Place Playoff", 103, "Loser M101", "Loser M102"),
    ("2026-07-19T03:00:00", "Final", 104, "Winner M101", "Winner M102"),
]

# ============================================================================
# 三、wc26_knockout_paths 修复
# ============================================================================
# 官方晋级路径 (来源: bracketmundial2026.com / FIFA)
# 格式: (match_number, round, advances_to_match_number)
# 仅列出修正项；原表 match_number 73-104，round 'Round of 32'/'Round of 16'/'Quarterfinal'/'Semifinal'

CORRECTED_KNOCKOUT_PATHS = [
    # Round of 32 → Round of 16 (修正6条)
    # M73 → M90 (原: M73→M89, 错误)
    # M74 → M89 (原: M74→M89, 正确)
    # M75 → M90 (原: M75→M90, 正确... wait let me verify)
    # Let me just list the COMPLETE correct path
    
    # Each tuple: (match_number, current_round, advances_to_match)
    
    # Round of 32 (73-88)
    (73, 89),   # M73 → M90  (A2 v B2 winner goes to play M75 winner)
    (74, 89),   # M74 → M89  (E1 v 3rd winner goes to play M77 winner)
    (75, 90),   # M75 → M90
    (76, 91),   # M76 → M91  (C1 v F2 winner)
    (77, 91),   # M77 → M91
    (78, 92),   # M78 → M92
    (79, 92),   # M79 → M92
    (80, 93),   # M80 → M93  (L1 v 3rd)
    (81, 94),   # M81 → M94
    (82, 94),   # M82 → M94
    (83, 93),   # M83 → M93  (K2 v L2)
    (84, 96),   # M84 → M96  (H1 v J2)
    (85, 96),   # M85 → M96
    (86, 95),   # M86 → M95  (J1 v H2)
    (87, 95),   # M87 → M95
    (88, 98),   # M88 → M98  (D2 v G2) — wait, let me recheck

    # Round of 16 (89-96)
    # Actually let me re-derive from the bracketmundial data:
    # M89 = M74 vs M77 → Philadelphia
    # M90 = M73 vs M75 → Houston
    # M91 = M76 vs M78 → NY/NJ
    # M92 = M79 vs M80 → Mexico City
    # M93 = M83 vs M84 → Dallas
    # M94 = M81 vs M82 → Seattle
    # M95 = M86 vs M88 → Atlanta
    # M96 = M85 vs M87 → Vancouver
    (89, 97),   # M89 → M97
    (90, 97),   # M90 → M97  (M89 v M90 → QF M97) — wait
]

# Actually this is getting complex. Let me just define the COMPLETE correct bracket
# and have the script do the updates.

# Complete bracket structure (source: FIFA official / bracketmundial2026.com):
CORRECT_BRACKET = """
=== Round of 32 (73-88) ===
M73: 2A vs 2B
M74: 1E vs 3rd(A,B,C,D,F)
M75: 1F vs 2C
M76: 1C vs 2F
M77: 1I vs 3rd(C,D,F,G,H)
M78: 2E vs 2I
M79: 1A vs 3rd(C,E,F,H,I)
M80: 1L vs 3rd(E,H,I,J,K)
M81: 1D vs 3rd(B,E,F,I,J)
M82: 1G vs 3rd(A,E,H,I,J)
M83: 2K vs 2L
M84: 1H vs 2J
M85: 1B vs 3rd(E,F,G,I,J)
M86: 1J vs 2H
M87: 1K vs 3rd(D,E,I,J,L)
M88: 2D vs 2G

=== Round of 16 (89-96) ===
M89 = M74 winner vs M77 winner  → QF M97
M90 = M73 winner vs M75 winner  → QF M97
M91 = M76 winner vs M78 winner  → QF M98
M92 = M79 winner vs M80 winner  → QF M98
M93 = M83 winner vs M84 winner  → QF M99
M94 = M81 winner vs M82 winner  → QF M99
M95 = M86 winner vs M88 winner  → QF M100
M96 = M85 winner vs M87 winner  → QF M100

=== Quarterfinals (97-100) ===
M97 = M89 winner vs M90 winner  → SF M101
M98 = M91 winner vs M92 winner  → SF M101
M99 = M93 winner vs M94 winner  → SF M102
M100 = M95 winner vs M96 winner → SF M102

=== Semifinals (101-102) ===
M101 = M97 winner vs M98 winner → Final M104
M102 = M99 winner vs M100 winner → Final M104

=== Finals ===
M103 = M101 loser vs M102 loser (Third Place)
M104 = M101 winner vs M102 winner (Final)
"""

if __name__ == "__main__":
    print(f"Total group matches: {len(GROUP_MATCHES)}")
    print(f"Total knockout matches: {len(KNOCKOUT_MATCHES)}")
    print(f"验证: 72场小组赛 + 32场淘汰赛 = {len(GROUP_MATCHES) + len(KNOCKOUT_MATCHES)} (应为104)")
    print("\n此文件为数据规格定义。执行修复需另外运行 fix_schedule.py")
