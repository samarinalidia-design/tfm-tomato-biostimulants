"""V5 step 1: source-verified corrections + TRAIN and TEST tables for FRUIT_YIELD and DRY_BIOMASS,
built with one set of definitions, dictionaries, units and selection rules.

Inputs (read only):
  TRAIN  data/raw/contrast_candidates.parquet  (= DATA_FREEZE_20261113T112939135807Z, SHA-256 verified copy)
  TEST   TFM_TEST_2024_2026_Agent_System/exports/DATA_FREEZE_20261118T105532769144Z/contrast_candidates.parquet
Learnt quantities (CV-bar and median n for variance imputation) are estimated on TRAIN only and applied to TEST.
Outputs: v5/data/*.parquet|csv, v5/data/corrections_register.csv, v5/results/build_flow_v5.csv,
         v5/results/variance_imputation_v5.csv, v5/results/overlap_train_test.csv
"""
import sys, re, json, hashlib, pathlib
import numpy as np
import pandas as pd
from scipy import stats

V5 = pathlib.Path(__file__).resolve().parents[1]
ROOT = V5.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import harmonize as H

MASTER = ROOT.parent
TRAIN_FREEZE = MASTER / 'TFM_A399_Agent_System_v2_2_2026-10-19/TFM_AGENT_SYSTEM_v2_2/exports/DATA_FREEZE_20261113T112939135807Z'
TEST_FREEZE = MASTER / 'TFM_TEST_2024_2026_Agent_System/exports/DATA_FREEZE_20261118T105532769144Z'
OUT, RES = V5 / 'data', V5 / 'results'
OUT.mkdir(parents=True, exist_ok=True); RES.mkdir(parents=True, exist_ok=True)
REG = []          # corrections register
FLOW = []


def reg(study, scope, field, old, new, evidence, status='CONFIRMED_FROM_SOURCE'):
    REG.append(dict(study_id=study, scope=scope, field=field, old_value=str(old), new_value=str(new), evidence=evidence, status=status))


def log(role, table, step, df, note=''):
    FLOW.append(dict(role=role, table=table, step=step, contrasts=len(df), studies=df.study_id.nunique(),
                     clusters=df.dependency_cluster_id.nunique(), note=note))


def add_flag(flags, f):
    L = json.loads(flags) if isinstance(flags, str) and flags else []
    if f not in L:
        L.append(f)
    return json.dumps(L)


# ===================================================================== 1. corrections (raw contrast level)
def fix_size_fractions(d, arm_means):
    """Fruit-size fractions (Small/Medium/Large) stored as separate 'TOTAL' contrasts.
    Rebuilt as ONE total-yield contrast per arm pair: mean = sum of the fraction means of that arm.
    SDs are NOT summed (none reported; covariance between fractions unknown) -> variance imputed downstream."""
    m = d.endpoint.eq('FRUIT_YIELD') & d.signature.str.contains('FRUIT_SIZE_CLASS', na=False)
    if not m.any():
        return d
    frac = d[m].copy()
    frac['sig0'] = frac.signature.str.replace(r';context=FRUIT_SIZE_CLASS[^;]*', ';context=SUM_OF_SIZE_FRACTIONS', regex=True)
    frac['n_arms'] = frac.tv_ids.map(lambda v: len(json.loads(v)))
    new = []
    for key, g in frac.groupby(['study_id', 'experiment_key', 'contrast_type', 'arm_key_t', 'arm_key_c', 'sig0', 'n_arms']):
        study, ek, ct, at, ac, sig0, na = key
        r = g.iloc[0].copy()
        ids = np.array([json.loads(v) for v in g.tv_ids])            # fractions x arms
        sums = [sum(arm_means[i] for i in ids[:, j]) for j in range(na)]
        if na == 2:
            eff = np.log(sums[0] / sums[1])
            r['mean_t'] = g.mean_t.sum(); r['mean_c'] = g.mean_c.sum()
        else:                                                         # AxB: ln(AB) - ln(C)... verified formula
            eff = np.log(sums[0]) - np.log(sums[2]) - np.log(sums[3]) + np.log(sums[1])
            r['mean_t'] = np.nan; r['mean_c'] = np.nan
        r['effect'] = eff
        r['effect_bc'] = np.nan; r['var_effect'] = np.nan; r['se_effect'] = np.nan
        r['ci95_lower'] = np.nan; r['ci95_upper'] = np.nan; r['pct_effect'] = 100 * (np.exp(eff) - 1)
        r['sd_t'] = np.nan; r['sd_c'] = np.nan
        for s in ('t', 'c'):
            r['dispersion_basis_raw_' + s] = 'NOT_REPORTED'; r['dispersion_type_reported_raw_' + s] = None
        r['tv_ids'] = json.dumps([f'SUMFRAC:{study}:' + '+'.join(str(i) for i in ids[:, j]) for j in range(na)])
        r['signature'] = sig0.replace('yield_scope=UNSPECIFIED', 'yield_scope=TOTAL')
        r['yield_scope'] = 'TOTAL'
        r['shared_control_id'] = str(r['shared_control_id']).split('|FRUIT_YIELD')[0] + '|TOTAL_SUM_OF_SIZE_FRACTIONS'
        r['flags'] = add_flag(r['flags'], 'TOTAL_SUMMED_FROM_SIZE_FRACTIONS_SD_NOT_SUMMED')
        r['contrast_id'] = 'V5_' + hashlib.sha1('|'.join(map(str, key)).encode()).hexdigest()[:20]
        r['v5_fractions_summed'] = len(g)
        new.append(r)
        reg(study, f'{ct} {at} vs {ac}', 'size fractions -> total', f'{len(g)} contrasts (fractions labelled TOTAL/UNSPECIFIED)',
            f'1 contrast, lnRR={eff:.4f}, mean_t={r["mean_t"]}, mean_c={r["mean_c"]}',
            'Source table: total fruit yield (kg/10 plants) given by fruit size Small/Medium/Large; fractions are parts of the total. '
            'Total = sum of fraction means (same plants). SD not summed (not reported; fraction covariance unknown).')
    out = pd.concat([d[~m], pd.DataFrame(new)], ignore_index=True)
    return out


