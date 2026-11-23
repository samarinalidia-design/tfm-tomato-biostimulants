"""Comparable grouped CV on TRAIN for three targets: fruit yield, dry biomass (V6 tables) and leaf chlorophyll content (V8).

Same engine for all (V5 02_cv_models via v5_common: Featurizer with levels in >= 3 studies, median imputation + missing
indicators, nested inner CV for hyper-parameters, 3-level MR0), same seeds (11/22/33), same 5 outer folds grouped by
dependency cluster (made per target over its own studies), same model / weight configurations, evaluation on the default
rows of each target (yield / biomass: in_default_v6; chlorophyll: in_default_chl). Features: the a-priori REF set of V5
(yield and biomass: V5 REF of the endpoint; chlorophyll: the biomass REF with the outcome-definition columns of chlorophyll
instead of organ_scope / dry_basis_confirmed).
Weight schemes: ivw_re (1/(v+tau2), V5 default), none, n (= equal weight per study: w_n = 1 / contrasts of the study).
Uncertainty: study bootstrap (2000) of RMSE(model) - RMSE(mean), pooled over seeds.
Usage: python c09_cv_three_targets.py yield|biomass|chlorophyll|chl_index [quick] [authorgroup]
"""
import sys, json, time, pathlib
import numpy as np
import pandas as pd

OUT = pathlib.Path(__file__).resolve().parents[1]
REPO = OUT.parent
sys.path.insert(0, str(REPO / '05_analysis_train_expansion_v5' / 'v5' / 'scripts'))
_argv = sys.argv; sys.argv = sys.argv[:1]
import v5_common as V
sys.argv = _argv
cv, r5 = V.cv, V.r5
TARGET = sys.argv[1] if len(sys.argv) > 1 else 'chlorophyll'
QUICK = 'quick' in sys.argv
SEEDS = [11] if QUICK else [11, 22, 33]
EP = 'yield' if TARGET == 'yield' else 'biomass'           # engine branch (MR design, featurizer names)

if TARGET == 'yield':
    T = pd.read_parquet(REPO / '06_database_corrections_v6' / 'data' / 'train_yield_V6.parquet'); T = T[T.in_default_v6 == 1]
elif TARGET == 'biomass':
    T = pd.read_parquet(REPO / '06_database_corrections_v6' / 'data' / 'train_dry_biomass_V6.parquet'); T = T[T.in_default_v6 == 1]
elif TARGET == 'chlorophyll':
    T = pd.read_parquet(OUT / 'data' / 'train_chlorophyll_V8.parquet'); T = T[T.in_default == 1]
else:
    T = pd.read_parquet(OUT / 'data' / 'train_chl_index_V8.parquet'); T = T[T.in_default == 1]
T = T.copy()
T['study_id'] = T.study_id.astype(str)
T['target'] = T.effect.astype(float)
T['v'] = T.var_lnrr_imp.astype(float)
T['exp_uid'] = T.study_id + '|' + T.experiment_key.astype(str)
T['endpoint_is_yield'] = int(TARGET == 'yield')
T['w_n'] = 1.0 / T.groupby('study_id').target.transform('size')          # equal study weight, same definition for all targets
T = T[T.target.notna() & T.v.notna() & (T.v > 0)].reset_index(drop=True)
if 'contrast_id' not in T:
    T['contrast_id'] = np.arange(len(T)).astype(str)

