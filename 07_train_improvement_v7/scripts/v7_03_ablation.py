"""V7 step 3: which feature groups carry signal and which add noise?  (TRAIN, grouped nested CV, exploratory)

Data V6 (in_default_v6), model Ridge (V5 engine, nested alpha, ivw_re weights), the identical outer folds and evaluation
rows as v7_02_cv.py, seeds 11/22/33.
  DROP_<g>  full REF_V5 set minus group g   -> RMSE falls  => g adds noise; RMSE rises => g carries signal
  ONLY_<g>  CORE (outcome definition + contrast type) plus group g alone
Uncertainty: paired difference to the reference model on the same rows; 95 % CI from 2000 bootstrap resamples of
studies (the out-of-fold squared errors of the 3 seeds are averaged per contrast first).
Usage: python v7_03_ablation.py yield|biomass
"""
import sys, pathlib, time
import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
EP = sys.argv[1] if len(sys.argv) > 1 else 'yield'
sys.argv = [sys.argv[0], EP]
sys.path.insert(0, str(HERE))
import v7_02_cv as H                       # data, folds, engine (its main() is not run)

cv, r5 = H.cv, H.r5
REF_CAT, REF_NUM = H.FS['REF_V5']
ALLF = REF_CAT + REF_NUM


def pick(pred):
    return [c for c in ALLF if pred(c)]


CORE = pick(lambda c: c in ['yield_tier', 'yield_scope', 'mass_basis', 'harvest_window', 'denominator', 'is_dry_yield',
                            'is_early_yield', 'organ_scope', 'is_terminal', 'dry_basis_confirmed', 'timepoint_days', 'is_B_vs_C'])
GROUPS = {
    'unit_strings (f_*_unit)': pick(lambda c: c.startswith('f_') and c.endswith('_unit')),
    'country (f_country)': pick(lambda c: c == 'f_country'),
    'genotype text (cultivar, genotype type, fruit type, growth habit, grafted)':
        pick(lambda c: c in ['f_cultivar', 'f_genotype_type', 'f_fruit_type', 'f_growth_habit', 'f_grafted']),
    'system/substrate text': pick(lambda c: c in ['f_system', 'f_substrate']),
    'stress text (type, onset, irrigation regime)': pick(lambda c: c in ['f_stress_type', 'f_stress_onset_stage', 'f_irrigation_regime']),
    'product text (class, composition, microorganism, strain)':
        pick(lambda c: c in ['f_biostimulant_class', 'f_composition', 'f_microorganism', 'f_strain']),
    'application text (route, frequency, stage, dose unit)':
        pick(lambda c: c in ['f_route', 'f_frequency', 'f_application_stage', 'f_dose_unit']),
    'season/soil/fertilisation text': pick(lambda c: c in ['f_season', 'f_soil_texture', 'f_fertilization']),
    'pathogen text': pick(lambda c: c in ['f_pathogen', 'f_pathogen_strain', 'f_inoculum_dose', 'f_inoculation_method']),
    'raw numeric environment (f_ pH, OM, lat, T, RH, PPFD, photoperiod, pot, density)':
        pick(lambda c: c in ['f_soil_ph', 'f_organic_matter', 'f_latitude', 'f_temperature_day_c', 'f_temperature_night_c',
                             'f_relative_humidity', 'f_ppfd', 'f_photoperiod_h', 'f_pot_volume_l', 'f_plant_density_m2']),
    'raw numeric stress (f_ FC, NaCl, soil EC, ECw, duration)':
        pick(lambda c: c in ['f_field_capacity_pct', 'f_nacl_mm', 'f_soil_ec', 'f_ec_irrigation_ds_m', 'f_stress_duration_days']),
    'raw numeric application (f_ dose, n applications, days before stress)':
        pick(lambda c: c in ['f_dose', 'f_n_applications', 'f_days_application_before_stress']),
    'harmonised categories (h_ dose class, stress class, crop group, habit, hybrid, system, route, du Jardin)':
        pick(lambda c: c in ['h_dose_class', 'h_stress_class', 'h_crop_group', 'h_growth_habit', 'h_hybrid', 'h_system', 'h_route', 'h2_dujardin']),
    'harmonised dose/application (h_log10_dose, dose rank, n applications)':
        pick(lambda c: c in ['h_log10_dose', 'h_dose_rel_study', 'h_n_applications']),
    'harmonised stress intensity (h_stress_intensity, rank, NaCl equiv.)':
        pick(lambda c: c in ['h_stress_intensity', 'h_stress_rank_study', 'h_nacl_equiv_mm']),
    'product type flags (live microbe, non-living microbial, n components, potted)':
        pick(lambda c: c in ['h2_n_components', 'h2_live_microorganism', 'h2_nonliving_microbial_product', 'h_potted']),
}
covered = set(CORE).union(*GROUPS.values())
rest = [c for c in ALLF if c not in covered]
if rest:
    GROUPS['other'] = rest
