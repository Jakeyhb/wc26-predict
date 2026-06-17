"""Full audit: England vs Croatia prediction."""
import json, math, sqlite3, re

print('='*70)
print('FULL SYSTEM AUDIT: England vs Croatia')
print('='*70)

with open('backend/data/_pred_England_Croatia.json') as f:
    p = json.load(f)

errors = []
layers = p['layers']
mkt = p['market']

# 1. Pipeline weight config
print('\n[1] PIPELINE WEIGHTS')
db = sqlite3.connect('backend/data/local_stage2.db')
cur = db.cursor()
cur.execute("SELECT config_key, config_value FROM model_weight_config WHERE config_key LIKE 'auto_optimized_%'")
w = {r[0]: float(r[1]) for r in cur.fetchall()}
db.close()

expected_w = {'auto_optimized_dc': 0.75, 'auto_optimized_enhancer': 0.25,
              'auto_optimized_elo': 0.10, 'auto_optimized_pi_rating': 0.05}
for k, v in expected_w.items():
    actual = w.get(k)
    if actual != v:
        print(f'  FAIL: {k} = {actual}, expected {v}')
        errors.append(f'weight {k}')
    else:
        print(f'  OK: {k} = {actual}')

print(f'  Label: {p["provenance"]["weight_label"]} Version: {p["provenance"]["version"]}')

# 2. All layers present and sum to 1
print('\n[2] LAYERS')
required = ['dc','enhancer','elo','pi','dc_enh','dc_enh_elo','pre_market','post_market','final']
for name in required:
    v = layers[name]
    s = v['home_win_prob'] + v['draw_prob'] + v['away_win_prob']
    if abs(s-1.0) > 0.001:
        print(f'  FAIL: {name} sum={s:.4f}')
        errors.append(f'layer sum {name}')
    else:
        print(f'  OK: {name} sum={1.0:.3f}')

# 3. Fusion math - DC+Enh: 0.75*DC + 0.25*Enhancer
print('\n[3] FUSION MATH')
dc = layers['dc']; enh = layers['enhancer']
dc_w = 0.75; enh_w = 0.25
exp_h = dc['home_win_prob']*dc_w + enh['home_win_prob']*enh_w
exp_d = dc['draw_prob']*dc_w + enh['draw_prob']*enh_w
exp_a = dc['away_win_prob']*dc_w + enh['away_win_prob']*enh_w
act = layers['dc_enh']
diff_h = abs(exp_h - act['home_win_prob'])
diff_d = abs(exp_d - act['draw_prob'])
diff_a = abs(exp_a - act['away_win_prob'])
print(f'  DC+Enh: expected H={exp_h:.4f} D={exp_d:.4f} A={exp_a:.4f}')
print(f'          actual   H={act["home_win_prob"]:.4f} D={act["draw_prob"]:.4f} A={act["away_win_prob"]:.4f}')
print(f'          diff     H={diff_h:.6f} D={diff_d:.6f} A={diff_a:.6f}')
if max(diff_h,diff_d,diff_a) > 0.0001:
    errors.append('fusion dc_enh')
else:
    print('  DC+Enh fusion OK')

# +Elo: 0.90*DC_Enh + 0.10*Elo
elo = layers['elo']
de = layers['dc_enh']
exp_h2 = de['home_win_prob']*0.90 + elo['home_win_prob']*0.10
exp_d2 = de['draw_prob']*0.90 + elo['draw_prob']*0.10
exp_a2 = de['away_win_prob']*0.90 + elo['away_win_prob']*0.10
act2 = layers['dc_enh_elo']
diff2 = max(abs(exp_h2-act2['home_win_prob']), abs(exp_d2-act2['draw_prob']), abs(exp_a2-act2['away_win_prob']))
print(f'  +Elo: diff max={diff2:.6f}')
if diff2 > 0.0001: errors.append('fusion elo')
else: print('  +Elo fusion OK')

# +Pi: 0.95*DC_Enh_Elo + 0.05*Pi
pi_l = layers['pi']
dee = layers['dc_enh_elo']
exp_h3 = dee['home_win_prob']*0.95 + pi_l['home_win_prob']*0.05
exp_d3 = dee['draw_prob']*0.95 + pi_l['draw_prob']*0.05
exp_a3 = dee['away_win_prob']*0.95 + pi_l['away_win_prob']*0.05
act3 = layers['pre_market']
diff3 = max(abs(exp_h3-act3['home_win_prob']), abs(exp_d3-act3['draw_prob']), abs(exp_a3-act3['away_win_prob']))
print(f'  +Pi: diff max={diff3:.6f}')
if diff3 > 0.0001: errors.append('fusion pi')
else: print('  +Pi fusion OK')