AUTHORGROUP = 'authorgroup' in sys.argv
if AUTHORGROUP:
    # stricter grouping (sensitivity): studies of one research group share a cluster (>= 3 shared author surnames, or 2 when one
    # of them is the first or last author; very common surnames ignored), united with the A399 dependency clusters
    import sqlite3, re, itertools
    import os
    DB = os.environ.get('TFM_TRAIN_DB', str(pathlib.Path(__file__).resolve().parents[2] / '03_data_freeze' / 'train_dev_DATA_FREEZE_20261113T112939135807Z' / 'TFM_DATABASE_CLASS_A_FINAL.sqlite'))   # unzip the release database here or set TFM_TRAIN_DB
    ST = pd.read_sql('select study_id, authors from studies', sqlite3.connect(f'file:{DB}?mode=ro', uri=True))
    ST['study_id'] = ST.study_id.astype(str)
    COMMON = {'li', 'zhang', 'liu', 'wang', 'chen', 'yang', 'zhao', 'wu', 'xu', 'sun', 'zhou', 'huang', 'lin', 'ma', 'zhu', 'hu', 'guo',
              'he', 'gao', 'khan', 'ali', 'ahmad', 'ahmed', 'kumar', 'singh', 'hussain', 'islam', 'kim', 'lee', 'park', 'wei', 'yu', 'liang'}
    sur = lambda a: [re.sub(r'[^a-z]', '', x.split(',')[0].lower()) for x in str(a).split(';') if x.strip()]
    AU = {r.study_id: [x for x in sur(r.authors) if x and x not in COMMON] for r in ST.itertuples() if r.study_id in set(T.study_id)}
    parent = {s: c for s, c in zip(T.study_id, T.dependency_cluster_id)}
    root = {}
    def find(x):
        while root.get(x, x) != x:
            x = root[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            root[ra] = rb
    for s, c in parent.items():
        union(s, 'CL:' + str(c))
    for a, b in itertools.combinations(AU, 2):
        A, B = AU[a], AU[b]
        if not A or not B:
            continue
        sh = set(A) & set(B)
        if len(sh) >= 3 or (len(sh) >= 2 and ({A[0], A[-1]} & set(B) or {B[0], B[-1]} & set(A))):
            union(a, b)
    T['dependency_cluster_id'] = T.study_id.map(lambda s: 'AG:' + find(s))

cat, num, _, _ = V.fsets('yield' if TARGET == 'yield' else 'biomass')['REF']
if TARGET in ('chlorophyll', 'chl_index'):
    cat = ['chl_basis', 'chl_measure_kind'] + [c for c in cat if c != 'organ_scope']
    num = [c for c in num if c not in ('dry_basis_confirmed',)] + ['is_computed_total']
cat = [c for c in cat if c in T.columns]; num = [c for c in num if c in T.columns]

cv.ALL = T[['study_id', 'dependency_cluster_id']].drop_duplicates('study_id')
cv.STUDY2CLUSTER = cv.ALL.set_index('study_id').dependency_cluster_id
cv.ROWS_PER_STUDY = T.study_id.value_counts()
CONFIGS = [('RIDGE', 'ivw_re'), ('RIDGE', 'none'), ('RIDGE', 'n'), ('RF', 'ivw_re'), ('RF', 'n')]


def run(seed):
    folds = cv.make_folds('cluster', seed)
    P = []
    for f in range(cv.N_OUTER):
        te = T[T.study_id.map(folds) == f].reset_index(drop=True)
        if te.empty:
            continue
        tr = T[(T.study_id.map(folds) != f) & ~T.dependency_cluster_id.isin(set(te.dependency_cluster_id))].reset_index(drop=True)
        mu, lo, hi, m0, _ = cv.fit_mr(tr, te, 'MR0', EP); tau2 = m0.sigma2.sum()
        preds = {'MR0': mu, 'BASELINE_mean': np.full(len(te), tr.target.mean()),
                 'BASELINE_mean_studyw': np.full(len(te), np.average(tr.target, weights=tr.w_n))}
        r5.V3Featurizer.TE, r5.V3Featurizer.TFIDF = [], False
        for model, w in CONFIGS:
            if QUICK and model == 'RF':
                continue
            p, *_ = cv.fit_predict_ml(model, tr, te, cat, num, w, tau2, 'cluster', seed + f)
            preds[f'{model}_REF_w{w}'] = p
        for m, p in preds.items():
            P.append(pd.DataFrame(dict(target=TARGET, seed=seed, fold=f, model=m, contrast_id=te.contrast_id, study_id=te.study_id,
                                       y=te.target, pred=p)))
        print(f'{TARGET} seed {seed} fold {f} done', flush=True)
    return pd.concat(P, ignore_index=True)


def summarise(P, B=2000):
    rows = []
    rng = np.random.default_rng(20261122)
    studies = P.study_id.unique()
    base = P[P.model == 'BASELINE_mean']
    for m, g in P.groupby('model'):
        e2 = (g.y - g.pred) ** 2
        r = dict(target=TARGET, model=m, n=len(g) // g.seed.nunique(), studies=g.study_id.nunique(),
                 RMSE=float(np.sqrt(e2.mean())), R2=float(1 - e2.sum() / ((g.y - g.y.mean()) ** 2).sum()),
                 RMSE_study_balanced=float(np.sqrt(g.assign(e2=e2).groupby('study_id').e2.mean().mean())))
        # study bootstrap of the RMSE difference to the mean
        a = g.assign(e2=e2).groupby('study_id').e2.agg(['sum', 'size'])
        b = base.assign(e2=(base.y - base.pred) ** 2).groupby('study_id').e2.agg(['sum', 'size'])
        a, b = a.reindex(studies).fillna(0), b.reindex(studies).fillna(0)
        idx = rng.integers(0, len(studies), (B, len(studies)))
        ra = np.sqrt(a['sum'].values[idx].sum(1) / a['size'].values[idx].sum(1))
        rb = np.sqrt(b['sum'].values[idx].sum(1) / b['size'].values[idx].sum(1))
        d = ra / rb - 1
        r.update(d_vs_mean_pct=100 * (r['RMSE'] / float(np.sqrt(((base.y - base.pred) ** 2).mean())) - 1),
                 d_ci_low_pct=100 * np.quantile(d, 0.025), d_ci_high_pct=100 * np.quantile(d, 0.975))
        rows.append(r)
    return pd.DataFrame(rows).sort_values('RMSE')


if __name__ == '__main__':
    t = time.time()
    P = pd.concat([run(s) for s in SEEDS], ignore_index=True)
    tag = TARGET + ('_quick' if QUICK else '') + ('_authorgroup' if AUTHORGROUP else '')
    P.to_parquet(OUT / 'results' / f'c09_oof_{tag}.parquet', index=False)
    S = summarise(P)
    S.to_csv(OUT / 'results' / f'c09_cv_summary_{tag}.csv', index=False)
    info = dict(target=TARGET, rows=len(T), studies=int(T.study_id.nunique()), clusters=int(T.dependency_cluster_id.nunique()),
                n_cat=len(cat), n_num=len(num), sd_target=float(T.target.std()), seconds=round(time.time() - t))
    (OUT / 'results' / f'c09_info_{tag}.json').write_text(json.dumps(info, indent=1), encoding='utf-8')
    print(json.dumps(info)); print(S.round(4).to_string(index=False))
