"""Comprehensive system overview after v2 cleanup."""
import sqlite3, json, os

DB = os.path.join(os.path.dirname(__file__), '..', 'data', 'local_stage2.db')
db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. PREDICTION RUNS — clean view
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print('=' * 70)
print('1. PREDICTION RUNS (by model_version + run_type)')
print('=' * 70)
for r in db.execute('''SELECT model_version, run_type, COUNT(*) as cnt
    FROM prediction_runs GROUP BY model_version, run_type
    ORDER BY cnt DESC'''):
    print(f'  v{r["model_version"]:25s} {r["run_type"]:20s} {r["cnt"]:4d}')
total_pr = db.execute('SELECT COUNT(*) FROM prediction_runs').fetchone()[0]
print(f'  {"TOTAL":>47s}  {total_pr:4d}')

# WC26-specific prediction runs
wc_pr = db.execute('''SELECT COUNT(*) FROM prediction_runs pr
    JOIN matches m ON REPLACE(LOWER(pr.match_id),"-","") = REPLACE(LOWER(m.id),"-","")
    WHERE m.competition LIKE "%World Cup 2026%"''').fetchone()[0]
print(f'\n  WC26 prediction runs: {wc_pr}')

# Old versions to clean
print('\n  [!] Old versions still present:')
for r in db.execute('''SELECT model_version, run_type, COUNT(*) as cnt
    FROM prediction_runs WHERE model_version NOT LIKE "4.%"
    GROUP BY model_version, run_type ORDER BY cnt DESC'''):
    print(f'      v{r["model_version"]:25s} {r["run_type"]:20s} {r["cnt"]:4d}')

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. LEARNING LOGS — accuracy metrics
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print('\n' + '=' * 70)
print('2. LEARNING LOGS — accuracy')
print('=' * 70)

for r in db.execute('SELECT status, COUNT(*) as cnt FROM prediction_learning_log GROUP BY status ORDER BY cnt DESC'):
    print(f'  {r["status"]:35s} {r["cnt"]:4d}')

# Active log accuracy
active = db.execute('''SELECT pll.match_id, pll.error_magnitude,
    pll.dc_marginal, pll.enhancer_marginal, pll.elo_marginal, pll.market_marginal,
    pr.model_version, pr.run_type
    FROM prediction_learning_log pll
    LEFT JOIN prediction_runs pr ON pll.prediction_run_id = pr.id
    WHERE pll.status = "active"
    ORDER BY pll.created_at DESC''').fetchall()

# Brier score from postmatch_eval
eval_briers = []
for r in db.execute('SELECT brier_score FROM postmatch_eval WHERE brier_score IS NOT NULL').fetchall():
    eval_briers.append(r['brier_score'])

if eval_briers:
    avg_brier = sum(eval_briers) / len(eval_briers)
    print(f'\n  Postmatch Brier scores: {len(eval_briers)} records')
    print(f'    Mean:   {avg_brier:.4f}')
    print(f'    Min:    {min(eval_briers):.4f}')
    print(f'    Max:    {max(eval_briers):.4f}')
    # Brier < 0.15 = excellent, < 0.20 = good, < 0.25 = acceptable, > 0.30 = poor
    excellent = sum(1 for b in eval_briers if b < 0.15)
    good = sum(1 for b in eval_briers if 0.15 <= b < 0.20)
    acceptable = sum(1 for b in eval_briers if 0.20 <= b < 0.25)
    poor = sum(1 for b in eval_briers if b >= 0.25)
    print(f'    < 0.15 (excellent): {excellent}')
    print(f'    0.15-0.20 (good):   {good}')
    print(f'    0.20-0.25 (ok):      {acceptable}')
    print(f'    >= 0.25 (poor):      {poor}')

