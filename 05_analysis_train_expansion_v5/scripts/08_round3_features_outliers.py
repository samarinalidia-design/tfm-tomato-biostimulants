"""Round 3: does the v2 feature representation (user review points 3-5) change the metrics, and how much
do the unusual studies drive the error?  Same outer folds/seeds as the main grid (study-grouped).

A. Feature sets (RF, GBM, RIDGE nested; MR1 meta-regression with the matching du Jardin column):
   V1_DEFAULT          grid default (RAW+HARM v1)
   V2_DUJARDIN_FIX     v1 with du Jardin v2 (cell-free fix, component count)
   V2_FULL             + context-aware stress numerics, phases, substrate, density
   V2_FULL_REFINED_DEF + yield definitions refined from locator text (yield only)
   V2_COMPACT          definition + harmonised v2 only (no raw f_* text categories)
   Context-aware imputation: a drought/salinity/duration value missing *inside* its stress context is
   imputed with the training median of that context only (never with the 100 % / 0 'not applicable' code).
B. Influence sensitivity (v1 features): train without flagged studies / winsorised training target;
   metrics on all rows and on non-flagged rows. Nothing is deleted from the tables.
"""
import sys, json, time, pathlib, importlib.util, warnings
import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('cv', HERE / '02_cv_models.py')
cv = importlib.util.module_from_spec(spec); sys.argv = sys.argv[:1]; spec.loader.exec_module(cv)
warnings.filterwarnings('ignore')
RES, PROC = cv.RES, cv.PROC
SEEDS = [11, 22, 33]

Y2 = pd.read_parquet(PROC / 'train_yield_v2.parquet'); B2 = pd.read_parquet(PROC / 'train_dry_biomass_v2.parquet')
for x in (Y2, B2):
    x['exp_uid'] = x.study_id + '|' + x.experiment_key
    x['endpoint_is_yield'] = int(x is Y2)
    for c in ['h2_drought_supply_reported', 'h2_salinity_reported', 'h2_stress_duration_reported']:
        x[c + '_cat'] = np.select([x[c] == 1, x[c] == 0], ['REPORTED', 'NOT_REPORTED'], 'NOT_APPLICABLE')
cv.Y, cv.B = Y2, B2                      # v2 tables contain every v1 column unchanged

CTX = {'h2_drought_fc_pct': ('h_stress_class', 'DROUGHT'), 'h2_drought_etc_pct': ('h_stress_class', 'DROUGHT'),
       'h2_salinity_nacl_mm': ('h_stress_class', 'SALINITY'), 'h2_salinity_ecw_dsm': ('h_stress_class', 'SALINITY'),
       'h2_stress_duration_days': ('is_B_vs_C', 0), 'h2_days_application_before_stress': ('is_B_vs_C', 0)}
_fit = cv.Featurizer.fit


def ctx_fit(self, df):
    _fit(self, df)
    for c, (col, val) in CTX.items():
        if c in self.num_keep:
            m = (df[col] == val) & df[c].notna()
            if m.any():
                self.med[c] = pd.to_numeric(df.loc[m, c]).median()
    return self


cv.Featurizer.fit = ctx_fit

H2_CAT = ['h2_dujardin', 'h2_drought_supply_type', 'h2_salinity_measure_type', 'h2_application_phase', 'h2_stress_onset_phase',
          'h2_substrate_type', 'h2_density_status', 'h2_drought_supply_reported_cat', 'h2_salinity_reported_cat', 'h2_stress_duration_reported_cat']
H2_NUM = ['h2_n_components', 'h2_live_microorganism', 'h2_nonliving_microbial_product', 'h2_drought_fc_pct', 'h2_drought_etc_pct',
          'h2_salinity_nacl_mm', 'h2_salinity_ecw_dsm', 'h2_stress_duration_days', 'h2_days_application_before_stress',
          'h2_soil_ec_dsm', 'h2_plant_density_m2']
V1_DJ = ['h_dujardin'] + [c for c in Y2.columns if c.startswith('h_dj_')]