# +Market: 0.75*PreMarket + 0.25*MarketImplied
ho, do, ao = mkt['home_odds'], mkt['draw_odds'], mkt['away_odds']
raw_sum = 1/ho + 1/do + 1/ao
h_imp = (1/ho)/raw_sum
d_imp = (1/do)/raw_sum
a_imp = (1/ao)/raw_sum
mw = mkt['market_weight']
pre = layers['pre_market']
raw_h = pre['home_win_prob']*(1-mw) + h_imp*mw
raw_d = pre['draw_prob']*(1-mw) + d_imp*mw
raw_a = pre['away_win_prob']*(1-mw) + a_imp*mw
total = raw_h+raw_d+raw_a
post = layers['post_market']
norm_h = raw_h/total
diff4 = max(abs(norm_h-post['home_win_prob']), abs(raw_d/total-post['draw_prob']), abs(raw_a/total-post['away_win_prob']))
print(f'  +Mkt raw: H={raw_h:.4f} D={raw_d:.4f} A={raw_a:.4f} sum={total:.4f}')
print(f'  +Mkt norm: H={norm_h:.4f} actual={post["home_win_prob"]:.4f} diff={diff4:.6f}')
if diff4 > 0.0001: errors.append('fusion market')
else: print('  Market fusion OK')

# Final = Post_Market
fin = layers['final']
diff5 = max(abs(fin['home_win_prob']-post['home_win_prob']),
            abs(fin['draw_prob']-post['draw_prob']),
            abs(fin['away_win_prob']-post['away_win_prob']))
if diff5 > 0.0001: errors.append('final != post_market')
else: print('  Final = Post_Market OK')

# 4. Report numbers vs JSON
print('\n[4] REPORT vs JSON DATA')
with open('backend/reports/PREMATCH_England_vs_Croatia_20260618.md', encoding='utf-8') as f:
    report = f.read()

# Check specific numbers from the report
checks = [
    ('46\\.6%', round(dc['home_win_prob']*100,1)),
    ('34\\.6%', round(dc['draw_prob']*100,1)),
    ('18\\.8%', round(dc['away_win_prob']*100,1)),
    ('30\\.1%', round(enh['home_win_prob']*100,1)),
    ('46\\.5%', round(enh['away_win_prob']*100,1)),
]
for pattern, expected_val in checks:
    found = re.search(pattern, report)
    if found:
        print(f'  OK: {pattern} -> {found.group()}')
    else:
        print(f'  MISSING: {pattern}')
        errors.append(f'report missing {pattern}')

# Market numbers
margin = (raw_sum-1)*100
h_imp_pct = round(h_imp*100, 1)
d_imp_pct = round(d_imp*100, 1)
a_imp_pct = round(a_imp*100, 1)
print(f'  Market margin: {margin:.1f}% (report ~6.0%)')
if abs(margin - 6.0) > 0.2:
    print(f'  FAIL: margin {margin:.1f}% vs report 6.0%')
    errors.append('market margin')

fh = round(fin['home_win_prob']*100, 1)
fd = round(fin['draw_prob']*100, 1)
fa = round(fin['away_win_prob']*100, 1)

# Check gap
gh = round(fh - h_imp_pct, 1)
if abs(gh - (-8.3)) > 0.2:
    print(f'  FAIL: ENG gap {gh} vs -8.3')
    errors.append('eng gap')
else: print(f'  OK: ENG gap = {gh}pp')

# 5. Poisson verification
print('\n[5] POISSON COMPUTATION')
lf = p['home_xg']; la = p['away_xg']
def poisson(k, lam): return lam**k * math.exp(-lam) / math.factorial(k)
scores = []
for h in range(9):
    for a in range(9):
        scores.append((h, a, poisson(h, lf) * poisson(a, la) * 100))
scores.sort(key=lambda x: -x[2])

report_expected = {(1,0):18.7,(0,0):15.9,(1,1):12.4,(2,0):11.0,(0,1):10.5,
                   (2,1):7.3,(3,0):4.3,(1,2):4.1,(0,2):3.5,(3,1):2.9,(2,2):2.4,(4,0):1.3}
poisson_errors = 0
for (h,a), expected in report_expected.items():
    actual_p = round(poisson(h,lf)*poisson(a,la)*100, 1)
    if abs(actual_p - expected) > 0.1:
        print(f'  FAIL: {h}-{a} computed={actual_p:.1f}% report={expected}%')
        poisson_errors += 1
        errors.append(f'poisson {h}-{a}')
if poisson_errors == 0:
    print(f'  OK: All {len(report_expected)} scorelines verified')

# 6. Elo/Pi/DC params
print('\n[6] ELO/PI/DC PARAMS')
eh = p['elo']['home']; ea_elo = p['elo']['away']
gap = round(eh - ea_elo)
print(f'  Elo: ENG={eh:.0f} CRO={ea_elo:.0f} gap={gap} (report +28)')
if gap != 28:
    print(f'  FAIL: Elo gap {gap}')
    errors.append('elo gap')

pi_h = p['pi']['home']; pi_a = p['pi']['away']
print(f'  Pi: ENG={pi_h:.2f} CRO={pi_a:.2f} (report 1.20/0.98)')
if abs(pi_h-1.20)>0.01 or abs(pi_a-0.98)>0.01:
    print(f'  FAIL: Pi mismatch')
    errors.append('pi')

