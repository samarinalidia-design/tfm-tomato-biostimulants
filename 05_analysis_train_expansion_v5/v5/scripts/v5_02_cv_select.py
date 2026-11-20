"""V5 step 2: model selection on TRAIN only, nested CV grouped by dependency_cluster_id (outer 5 folds x seeds 11/22/33,
inner 3 folds by cluster). Candidate set and the selection rule are fixed before any TEST evaluation:

  Category A (a-priori, design features only):
     BASELINE_mean, MR0 (3-level intercept), RIDGE_REF, RF_REF, RIDGE_V3TE, RF_V3TETF,
     STACK_A_REF = mean(RIDGE_REF, RF_REF), STACK_A_V3 = mean(RIDGE_V3TE, RF_V3TETF),
     LSTACK_A = NNLS weights (inner CV) over MR0, RIDGE_REF, RIDGE_V3TE, RF_V3TETF
  Category B (conditional: needs the observed stress effect S_vs_C of the new study, used only as a meta-regression moderator):
     MR2mt (3-level, design moderators + S_vs_C, yield+biomass pooled), STACK_B_REF = mean(RIDGE_REF, MR2mt),
     STACK_B_MR0 = mean(MR0, MR2mt), STACK_B_V3 = mean(RIDGE_V3TE, MR2mt), LSTACK_B = LSTACK_A members + MR2mt
  Rule: per endpoint and category, the candidate with the lowest mean RMSE over the 3 seeds; if another candidate is
  within 1 % of it, the simpler one (fewer fitted components) is chosen. BASELINE_mean and MR0 are always reported.
"""
import sys, time, json
import numpy as np
import pandas as pd
from scipy.optimize import nnls
from v5_common import cv, r5, Y, B, fsets, with_dj2, SEEDS, SCHEME, RES, V5Featurizer, DUP_AUDIT

V3F = r5.V3Featurizer
LA = ['MR0', 'RIDGE_REF', 'RIDGE_V3TE', 'RF_V3TETF']
LB = LA + ['MR2mt']
EQUAL = {'STACK_A_REF': ['RIDGE_REF', 'RF_REF'], 'STACK_A_V3': ['RIDGE_V3TE', 'RF_V3TETF'],
         'STACK_B_REF': ['RIDGE_REF', 'MR2mt'], 'STACK_B_MR0': ['MR0', 'MR2mt'], 'STACK_B_V3': ['RIDGE_V3TE', 'MR2mt']}
CATEGORY = {'BASELINE_mean': 'A', 'MR0': 'A', 'RIDGE_REF': 'A', 'RF_REF': 'A', 'RIDGE_V3TE': 'A', 'RF_V3TETF': 'A',
            'STACK_A_REF': 'A', 'STACK_A_V3': 'A', 'LSTACK_A': 'A',
            'MR2mt': 'B', 'STACK_B_REF': 'B', 'STACK_B_MR0': 'B', 'STACK_B_V3': 'B', 'LSTACK_B': 'B'}
COMPLEXITY = {'BASELINE_mean': 0, 'MR0': 1, 'RIDGE_REF': 2, 'RIDGE_V3TE': 2, 'RF_REF': 3, 'RF_V3TETF': 3, 'MR2mt': 2,
              'STACK_A_REF': 4, 'STACK_A_V3': 4, 'STACK_B_REF': 4, 'STACK_B_MR0': 3, 'STACK_B_V3': 4, 'LSTACK_A': 6, 'LSTACK_B': 7}


def members(tr, te, trm, ep, seed, need, ctx):
    out, FS = {}, fsets(ep)
    mu, lo, hi, m0, _ = cv.fit_mr(tr, te, 'MR0', ep); tau2 = m0.sigma2.sum()
    out['MR0'] = (mu, lo, hi)
    if 'MR2mt' in need:
        mu, lo, hi, _, _ = cv.fit_mr(with_dj2(trm), with_dj2(te), 'MR2', ep, True); out['MR2mt'] = (mu, lo, hi)
    for nm, key, fs in [('RIDGE_REF', 'RIDGE', 'REF'), ('RF_REF', 'RF', 'REF'), ('RIDGE_V3TE', 'RIDGE', 'V3TE'), ('RF_V3TETF', 'RF', 'V3TETF')]:
        if nm not in need:
            continue
        cat, num, tek, tf = FS[fs]
        V3F.TE, V3F.TFIDF = tek, tf
        V5Featurizer.CONTEXT = f'{ctx}|{nm}'
        p, lo, hi, hp, _ = cv.fit_predict_ml(key, tr, te, cat, num, 'ivw_re', tau2, SCHEME, seed)
        out[nm] = (p, lo, hi)
    V3F.TE, V3F.TFIDF = [], False
    return out, tau2


def learn_weights(tr, trm, ep, seed, tau2, ctx):
    splits = cv.inner_splits(cv.inner_groups(tr, SCHEME), seed=seed + 1000)
    O = {k: np.full(len(tr), np.nan) for k in LB}
    for a, b in splits:
        tri, vai = tr.iloc[a].reset_index(drop=True), tr.iloc[b].reset_index(drop=True)
        trmi = trm[~trm.study_id.isin(set(vai.study_id))].reset_index(drop=True)
        o, _ = members(tri, vai, trmi, ep, seed, set(LB), ctx + '|inner')
        for k in LB:
            O[k][b] = o[k][0]
    y, w = tr.target.values, cv.weights(tr, 'ivw_re', tau2)
    res = {}
    for nm, mem in [('LSTACK_A', LA), ('LSTACK_B', LB)]:
        X = np.column_stack([O[k] for k in mem]); sw = np.sqrt(w)
        wt, _ = nnls(X * sw[:, None], y * sw)
        wt = wt / wt.sum() if wt.sum() > 0 else np.full(len(mem), 1 / len(mem))
        res[nm] = (mem, wt, float(np.quantile(np.abs(y - X @ wt), 0.95)))
    return res