def feats(ep, fset):
    cat0 = list(cv.DEF_YIELD_CAT if ep == 'yield' else cv.DEF_BIO_CAT)
    num0 = list(cv.DEF_YIELD_NUM if ep == 'yield' else cv.DEF_BIO_NUM)
    cat, num = cv.feature_lists('RAW+HARM', False)
    if fset == 'V1_DEFAULT':
        return cat0 + cat, num0 + num
    cat = [c for c in cat if c not in V1_DJ]; num = [c for c in num if c not in V1_DJ]
    if fset == 'V2_DUJARDIN_FIX':
        return cat0 + cat + ['h2_dujardin'], num0 + num + ['h2_n_components', 'h2_live_microorganism', 'h2_nonliving_microbial_product']
    if fset in ('V2_FULL', 'V2_FULL_REFINED_DEF'):
        if fset == 'V2_FULL_REFINED_DEF':
            cat0 = [{'yield_scope': 'h2_yield_scope', 'harvest_window': 'h2_harvest_window'}.get(c, c) for c in cat0]
        return cat0 + cat + H2_CAT, num0 + num + H2_NUM
    if fset == 'V2_COMPACT':
        hc = [c for c in cv.H_CAT if c != 'h_dujardin']; hn = [c for c in cv.H_NUM if c not in V1_DJ]
        return cat0 + hc + H2_CAT, num0 + hn + H2_NUM


def mr1(tr, te, ep, dj_col):
    tr2, te2 = tr.copy(), te.copy()
    tr2['h_dujardin'], te2['h_dujardin'] = tr[dj_col], te[dj_col]
    return cv.fit_mr(tr2, te2, 'MR1', ep)


FLAGGED = {'D_19afb23b32e7648a': '10.32604/phyton.2022.016227 (42 -> 1166.6 g/plant, printed in source)',
           'D_9ade6969f561f9cc': '10.3390/IECPS2020-08883 (Francesca et al., conference; S = 0.07 kg/plant)',
           'D_24fe4181e5a0c693': '10.3390/agriculture13010006 (Fig. 7 digitised; S = 0.56 kg/plant)',
           'D_e8e2e6fbeb301530': '10.9734/IJPSS/2021/v33i1130479 (AMF-only arm below control in Table 6; 1-18 g/plant)'}


def run_A(ep, seed, tau2_ref):
    df = cv.select(ep, cv.BASE).reset_index(drop=True)
    folds = cv.make_folds('study', seed)
    fsets = ['V1_DEFAULT', 'V2_DUJARDIN_FIX', 'V2_FULL', 'V2_COMPACT'] + (['V2_FULL_REFINED_DEF'] if ep == 'yield' else [])
    rows, drop_log = [], []
    for fs in fsets:
        cat, num = feats(ep, fs)
        P = []
        for f in range(cv.N_OUTER):
            tr = df[df.study_id.map(folds) != f].reset_index(drop=True); te = df[df.study_id.map(folds) == f].reset_index(drop=True)
            tau2 = cv.fit_mr(tr, te, 'MR0', ep)[3].sigma2.sum()
            fz = cv.Featurizer(cat, num).fit(tr)
            drop_log += [dict(endpoint=ep, fset=fs, seed=seed, fold=f, feature=c, kept=int(c in fz.num_keep)) for c in num]
            out = {}
            for nm, key in [('RF', 'RF'), ('GBM', 'GBM'), ('RIDGE', 'RIDGE')]:
                p, lo, hi, hp, _ = cv.fit_predict_ml(key, tr, te, cat, num, 'ivw_re', tau2, 'study', seed + f)
                out[nm] = (p, lo, hi)
            if fs in ('V1_DEFAULT', 'V2_DUJARDIN_FIX'):
                mu, lo, hi, _, _ = mr1(tr, te, ep, 'h_dujardin' if fs == 'V1_DEFAULT' else 'h2_dujardin')
                out['MR1_3level_design'] = (mu, lo, hi)
            for nm, (p, lo, hi) in out.items():
                P.append(pd.DataFrame(dict(model=nm, study_id=te.study_id, y=te.target, pred=p, lo=lo, hi=hi, v_imp=te.var_lnrr_imp)))
        P = pd.concat(P)
        for nm, g in P.groupby('model'):
            rows.append(dict(endpoint=ep, part='A_features', variant=fs, model=nm, seed=seed, eval_set='OWN_rows',
                             **cv.metrics(g.y.values, g.pred.values, g.lo.values, g.hi.values, 1 / (g.v_imp.values + tau2_ref))))
    return rows, drop_log


