"""V7 step 8 (biomass): three targeted changes, tested with the same data (V6), engine, folds, evaluation rows and
bootstrap as v7_03.
  1 AGE    plant age coded with an explicit reference instead of the raw timepoint_days (mixed DAS / DAT / days of stress):
           log(1 + age days), the reference as a category, and a seedling-assay flag (age <= 30 d)
  2 SPLIT  separate models for SHOOT and WHOLE_PLANT (each trained on its organ only) vs one pooled model with organ as a feature
  3 W      training weights: ivw_re = 1/(v + tau2) (V5), none, n (equal total weight per study, V5 w_n)
Baselines: overall training mean, organ-specific training mean, MR0. Ridge for all; RF for the main variants.
"""
import sys, pathlib, time
import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.argv = [sys.argv[0], 'biomass']
sys.path.insert(0, str(HERE))
import v7_03_ablation as A

H, cv, r5 = A.H, A.cv, A.r5
EP = 'biomass'
TEXT = [c for g, cols in A.GROUPS.items() if 'text' in g or 'unit' in g for c in cols]
CLEAN = [c for c in A.ALLF if c not in TEXT]
AGE = ['age_log', 'age_ref', 'age_seedling']
CLEAN_AGE = [c for c in CLEAN if c != 'timepoint_days'] + AGE
CATS = set(A.REF_CAT) | {'age_ref'}


def add_age(df):
    df = df.copy()
    a = pd.to_numeric(df.v6_age_days, errors='coerce')
    df['age_log'] = np.log1p(a)
    df['age_ref'] = df.v6_age_reference.fillna('UNKNOWN').astype(str)
    df['age_seedling'] = np.where(a.notna(), (a <= 30).astype(float), np.nan)
    return df


# (name, features, weight scheme, split by organ, models)
CONFIGS = [('REF_CLEAN | w=ivw_re', CLEAN, 'ivw_re', False, ['RIDGE', 'RF']),
           ('REF_CLEAN | w=none', CLEAN, 'none', False, ['RIDGE', 'RF']),
           ('REF_CLEAN | w=n', CLEAN, 'n', False, ['RIDGE']),
           ('AGE | w=ivw_re', CLEAN_AGE, 'ivw_re', False, ['RIDGE']),
           ('AGE | w=none', CLEAN_AGE, 'none', False, ['RIDGE', 'RF']),
           ('AGE | w=n', CLEAN_AGE, 'n', False, ['RIDGE']),
           ('SPLIT | REF_CLEAN | w=none', CLEAN, 'none', True, ['RIDGE']),
           ('SPLIT | AGE | w=none', CLEAN_AGE, 'none', True, ['RIDGE', 'RF']),
           ('SPLIT | AGE | w=ivw_re', CLEAN_AGE, 'ivw_re', True, ['RIDGE'])]


def fit(model, tr, te, cols, wsch, seed):
    _, _, _, m0, _ = cv.fit_mr(tr, te, 'MR0', EP); tau2 = m0.sigma2.sum()
    cat = [c for c in cols if c in CATS and c in tr.columns]; num = [c for c in cols if c not in cat and c in tr.columns]
    r5.V3Featurizer.TE, r5.V3Featurizer.TFIDF = [], False
    p, *_ = cv.fit_predict_ml(model, tr, te, cat, num, wsch, tau2, H.SCHEME, seed)
    return p


def run(seed):
    folds = cv.make_folds(H.SCHEME, seed)
    src = add_age(H.rows('V6')); ev = add_age(H.EVAL)
    P = []
    for f in range(cv.N_OUTER):
        te = ev[ev.study_id.map(folds) == f].reset_index(drop=True)
        tr = src[(src.study_id.map(folds) != f) & ~src.dependency_cluster_id.isin(set(te.dependency_cluster_id))].reset_index(drop=True)
        rec = lambda name, p: P.append(pd.DataFrame(dict(seed=seed, config=name, contrast_id=te.contrast_id, study_id=te.study_id,
                                                         organ=te.organ_scope, y=te.target, pred=p)))
        rec('MEAN', np.full(len(te), tr.target.mean()))
        rec('MEAN_BY_ORGAN', te.organ_scope.map(tr.groupby('organ_scope').target.mean()).fillna(tr.target.mean()).values)
        mu, *_ = cv.fit_mr(tr, te, 'MR0', EP); rec('MR0', mu)
        for name, cols, wsch, split, models in CONFIGS:
            for m in models:
                if not split:
                    rec(f'{name} | {m}', fit(m, tr, te, cols, wsch, seed + f))
                    continue
                p = np.full(len(te), np.nan)
                for org in ['SHOOT', 'WHOLE_PLANT']:
                    a, b = tr[tr.organ_scope == org].reset_index(drop=True), te.organ_scope == org
                    if b.any():
                        p[b.values] = fit(m, a, te[b].reset_index(drop=True), [c for c in cols if c != 'organ_scope'], wsch, seed + f)
                rec(f'{name} | {m}', p)
        print(f'seed {seed} fold {f}', flush=True)
    return pd.concat(P, ignore_index=True)


if __name__ == '__main__':
    t = time.time()
    A.CONFIGS = [(f'{n} | {m}', c) for n, c, _, _, ms in CONFIGS for m in ms]
    P = pd.concat([run(s) for s in H.SEEDS], ignore_index=True)
    P.to_parquet(H.OUT / 'results' / 'v7_biomass_oof.parquet', index=False)
    S = A.summarise(P.drop(columns='organ'), ref='REF_CLEAN | w=ivw_re | RIDGE')
    S.to_csv(H.OUT / 'results' / 'v7_biomass_three_changes.csv', index=False)
    by = (P.assign(e2=(P.y - P.pred) ** 2).groupby(['config', 'organ', 'seed']).e2.mean().pow(.5)
          .groupby(['config', 'organ']).mean().unstack().round(4))
    by.to_csv(H.OUT / 'results' / 'v7_biomass_by_organ.csv')
    pd.set_option('display.width', 250)
    print(S[['config', 'RMSE', 'RMSE_seed_sd', 'd_vs_REF', 'd_vs_REF_lo', 'd_vs_REF_hi', 'd_vs_MEAN_pct', 'd_vs_MEAN_lo',
             'd_vs_MEAN_hi']].round(4).to_string(index=False))
    print(by.to_string())
    print(f'{time.time() - t:.0f}s')
