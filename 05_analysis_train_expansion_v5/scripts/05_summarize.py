"""Aggregate CV metrics over seeds; deltas of every variant vs DEFAULT (same model, same seeds, same folds)."""
import pathlib
import numpy as np
import pandas as pd

RES = pathlib.Path(__file__).resolve().parents[1] / 'results'
M = pd.read_csv(RES / 'cv_metrics_all_runs.csv')
KEYS = ['endpoint', 'variant', 'model', 'scheme', 'eval_set']
MET = ['RMSE', 'MAE', 'R2', 'wRMSE', 'coverage95', 'mean_PI_width']
agg = M.groupby(KEYS).agg(n_seeds=('seed', 'nunique'), n_eval=('n', 'first'), eval_studies=('n_studies', 'first'),
                          train_contrasts=('train_contrasts', 'first'), train_studies=('train_studies', 'first'),
                          **{f'{m}_mean': (m, 'mean') for m in MET}, **{f'{m}_sd': (m, 'std') for m in MET}).reset_index()
agg.to_csv(RES / 'cv_metrics_summary_all_variants.csv', index=False)

# paired deltas vs DEFAULT on the common reference rows (study-grouped folds, matching seeds)
ref = M[(M.variant == 'DEFAULT') & (M.scheme == 'study')]
rows = []
for (ep, var, model), g in M[(M.scheme == 'study') & (M.eval_set == 'DEFAULT_reference_rows')].groupby(['endpoint', 'variant', 'model']):
    if var == 'DEFAULT':
        continue
    r = ref[(ref.endpoint == ep) & (ref.model == model) & (ref.eval_set == 'DEFAULT_reference_rows')]
    if var == 'TARGET_effect_bc':
        continue                       # different target: not comparable on the same scale
    j = g.merge(r, on='seed', suffixes=('', '_def'))
    if j.empty:
        continue
    rows.append(dict(endpoint=ep, variant=var, model=model, seeds=len(j),
                     dRMSE=(j.RMSE - j.RMSE_def).mean(), dRMSE_pct=100 * ((j.RMSE - j.RMSE_def) / j.RMSE_def).mean(),
                     dMAE=(j.MAE - j.MAE_def).mean(), dR2=(j.R2 - j.R2_def).mean(), dwRMSE=(j.wRMSE - j.wRMSE_def).mean(),
                     dCoverage=(j.coverage95 - j.coverage95_def).mean(),
                     improves_RMSE_all_seeds=bool((j.RMSE < j.RMSE_def).all())))
D = pd.DataFrame(rows)
D.to_csv(RES / 'cv_ablation_deltas_vs_default.csv', index=False)

# compact pivot for the report: DEFAULT, study vs cluster schemes
piv = agg[(agg.variant.isin(['DEFAULT', 'TARGET_effect_bc'])) & (agg.eval_set == 'OWN_rows')]
piv.to_csv(RES / 'cv_default_models_study_vs_cluster.csv', index=False)
print(piv[['endpoint', 'variant', 'scheme', 'model', 'n_eval', 'RMSE_mean', 'RMSE_sd', 'MAE_mean', 'R2_mean', 'wRMSE_mean', 'coverage95_mean']].round(3).to_string())
print(D.round(4).sort_values(['endpoint', 'model', 'dRMSE']).to_string())