def run_B(ep, seed, tau2_ref):
    df = cv.select(ep, cv.BASE).reset_index(drop=True)
    folds = cv.make_folds('study', seed)
    cat, num = feats(ep, 'V1_DEFAULT')
    flagged = set(FLAGGED) if ep == 'yield' else set()
    if ep == 'biomass':                      # top-3 biomass contributors of baseline squared error
        e = (df.target - df.target.mean()) ** 2
        flagged = set(e.groupby(df.study_id).sum().sort_values(ascending=False).index[:3])
    rows, P = [], []
    for strat in ('AS_IS', 'TRAIN_WITHOUT_FLAGGED', 'WINSORISED_TRAIN_TARGET_2.5_97.5'):
        for f in range(cv.N_OUTER):
            tr = df[df.study_id.map(folds) != f].reset_index(drop=True); te = df[df.study_id.map(folds) == f].reset_index(drop=True)
            if strat == 'TRAIN_WITHOUT_FLAGGED':
                tr = tr[~tr.study_id.isin(flagged)].reset_index(drop=True)
            if strat.startswith('WINSOR'):
                lo_, hi_ = tr.target.quantile([0.025, 0.975]); tr = tr.assign(target=tr.target.clip(lo_, hi_))
            mu0, lo0, hi0, m0, _ = cv.fit_mr(tr, te, 'MR0', ep); tau2 = m0.sigma2.sum()
            out = {'MR0_3level_intercept': (mu0, lo0, hi0), 'MR2_3level_design+SvsC': cv.fit_mr(tr, te, 'MR2', ep)[:3]}
            c = tr.target.mean(); h = np.quantile(np.abs(tr.target - c), 0.95)
            out['BASELINE_mean'] = (np.full(len(te), c), np.full(len(te), c - h), np.full(len(te), c + h))
            for nm, key in [('RF', 'RF'), ('RIDGE', 'RIDGE')]:
                p, lo, hi, _, _ = cv.fit_predict_ml(key, tr, te, cat, num, 'ivw_re', tau2, 'study', seed + f)
                out[nm] = (p, lo, hi)
            for nm, (p, lo, hi) in out.items():
                P.append(pd.DataFrame(dict(strategy=strat, model=nm, study_id=te.study_id, y=te.target, pred=p, lo=lo, hi=hi, v_imp=te.var_lnrr_imp)))
    P = pd.concat(P)
    for (strat, nm), g in P.groupby(['strategy', 'model']):
        for es, gg in [('ALL_rows', g), ('NON_FLAGGED_rows', g[~g.study_id.isin(flagged)])]:
            rows.append(dict(endpoint=ep, part='B_influence', variant=strat, model=nm, seed=seed, eval_set=es,
                             flagged=';'.join(sorted(flagged)),
                             **cv.metrics(gg.y.values, gg.pred.values, gg.lo.values, gg.hi.values, 1 / (gg.v_imp.values + tau2_ref))))
        e2 = (g.y - g.pred) ** 2
        rows.append(dict(endpoint=ep, part='B_influence', variant=strat, model=nm, seed=seed, eval_set='SSE_share_of_flagged',
                         flagged=';'.join(sorted(flagged)), RMSE=float(e2[g.study_id.isin(flagged)].sum() / e2.sum())))
    return rows


if __name__ == '__main__':
    tau2_ref = json.load(open(RES / 'tau2_reference_for_wRMSE.json'))
    allr, drops = [], []
    for ep in ('yield', 'biomass'):
        for s in SEEDS:
            t = time.time()
            r, d = run_A(ep, s, tau2_ref[ep]); allr += r; drops += d
            allr += run_B(ep, s, tau2_ref[ep])
            print(f'{ep} seed={s} {time.time() - t:.0f}s', flush=True)
            pd.DataFrame(allr).to_csv(RES / 'cv_metrics_round3_features_influence.csv', index=False)
    D = pd.DataFrame(drops)
    D.groupby(['endpoint', 'fset', 'feature']).kept.agg(['sum', 'count']).rename(columns={'sum': 'folds_kept', 'count': 'folds_total'}) \
        .reset_index().to_csv(RES / 'feature_retention_across_folds.csv', index=False)
    pd.DataFrame([{'study_id': k, 'reason': v} for k, v in FLAGGED.items()]).to_csv(RES / 'flagged_unusual_studies_yield.csv', index=False)
