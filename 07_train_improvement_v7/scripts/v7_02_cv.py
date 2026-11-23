"""V7 step 2: does data recovery / cleaning / representation improve grouped CV on TRAIN?  (exploratory)

Engine: the V5 CV code itself (02_cv_models.Featurizer + V5 duplicate removal, fit_predict_ml with nested inner CV,
ivw_re weights, 3-level MR0). Folds: cv.make_folds('cluster', seed) over the UNION of studies of all configurations, so
every configuration uses identical outer folds; seeds 11/22/33.

Every configuration is scored on the SAME evaluation rows: in_default_v6 == 1 (V6 corrected, one contrast per arm pair).
Recovered rows / quality filtering change only what the models are TRAINED on. A configuration therefore cannot look
better because easier rows were removed from the evaluation.

Usage: python v7_02_cv.py yield|biomass [quick]
"""
import sys, json, time, pathlib
import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / '05_analysis_train_expansion_v5' / 'v5' / 'scripts'))
_argv = sys.argv; sys.argv = sys.argv[:1]
import v5_common as V
sys.argv = _argv
cv, r5 = V.cv, V.r5
OUT = REPO / '07_train_improvement_v7'
EP = sys.argv[1] if len(sys.argv) > 1 else 'yield'
QUICK = 'quick' in sys.argv
SEEDS = [11] if QUICK else [11, 22, 33]
SCHEME = 'cluster'

V5D = REPO / '05_analysis_train_expansion_v5' / 'v5' / 'data'
stem = 'yield' if EP == 'yield' else 'dry_biomass'
T5 = pd.read_parquet(V5D / f'train_{stem}.parquet')
T7 = pd.read_parquet(OUT / 'data' / f'train_{stem}_V7.parquet')
if EP == 'yield':                      # a study recovered both ways keeps the arm-level proxy, not the pooled main effect
    prox = set(T7.loc[T7.v7_source == 'COMPONENT_PROXY', 'study_id'])
    T7 = T7[~((T7.v7_source == 'MAIN_EFFECT') & T7.study_id.isin(prox))].reset_index(drop=True)


def prep(x):
    x = x.copy()
    x['target'] = x.effect.astype(float)
    x['v'] = x.var_lnrr_imp.astype(float)
    x['exp_uid'] = x.study_id.astype(str) + '|' + x.experiment_key.astype(str)
    x['endpoint_is_yield'] = int(EP == 'yield')
    for c in ['h2_drought_supply_reported', 'h2_salinity_reported', 'h2_stress_duration_reported']:
        if c in x.columns:
            x[c + '_cat'] = np.select([x[c] == 1, x[c] == 0], ['REPORTED', 'NOT_REPORTED'], 'NOT_APPLICABLE')
    return x[x.target.notna() & x.v.notna()].reset_index(drop=True)


T5, T7 = prep(T5), prep(T7)
EVAL_IDS = set(T7.loc[T7.in_default_v6 == 1, 'contrast_id'])

# --------------------------------------------------------------------------------------------- feature sets
REF_CAT, REF_NUM, _, _ = V.fsets(EP)['REF']
OUTCOME_CAT = (['yield_tier', 'h2_yield_scope', 'harvest_window', 'denominator'] if EP == 'yield' else ['organ_scope'])
OUTCOME_NUM = (['is_B_vs_C', 'is_dry_yield', 'is_early_yield', 'v7_is_main_effect', 'v7_is_proxy'] if EP == 'yield'
               else ['is_B_vs_C', 'is_terminal', 'dry_basis_confirmed', 'v6_age_days'])
PRODUCT = ['h2_live_microorganism', 'h2_nonliving_microbial_product', 'h2_n_components', 'h3_taxon_bacillus', 'h3_taxon_pseudomonas',
           'h3_taxon_trichoderma', 'h3_taxon_amf', 'h3_active_seaweed', 'h3_active_humic', 'h3_active_protein_amino',
           'h3_active_chitosan', 'h3_active_silicon', 'h3_log_n_applications', 'h_dose_rel_study', 'h3_phase_app_minus_stress']
