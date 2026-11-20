"""Task 1 + Task 2: expanded training tables for FRUIT_YIELD and DRY_BIOMASS with
missing-variance imputation (Nakagawa et al. 2023, Ecol. Lett.).

Input : data/raw/contrast_candidates.parquet (DATA_FREEZE_20261113T112939135807Z, read only)
Output: data/processed/*.parquet|csv, data/processed/new_columns_dictionary.csv,
        results/build_flow_counts.csv, results/variance_imputation_summary.csv
"""
import json, re, pathlib
import numpy as np
import pandas as pd
from scipy import stats
from harmonize import harmonize

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW, OUT, RES = ROOT / 'data/raw', ROOT / 'data/processed', ROOT / 'results'
OUT.mkdir(parents=True, exist_ok=True); RES.mkdir(exist_ok=True)

d = pd.read_parquet(RAW / 'contrast_candidates.parquet')
d['flag_list'] = d['flags'].map(json.loads)
d['year_num'] = pd.to_numeric(d['year'], errors='coerce')
flow = []


def log(table, step, df, note=''):
    flow.append(dict(table=table, step=step, contrasts=len(df), studies=df['study_id'].nunique(),
                     clusters=df['dependency_cluster_id'].nunique(), note=note))


def has_flag(df, f):
    return df['flag_list'].map(lambda L: any(x == f or x.startswith(f + ':') for x in L))


# ============================================================ common eligibility
def base_pool(endpoint, tag):
    x = d[d.endpoint == endpoint].copy(); log(tag, '00 endpoint=' + endpoint + ' (all contrast types)', x)
    x = x[x.dataset_role == 'TRAIN_DEV']; log(tag, '01 dataset_role TRAIN_DEV', x)
    x = x[~x.exclusion_reason.str.contains('TEMPORAL')]; log(tag, '02 drop TEMPORAL_OR_DATASET_ROLE_INELIGIBLE', x)
    x = x[(x.effect_metric == 'lnRR') & x.effect.notna() & (x.mean_t > 0) & (x.mean_c > 0)]
    log(tag, '03 lnRR computable (means > 0)', x)
    x['is_duplicate'] = has_flag(x, 'DUPLICATE_EXCLUDED').astype(int)
    x = x[x.is_duplicate == 0]; log(tag, '04 drop DUPLICATE_EXCLUDED', x, 'no contrast carries this flag in this freeze')
    x['is_boxplot'] = has_flag(x, 'BOX_CENTRE_ASSUMED_MEAN').astype(int)
    return x


# ============================================================ YIELD
y = base_pool('FRUIT_YIELD', 'yield')
y_inter = y[y.contrast_type.isin(['SxB', 'AxB', 'B_MAIN_EFFECT'])].copy()
y_svc = y[y.contrast_type == 'S_vs_C'].copy()
y = y[y.contrast_type.isin(['SB_vs_S', 'B_vs_C'])].copy()
log('yield', '05 contrast_type in {SB_vs_S, B_vs_C} (SxB/AxB/B_MAIN_EFFECT kept in separate table; S_vs_C -> moderator only)', y)
y = y[y.yield_scope.fillna('') != 'NON_MARKETABLE']; log('yield', '06 drop NON_MARKETABLE yield', y)


def yield_tier(r):
    den_ok = r.denominator not in ('UNSPECIFIED', 'OTHER', None) and r.denominator == r.denominator
    unit_ok = bool(r.unit_norm) and r.unit_norm == r.unit_norm
    if r.yield_scope == 'TOTAL' and r.mass_basis == 'FRESH' and r.harvest_window == 'CUMULATIVE' and den_ok and unit_ok:
        return 'STRICT'
    if r.yield_scope in ('TOTAL', 'UNSPECIFIED') and r.mass_basis in ('FRESH', 'UNSPECIFIED') and r.harvest_window in ('CUMULATIVE', 'UNSPECIFIED') and den_ok and unit_ok:
        return 'ASSUMED'
    if r.yield_scope in ('TOTAL', 'MARKETABLE', 'UNSPECIFIED') and r.mass_basis in ('FRESH', 'UNSPECIFIED') and r.harvest_window in ('CUMULATIVE', 'SINGLE_HARVEST', 'PARTIAL', 'UNSPECIFIED') and den_ok and unit_ok:
        return 'BROAD'
    if r.yield_scope in ('TOTAL', 'MARKETABLE', 'UNSPECIFIED') and r.mass_basis in ('FRESH', 'UNSPECIFIED') and r.harvest_window in ('CUMULATIVE', 'SINGLE_HARVEST', 'PARTIAL', 'UNSPECIFIED'):
        return 'UNIT_UNRESOLVED'
    if r.yield_scope == 'EARLY':
        return 'EARLY'
    if r.mass_basis == 'DRY':
        return 'DRY'
    return 'OTHER_DEFINITION'


