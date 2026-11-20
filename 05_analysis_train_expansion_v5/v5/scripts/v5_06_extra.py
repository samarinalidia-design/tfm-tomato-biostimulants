"""V5 extra analyses for the figures.
  gradient  : stress-damage gradient ln(SB/S) vs D = ln(S/C) (study means, study bootstrap), recovered share,
              expected (Maas-Hoffman, tomato a = 2.5 dS/m, b = 9.9 %/dS/m) vs realised salinity damage   [TRAIN + TEST, descriptive]
  learning  : grouped learning curves (TRAIN, outer folds by dependency cluster, 20-100 % of training clusters, 3 draws)
  ad        : applicability domain (distance to 5 nearest TRAIN contrasts of other clusters) + error in/out of domain  [after freeze]
  importance: grouped permutation importance of RIDGE_REF / RF_V3TETF in the outer cluster CV (seed 11)
Usage: python v5_06_extra.py gradient learning | ad importance
"""
import sys, json
import numpy as np
import pandas as pd
from scipy import stats
from v5_common import cv, r5, Y, B, fsets, SCHEME, RES, V5, load_test, V5Featurizer
import v5_02_cv_select as S

OUT = RES / 'extra'; OUT.mkdir(exist_ok=True)
V3F = r5.V3Featurizer


def gradient():
    rows, sm_all = [], []
    ty, tb = load_test()
    for ep, tr, te in [('yield', Y, ty), ('biomass', B, tb)]:
        for role, x in [('TRAIN', tr), ('TEST', te)]:
            x = x[(x.in_default == 1) & (x.contrast_type == 'SB_vs_S') & x.mod_lnrr_stress_SvsC.notna()].copy()
            x['D'] = x.mod_lnrr_stress_SvsC; x['R'] = x.effect; x['vS'] = x.cv_used_c ** 2 / x.n_imp_c
            sm = x.groupby('study_id').agg(D=('D', 'mean'), R=('R', 'mean'), vS=('vS', 'mean'), stress=('h_stress_class', 'first'), k=('R', 'size')).reset_index()
            sm['endpoint'], sm['role'] = ep, role; sm_all.append(sm)
            if len(sm) < 4:
                continue
            sl = stats.linregress(sm.D, sm.R)
            rng = np.random.default_rng(0); bs = []
            for _ in range(2000):
                i = rng.integers(0, len(sm), len(sm)); s = sm.iloc[i]
                if s.D.nunique() > 2:
                    bs.append(stats.linregress(s.D, s.R).slope)
            artefact = -sm.vS.mean() / sm.D.var()
            dam = sm[sm.D < -0.05]
            rl = (dam.R / (-dam.D))
            rows.append(dict(endpoint=ep, role=role, studies=len(sm), contrasts=int(sm.k.sum()), slope=sl.slope, slope_ci_lo=np.quantile(bs, .025),
                             slope_ci_hi=np.quantile(bs, .975), intercept=sl.intercept, R2=sl.rvalue ** 2, p=sl.pvalue,
                             null_artefact_slope_approx=artefact, studies_damaged=len(dam), recovered_share_median=float(rl.median()) if len(rl) else np.nan,
                             recovered_share_iqr=f'{rl.quantile(.25):.2f}-{rl.quantile(.75):.2f}' if len(rl) else ''))
    pd.DataFrame(rows).to_csv(OUT / 'stress_gradient.csv', index=False)
    pd.concat(sm_all).to_csv(OUT / 'stress_gradient_study_means.csv', index=False)
    # expected vs realised salinity damage (yield, S vs C arms)
    sal = []
    for role, x in [('TRAIN', Y), ('TEST', ty)]:
        z = x[(x.in_default == 1) & (x.contrast_type == 'SB_vs_S') & (x.h_stress_class == 'SALINITY') & x.mod_lnrr_stress_SvsC.notna()].copy()
        ec = pd.to_numeric(z.h2_salinity_ecw_dsm, errors='coerce').replace(0, np.nan).fillna(pd.to_numeric(z.h2_salinity_nacl_mm, errors='coerce') / 10.0)
        z['EC_equiv'] = ec; z['expected_loss'] = np.clip(0.099 * (ec - 2.5), 0, 1); z['realised_loss'] = 1 - np.exp(z.mod_lnrr_stress_SvsC)
        g = z.dropna(subset=['EC_equiv']).groupby('study_id').agg(EC_equiv=('EC_equiv', 'mean'), expected_loss=('expected_loss', 'mean'),
                                                                   realised_loss=('realised_loss', 'mean')).reset_index()
        g['role'] = role; sal.append(g)
    sal = pd.concat(sal); sal.to_csv(OUT / 'salinity_expected_vs_realised.csv', index=False)
    print(pd.DataFrame(rows).round(3).to_string())