STRESS = ['h_stress_rank_study', 'v7_exp_loss', 'v7_sal_ec_dsm', 'v7_drought_supply_frac', 'v7_log_stress_days']
CROP_ENV = ['h_potted', 'v7_log_pot_l', 'h3_small_fruited', 'h3_processing_type', 'h3_hybrid', 'v7_lat', 'h3_warm_season',
            'v7_temp_day', 'h3_sand_pct', 'h3_clay_pct', 'v7_log_fert_n', 'h3_experiment_year']
CAT_H = ['h2_dujardin', 'h_stress_class', 'h_route', 'h_system', 'h_dose_class', 'h2_application_phase', 'h2_stress_onset_phase',
         'h3_region', 'v7_fert_regime', 'h_growth_habit']
FS = {
    'REF_V5': (REF_CAT, REF_NUM),                                                     # what V5 selected for yield
    'COMPACT_V7': (OUTCOME_CAT + CAT_H, OUTCOME_NUM + PRODUCT + STRESS + CROP_ENV),
    'COMPACT_V7_noNEW': (OUTCOME_CAT + CAT_H, [c for c in OUTCOME_NUM + PRODUCT + STRESS + CROP_ENV
                                              if not c.startswith('v7_') and not c.startswith('v6_')] +
                         (['h_stress_intensity', 'h_nacl_equiv_mm'])),
    'MINIMAL_V7': (OUTCOME_CAT + ['h2_dujardin', 'h_stress_class'],
                   OUTCOME_NUM + ['v7_exp_loss', 'h_stress_rank_study', 'h_dose_rel_study', 'h3_log_n_applications', 'h_potted',
                                  'h3_small_fruited', 'h2_live_microorganism']),
}

DENSE_CAT = OUTCOME_CAT + ['h2_dujardin', 'h_stress_class', 'h_route', 'h_system']
DENSE_NUM = OUTCOME_NUM + ['h2_live_microorganism', 'h2_nonliving_microbial_product', 'h2_n_components', 'h_potted',
                           'h3_taxon_amf', 'h3_taxon_bacillus', 'h3_taxon_trichoderma', 'h3_active_seaweed', 'h3_active_silicon',
                           'h3_active_chitosan', 'h3_active_humic', 'h3_active_protein_amino',
                           'd_exp_loss', 'd_stress_rank', 'd_sal_ec', 'd_drought_supply', 'd_log_n_app', 'd_app_phase']
FS['DENSE_V7'] = (DENSE_CAT, DENSE_NUM)


def densify(tr, te):
    """Structural / in-fold group-median filling so that no feature carries a missingness pattern (which acts as a
    study identifier with ~60 training studies). Statistics come from the training rows only."""
    tr, te = tr.copy(), te.copy()
    none_tr = tr.h_stress_class.astype(str).eq('NONE') | (tr.contrast_type == 'B_vs_C')
    med_cls = tr[~none_tr].groupby('h_stress_class').v7_exp_loss.median()
    med_all = tr.loc[~none_tr, 'v7_exp_loss'].median()
    stats = {c: (set(tr[c].dropna().unique()) <= {0, 1}, tr[c].median()) for c in DENSE_NUM if c in tr.columns}
    n_med, ph_med = tr.h3_log_n_applications.median(), tr.h3_application_phase_ord.median()
    for x in (tr, te):
        none = x.h_stress_class.astype(str).eq('NONE') | (x.contrast_type == 'B_vs_C')
        el = x.v7_exp_loss.fillna(x.h_stress_class.map(med_cls)).fillna(med_all if pd.notna(med_all) else 0)
        x['d_exp_loss'] = np.where(none, 0.0, el)
        x['d_stress_rank'] = np.where(none, 0.0, x.h_stress_rank_study.fillna(1.0))
        x['d_sal_ec'] = x.v7_sal_ec_dsm.fillna(0.0)
        x['d_drought_supply'] = x.v7_drought_supply_frac.fillna(1.0)
        x['d_log_n_app'] = x.h3_log_n_applications.fillna(n_med)
        x['d_app_phase'] = x.h3_application_phase_ord.fillna(ph_med)
        for c, (binary, med) in stats.items():
            if not c.startswith('d_') and x[c].isna().any():
                x[c] = x[c].fillna(0 if binary else med)
    return tr, te


