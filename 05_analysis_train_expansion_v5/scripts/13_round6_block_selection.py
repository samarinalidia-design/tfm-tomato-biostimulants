"""Round 6 (yield): forward selection of v3 feature BLOCKS inside the inner CV.

For every outer training fold (study-grouped, same folds/seeds as all rounds):
  start = REF_V2DJ (round-3/4 best a-priori set)
  repeat (max MAX_STEPS): for each remaining block, inner grouped CV (3 folds by study, training studies only)
    -> weighted MSE (RE weights);  add the best block only if it lowers inner wMSE by >= MIN_GAIN (relative)
  then the usual nested hp tuning + refit on the whole training fold with the selected blocks, predict validation.
The outer validation studies are never used for block choice -> unbiased estimate of the whole procedure.
Selection cost control: RIDGE scored with its full alpha grid; RF scored with one fixed regularised setting
(max_features=0.33, min_samples_leaf=10, 150 trees); final RF re-tuned with the normal grid.
TE / TF-IDF blocks are fitted inside each inner training split (V3Featurizer from round 5).
"""
import sys, json, time, pathlib, importlib.util, warnings
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('r5', HERE / '12_round5_v3.py')
r5 = importlib.util.module_from_spec(spec); spec.loader.exec_module(r5)
cv, r3, RES = r5.cv, r5.r3, r5.RES
V3F = r5.V3Featurizer
warnings.filterwarnings('ignore')

MIN_GAIN, MAX_STEPS, SEEDS = 0.01, 3, [11, 22, 33]
Y3 = cv.Y
h = lambda p: [c for c in Y3.columns if c.startswith(p)]
BLOCKS = {   # name: (cat, num, te_keys, tfidf)
    'TAXON':    (['h3_genus_main'], h('h3_taxon_') + ['h3_n_taxa'], [], False),
    'ACTIVE':   ([], h('h3_active_') + ['h3_n_actives'], [], False),
    'ROUTE':    (['h3_n_applications_source'], h('h3_route_') + ['h3_n_routes', 'h3_n_applications', 'h3_log_n_applications'], [], False),
    'STRESS':   ([], [c for c in h('h3_stress_') if c not in ('h3_stress_onset_phase_ord', 'h3_stress_metal')] + ['h3_n_stresses'], [], False),
    'PHASE':    ([], ['h3_application_phase_ord', 'h3_stress_onset_phase_ord', 'h3_phase_app_minus_stress'], [], False),
    'SOIL_FERT': (['h3_soil_texture_source'], ['h3_sand_pct', 'h3_clay_pct'] + h('h3_fert_'), [], False),
    'SEASON':   ([], ['h3_start_month_sin', 'h3_start_month_cos', 'h3_experiment_year', 'h3_warm_season'], [], False),
    'GEO':      (['h3_region', 'h3_latitude_source'], ['h3_abs_latitude', 'h3_arid_country'], [], False),
    'GENOTYPE': ([], ['h3_hybrid', 'h3_declared_tolerance', 'h3_small_fruited', 'h3_processing_type'], [], False),
    'TE':       ([], [], r5.TE_KEYS, False),
    'TFIDF':    ([], [], [], True),
}


def compose(base, sel):
    cat, num, te, tf = list(base[0]), list(base[1]), [], False
    for b in sel:
        c, n, t, f = BLOCKS[b]
        cat += [x for x in c if x not in cat]; num += [x for x in n if x not in num]; te += t; tf = tf or f
    return cat, num, te, tf


