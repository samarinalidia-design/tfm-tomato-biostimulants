"""Exploratory (after the one-time TEST evaluation): grouped permutation importance of the frozen ML candidates on TEST and on
TRAIN (in-sample of the frozen fit is not used; TRAIN importance = c15 seed-11 OOF is not available per feature, so TEST only).
Permutes each raw input column of the frozen featuriser across TEST rows (20 repeats) and records the RMSE increase.
Output: results/c16_test_permutation_importance.csv"""
import sys, pathlib
import numpy as np, pandas as pd, joblib
OUT = pathlib.Path(__file__).resolve().parents[1]; REPO = OUT.parent
sys.path.insert(0, str(REPO / '05_analysis_train_expansion_v5' / 'v5' / 'scripts'))
_a = sys.argv; sys.argv = sys.argv[:1]
import v5_common as V
sys.argv = _a
FZ = joblib.load(OUT / 'freeze' / 'models_chl.joblib')
rows = []
for ep, f, m in [('CHL_CONTENT', 'test_chlorophyll_V8.parquet', 'RF_REF_wn'), ('CHL_INDEX', 'test_chl_index_V8.parquet', 'RF_REF_wivw_re')]:
    T = pd.read_parquet(OUT / 'data' / f); T = T[T.in_default == 1].copy(); T['target'] = T.effect.astype(float)
    T['study_id'] = T.study_id.astype(str); T['endpoint_is_yield'] = 0
    T = T[T.target.notna() & T.var_lnrr_imp.notna() & (T.var_lnrr_imp > 0)].reset_index(drop=True)
    F = FZ[ep]; d = F['models'][m]; cols = list(dict.fromkeys(list(T.columns) + F['cat'] + F['num'])); T = T.reindex(columns=cols)
    pred = lambda X: d['model'].predict(d['fz'].transform(X, d['kind'])[0])
    base = np.sqrt(np.mean((pred(T) - T.target) ** 2)); rng = np.random.default_rng(0)
    for c in F['cat'] + F['num']:
        inc = []
        for _ in range(20):
            X = T.copy(); X[c] = rng.permutation(X[c].values); inc.append(np.sqrt(np.mean((pred(X) - T.target) ** 2)) - base)
        rows.append(dict(endpoint=ep, model=m, feature=c, d_rmse=np.mean(inc), sd=np.std(inc), n_nonmissing=int(T[c].notna().sum())))
R = pd.DataFrame(rows).sort_values(['endpoint', 'd_rmse'], ascending=[True, False]); R.to_csv(OUT / 'results' / 'c16_test_permutation_importance.csv', index=False)
for ep, g in R.groupby('endpoint'):
    print(ep); print(g.head(12).round(4).to_string(index=False))