def apply_corrections(d, role, arm_means):
    d = d.copy()
    d['v5_stress_declared'] = None
    d['v5_correction'] = ''
    if role == 'TRAIN':
        d = fix_size_fractions(d, arm_means)
        # --- 112: author-declared saline soil (EC 1.2 mS/cm) is below the tomato threshold (~2.5 dS/m) and the control arm is
        #     numerically shared with D_8a246bc169c4b812 (non-stressed control, V2 audit). -> no stress background; flagged.
        m = (d.study_id == '112') & (d.contrast_type == 'SB_vs_S')
        for i in d.index[m]:
            d.at[i, 'flags'] = add_flag(d.at[i, 'flags'], 'STRESS_RECLASSIFIED_NONE_DISPUTED')
        d.loc[m, 'v5_stress_declared'] = 'SALINITY_AUTHOR_DECLARED_SOIL_EC_1.2_mS_cm'
        d.loc[m, 'contrast_type'] = 'B_vs_C'; d.loc[m, 'stress_code'] = 'NONE'; d.loc[m, 'v5_correction'] += 'STRESS_DISPUTED;'
        reg('112', 'SB_vs_S yield', 'contrast_type / stress', 'SB_vs_S, SAL_FIELD_BG_EC1.2', 'B_vs_C, NONE (flag STRESS_RECLASSIFIED_NONE_DISPUTED)',
            'p.2: soil EC ~1.2 mS/cm called saline by authors; below tomato salinity threshold (~2.5 dS/m). Control vector 6.67/23.55/20.87 '
            'kg/10 plants identical to the non-stressed control of D_8a246bc169c4b812 (study_relations SHARED_CONTROLS, CONFIRMED); the same '
            'physical control cannot be stressed in one record and unstressed in the other. Same rule as V2 audit (rejected proposal for D_8a246...).',
            'DISPUTED_FLAGGED')
        # --- 717: year binding. Two seasons (2018, 2019) recorded as one experiment E1; season text '2018;2019', year = publication.
        m = d.study_id == '717'
        yr = d.loc[m, 'timepoint_key'].astype(str).str.extract(r'Y(20\d\d)', expand=False)
        d.loc[m & yr.reindex(d.index).notna(), 'experiment_key'] = 'E1_' + yr.dropna()
        d.loc[m, 'v5_measurement_year'] = pd.to_numeric(yr, errors='coerce')
        reg('717', 'all endpoints', 'experiment_key / measurement year', 'E1, season 2018;2019, year 2021 (publication)',
            'E1_2018 / E1_2019; v5_measurement_year from timepoint (Y2018/Y2019)',
            'Table 3 p.7 (journal p.173): separate columns for 2018 and 2019; values verified against the PDF view (all 54 yield rows match the year columns). '
            'Each season is its own experiment level; publication year 2021 is not the measurement year.')
        # green (unripe) fruit yield is a fraction, not total/marketable yield
        m = (d.study_id == '717') & d.endpoint.eq('FRUIT_YIELD') & d.locator_t.astype(str).str.contains('Green yield')
        d.loc[m, 'yield_scope'] = 'FRACTION_GREEN_UNRIPE'
        reg('717', f'{int(m.sum())} yield contrasts', 'yield_scope', 'UNSPECIFIED', 'FRACTION_GREEN_UNRIPE (excluded from yield tables)',
            "Table 3 column 'Green yield t/ha' = unripe-fruit fraction; Total = marketable + green + diseased.")
        # other multi-year timepoints: measurement year attached per row
        for sid in ['D_068b862524c2c34a', 'D_0e4b363eeb15d524']:
            mm = d.study_id == sid
            yy = pd.to_numeric(d.loc[mm, 'timepoint_key'].astype(str).str.extract(r'(20\d\d)', expand=False), errors='coerce')
            d.loc[mm, 'v5_measurement_year'] = yy
            reg(sid, 'all endpoints', 'v5_measurement_year', 'season text only', 'year from timepoint key', 'timepoint key carries the harvest year')
        # --- 41: full-irrigation arms coded as stress (WW_SWC35, PRESTRESS_FC) -> no-stress contrasts
        m = (d.study_id == '41') & d.stress_code.isin(['WW_SWC35', 'PRESTRESS_FC']) & (d.contrast_type == 'SB_vs_S')
        reg('41', f'{int(m.sum())} SB_vs_S', 'contrast_type / stress', 'SB_vs_S (WW_SWC35 / PRESTRESS_FC)', 'B_vs_C, NONE',
            "db_arms: 'I1 irrigated to 35% SWC (authors' full irrigation reference)' and 'No deficit; irrigated to field capacity': no stress.")
        d.loc[m, 'contrast_type'] = 'B_vs_C'; d.loc[m, 'stress_code'] = 'NONE'; d.loc[m, 'v5_correction'] += 'NO_STRESS_RECODED;'
    if 'v5_measurement_year' not in d:
        d['v5_measurement_year'] = np.nan
    return d


