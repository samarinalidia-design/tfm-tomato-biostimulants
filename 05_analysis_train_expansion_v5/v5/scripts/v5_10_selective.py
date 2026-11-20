"""V5 add-on: selective prediction (abstention) on TRAIN only. TEST is not read.

Question (pre-specified, written to results/selective/PLAN_selective.json before any result is computed):
  Can we tell in advance for which contrasts the a-priori model errs less, and does predicting only those
  give an advantage over simple alternatives while keeping a practically useful number of studies?

Design
  * Outer folds = the V5 nested CV folds (grouped by dependency_cluster_id, seeds 11/22/33).
  * Models refit in every outer training fold: BASELINE_mean, MR0, RIDGE_REF (selected category-A model, nested tuning).
  * Confidence scores, learnt from the outer TRAINING fold only:
      AD_DISTANCE    mean distance to the 5 nearest training contrasts (standardised design features of the fold's featuriser);
                     training reference distribution uses neighbours from OTHER clusters only
      LOCAL_ERROR    mean |inner out-of-fold Ridge residual| of the 15 nearest training contrasts (other clusters for the reference)
      DISAGREEMENT   |Ridge prediction - training mean| (reference: inner out-of-fold Ridge predictions)
      RANDOM         uniform random score (control)
  * Retention targets r = 0.5 ... 1.0: threshold = r-quantile of the training reference scores; a validation contrast is
    predicted if its score <= threshold. Achieved retention, retained studies and clusters are reported.
  * Comparisons on the SAME retained contrasts: Ridge vs mean vs MR0; and Ridge-retained vs Ridge-all.
  * Ridge 95 % interval = quantile of inner OOF residuals (as in the frozen pipeline): coverage and width on retained rows.
  * Uncertainty: 2000 cluster-bootstrap resamples of the pooled outer predictions (per seed), CIs averaged over seeds.
  Primary analysis: yield, LOCAL_ERROR, r = 0.8. Advantage = Ridge beats the mean on the retained set with CI < 0 AND the gain
  over the mean is larger than without abstention (r = 1.0) AND >= 50 % of the TRAIN studies keep at least one prediction.
"""
import json, time
import numpy as np
import pandas as pd
from v5_common import cv, fsets, SCHEME, RES, SEEDS, V5Featurizer
import v5_02_cv_select as S

OUT = RES / 'selective'; OUT.mkdir(exist_ok=True)
R_GRID = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
SCORES = ['AD_DISTANCE', 'LOCAL_ERROR', 'DISAGREEMENT', 'RANDOM']
K_AD, K_LE = 5, 15


def ridge_fold(tr, te, ep, tau2, seed):
    """Nested-tuned Ridge (identical procedure to cv.fit_predict_ml) that also returns the inner OOF residuals and the featuriser."""
    cat, num, _, _ = fsets(ep)['REF']
    ytr = tr.target.values; wtr = cv.weights(tr, 'ivw_re', tau2)
    splits = cv.inner_splits(cv.inner_groups(tr, SCHEME), seed=seed)
    best, best_sc, best_res = None, np.inf, None
    for hp in cv.GRIDS['RIDGE']:
        res = np.full(len(tr), np.nan)
        for itr, iva in splits:
            fz = cv.Featurizer(cat, num).fit(tr.iloc[itr]); m, kind = cv.make_model('RIDGE', hp, seed)
            Xa, _ = fz.transform(tr.iloc[itr], kind); Xb, _ = fz.transform(tr.iloc[iva], kind)
            m.fit(Xa, ytr[itr], sample_weight=wtr[itr]); res[iva] = ytr[iva] - m.predict(Xb)
        sc = np.average(res ** 2, weights=wtr)
        if sc < best_sc:
            best, best_sc, best_res = hp, sc, res
    fz = cv.Featurizer(cat, num).fit(tr); m, kind = cv.make_model('RIDGE', best, seed)
    Xtr, _ = fz.transform(tr, kind); Xte, _ = fz.transform(te, kind)
    m.fit(Xtr, ytr, sample_weight=wtr)
    return m.predict(Xte), best_res, float(np.quantile(np.abs(best_res), 0.95)), Xtr, Xte


