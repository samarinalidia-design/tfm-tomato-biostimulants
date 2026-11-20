"""Round 2 of legitimate improvement attempts (after the main ablation grid).

Same outer folds as 02_cv_models.py (make_folds is deterministic in the seed) -> directly comparable
with the DEFAULT rows of cv_metrics_all_runs.csv. Every data-driven choice (hyper-parameters,
blend weight lambda, stacking weights) is made on inner grouped CV of the training studies only.
Base learners inside blends/stacks use hyper-parameters fixed a priori (not tuned on outer data).

Variants tried (all reported):
  RF_strong_reg          RF, grid with larger leaves / fewer features (nested)
  GBM_absolute_loss      HistGB with absolute-error loss, shallow grid (nested)
  RF_compact / RIDGE_compact   compact harmonised feature set
  BLEND_RF_MR0 / BLEND_RIDGE_MR0  lambda*ML + (1-lambda)*3-level mean, lambda by inner CV
  STACK_mean             mean of RF, RIDGE, MR2 predictions (no tuning)
  STACK_nnls             non-negative weights (sum 1) over RF, RIDGE, MR0, MR2 from inner OOF
  MULTITASK4_RF / MULTITASK4_RIDGE  trained on yield+biomass+FRUIT_NUMBER+MEAN_FRUIT_MASS, scored on target endpoint
"""
import sys, json, time, pathlib, importlib.util, warnings
import numpy as np
import pandas as pd
from scipy.optimize import nnls
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('cv', HERE / '02_cv_models.py')
cv = importlib.util.module_from_spec(spec); sys.argv = sys.argv[:1]; spec.loader.exec_module(cv)
from harmonize import harmonize
from metalib import ThreeLevelMeta
warnings.filterwarnings('ignore')
RES = cv.RES
SEEDS = [11, 22, 33]


# ------------------------------------------------------------------ auxiliary endpoints (yield components)
def aux_table(endpoint):
    d = pd.read_parquet(cv.RAW / 'contrast_candidates.parquet')
    x = d[(d.endpoint == endpoint) & d.contrast_type.isin(['SB_vs_S', 'B_vs_C']) & (d.effect_metric == 'lnRR') &
          d.effect.notna() & (d.mean_t > 0) & (d.mean_c > 0) & ~d.exclusion_reason.str.contains('TEMPORAL') &
          ~d['flags'].str.contains('BOX_CENTRE_ASSUMED_MEAN|DUPLICATE_EXCLUDED')].copy()
    # same imputation rule as 01_build_tables (own author SD -> CV-bar of this endpoint; median n)
    cvs = []
    for s in ('t', 'c'):
        own = (x['dispersion_basis_raw_' + s] == 'SOURCE_REPORTED') & x['sd_' + s].gt(0)
        cvs.append(pd.DataFrame({'study_id': x.study_id, 'cv': (x['sd_' + s] / x['mean_' + s]).where(own), 'n': x['n_' + s]}))
    g = pd.concat(cvs).dropna(subset=['cv']).groupby('study_id').agg(cv=('cv', 'mean'), n=('n', 'mean'))
    cvbar = np.average(g.cv, weights=g.n.fillna(g.n.median()))
    nmed = pd.concat([x.n_t, x.n_c]).median()
    for s in ('t', 'c'):
        own = (x['dispersion_basis_raw_' + s] == 'SOURCE_REPORTED') & x['sd_' + s].gt(0)
        x['cv_used_' + s] = (x['sd_' + s] / x['mean_' + s]).where(own, cvbar)
        x['n_imp_' + s] = x['n_' + s].fillna(nmed)
    x['var_lnrr_imp'] = x.cv_used_t ** 2 / x.n_imp_t + x.cv_used_c ** 2 / x.n_imp_c
    x['w_n'] = x.n_imp_t * x.n_imp_c / (x.n_imp_t + x.n_imp_c)
    h = harmonize(x)
    for c in h.columns:
        x[c] = h[c]
    x['is_B_vs_C'] = (x.contrast_type == 'B_vs_C').astype(int)
    x['is_terminal'] = x.is_terminal_t
    x['exp_uid'] = x.study_id + '|' + x.experiment_key
    x['endpoint_is_yield'] = 0
    x['aux_endpoint'] = endpoint
    x['v'] = x.var_lnrr_imp; x['target'] = x.effect
    print(f'aux {endpoint}: {len(x)} contrasts, {x.study_id.nunique()} studies, CV-bar={cvbar:.3f}')
    return x


AUX = pd.concat([aux_table('FRUIT_NUMBER'), aux_table('MEAN_FRUIT_MASS')], ignore_index=True)
# aux studies outside the global fold map get their own fold by hashing (they never appear in evaluation)