# ===================================================================== 2. stress classes (fixed rules, combined, explicit overrides)
FAMILY_RULES = [
    ('SALINITY', r'salin|nacl|\bsalt|\bec\d|ec_?\d|sodic|seawater'),
    ('DROUGHT', r'drought|water deficit|deficit irrig|\bwd\b|wd_|\bfc\b|\d+fc|fc\d|water stress|withhold|rainfed|\bdi_|\bdi\d|\bdi\b|osmotic|peg|\bws_|swc|whc|etc\b|\d+etc|iwcpe|pan_evap|cwr\b|\bsm\d|_sm_|smp_m'),
    ('HEAT', r'heat|high temp|(?<![a-z])ht(?![a-z])|temp_3[5-9]c|temp_4\dc'),
    ('COLD', r'cold|chill|low temp|(?<![a-z])lt(?![a-z])|frost|temp_20c'),
    ('NUTRIENT', r'deficien|low n\b|pdef|p_lim|\bp def|low p\b|nitrogen def|potassium def|fert_red|n_red|nutrient (?:def|stress|limit)'),
    ('HEAVY_METAL', r'cadmium|\bcd\d|\bcd\b|lead|\bpb\b|arsenic|chromium|nickel|copper|heavy metal|boron tox|b_tox|alumin|tailings'),
    ('CHEMICAL_TOXICITY', r'_np_|nanopart|benzoic|\bs_ba|herbicid|pesticid'),
    ('BIOTIC', r'biotic|nematode|meloidogyne|rkn|minc|fusarium|oxysporum|ralstonia|botrytis|phytophthora|rhizoctonia|rsolani|\brs_|alternaria|asolani|solani|blight|rolfsii|pathogen|virus|tylcv|pythium|cmm|clavibacter|xanthomonas|syringae|insect|whitefly|tuta|larva|replant|disease|pinf'),
    ('ALKALINITY_CALCAREOUS', r'alkalin|calcare|bicarbonate|high ph'),
    ('LIGHT_UV_OZONE', r'shade|low light|\buv\b|ozone'),
    ('FLOOD_HYPOXIA', r'flood|waterlog|hypox|smp_0kpa'),
]
OVERRIDE = {   # explicit, documented decisions (stress_code -> families)
    'WASTEWATER_IRRIGATION': ['SALINITY', 'HEAVY_METAL'],     # EC 2.86 dS/m + Cd/Ni/Cu (Table 1)
    'MWW_1.5L_weekly': ['SALINITY', 'HEAVY_METAL'],           # EC 2.69 dS/m municipal wastewater (Table 2)
    'FERTIG_SENSOR_MODULATED': ['OTHER_MANAGEMENT'],          # sensor-modulated fertigation, not an imposed stress
}


