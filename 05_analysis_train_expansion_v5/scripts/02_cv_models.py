"""Task 3: grouped (study / dependency-cluster) nested cross-validation of every model x variant.

No study ever appears in both training and validation. All tuning is inside an inner GroupKFold
on the training studies only. ML features are restricted to role FEATURE (feature_policy.csv)
plus the author-mandated outcome-definition descriptors; harmonised h_* columns are derived only
from FEATURE columns and design codes. The S-vs-C stress reduction is used only as a
meta-regression moderator (model MR2), never in ML.

Usage: python 02_cv_models.py [quick]
"""
import sys, json, time, pathlib, itertools, warnings
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from metalib import ThreeLevelMeta

warnings.filterwarnings('ignore')
ROOT = pathlib.Path(__file__).resolve().parents[1]
PROC, RES, RAW = ROOT / 'data/processed', ROOT / 'results', ROOT / 'data/raw'
QUICK = len(sys.argv) > 1 and sys.argv[1] == 'quick'
N_OUTER = 5
N_INNER = 3
SEEDS_DEFAULT = [11, 22, 33] if not QUICK else [11]
SEEDS_ABL = [11, 22] if not QUICK else [11]
MIN_STUDIES_LEVEL = 3        # a category level must occur in >= 3 training studies, else -> OTHER

policy = pd.read_csv(RAW / 'feature_policy.csv')
FEATURE_COLS = policy.loc[policy.role == 'FEATURE', 'column'].tolist()

Y = pd.read_parquet(PROC / 'train_yield.parquet')
B = pd.read_parquet(PROC / 'train_dry_biomass.parquet')
Y['endpoint_is_yield'] = 1; B['endpoint_is_yield'] = 0
for x in (Y, B):
    x['exp_uid'] = x.study_id + '|' + x.experiment_key

# ------------------------------------------------------------------ feature sets
DEF_YIELD_CAT = ['yield_tier', 'yield_scope', 'mass_basis', 'harvest_window', 'denominator']
DEF_YIELD_NUM = ['is_B_vs_C', 'is_dry_yield', 'is_early_yield']
DEF_BIO_CAT = ['organ_scope']
DEF_BIO_NUM = ['is_B_vs_C', 'is_terminal', 'dry_basis_confirmed', 'timepoint_days']
H_CAT = ['h_dujardin', 'h_dose_class', 'h_stress_class', 'h_crop_group', 'h_growth_habit', 'h_hybrid', 'h_system', 'h_route']
H_NUM = ['h_log10_dose', 'h_dose_rel_study', 'h_stress_intensity', 'h_stress_rank_study', 'h_nacl_equiv_mm',
         'h_potted', 'h_n_applications'] + [c for c in Y.columns if c.startswith('h_dj_')]
RAW_NUM = [c for c in FEATURE_COLS if pd.api.types.is_numeric_dtype(Y[c])]
RAW_CAT = [c for c in FEATURE_COLS if c not in RAW_NUM]
FORBIDDEN = {'mod_lnrr_stress_SvsC', 'effect', 'effect_bc', 'effect_bc_imp', 'pct_effect', 'mean_t', 'mean_c', 'sd_t', 'sd_c',
             'var_effect', 'var_lnrr_imp', 'se_effect', 'ci95_lower', 'ci95_upper'}


def feature_lists(fset, multitask):
    cat, num = [], []
    if multitask:
        cat += sorted(set(DEF_YIELD_CAT + DEF_BIO_CAT)); num += sorted(set(DEF_YIELD_NUM + DEF_BIO_NUM)) + ['endpoint_is_yield']
    else:
        pass  # filled by caller per endpoint
    if fset in ('RAW', 'RAW+HARM'):
        cat += RAW_CAT; num += RAW_NUM
    if fset in ('HARM', 'RAW+HARM'):
        cat += H_CAT; num += H_NUM
    return cat, num


