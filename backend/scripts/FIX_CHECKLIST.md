# 修复清单

## 文件位置
数据库: `D:\hermes agent\2026世界杯分析\backend\data\local_stage2.db`
数据规格: `backend/scripts/schedule_fix_spec.py`
修复脚本: `backend/scripts/fix_schedule.py` (待编写并执行)

---

## 修复 1: `matches` 表 — 72场小组赛日期+时间

**问题:** 所有比赛日期错误，按每天6场均分12天，实际每天2-4场共17天。

**操作:** 根据 `schedule_fix_spec.py` 中的 `GROUP_MATCHES` 列表，逐场 UPDATE。

方法: 通过 `teams.name` 匹配 `home_team_id`/`away_team_id`，然后更新 `match_date`。

```sql
-- 示例：墨西哥 vs 南非应为 6/12 03:00 北京 = 6/11 19:00 UTC
UPDATE matches SET match_date = '2026-06-11T19:00:00'
WHERE competition LIKE '%World Cup 2026%'
  AND home_team_id = (SELECT id FROM teams WHERE name = 'Mexico')
  AND away_team_id = (SELECT id FROM teams WHERE name = 'South Africa')
  AND stage = 'Group A - Matchday 1';
```

共72条类似UPDATE。

---

## 修复 2: `wc26_schedule` 表 — 小组赛日期+开球时间

**问题:** `match_date` 和 `kickoff_time` 与实际不符。实际 kickoff_time 是当地时间（北美），需要换算。

**操作:** 清空后重新插入。数据规格见 `schedule_fix_spec.py`。

---

## 修复 3: `matches` 表 — 32场淘汰赛日期+落位

**问题:**
1. 日期偏移1-3天
2. 所有对阵写死为 TBD，缺少落位规则
3. 每天固定2场，实际每天2-4场

**操作:** 更新 `match_date`，并将 `home_team_id`/`away_team_id` 替换为落位描述（写入 `stage` 备注或新建字段）。

```sql
-- 32强 M73: A2 vs B2, 6/29 03:00 北京 = 6/28 19:00 UTC
UPDATE matches SET match_date = '2026-06-28T19:00:00',
    stage = 'Round of 32 — A2 vs B2'
WHERE stage = 'Round of 32' AND match_number = 73;
```

完整的32场规格见 `schedule_fix_spec.py` 中的 `KNOCKOUT_MATCHES`。

---

## 修复 4: `wc26_knockout_paths` 表 — 晋级路径

**问题:** 8条路径中6条错误。数据库使用简单顺序配对(73+74→89)，FIFA实际使用交叉落位。

**正确路径:**

| 32强来源 | → 16强 | → 8强 | → 半决赛 | → 决赛 |
|----------|--------|-------|----------|--------|
| M73, M75 | M90 | | | |
| M74, M77 | M89 | M97 | | |
| M76, M78 | M91 | | M101 | |
| M79, M80 | M92 | M98 | | |
| M83, M84 | M93 | | | M104 |
| M81, M82 | M94 | M99 | | |
| M86, M88 | M95 | | M102 | |
| M85, M87 | M96 | M100 | | |

需修正的条目:
- M73 → M90 (原 M89)
- M75 → M90 (原 M90) ✅
- M77 → M91 (原 M91) ✅  
- M81 → M94 (原 M93)
- M82 → M94 (原 M94) ✅
- M83 → M93 (原 M95)
- M84 → M96 (原 M96) ✅
- M85 → M93 (原 M93)... 

实际上更简单的方式：**DELETE FROM wc26_knockout_paths 然后按上方表格重新 INSERT**。

完整SQL:
```sql
DELETE FROM wc26_knockout_paths;
INSERT INTO wc26_knockout_paths (round, match_number, winner_advances_to_match) VALUES
('Round of 32', 73, 90), ('Round of 32', 74, 89),
('Round of 32', 75, 90), ('Round of 32', 76, 91),
('Round of 32', 77, 91), ('Round of 32', 78, 92),
('Round of 32', 79, 92), ('Round of 32', 80, 93),
('Round of 32', 81, 94), ('Round of 32', 82, 94),
('Round of 32', 83, 93), ('Round of 32', 84, 96),
('Round of 32', 85, 96), ('Round of 32', 86, 95),
('Round of 32', 87, 95), ('Round of 32', 88, 98),
('Round of 16', 89, 97),  ('Round of 16', 90, 97),
('Round of 16', 91, 98),  ('Round of 16', 92, 98),
('Round of 16', 93, 99),  ('Round of 16', 94, 99),
('Round of 16', 95, 100), ('Round of 16', 96, 100),
('Quarterfinal', 97, 101), ('Quarterfinal', 98, 101),
('Quarterfinal', 99, 102), ('Quarterfinal', 100, 102),
('Semifinal', 101, 104),   ('Semifinal', 102, 104);
```

---

## 修复 5: `matches` 表 — 淘汰赛UTC时间转换为北京时间存储

**注意:** `matches.match_date` 存储的是UTC，但淘汰赛规格中的时间是北京时间。需转换：`UTC = 北京时间 - 8小时`。

所有淘汰赛UTC时间见 `schedule_fix_spec.py` 中 `KNOCKOUT_MATCHES` 第一列。

---

## 修复顺序建议

1. **先备份** `cp local_stage2.db local_stage2.db.bak`
2. 更新 `matches` 表小组赛日期 (72条)
3. 更新 `matches` 表淘汰赛日期+落位 (32条)
4. 重建 `wc26_schedule` 表
5. 重建 `wc26_knockout_paths` 表
6. 验证: `SELECT count(*), date(match_date) FROM matches WHERE competition LIKE '%World Cup%' GROUP BY date(match_date) ORDER BY date(match_date)`
