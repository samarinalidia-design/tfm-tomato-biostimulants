"""Chlorophyll analogues of the V5 analyses behind TFM Figs 17, 21, 22 and 23 (same procedures as v5_02 / v5_06 / v5_10).

  uncertainty : grouped CV (same folds / seeds / configs as c09) that also keeps the 95 % intervals of every model
                (ML: quantile of inner out-of-fold residuals; MR0: model-based mu +/- 1.96 sqrt(tau2 + v) as fit_mr;
                 mean: training mean +/- 95 % quantile of |training residual|)  -> coverage vs half-width (TFM Fig 17)
  learning    : grouped learning curves, seed 11 folds, 20-100 % of the training clusters, 3 draws (TFM Fig 21)
  ad          : applicability domain = mean distance to the 5 nearest TRAIN contrasts of other dependency clusters in the
                standardised feature space of the frozen ML candidate; threshold = 95th percentile of TRAIN; errors of the
                ML candidate (CV out-of-fold seed 11 and TEST)  (TFM Fig 22)     [uses the frozen models, after the freeze]
  selective   : selective prediction (abstention) on TRAIN, nested CV seeds 11/22/33, scores AD_DISTANCE / LOCAL_ERROR /
                DISAGREEMENT / RANDOM, retention 0.5-1.0 (TFM Fig 23). TEST not read.
ML model per target = the pre-declared ML candidate of the freeze (CHL_CONTENT: RF_REF_wn; CHL_INDEX: RF_REF_wivw_re).
Usage: python c15_chl_extra.py uncertainty|learning|ad|selective chlorophyll|chl_index
Outputs: results/c15_<analysis>_<target>*.csv
"""
import sys, json, pathlib
import numpy as np
import pandas as pd

OUT = pathlib.Path(__file__).resolve().parents[1]
REPO = OUT.parent
sys.path.insert(0, str(REPO / '05_analysis_train_expansion_v5' / 'v5' / 'scripts'))
_argv = sys.argv; sys.argv = sys.argv[:1]
import v5_common as V
sys.argv = _argv
cv, r5 = V.cv, V.r5
RES = OUT / 'results'
ANALYSIS, TARGET = sys.argv[1], sys.argv[2]
EP = {'chlorophyll': 'CHL_CONTENT', 'chl_index': 'CHL_INDEX'}[TARGET]
ML = {'chlorophyll': ('RF', 'n'), 'chl_index': ('RF', 'ivw_re')}[TARGET]
ML_NAME = f'{ML[0]}_REF_w{ML[1]}'
CONFIGS = [('RIDGE', 'ivw_re'), ('RIDGE', 'none'), ('RIDGE', 'n'), ('RF', 'ivw_re'), ('RF', 'n')]
SEEDS = [11, 22, 33]


def prep(T):
    T = T[T.in_default == 1].copy()
    T['study_id'] = T.study_id.astype(str); T['target'] = T.effect.astype(float); T['v'] = T.var_lnrr_imp.astype(float)
    T['exp_uid'] = T.study_id + '|' + T.experiment_key.astype(str); T['endpoint_is_yield'] = 0
    T = T[T.target.notna() & T.v.notna() & (T.v > 0)].reset_index(drop=True)
    T['w_n'] = 1.0 / T.groupby('study_id').target.transform('size')
    return T


f_tr = 'train_chlorophyll_V8.parquet' if TARGET == 'chlorophyll' else 'train_chl_index_V8.parquet'
T = prep(pd.read_parquet(OUT / 'data' / f_tr))
cat, num, _, _ = V.fsets('biomass')['REF']
cat = ['chl_basis', 'chl_measure_kind'] + [c for c in cat if c != 'organ_scope']
num = [c for c in num if c != 'dry_basis_confirmed'] + ['is_computed_total']
cat = [c for c in cat if c in T.columns]; num = [c for c in num if c in T.columns]
cv.ALL = T[['study_id', 'dependency_cluster_id']].drop_duplicates('study_id')
cv.STUDY2CLUSTER = cv.ALL.set_index('study_id').dependency_cluster_id
cv.ROWS_PER_STUDY = T.study_id.value_counts()
r5.V3Featurizer.TE, r5.V3Featurizer.TFIDF = [], False