class Featurizer:
    def __init__(self, cat, num):
        self.cat, self.num = list(dict.fromkeys(cat)), list(dict.fromkeys(num))
        assert not (set(self.cat) | set(self.num)) & FORBIDDEN, 'post-treatment column in features'
        for c in self.cat + self.num:
            assert c in FEATURE_COLS or not c.startswith('f_'), c

    def fit(self, df):
        self.levels = {}
        for c in self.cat:
            s = df[c].astype(str)
            ns = df.groupby(s).study_id.nunique()
            self.levels[c] = sorted(ns[ns >= MIN_STUDIES_LEVEL].index.difference(['nan', 'None', '']))
        self.num_keep = [c for c in self.num if df[c].notna().any() and pd.to_numeric(df[c], errors='coerce').nunique() > 1]
        nd = df[self.num_keep].apply(pd.to_numeric, errors='coerce')
        self.lo, self.hi = nd.quantile(0.01), nd.quantile(0.99)     # winsorisation bounds learnt on training rows
        nd = nd.clip(self.lo, self.hi, axis=1)
        self.med = nd.median()
        self.mu = nd.fillna(self.med).mean(); self.sd = nd.fillna(self.med).std().replace(0, 1)
        self.miss_cols = [c for c in self.num_keep if nd[c].isna().any()]
        return self

    def transform(self, df, kind):
        nd = df[self.num_keep].apply(pd.to_numeric, errors='coerce').clip(self.lo, self.hi, axis=1)
        parts = []
        if kind == 'nan':
            parts.append(nd)
        else:
            z = nd.fillna(self.med)
            if kind == 'scaled':
                z = (z - self.mu) / self.sd
            parts.append(z)
            parts.append(nd[self.miss_cols].isna().astype(float).add_suffix('__missing'))
        for c in self.cat:
            s = df[c].astype(str)
            for lv in self.levels[c]:
                parts.append(pd.Series((s == lv).astype(float), index=df.index, name=f'{c}=={lv}'))
        X = pd.concat(parts, axis=1)
        return X.values.astype(float), list(X.columns)


# ------------------------------------------------------------------ folds (global, over the union of studies)
ALL = pd.concat([Y[['study_id', 'dependency_cluster_id']], B[['study_id', 'dependency_cluster_id']]]).drop_duplicates()
assert ALL.groupby('study_id').dependency_cluster_id.nunique().max() == 1, 'a study maps to >1 dependency cluster'
STUDY2CLUSTER = ALL.set_index('study_id').dependency_cluster_id
ROWS_PER_STUDY = pd.concat([Y.study_id, B.study_id]).value_counts()


def make_folds(scheme, seed, k=N_OUTER):
    """Balanced shuffled GroupKFold: returns study_id -> fold."""
    rng = np.random.default_rng(seed)
    if scheme == 'cluster':
        sizes = ROWS_PER_STUDY.groupby(STUDY2CLUSTER[ROWS_PER_STUDY.index].values).sum()
    else:
        sizes = ROWS_PER_STUDY
    groups = list(sizes.index)
    rng.shuffle(groups)
    groups = sorted(groups, key=lambda g: -sizes[g] + rng.uniform(0, 0.5))
    load = np.zeros(k); gfold = {}
    for g in groups:
        f = int(np.argmin(load)); gfold[g] = f; load[f] += sizes[g]
    if scheme == 'study':
        return {s: gfold[s] for s in ALL.study_id}
    return {s: gfold[STUDY2CLUSTER[s]] for s in ALL.study_id}


def inner_groups(df, scheme):
    return df.study_id.values if scheme == 'study' else df.dependency_cluster_id.values


def inner_splits(groups, k=N_INNER, seed=0):
    rng = np.random.default_rng(seed)
    ug = np.unique(groups); rng.shuffle(ug)
    f = {g: i % k for i, g in enumerate(ug)}
    fa = np.array([f[g] for g in groups])
    return [(np.where(fa != i)[0], np.where(fa == i)[0]) for i in range(k)]


# ------------------------------------------------------------------ models
def weights(df, scheme_w, tau2):
    v = df.v.values
    if scheme_w == 'ivw_re':
        return 1.0 / (v + tau2)
    if scheme_w == 'ivw_fixed':
        w = 1.0 / v
        return np.minimum(w, np.quantile(w, 0.99))      # cap the top 1 % to avoid single-row dominance
    if scheme_w == 'n':
        return df.w_n.values
    return np.ones(len(df))


