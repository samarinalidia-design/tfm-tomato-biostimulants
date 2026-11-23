"""Inputs for the V5 meta-analysis script (v5_05_meta.R, unchanged statistics) for the chlorophyll targets.
Writes v8_meta/data/{train,test}_{chl_index,chlorophyll}.csv with the columns the R script expects:
contrast_id, study_id, effect, var_lnrr_imp, in_default, contrast_type, shared_control_id (= study|experiment|control arm),
cv_used_c / n_imp_c chosen so that the shared-control covariance term cv^2/n equals half of var_lnRR (the control share of the
lnRR variance when treated and control arms have similar CV; the chlorophyll tables keep only the total var_lnRR),
variance_from_author_sd, dataset_role_v5, is_boxplot, h_* / h2_* / h3_* moderators.
"""
import pathlib
import numpy as np
import pandas as pd
OUT = pathlib.Path(__file__).resolve().parents[1]
for role in ('train', 'test'):
    for name in ('chl_index', 'chlorophyll'):
        f = OUT / 'data' / f'{role}_{name}_V8.parquet'
        if not f.exists():
            print('missing', f); continue
        x = pd.read_parquet(f)
        x['shared_control_id'] = x.study_id.astype(str) + '|' + x.experiment_key.astype(str) + '|' + x.arm_key_c.astype(str)
        x['n_imp_c'] = 1.0; x['cv_used_c'] = np.sqrt(x.var_lnrr_imp / 2)
        x['variance_from_author_sd'] = x.variance_status.fillna('').str.fullmatch(r'REPORTED\|REPORTED').astype(int)
        x['dataset_role_v5'] = role.upper(); x['is_boxplot'] = 0
        x['yield_tier'] = ''
        keep = [c for c in x.columns if not c.startswith(('context_', 'f_')) and c != 'h3_text_all']
        x[keep].to_csv(OUT / 'v8_meta' / 'data' / f'{role}_{name}.csv', index=False)
        print(role, name, len(x), int(x.in_default.sum()))