y['yield_tier'] = y.apply(yield_tier, axis=1)
y['is_dry_yield'] = (y.mass_basis == 'DRY').astype(int)
y['is_early_yield'] = (y.yield_scope == 'EARLY').astype(int)
for t in ['STRICT', 'ASSUMED', 'BROAD', 'UNIT_UNRESOLVED', 'EARLY', 'DRY', 'OTHER_DEFINITION']:
    log('yield', f'   tier {t}', y[y.yield_tier == t])
for c in ['SB_vs_S', 'B_vs_C']:
    log('yield', f'   contrast_type {c}', y[y.contrast_type == c])
log('yield', '   boxplot (BOX_CENTRE_ASSUMED_MEAN) rows', y[y.is_boxplot == 1])

# ============================================================ BIOMASS
b = base_pool('DRY_BIOMASS', 'biomass')
b_inter = b[b.contrast_type.isin(['SxB', 'AxB'])].copy()
b_svc = b[b.contrast_type == 'S_vs_C'].copy()
b = b[b.contrast_type.isin(['SB_vs_S', 'B_vs_C'])].copy()
log('biomass', '05 contrast_type in {SB_vs_S, B_vs_C}', b)
b = b[b.organ_scope.isin(['SHOOT', 'WHOLE_PLANT'])]; log('biomass', '06 organ_scope in {SHOOT, WHOLE_PLANT} (ROOT/LEAF/STEM/OTHER dropped)', b)
b_inter = b_inter[b_inter.organ_scope.isin(['SHOOT', 'WHOLE_PLANT'])]
b_svc = b_svc[b_svc.organ_scope.isin(['SHOOT', 'WHOLE_PLANT'])]

# last timepoint per group: same study / experiment / arms / organ / measurement signature without tp
b['sig_no_tp'] = b.signature.str.replace(r';tp=[^;]*', '', regex=True)
b['tp_group_id'] = b[['study_id', 'experiment_key', 'arm_key_t', 'arm_key_c', 'organ_scope', 'sig_no_tp']].astype(str).agg('|'.join, axis=1)
b['_ord_days'] = b.timepoint_days.fillna(-1)
b = b.sort_values(['tp_group_id', 'is_terminal_t', '_ord_days', 'timepoint_key'])
b['n_timepoints_in_group'] = b.groupby('tp_group_id').contrast_id.transform('size')
b['is_last_timepoint'] = (~b.duplicated('tp_group_id', keep='last')).astype(int)
b = b.drop(columns='_ord_days')
log('biomass', '   last timepoint per group (default model)', b[b.is_last_timepoint == 1])
log('biomass', '   all timepoints (sensitivity)', b)
log('biomass', '   boxplot rows', b[b.is_boxplot == 1])
for c in ['SB_vs_S', 'B_vs_C']:
    log('biomass', f'   contrast_type {c} (last tp)', b[(b.contrast_type == c) & (b.is_last_timepoint == 1)])

# ============================================================ TASK 2 : variance imputation


def parse_study_dispersion(txt):
    """Returns ('CV', cv_fraction) | ('LSD', value) | (None, nan) from the printed dispersion text."""
    if not isinstance(txt, str):
        return None, np.nan
    m = re.search(r'LSD[^0-9=]*(?:0\.05|5 ?%)?\)?\s*=\s*([0-9]+(?:\.[0-9]+)?)', txt)
    if m:
        return 'LSD', float(m.group(1))
    m = re.search(r'\bCV\b[^0-9]*?(?:=|\(%\)\s*=|%\s*=)?\s*([0-9]+(?:\.[0-9]+)?)', txt)
    if m and 'blank' not in txt.lower().split('cv')[-1][:12]:
        return 'CV', float(m.group(1)) / 100.0
    return None, np.nan


