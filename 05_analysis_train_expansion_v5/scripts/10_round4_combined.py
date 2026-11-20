"""Round 4: do the individually helpful changes add up?
Combines: du Jardin v2 fix (round 3), yield+biomass multitask (main grid), MR2 with S_vs_C moderator, and a
pre-specified equal-weight stack (weights fixed in advance -> nothing tuned on validation rows).

Same study-grouped outer folds / seeds as all other rounds (make_folds over the union of studies), nested
tuning for ML, RE weights 1/(v+tau2_train). Evaluation on DEFAULT rows of the target endpoint.
Stack interval: mean of member half-widths (approximation; reported, not used for model choice).
"""
import sys, json, time, pathlib, importlib.util, warnings
import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('r3', HERE / '08_round3_features_outliers.py')
r3 = importlib.util.module_from_spec(spec); spec.loader.exec_module(r3)   # sets cv.Y/cv.B to v2 tables + context-aware imputation
cv, RES = r3.cv, r3.RES
warnings.filterwarnings('ignore')
_mm = cv.make_model
def make_model_lowmem(*a, **k):
    m, kind = _mm(*a, **k)
    if hasattr(m, 'n_jobs'):
        m.set_params(n_jobs=4)
    return m, kind
cv.make_model = make_model_lowmem

SEEDS = [11, 22, 33]
DJ2_NUM = ['h2_n_components', 'h2_live_microorganism', 'h2_nonliving_microbial_product']


def mt_feats():
    cat, num = cv.feature_lists('RAW+HARM', True)
    cat = [c for c in cat if c not in r3.V1_DJ] + ['h2_dujardin']
    num = [c for c in num if c not in r3.V1_DJ] + DJ2_NUM
    return cat, num


def with_dj2(df):
    d = df.copy(); d['h_dujardin'] = d['h2_dujardin']; return d


def run(ep, seed, tau2_ref):
    df = cv.select(ep, cv.BASE).reset_index(drop=True)
    other = cv.select('biomass' if ep == 'yield' else 'yield', cv.BASE)
    pool = pd.concat([df, other], ignore_index=True)
    df = df.reindex(columns=pool.columns)
    folds = cv.make_folds('study', seed)
    cat1, num1 = r3.feats(ep, 'V2_DUJARDIN_FIX')
    catc, numc = r3.feats(ep, 'V2_COMPACT')
    catm, numm = mt_feats()
    P = []
    for f in range(cv.N_OUTER):
        tr = df[df.study_id.map(folds) != f].reset_index(drop=True)
        te = df[df.study_id.map(folds) == f].reset_index(drop=True)
        trm = pool[pool.study_id.map(folds) != f].reset_index(drop=True)
        assert not set(trm.study_id) & set(te.study_id)
        if len(te) == 0:
            continue
        out = {}
        mu, lo, hi, m0, _ = cv.fit_mr(tr, te, 'MR0', ep); tau2 = m0.sigma2.sum()
        out['MR0_3level_intercept'] = (mu, lo, hi)
        mu, lo, hi, m0m, _ = cv.fit_mr(trm, te, 'MR0', ep); tau2m = m0m.sigma2.sum()
        c = tr.target.mean(); h = np.quantile(np.abs(tr.target - c), 0.95)
        out['BASELINE_mean'] = (np.full(len(te), c), np.full(len(te), c - h), np.full(len(te), c + h))
        for nm, (a, b, mt) in {'MR2_v2DJ': (tr, te, False), 'MR2_v2DJ_MULTITASK': (trm, te, True)}.items():
            try:
                mu, lo, hi, _, _ = cv.fit_mr(with_dj2(a), with_dj2(b), 'MR2', ep, mt); out[nm] = (mu, lo, hi)
            except Exception as ex:
                print('MR fail', nm, ex, flush=True)
        for nm, key, a, cc, nn, t2 in [('RIDGE_v2DJ', 'RIDGE', tr, cat1, num1, tau2), ('RF_v2DJ', 'RF', tr, cat1, num1, tau2),
                                       ('RF_v2COMPACT', 'RF', tr, catc, numc, tau2),
                                       ('RIDGE_v2DJ_MULTITASK', 'RIDGE', trm, catm, numm, tau2m),
                                       ('RF_v2DJ_MULTITASK', 'RF', trm, catm, numm, tau2m)]:
            p, lo, hi, hp, _ = cv.fit_predict_ml(key, a, te, cc, nn, 'ivw_re', t2, 'study', seed + f)
            out[nm] = (p, lo, hi)
        stacks = {'STACK3_RIDGEv2DJ_RFv2DJmt_MR2v2DJmt': ['RIDGE_v2DJ', 'RF_v2DJ_MULTITASK', 'MR2_v2DJ_MULTITASK'],
                  'STACK2_RIDGEv2DJ_MR2v2DJmt': ['RIDGE_v2DJ', 'MR2_v2DJ_MULTITASK'],
                  'STACK2_MR0_RFv2COMPACT': ['MR0_3level_intercept', 'RF_v2COMPACT'],
                  'STACK2_MR0_MR2v2DJmt': ['MR0_3level_intercept', 'MR2_v2DJ_MULTITASK']}
        for nm, mem in stacks.items():
            if all(k in out for k in mem):
                p = np.mean([out[k][0] for k in mem], axis=0)
                h = np.mean([(out[k][2] - out[k][1]) / 2 for k in mem], axis=0)
                out[nm] = (p, p - h, p + h)
        for nm, (p, lo, hi) in out.items():
            P.append(pd.DataFrame(dict(contrast_id=te.contrast_id, study_id=te.study_id, fold=f, model=nm, y=te.target,
                                       pred=p, lo=lo, hi=hi, v_imp=te.var_lnrr_imp)))
    P = pd.concat(P, ignore_index=True)
    rows = []
    for nm, g in P.groupby('model'):
        rows.append(dict(endpoint=ep, model=nm, seed=seed, eval_set='OWN_rows', n_studies=g.study_id.nunique(),
                         **cv.metrics(g.y.values, g.pred.values, g.lo.values, g.hi.values, 1 / (g.v_imp.values + tau2_ref))))
    return rows, P.assign(endpoint=ep, seed=seed)