def knn_mean(Xq, Xr, vals, k, excl_q=None, excl_r=None):
    out = np.empty(len(Xq))
    for i in range(len(Xq)):
        d = np.sqrt(((Xr - Xq[i]) ** 2).sum(1))
        if excl_q is not None:
            d[excl_r == excl_q[i]] = np.inf
        idx = np.argpartition(d, k)[:k]
        out[i] = d[idx].mean() if vals is None else np.mean(vals[idx])
    return out


def run(ep, seed):
    df, _ = S.pools(ep, cv.Y, cv.B)
    folds = cv.make_folds(SCHEME, seed)
    rows = []
    for f in range(cv.N_OUTER):
        tr = df[df.study_id.map(folds) != f].reset_index(drop=True); te = df[df.study_id.map(folds) == f].reset_index(drop=True)
        if len(te) == 0:
            continue
        mu0, lo0, hi0, m0, _ = cv.fit_mr(tr, te, 'MR0', ep); tau2 = m0.sigma2.sum()
        V5Featurizer.CONTEXT = f'SELECTIVE|{ep}|{seed}|{f}'
        pr, res_in, half, Xtr, Xte = ridge_fold(tr, te, ep, tau2, seed + f)
        cl_tr, mean_tr = tr.dependency_cluster_id.values, tr.target.mean()
        rng = np.random.default_rng(1000 * seed + f)
        sc_tr = {'AD_DISTANCE': knn_mean(Xtr, Xtr, None, K_AD, cl_tr, cl_tr),
                 'LOCAL_ERROR': knn_mean(Xtr, Xtr, np.abs(res_in), K_LE, cl_tr, cl_tr),
                 'DISAGREEMENT': np.abs((tr.target.values - res_in) - mean_tr),
                 'RANDOM': rng.uniform(size=len(tr))}
        sc_te = {'AD_DISTANCE': knn_mean(Xte, Xtr, None, K_AD),
                 'LOCAL_ERROR': knn_mean(Xte, Xtr, np.abs(res_in), K_LE),
                 'DISAGREEMENT': np.abs(pr - mean_tr),
                 'RANDOM': rng.uniform(size=len(te))}
        base = pd.DataFrame(dict(endpoint=ep, seed=seed, fold=f, contrast_id=te.contrast_id, study_id=te.study_id,
                                 cluster=te.dependency_cluster_id, y=te.target.values, pred_ridge=pr, pred_mean=mean_tr, pred_mr0=mu0,
                                 lo_ridge=pr - half, hi_ridge=pr + half))
        for s in SCORES:
            base[f'score_{s}'] = sc_te[s]
            for r in R_GRID:
                thr = np.inf if r >= 1 else np.quantile(sc_tr[s], r)
                base[f'keep_{s}_{r}'] = (sc_te[s] <= thr).astype(int)
        rows.append(base)
        print(f'  {ep} seed={seed} fold={f}', flush=True)
    return pd.concat(rows, ignore_index=True)


def rmse(e):
    return float(np.sqrt(np.mean(e ** 2))) if len(e) else np.nan