def impute_variance(x, tag):
    x = x.copy()
    x['var_effect_original'] = x['var_effect']
    x['effect_bc_original'] = x['effect_bc']
    # ---- group level (arms) : author SD only
    arms = []
    for s in ('t', 'c'):
        a = pd.DataFrame({'study_id': x.study_id, 'arm_uid': x.tv_ids.map(lambda v: json.loads(v)[0 if s == 't' else 1]),
                          'mean': x['mean_' + s], 'sd': x['sd_' + s], 'n': x['n_' + s],
                          'basis': x['dispersion_basis_raw_' + s], 'rep': x['dispersion_type_reported_raw_' + s],
                          'is_boxplot': x.is_boxplot})
        arms.append(a)
    arms = pd.concat(arms).drop_duplicates('arm_uid')
    own = (arms.basis == 'SOURCE_REPORTED') & arms.sd.notna() & (arms['mean'] > 0) & (arms.is_boxplot == 0)
    arms['cv'] = np.where(own, arms.sd / arms['mean'], np.nan)
    pool = arms[own & (arms.cv > 0)]
    st = pool.groupby('study_id').agg(cv_study=('cv', 'mean'), n_study=('n', 'mean'), k_groups=('cv', 'size'))
    st['n_study'] = st.n_study.fillna(arms.n.median())
    cvbar = float(np.average(st.cv_study, weights=st.n_study))
    n_med = float(arms.n.median())
    summ = dict(table=tag, groups_total=len(arms), groups_with_author_sd=int(own.sum()), studies_with_author_sd=len(st),
                studies_total=x.study_id.nunique(), CV_bar=cvbar, CV_bar_sq=cvbar ** 2, median_n=n_med,
                cv_study_p05=st.cv_study.quantile(.05), cv_study_median=st.cv_study.median(), cv_study_p95=st.cv_study.quantile(.95))
    # ---- per contrast
    for s in ('t', 'c'):
        m, sd, n = x['mean_' + s], x['sd_' + s], x['n_' + s]
        own_s = (x['dispersion_basis_raw_' + s] == 'SOURCE_REPORTED') & sd.notna() & (m > 0) & (x.is_boxplot == 0) & (sd > 0)
        x['n_imp_' + s] = n.fillna(n_med)
        x['n_imputed_' + s] = n.isna().astype(int)
        cv = pd.Series(np.where(own_s, sd / m, np.nan), index=x.index)
        src = pd.Series(np.where(own_s, 'AUTHOR_SD', ''), index=x.index, dtype=object)
        # study-level printed dispersion (ANOVA CV% or LSD) -> study's own spread
        parsed = x['dispersion_type_reported_raw_' + s].map(parse_study_dispersion)
        kind = parsed.map(lambda p: p[0]); val = parsed.map(lambda p: p[1])
        # grand mean of the arms in that study x signature (pooled CV refers to it)
        gm = x.groupby(['study_id', 'signature'])[['mean_t', 'mean_c']].transform('mean').mean(axis=1)
        need = cv.isna()
        mcv = need & (kind == 'CV')
        cv[mcv] = val[mcv] * gm[mcv] / m[mcv]; src[mcv] = 'STUDY_PRINTED_CV_PCT'
        k_arms = x.groupby(['study_id', 'signature']).arm_key_t.transform('nunique') + 1
        nn = x['n_imp_' + s]
        df_err = (k_arms * (nn - 1)).clip(lower=2)
        mlsd = need & (kind == 'LSD')
        sdp = val / (stats.t.ppf(0.975, df_err) * np.sqrt(2.0 / nn))
        cv[mlsd] = sdp[mlsd] / m[mlsd]; src[mlsd] = 'STUDY_PRINTED_LSD'
        rest = cv.isna()
        cv[rest] = cvbar; src[rest] = 'IMPUTED_MEAN_CV'
        x['cv_used_' + s] = cv; x['cv_source_' + s] = src
    x['var_lnrr_imp'] = x.cv_used_t ** 2 / x.n_imp_t + x.cv_used_c ** 2 / x.n_imp_c
    x['var_lnrr_meancv_all'] = cvbar ** 2 / x.n_imp_t + cvbar ** 2 / x.n_imp_c   # Nakagawa "method 1" (CV-bar for every group)
    x['effect_bc_imp'] = x.effect + 0.5 * (x.cv_used_t ** 2 / x.n_imp_t - x.cv_used_c ** 2 / x.n_imp_c)
    x['variance_from_author_sd'] = ((x.cv_source_t == 'AUTHOR_SD') & (x.cv_source_c == 'AUTHOR_SD') &
                                   (x.n_imputed_t == 0) & (x.n_imputed_c == 0)).astype(int)
    fl = []
    for i, r in x.iterrows():
        f = []
        if 'IMPUTED_MEAN_CV' in (r.cv_source_t, r.cv_source_c): f.append('VARIANCE_IMPUTED_MEAN_CV')
        if 'STUDY_PRINTED_CV_PCT' in (r.cv_source_t, r.cv_source_c): f.append('VARIANCE_FROM_STUDY_CV_PCT')
        if 'STUDY_PRINTED_LSD' in (r.cv_source_t, r.cv_source_c): f.append('VARIANCE_FROM_STUDY_LSD')
        if r.n_imputed_t or r.n_imputed_c: f.append('N_IMPUTED_MEDIAN')
        if 'USER_ASSUMED_SE' in r.flag_list: f.append('USER_ASSUMED_SE_NOT_USED_FOR_VARIANCE')
        if 'DEPENDENT_OR_UNKNOWN_ALLOCATION_VARIANCE_UNAVAILABLE' in r.flag_list: f.append('INDEPENDENT_ARMS_ASSUMED_FOR_VARIANCE')
        fl.append(json.dumps(f))
    x['variance_flags'] = fl
    x['variance_status'] = np.select([x.variance_from_author_sd == 1,
                                      x.variance_flags.str.contains('IMPUTED_MEAN_CV')],
                                     ['AUTHOR_SD_SE', 'IMPUTED_MEAN_CV'], 'STUDY_PRINTED_CV_OR_LSD_OR_N_IMPUTED')
    x['w_n'] = x.n_imp_t * x.n_imp_c / (x.n_imp_t + x.n_imp_c)
    summ.update({f'contrasts_{k}': int(v) for k, v in x.variance_status.value_counts().items()})
    summ['contrasts_N_IMPUTED_MEDIAN'] = int(x.variance_flags.str.contains('N_IMPUTED').sum())
    summ['contrasts_STUDY_CV_PCT'] = int(x.variance_flags.str.contains('STUDY_CV_PCT').sum())
    summ['contrasts_STUDY_LSD'] = int(x.variance_flags.str.contains('STUDY_LSD').sum())
    summ['studies_any_imputed'] = x[x.variance_status != 'AUTHOR_SD_SE'].study_id.nunique()
    return x, summ


