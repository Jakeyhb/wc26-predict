"""Full audit: Ghana vs Panama prediction."""
import json, math, sqlite3, re, unicodedata

print('='*70)
print('FULL SYSTEM AUDIT: Ghana vs Panama')
print('='*70)

with open('backend/data/_pred_Ghana_Panama.json') as f:
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
    if w.get(k) != v:
        print(f'  FAIL: {k} = {w.get(k)}, expected {v}')
        errors.append(f'weight {k}')
    else:
        print(f'  OK: {k} = {w.get(k)}')
print(f'  Label: {p["provenance"]["weight_label"]}')

# 2. All layers
print('\n[2] LAYERS')
for name in ['dc','enhancer','elo','pi','dc_enh','dc_enh_elo','pre_market','post_market','final']:
    v = layers[name]; s = v['home_win_prob']+v['draw_prob']+v['away_win_prob']
    if abs(s-1.0) > 0.001:
        print(f'  FAIL: {name} sum={s:.4f}')
        errors.append(f'layer sum {name}')
    else:
        print(f'  OK: {name} sum=1.000')

# 3. Fusion math
print('\n[3] FUSION MATH')
dc=layers['dc']; enh=layers['enhancer']; elo=layers['elo']; pi_l=layers['pi']
# DC+Enh
h1=0.75*dc['home_win_prob']+0.25*enh['home_win_prob']
d1=0.75*dc['draw_prob']+0.25*enh['draw_prob']
a1=0.75*dc['away_win_prob']+0.25*enh['away_win_prob']
act1=layers['dc_enh']
d1max = max(abs(h1-act1['home_win_prob']), abs(d1-act1['draw_prob']), abs(a1-act1['away_win_prob']))
print(f'  DC+Enh diff={d1max:.6f} {"OK" if d1max<0.0001 else "FAIL"}')
if d1max>0.0001: errors.append('fusion dc_enh')
# +Elo
h2=0.90*h1+0.10*elo['home_win_prob']; d2=0.90*d1+0.10*elo['draw_prob']; a2=0.90*a1+0.10*elo['away_win_prob']
act2=layers['dc_enh_elo']
d2max = max(abs(h2-act2['home_win_prob']), abs(d2-act2['draw_prob']), abs(a2-act2['away_win_prob']))
print(f'  +Elo diff={d2max:.6f} {"OK" if d2max<0.0001 else "FAIL"}')
if d2max>0.0001: errors.append('fusion elo')
# +Pi
h3=0.95*h2+0.05*pi_l['home_win_prob']; d3=0.95*d2+0.05*pi_l['draw_prob']; a3=0.95*a2+0.05*pi_l['away_win_prob']
act3=layers['pre_market']
d3max = max(abs(h3-act3['home_win_prob']), abs(d3-act3['draw_prob']), abs(a3-act3['away_win_prob']))
print(f'  +Pi diff={d3max:.6f} {"OK" if d3max<0.0001 else "FAIL"}')
if d3max>0.0001: errors.append('fusion pi')
# +Market
ho,do,ao=mkt['home_odds'],mkt['draw_odds'],mkt['away_odds']
rs=1/ho+1/do+1/ao; h_imp=(1/ho)/rs; d_imp=(1/do)/rs; a_imp=(1/ao)/rs; mw=mkt['market_weight']
rh=h3*(1-mw)+h_imp*mw; rd=d3*(1-mw)+d_imp*mw; ra=a3*(1-mw)+a_imp*mw; tot=rh+rd+ra
post=layers['post_market']
d4max = max(abs(rh/tot-post['home_win_prob']), abs(rd/tot-post['draw_prob']), abs(ra/tot-post['away_win_prob']))
print(f'  +Mkt diff={d4max:.6f} {"OK" if d4max<0.0001 else "FAIL"}')
if d4max>0.0001: errors.append('fusion market')
# Final==Post
d5max = max(abs(layers['final']['home_win_prob']-post['home_win_prob']),
            abs(layers['final']['draw_prob']-post['draw_prob']),
            abs(layers['final']['away_win_prob']-post['away_win_prob']))