COMPACT_CAT = ['h_dujardin', 'h_stress_class', 'h_system', 'h_route', 'h_dose_class']
COMPACT_NUM = ['h_stress_intensity', 'h_log10_dose', 'h_n_applications', 'f_soil_ph', 'f_temperature_day_c']

FIXED = {'RF': dict(max_features=0.33, min_samples_leaf=10), 'RIDGE': dict(alpha=100)}


def fixed_model(key, seed):
    if key == 'RF':
        return RandomForestRegressor(n_estimators=300, n_jobs=-1, random_state=seed, **FIXED['RF']), 'imputed'
    return Ridge(**FIXED['RIDGE']), 'scaled'


def fit_fixed(key, tr, te, cat, num, w, seed):
    fz = cv.Featurizer(cat, num).fit(tr)
    m, kind = fixed_model(key, seed)
    m.fit(fz.transform(tr, kind)[0], tr.target.values, sample_weight=w)
    return m.predict(fz.transform(te, kind)[0])


def base_preds(tr, te, ep, cat, num, seed):
    """Predictions of the four base learners (fixed hp) for te, trained on tr."""
    mu0, *_ , m0, _ = cv.fit_mr(tr, te, 'MR0', ep)
    tau2 = m0.sigma2.sum()
    mu2 = cv.fit_mr(tr, te, 'MR2', ep)[0]
    w = cv.weights(tr, 'ivw_re', tau2)
    return dict(RF=fit_fixed('RF', tr, te, cat, num, w, seed), RIDGE=fit_fixed('RIDGE', tr, te, cat, num, w, seed),
                MR0=mu0, MR2=mu2), tau2