# CV-bar is estimated on the full pool of each endpoint table (all tiers / timepoints), never on S_vs_C or interactions
y, sy = impute_variance(y, 'yield')
b, sb = impute_variance(b, 'biomass')
pd.DataFrame([sy, sb]).to_csv(RES / 'variance_imputation_summary.csv', index=False)
CVBAR = {'yield': sy['CV_bar'], 'biomass': sb['CV_bar']}

# ============================================================ S_vs_C moderator (meta-regression only)


def attach_svc(x, svc):
    key = svc.assign(k=svc.study_id + '|' + svc.experiment_key + '|' + svc.signature + '|' + svc.arm_key_t)
    key = key.drop_duplicates('k').set_index('k')['effect']
    k = x.study_id + '|' + x.experiment_key + '|' + x.signature + '|' + x.arm_key_c
    v = k.map(key)
    v[x.contrast_type == 'B_vs_C'] = 0.0      # no stress -> no stress-induced reduction
    return v


y['mod_lnrr_stress_SvsC'] = attach_svc(y, y_svc)
b['mod_lnrr_stress_SvsC'] = attach_svc(b, b_svc)

# ============================================================ harmonised + definition features
for x in (y, b):
    h = harmonize(x)
    for c in h.columns:
        x[c] = h[c]
    x['is_B_vs_C'] = (x.contrast_type == 'B_vs_C').astype(int)
    x['stress'] = np.where(x.contrast_type == 'B_vs_C', 'NONE', x.stress_code)
    x['is_terminal'] = x.is_terminal_t
    x['year_num'] = pd.to_numeric(x.year, errors='coerce')