CONFIGS = [('REF_FULL', ALLF), ('CORE_ONLY', CORE)]
for g, cols in GROUPS.items():
    if cols:
        CONFIGS.append(('DROP | ' + g, [c for c in ALLF if c not in cols]))
        CONFIGS.append(('ONLY | ' + g, CORE + cols))


def split_cols(cols, df):
    cat = [c for c in cols if c in REF_CAT and c in df.columns]
    num = [c for c in cols if c in REF_NUM and c in df.columns]
    return cat, num


def run(seed):
    folds = cv.make_folds(H.SCHEME, seed)
    src = H.rows('V6')
    P = []
    for f in range(cv.N_OUTER):
        te = H.EVAL[H.EVAL.study_id.map(folds) == f].reset_index(drop=True)
        if te.empty:
            continue
        tr = src[(src.study_id.map(folds) != f) & ~src.dependency_cluster_id.isin(set(te.dependency_cluster_id))].reset_index(drop=True)
        _, _, _, m0, _ = cv.fit_mr(tr, te, 'MR0', EP); tau2 = m0.sigma2.sum()
        P.append(pd.DataFrame(dict(seed=seed, config='MEAN', contrast_id=te.contrast_id, study_id=te.study_id, y=te.target,
                                   pred=tr.target.mean())))
        r5.V3Featurizer.TE, r5.V3Featurizer.TFIDF = [], False
        for name, cols in CONFIGS:
            cat, num = split_cols(cols, tr)
            p, *_ = cv.fit_predict_ml('RIDGE', tr, te, cat, num, 'ivw_re', tau2, H.SCHEME, seed + f)
            P.append(pd.DataFrame(dict(seed=seed, config=name, contrast_id=te.contrast_id, study_id=te.study_id, y=te.target, pred=p)))
        print(f'{EP} seed {seed} fold {f}', flush=True)
    return pd.concat(P, ignore_index=True)


def summarise(P, ref='REF_FULL', B=2000):
    P = P.assign(e2=(P.y - P.pred) ** 2)
    E = P.groupby(['config', 'contrast_id', 'study_id']).e2.mean().reset_index()       # average over seeds
    W = E.pivot(index=['contrast_id', 'study_id'], columns='config', values='e2').reset_index()
    studies = W.study_id.unique(); rng = np.random.default_rng(2026)
    idx = {s: np.where(W.study_id.values == s)[0] for s in studies}
    boots = [np.concatenate([idx[s] for s in rng.choice(studies, len(studies))]) for _ in range(B)]
    rm = lambda col, ii: np.sqrt(W[col].values[ii].mean())
    seed_rmse = P.groupby(['config', 'seed']).e2.mean().pow(0.5).unstack()
    out = []
    for c in [c for c in W.columns if c not in ('contrast_id', 'study_id')]:
        full = np.arange(len(W))
        d_ref = np.array([rm(c, b) - rm(ref, b) for b in boots]); d_mean = np.array([rm(c, b) - rm('MEAN', b) for b in boots])
        out.append(dict(config=c, n_features=len(dict(CONFIGS).get(c, [])), RMSE=rm(c, full),
                        RMSE_seed_sd=float(seed_rmse.loc[c].std()),
                        d_vs_REF=rm(c, full) - rm(ref, full), d_vs_REF_lo=np.quantile(d_ref, .025), d_vs_REF_hi=np.quantile(d_ref, .975),
                        d_vs_MEAN_pct=(rm(c, full) / rm('MEAN', full) - 1) * 100,
                        d_vs_MEAN_lo=np.quantile(d_mean, .025), d_vs_MEAN_hi=np.quantile(d_mean, .975)))
    return pd.DataFrame(out).sort_values('RMSE')


if __name__ == '__main__':
    t = time.time()
    P = pd.concat([run(s) for s in H.SEEDS], ignore_index=True)
    P.to_parquet(H.OUT / 'results' / f'v7_ablation_oof_{EP}.parquet', index=False)
    S = summarise(P)
    S.to_csv(H.OUT / 'results' / f'v7_ablation_{EP}.csv', index=False)
    pd.DataFrame([(g, len(c), ';'.join(c)) for g, c in GROUPS.items()], columns=['group', 'n', 'columns']).to_csv(
        H.OUT / 'results' / f'v7_ablation_groups_{EP}.csv', index=False)
    pd.set_option('display.width', 250); pd.set_option('display.max_colwidth', 95)
    print(S.round(4).to_string(index=False)); print(f'{time.time() - t:.0f}s')
