"""Summaries of improvement round 2 (models) and round 3 (features v2 / unusual studies).
Paired by seed on the same study-grouped folds (make_folds('study', seed) is shared by all scripts)."""
import pathlib
import pandas as pd

RES = pathlib.Path(__file__).resolve().parents[1] / 'results'
MET = ['RMSE', 'MAE', 'R2', 'wRMSE', 'coverage95']
main = pd.read_csv(RES / 'cv_metrics_all_runs.csv')
base = main[(main.variant == 'DEFAULT') & (main.scheme == 'study') & (main.eval_set == 'OWN_rows')]

out = []
f2 = RES / 'cv_metrics_round2.csv'
if f2.exists():
    R2 = pd.read_csv(f2)
    agg = R2.groupby(['endpoint', 'model']).agg(n_seeds=('seed', 'nunique'), **{f'{m}_mean': (m, 'mean') for m in MET},
                                                **{f'{m}_sd': (m, 'std') for m in MET}).reset_index()
    agg.to_csv(RES / 'cv_metrics_round2_summary.csv', index=False)
    rows = []
    for ref_model in ['BASELINE_mean', 'MR0_3level_intercept', 'RF_weighted(MetaForest-style)']:
        b = base[base.model == ref_model][['endpoint', 'seed'] + MET]
        j = R2.merge(b, on=['endpoint', 'seed'], suffixes=('', '_ref'))
        for (ep, m), g in j.groupby(['endpoint', 'model']):
            rows.append(dict(endpoint=ep, model=m, reference=ref_model, seeds=len(g),
                             dRMSE=(g.RMSE - g.RMSE_ref).mean(), dRMSE_pct=100 * ((g.RMSE - g.RMSE_ref) / g.RMSE_ref).mean(),
                             dR2=(g.R2 - g.R2_ref).mean(), dwRMSE=(g.wRMSE - g.wRMSE_ref).mean(),
                             better_all_seeds=bool((g.RMSE < g.RMSE_ref).all())))
    pd.DataFrame(rows).to_csv(RES / 'cv_round2_deltas.csv', index=False)
    print(agg.round(4).to_string())

f3 = RES / 'cv_metrics_round3_features_influence.csv'
if f3.exists():
    R3 = pd.read_csv(f3)
    mcols = [m for m in MET + ['value'] if m in R3.columns]
    agg = R3.groupby(['endpoint', 'part', 'variant', 'model', 'eval_set']).agg(
        n_seeds=('seed', 'nunique'), **{f'{m}_mean': (m, 'mean') for m in mcols}, **{f'{m}_sd': (m, 'std') for m in mcols}).reset_index()
    agg.to_csv(RES / 'cv_metrics_round3_summary.csv', index=False)
    rows = []
    for part, refv in [('A_features', 'V1_DEFAULT'), ('B_influence', 'AS_IS')]:
        P = R3[R3.part == part]
        r = P[P.variant == refv]
        j = P[P.variant != refv].merge(r[['endpoint', 'model', 'seed', 'eval_set'] + mcols], on=['endpoint', 'model', 'seed', 'eval_set'],
                                       suffixes=('', '_ref'))
        for (ep, v, m, es), g in j.groupby(['endpoint', 'variant', 'model', 'eval_set']):
            d = dict(endpoint=ep, part=part, variant=v, reference=refv, model=m, eval_set=es, seeds=len(g))
            for k in mcols:
                d[f'd{k}'] = (g[k] - g[f'{k}_ref']).mean()
            if 'RMSE' in mcols:
                d['dRMSE_pct'] = 100 * ((g.RMSE - g.RMSE_ref) / g.RMSE_ref).mean()
                d['better_all_seeds'] = bool((g.RMSE < g.RMSE_ref).all())
            rows.append(d)
    pd.DataFrame(rows).to_csv(RES / 'cv_round3_deltas.csv', index=False)
    print(agg.round(4).to_string())