# default-inclusion flags
y['in_default'] = (y.is_boxplot == 0).astype(int)
b['in_default'] = ((b.is_boxplot == 0) & (b.is_last_timepoint == 1)).astype(int)
log('yield', '07 DEFAULT model table (boxplots excluded)', y[y.in_default == 1])
log('biomass', '07 DEFAULT model table (boxplots excluded, last timepoint)', b[b.in_default == 1])
log('yield', '   default rows with author SD/SE variance (no imputation)', y[(y.in_default == 1) & (y.variance_from_author_sd == 1)])
log('biomass', '   default rows with author SD/SE variance (no imputation)', b[(b.in_default == 1) & (b.variance_from_author_sd == 1)])
log('yield', '   default SB_vs_S rows with S_vs_C moderator', y[(y.in_default == 1) & (y.contrast_type == 'SB_vs_S') & y.mod_lnrr_stress_SvsC.notna()])

# ============================================================ write
drop = ['flag_list']
for name, x in [('train_yield', y), ('train_dry_biomass', b),
                ('yield_interactions_SxB_AxB_main', y_inter), ('dry_biomass_interactions_SxB_AxB', b_inter),
                ('yield_S_vs_C_moderator_source', y_svc), ('dry_biomass_S_vs_C_moderator_source', b_svc)]:
    x = x.drop(columns=[c for c in drop if c in x])
    x.to_parquet(OUT / f'{name}.parquet', index=False)
    x.to_csv(OUT / f'{name}.csv', index=False, encoding='utf-8')
pd.DataFrame(flow).to_csv(RES / 'build_flow_counts.csv', index=False)