if __name__ == '__main__':
    tau2_ref = json.load(open(RES / 'tau2_reference_for_wRMSE.json'))
    allr, allp = [], []
    for ep in ('yield', 'biomass'):
        for s in SEEDS:
            t = time.time()
            r, p = run(ep, s, tau2_ref[ep]); allr += r; allp.append(p)
            pd.DataFrame(allr).to_csv(RES / 'cv_metrics_round4_combined.csv', index=False)
            print(f'{ep} seed={s} {time.time() - t:.0f}s', flush=True)
    pd.concat(allp).to_parquet(RES / 'cv_oof_predictions_round4.parquet', index=False)
    M = pd.DataFrame(allr)
    b = M[M.model == 'BASELINE_mean'][['endpoint', 'seed', 'RMSE']].rename(columns={'RMSE': 'RMSE_base'})
    j = M.merge(b, on=['endpoint', 'seed'])
    j['dRMSE_pct_vs_mean'] = 100 * (j.RMSE - j.RMSE_base) / j.RMSE_base
    S = j.groupby(['endpoint', 'model']).agg(seeds=('seed', 'nunique'), RMSE=('RMSE', 'mean'), RMSE_sd=('RMSE', 'std'),
                                             MAE=('MAE', 'mean'), R2=('R2', 'mean'), wRMSE=('wRMSE', 'mean'),
                                             coverage95=('coverage95', 'mean'), PI_width=('mean_PI_width', 'mean'),
                                             dRMSE_pct_vs_mean=('dRMSE_pct_vs_mean', 'mean'),
                                             better_than_mean_all_seeds=('dRMSE_pct_vs_mean', lambda x: bool((x < 0).all()))).reset_index()
    S.sort_values(['endpoint', 'RMSE']).to_csv(RES / 'cv_metrics_round4_summary.csv', index=False)
    print(S.sort_values(['endpoint', 'RMSE']).round(4).to_string())