GRIDS = {
    'RF': [dict(max_features=mf, min_samples_leaf=ml) for mf in (0.33, 0.66) for ml in (3, 10)],
    'GBM': [dict(learning_rate=lr, max_depth=md) for lr in (0.03, 0.1) for md in (2, 3)],
    'RIDGE': [dict(alpha=a) for a in (0.1, 1, 10, 100, 1000)],
}


def make_model(name, hp, seed):
    if name == 'RF':
        return RandomForestRegressor(n_estimators=300, n_jobs=-1, random_state=seed, **hp), 'imputed'
    if name == 'GBM':
        return HistGradientBoostingRegressor(max_iter=300, min_samples_leaf=20, l2_regularization=1.0,
                                             random_state=seed, **hp), 'nan'
    return Ridge(**hp), 'scaled'


def fit_predict_ml(name, tr, te, cat, num, wscheme, tau2, scheme, seed):
    """Nested: choose hp by inner grouped CV on training studies (weighted MSE), refit, predict."""
    ytr = tr.target.values; wtr = weights(tr, wscheme, tau2)
    splits = inner_splits(inner_groups(tr, scheme), seed=seed)
    best, best_sc, best_res = None, np.inf, None
    for hp in GRIDS[name]:
        res = np.full(len(tr), np.nan)
        for itr, iva in splits:
            fz = Featurizer(cat, num).fit(tr.iloc[itr])
            m, kind = make_model(name, hp, seed)
            Xa, _ = fz.transform(tr.iloc[itr], kind); Xb, _ = fz.transform(tr.iloc[iva], kind)
            m.fit(Xa, ytr[itr], sample_weight=wtr[itr])
            res[iva] = ytr[iva] - m.predict(Xb)
        sc = np.average(res ** 2, weights=wtr)
        if sc < best_sc:
            best, best_sc, best_res = hp, sc, res
    fz = Featurizer(cat, num).fit(tr)
    m, kind = make_model(name, best, seed)
    Xa, cols = fz.transform(tr, kind); Xb, _ = fz.transform(te, kind)
    m.fit(Xa, ytr, sample_weight=wtr)
    pred = m.predict(Xb)
    half = np.quantile(np.abs(best_res), 0.95)                 # inner-OOF (conformal-style) 95 % half-width
    return pred, pred - half, pred + half, json.dumps(best), (m, cols)


def mr_design(df_tr, df_te, endpoint, with_svc, multitask=False):
    """Design matrix for meta-regression moderators (levels with >=5 training studies)."""
    cats = ['h_stress_class', 'h_dujardin']
    nums = ['is_B_vs_C']
    if endpoint == 'yield' or multitask:
        cats += ['yield_tier']
    if endpoint == 'biomass' or multitask:
        cats += ['organ_scope']; nums += ['is_terminal', 'dry_basis_confirmed']
    if multitask:
        nums += ['endpoint_is_yield']
    cols_tr, cols_te, names = [np.ones(len(df_tr))], [np.ones(len(df_te))], ['intercept']
    for c in nums:
        a, b = df_tr[c].astype(float).fillna(0).values, df_te[c].astype(float).fillna(0).values
        if np.std(a) > 0:
            cols_tr.append(a); cols_te.append(b); names.append(c)
    for c in cats:
        s_tr, s_te = df_tr[c].astype(str), df_te[c].astype(str)
        ns = df_tr.groupby(s_tr).study_id.nunique()
        lv = ns[ns >= 5].sort_values(ascending=False).index.tolist()
        for l in lv[1:]:                                       # most frequent level = reference
            cols_tr.append((s_tr == l).astype(float).values); cols_te.append((s_te == l).astype(float).values)
            names.append(f'{c}=={l}')
    if with_svc:
        a, b = df_tr.mod_lnrr_stress_SvsC, df_te.mod_lnrr_stress_SvsC
        mu = a.mean()
        cols_tr += [a.fillna(mu).values, a.isna().astype(float).values]
        cols_te += [b.fillna(mu).values, b.isna().astype(float).values]
        names += ['mod_lnrr_stress_SvsC', 'mod_lnrr_stress_SvsC__missing']
    return np.column_stack(cols_tr), np.column_stack(cols_te), names