def stress_families(code, text):
    c = str(code).lower()
    if c == 'none':
        return []
    if code in OVERRIDE:
        return OVERRIDE[code]
    fam = [n for n, p in FAMILY_RULES if re.search(p, c)]
    if not fam:
        fam = [n for n, p in FAMILY_RULES if re.search(p, str(text).lower())][:1]
    return fam or ['OTHER']


def stress_v5(df):
    fams = [stress_families(c, t) for c, t in zip(df.stress_code, df.get('f_stress_type', pd.Series('', index=df.index)).astype(str))]
    cls = ['NONE' if not f else (f[0] if len(f) == 1 else 'COMBINED') for f in fams]
    return pd.Series(cls, index=df.index), pd.Series(['+'.join(f) if f else 'NONE' for f in fams], index=df.index)


def hybrid_v5(df):
    """HYBRID only with explicit hybrid/F1 evidence; OP only with explicit open-pollinated/landrace/heirloom/inbred evidence;
    otherwise UNSPECIFIED (unknown is never turned into 'not hybrid')."""
    gt = H._txt(df, ['f_genotype_type', 'f_cultivar'])
    return pd.Series(np.select([gt.str.contains(r'hybrid|\bf1\b|\bf 1\b'),
                                gt.str.contains(r'open[- ]?pollinat|\bop\b|landrace|heirloom|inbred|wild|accession|traditional')],
                               ['HYBRID', 'OP_CULTIVAR_LINE'], 'UNSPECIFIED'), index=df.index)


# ===================================================================== 3. selection rules (identical for TRAIN and TEST)
def has_flag(df, f):
    return df['flags'].map(lambda s: any(x == f or x.startswith(f + ':') for x in (json.loads(s) if isinstance(s, str) and s else [])))


def base_pool(d, endpoint, role, tag):
    x = d[d.endpoint == endpoint].copy(); log(role, tag, '00 endpoint', x)
    x = x[x.dataset_role == ('TRAIN_DEV' if role == 'TRAIN' else 'EXTERNAL_TEST')]; log(role, tag, '01 dataset_role', x)
    x = x[~x.exclusion_reason.fillna('').str.contains('TEMPORAL')]; log(role, tag, '02 drop temporal ineligible', x)
    x = x[(x.effect_metric == 'lnRR') & x.effect.notna() & ((x.mean_t > 0) & (x.mean_c > 0) | x.contrast_type.isin(['AxB', 'SxB']))]
    log(role, tag, '03 lnRR computable', x)
    x = x[~has_flag(x, 'DUPLICATE_EXCLUDED')]; log(role, tag, '04 drop DUPLICATE_EXCLUDED', x)
    x['is_boxplot'] = has_flag(x, 'BOX_CENTRE_ASSUMED_MEAN').astype(int)
    return x


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


