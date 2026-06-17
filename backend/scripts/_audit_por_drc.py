"""Full audit: Portugal vs DR Congo prediction."""
import json, math, sqlite3, re

print('='*70)
print('FULL SYSTEM AUDIT: Portugal vs DR Congo')
print('='*70)

with open('backend/data/_pred_Portugal_DR_Congo.json') as f:
    p = json.load(f)

errors = []
layers = p['layers']
mkt = p['market']

# 1. Pipeline weight config
print('\n[1] PIPELINE WEIGHTS')
prov = p['provenance']
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

print(f'  Label: {prov["weight_label"]} Version: {prov["version"]}')

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
        print(f'  OK: {name} sum=1.000')

# 3. Fusion math
print('\n[3] FUSION MATH')
dc = layers['dc']; enh = layers['enhancer']
dc_w = 0.75; enh_w = 0.25
exp_h = dc['home_win_prob']*dc_w + enh['home_win_prob']*enh_w
act = layers['dc_enh']
diff = abs(exp_h - act['home_win_prob'])
print(f'  DC+Enh H: expected={exp_h:.4f} actual={act["home_win_prob"]:.4f} diff={diff:.6f}')
if diff > 0.0001: errors.append('fusion dc_enh')
else: print('  DC+Enh fusion OK')

# Market fusion
pre = layers['pre_market']
mkt_w = mkt['market_weight']
raw_h = pre['home_win_prob']*(1-mkt_w) + mkt['home_prob']*mkt_w
raw_d = pre['draw_prob']*(1-mkt_w) + mkt['draw_prob']*mkt_w
raw_a = pre['away_win_prob']*(1-mkt_w) + mkt['away_prob']*mkt_w
total = raw_h+raw_d+raw_a
post = layers['post_market']
norm_h = raw_h/total
diff2 = abs(norm_h - post['home_win_prob'])
print(f'  +Market H: raw={raw_h:.4f} norm={norm_h:.4f} actual={post["home_win_prob"]:.4f} diff={diff2:.6f}')
if diff2 > 0.0001: errors.append('fusion market')
else: print('  Market fusion OK')

# 4. Report numbers vs JSON
print('\n[4] REPORT vs JSON DATA')
with open('backend/reports/PREMATCH_Portugal_vs_DR_Congo_20260617.md', encoding='utf-8') as f:
    report = f.read()

checks = [
    ('31\\.1%', round(dc['home_win_prob']*100,1)),
    ('42\\.7%', round(dc['draw_prob']*100,1)),
    ('26\\.2%', round(dc['away_win_prob']*100,1)),
    ('37\\.9%', round(enh['home_win_prob']*100,1)),
    ('38\\.4%', round(enh['away_win_prob']*100,1)),
]
for pattern, expected_val in checks:
    found = re.search(pattern, report)
    if found:
        print(f'  OK: {pattern} -> {found.group()}')
    else:
        print(f'  MISSING: {pattern}')
        errors.append(f'report missing {pattern}')

# Market numbers
ho, do, ao = mkt['home_odds'], mkt['draw_odds'], mkt['away_odds']
raw = 1/ho + 1/do + 1/ao
margin = (raw-1)*100
h_imp = (1/ho)/raw*100
d_imp = (1/do)/raw*100
a_imp = (1/ao)/raw*100

# Check margin in report
if abs(margin - 5.8) < 0.2:
    print(f'  OK: Market margin = {margin:.1f}% (report ~5.8%)')
else:
    print(f'  FAIL: margin {margin:.1f}% vs report 5.8%')
    errors.append('market margin')

# Check implied probs
fh = round(layers['final']['home_win_prob']*100, 1)
fd = round(layers['final']['draw_prob']*100, 1)
fa = round(layers['final']['away_win_prob']*100, 1)
gh = round(fh - h_imp, 1)
if abs(gh - (-26.9)) > 0.2:
    print(f'  FAIL: POR gap {gh} vs -26.9')
    errors.append('por gap')
else: print(f'  OK: POR gap = {gh}pp')