def fit_mr(tr, te, level, endpoint, multitask=False):
    if level == 'MR0':
        Xtr, Xte, names = np.ones((len(tr), 1)), np.ones((len(te), 1)), ['intercept']
    else:
        Xtr, Xte, names = mr_design(tr, te, endpoint, with_svc=(level == 'MR2'), multitask=multitask)
    m = ThreeLevelMeta().fit(tr.target.values, tr.v.values, Xtr, tr.study_id.values, tr.exp_uid.values)
    mu, sd = m.predict(Xte, te.v.values)
    return mu, mu - 1.96 * sd, mu + 1.96 * sd, m, names


# ------------------------------------------------------------------ metrics
def metrics(y, p, lo, hi, w):
    e = y - p
    sst = ((y - y.mean()) ** 2).sum()
    return dict(n=len(y), RMSE=float(np.sqrt(np.mean(e ** 2))), MAE=float(np.mean(np.abs(e))),
                R2=float(1 - (e ** 2).sum() / sst) if sst > 0 else np.nan,
                wRMSE=float(np.sqrt(np.sum(w * e ** 2) / np.sum(w))),
                coverage95=float(np.mean((y >= lo) & (y <= hi))) if lo is not None else np.nan,
                mean_PI_width=float(np.mean(hi - lo)) if lo is not None else np.nan)


# ------------------------------------------------------------------ variants
def table(endpoint):
    return (Y if endpoint == 'yield' else B).copy()


def select(endpoint, v):
    x = table(endpoint)
    sel = pd.Series(True, index=x.index)
    if not v.get('boxplots', False):
        sel &= x.is_boxplot == 0
    if endpoint == 'biomass' and not v.get('all_timepoints', False):
        sel &= x.is_last_timepoint == 1
    if not v.get('b_vs_c', True):
        sel &= x.contrast_type == 'SB_vs_S'
    if endpoint == 'yield':
        if v.get('strict_only', False):
            sel &= x.yield_tier == 'STRICT'
        if not v.get('dry_early', True):
            sel &= ~x.yield_tier.isin(['DRY', 'EARLY'])
    if v.get('variance') == 'author_only':
        sel &= x.variance_from_author_sd == 1
    x = x[sel].copy()
    # sampling variance used for weights / meta-models
    if v.get('variance') == 'meancv_all':
        x['v'] = x.var_lnrr_meancv_all
    elif v.get('variance') == 'author_only':
        x['v'] = x.var_lnrr_imp                       # == own author-SD variance for these rows
    else:
        x['v'] = x.var_lnrr_imp
    tgt = v.get('target', 'lnRR')
    x['target'] = x.effect if tgt == 'lnRR' else x.effect_bc_imp
    return x


BASE = dict(variance='imputed', b_vs_c=True, strict_only=False, boxplots=False, all_timepoints=False,
            dry_early=True, weights='ivw_re', multitask=False, features='RAW+HARM', target='lnRR')