# Active learning logs: marginal contributions (only using v4.x linked ones)
v4_active = [a for a in active if a['model_version'] and a['model_version'].startswith('4.')]
print(f'\n  Active logs linked to v4.x: {len(v4_active)}')
if v4_active:
    dc_vals = [a['dc_marginal'] for a in v4_active if a['dc_marginal'] is not None]
    enh_vals = [a['enhancer_marginal'] for a in v4_active if a['enhancer_marginal'] is not None]
    elo_vals = [a['elo_marginal'] for a in v4_active if a['elo_marginal'] is not None]
    mkt_vals = [a['market_marginal'] for a in v4_active if a['market_marginal'] is not None]
    avg_err = sum(a['error_magnitude'] for a in v4_active if a['error_magnitude'] is not None) / len(v4_active)

    def avg_pos(vals):
        """Avg of positive values (component helped)"""
        p = [v for v in vals if v and v > 0]
        return sum(p)/len(p) if p else 0
    def avg_neg(vals):
        """Avg of negative values (component hurt)"""
        n = [v for v in vals if v and v < 0]
        return sum(n)/len(n) if n else 0

    print(f'  Average error_magnitude: {avg_err:.4f}')
    print(f'\n  Marginal contributions (v4.x only):')
    print(f'    {"Component":12s} {"Mean":>8s} {"Positive%":>10s} {"Avg+":>8s} {"Avg-":>8s}')
    for name, vals in [('DC', dc_vals), ('Enhancer', enh_vals), ('Elo', elo_vals), ('Market', mkt_vals)]:
        if vals:
            mu = sum(vals)/len(vals)
            pos_pct = sum(1 for v in vals if v > 0) / len(vals) * 100
            print(f'    {name:12s} {mu:>+8.4f} {pos_pct:>9.1f}% {avg_pos(vals):>+8.4f} {avg_neg(vals):>+8.4f}')

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. WEIGHTS — actual configuration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print('\n' + '=' * 70)
print('3. WEIGHTS CONFIGURATION')
print('=' * 70)

print('\n  [DB model_weight_config — auto-optimized (REJECTED by sanity check)]')
for r in db.execute('SELECT config_key, config_value FROM model_weight_config WHERE config_key LIKE "auto_optimized_%"').fetchall():
    print(f'    {r["config_key"]:30s} = {r["config_value"]}')

print('\n  [DB model_weight_config — manual weights]')
for r in db.execute('SELECT config_key, config_value FROM model_weight_config WHERE config_key NOT LIKE "auto_optimized_%" AND config_key NOT LIKE "kappa_%" ORDER BY config_key').fetchall():
    print(f'    {r["config_key"]:30s} = {r["config_value"]}')

print('\n  [DB model_weight_config — kappa values]')
for r in db.execute('SELECT config_key, config_value FROM model_weight_config WHERE config_key LIKE "kappa_%" ORDER BY config_key').fetchall():
    print(f'    {r["config_key"]:30s} = {r["config_value"]}')

print('\n  [Code defaults — weights.py hardcoded]')
print('    WORLD_CUP_V4.3.1:       dc=0.90  enhancer=0.10  elo=0.12  pi=0.17  weibull=0.10  market_max=0.30')
print('    WORLD_CUP_KNOCKOUT_V4.3.1: dc=0.90  enhancer=0.10  elo=0.22  pi=0.18  weibull=0.10  market_max=0.30')
print('    LEAGUE:                 dc=0.50  enhancer=0.50  elo=0.05  pi=0.05  weibull=0.10  market_max=0.10')
print('    FRIENDLY_ADJUSTED_V2:   dc=0.28  enhancer=0.72  elo=0.02  pi=0.16  weibull=0.12  market_max=0.10')

# Sanity check result
print('\n  [Sanity check result]')
print('    auto_optimized_dc=0.0257 < floor 0.20 → REJECTED')
print('    Fallback → competition-aware defaults (WORLD_CUP_V4.3.1 for WC)')