def select_tables(d, role):
    y = base_pool(d, 'FRUIT_YIELD', role, 'yield')
    y_inter = y[y.contrast_type.isin(['SxB', 'AxB', 'B_MAIN_EFFECT'])].copy()
    y_svc = y[y.contrast_type == 'S_vs_C'].copy()
    y = y[y.contrast_type.isin(['SB_vs_S', 'B_vs_C'])].copy(); log(role, 'yield', '05 SB_vs_S + B_vs_C', y)
    y = y[y.yield_scope.fillna('') != 'NON_MARKETABLE']; log(role, 'yield', '06 drop NON_MARKETABLE', y)
    y = y[~y.yield_scope.fillna('').str.startswith('FRACTION_')]; log(role, 'yield', '07 drop yield fractions (green/unripe)', y)
    y['yield_tier'] = y.apply(yield_tier, axis=1)
    y['is_dry_yield'] = (y.mass_basis == 'DRY').astype(int)
    y['is_early_yield'] = (y.yield_scope == 'EARLY').astype(int)
    b = base_pool(d, 'DRY_BIOMASS', role, 'biomass')
    b_inter = b[b.contrast_type.isin(['SxB', 'AxB'])].copy()
    b_svc = b[b.contrast_type == 'S_vs_C'].copy()
    b = b[b.contrast_type.isin(['SB_vs_S', 'B_vs_C'])].copy(); log(role, 'biomass', '05 SB_vs_S + B_vs_C', b)
    b = b[b.organ_scope.isin(['SHOOT', 'WHOLE_PLANT'])]; log(role, 'biomass', '06 organ SHOOT/WHOLE_PLANT', b)
    b_inter = b_inter[b_inter.organ_scope.isin(['SHOOT', 'WHOLE_PLANT'])]
    b_svc = b_svc[b_svc.organ_scope.isin(['SHOOT', 'WHOLE_PLANT'])]
    b['sig_no_tp'] = b.signature.str.replace(r';tp=[^;]*', '', regex=True)
    b['tp_group_id'] = b[['study_id', 'experiment_key', 'arm_key_t', 'arm_key_c', 'organ_scope', 'sig_no_tp']].astype(str).agg('|'.join, axis=1)
    b['_o'] = b.timepoint_days.fillna(-1)
    b = b.sort_values(['tp_group_id', 'is_terminal_t', '_o', 'timepoint_key']).drop(columns='_o')
    b['n_timepoints_in_group'] = b.groupby('tp_group_id').contrast_id.transform('size')
    b['is_last_timepoint'] = (~b.duplicated('tp_group_id', keep='last')).astype(int)
    return y, y_inter, y_svc, b, b_inter, b_svc


# ===================================================================== 4. variance imputation (Nakagawa et al. 2023), CV-bar from TRAIN
def parse_study_dispersion(txt):
    if not isinstance(txt, str):
        return None, np.nan
    m = re.search(r'LSD[^0-9=]*(?:0\.05|5 ?%)?\)?\s*=\s*([0-9]+(?:\.[0-9]+)?)', txt)
    if m:
        return 'LSD', float(m.group(1))
    m = re.search(r'\bCV\b[^0-9]*?(?:=|\(%\)\s*=|%\s*=)?\s*([0-9]+(?:\.[0-9]+)?)', txt)
    if m and 'blank' not in txt.lower().split('cv')[-1][:12]:
        return 'CV', float(m.group(1)) / 100.0
    return None, np.nan


def arm_table(x):
    arms = []
    for s in ('t', 'c'):
        arms.append(pd.DataFrame({'study_id': x.study_id, 'arm_uid': x.tv_ids.map(lambda v: str(json.loads(v)[0 if s == 't' else 1])),
                                  'mean': x['mean_' + s], 'sd': x['sd_' + s], 'n': x['n_' + s],
                                  'basis': x['dispersion_basis_raw_' + s], 'is_boxplot': x.is_boxplot}))
    return pd.concat(arms).drop_duplicates('arm_uid')


def learn_cvbar(x):
    arms = arm_table(x)
    own = (arms.basis == 'SOURCE_REPORTED') & arms.sd.notna() & (arms['mean'] > 0) & (arms.is_boxplot == 0)
    arms['cv'] = np.where(own, arms.sd / arms['mean'], np.nan)
    pool = arms[own & (arms.cv > 0)]
    st = pool.groupby('study_id').agg(cv_study=('cv', 'mean'), n_study=('n', 'mean'))
    st['n_study'] = st.n_study.fillna(arms.n.median())
    return dict(CV_bar=float(np.average(st.cv_study, weights=st.n_study)), median_n=float(arms.n.median()),
                groups_with_author_sd=int(own.sum()), studies_with_author_sd=len(st), groups_total=len(arms))