def summarise(P, n_train_studies, B=2000):
    out = []
    for (ep, seed), g in P.groupby(['endpoint', 'seed']):
        uc = g.cluster.unique(); idx = {c: np.where(g.cluster.values == c)[0] for c in uc}
        rng = np.random.default_rng(seed)
        boots = [np.concatenate([idx[c] for c in rng.choice(uc, len(uc), replace=True)]) for _ in range(B)]
        y, pr, pm, p0 = g.y.values, g.pred_ridge.values, g.pred_mean.values, g.pred_mr0.values
        lo, hi = g.lo_ridge.values, g.hi_ridge.values
        ridge_all = rmse(pr - y); mean_all = rmse(pm - y)
        for s in SCORES:
            for r in R_GRID:
                k = g[f'keep_{s}_{r}'].values.astype(bool)
                d_mean = [rmse(pr[b][k[b]] - y[b][k[b]]) - rmse(pm[b][k[b]] - y[b][k[b]]) for b in boots]
                d_all = [rmse(pr[b][k[b]] - y[b][k[b]]) - rmse(pr[b] - y[b]) for b in boots]
                gain_vs_r1 = [(rmse(pr[b][k[b]] - y[b][k[b]]) - rmse(pm[b][k[b]] - y[b][k[b]])) - (rmse(pr[b] - y[b]) - rmse(pm[b] - y[b])) for b in boots]
                q = lambda v: (float(np.nanquantile(v, .025)), float(np.nanquantile(v, .975)))
                out.append(dict(endpoint=ep, seed=seed, score=s, target_retention=r, retained_frac=k.mean(), retained_contrasts=int(k.sum()),
                                retained_studies=g.study_id[k].nunique(), retained_studies_frac=g.study_id[k].nunique() / n_train_studies[ep],
                                RMSE_ridge=rmse(pr[k] - y[k]), RMSE_mean=rmse(pm[k] - y[k]), RMSE_MR0=rmse(p0[k] - y[k]),
                                RMSE_ridge_all=ridge_all, RMSE_mean_all=mean_all,
                                d_ridge_vs_mean=rmse(pr[k] - y[k]) - rmse(pm[k] - y[k]), d_ridge_vs_mean_ci=q(d_mean),
                                d_ridge_vs_ridge_all=rmse(pr[k] - y[k]) - ridge_all, d_ridge_vs_ridge_all_ci=q(d_all),
                                extra_gain_vs_no_abstention=float(np.mean(gain_vs_r1)), extra_gain_ci=q(gain_vs_r1),
                                coverage_ridge=float(np.mean((y[k] >= lo[k]) & (y[k] <= hi[k]))), width_ridge=float(np.mean(hi[k] - lo[k]))))
    S_ = pd.DataFrame(out)
    for c in ['d_ridge_vs_mean_ci', 'd_ridge_vs_ridge_all_ci', 'extra_gain_ci']:
        S_[c + '_lo'] = S_[c].map(lambda t: t[0]); S_[c + '_hi'] = S_[c].map(lambda t: t[1])
    S_ = S_.drop(columns=['d_ridge_vs_mean_ci', 'd_ridge_vs_ridge_all_ci', 'extra_gain_ci'])
    S_.to_csv(OUT / 'selective_by_seed.csv', index=False)
    A = S_.groupby(['endpoint', 'score', 'target_retention']).mean(numeric_only=True).drop(columns='seed').reset_index()
    A.to_csv(OUT / 'selective_summary.csv', index=False)
    return A


if __name__ == '__main__':
    plan = dict(created=time.strftime('%Y-%m-%dT%H:%M:%S'), data='V5 TRAIN only (TEST not read)', doc=__doc__)
    json.dump(plan, open(OUT / 'PLAN_selective.json', 'w'), indent=1)
    parts = []
    for ep in ('yield', 'biomass'):
        for s in SEEDS:
            p = OUT / f'selective_oof_{ep}_{s}.parquet'
            if not p.exists():
                run(ep, s).to_parquet(p, index=False)
            parts.append(pd.read_parquet(p))
    P = pd.concat(parts)
    nst = {'yield': cv.select('yield', cv.BASE).study_id.nunique(), 'biomass': cv.select('biomass', cv.BASE).study_id.nunique()}
    A = summarise(P, nst)
    pd.set_option('display.width', 250)
    cols = ['endpoint', 'score', 'target_retention', 'retained_frac', 'retained_studies', 'RMSE_ridge', 'RMSE_mean', 'RMSE_MR0', 'd_ridge_vs_mean',
            'd_ridge_vs_mean_ci_lo', 'd_ridge_vs_mean_ci_hi', 'extra_gain_vs_no_abstention', 'extra_gain_ci_lo', 'extra_gain_ci_hi', 'coverage_ridge', 'width_ridge']
    print(A[cols].round(4).to_string())