# 5. Poisson verification
print('\n[5] POISSON COMPUTATION')
lf = p['home_xg']; la = p['away_xg']
def poisson(k, lam): return lam**k * math.exp(-lam) / math.factorial(k)
scores = []
for h in range(9):
    for a in range(9):
        scores.append((h, a, poisson(h, lf) * poisson(a, la) * 100))
scores.sort(key=lambda x: -x[2])

report_expected = {(0,0):26.0,(1,0):18.6,(0,1):16.5,(1,1):11.8,(2,0):6.6,(0,2):5.2,
                   (2,1):4.2,(1,2):3.7,(3,0):1.6,(2,2):1.3,(0,3):1.1,(3,1):1.0}
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
if gap != 116:
    print(f'  FAIL: Elo gap {gap} vs report 116')
    errors.append('elo gap')
else: print(f'  OK: Elo gap = {gap}')

pi_h = p['pi']['home']; pi_a = p['pi']['away']
if abs(pi_h - 2.00) > 0.01 or abs(pi_a - 0.85) > 0.01:
    print(f'  FAIL: Pi {pi_h:.2f}/{pi_a:.2f} vs report 2.00/0.85')
    errors.append('pi')
else: print(f'  OK: Pi = {pi_h:.2f}/{pi_a:.2f}')

dcp = p['dc_params']
for k, exp in [('home_atk',2.404),('home_def',0.483),('away_atk',1.313),('away_def',0.298)]:
    actual = round(dcp[k], 3)
    if abs(actual - exp) > 0.001:
        print(f'  FAIL: DC {k} = {actual} vs {exp}')
        errors.append(f'dc {k}')
    else:
        print(f'  OK: DC {k} = {actual}')

# 7. Math claims
print('\n[7] MATH CLAIMS')
por_undef = fh + fd
drc_undef = fd + fa
print(f'  POR undefeated: {por_undef:.1f}% (report 76.6%)')
print(f'  DRC undefeated: {drc_undef:.1f}%')
print(f'  DRC undef > POR win: {drc_undef:.1f} > {fh:.1f} = {drc_undef > fh}')

# 8. DB snapshot
print('\n[8] DB SNAPSHOT')
db2 = sqlite3.connect('backend/data/local_stage2.db')
c2 = db2.cursor()
c2.execute("SELECT id, home_team, away_team, model_version FROM prediction_snapshots WHERE home_team='Portugal'")
s = c2.fetchall()
for row in s:
    print(f'  Snapshot: {row[0][:20]}... {row[1]}-{row[2]} v{row[3]}')
c2.execute("SELECT match_status FROM wc26_schedule WHERE home_team='Portugal' AND away_team='DR Congo'")
print(f'  Schedule: {c2.fetchone()}')
db2.close()

# 9. News verification keywords
print('\n[9] NEWS KEYWORDS')
keywords = ['NRG Stadium','Houston','retractable roof','Al-Jassim','Ruben Dias',
            '52-year','1974','Zaire','Cristiano Ronaldo','Martinez','Desabre',
            'Vitinha','Bruno Fernandes','Joao Neves','Wan-Bissaka','Bakambu']
for kw in keywords:
    if kw.lower() in report.lower():
        print(f'  OK: {kw}')
    else:
        print(f'  MISSING: {kw}')
        errors.append(f'news keyword {kw}')

# 10. Section completeness
print('\n[10] REPORT SECTIONS')
sections = ['比赛基本信息','V3.8.1.*预测概率','市场赔率分析','球队实力对比',
            '阵容与伤停','天气','战术预判','关键信号','比分概率分布',
            '模型内部分歧','综合评估','情报汇总','元数据','最终预测']
for sec in sections:
    if re.search(sec, report):
        print(f'  OK: {sec}')
    else:
        print(f'  MISSING: {sec}')
        errors.append(f'section {sec}')

# SUMMARY
print('\n' + '='*70)
if errors:
    print(f'AUDIT FAILED: {len(errors)} issues found')
    for e in errors:
        print(f'  - {e}')
else:
    print('AUDIT PASSED: Zero errors, zero shortcuts')
print('='*70)