def fit_ml(name, w, tr, te, tau2, seed):
    """cv.fit_predict_ml with the inner OOF residuals and the fitted featuriser returned as well."""
    ytr = tr.target.values; wtr = cv.weights(tr, w, tau2)
    splits = cv.inner_splits(cv.inner_groups(tr, 'cluster'), seed=seed)
    best, best_sc, best_res = None, np.inf, None
    for hp in cv.GRIDS[name]:
        res = np.full(len(tr), np.nan)
        for itr, iva in splits:
            fz = cv.Featurizer(cat, num).fit(tr.iloc[itr]); m, kind = cv.make_model(name, hp, seed)
            Xa, _ = fz.transform(tr.iloc[itr], kind); Xb, _ = fz.transform(tr.iloc[iva], kind)
            m.fit(Xa, ytr[itr], sample_weight=wtr[itr]); res[iva] = ytr[iva] - m.predict(Xb)
        sc = np.average(res ** 2, weights=wtr)
        if sc < best_sc:
            best, best_sc, best_res = hp, sc, res
    fz = cv.Featurizer(cat, num).fit(tr); m, kind = cv.make_model(name, best, seed)
    Xa, _ = fz.transform(tr, kind); Xb, _ = fz.transform(te, kind)
    m.fit(Xa, ytr, sample_weight=wtr)
    return m.predict(Xb), best_res, float(np.quantile(np.abs(best_res), 0.95)), fz


def outer(seed):
    folds = cv.make_folds('cluster', seed)
    for f in range(cv.N_OUTER):
        te = T[T.study_id.map(folds) == f].reset_index(drop=True)
        if te.empty:
            continue
        tr = T[(T.study_id.map(folds) != f) & ~T.dependency_cluster_id.isin(set(te.dependency_cluster_id))].reset_index(drop=True)
        yield f, tr, te


def uncertainty():
    P = []
    for seed in SEEDS:
        for f, tr, te in outer(seed):
            mu, lo, hi, m0, _ = cv.fit_mr(tr, te, 'MR0', 'biomass'); tau2 = m0.sigma2.sum()
            c = tr.target.mean(); hw = float(np.quantile(np.abs(tr.target - c), 0.95))
            out = {'MR0': (mu, lo, hi), 'BASELINE_mean': (np.full(len(te), c), np.full(len(te), c - hw), np.full(len(te), c + hw))}
            for name, w in CONFIGS:
                p, _, half, _ = fit_ml(name, w, tr, te, tau2, seed + f)
                out[f'{name}_REF_w{w}'] = (p, p - half, p + half)
            for m, (p, l, h) in out.items():
                P.append(pd.DataFrame(dict(target=TARGET, seed=seed, fold=f, model=m, contrast_id=te.contrast_id, study_id=te.study_id,
                                           cluster=te.dependency_cluster_id, y=te.target, pred=p, lo=l, hi=h)))
            print(TARGET, 'uncertainty seed', seed, 'fold', f, flush=True)
    P = pd.concat(P, ignore_index=True); P.to_parquet(RES / f'c15_uncertainty_oof_{TARGET}.parquet', index=False)
    S = P.assign(cov=((P.y >= P.lo) & (P.y <= P.hi)).astype(float), half=(P.hi - P.lo) / 2, e2=(P.y - P.pred) ** 2) \
         .groupby('model').agg(coverage95=('cov', 'mean'), half_width=('half', 'mean'), MSE=('e2', 'mean')).reset_index()
    S['RMSE'] = np.sqrt(S.pop('MSE')); S.insert(0, 'target', TARGET)
    S.to_csv(RES / f'c15_uncertainty_{TARGET}.csv', index=False); print(S.round(3).to_string(index=False))


def learning():
    rows = []
    for f, tr0, te in outer(11):
        cl = np.array(sorted(tr0.dependency_cluster_id.unique()))
        for frac in (0.2, 0.4, 0.6, 0.8, 1.0):
            for draw in range(3 if frac < 1 else 1):
                rng = np.random.default_rng(100 * f + draw)
                keep = rng.choice(cl, max(5, int(round(frac * len(cl)))), replace=False)
                tr = tr0[tr0.dependency_cluster_id.isin(keep)].reset_index(drop=True)
                tr['w_n'] = 1.0 / tr.groupby('study_id').target.transform('size')
                mu, lo, hi, m0, _ = cv.fit_mr(tr, te, 'MR0', 'biomass'); tau2 = m0.sigma2.sum()
                preds = {'BASELINE_mean': np.full(len(te), tr.target.mean()), 'MR0': mu,
                         ML_NAME: fit_ml(ML[0], ML[1], tr, te, tau2, 11 + f)[0]}
                for m, p in preds.items():
                    rows.append(dict(target=TARGET, fold=f, frac=frac, draw=draw, n_train_studies=tr.study_id.nunique(), model=m,
                                     RMSE=float(np.sqrt(np.mean((p - te.target) ** 2))), MAE=float(np.mean(np.abs(p - te.target)))))
        print(TARGET, 'learning fold', f, flush=True)
    R = pd.DataFrame(rows); R.to_csv(RES / f'c15_learning_raw_{TARGET}.csv', index=False)
    g = R.groupby(['target', 'frac', 'model']).agg(n_train_studies=('n_train_studies', 'mean'), RMSE=('RMSE', 'mean'),
                                                   RMSE_se=('RMSE', 'sem'), MAE=('MAE', 'mean')).reset_index()
    g.to_csv(RES / f'c15_learning_{TARGET}.csv', index=False); print(g.round(3).to_string())


