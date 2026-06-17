"""Audit France vs Senegal prediction report against source JSON."""
import json, math

with open('backend/data/_pred_France_Senegal.json') as f:
    p = json.load(f)
layers = p['layers']

print('='*70)
print('COMPREHENSIVE AUDIT: France vs Senegal Prediction Report')
print('='*70)

errors = []
warnings = []

# ── Section 2.1: Layer probabilities ──
print('\n[2.1] Layer probability verification:')
checks = {
    'dc': ('41.8%', '31.7%', '26.5%'),
    'enhancer': ('31.5%', '23.3%', '45.1%'),
    'elo': ('52.6%', '11.8%', '35.6%'),
    'pi': ('50.2%', '20.3%', '29.5%'),
}
for layer, expected in checks.items():
    l = layers[layer]
    h = round(l['home_win_prob']*100, 1)
    d = round(l['draw_prob']*100, 1)
    a = round(l['away_win_prob']*100, 1)
    exp_h, exp_d, exp_a = expected
    ok = f'{h}%' == exp_h and f'{d}%' == exp_d and f'{a}%' == exp_a
    if ok: print(f'  {layer:10s}: {h}%/{d}%/{a}% OK')
    else:
        print(f'  {layer:10s}: GOT {h}%/{d}%/{a}% EXPECT {exp_h}/{exp_d}/{exp_a} ERROR')
        errors.append(f'{layer} probs mismatch')

# ── Fusion stages ──
print('\n[2.1b] Fusion stage verification:')
f_checks = {
    'dc_enh': ('39.2%', '29.6%', '31.2%'),
    'dc_enh_elo': ('40.5%', '27.8%', '31.6%'),
    'pre_market': ('41.0%', '27.4%', '31.5%'),
}
for layer, expected in f_checks.items():
    l = layers[layer]
    h = round(l['home_win_prob']*100, 1)
    d = round(l['draw_prob']*100, 1)
    a = round(l['away_win_prob']*100, 1)
    exp_h, exp_d, exp_a = expected
    ok = f'{h}%' == exp_h and f'{d}%' == exp_d and f'{a}%' == exp_a
    if ok: print(f'  {layer:15s}: {h}%/{d}%/{a}% OK')
    else:
        print(f'  {layer:15s}: GOT {h}%/{d}%/{a}% EXPECT {exp_h}/{exp_d}/{exp_a} ERROR')
        errors.append(f'{layer} fusion mismatch')

# ── Final probabilities ──
print('\n[2.2] Final prediction:')
final = layers['final']
fh_pct = round(final['home_win_prob']*100, 1)
fd_pct = round(final['draw_prob']*100, 1)
fa_pct = round(final['away_win_prob']*100, 1)
print(f'  France {fh_pct}% / Draw {fd_pct}% / Senegal {fa_pct}%')
fr_odds = 100/fh_pct
dr_odds = 100/fd_pct
sr_odds = 100/fa_pct
print(f'  Implied odds: France={fr_odds:.2f} Draw={dr_odds:.2f} Senegal={sr_odds:.2f}')
if abs(fr_odds - 2.13) > 0.02: errors.append(f'FR odds {fr_odds:.2f} vs report 2.13')
if abs(dr_odds - 3.88) > 0.02: errors.append(f'Draw odds {dr_odds:.2f} vs report 3.88')
if abs(sr_odds - 3.66) > 0.02: errors.append(f'SN odds {sr_odds:.2f} vs report 3.66')

# ── xG ──
print('\n[2.3] xG verification:')
hxg = p['home_xg']; axg = p['away_xg']
print(f'  France xG = {hxg:.2f} (report 1.32)')
print(f'  Senegal xG = {axg:.2f} (report 1.01)')
print(f'  Total xG = {hxg+axg:.2f} (report 2.33)')

