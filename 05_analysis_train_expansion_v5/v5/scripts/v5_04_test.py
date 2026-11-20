"""V5 step 4: one evaluation of the frozen pipeline on TEST (2024-2026). Label: POST_HOC_TEST_REUSE.
Nothing is tuned here: models, weights, encoders and intervals come from v5/freeze (SHA-256 checked).
Category B (conditional on the observed S_vs_C of each TEST study) is reported separately.
"""
import json, hashlib
import numpy as np
import pandas as pd
import joblib
from v5_common import cv, RES, V5, with_dj2, load_test
import v5_02_cv_select as S

FZ = V5 / 'freeze'; OUT = RES / 'test'; OUT.mkdir(exist_ok=True)
LABEL = 'POST_HOC_TEST_REUSE'


def check_freeze():
    lines = (FZ / 'MODEL_FREEZE_V5.sha256').read_text().split('\n')
    for ln in filter(None, lines):
        h, f = ln.split('  ')
        assert hashlib.sha256((FZ / f).read_bytes()).hexdigest() == h, f'freeze file changed: {f}'


def select_test(ep, T):
    x = (T[0] if ep == 'yield' else T[1]).copy()
    sel = x.is_boxplot == 0
    if ep == 'biomass':
        sel &= x.is_last_timepoint == 1
    x = x[sel].reset_index(drop=True)
    x['v'] = x.var_lnrr_imp; x['target'] = x.effect
    return x


def predict_all(F, te, ep):
    te = te.reindex(columns=list(dict.fromkeys(list(te.columns) + list(F['pool'].columns))))   # other-endpoint columns -> NaN (as in CV)
    out, n = {}, len(te)
    m0 = F['mr0']; mu, sd = m0.predict(np.ones((n, 1)), te.v.values); out['MR0'] = (mu, mu - 1.96 * sd, mu + 1.96 * sd)
    Xtr, Xte, names = cv.mr_design(with_dj2(F['pool']), with_dj2(te), ep, with_svc=True, multitask=True)
    assert list(names) == list(F['mr2_names'])
    mu, sd = F['mr2'].predict(Xte, te.v.values); out['MR2mt'] = (mu, mu - 1.96 * sd, mu + 1.96 * sd)
    for nm, d in F['ml'].items():
        X, cols = d['fz'].transform(te, d['kind'])
        assert cols == d['columns']
        p = d['model'].predict(X); out[nm] = (p, p - d['half'], p + d['half'])
    c, hw = F['baseline']; out['BASELINE_mean'] = (np.full(n, c), np.full(n, c - hw), np.full(n, c + hw))
    for nm, mem in S.EQUAL.items():
        p = np.mean([out[k][0] for k in mem], axis=0); h = np.mean([(out[k][2] - out[k][1]) / 2 for k in mem], axis=0)
        out[nm] = (p, p - h, p + h)
    for nm, (mem, w, half) in F['lstack'].items():
        p = np.column_stack([out[k][0] for k in mem]) @ np.array(w); out[nm] = (p, p - half, p + half)
    return out


def met(y, p, lo, hi):
    e = p - y; sst = ((y - y.mean()) ** 2).sum()
    return dict(RMSE=float(np.sqrt(np.mean(e ** 2))), MAE=float(np.mean(np.abs(e))), R2=float(1 - (e ** 2).sum() / sst),
                bias=float(e.mean()), coverage95=float(np.mean((y >= lo) & (y <= hi))), PI_width=float(np.mean(hi - lo)))


def boot(te, out, models, B=2000, seed=0):
    rng = np.random.default_rng(seed); cl = te.dependency_cluster_id.values; uc = np.unique(cl)
    idx = {c: np.where(cl == c)[0] for c in uc}
    y = te.target.values
    R = {m: [] for m in models}; D = {m: {'BASELINE_mean': [], 'MR0': []} for m in models}
    for _ in range(B):
        ii = np.concatenate([idx[c] for c in rng.choice(uc, len(uc), replace=True)])
        rm = {m: np.sqrt(np.mean((out[m][0][ii] - y[ii]) ** 2)) for m in models}
        for m in models:
            R[m].append(rm[m]); D[m]['BASELINE_mean'].append(rm[m] - rm['BASELINE_mean']); D[m]['MR0'].append(rm[m] - rm['MR0'])
    q = lambda v: (float(np.quantile(v, .025)), float(np.quantile(v, .975)))
    return {m: dict(RMSE_ci=q(R[m]), d_vs_mean=float(np.mean(D[m]['BASELINE_mean'])), d_vs_mean_ci=q(D[m]['BASELINE_mean']),
                    d_vs_MR0_ci=q(D[m]['MR0'])) for m in models}