def fit_mrx(tr, te):
    """3-level meta-regression (study / experiment random effects) with compact dense moderators."""
    from metalib import ThreeLevelMeta
    nums = [c for c in ['is_B_vs_C', 'd_exp_loss', 'd_stress_rank', 'h2_live_microorganism', 'h_potted', 'd_log_n_app']
            + (['is_dry_yield', 'is_early_yield'] if EP == 'yield' else ['is_terminal']) if c in tr.columns]
    cats = ['h_stress_class', 'h2_dujardin'] + (['yield_tier'] if EP == 'yield' else ['organ_scope'])
    A, Bm = [np.ones(len(tr))], [np.ones(len(te))]
    for c in nums:
        a = tr[c].astype(float).values
        if np.nanstd(a) > 0:
            A.append(a); Bm.append(te[c].astype(float).values)
    for c in cats:
        s_tr, s_te = tr[c].astype(str), te[c].astype(str)
        ns = tr.groupby(s_tr).study_id.nunique()
        lv = ns[ns >= 5].sort_values(ascending=False).index.tolist()
        for l in lv[1:]:
            A.append((s_tr == l).astype(float).values); Bm.append((s_te == l).astype(float).values)
    m = ThreeLevelMeta().fit(tr.target.values, tr.v.values, np.column_stack(A), tr.study_id.values, tr.exp_uid.values)
    mu, _ = m.predict(np.column_stack(Bm), te.v.values)
    return mu


# --------------------------------------------------------------------------------------------- data configurations
def rows(name):
    if name == 'V5':            # V5 default rows (duplicates, lost V3.1 fixes, V5 features)
        return T5[T5.in_default == 1]
    if name == 'V6':
        return T7[T7.in_default_v6 == 1]
    if name == 'V6_QCORE':      # reliability-flagged rows removed from TRAINING only
        return T7[T7.in_quality_core_v6 == 1]
    rec = T7[T7.v7_source.isin(['MAIN_EFFECT', 'COMPONENT_PROXY'])]
    if name == 'V7_RECOVERED':
        return pd.concat([T7[T7.in_default_v6 == 1], rec], ignore_index=True)
    if name == 'V7_RECOVERED_QCORE':
        return pd.concat([T7[T7.in_quality_core_v6 == 1], rec[rec.v6_reliability_flag == 0]], ignore_index=True)
    raise KeyError(name)


DATA = ['V5', 'V6', 'V6_QCORE', 'V7_RECOVERED', 'V7_RECOVERED_QCORE'] if EP == 'yield' else ['V5', 'V6', 'V6_QCORE']
# (data, features, models, weight scheme)
CONFIGS = [('V5', 'REF_V5', ['RIDGE', 'RF'], 'ivw_re'),
           ('V6', 'REF_V5', ['RIDGE', 'RF'], 'ivw_re'),
           ('V6', 'REF_V5', ['RIDGE'], 'none'),
           ('V6', 'COMPACT_V7', ['RIDGE'], 'ivw_re'),
           ('V6', 'DENSE_V7', ['RIDGE', 'RF', 'MRX'], 'ivw_re'),
           ('V6', 'DENSE_V7', ['RIDGE'], 'none')]
CONFIGS += [(d, 'DENSE_V7', ['RIDGE', 'MRX'], 'ivw_re') for d in DATA[2:]]
CONFIGS += [(d, 'REF_V5', ['RIDGE'], 'ivw_re') for d in DATA[2:]]
EVAL = T7[T7.in_default_v6 == 1].reset_index(drop=True)
for c in set(EVAL.columns) - set(T5.columns):              # V5-trained models need the same columns on the eval rows
    T5[c] = np.nan
# folds over the union of all studies of every configuration
ALL = pd.concat([T5[['study_id', 'dependency_cluster_id']], T7[['study_id', 'dependency_cluster_id']],
                 V.B[['study_id', 'dependency_cluster_id']], V.Y[['study_id', 'dependency_cluster_id']]]).drop_duplicates('study_id')
cv.ALL = ALL; cv.STUDY2CLUSTER = ALL.set_index('study_id').dependency_cluster_id
cv.ROWS_PER_STUDY = pd.concat([T7.study_id, V.B.study_id if EP == 'yield' else V.Y.study_id]).value_counts()
for s in ALL.study_id:
    if s not in cv.ROWS_PER_STUDY.index:
        cv.ROWS_PER_STUDY[s] = 1


