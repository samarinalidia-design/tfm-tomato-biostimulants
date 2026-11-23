"""One-time TEST evaluation of the frozen chlorophyll models (same metrics, bootstrap and criteria as V5 v5_04_test.py).

Checks the freeze hashes, predicts the default TEST rows (test_chl_index_V8 / test_chlorophyll_V8: SB_vs_S and B_vs_C) with
every frozen configuration, and scores them against the TRAIN mean (frozen value). Intervals: ML = prediction +/- the frozen
inner-OOF 95 % half-width; MR0 = mu +/- 1.96 sqrt(tau2 + v); TRAIN mean = mean +/- the 95 % quantile of |TRAIN residual|.
Cluster bootstrap (TEST dependency clusters, 2000) of the RMSE and of the RMSE difference to the TRAIN mean and MR0.
Criteria (V5, Table 16): H1 primary model better than the mean (CI of dRMSE < 0); H2 transfer, RMSE_TEST <= 1.25 RMSE_CV;
H3 coverage of the 95 % interval >= 0.90. RMSE_CV = c09 (A399 clusters).
Outputs: results/c12_test_metrics.csv, results/c12_test_predictions.csv, results/c12_test_verdict.csv
"""
import sys, json, hashlib, pathlib
import numpy as np
import pandas as pd
import joblib

OUT = pathlib.Path(__file__).resolve().parents[1]
REPO = OUT.parent
sys.path.insert(0, str(REPO / '05_analysis_train_expansion_v5' / 'v5' / 'scripts'))
_argv = sys.argv; sys.argv = sys.argv[:1]
import v5_common as V
sys.argv = _argv
FZ = OUT / 'freeze'
TAGS = {'CHL_INDEX': ('chl_index', 'test_chl_index_V8.parquet', 'train_chl_index_V8.parquet'),
        'CHL_CONTENT': ('chlorophyll', 'test_chlorophyll_V8.parquet', 'train_chlorophyll_V8.parquet')}


def check_freeze():
    for line in (FZ / 'MODEL_FREEZE_CHL.sha256').read_text().split('\n'):
        if line.strip():
            h, f = line.split()
            assert hashlib.sha256((FZ / f).read_bytes()).hexdigest() == h, f'freeze file changed: {f}'


def prep(T):
    T = T[T.in_default == 1].copy()
    T['study_id'] = T.study_id.astype(str); T['target'] = T.effect.astype(float); T['v'] = T.var_lnrr_imp.astype(float)
    T['exp_uid'] = T.study_id + '|' + T.experiment_key.astype(str); T['endpoint_is_yield'] = 0
    return T[T.target.notna() & T.v.notna() & (T.v > 0)].reset_index(drop=True)


def met(y, p, lo, hi):
    e = p - y; sst = ((y - y.mean()) ** 2).sum()
    return dict(RMSE=float(np.sqrt(np.mean(e ** 2))), MAE=float(np.mean(np.abs(e))), R2=float(1 - (e ** 2).sum() / sst),
                bias=float(e.mean()), coverage95=float(np.mean((y >= lo) & (y <= hi))), PI_width=float(np.mean(hi - lo)))


def boot(te, out, B=2000, seed=0):
    rng = np.random.default_rng(seed); cl = te.dependency_cluster_id.values; uc = np.unique(cl)
    idx = {c: np.where(cl == c)[0] for c in uc}; y = te.target.values
    R = {m: [] for m in out}; D = {m: [] for m in out}; D0 = {m: [] for m in out}
    for _ in range(B):
        ii = np.concatenate([idx[c] for c in rng.choice(uc, len(uc), replace=True)])
        rm = {m: np.sqrt(np.mean((out[m][0][ii] - y[ii]) ** 2)) for m in out}
        for m in out:
            R[m].append(rm[m]); D[m].append(rm[m] / rm['BASELINE_mean'] - 1); D0[m].append(rm[m] - rm['MR0'])
    q = lambda v: (float(np.quantile(v, .025)), float(np.quantile(v, .975)))
    return {m: dict(RMSE_ci=q(R[m]), d_pct_ci=tuple(100 * x for x in q(D[m])), d_MR0_ci=q(D0[m])) for m in out}