def main():
    check_freeze()
    spec = json.load(open(FZ / 'MODEL_FREEZE_V5.json')); frozen = joblib.load(FZ / 'models_v5.joblib')
    cvS = pd.read_csv(RES / 'v5_cv_summary.csv')
    rows, preds, verdicts = [], [], []
    T = load_test()
    for ep in ('yield', 'biomass'):
        te = select_test(ep, T); out = predict_all(frozen[ep], te, ep)
        models = list(out)
        bs = boot(te, out, models)
        for m in models:
            r = dict(label=LABEL, endpoint=ep, model=m, category=S.CATEGORY[m], n_contrasts=len(te), n_studies=te.study_id.nunique(),
                     n_clusters=te.dependency_cluster_id.nunique(), **met(te.target.values, *out[m]))
            r.update(RMSE_ci_lo=bs[m]['RMSE_ci'][0], RMSE_ci_hi=bs[m]['RMSE_ci'][1], dRMSE_vs_mean=r['RMSE'] - met(te.target.values, *out['BASELINE_mean'])['RMSE'],
                     dRMSE_vs_mean_ci_lo=bs[m]['d_vs_mean_ci'][0], dRMSE_vs_mean_ci_hi=bs[m]['d_vs_mean_ci'][1],
                     dRMSE_vs_MR0_ci_lo=bs[m]['d_vs_MR0_ci'][0], dRMSE_vs_MR0_ci_hi=bs[m]['d_vs_MR0_ci'][1])
            c = cvS[(cvS.endpoint == ep) & (cvS.model == m)]
            r['RMSE_CV'] = float(c.RMSE.iloc[0]) if len(c) else np.nan; r['coverage_CV'] = float(c.coverage95.iloc[0]) if len(c) else np.nan
            r['selected'] = m in spec['endpoints'][ep]['selected'].values()
            rows.append(r)
            preds.append(pd.DataFrame(dict(label=LABEL, endpoint=ep, model=m, contrast_id=te.contrast_id, study_id=te.study_id,
                                           cluster=te.dependency_cluster_id, contrast_type=te.contrast_type, stress=te.h_stress_class,
                                           y=te.target, pred=out[m][0], lo=out[m][1], hi=out[m][2])))
        R = pd.DataFrame([r for r in rows if r['endpoint'] == ep]).set_index('model')
        a = spec['endpoints'][ep]['selected']['A']; b = spec['endpoints'][ep]['selected'].get('B')
        h1 = bool(R.loc[a, 'dRMSE_vs_mean_ci_hi'] < 0) if a != 'BASELINE_mean' else False
        h2 = bool(R.loc[a, 'RMSE'] <= 1.25 * R.loc[a, 'RMSE_CV'])
        h3 = bool(R.loc[a, 'coverage95'] >= 0.90)
        h4 = bool(R.loc[b, 'RMSE'] < R.loc[a, 'RMSE']) if b else None
        npass = h1 + h2 + h3
        verdicts.append(dict(label=LABEL, endpoint=ep, selected_A=a, selected_B=b, H1_point_better_than_mean=h1, H2_transfer=h2,
                             H3_coverage=h3, H4_conditional_B_better=h4,
                             verdict='CONFIRMED' if npass == 3 else ('PARTIAL' if npass else 'NOT_CONFIRMED'),
                             RMSE_A=R.loc[a, 'RMSE'], RMSE_A_CV=R.loc[a, 'RMSE_CV'], RMSE_mean=R.loc['BASELINE_mean', 'RMSE'],
                             RMSE_B=R.loc[b, 'RMSE'] if b else None, coverage_A=R.loc[a, 'coverage95']))
    pd.DataFrame(rows).to_csv(OUT / 'v5_test_metrics_POST_HOC_TEST_REUSE.csv', index=False)
    pd.concat(preds).to_csv(OUT / 'v5_test_predictions_POST_HOC_TEST_REUSE.csv', index=False)
    pd.DataFrame(verdicts).to_csv(OUT / 'v5_test_verdict_POST_HOC_TEST_REUSE.csv', index=False)
    pd.set_option('display.width', 250)
    print(pd.DataFrame(rows)[['endpoint', 'category', 'model', 'RMSE', 'RMSE_CV', 'MAE', 'R2', 'bias', 'coverage95', 'dRMSE_vs_mean', 'dRMSE_vs_mean_ci_lo', 'dRMSE_vs_mean_ci_hi', 'selected']].round(4).to_string())
    print(pd.DataFrame(verdicts).T.to_string())


if __name__ == '__main__':
    main()