def learning():
    rows = []
    for ep in ('yield', 'biomass'):
        df, pool = S.pools(ep, cv.Y, cv.B)
        folds = cv.make_folds(SCHEME, 11)
        cat, num, _, _ = fsets(ep)['REF']
        for f in range(cv.N_OUTER):
            tr0 = df[df.study_id.map(folds) != f]; te = df[df.study_id.map(folds) == f].reset_index(drop=True)
            cl = np.array(sorted(tr0.dependency_cluster_id.unique()))
            for frac in (0.2, 0.4, 0.6, 0.8, 1.0):
                for draw in range(3 if frac < 1 else 1):
                    rng = np.random.default_rng(100 * f + draw)
                    keep = rng.choice(cl, max(5, int(round(frac * len(cl)))), replace=False)
                    tr = tr0[tr0.dependency_cluster_id.isin(keep)].reset_index(drop=True)
                    mu, lo, hi, m0, _ = cv.fit_mr(tr, te, 'MR0', ep); tau2 = m0.sigma2.sum()
                    preds = {'BASELINE_mean': np.full(len(te), tr.target.mean()), 'MR0': mu}
                    V3F.TE, V3F.TFIDF = [], False
                    preds['RIDGE_REF'] = cv.fit_predict_ml('RIDGE', tr, te, cat, num, 'ivw_re', tau2, SCHEME, 11 + f)[0]
                    for m, p in preds.items():
                        rows.append(dict(endpoint=ep, fold=f, frac=frac, draw=draw, n_train_studies=tr.study_id.nunique(), model=m,
                                         RMSE=float(np.sqrt(np.mean((p - te.target) ** 2))), MAE=float(np.mean(np.abs(p - te.target)))))
            print(ep, 'fold', f, flush=True)
    R = pd.DataFrame(rows); R.to_csv(OUT / 'learning_curves_raw.csv', index=False)
    g = R.groupby(['endpoint', 'frac', 'model']).agg(n_train_studies=('n_train_studies', 'mean'), RMSE=('RMSE', 'mean'), RMSE_se=('RMSE', 'sem'),
                                                     MAE=('MAE', 'mean')).reset_index()
    g.to_csv(OUT / 'learning_curves_summary.csv', index=False); print(g.round(3).to_string())


def _featurized(ep):
    import joblib
    F = joblib.load(V5 / 'freeze/models_v5.joblib')[ep]
    d = F['ml']['RIDGE_REF']; fz = d['fz']
    ty, tb = load_test()
    te = (ty if ep == 'yield' else tb)
    te = te[(te.is_boxplot == 0) & ((te.is_last_timepoint == 1) if ep == 'biomass' else True)].reset_index(drop=True)
    tr = F['train']
    Xtr, _ = fz.transform(tr, 'scaled'); Xte, _ = fz.transform(te, 'scaled')
    return tr, te, Xtr, Xte


