"""Finish round 3 after the low-memory stop: run the missing (endpoint, seed) jobs only and append them;
write feature-retention table (Featurizer-only pass, all endpoints/seeds/folds) and the flagged-study list."""
import sys, json, pathlib, importlib.util, time
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('r3', HERE / '08_round3_features_outliers.py')
r3 = importlib.util.module_from_spec(spec); spec.loader.exec_module(r3)
cv, RES = r3.cv, r3.RES
_mm = cv.make_model
def make_model_lowmem(*a, **k):            # fewer parallel RF workers -> lower peak memory
    m, kind = _mm(*a, **k)
    if hasattr(m, 'n_jobs'):
        m.set_params(n_jobs=4)
    return m, kind
cv.make_model = make_model_lowmem

f = RES / 'cv_metrics_round3_features_influence.csv'
prev = pd.read_csv(f)
done = set(map(tuple, prev[['endpoint', 'seed']].drop_duplicates().values.tolist()))
tau2_ref = json.load(open(RES / 'tau2_reference_for_wRMSE.json'))
rows = []
for ep in ('yield', 'biomass'):
    for s in r3.SEEDS:
        if (ep, s) in done:
            continue
        t = time.time()
        r, _ = r3.run_A(ep, s, tau2_ref[ep]); rows += r
        rows += r3.run_B(ep, s, tau2_ref[ep])
        pd.concat([prev, pd.DataFrame(rows)]).to_csv(f, index=False)
        print(f'{ep} seed={s} {time.time() - t:.0f}s', flush=True)

# feature retention: which numeric features survive the training-fold filter (non-constant, not all-missing)
log = []
for ep in ('yield', 'biomass'):
    df = cv.select(ep, cv.BASE).reset_index(drop=True)
    fsets = ['V1_DEFAULT', 'V2_DUJARDIN_FIX', 'V2_FULL', 'V2_COMPACT'] + (['V2_FULL_REFINED_DEF'] if ep == 'yield' else [])
    for s in r3.SEEDS:
        folds = cv.make_folds('study', s)
        for fold in range(cv.N_OUTER):
            tr = df[df.study_id.map(folds) != fold]
            for fs in fsets:
                cat, num = r3.feats(ep, fs)
                fz = cv.Featurizer(cat, num).fit(tr)
                log += [dict(endpoint=ep, fset=fs, feature=c, kept=int(c in fz.num_keep)) for c in dict.fromkeys(num)]
                log += [dict(endpoint=ep, fset=fs, feature=c, kept=int(len(fz.levels[c]) > 0)) for c in dict.fromkeys(cat)]
D = pd.DataFrame(log)
D.groupby(['endpoint', 'fset', 'feature']).kept.agg(['sum', 'count']).rename(columns={'sum': 'folds_kept', 'count': 'folds_total'}) \
    .reset_index().to_csv(RES / 'feature_retention_across_folds.csv', index=False)
pd.DataFrame([{'study_id': k, 'reason': v} for k, v in r3.FLAGGED.items()]).to_csv(RES / 'flagged_unusual_studies_yield.csv', index=False)
print('done')