def run(ep, scheme, seed, tau2_ref):
    df = cv.select(ep, cv.BASE).reset_index(drop=True)
    df['aux_endpoint'] = 'YIELD_OR_BIOMASS'
    folds = cv.make_folds(scheme, seed)
    cat0 = (cv.DEF_YIELD_CAT if ep == 'yield' else cv.DEF_BIO_CAT)
    num0 = (cv.DEF_YIELD_NUM if ep == 'yield' else cv.DEF_BIO_NUM)
    cat_full, num_full = cv.feature_lists('RAW+HARM', False); cat_full, num_full = cat0 + cat_full, num0 + num_full
    cat_c, num_c = cat0 + COMPACT_CAT, num0 + COMPACT_NUM
    other = cv.select('biomass' if ep == 'yield' else 'yield', cv.BASE)
    mt_pool = pd.concat([df, other, AUX], ignore_index=True)
    mt_cat, mt_num = cv.feature_lists('RAW+HARM', True)
    mt_cat = mt_cat + ['aux_endpoint']
    for c in ('aux_endpoint',):
        mt_pool[c] = mt_pool[c].fillna('YIELD_OR_BIOMASS')
    df = df.reindex(columns=list(dict.fromkeys(list(df.columns) + list(mt_pool.columns))))  # other-endpoint cols -> NaN
    preds = []
    for f in range(cv.N_OUTER):
        tr = df[df.study_id.map(folds) != f].reset_index(drop=True)
        te = df[df.study_id.map(folds) == f].reset_index(drop=True)
        if len(te) == 0:
            continue
        test_studies = set(te.study_id)
        out = {}
        # ---- tuned single models with stronger regularisation (nested)
        cv.GRIDS['RF_SR'] = [dict(max_features=mf, min_samples_leaf=ml) for mf in (0.2, 0.33) for ml in (20, 50)]
        cv.GRIDS['GBM_ABS'] = [dict(learning_rate=lr, max_depth=md, loss='absolute_error') for lr in (0.03, 0.1) for md in (1, 2)]
        tau2 = cv.fit_mr(tr, te, 'MR0', ep)[3].sigma2.sum()
        for name, key in [('RF_strong_reg', 'RF_SR'), ('GBM_absolute_loss', 'GBM_ABS')]:
            out[name] = _nested(key, tr, te, cat_full, num_full, tau2, scheme, seed + f)
        out['RF_compact'] = _nested('RF', tr, te, cat_c, num_c, tau2, scheme, seed + f)
        out['RIDGE_compact'] = _nested('RIDGE', tr, te, cat_c, num_c, tau2, scheme, seed + f)
        # ---- blends / stacks: inner OOF of the base learners on training studies
        splits = cv.inner_splits(cv.inner_groups(tr, scheme), seed=seed + f)
        oof = {k: np.full(len(tr), np.nan) for k in ('RF', 'RIDGE', 'MR0', 'MR2')}
        for itr, iva in splits:
            bp, _ = base_preds(tr.iloc[itr].reset_index(drop=True), tr.iloc[iva].reset_index(drop=True), ep, cat_full, num_full, seed + f)
            for k in oof:
                oof[k][iva] = bp[k]
        bp_te, _ = base_preds(tr, te, ep, cat_full, num_full, seed + f)
        ytr = tr.target.values; wtr = cv.weights(tr, 'ivw_re', tau2)
        for ml in ('RF', 'RIDGE'):
            best = min(np.linspace(0, 1, 11), key=lambda l: np.average((ytr - (l * oof[ml] + (1 - l) * oof['MR0'])) ** 2, weights=wtr))
            res = ytr - (best * oof[ml] + (1 - best) * oof['MR0'])
            p = best * bp_te[ml] + (1 - best) * bp_te['MR0']
            h = np.quantile(np.abs(res), 0.95)
            out[f'BLEND_{ml}_MR0'] = (p, p - h, p + h, f'lambda={best:.1f}')
        sm_oof = (oof['RF'] + oof['RIDGE'] + oof['MR2']) / 3
        p = (bp_te['RF'] + bp_te['RIDGE'] + bp_te['MR2']) / 3; h = np.quantile(np.abs(ytr - sm_oof), 0.95)
        out['STACK_mean_RF_RIDGE_MR2'] = (p, p - h, p + h, '')
        A = np.column_stack([oof[k] for k in ('RF', 'RIDGE', 'MR0', 'MR2')]); sw = np.sqrt(wtr)
        wts, _ = nnls(A * sw[:, None], ytr * sw); wts = wts / wts.sum() if wts.sum() > 0 else np.full(4, .25)
        p = np.column_stack([bp_te[k] for k in ('RF', 'RIDGE', 'MR0', 'MR2')]) @ wts
        h = np.quantile(np.abs(ytr - A @ wts), 0.95)
        out['STACK_nnls_RF_RIDGE_MR0_MR2'] = (p, p - h, p + h, json.dumps(dict(zip(['RF', 'RIDGE', 'MR0', 'MR2'], np.round(wts, 3).tolist()))))
        # ---- 4-endpoint multitask (all rows of held-out studies removed from training, any endpoint)
        mtr = mt_pool[~mt_pool.study_id.isin(test_studies) & (mt_pool.study_id.map(folds).fillna(-1) != f)].reset_index(drop=True)
        for name, key in [('MULTITASK4_RF', 'RF'), ('MULTITASK4_RIDGE', 'RIDGE')]:
            out[name] = _nested(key, mtr, te, mt_cat, mt_num, tau2, scheme, seed + f)
        for nm, (p, lo, hi, hp) in out.items():
            preds.append(pd.DataFrame(dict(contrast_id=te.contrast_id, study_id=te.study_id, fold=f, model=nm, y=te.target,
                                           pred=p, lo=lo, hi=hi, v_imp=te.var_lnrr_imp, hp=hp)))
    P = pd.concat(preds, ignore_index=True)
    rows = []
    for nm, g in P.groupby('model'):
        mt = cv.metrics(g.y.values, g.pred.values, g.lo.values, g.hi.values, 1 / (g.v_imp.values + tau2_ref))
        rows.append(dict(endpoint=ep, variant='ROUND2', model=nm, scheme=scheme, seed=seed, eval_set='OWN_rows',
                         n_studies=g.study_id.nunique(), **mt))
    return pd.DataFrame(rows), P.assign(endpoint=ep, scheme=scheme, seed=seed)


def _nested(key, tr, te, cat, num, tau2, scheme, seed):
    p, lo, hi, hp, _ = cv.fit_predict_ml(key if key in ('RF', 'GBM', 'RIDGE') else key, tr, te, cat, num, 'ivw_re', tau2, scheme, seed)
    return p, lo, hi, hp


# make_model must know the round-2 grid keys
_orig = cv.make_model
def _mm(name, hp, seed):
    if name == 'RF_SR':
        return _orig('RF', hp, seed)
    if name == 'GBM_ABS':
        return _orig('GBM', hp, seed)
    return _orig(name, hp, seed)
cv.make_model = _mm


if __name__ == '__main__':
    tau2_ref = json.load(open(RES / 'tau2_reference_for_wRMSE.json'))
    allm, allp = [], []
    for ep in ('yield', 'biomass'):
        for s in SEEDS:
            t = time.time()
            m, p = run(ep, 'study', s, tau2_ref[ep])
            allm.append(m); allp.append(p)
            print(f'{ep} seed={s} {time.time() - t:.0f}s', flush=True)
            pd.concat(allm).to_csv(RES / 'cv_metrics_round2.csv', index=False)
    pd.concat(allp).to_parquet(RES / 'cv_oof_predictions_round2.parquet', index=False)