def ad():
    out, summ = [], []
    spec = json.load(open(V5 / 'freeze/MODEL_FREEZE_V5.json'))
    tp = pd.read_csv(RES / 'test/v5_test_predictions_POST_HOC_TEST_REUSE.csv')
    for ep in ('yield', 'biomass'):
        tr, te, Xtr, Xte = _featurized(ep)
        cl = tr.dependency_cluster_id.values
        dtr = np.zeros(len(tr))
        for i in range(len(tr)):
            dd = np.sqrt(((Xtr - Xtr[i]) ** 2).sum(1)); dd[cl == cl[i]] = np.inf
            dtr[i] = np.sort(dd)[:5].mean()
        dte = np.array([np.sort(np.sqrt(((Xtr - Xte[i]) ** 2).sum(1)))[:5].mean() for i in range(len(te))])
        thr = np.quantile(dtr, 0.95)
        a = spec['endpoints'][ep]['selected']['A']
        oof = pd.read_parquet(RES / f'v5_cv_oof_{ep}_11.parquet'); oof = oof[oof.model == a].set_index('contrast_id')
        t1 = pd.DataFrame(dict(endpoint=ep, role='TRAIN_CV', contrast_id=tr.contrast_id, stress=tr.h_stress_class, dist=dtr / thr))
        t1 = t1.join(oof[['y', 'pred', 'lo', 'hi']], on='contrast_id')
        t2 = pd.DataFrame(dict(endpoint=ep, role='TEST', contrast_id=te.contrast_id, stress=te.h_stress_class, dist=dte / thr))
        p2 = tp[(tp.endpoint == ep) & (tp.model == a)].set_index('contrast_id')[['y', 'pred', 'lo', 'hi']]
        t2 = t2.join(p2, on='contrast_id')
        T = pd.concat([t1, t2]); T['ood'] = (T.dist > 1).astype(int); T['abs_err'] = (T.pred - T.y).abs()
        T['covered'] = ((T.y >= T.lo) & (T.y <= T.hi)).astype(int); T['model'] = a
        out.append(T)
        for (role, ood), g in T.groupby(['role', 'ood']):
            summ.append(dict(endpoint=ep, model=a, role=role, ood=ood, n=len(g), MAE=g.abs_err.mean(), coverage=g.covered.mean()))
    pd.concat(out).to_csv(OUT / 'applicability_domain_rows.csv', index=False)
    pd.DataFrame(summ).to_csv(OUT / 'applicability_domain_summary.csv', index=False)
    print(pd.DataFrame(summ).round(3).to_string())


def importance():
    from v5_03_freeze_fit import fit_ml_final
    rows = []
    for ep in ('yield', 'biomass'):
        df, pool = S.pools(ep, cv.Y, cv.B)
        folds = cv.make_folds(SCHEME, 11)
        for nm, key, fs in [('RIDGE_REF', 'RIDGE', 'REF')]:   # RF omitted: ~2 h of compute for a secondary panel
            cat, num, tek, tf = fsets(ep)[fs]
            raw = list(dict.fromkeys(cat + num)) + (list(tek) if tek else []) + (['h3_text_all'] if tf else [])
            for f in range(cv.N_OUTER):
                tr = df[df.study_id.map(folds) != f].reset_index(drop=True); te = df[df.study_id.map(folds) == f].reset_index(drop=True)
                tau2 = cv.fit_mr(tr, te, 'MR0', ep)[3].sigma2.sum()
                d = fit_ml_final(key, tr, cat, num, tau2, 11 + f, tek, tf)
                pred = lambda z: d['model'].predict(d['fz'].transform(z, d['kind'])[0])
                base = np.sqrt(np.mean((pred(te) - te.target) ** 2))
                rng = np.random.default_rng(f)
                for c in raw:
                    inc = []
                    for rep in range(3):
                        z = te.copy(); z[c] = z[c].values[rng.permutation(len(z))]
                        inc.append(np.sqrt(np.mean((pred(z) - te.target) ** 2)) - base)
                    rows.append(dict(endpoint=ep, model=nm, fold=f, feature=c, dRMSE=float(np.mean(inc))))
                print(ep, nm, f, flush=True)
    R = pd.DataFrame(rows)
    g = R.groupby(['endpoint', 'model', 'feature']).dRMSE.agg(['mean', 'std']).reset_index().sort_values(['endpoint', 'model', 'mean'], ascending=[True, True, False])
    g.to_csv(OUT / 'permutation_importance.csv', index=False); print(g.groupby(['endpoint', 'model']).head(8).round(4).to_string())


if __name__ == '__main__':
    for part in sys.argv[1:]:
        globals()[part]()