# ── Section 3.1: Market margin CORRECTION ──
print('\n[3.1] Market odds & MARGIN:')
mkt = p['market']
ho, do, ao = mkt['home_odds'], mkt['draw_odds'], mkt['away_odds']
raw_sum = 1/ho + 1/do + 1/ao
margin = (raw_sum - 1) * 100
print(f'  Raw odds: H={ho}/D={do}/A={ao}')
print(f'  Sum of 1/odds: {raw_sum:.4f}')
print(f'  TRUE OVERROUND: {margin:.2f}%')
print(f'  Report says: ~3.7%')
if abs(margin - 6.6) < 0.2:
    print(f'  *** ERROR: Report margin ~3.7% is WRONG. Correct is ~{margin:.1f}% ***')
    errors.append(f'Market margin: report says ~3.7%, actual is ~{margin:.1f}%')
else:
    print(f'  Margin verified: {margin:.1f}%')

# Normalized implied probs
h_imp = (1/ho) / raw_sum * 100
d_imp = (1/do) / raw_sum * 100
a_imp = (1/ao) / raw_sum * 100
print(f'  Normalized implied: H={h_imp:.1f}% D={d_imp:.1f}% A={a_imp:.1f}%')
print(f'  Report: H=64.7% D=20.9% A=14.4%')

# ── Section 3.3: Model vs Market gap ──
print('\n[3.3] Model-Market gap:')
gh = round(fh_pct - h_imp, 1)
gd = round(fd_pct - d_imp, 1)
ga = round(fa_pct - a_imp, 1)
print(f'  France gap: {fh_pct} - {h_imp:.1f} = {gh:.1f}pp (report -17.8pp)')
print(f'  Draw gap:   {fd_pct} - {d_imp:.1f} = +{gd:.1f}pp (report +4.9pp)')
print(f'  Senegal gap: {fa_pct} - {a_imp:.1f} = +{ga:.1f}pp (report +12.9pp)')
if abs(gh - (-17.8)) > 0.2: errors.append(f'France gap')
if abs(gd - 4.9) > 0.2: errors.append(f'Draw gap')
if abs(ga - 12.9) > 0.2: errors.append(f'Senegal gap')

# ── Section 4.1: Elo gap ──
print('\n[4.1] Elo verification:')
eh = p['elo']['home']; ea = p['elo']['away']
gap = eh - ea
print(f'  France: {eh:.1f} -> {round(eh)} (report 1832)')
print(f'  Senegal: {ea:.1f} -> {round(ea)} (report 1765)')
print(f'  True gap: {gap:.2f} -> rounded {round(gap)}')
print(f'  Report: +67')
if round(gap) == 68:
    print(f'  *** WARNING: Gap rounds to {round(gap)}, but report says 67 ***')
    warnings.append(f'Elo gap: {gap:.2f} rounds to {round(gap)}, report says 67')
elif round(gap) == 67:
    print(f'  Elo gap OK')

# ── Section 4.2: Pi ──
print('\n[4.2] Pi verification:')
pi_h = p['pi']['home']; pi_a = p['pi']['away']
print(f'  France Pi: {pi_h:.2f} (report 1.38)')
print(f'  Senegal Pi: {pi_a:.2f} (report 1.08)')
print(f'  Direction: {"NORMAL" if pi_h > pi_a else "ANOMALY"}')

# ── Section 4.3: DC params ──
print('\n[4.3] DC params:')
dcp = p['dc_params']
print(f'  France: atk={dcp["home_atk"]:.3f} def={dcp["home_def"]:.3f}')
print(f'  Senegal: atk={dcp["away_atk"]:.3f} def={dcp["away_def"]:.3f}')

# ── Section 9: Poisson scoreline AUDIT ──
print('\n[9] POISSON SCORELINE AUDIT (CRITICAL):')
lf = p['home_xg']; la = p['away_xg']
print(f'  Lambda F={lf:.5f}, Lambda S={la:.5f}')

def poisson_pmf(k, lam):
    return lam**k * math.exp(-lam) / math.factorial(k)