def main():
    check_freeze()
    spec = json.loads((FZ / 'MODEL_FREEZE_CHL.json').read_text(encoding='utf-8')); frozen = joblib.load(FZ / 'models_chl.joblib')
    rows, preds, verdicts = [], [], []
    for ep, (tag, ftest, ftrain) in TAGS.items():
        te = prep(pd.read_parquet(OUT / 'data' / ftest)); tr = prep(pd.read_parquet(OUT / 'data' / ftrain))
        F = frozen[ep]; M = F['models']; out = {}
        mu = M['MR0']['value']; s = np.sqrt(M['MR0']['tau2'] + te.v.values)
        out['MR0'] = (np.full(len(te), mu), mu - 1.96 * s, mu + 1.96 * s)
        c = M['BASELINE_mean']['value']; hw = float(np.quantile(np.abs(tr.target - c), 0.95))
        out['BASELINE_mean'] = (np.full(len(te), c), np.full(len(te), c - hw), np.full(len(te), c + hw))
        te_x = te.reindex(columns=list(dict.fromkeys(list(te.columns) + F['cat'] + F['num'])))
        for nm, d in M.items():
            if 'model' not in d:
                continue
            X, cols = d['fz'].transform(te_x, d['kind']); assert list(cols) == list(d['columns'])
            p = d['model'].predict(X); out[nm] = (p, p - d['half'], p + d['half'])
        bs = boot(te, out)
        cvS = pd.read_csv(OUT / 'results' / f'c09_cv_summary_{tag}.csv').set_index('model')
        base = met(te.target.values, *out['BASELINE_mean'])['RMSE']
        for m in out:
            r = dict(endpoint=ep, model=m, n_contrasts=len(te), n_studies=te.study_id.nunique(), n_clusters=te.dependency_cluster_id.nunique(),
                     **met(te.target.values, *out[m]))
            r.update(RMSE_ci_lo=bs[m]['RMSE_ci'][0], RMSE_ci_hi=bs[m]['RMSE_ci'][1], d_vs_mean_pct=100 * (r['RMSE'] / base - 1),
                     d_vs_mean_ci_lo_pct=bs[m]['d_pct_ci'][0], d_vs_mean_ci_hi_pct=bs[m]['d_pct_ci'][1],
                     RMSE_CV=float(cvS.RMSE.get(m, np.nan)), primary=m == spec['targets'][ep]['primary'],
                     ml_candidate=m == spec['targets'][ep]['ml_candidate'])
            rows.append(r)
            preds.append(pd.DataFrame(dict(endpoint=ep, model=m, contrast_id=te.contrast_id, study_id=te.study_id, cluster=te.dependency_cluster_id,
                                           contrast_type=te.contrast_type, stress=te.h_stress_class, biostimulant=te.h2_dujardin,
                                           y=te.target, pred=out[m][0], lo=out[m][1], hi=out[m][2])))
        R = pd.DataFrame([r for r in rows if r['endpoint'] == ep]).set_index('model')
        for role in ('primary', 'ml_candidate'):
            a = spec['targets'][ep][role]
            h1 = bool(R.loc[a, 'd_vs_mean_ci_hi_pct'] < 0) if a not in ('BASELINE_mean', 'MR0') else False
            h2 = bool(R.loc[a, 'RMSE'] <= 1.25 * R.loc[a, 'RMSE_CV'])
            h3 = bool(R.loc[a, 'coverage95'] >= 0.90)
            npass = h1 + h2 + h3
            verdicts.append(dict(endpoint=ep, role=role, model=a, H1_better_than_mean=h1, H2_transfer=h2, H3_coverage=h3,
                                 verdict='CONFIRMED' if npass == 3 else ('PARTIAL' if npass else 'NOT_CONFIRMED'),
                                 RMSE=R.loc[a, 'RMSE'], RMSE_CV=R.loc[a, 'RMSE_CV'], RMSE_mean=R.loc['BASELINE_mean', 'RMSE'],
                                 d_vs_mean_pct=R.loc[a, 'd_vs_mean_pct'], ci=(R.loc[a, 'd_vs_mean_ci_lo_pct'], R.loc[a, 'd_vs_mean_ci_hi_pct']),
                                 coverage=R.loc[a, 'coverage95']))
    pd.DataFrame(rows).to_csv(OUT / 'results' / 'c12_test_metrics.csv', index=False)
    pd.concat(preds).to_csv(OUT / 'results' / 'c12_test_predictions.csv', index=False)
    pd.DataFrame(verdicts).to_csv(OUT / 'results' / 'c12_test_verdict.csv', index=False)
    pd.set_option('display.width', 250)
    print(pd.DataFrame(rows)[['endpoint', 'model', 'n_studies', 'RMSE', 'RMSE_CV', 'R2', 'coverage95', 'd_vs_mean_pct', 'd_vs_mean_ci_lo_pct',
                              'd_vs_mean_ci_hi_pct', 'primary']].round(3).to_string(index=False))
    print(pd.DataFrame(verdicts).to_string(index=False))


if __name__ == '__main__':
    main()