print(f'  Final=Post diff={d5max:.6f} {"OK" if d5max<0.0001 else "FAIL"}')
if d5max>0.0001: errors.append('final != post')

# 4. Report numbers vs JSON
print('\n[4] REPORT vs JSON')
with open('backend/reports/PREMATCH_Ghana_vs_Panama_20260618.md', encoding='utf-8') as f:
    report = f.read()
for pat in ['27\\.6%','30\\.2%','42\\.2%','13\\.4%','63\\.4%','43\\.1%','29\\.6%','27\\.3%']:
    if re.search(pat, report):
        print(f'  OK: {pat}')
    else:
        print(f'  MISSING: {pat}')
        errors.append(f'report missing {pat}')
margin=(rs-1)*100
print(f'  Margin: {margin:.1f}% (report ~6.3%)')
if abs(margin-6.3)>0.2: errors.append('margin')
fh=layers['final']['home_win_prob']*100; h_imp_pct=h_imp*100
gh=round(fh-h_imp_pct,1)
print(f'  GHA gap: {gh}pp (report -12.0pp)')
if abs(gh-(-12.0))>0.2: errors.append('gha gap')

# 5. Poisson
print('\n[5] POISSON')
lf=p['home_xg']; la=p['away_xg']
def poi(k,lam): return lam**k*math.exp(-lam)/math.factorial(k)
expected_poisson = {(1,1):12.5,(0,1):11.2,(1,2):8.9,(1,0):8.8,(0,2):8.0,(0,0):7.9,
                    (2,1):7.0,(2,2):5.0,(2,0):4.9,(1,3):4.2,(0,3):3.8,(3,1):2.6,(2,3):2.4,(3,2):1.8}
errs=0
for (h,a),exp in expected_poisson.items():
    act=round(poi(h,lf)*poi(a,la)*100,1)
    if abs(act-exp)>0.1:
        print(f'  FAIL: {h}-{a} computed={act:.1f}% report={exp}%')
        errs+=1; errors.append(f'poisson {h}-{a}')
if errs==0: print(f'  OK: All {len(expected_poisson)} scorelines verified')

# 6. Elo/Pi/DC
print('\n[6] ELO/PI/DC')
gap=round(p['elo']['home']-p['elo']['away'])
print(f'  Elo gap={gap} (report -88)')
if gap!=-88: errors.append('elo gap')
print(f'  Pi={p["pi"]["home"]:.2f}/{p["pi"]["away"]:.2f} (report 0.45/0.51)')
if abs(p['pi']['home']-0.45)>0.01 or abs(p['pi']['away']-0.51)>0.01: errors.append('pi')
dcp=p['dc_params']
for k,exp in [('home_atk',1.395),('home_def',0.793),('away_atk',1.813),('away_def',0.804)]:
    a=round(dcp[k],3)
    if abs(a-exp)>0.001:
        print(f'  FAIL: DC {k}={a} vs {exp}')
        errors.append(f'dc {k}')
    else: print(f'  OK: DC {k}={a}')