def impute_variance(x, P):
    x = x.copy(); cvbar, n_med = P['CV_bar'], P['median_n']
    x['var_effect_original'] = x['var_effect']; x['effect_bc_original'] = x['effect_bc']
    for s in ('t', 'c'):
        m, sd, n = x['mean_' + s], x['sd_' + s], x['n_' + s]
        own_s = (x['dispersion_basis_raw_' + s] == 'SOURCE_REPORTED') & sd.notna() & (m > 0) & (x.is_boxplot == 0) & (sd > 0)
        x['n_imp_' + s] = n.fillna(n_med); x['n_imputed_' + s] = n.isna().astype(int)
        cv = pd.Series(np.where(own_s, sd / m, np.nan), index=x.index)
        src = pd.Series(np.where(own_s, 'AUTHOR_SD', ''), index=x.index, dtype=object)
        parsed = x['dispersion_type_reported_raw_' + s].map(parse_study_dispersion)
        kind = parsed.map(lambda p: p[0]); val = parsed.map(lambda p: p[1])
        gm = x.groupby(['study_id', 'signature'])[['mean_t', 'mean_c']].transform('mean').mean(axis=1)
        need = cv.isna()
        mcv = need & (kind == 'CV'); cv[mcv] = val[mcv] * gm[mcv] / m[mcv]; src[mcv] = 'STUDY_PRINTED_CV_PCT'
        k_arms = x.groupby(['study_id', 'signature']).arm_key_t.transform('nunique') + 1
        nn = x['n_imp_' + s]; df_err = (k_arms * (nn - 1)).clip(lower=2)
        mlsd = need & (kind == 'LSD')
        sdp = val / (stats.t.ppf(0.975, df_err) * np.sqrt(2.0 / nn))
        cv[mlsd] = sdp[mlsd] / m[mlsd]; src[mlsd] = 'STUDY_PRINTED_LSD'
        rest = cv.isna(); cv[rest] = cvbar; src[rest] = 'IMPUTED_MEAN_CV'
        x['cv_used_' + s] = cv; x['cv_source_' + s] = src
    x['var_lnrr_imp'] = x.cv_used_t ** 2 / x.n_imp_t + x.cv_used_c ** 2 / x.n_imp_c
    x['var_lnrr_meancv_all'] = cvbar ** 2 / x.n_imp_t + cvbar ** 2 / x.n_imp_c
    x['effect_bc_imp'] = x.effect + 0.5 * (x.cv_used_t ** 2 / x.n_imp_t - x.cv_used_c ** 2 / x.n_imp_c)
    x['variance_from_author_sd'] = ((x.cv_source_t == 'AUTHOR_SD') & (x.cv_source_c == 'AUTHOR_SD') & (x.n_imputed_t == 0) & (x.n_imputed_c == 0)).astype(int)
    x['variance_status'] = np.select([x.variance_from_author_sd == 1, (x.cv_source_t == 'IMPUTED_MEAN_CV') | (x.cv_source_c == 'IMPUTED_MEAN_CV')],
                                     ['AUTHOR_SD_SE', 'IMPUTED_MEAN_CV_NOT_AUTHOR_REPORTED'], 'STUDY_PRINTED_CV_OR_LSD_OR_N_IMPUTED')
    x['w_n'] = x.n_imp_t * x.n_imp_c / (x.n_imp_t + x.n_imp_c)
    return x


def attach_svc(x, svc):
    key = svc.assign(k=svc.study_id + '|' + svc.experiment_key + '|' + svc.signature + '|' + svc.arm_key_t).drop_duplicates('k').set_index('k')['effect']
    v = (x.study_id + '|' + x.experiment_key + '|' + x.signature + '|' + x.arm_key_c).map(key)
    v[x.contrast_type == 'B_vs_C'] = 0.0
    return v


# ===================================================================== 5. feature layers v2/v3 (functions reused from 07/11)
def load_v2_module(freeze):
    src = (ROOT / 'scripts/07_features_v2.py').read_text(encoding='utf-8').split('\nAUDIT = []')[0]
    ns = {'__file__': str(ROOT / 'scripts/07_features_v2.py'), '__name__': 'v2'}
    exec(compile(src, '07_features_v2', 'exec'), ns)
    ns['ARMS'] = pd.read_parquet(freeze / 'db_arms.parquet'); ns['MOD'] = pd.read_parquet(freeze / 'db_moderators.parquet')
    return ns