VARIANTS = {
    'yield': [
        ('DEFAULT', {}),
        ('TARGET_effect_bc', dict(target='effect_bc')),
        ('NO_IMPUTATION_author_SD_only', dict(variance='author_only')),
        ('IMPUTATION_meanCV_all_groups', dict(variance='meancv_all')),
        ('NO_B_vs_C', dict(b_vs_c=False)),
        ('STRICT_yield_only', dict(strict_only=True)),
        ('WITH_boxplots', dict(boxplots=True)),
        ('NO_dry_early_yield', dict(dry_early=False)),
        ('WEIGHTS_ivw_fixed', dict(weights='ivw_fixed')),
        ('WEIGHTS_n', dict(weights='n')),
        ('WEIGHTS_none', dict(weights='none')),
        ('MULTITASK_yield+biomass', dict(multitask=True)),
        ('FEATURES_raw_only', dict(features='RAW')),
        ('FEATURES_harmonised_only', dict(features='HARM')),
    ],
    'biomass': [
        ('DEFAULT', {}),
        ('TARGET_effect_bc', dict(target='effect_bc')),
        ('NO_IMPUTATION_author_SD_only', dict(variance='author_only')),
        ('IMPUTATION_meanCV_all_groups', dict(variance='meancv_all')),
        ('NO_B_vs_C', dict(b_vs_c=False)),
        ('ALL_timepoints', dict(all_timepoints=True)),
        ('WITH_boxplots', dict(boxplots=True)),
        ('WEIGHTS_ivw_fixed', dict(weights='ivw_fixed')),
        ('WEIGHTS_n', dict(weights='n')),
        ('WEIGHTS_none', dict(weights='none')),
        ('MULTITASK_yield+biomass', dict(multitask=True)),
        ('FEATURES_raw_only', dict(features='RAW')),
        ('FEATURES_harmonised_only', dict(features='HARM')),
    ]}
MODELS = ['BASELINE_mean', 'BASELINE_wmean', 'MR0_3level_intercept', 'MR1_3level_design', 'MR2_3level_design+SvsC',
          'RF_weighted(MetaForest-style)', 'GBM_weighted', 'RIDGE_weighted']


def run_variant(endpoint, vname, vopt, scheme, seed, tau2_ref):
    v = {**BASE, **vopt}
    df = select(endpoint, v)
    other = 'biomass' if endpoint == 'yield' else 'yield'
    train_pool = df
    if v['multitask']:
        o = select(other, {**BASE})
        train_pool = pd.concat([df, o], ignore_index=True)
    # evaluation sets: own rows, and the endpoint DEFAULT rows (common reference set)
    ref = select(endpoint, {**BASE, 'target': v['target']})
    eval_pool = pd.concat([df.assign(_own=1), ref[~ref.contrast_id.isin(df.contrast_id)].assign(_own=0)], ignore_index=True)
    eval_pool['_ref'] = eval_pool.contrast_id.isin(ref.contrast_id).astype(int)
    if v['multitask']:   # other-endpoint columns absent on eval rows -> NaN, as in the concatenated train pool
        eval_pool = eval_pool.reindex(columns=list(dict.fromkeys(list(eval_pool.columns) + list(train_pool.columns))))
    folds = make_folds(scheme, seed)
    if v['multitask']:
        cat, num = feature_lists(v['features'], True)
    else:
        cat, num = feature_lists(v['features'], False)
        cat = (DEF_YIELD_CAT if endpoint == 'yield' else DEF_BIO_CAT) + cat
        num = (DEF_YIELD_NUM if endpoint == 'yield' else DEF_BIO_NUM) + num
    preds = []
    for f in range(N_OUTER):
        tr = train_pool[train_pool.study_id.map(folds) != f].reset_index(drop=True)
        te = eval_pool[eval_pool.study_id.map(folds) == f].reset_index(drop=True)
        assert not set(tr.study_id) & set(te.study_id)
        if len(te) == 0 or tr.study_id.nunique() < 5:
            continue
        out = {}
        # meta-models (always inverse-variance with REML random effects)
        mu0, lo0, hi0, m0, _ = fit_mr(tr, te, 'MR0', endpoint, v['multitask'])
        tau2 = m0.sigma2.sum()
        out['MR0_3level_intercept'] = (mu0, lo0, hi0, '')
        for lvl, nm in [('MR1', 'MR1_3level_design'), ('MR2', 'MR2_3level_design+SvsC')]:
            try:
                mu, lo, hi, _, names = fit_mr(tr, te, lvl, endpoint, v['multitask'])
                out[nm] = (mu, lo, hi, f'p={len(names)}')
            except Exception as ex:
                print('MR fail', vname, lvl, ex)
        # baselines
        w = weights(tr, v['weights'], tau2)
        for nm, c in [('BASELINE_mean', tr.target.mean()), ('BASELINE_wmean', np.average(tr.target, weights=w))]:
            half = np.quantile(np.abs(tr.target - c), 0.95)
            out[nm] = (np.full(len(te), c), np.full(len(te), c - half), np.full(len(te), c + half), '')
        for nm, key in [('RF_weighted(MetaForest-style)', 'RF'), ('GBM_weighted', 'GBM'), ('RIDGE_weighted', 'RIDGE')]:
            p, lo, hi, hp, _ = fit_predict_ml(key, tr, te, cat, num, v['weights'], tau2, scheme, seed + f)
            out[nm] = (p, lo, hi, hp)
        for nm, (p, lo, hi, hp) in out.items():
            preds.append(pd.DataFrame(dict(contrast_id=te.contrast_id, study_id=te.study_id, fold=f, model=nm,
                                           y=te.target, pred=p, lo=lo, hi=hi, v=te.v, v_imp=te.var_lnrr_imp, own=te._own, ref=te._ref,
                                           tau2_train=tau2, hp=hp)))
    P = pd.concat(preds, ignore_index=True)
    P['endpoint'], P['variant'], P['scheme'], P['seed'] = endpoint, vname, scheme, seed
    rows = []
    for (model), g in P.groupby('model'):
        for subset, gg in [('OWN_rows', g[g.own == 1]), ('DEFAULT_reference_rows', g[g.ref == 1])]:
            if len(gg) == 0:
                continue
            wref = 1.0 / (gg.v_imp.values + tau2_ref)
            mt = metrics(gg.y.values, gg.pred.values, gg.lo.values, gg.hi.values, wref)
            rows.append(dict(endpoint=endpoint, variant=vname, model=model, scheme=scheme, seed=seed, eval_set=subset,
                             n_studies=gg.study_id.nunique(), train_contrasts=len(train_pool), target_rows=len(df),
                             train_studies=train_pool.study_id.nunique(), **mt))
    return pd.DataFrame(rows), P