scores = []
for h in range(8):
    for a in range(8):
        prob = poisson_pmf(h, lf) * poisson_pmf(a, la) * 100
        scores.append((h, a, prob))
scores.sort(key=lambda x: -x[2])

report_probs = {
    (1,1): 13.0, (1,0): 12.8, (2,1): 8.5, (2,0): 8.5,
    (0,0): 9.8, (0,1): 9.9, (1,2): 6.6, (0,2): 5.0, (2,2): 4.3, (3,1): 3.7
}

print(f'  Top 10 scorelines (independent Poisson):')
for i, (h, a, prob) in enumerate(scores[:10]):
    if h > a: result = 'FRA'
    elif a > h: result = 'SEN'
    else: result = 'DRAW'

    marker = ''
    if (h,a) in report_probs:
        rp = report_probs[(h,a)]
        diff = prob - rp
        if abs(diff) > 0.8:
            marker = f' <-- REPORT={rp:.1f}% DIFF={diff:+.1f}pp ***ERROR***'
            errors.append(f'Poisson {h}-{a}: computed {prob:.1f}% vs report {rp:.1f}% (diff {diff:+.1f}pp)')
        elif abs(diff) > 0.3:
            marker = f' <-- report={rp:.1f}% diff={diff:+.1f}pp (minor)'

    print(f'    #{i+1}: {h}-{a} = {prob:5.1f}% [{result:4s}]{marker}')

# Check if report has scorelines not in top 15
top_set = set((h,a) for h,a,_ in scores[:15])
missing = set(report_probs.keys()) - top_set
if missing:
    print(f'  Scorelines in report NOT in top 15 Poisson: {missing}')
    errors.append(f'Reported scorelines not in top 15: {missing}')

# ── Section 10.1: DC-Enhancer divergence ──
print('\n[10.1] DC-Enhancer divergence:')
dc = layers['dc']; enh = layers['enhancer']
dh = round(abs(dc['home_win_prob'] - enh['home_win_prob']) * 100, 1)
dd = round(abs(dc['draw_prob'] - enh['draw_prob']) * 100, 1)
da = round(abs(dc['away_win_prob'] - enh['away_win_prob']) * 100, 1)
print(f'  France: {dh}pp (report 10.3pp)')
print(f'  Draw:   {dd}pp (report 8.4pp)')
print(f'  Senegal: {da}pp (report 18.6pp)')
if abs(dh-10.3) > 0.1: errors.append(f'DC-Enh France gap')
if abs(dd-8.4) > 0.1: errors.append(f'DC-Enh Draw gap')
if abs(da-18.6) > 0.1: errors.append(f'DC-Enh Senegal gap')

# ── Section 14: Math claims ──
print('\n[14] Final math claims:')
fra_undef = fh_pct + fd_pct
sen_undef = fd_pct + fa_pct
print(f'  France undefeated: {fh_pct}+{fd_pct}={fra_undef:.1f}% (report 72.7%)')
print(f'  Senegal undefeated: {fd_pct}+{fa_pct}={sen_undef:.1f}% (report 53.1%)')
print(f'  Senegal undef > France win: {sen_undef:.1f} > {fh_pct:.1f} = {sen_undef > fh_pct}')

# ── Weight config ──
print('\n[Weights] Configuration:')
print(f'  DC=0.75 Enhancer=0.25 (=1-DC={1-0.75}) Elo=0.10 Pi=0.05 Market=0.25')
print(f'  Label: AUTO_OPTIMIZED (V3.8.1)')

# ── SUMMARY ──
print('\n' + '='*70)
print('FINAL AUDIT VERDICT')
print('='*70)
if errors:
    print(f'\nERRORS FOUND: {len(errors)}')
    for i, e in enumerate(errors, 1):
        print(f'  {i}. {e}')
else:
    print('\nNo computational errors found.')
if warnings:
    print(f'\nWARNINGS: {len(warnings)}')
    for i, w in enumerate(warnings, 1):
        print(f'  {i}. {w}')
print()