def features(x, freeze, endpoint):
    h = H.harmonize(x)
    for c in h.columns:
        x[c] = h[c].values
    x['h_stress_class'], x['h_stress_families'] = stress_v5(x)
    x['h_hybrid'] = hybrid_v5(x)
    x['is_B_vs_C'] = (x.contrast_type == 'B_vs_C').astype(int)
    x['stress'] = np.where(x.contrast_type == 'B_vs_C', 'NONE', x.stress_code)
    x['is_terminal'] = x.is_terminal_t
    v2 = load_v2_module(freeze)
    out = v2['dujardin_v2'](x).join(v2['stress_v2'](x))
    none = x.h_stress_class == 'NONE'
    out['h2_application_phase'] = v2['phase'](x.f_application_stage)
    out['h2_stress_onset_phase'] = v2['phase'](x.f_stress_onset_stage, none_mask=none)
    out['h2_substrate_type'], out['h2_soil_ec_dsm'] = v2['substrate'](x)
    out['h2_plant_density_m2'], out['h2_density_source'], out['h2_density_status'] = v2['density'](x)
    if endpoint == 'yield':
        out['h2_yield_scope'], out['h2_harvest_window'], out['h2_definition_refined_from_locator'] = v2['refine_definitions'](x)
    for c in out.columns:
        x[c] = out[c].values
    import importlib.util
    spec = importlib.util.spec_from_file_location('f3', ROOT / 'scripts/11_features_v3.py')
    f3 = importlib.util.module_from_spec(spec); spec.loader.exec_module(f3)
    x = f3.build(x)
    # v5 fixes on top of v3
    x['h3_hybrid'] = x.h_hybrid.map({'HYBRID': 1.0, 'OP_CULTIVAR_LINE': 0.0})          # unknown -> NaN (not 0)
    yr = pd.to_numeric(x.get('v5_measurement_year'), errors='coerce')
    x['h3_experiment_year'] = yr.fillna(x.h3_experiment_year)
    x['h3_experiment_year_source'] = np.where(yr.notna(), 'TIMEPOINT_KEY', np.where(x.h3_experiment_year.notna(), 'SEASON_TEXT', 'MISSING'))
    x['h3_stress_combined'] = (x.h_stress_class == 'COMBINED').astype(int)
    x['h3_cultivar_key'] = x.h3_cultivar_key.replace({'': 'UNSPECIFIED'}).fillna('UNSPECIFIED')
    # endpoint-generic identifiers
    x['exp_uid'] = x.study_id + '|' + x.experiment_key
    return x


# ===================================================================== main
def tv_means(freeze):
    av = pd.read_parquet(freeze / 'arm_values_verified.parquet', columns=['tv_id', 'mean'])
    return av.set_index('tv_id')['mean'].to_dict()