def inner_score(name, tr, spec_, splits, wtr):
    cat, num, te, tf = spec_
    V3F.TE, V3F.TFIDF = te, tf
    y = tr.target.values
    if name == 'RIDGE':
        grid = cv.GRIDS['RIDGE']
    else:
        grid = [None]
    res = {i: np.full(len(tr), np.nan) for i in range(len(grid))}
    for itr, iva in splits:
        fz = V3F(cat, num).fit(tr.iloc[itr])
        kind = 'scaled' if name == 'RIDGE' else 'imputed'
        Xa, _ = fz.transform(tr.iloc[itr], kind); Xb, _ = fz.transform(tr.iloc[iva], kind)
        for i, hp in enumerate(grid):
            if name == 'RIDGE':
                m, _ = cv.make_model('RIDGE', hp, 0)
            else:
                m = RandomForestRegressor(n_estimators=150, max_features=0.33, min_samples_leaf=10, n_jobs=4, random_state=0)
            m.fit(Xa, y[itr], sample_weight=wtr[itr]); res[i][iva] = y[iva] - m.predict(Xb)
    return min(np.average(r ** 2, weights=wtr) for r in res.values())


def select_blocks(name, tr, base, tau2, seed):
    wtr = cv.weights(tr, 'ivw_re', tau2)
    splits = cv.inner_splits(cv.inner_groups(tr, 'study'), seed=seed)
    sel, best = [], inner_score(name, tr, compose(base, []), splits, wtr)
    trace = [('BASE', best)]
    for _ in range(MAX_STEPS):
        cand = {b: inner_score(name, tr, compose(base, sel + [b]), splits, wtr) for b in BLOCKS if b not in sel}
        b, sc = min(cand.items(), key=lambda kv: kv[1])
        if sc > best * (1 - MIN_GAIN):
            break
        sel.append(b); best = sc; trace.append((b, sc))
    return sel, trace


def run(seed, tau2_ref):
    ep = 'yield'
    df = cv.select(ep, cv.BASE).reset_index(drop=True)
    other = cv.select('biomass', cv.BASE)
    pool = pd.concat([df, other], ignore_index=True)
    df = df.reindex(columns=pool.columns)
    folds = cv.make_folds('study', seed)
    cat_ref, num_ref = r3.feats(ep, 'V2_DUJARDIN_FIX'); base = (cat_ref, num_ref)
    P, SEL = [], []
    for f in range(cv.N_OUTER):
        tr = df[df.study_id.map(folds) != f].reset_index(drop=True)
        te = df[df.study_id.map(folds) == f].reset_index(drop=True)
        trm = pool[pool.study_id.map(folds) != f].reset_index(drop=True)
        assert not set(tr.study_id) & set(te.study_id)
        if len(te) == 0:
            continue
        out = {}
        mu, lo, hi, m0, _ = cv.fit_mr(tr, te, 'MR0', ep); tau2 = m0.sigma2.sum()
        out['MR0_3level_intercept'] = (mu, lo, hi)
        c = tr.target.mean(); hw = np.quantile(np.abs(tr.target - c), 0.95)
        out['BASELINE_mean'] = (np.full(len(te), c), np.full(len(te), c - hw), np.full(len(te), c + hw))
        mu, lo, hi, _, _ = cv.fit_mr(r5.with_dj2(trm), r5.with_dj2(te), 'MR2', ep, True)
        out['MR2_v2DJ_MULTITASK'] = (mu, lo, hi)
        for key in ('RIDGE', 'RF'):
            V3F.TE, V3F.TFIDF = [], False
            p, lo, hi, _, _ = cv.fit_predict_ml(key, tr, te, cat_ref, num_ref, 'ivw_re', tau2, 'study', seed + f)
            out[f'{key}|REF_V2DJ'] = (p, lo, hi)
            t0 = time.time()
            sel, trace = select_blocks(key, tr, base, tau2, seed + f)
            cat, num, tek, tf = compose(base, sel)
            V3F.TE, V3F.TFIDF = tek, tf
            p, lo, hi, hp, _ = cv.fit_predict_ml(key, tr, te, cat, num, 'ivw_re', tau2, 'study', seed + f)
            out[f'{key}|SELECTED'] = (p, lo, hi)
            SEL.append(dict(seed=seed, fold=f, model=key, selected='+'.join(sel) or '(none)', hp=hp,
                            trace=json.dumps([(b, round(s, 5)) for b, s in trace]), sec=round(time.time() - t0)))
            print(f'  seed={seed} fold={f} {key}: {SEL[-1]["selected"]}  {SEL[-1]["trace"]}', flush=True)
        V3F.TE, V3F.TFIDF = [], False
        for fs in ('REF_V2DJ', 'SELECTED'):
            for nm, mem in [('STACK_A_RIDGE+RF', [f'RIDGE|{fs}', f'RF|{fs}']), ('STACK_B_RIDGE+MR2mt', [f'RIDGE|{fs}', 'MR2_v2DJ_MULTITASK'])]:
                p = np.mean([out[k][0] for k in mem], axis=0); hw = np.mean([(out[k][2] - out[k][1]) / 2 for k in mem], axis=0)
                out[f'{nm}|{fs}'] = (p, p - hw, p + hw)
        for nm, (p, lo, hi) in out.items():
            P.append(pd.DataFrame(dict(contrast_id=te.contrast_id, study_id=te.study_id, fold=f, model=nm, y=te.target,
                                       pred=p, lo=lo, hi=hi, v_imp=te.var_lnrr_imp)))
    P = pd.concat(P, ignore_index=True)
    rows = []
    for nm, g in P.groupby('model'):
        model, fs = (nm.split('|') + [''])[:2]
        rows.append(dict(endpoint=ep, model=model, feature_set=fs, seed=seed, n_studies=g.study_id.nunique(),
                         **cv.metrics(g.y.values, g.pred.values, g.lo.values, g.hi.values, 1 / (g.v_imp.values + tau2_ref))))
    return rows, P.assign(endpoint=ep, seed=seed), SEL