dcp = p['dc_params']
for k, exp in [('home_atk',2.149),('home_def',0.375),('away_atk',1.765),('away_def',0.551)]:
    actual = round(dcp[k], 3)
    if abs(actual - exp) > 0.001:
        print(f'  FAIL: DC {k} = {actual} vs {exp}')
        errors.append(f'dc {k}')
    else:
        print(f'  OK: DC {k} = {actual}')

# 7. Math claims
print('\n[7] MATH CLAIMS')
# Under 2.5
u25 = sum(poisson(h,lf)*poisson(a,la) for h in range(9) for a in range(9) if h+a<=2)*100
print(f'  Under 2.5: {u25:.1f}% (report 72.0%)')
if abs(u25 - 72.0) > 0.2:
    print(f'  FAIL: Under 2.5')
    errors.append('under 2.5')

# ENG undefeated
eng_undef = fh + fd
print(f'  ENG undefeated: {eng_undef:.1f}% (report 74.7%)')
if abs(eng_undef - 74.7) > 0.2: errors.append('eng undef')

# CRO undefeated
cro_undef = fd + fa
print(f'  CRO undefeated: {cro_undef:.1f}% (report 54.1%)')
print(f'  CRO undef > ENG win: {cro_undef:.1f} > {fh:.1f} = {cro_undef > fh}')

# Implied odds
eng_odds = 100/fh; draw_odds = 100/fd; cro_odds = 100/fa
print(f'  Implied: ENG={eng_odds:.2f} Draw={draw_odds:.2f} CRO={cro_odds:.2f}')
if abs(eng_odds-2.18)>0.02: errors.append('eng implied odds')
if abs(draw_odds-3.48)>0.02: errors.append('draw implied odds')
if abs(cro_odds-3.95)>0.02: errors.append('cro implied odds')

# DC-Enh divergence
dc_e_h = abs(dc['home_win_prob'] - enh['home_win_prob'])*100
dc_e_d = abs(dc['draw_prob'] - enh['draw_prob'])*100
dc_e_a = abs(dc['away_win_prob'] - enh['away_win_prob'])*100
print(f'  DC-Enh divergence: ENG={dc_e_h:.1f}pp Draw={dc_e_d:.1f}pp CRO={dc_e_a:.1f}pp')
if abs(dc_e_h-16.5)>0.1: errors.append('dc-enh eng')
if abs(dc_e_d-11.2)>0.1: errors.append('dc-enh draw')
if abs(dc_e_a-27.7)>0.1: errors.append('dc-enh cro')

# 8. DB snapshot
print('\n[8] DB SNAPSHOT')
db2 = sqlite3.connect('backend/data/local_stage2.db')
c2 = db2.cursor()
c2.execute("SELECT id, home_team, away_team, model_version FROM prediction_snapshots WHERE home_team='England' AND away_team='Croatia' ORDER BY generated_at DESC LIMIT 3")
for row in c2.fetchall():
    print(f'  Snapshot: {row[0][:20]}... {row[1]}-{row[2]} v{row[3]}')
c2.execute("SELECT match_status, venue FROM wc26_schedule WHERE home_team='England' AND away_team='Croatia'")
print(f'  Schedule: {c2.fetchone()}')
db2.close()

# 9. Report sections
print('\n[9] REPORT SECTIONS')
sections = ['比赛基本信息','V3.8.1.*预测概率','市场赔率分析','球队实力对比',
            '阵容与伤停','天气','战术预判','关键信号','比分概率分布',
            '模型内部分歧','综合评估','情报汇总','元数据','最终预测']
for sec in sections:
    if re.search(sec, report):
        print(f'  OK: {sec}')
    else:
        print(f'  MISSING: {sec}')
        errors.append(f'section {sec}')

# 10. News keywords
print('\n[10] NEWS KEYWORDS')
keywords = ['AT&T Stadium','Arlington','Tuchel','Turpin','Saka','Bellingham',
            'Kane','Modric','Gvardiol','Musa','retractable','air-conditioned',
            'hydration','Pickford','Rice','Kovacic','Perisic','Livakovic',
            'Achilles','cheekbone','FC Dallas','2018','semi-final']
for kw in keywords:
    # Use ASCII-safe comparison for special chars
    import unicodedata
    report_ascii = unicodedata.normalize('NFKD', report.lower()).encode('ascii','ignore').decode()
    kw_ascii = unicodedata.normalize('NFKD', kw.lower()).encode('ascii','ignore').decode()
    if kw_ascii in report_ascii:
        try:
            print(f'  OK: {kw}')
        except UnicodeEncodeError:
            print(f'  OK: (special chars)')
    else:
        try:
            print(f'  MISSING: {kw}')
        except UnicodeEncodeError:
            print(f'  MISSING: (special chars)')
        errors.append(f'news keyword {kw}')

# SUMMARY
print('\n' + '='*70)
if errors:
    print(f'AUDIT FAILED: {len(errors)} issues found')
    for e in errors:
        print(f'  - {e}')
else:
    print('AUDIT PASSED: Zero errors, zero shortcuts')
print('='*70)