# Effective sequential weights
print('\n  [Effective sequential weights — WC group stage V4.3.1]')
# DC=0.90, Enhancer=0.10, Weibull=0.10, Elo=0.12, Pi=0.17, Market=0.30
# Sequential fusion: each step's remaining weight pool
print('    Pipeline: DC(0.90) + Enhancer(0.10) → NegBin(5%) → Weibull(0.10) → Elo(0.12) → Pi(0.17) → Market(0.30)')
dc_eff = 0.90
enh_eff = 0.10  # (1-dc)
wb_eff = 0.10 * (1 - 0.05)  # after NegBin skims 5%
remaining = 1 - dc_eff - enh_eff - wb_eff
elo_eff = 0.12 * remaining
remaining -= elo_eff
pi_eff = 0.17 * remaining
remaining -= pi_eff
mkt_eff = 0.30 * remaining
print(f'    DC={dc_eff:.1%}  Enhancer={enh_eff:.1%}  NegBin=5%  Weibull={wb_eff:.1%}  Elo={elo_eff:.1%}  Pi={pi_eff:.1%}  Market={mkt_eff:.1%}')

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. COMPONENT ACCURACY (from postmatch_eval notes)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print('\n' + '=' * 70)
print('4. COMPONENT DIRECTIONAL ACCURACY (from WC memory)')
print('=' * 70)
print('  Last known panel (13 matches, before cleanup):')
print('    Market:    11/13 (85%)  — strongest')
print('    DC:        10/13 (77%)  — reliable')
print('    Pi:         9/13 (69%)  — best non-market')
print('    Elo:        9/13 (69%)  — reliable')
print('    Enhancer:   3/13 (23%)  — systematic away/underdog bias')
print('  → V4.3.1 response: ENHANCER weight reduced (dc 0.68→0.90)')

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. OLD ARTIFACTS CHECK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print('\n' + '=' * 70)
print('5. OLD VERSION ARTIFACTS')
print('=' * 70)

# Snapshots still not v4.x
old_snaps = db.execute('''SELECT model_version, COUNT(*) as cnt
    FROM prediction_snapshots WHERE model_version NOT LIKE "4.%"
    GROUP BY model_version ORDER BY cnt DESC''').fetchall()
print('\n  [Old prediction_snapshots]')
for r in old_snaps:
    print(f'    v{r["model_version"]:25s} {r["cnt"]:4d}')

# Old prediction_runs
old_pr = db.execute('''SELECT model_version, run_type, COUNT(*) as cnt
    FROM prediction_runs WHERE model_version NOT LIKE "4.%"
    GROUP BY model_version, run_type ORDER BY cnt DESC''').fetchall()
print('\n  [Old prediction_runs]')
for r in old_pr:
    print(f'    v{r["model_version"]:25s} {r["run_type"]:20s} {r["cnt"]:4d}')

# WC26 matches: finished + predicted + learned
print('\n  [WC26 coverage]')
wc_finished = db.execute('''SELECT COUNT(*) FROM matches
    WHERE competition LIKE "%World Cup 2026%" AND status IN ("finished","FINISHED")''').fetchone()[0]
wc_scheduled = db.execute('''SELECT COUNT(*) FROM matches
    WHERE competition LIKE "%World Cup 2026%" AND status NOT IN ("finished","FINISHED")''').fetchone()[0]
wc_with_pred = db.execute('''SELECT COUNT(DISTINCT pr.match_id) FROM prediction_runs pr
    JOIN matches m ON REPLACE(LOWER(pr.match_id),"-","") = REPLACE(LOWER(m.id),"-","")
    WHERE m.competition LIKE "%World Cup 2026%"''').fetchone()[0]
wc_with_learn = db.execute('''SELECT COUNT(DISTINCT pll.match_id) FROM prediction_learning_log pll
    JOIN matches m ON REPLACE(LOWER(pll.match_id),"-","") = REPLACE(LOWER(m.id),"-","")
    WHERE m.competition LIKE "%World Cup 2026%" AND pll.status = "active"''').fetchone()[0]
print(f'    Finished: {wc_finished}')
print(f'    Scheduled: {wc_scheduled}')
print(f'    With predictions: {wc_with_pred}')
print(f'    With active learning: {wc_with_learn}')

db.close()
print('\nDone.')