def combine(out, tr, trm, ep, seed, tau2, ctx, W=None):
    for nm, mem in EQUAL.items():
        p = np.mean([out[k][0] for k in mem], axis=0); h = np.mean([(out[k][2] - out[k][1]) / 2 for k in mem], axis=0)
        out[nm] = (p, p - h, p + h)
    lw = learn_weights(tr, trm, ep, seed, tau2, ctx)
    for nm, (mem, wt, half) in lw.items():
        p = np.column_stack([out[k][0] for k in mem]) @ wt
        out[nm] = (p, p - half, p + half)
        if W is not None:
            W.append(dict(context=ctx, stack=nm, **{k: round(float(x), 4) for k, x in zip(mem, wt)}))
    return out, lw


def pools(ep, y, b):
    df = cv.select(ep, cv.BASE).reset_index(drop=True)
    other = cv.select('biomass' if ep == 'yield' else 'yield', cv.BASE)
    pool = pd.concat([df, other], ignore_index=True)
    return df.reindex(columns=pool.columns), pool


def run(ep, seed, tau2_ref, W):
    df, pool = pools(ep, cv.Y, cv.B)
    folds = cv.make_folds(SCHEME, seed)
    P = []
    for f in range(cv.N_OUTER):
        tr = df[df.study_id.map(folds) != f].reset_index(drop=True)
        te = df[df.study_id.map(folds) == f].reset_index(drop=True)
        trm = pool[pool.study_id.map(folds) != f].reset_index(drop=True)
        assert not set(trm.dependency_cluster_id) & set(te.dependency_cluster_id)
        if len(te) == 0:
            continue
        t0 = time.time(); ctx = f'{ep}|seed{seed}|fold{f}'
        out, tau2 = members(tr, te, trm, ep, seed + f, set(LB) | {'RF_REF'}, ctx)
        c = tr.target.mean(); hw = np.quantile(np.abs(tr.target - c), 0.95)
        out['BASELINE_mean'] = (np.full(len(te), c), np.full(len(te), c - hw), np.full(len(te), c + hw))
        out, _ = combine(out, tr, trm, ep, seed + f, tau2, ctx, W)
        print(f'  {ctx} {time.time() - t0:.0f}s', flush=True)
        for nm, (p, lo, hi) in out.items():
            P.append(pd.DataFrame(dict(contrast_id=te.contrast_id, study_id=te.study_id, cluster=te.dependency_cluster_id, fold=f,
                                       model=nm, y=te.target, pred=p, lo=lo, hi=hi, v_imp=te.var_lnrr_imp)))
    P = pd.concat(P, ignore_index=True)
    rows = [dict(endpoint=ep, model=nm, category=CATEGORY[nm], seed=seed, n_studies=g.study_id.nunique(), n_clusters=g.cluster.nunique(),
                 bias=float((g.pred - g.y).mean()),
                 **cv.metrics(g.y.values, g.pred.values, g.lo.values, g.hi.values, 1 / (g.v_imp.values + tau2_ref)))
            for nm, g in P.groupby('model')]
    return rows, P.assign(endpoint=ep, seed=seed)


def select_final(S):
    out = []
    for (ep, cat), g in S.groupby(['endpoint', 'category']):
        g = g.sort_values('RMSE'); best = g.iloc[0]
        near = g[g.RMSE <= best.RMSE * 1.01].copy()
        near['cx'] = near.model.map(COMPLEXITY)
        pick = near.sort_values(['cx', 'RMSE']).iloc[0]
        out.append(dict(endpoint=ep, category=cat, selected=pick.model, RMSE=pick.RMSE, best_by_RMSE=best.model, best_RMSE=best.RMSE,
                        within_1pct=';'.join(near.model)))
    return pd.DataFrame(out)


if __name__ == '__main__':
    import json as _j
    eps = sys.argv[1:] or ['yield', 'biomass']
    tau2_ref = {}
    for e in ('yield', 'biomass'):
        d0 = cv.select(e, cv.BASE).reset_index(drop=True)
        tau2_ref[e] = float(cv.fit_mr(d0, d0.iloc[:2], 'MR0', e)[3].sigma2.sum())
    _j.dump(tau2_ref, open(RES / 'v5_tau2_reference_for_wRMSE.json', 'w'))
    out_csv = RES / 'v5_cv_metrics_by_seed.csv'
    for ep in eps:
        for s in SEEDS:
            part = RES / f'v5_cv_{ep}_{s}.csv'
            if part.exists():
                continue
            W = []; t = time.time()
            r, p = run(ep, s, tau2_ref[ep], W)
            p.to_parquet(RES / f'v5_cv_oof_{ep}_{s}.parquet', index=False)
            pd.DataFrame(W).to_csv(RES / f'v5_cv_stack_weights_{ep}_{s}.csv', index=False)
            pd.DataFrame(DUP_AUDIT).to_csv(RES / f'v5_feature_duplicates_audit_{ep}_{s}.csv', index=False); DUP_AUDIT.clear()
            pd.DataFrame(r).to_csv(part, index=False)
            print(f'{ep} seed={s} {time.time() - t:.0f}s', flush=True)