if __name__ == '__main__':
    tau2_ref = json.load(open(RES / 'tau2_reference_for_wRMSE.json'))
    out_csv, sel_csv = RES / 'cv_metrics_round6_blocksel.csv', RES / 'round6_selected_blocks.csv'
    allr = pd.read_csv(out_csv).to_dict('records') if out_csv.exists() else []
    alls = pd.read_csv(sel_csv).to_dict('records') if sel_csv.exists() else []
    done = {r['seed'] for r in allr}
    for s in SEEDS:
        if s in done:
            continue
        t = time.time()
        r, p, sel = run(s, tau2_ref['yield']); allr += r; alls += sel
        pd.DataFrame(allr).to_csv(out_csv, index=False); pd.DataFrame(alls).to_csv(sel_csv, index=False)
        p.to_parquet(RES / f'cv_oof_round6_yield_{s}.parquet', index=False)
        print(f'yield seed={s} {time.time() - t:.0f}s', flush=True)
    M = pd.DataFrame(allr)
    b = M[M.model == 'BASELINE_mean'][['seed', 'RMSE']].rename(columns={'RMSE': 'RMSE_base'})
    ref = M[M.feature_set == 'REF_V2DJ'][['model', 'seed', 'RMSE']].rename(columns={'RMSE': 'RMSE_ref'})
    j = M.merge(b, on='seed').merge(ref, on=['model', 'seed'], how='left')
    j['d_vs_mean_pct'] = 100 * (j.RMSE - j.RMSE_base) / j.RMSE_base
    j['d_vs_REF_pct'] = 100 * (j.RMSE - j.RMSE_ref) / j.RMSE_ref
    S = j.groupby(['endpoint', 'model', 'feature_set']).agg(
        seeds=('seed', 'nunique'), RMSE=('RMSE', 'mean'), RMSE_sd=('RMSE', 'std'), MAE=('MAE', 'mean'), R2=('R2', 'mean'),
        wRMSE=('wRMSE', 'mean'), coverage95=('coverage95', 'mean'), d_vs_mean_pct=('d_vs_mean_pct', 'mean'),
        d_vs_REF_pct=('d_vs_REF_pct', 'mean'), better_than_REF_all_seeds=('d_vs_REF_pct', lambda x: bool((x < 0).all()))).reset_index()
    S.sort_values('RMSE').to_csv(RES / 'cv_metrics_round6_summary.csv', index=False)
    pd.set_option('display.width', 250)
    print(S.sort_values('RMSE').round(4).to_string())
    print(pd.DataFrame(alls).groupby('model').selected.value_counts().to_string())