def main():
    t0 = time.time()
    # reference tau^2 for weighted RMSE: full-data DEFAULT 3-level intercept model, per endpoint
    tau2_ref = {}
    for ep in ('yield', 'biomass'):
        d = select(ep, BASE)
        tau2_ref[ep] = ThreeLevelMeta().fit(d.target, d.v, np.ones((len(d), 1)), d.study_id, d.exp_uid).sigma2.sum()
    json.dump(tau2_ref, open(RES / 'tau2_reference_for_wRMSE.json', 'w'), indent=1)
    allm, allp = [], []
    done = set()
    prev = RES / 'cv_metrics_all_runs.csv'
    if prev.exists():   # resume: keep finished jobs (their metrics), run only the missing ones
        pm = pd.read_csv(prev); allm.append(pm)
        done = set(map(tuple, pm[['endpoint', 'variant', 'scheme', 'seed']].drop_duplicates().values.tolist()))
    jobs = []
    for ep in ('yield', 'biomass'):
        for vname, vopt in VARIANTS[ep]:
            if vname == 'DEFAULT':
                jobs += [(ep, vname, vopt, sc, s) for sc in ('study', 'cluster') for s in SEEDS_DEFAULT]
            elif vname == 'TARGET_effect_bc':
                jobs += [(ep, vname, vopt, 'study', s) for s in SEEDS_DEFAULT]
            else:
                jobs += [(ep, vname, vopt, 'study', s) for s in SEEDS_ABL]
    for i, (ep, vname, vopt, sc, s) in enumerate(jobs):
        t = time.time()
        if (ep, vname, sc, s) in done:
            continue
        m, p = run_variant(ep, vname, vopt, sc, s, tau2_ref[ep])
        allm.append(m); allp.append(p)
        print(f'[{i + 1}/{len(jobs)}] {ep} {vname} {sc} seed={s} {time.time() - t:.0f}s', flush=True)
        pd.concat(allm).to_csv(RES / 'cv_metrics_all_runs.csv', index=False)
    if allp:
        pd.concat(allp).to_parquet(RES / 'cv_oof_predictions.parquet', index=False)
    print('total', time.time() - t0)


if __name__ == '__main__':
    main()