NEW = {
    'yield_tier': 'Yield definition tier (STRICT/ASSUMED/BROAD/UNIT_UNRESOLVED per export.py rules; EARLY; DRY; OTHER_DEFINITION). Feature, not a filter.',
    'is_dry_yield': '1 if mass_basis == DRY (yield table).',
    'is_early_yield': '1 if yield_scope == EARLY (yield table).',
    'is_boxplot': '1 if flag BOX_CENTRE_ASSUMED_MEAN (box centre assumed to be a mean). Excluded from default model.',
    'is_duplicate': '1 if flag DUPLICATE_EXCLUDED. None in this freeze.',
    'in_default': '1 if the row belongs to the default model table (no boxplot; biomass: last timepoint per group).',
    'sig_no_tp': 'Biomass: measurement signature with the timepoint removed.',
    'tp_group_id': 'Biomass: group of the same contrast measured at several timepoints.',
    'n_timepoints_in_group': 'Biomass: number of timepoints available for the group.',
    'is_last_timepoint': 'Biomass: 1 for the last timepoint of the group (terminal first, then max days).',
    'var_effect_original': 'Sampling variance of lnRR as delivered in the freeze (may include USER_ASSUMED_SE). Untouched.',
    'effect_bc_original': 'Bias-corrected lnRR as delivered in the freeze (only where SD known).',
    'n_imp_t / n_imp_c': 'Group n; missing n replaced by the median n of the endpoint table (flag N_IMPUTED_MEDIAN).',
    'n_imputed_t / n_imputed_c': '1 if n was imputed.',
    'cv_used_t / cv_used_c': 'CV (sd/mean) used for the variance of each group.',
    'cv_source_t / cv_source_c': 'AUTHOR_SD (authors\' SD/SE, SOURCE_REPORTED) | STUDY_PRINTED_CV_PCT (study ANOVA CV%) | STUDY_PRINTED_LSD | IMPUTED_MEAN_CV (pooled CV-bar, NOT reported by authors).',
    'var_lnrr_imp': 'var(lnRR) = CV_t^2/n_t + CV_c^2/n_c with own CV where author SD exists, else study CV%/LSD, else CV-bar (Nakagawa et al. 2023 mixed approach).',
    'var_lnrr_meancv_all': 'var(lnRR) using CV-bar for every group (Nakagawa et al. 2023 method 1), sensitivity only.',
    'effect_bc_imp': 'Bias-corrected lnRR: lnRR + 0.5*(CV_t^2/n_t - CV_c^2/n_c) using cv_used and n_imp.',
    'variance_from_author_sd': '1 if both groups have author SD/SE and reported n (no imputation of any kind).',
    'variance_flags': 'JSON list: VARIANCE_IMPUTED_MEAN_CV, VARIANCE_FROM_STUDY_CV_PCT, VARIANCE_FROM_STUDY_LSD, N_IMPUTED_MEDIAN, USER_ASSUMED_SE_NOT_USED_FOR_VARIANCE, INDEPENDENT_ARMS_ASSUMED_FOR_VARIANCE.',
    'variance_status': 'AUTHOR_SD_SE | IMPUTED_MEAN_CV | STUDY_PRINTED_CV_OR_LSD_OR_N_IMPUTED.',
    'w_n': 'Sample-size weight n_t*n_c/(n_t+n_c) (imputed n where missing).',
    'mod_lnrr_stress_SvsC': 'lnRR of S vs C for the matching stressed control arm (0 for B_vs_C). META-REGRESSION MODERATOR ONLY. Never an ML feature (post-stress outcome).',
    'is_B_vs_C': '1 for contrasts without stress (B vs C).',
    'stress': 'stress_code; NONE for B_vs_C.',
    'is_terminal': 'is_terminal_t.',
    'year_num': 'Publication year as number (descriptive only, not a feature).',
    'h_dujardin': 'Primary biostimulant category after du Jardin (2015): HUMIC_FULVIC, PROTEIN_N, SEAWEED_BOTANICAL, CHITOSAN_BIOPOLYMER, INORGANIC, BENEFICIAL_FUNGI, BENEFICIAL_BACTERIA; MIXTURE if >1; OTHER_NON_DUJARDIN; UNCLASSIFIED. Regex over f_biostimulant_class/bio_code/f_microorganism/f_composition/f_strain.',
    'h_dj_*': 'Multi-hot du Jardin categories (a product can belong to several).',
    'h_dose_class': 'Harmonised dose unit class (CFU, MOLAR_mM, MOLAR_uM, CONC_gL_or_mLL, PER_PLANT_OR_POT, PER_AREA, PER_SOIL_MASS, UNKNOWN, NOT_REPORTED).',
    'h_log10_dose': 'log10 of dose on the canonical scale of its class (mg/L->g/L, uM->mM, 1 % = 10 g/L).',
    'h_dose_rel_study': 'Dose rescaled 0..1 within study and dose class (design only).',
    'h_stress_class': 'Harmonised stress class (NONE, SALINITY, DROUGHT, HEAT, COLD, NUTRIENT, HEAVY_METAL, BIOTIC, ...).',
    'h_stress_intensity': 'Design-based relative stress intensity: salinity NaCl-equivalent mM / 200 (EC dS/m*10; 1 % w/v = 171 mM); drought 1 - FC/100; NONE = 0. Never uses an outcome.',
    'h_stress_rank_study': 'Within-study dense rank of the stress level / max rank (0..1).',
    'h_nacl_equiv_mm': 'NaCl-equivalent concentration (mM), salinity only.',
    'h_crop_group': 'Tomato market group from f_fruit_type/f_cultivar: CHERRY_COCKTAIL, PROCESSING, BEEF_LARGE, ROUND_FRESH_MARKET, UNSPECIFIED.',
    'h_growth_habit': 'DETERMINATE / SEMI_DETERMINATE / INDETERMINATE / UNSPECIFIED.',
    'h_hybrid': 'HYBRID / OP_CULTIVAR_LINE / UNSPECIFIED.',
    'h_system': 'Growing system: FIELD / GREENHOUSE / CHAMBER / SOILLESS / UNSPECIFIED.',
    'h_potted': '1 if grown in pots/bags/containers.',
    'h_route': 'Application route: FOLIAR / SEED / ROOT_DIP / FERTIGATION / SOIL_SUBSTRATE / UNSPECIFIED.',
    'h_n_applications': 'Number of applications (numeric f_n_applications).',
}
pd.DataFrame([{'column': k, 'description': v} for k, v in NEW.items()]).to_csv(OUT / 'new_columns_dictionary.csv', index=False, encoding='utf-8')
print(pd.DataFrame(flow).to_string())
print(pd.DataFrame([sy, sb]).T.to_string())