def ad():
    import joblib
    F = joblib.load(OUT / 'freeze' / 'models_chl.joblib')[EP]; fz = F['models'][ML_NAME]['fz']
    f_te = 'test_chlorophyll_V8.parquet' if TARGET == 'chlorophyll' else 'test_chl_index_V8.parquet'
    te = prep(pd.read_parquet(OUT / 'data' / f_te))
    cols = list(dict.fromkeys(list(T.columns) + F['cat'] + F['num']))
    Xtr, _ = fz.transform(T.reindex(columns=cols), 'scaled'); Xte, _ = fz.transform(te.reindex(columns=cols), 'scaled')
    Xtr, Xte = np.asarray(Xtr, float), np.asarray(Xte, float)
    cl = T.dependency_cluster_id.values; dtr = np.zeros(len(T))
    for i in range(len(T)):
        dd = np.sqrt(((Xtr - Xtr[i]) ** 2).sum(1)); dd[cl == cl[i]] = np.inf; dtr[i] = np.sort(dd)[:5].mean()
    dte = np.array([np.sort(np.sqrt(((Xtr - Xte[i]) ** 2).sum(1)))[:5].mean() for i in range(len(te))])
    thr = np.quantile(dtr, 0.95)
    oof = pd.read_parquet(RES / f'c15_uncertainty_oof_{TARGET}.parquet')
    oof = oof[(oof.model == ML_NAME) & (oof.seed == 11)].set_index('contrast_id')
    t1 = pd.DataFrame(dict(target=TARGET, role='TRAIN_CV', contrast_id=T.contrast_id, stress=T.h_stress_class, dist=dtr / thr))
    t1 = t1.join(oof[['y', 'pred', 'lo', 'hi']], on='contrast_id')
    tp = pd.read_csv(RES / 'c12_test_predictions.csv'); tp = tp[(tp.endpoint == EP) & (tp.model == ML_NAME)].set_index('contrast_id')
    t2 = pd.DataFrame(dict(target=TARGET, role='TEST', contrast_id=te.contrast_id, stress=te.h_stress_class, dist=dte / thr))
    t2 = t2.join(tp[['y', 'pred', 'lo', 'hi']], on='contrast_id')
    A = pd.concat([t1, t2]); A['ood'] = (A.dist > 1).astype(int); A['abs_err'] = (A.pred - A.y).abs()
    A['covered'] = ((A.y >= A.lo) & (A.y <= A.hi)).astype(int); A['model'] = ML_NAME
    A.to_csv(RES / f'c15_ad_rows_{TARGET}.csv', index=False)
    S = A.groupby(['role', 'ood']).agg(n=('dist', 'size'), MAE=('abs_err', 'mean'), coverage=('covered', 'mean')).reset_index()
    S.insert(0, 'model', ML_NAME); S.insert(0, 'target', TARGET); S.to_csv(RES / f'c15_ad_summary_{TARGET}.csv', index=False)
    print(S.round(3).to_string(index=False))


def knn_mean(Xq, Xr, vals, k, excl_q=None, excl_r=None):
    out = np.empty(len(Xq))
    for i in range(len(Xq)):
        d = np.sqrt(((Xr - Xq[i]) ** 2).sum(1))
        if excl_q is not None:
            d[excl_r == excl_q[i]] = np.inf
        idx = np.argpartition(d, k)[:k]
        out[i] = d[idx].mean() if vals is None else np.mean(vals[idx])
    return out


R_GRID = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
SCORES = ['AD_DISTANCE', 'LOCAL_ERROR', 'DISAGREEMENT', 'RANDOM']


def rmse(e):
    return float(np.sqrt(np.mean(e ** 2))) if len(e) else np.nan