# 7. Math claims
print('\n[7] MATH CLAIMS')
u25=sum(poi(h,lf)*poi(a,la) for h in range(9) for a in range(9) if h+a<=2)*100
# Find Under 2.5 in section 9 (Poisson section) — look for the bold one
u25_match = re.search(r'Under 2\.5 概率.*?\*\*(\d+\.\d+)%\*\*', report)
report_u25 = float(u25_match.group(1)) if u25_match else 0.0
print(f'  Under 2.5: {u25:.1f}% (report {report_u25:.1f}%)')
if abs(u25-report_u25) > 0.3: errors.append(f'under 2.5 computed={u25:.1f} vs report={report_u25:.1f}')
pan_undef=layers['final']['draw_prob']*100+layers['final']['away_win_prob']*100
print(f'  PAN undef: {pan_undef:.1f}% (report 70.4%)')
if abs(pan_undef-70.4)>0.2: errors.append('pan undef')
dc_e_pan=abs(dc['away_win_prob']-enh['away_win_prob'])*100
print(f'  DC-Enh PAN div: {dc_e_pan:.1f}pp (report 21.2pp)')
if abs(dc_e_pan-21.2)>0.2: errors.append('dc-enh pan')
pan_odds=1/layers['final']['away_win_prob']
print(f'  PAN fair odds: {pan_odds:.2f} (report 2.32)')
if abs(pan_odds-2.32)>0.02: errors.append('pan odds')

# 8. DB snapshot
print('\n[8] DB SNAPSHOT')
db2=sqlite3.connect('backend/data/local_stage2.db')
c2=db2.cursor()
c2.execute("SELECT id,home_team,away_team,model_version FROM prediction_snapshots WHERE home_team='Ghana' ORDER BY generated_at DESC LIMIT 2")
for r in c2.fetchall(): print(f'  Snapshot: {r[0][:30]}... {r[1]}-{r[2]} v{r[3]}')
c2.execute("SELECT match_status,venue FROM wc26_schedule WHERE home_team='Ghana' AND away_team='Panama'")
print(f'  Schedule: {c2.fetchone()}')
db2.close()

# 9. Sections
print('\n[9] SECTIONS')
for sec in ['比赛基本信息','预测概率','市场赔率分析','球队实力对比','阵容与伤停','天气与场地','战术预判','关键信号','比分概率分布','模型内部分歧','综合评估','情报汇总','元数据','最终预测']:
    if re.search(sec, report): print(f'  OK: {sec}')
    else:
        print(f'  MISSING: {sec}')
        errors.append(f'section {sec}')

# 10. Anti-laziness checks
print('\n[10] ANTI-LAZINESS')
tilde_pct=re.findall(r'~\d+\.?\d*%', report)
if tilde_pct:
    print(f'  FAIL: {len(tilde_pct)} ~X% approximation(s)')
    errors.append(f'{len(tilde_pct)} ~X% approximations')
else: print('  OK: No ~X% approximations')
for eyeball_pat in ['大约','大概','差不多']:
    # Only flag if near a percentage sign (probability context)
    for m in re.finditer(eyeball_pat, report):
        ctx = report[max(0,m.start()-3):m.end()+8]
        if '%' in ctx:
            print(f'  WARNING: eyeball "{eyeball_pat}" near %: "{ctx}"')
            errors.append(f'eyeball: {eyeball_pat}')
if not any(re.search(f'{e}.*%|%.*{e}', report) for e in ['大约','大概','差不多']):
    print('  OK: No eyeballed probability values')

# 11. News keyword depth
print('\n[11] NEWS DEPTH')
keywords=['Partey','visa','Kudus','Semenyo','Man City','62.5M','Queiroz','Christiansen',
          'BMO Field','Toronto','NYBERG','Carrasquilla','Godoy','Ismael Diaz',
          'storm','thunderstorm','80-100','100 km/h','unbeaten','10场不败','7场不胜']
for kw in keywords:
    kw_a=unicodedata.normalize('NFKD',kw.lower()).encode('ascii','ignore').decode()
    rp_a=unicodedata.normalize('NFKD',report.lower()).encode('ascii','ignore').decode()
    if kw_a in rp_a: print(f'  OK: {kw}')
    else:
        print(f'  MISSING: {kw}')
        errors.append(f'keyword {kw}')

# SUMMARY
print('\n'+'='*70)
if errors:
    print(f'AUDIT: {len(errors)} issues found')
    for e in errors: print(f'  - {e}')
else:
    print('AUDIT PASSED: Zero errors')
print('='*70)