def run(seed):
    folds = cv.make_folds(SCHEME, seed)
    P = []
    for f in range(cv.N_OUTER):
        te = EVAL[EVAL.study_id.map(folds) == f].reset_index(drop=True)
        if te.empty:
            continue
        test_clusters = set(te.dependency_cluster_id)
        done_base = set()
        for dname, fname, models, wsch in CONFIGS:
            src = rows(dname)
            tr = src[(src.study_id.map(folds) != f) & ~src.dependency_cluster_id.isin(test_clusters)].reset_index(drop=True)
            te_x = te if dname != 'V5' else te.reindex(columns=list(dict.fromkeys(list(te.columns) + list(tr.columns))))
            if fname == 'DENSE_V7':
                tr, te_x = densify(tr, te_x)
            mu, lo, hi, m0, _ = cv.fit_mr(tr, te_x, 'MR0', EP); tau2 = m0.sigma2.sum()
            preds = {}
            if dname not in done_base:
                preds.update({'MR0': mu, 'BASELINE_mean': np.full(len(te), tr.target.mean())}); done_base.add(dname)
            cat, num = FS[fname]
            cat = [c for c in cat if c in tr.columns]; num = [c for c in num if c in tr.columns]
            r5.V3Featurizer.TE, r5.V3Featurizer.TFIDF = [], False
            for model in models:
                if QUICK and model == 'RF':
                    continue
                if model == 'MRX':
                    preds['MRX'] = fit_mrx(tr, te_x)
                    continue
                p, *_ = cv.fit_predict_ml(model, tr, te_x, cat, num, wsch, tau2, SCHEME, seed + f)
                preds[model + ('' if wsch == 'ivw_re' else '_w' + wsch)] = p
            for m, p in preds.items():
                fs_tag = fname if m not in ('MR0', 'BASELINE_mean') else '-'
                P.append(pd.DataFrame(dict(seed=seed, fold=f, data=dname, features=fs_tag, model=m, contrast_id=te.contrast_id,
                                           study_id=te.study_id, y=te.target, pred=p)))
        print(f'{EP} seed {seed} fold {f} done', flush=True)
    return pd.concat(P, ignore_index=True)


def score(P):
    out = []
    for (d, fs, m, s), g in P.groupby(['data', 'features', 'model', 'seed']):
        e = g.y - g.pred
        st = g.assign(e2=e ** 2).groupby('study_id').e2.mean()
        out.append(dict(data=d, features=fs, model=m, seed=s, n=len(g), studies=g.study_id.nunique(),
                        RMSE=float(np.sqrt((e ** 2).mean())), MAE=float(e.abs().mean()),
                        R2=float(1 - (e ** 2).sum() / ((g.y - g.y.mean()) ** 2).sum()),
                        RMSE_study_balanced=float(np.sqrt(st.mean()))))
    S = pd.DataFrame(out)
    base = S[(S.data == 'V5') & (S.model == 'BASELINE_mean')].set_index('seed')[['RMSE', 'RMSE_study_balanced']]
    S['dRMSE_vs_V5_mean_pct'] = (S.RMSE / S.seed.map(base.RMSE) - 1) * 100
    S['dRMSEsb_vs_V5_mean_pct'] = (S.RMSE_study_balanced / S.seed.map(base.RMSE_study_balanced) - 1) * 100
    return S


if __name__ == '__main__':
    t = time.time()
    P = pd.concat([run(s) for s in SEEDS], ignore_index=True)
    tag = EP + ('_quick' if QUICK else '')
    P.to_parquet(OUT / 'results' / f'v7_cv_oof_{tag}.parquet', index=False)
    S = score(P)
    S.to_csv(OUT / 'results' / f'v7_cv_by_seed_{tag}.csv', index=False)
    agg = S.groupby(['data', 'features', 'model']).agg(RMSE=('RMSE', 'mean'), RMSE_sd=('RMSE', 'std'), R2=('R2', 'mean'),
                                                        RMSE_sb=('RMSE_study_balanced', 'mean'),
                                                        d_vs_V5mean=('dRMSE_vs_V5_mean_pct', 'mean'),
                                                        d_sb_vs_V5mean=('dRMSEsb_vs_V5_mean_pct', 'mean')).reset_index()
    agg = agg.sort_values('RMSE')
    agg.to_csv(OUT / 'results' / f'v7_cv_summary_{tag}.csv', index=False)
    print(agg.round(4).to_string(index=False)); print(f'{time.time() - t:.0f}s')