def selective():
    parts = []
    for seed in SEEDS:
        for f, tr, te in outer(seed):
            mu0, _, _, m0, _ = cv.fit_mr(tr, te, 'MR0', 'biomass'); tau2 = m0.sigma2.sum()
            pr, res_in, half, fz = fit_ml(ML[0], ML[1], tr, te, tau2, seed + f)
            Xtr = np.asarray(fz.transform(tr, 'scaled')[0], float); Xte = np.asarray(fz.transform(te, 'scaled')[0], float)
            cl_tr, mean_tr = tr.dependency_cluster_id.values, tr.target.mean()
            rng = np.random.default_rng(1000 * seed + f)
            sc_tr = {'AD_DISTANCE': knn_mean(Xtr, Xtr, None, 5, cl_tr, cl_tr), 'LOCAL_ERROR': knn_mean(Xtr, Xtr, np.abs(res_in), 15, cl_tr, cl_tr),
                     'DISAGREEMENT': np.abs((tr.target.values - res_in) - mean_tr), 'RANDOM': rng.uniform(size=len(tr))}
            sc_te = {'AD_DISTANCE': knn_mean(Xte, Xtr, None, 5), 'LOCAL_ERROR': knn_mean(Xte, Xtr, np.abs(res_in), 15),
                     'DISAGREEMENT': np.abs(pr - mean_tr), 'RANDOM': rng.uniform(size=len(te))}
            b = pd.DataFrame(dict(target=TARGET, seed=seed, fold=f, contrast_id=te.contrast_id, study_id=te.study_id, cluster=te.dependency_cluster_id,
                                  y=te.target.values, pred_ml=pr, pred_mean=mean_tr, pred_mr0=mu0, lo_ml=pr - half, hi_ml=pr + half))
            for s in SCORES:
                for r in R_GRID:
                    thr = np.inf if r >= 1 else np.quantile(sc_tr[s], r)
                    b[f'keep_{s}_{r}'] = (sc_te[s] <= thr).astype(int)
            parts.append(b); print(TARGET, 'selective seed', seed, 'fold', f, flush=True)
    P = pd.concat(parts, ignore_index=True); P.to_parquet(RES / f'c15_selective_oof_{TARGET}.parquet', index=False)
    nst = T.study_id.nunique(); out = []
    for seed, g in P.groupby('seed'):
        uc = g.cluster.unique(); idx = {c: np.where(g.cluster.values == c)[0] for c in uc}
        rng = np.random.default_rng(seed); boots = [np.concatenate([idx[c] for c in rng.choice(uc, len(uc), replace=True)]) for _ in range(2000)]
        y, pr, pm, p0, lo, hi = (g[c].values for c in ['y', 'pred_ml', 'pred_mean', 'pred_mr0', 'lo_ml', 'hi_ml'])
        for s in SCORES:
            for r in R_GRID:
                k = g[f'keep_{s}_{r}'].values.astype(bool)
                d = [rmse(pr[bb][k[bb]] - y[bb][k[bb]]) - rmse(pm[bb][k[bb]] - y[bb][k[bb]]) for bb in boots]
                out.append(dict(target=TARGET, seed=seed, score=s, target_retention=r, retained_frac=k.mean(), retained_contrasts=int(k.sum()),
                                retained_studies=g.study_id[k].nunique(), retained_studies_frac=g.study_id[k].nunique() / nst,
                                RMSE_ml=rmse(pr[k] - y[k]), RMSE_mean=rmse(pm[k] - y[k]), RMSE_MR0=rmse(p0[k] - y[k]),
                                d_ml_vs_mean=rmse(pr[k] - y[k]) - rmse(pm[k] - y[k]),
                                d_ml_vs_mean_ci_lo=float(np.nanquantile(d, .025)), d_ml_vs_mean_ci_hi=float(np.nanquantile(d, .975)),
                                coverage_ml=float(np.mean((y[k] >= lo[k]) & (y[k] <= hi[k]))), width_ml=float(np.mean(hi[k] - lo[k]))))
    S = pd.DataFrame(out); S.to_csv(RES / f'c15_selective_by_seed_{TARGET}.csv', index=False)
    A = S.groupby(['target', 'score', 'target_retention']).mean(numeric_only=True).drop(columns='seed').reset_index()
    A['model'] = ML_NAME; A.to_csv(RES / f'c15_selective_{TARGET}.csv', index=False)
    print(A[['score', 'target_retention', 'retained_frac', 'retained_studies', 'RMSE_ml', 'RMSE_mean', 'd_ml_vs_mean', 'd_ml_vs_mean_ci_lo',
             'd_ml_vs_mean_ci_hi', 'coverage_ml']].round(3).to_string(index=False))


if __name__ == '__main__':
    {'uncertainty': uncertainty, 'learning': learning, 'ad': ad, 'selective': selective}[ANALYSIS]()