def main():
    tr_raw = pd.read_parquet(ROOT / 'data/raw/contrast_candidates.parquet')
    te_raw = pd.read_parquet(TEST_FREEZE / 'contrast_candidates.parquet').reindex(columns=list(tr_raw.columns) +
                                                                                   ['first_publication_date'])
    tr = apply_corrections(tr_raw, 'TRAIN', tv_means(TRAIN_FREEZE))
    te = apply_corrections(te_raw, 'TEST', tv_means(TEST_FREEZE))
    tables = {}
    for role, d, freeze in [('TRAIN', tr, TRAIN_FREEZE), ('TEST', te, TEST_FREEZE)]:
        tables[role] = select_tables(d, role)
    P = {'yield': learn_cvbar(tables['TRAIN'][0]), 'biomass': learn_cvbar(tables['TRAIN'][3])}
    pd.DataFrame([dict(table=k, **v, learnt_on='TRAIN only') for k, v in P.items()]).to_csv(RES / 'variance_imputation_v5.csv', index=False)
    for role, freeze in [('TRAIN', TRAIN_FREEZE), ('TEST', TEST_FREEZE)]:
        y, y_inter, y_svc, b, b_inter, b_svc = tables[role]
        y = impute_variance(y, P['yield']); b = impute_variance(b, P['biomass'])
        y['mod_lnrr_stress_SvsC'] = attach_svc(y, y_svc); b['mod_lnrr_stress_SvsC'] = attach_svc(b, b_svc)
        y = features(y, freeze, 'yield'); b = features(b, freeze, 'biomass')
        y['in_default'] = (y.is_boxplot == 0).astype(int)
        b['in_default'] = ((b.is_boxplot == 0) & (b.is_last_timepoint == 1)).astype(int)
        log(role, 'yield', '08 DEFAULT (no boxplot)', y[y.in_default == 1])
        log(role, 'biomass', '08 DEFAULT (no boxplot, last timepoint)', b[b.in_default == 1])
        for x in (y_inter, y_svc, b_inter, b_svc):
            hs = stress_v5(x); x['h_stress_class'], x['h_stress_families'] = hs[0].values, hs[1].values
            hd = H.dujardin(x)[0]; x['h_dujardin'] = hd.values
        tag = role.lower()
        for name, x in [(f'{tag}_yield', y), (f'{tag}_dry_biomass', b), (f'{tag}_yield_interactions', y_inter),
                        (f'{tag}_dry_biomass_interactions', b_inter), (f'{tag}_yield_SvsC', y_svc), (f'{tag}_dry_biomass_SvsC', b_svc)]:
            x = x.copy()
            x['dataset_role_v5'] = role
            x.to_parquet(OUT / f'{name}.parquet', index=False)
            x.drop(columns=[c for c in ['h3_text_all'] if c in x]).to_csv(OUT / f'{name}.csv', index=False, encoding='utf-8')
    pd.DataFrame(REG).to_csv(OUT / 'corrections_register.csv', index=False, encoding='utf-8')
    pd.DataFrame(FLOW).to_csv(RES / 'build_flow_v5.csv', index=False)
    # overlap checks
    st_tr = pd.read_parquet(TRAIN_FREEZE / 'db_studies.parquet'); st_te = pd.read_parquet(TEST_FREEZE / 'db_studies.parquet')
    norm = lambda s: s.astype(str).str.lower().str.replace(r'[^a-z0-9]', '', regex=True)
    ov = []
    ytr, yte = pd.read_parquet(OUT / 'train_yield.parquet'), pd.read_parquet(OUT / 'test_yield.parquet')
    btr, bte = pd.read_parquet(OUT / 'train_dry_biomass.parquet'), pd.read_parquet(OUT / 'test_dry_biomass.parquet')
    s_tr = set(ytr.study_id) | set(btr.study_id); s_te = set(yte.study_id) | set(bte.study_id)
    c_tr = set(ytr.dependency_cluster_id) | set(btr.dependency_cluster_id); c_te = set(yte.dependency_cluster_id) | set(bte.dependency_cluster_id)
    doi_tr = set(norm(st_tr[st_tr.study_id.isin(s_tr)].doi)) - {'', 'none', 'nan'}
    doi_te = set(norm(st_te[st_te.study_id.isin(s_te)].doi)) - {'', 'none', 'nan'}
    ti_tr = set(norm(st_tr[st_tr.study_id.isin(s_tr)].title)); ti_te = set(norm(st_te[st_te.study_id.isin(s_te)].title))
    ov.append(dict(check='study_id overlap', n=len(s_tr & s_te), items=';'.join(sorted(s_tr & s_te))))
    ov.append(dict(check='dependency_cluster_id overlap', n=len(c_tr & c_te), items=';'.join(sorted(c_tr & c_te))))
    ov.append(dict(check='DOI overlap', n=len(doi_tr & doi_te), items=';'.join(sorted(doi_tr & doi_te))))
    ov.append(dict(check='normalised title overlap', n=len(ti_tr & ti_te), items=';'.join(sorted(ti_tr & ti_te))[:500]))
    ov.append(dict(check='TEST relations to TRAIN studies (study_relations)', n=0, items=''))
    rel = pd.read_parquet(TEST_FREEZE / 'db_study_relations.parquet') if (TEST_FREEZE / 'db_study_relations.parquet').exists() else pd.DataFrame()
    if len(rel):
        hit = rel[rel.study_a.isin(s_tr) | rel.study_b.isin(s_tr)]
        ov[-1].update(n=len(hit), items=';'.join(hit.study_a + '~' + hit.study_b))
    pd.DataFrame(ov).to_csv(RES / 'overlap_train_test.csv', index=False)
    print(pd.DataFrame(FLOW).to_string()); print(pd.DataFrame(ov).to_string()); print(P)


if __name__ == '__main__':
    main()
