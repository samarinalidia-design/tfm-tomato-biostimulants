"""Full-data (non-predictive) diagnostics, reported for every variant:
- 3-level REML intercept model: pooled lnRR, tau^2 per level, I^2 (total and per level), Q;
- meta-regression MR1 / MR2 coefficients with cluster-robust (CR1) SE;
- influence for the DEFAULT tables: leave-one-study-out (LOSO) and study-level Cook's distance.
Nothing is deleted: influence is reported only.
"""
import sys, json, importlib.util, pathlib
import numpy as np
import pandas as pd
from metalib import ThreeLevelMeta

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('cv', HERE / '02_cv_models.py')
cv = importlib.util.module_from_spec(spec); sys.argv = ['x']; spec.loader.exec_module(cv)
RES = cv.RES

het, coefs = [], []
for ep in ('yield', 'biomass'):
    for vname, vopt in cv.VARIANTS[ep]:
        v = {**cv.BASE, **vopt}
        if v['multitask'] or vname.startswith('WEIGHTS') or vname.startswith('FEATURES'):
            continue          # identical meta-analytic data to DEFAULT
        d = cv.select(ep, v).reset_index(drop=True)
        m0 = ThreeLevelMeta().fit(d.target, d.v, np.ones((len(d), 1)), d.study_id, d.exp_uid)
        h = m0.heterogeneity()
        se = np.sqrt(m0.vcov_robust[0, 0])
        het.append(dict(endpoint=ep, variant=vname, model='MR0_intercept', pooled_lnRR=m0.b[0], se_robust=se,
                        pct_change=100 * (np.exp(m0.b[0]) - 1), contrasts=len(d), studies=d.study_id.nunique(), **h))
        for lvl in ('MR1', 'MR2'):
            Xtr, _, names = cv.mr_design(d, d.iloc[:1], ep, with_svc=(lvl == 'MR2'))
            m = ThreeLevelMeta().fit(d.target, d.v, Xtr, d.study_id, d.exp_uid)
            hh = m.heterogeneity()
            het.append(dict(endpoint=ep, variant=vname, model=lvl + '_residual', contrasts=len(d), studies=d.study_id.nunique(),
                            R2_tau2_vs_MR0=1 - hh['tau2_total'] / h['tau2_total'], **hh))
            for r in m.coef_table(names):
                coefs.append(dict(endpoint=ep, variant=vname, model=lvl, **r))
pd.DataFrame(het).to_csv(RES / 'heterogeneity_all_variants.csv', index=False)
pd.DataFrame(coefs).to_csv(RES / 'meta_regression_coefficients_RVE.csv', index=False)

# ---------------------------------------------------------------- influence (DEFAULT tables)
inf = []
for ep in ('yield', 'biomass'):
    d = cv.select(ep, cv.BASE).reset_index(drop=True)
    for lvl in ('MR0', 'MR1'):
        if lvl == 'MR0':
            X, names = np.ones((len(d), 1)), ['intercept']
        else:
            X, _, names = cv.mr_design(d, d.iloc[:1], ep, with_svc=False)
        full = ThreeLevelMeta().fit(d.target, d.v, X, d.study_id, d.exp_uid)
        Vinv = np.linalg.pinv(full.vcov_model)
        for s in d.study_id.unique():
            keep = (d.study_id != s).values
            Xk = X[keep]
            ok = Xk.std(axis=0) > 0; ok[0] = True          # drop moderator columns that become constant
            m = ThreeLevelMeta().fit(d.target[keep], d.v[keep], Xk[:, ok], d.study_id[keep], d.exp_uid[keep], init=full.sigma2)
            bfull = full.b[ok]; diff = bfull - m.b
            cook = float(diff @ np.linalg.pinv(full.vcov_model[np.ix_(ok, ok)]) @ diff)
            inf.append(dict(endpoint=ep, model=lvl, study_id=s, n_contrasts=int((~keep).sum()),
                            intercept_full=full.b[0], intercept_loso=m.b[0], delta_intercept=m.b[0] - full.b[0],
                            tau2_total_full=full.sigma2.sum(), tau2_total_loso=m.sigma2.sum(),
                            cooks_distance=cook, p=int(ok.sum())))
I = pd.DataFrame(inf)
I['cook_flag_4_over_k'] = I.cooks_distance > 4 / I.groupby(['endpoint', 'model']).study_id.transform('nunique')
I.to_csv(RES / 'influence_loso_cooks.csv', index=False)
summ = I.groupby(['endpoint', 'model']).agg(studies=('study_id', 'size'), intercept_full=('intercept_full', 'first'),
                                             loso_min=('intercept_loso', 'min'), loso_max=('intercept_loso', 'max'),
                                             max_cook=('cooks_distance', 'max'), n_cook_flag=('cook_flag_4_over_k', 'sum'))
summ.to_csv(RES / 'influence_summary.csv')
print(pd.DataFrame(het)[['endpoint', 'variant', 'model', 'contrasts', 'studies', 'pooled_lnRR', 'tau2_total', 'I2_total']].round(4).to_string())
print(summ.round(4).to_string())
