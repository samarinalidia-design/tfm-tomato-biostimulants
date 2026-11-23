"""V6 database corrections (2026-11-22).

Input (read-only):
  05_analysis_train_expansion_v5/v5/data/{train,test}_{yield,dry_biomass}.parquet   (V5 analysis tables)
  03_data_freeze/<train|test freeze>/db_moderators.parquet, db_arms.parquet       (frozen databases)
Output:
  06_database_corrections_v6/data/{train,test}_{yield,dry_biomass}_V6.parquet/.csv
  06_database_corrections_v6/data/corrections_register_V6.csv   (every changed cell: old -> new, rule, evidence)
  06_database_corrections_v6/data/study_audit_corrections_V6.csv (source-checked corrections of single studies)
  06_database_corrections_v6/results/*.csv, summary_V6.json

Three kinds of change:
  A. Source-checked corrections of single studies (TRAIN). Each was checked in the original full-text PDF
     on 2026-11-22; the page is given in `evidence`.
  B. Rule-based corrections applied to TRAIN and TEST alike:
     B1 restore the V3.1 contrast fixes lost in V5 (vehicle / fertiliser-only "biostimulants", re-based controls);
     B2 parse numeric moderators that the frozen DB stores as text ("25 +/- 5", "26-28", weeks, plants/ha, DMS)
        and fill V5 features that were missing; never overwrite a non-missing V5 value;
     B3 one primary contrast per arm pair and harvest (TOTAL > UNSPECIFIED > MARKETABLE ...);
     B4 realised stress (from the study's own unstressed control) and target-reliability flags;
     B5 rootstock / grafting from the arm genotype text;
     B6 a single plant-age reference for the measurement time point (dry biomass);
     B7 N fertilisation in kg/ha parsed from the fertilisation text.
  C. New default sets: in_default_v6 (B1 + B3 applied) and in_quality_core_v6 (no reliability flag).

Nothing is invented: a value that cannot be parsed stays missing and gets a status.
"""
from __future__ import annotations
import json, math, re, pathlib, datetime
import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parents[2]
V5D = REPO / '05_analysis_train_expansion_v5' / 'v5' / 'data'
FRZ = {'train': REPO / '03_data_freeze' / 'train_dev_DATA_FREEZE_20261113T112939135807Z',
       'test': REPO / '03_data_freeze' / 'external_test_DATA_FREEZE_20261118T105532769144Z'}
OUT = REPO / '06_database_corrections_v6'
DATA, RES = OUT / 'data', OUT / 'results'
DATA.mkdir(parents=True, exist_ok=True); RES.mkdir(parents=True, exist_ok=True)

REG: list[dict] = []          # corrections register (cell level)


def log(split, endpoint, row, field, old, new, rule, evidence=''):
    def j(v):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ''
        return str(v)
    if j(old) == j(new):
        return
    REG.append({'split': split, 'endpoint': endpoint, 'contrast_id': row.get('contrast_id', ''),
                'study_id': row.get('study_id', ''), 'experiment_key': row.get('experiment_key', ''),
                'arm_key_t': row.get('arm_key_t', ''), 'arm_key_c': row.get('arm_key_c', ''),
                'field': field, 'old_value': j(old), 'new_value': j(new), 'rule': rule, 'evidence': evidence})


def setv(df, idx, field, value, split, endpoint, rule, evidence=''):
    if field not in df.columns:
        df[field] = np.nan if isinstance(value, (int, float)) and not isinstance(value, bool) else None
        if isinstance(value, str):
            df[field] = df[field].astype(object)
    for i in idx:
        old = df.at[i, field]
        if isinstance(value, str) and df[field].dtype != object:
            df[field] = df[field].astype(object)
        df.at[i, field] = value
        log(split, endpoint, df.loc[i].to_dict(), field, old, value, rule, evidence)


def add_flag(df, idx, flag, split, endpoint, rule, evidence=''):
    for i in idx:
        old = df.at[i, 'v6_flags'] or ''
        parts = [p for p in old.split(';') if p]
        if flag not in parts:
            parts.append(flag)
            df.at[i, 'v6_flags'] = ';'.join(parts)
            log(split, endpoint, df.loc[i].to_dict(), 'v6_flags', old, df.at[i, 'v6_flags'], rule, evidence)


# ---------------------------------------------------------------------------------------------- B2 parsing
NUM = r'-?\d+(?:[.,]\d+)?'


def _f(s):
    return float(s.replace(',', '.'))


def parse_number(value):
    """Return (number, status). Status: EXACT, RANGE_MIDPOINT, PLUS_MINUS_CENTRE, FIRST_NUMBER, or a reason for None."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None, 'MISSING'
    s = re.sub(rf'({NUM})\s*%', r'\1', str(value).strip())
    if not s or re.match(r'(UNKNOWN|SOURCE_CONFLICT|NOT_|NA\b|none)', s, re.I):
        return None, 'NOT_REPORTED_OR_CONFLICT'
    if re.fullmatch(NUM, s):
        return _f(s), 'EXACT'
    m = re.match(rf'^\s*({NUM})\s*(?:-|–|—|to)\s*({NUM})(?!\s*[x×])', s)
    if m and not s.startswith('-'):
        a, b = _f(m.group(1)), _f(m.group(2))
        if b >= a:
            return (a + b) / 2, 'RANGE_MIDPOINT'
    m = re.match(rf'^\s*({NUM})\s*(?:±|\+/-|\+-|�|\+)\s*{NUM}', s)
    if m:
        return _f(m.group(1)), 'PLUS_MINUS_CENTRE'
    nums = re.findall(NUM, s)
    if ';' in s and len(set(nums)) > 1:
        return None, 'MULTIPLE_VALUES'
    m = re.match(rf'^\s*({NUM})\b', s)
    if m:
        return _f(m.group(1)), 'FIRST_NUMBER'
    return None, 'NOT_NUMERIC_TEXT'


def parse_duration_days(value, unit):
    u, s = (unit or '').lower(), str(value).lower()
    if re.search(r'no numeric|unstated reference|not assigned', s):
        return None, 'NOT_REPORTED_OR_CONFLICT'
    if re.search(rf'{NUM}\s*(h|hr|hrs|hours?)\b', s) or re.match(r'^\s*(h|hour)', u) or 'month' in u or 'month' in s:
        return None, 'UNIT_NOT_CONVERTED(D2: days and weeks only)'
    if re.search(rf'({NUM}|\))\s*\+\s*{NUM}', s):
        return None, 'MULTIPLE_PERIODS'
    x, st = parse_number(value)
    if x is None:
        return None, st
    # the unit's FIRST word decides ("days (printed as 4 weeks)" is already in days); without a unit, the value text
    head = re.match(r'\s*([a-z]+)', u)
    head = head.group(1) if head else ''
    if head in ('d', 'day', 'days'):
        weeks = False
    elif head in ('week', 'weeks', 'wk', 'wks', 'w'):
        weeks = True
    else:
        weeks = bool(re.match(rf'^\s*{NUM}\s*(weeks?|wk)\b', s))
    if st == 'FIRST_NUMBER':
        tail = re.sub(rf'^\s*{NUM}\s*', '', s)
        if not (weeks or re.match(r'(d\b|days?\b|dat\b|das\b|\(|$)', tail)):
            return None, 'AMBIGUOUS_TEXT'
    if weeks:
        return x * 7, st + '|WEEKS_X7'
    return x, st


def parse_photoperiod(value, unit):
    nums = [_f(n) for n in re.findall(NUM, str(value))]
    if len(nums) >= 2 and abs(nums[0] + nums[1] - 24) < 0.01:          # "16-8", "16 h/8 h": light/dark
        return nums[0], 'LIGHT_DARK_PAIR'
    if re.search(r'only|not stated', str(value), re.I) and len(nums) == 1:
        return None, 'PARTIAL_PHASE_ONLY'
    return parse_number(value)


def parse_pot_volume(value, unit):
    u, s = (unit or '').lower(), str(value).lower()
    if re.search(r'gallon', s):
        x = re.match(rf'^\s*({NUM})', s)
        return (_f(x.group(1)) * 3.785, 'US_GALLON_X3.785') if x else (None, 'NOT_NUMERIC_TEXT')
    if re.search(r'\bkg\b|inch|\bg\b|not converted|not stated', s + ' ' + u) and not re.fullmatch(r'\s*l\s*', u):
        return None, 'NOT_A_VOLUME'
    return parse_number(value)


def parse_density(value, unit):
    u, s = (unit or '').lower(), str(value)
    m = re.search(rf'({NUM})\s*cm\s*between rows?;?\s*({NUM})\s*cm\s*within row', s)
    if m:
        a, b = _f(m.group(1)) / 100, _f(m.group(2)) / 100
        return 1 / (a * b), 'SPACING_ROW_X_PLANT'
    x, st = parse_number(value)
    if x is None:
        return None, st
    if st == 'FIRST_NUMBER':
        return None, 'AMBIGUOUS_TEXT'
    if 'ha' in u.split() or 'ha-1' in u or 'per ha' in u or '/ha' in u:
        return x / 10000, st + '|PER_HA_DIV_1E4'
    if 'plot' in u or 'spacing' in u:
        return None, 'PLOT_OR_SPACING_NOT_CONVERTED'
    if x > 1000:
        return x / 10000, st + '|VALUE_GT_1000_READ_AS_PER_HA'
    return x, st


def parse_latitude(value, unit):
    s = str(value)
    m = re.search(r'(\d{1,2})\s*(?:[°º�]|deg)\s*(\d{1,2})?\s*[\'′’]?\s*(\d{1,2}(?:\.\d+)?)?\s*["″”]?\s*([NS])?', s)
    if m and m.group(2):
        d = int(m.group(1)) + int(m.group(2)) / 60 + (float(m.group(3)) / 3600 if m.group(3) else 0)
        return d, 'DMS_CONVERTED'
    x, st = parse_number(value)
    if x is None:
        return None, st
    return abs(x), st


PARSERS = {
    # moderator feature -> (V5 column to fill, parser, unit-aware?)
    'stress_duration_days': ('h2_stress_duration_days', parse_duration_days),
    'days_application_before_stress': ('h2_days_application_before_stress', parse_duration_days),
    'plant_density_m2': ('h2_plant_density_m2', parse_density),
    'temperature_day_c': ('v6_temperature_day_c', lambda v, u: parse_number(v)),
    'temperature_night_c': ('v6_temperature_night_c', lambda v, u: parse_number(v)),
    'relative_humidity': ('v6_relative_humidity_pct', lambda v, u: parse_number(v)),
    'pot_volume_l': ('v6_pot_volume_l', parse_pot_volume),
    'photoperiod_h': ('v6_photoperiod_h', parse_photoperiod),
    'latitude': ('v6_abs_latitude_printed', parse_latitude),
}
# stress descriptors are only meaningful for contrasts made under stress (V5 sets 0 / NaN on B_vs_C rows)
STRESS_FIELDS = {'h2_stress_duration_days', 'h2_stress_duration_reported', 'h2_days_application_before_stress',
                 'h2_stress_onset_phase', 'h_stress_class', 'h3_stress_combined', 'h3_n_stresses', 'h3_stress_salinity',
                 'h3_stress_drought', 'h2_salinity_nacl_mm', 'h2_salinity_measure_type', 'h2_salinity_reported',
                 'h2_drought_etc_pct', 'h2_drought_fc_pct', 'h2_drought_supply_type'}
PLAUSIBLE = {'v6_temperature_day_c': (0, 50), 'v6_temperature_night_c': (-5, 40), 'v6_relative_humidity_pct': (5, 100),
             'v6_pot_volume_l': (0.05, 2000), 'v6_photoperiod_h': (4, 24), 'v6_abs_latitude_printed': (0, 70),
             'h2_stress_duration_days': (0.1, 400), 'h2_days_application_before_stress': (-200, 200),
             'h2_plant_density_m2': (0.1, 60)}


def moderator_table(split):
    m = pd.read_parquet(FRZ[split] / 'db_moderators.parquet')
    m = m[m.feature.isin(PARSERS)].copy()
    m = m[m.availability.fillna('') != 'OBSERVED_POST_TREATMENT']        # post-treatment observations are not features
    rows = []
    for r in m.itertuples():
        col, fn = PARSERS[r.feature]
        x, st = fn(r.value, r.unit)
        lo, hi = PLAUSIBLE.get(col, (-1e9, 1e9))
        if x is not None and not (lo <= x <= hi):
            x, st = None, f'IMPLAUSIBLE({st})'
        rows.append({'study_id': str(r.study_id), 'experiment_key': r.experiment_key, 'arm_key': r.arm_key,
                     'feature': r.feature, 'target_col': col, 'value_raw': r.value, 'unit_raw': r.unit,
                     'value_num': x, 'parse_status': st, 'mod_id': r.mod_id, 'locator': r.locator})
    t = pd.DataFrame(rows)
    t.to_csv(RES / f'moderators_parsed_{split}_V6.csv', index=False)
    return t


def fill_moderators(df, split, endpoint, mt):
    """Arm-level value of the treated arm > experiment-level value > study-level value. Never copied from another experiment."""
    ok = mt[mt.value_num.notna()]
    by_arm = {(r.study_id, r.arm_key, r.target_col): (r.value_num, r.parse_status, r.mod_id)
              for r in ok[ok.arm_key.notna()].itertuples()}
    ok = ok.copy()
    ok['experiment_key'] = ok.experiment_key.fillna('__STUDY__')     # study-level statements apply to every experiment
    exp = ok[ok.arm_key.isna()].groupby(['study_id', 'experiment_key', 'target_col'])
    by_exp = {}
    for k, g in exp:
        vals = g.value_num.round(6).unique()
        if len(vals) == 1:                                   # conflicting experiment-level values stay missing
            by_exp[k] = (float(vals[0]), '|'.join(sorted(set(g.parse_status))), int(g.mod_id.iloc[0]))
    for col in sorted(set(ok.target_col)):
        if col not in df.columns:
            df[col] = np.nan
        src = col + '_v6src'
        if src not in df.columns:
            df[src] = None
    stats = {}
    for i, r in df.iterrows():
        sid, ek, arm = str(r.study_id), str(r.experiment_key), r.arm_key_t
        eks = [ek, ek.split('_')[0], '__STUDY__']             # 717: E1_2018 -> E1; then study-level value
        for col in sorted(set(ok.target_col)):
            cur = r[col]
            if not (cur is None or (isinstance(cur, float) and math.isnan(cur))):
                continue
            if col == 'h2_plant_density_m2' and r.get('h2_density_status') == 'NOT_APPLICABLE_POTS':
                continue
            if col in STRESS_FIELDS and r.contrast_type != 'SB_vs_S':
                continue
            hit = by_arm.get((sid, arm, col))
            if hit is None:
                for e in eks:
                    hit = by_exp.get((sid, e, col))
                    if hit:
                        break
            if hit is None:
                continue
            v, st, mid = hit
            df.at[i, col] = v
            df.at[i, col + '_v6src'] = f'DB_MODERATOR mod_id={mid} {st}'
            log(split, endpoint, r.to_dict(), col, cur, v, 'B2_PARSED_MODERATOR', f'db_moderators mod_id={mid}; {st}')
            stats[col] = stats.get(col, 0) + 1
    # keep the reported-flags of V5 consistent with the filled values
    for col, flag in [('h2_stress_duration_days', 'h2_stress_duration_reported')]:
        if flag in df.columns:
            m = df[col].notna() & (df[flag] != 1) & (df.contrast_type == 'SB_vs_S')
            for i in df.index[m]:
                log(split, endpoint, df.loc[i].to_dict(), flag, df.at[i, flag], 1, 'B2_PARSED_MODERATOR')
            df.loc[m, flag] = 1
    # printed latitude replaces the country centroid
    if 'v6_abs_latitude_printed' in df.columns and 'h3_abs_latitude' in df.columns:
        m = df.v6_abs_latitude_printed.notna() & (df.h3_latitude_source != 'PRINTED')
        for i in df.index[m]:
            setv(df, [i], 'h3_abs_latitude', float(df.at[i, 'v6_abs_latitude_printed']), split, endpoint,
                 'B2_PRINTED_LATITUDE_REPLACES_CENTROID', 'db_moderators latitude')
            setv(df, [i], 'h3_latitude_source', 'PRINTED_V6', split, endpoint, 'B2_PRINTED_LATITUDE_REPLACES_CENTROID')
    return stats


# ---------------------------------------------------------------------------------------------- B7 fertiliser N
def parse_n_kg_ha(text):
    if not isinstance(text, str) or not text.strip():
        return None, 'MISSING'
    t = text.replace(' ', ' ')
    per_fed = bool(re.search(r'fed(dan)?', t, re.I))
    per_ha = bool(re.search(r'\bha\b|ha-1|ha\^-1|/ha|ha−1|hectare', t, re.I))
    if not (per_ha or per_fed):
        return None, 'NO_AREA_BASIS'
    pats = [rf'({NUM})\s*kg\s*(?:of\s*)?N\b(?!a|H|O|P)', rf'\bN\s*[:=]?\s*({NUM})\s*kg', rf'({NUM})\s*kg\s*N\s*(?:/|per)\s*(?:ha|fed)',
            rf'N\s*(?:at|of)\s*({NUM})\s*kg']
    vals = []
    for p in pats:
        vals += [_f(x) for x in re.findall(p, t)]
    vals = sorted(set(vals))
    if not vals:
        return None, 'NO_N_RATE_FOUND'
    if len(vals) > 1:
        return None, f'MULTIPLE_N_RATES({vals})'
    v = vals[0] / 0.42 if per_fed and not per_ha else vals[0]
    if not (0 < v <= 1500):
        return None, 'IMPLAUSIBLE'
    return v, 'PARSED_FERT_TEXT' + ('|FEDDAN_DIV_0.42' if per_fed and not per_ha else '')


def fill_fert_n(df, split, endpoint):
    if 'h3_fert_n_kg_ha' not in df.columns:
        return 0
    src = 'context_fertilization_all' if 'context_fertilization_all' in df.columns else 'f_fertilization'
    n = 0
    df['h3_fert_n_kg_ha_v6src'] = df.get('h3_fert_n_kg_ha_v6src')
    for i in df.index[df.h3_fert_n_kg_ha.isna()]:
        v, st = parse_n_kg_ha(df.at[i, src] if src in df.columns else None)
        if v is None and 'f_fertilization' in df.columns:
            v, st = parse_n_kg_ha(df.at[i, 'f_fertilization'])
        if v is not None:
            setv(df, [i], 'h3_fert_n_kg_ha', round(v, 1), split, endpoint, 'B7_FERT_N_PARSED', st)
            df.at[i, 'h3_fert_n_kg_ha_v6src'] = st
            if 'h3_fert_reported' in df.columns and df.at[i, 'h3_fert_reported'] != 1:
                setv(df, [i], 'h3_fert_reported', 1, split, endpoint, 'B7_FERT_N_PARSED')
            n += 1
    return n


# ---------------------------------------------------------------------------------------------- B5 rootstock
def fill_rootstock(df, split, endpoint):
    arms = pd.read_parquet(FRZ[split] / 'db_arms.parquet')[['study_id', 'arm_key', 'genotype']]
    arms['study_id'] = arms.study_id.astype(str)
    g = arms.set_index(['study_id', 'arm_key']).genotype.to_dict()
    df['v6_rootstock'] = None
    df['v6_grafted'] = np.nan
    for i, r in df.iterrows():
        txt = g.get((str(r.study_id), r.arm_key_t))
        if not isinstance(txt, str):
            continue
        m = re.search(r'rootstock\s+([^;,()]+(?:\([^)]*\))?)', txt, re.I)
        if m:
            rs = m.group(1).strip()
            self_g = bool(re.search(r'self-?grafted', txt, re.I))
            df.at[i, 'v6_rootstock'] = 'SELF_GRAFTED' if self_g else rs
            df.at[i, 'v6_grafted'] = 0.5 if self_g else 1.0
        elif re.search(r'non-?grafted|ungrafted', txt, re.I):
            df.at[i, 'v6_grafted'] = 0.0
    return int(df.v6_rootstock.notna().sum())


# ---------------------------------------------------------------------------------------------- B6 plant age
def plant_age(key):
    if not isinstance(key, str):
        return None, 'MISSING', None
    k = re.sub(r'^E\d+[A-Z0-9]*[._]', '', key)
    kl = k.lower()
    if re.search(r'\d+\s*mat\b|maturity', kl):                      # "1MAT", "2MAT": n-th maturity, not days
        return None, 'END_OF_EXPERIMENT_NO_DAYS', None
    m = re.search(r'(\d+(?:\.\d+)?)\s*(was|wat)\b', kl)               # weeks after sowing / transplanting
    if m:
        return float(m.group(1)) * 7, 'AFTER_SOWING' if m.group(2) == 'was' else 'AFTER_TRANSPLANT', 'WEEKS_X7'
    num = re.findall(r'\d+(?:\.\d+)?', k)
    x = float(num[0]) if num else None
    if re.search(r'das|after_sow|sowing', kl): ref = 'AFTER_SOWING'
    elif re.search(r'dat|after_transpl|transpl|dpp', kl): ref = 'AFTER_TRANSPLANT'
    elif re.search(r'after_s\b|_stress|after_stress|d\d+_after_s', kl): ref = 'AFTER_STRESS_START'
    elif re.search(r'dai|wpi|post_inoc|inoc', kl): ref = 'AFTER_INOCULATION'
    elif re.search(r'germ', kl): ref = 'AFTER_GERMINATION'
    elif re.search(r'harv|maturity|end|final|post', kl) and x is None: ref = 'END_OF_EXPERIMENT_NO_DAYS'
    elif x is not None: ref = 'REFERENCE_NOT_STATED'
    else: ref = 'UNKNOWN'
    if x is None:
        return None, ref, None
    if re.search(r'(\d)\s*(wk|w\b|_wk|week)|^w\d|t\d+w|wk', kl):
        return x * 7, ref, 'WEEKS_X7'
    if re.search(r'(\d)\s*(mo|m\b)|_\d+m\b|mo_|\dmo|_m$|h_\d+m', kl):
        return round(x * 30.44, 1), ref, 'MONTHS_X30.44_APPROX'
    return x, ref, 'DAYS'


def fill_age(df):
    out = df.timepoint_key.map(plant_age)
    df['v6_age_days'] = [o[0] for o in out]
    df['v6_age_reference'] = [o[1] for o in out]
    df['v6_age_unit_rule'] = [o[2] for o in out]
    # a printed timepoint_days is kept when the key gives no number
    m = df.v6_age_days.isna() & df.timepoint_days.notna()
    df.loc[m, 'v6_age_days'] = df.loc[m, 'timepoint_days']
    df.loc[m, 'v6_age_unit_rule'] = 'TIMEPOINT_DAYS_FIELD'
    df.loc[m & df.v6_age_reference.isin(['END_OF_EXPERIMENT_NO_DAYS', 'UNKNOWN']), 'v6_age_reference'] = 'REFERENCE_NOT_STATED'
    for ref in ['AFTER_SOWING', 'AFTER_TRANSPLANT', 'AFTER_STRESS_START']:
        df[f'v6_days_{ref.lower()}'] = np.where(df.v6_age_reference == ref, df.v6_age_days, np.nan)


# ---------------------------------------------------------------------------------------------- B4 flags
def severity_and_flags(df, split, endpoint):
    s = df['mod_lnrr_stress_SvsC'] if 'mod_lnrr_stress_SvsC' in df.columns else pd.Series(np.nan, index=df.index)
    sb = df.contrast_type == 'SB_vs_S'
    cls = np.select([~sb, s.isna(), s > -0.05, s > -0.223, s < math.log(0.25)],
                    ['NOT_APPLICABLE', 'NO_UNSTRESSED_REFERENCE', 'NOT_REALISED', 'MILD', 'SEVERE_CONTROL_LT_25PCT'],
                    'REALISED')
    df['v6_stress_realisation'] = cls
    df['v6_stress_loss_pct'] = np.where(sb, (1 - np.exp(s)) * 100, np.nan)
    add_flag(df, df.index[cls == 'NOT_REALISED'], 'STRESS_NOT_REALISED', split, endpoint,
             'B4_SvsC_GE_-0.05', 'ln(S/C) of the study\'s own unstressed control >= -0.05')
    add_flag(df, df.index[cls == 'SEVERE_CONTROL_LT_25PCT'], 'CONTROL_COLLAPSED_LT_25PCT', split, endpoint,
             'B4_SvsC_LT_ln0.25', 'stressed control below 25% of the unstressed control')
    # quantised targets: >= 4 arm means, all whole numbers, at most 2 distinct values (lnRR can only be 0 or ln k)
    for sid, g in df.groupby('study_id'):
        vals = pd.concat([g.mean_t, g.mean_c]).dropna()
        if len(vals) >= 4 and np.allclose(vals, np.round(vals)) and vals.nunique() <= 2:
            add_flag(df, g.index, 'TARGET_QUANTIZED_WHOLE_UNITS', split, endpoint, 'B4_QUANTIZED',
                     f'all arm means integer, distinct values {sorted(vals.unique())}')


# ---------------------------------------------------------------------------------------------- B3 duplicates
SCOPE_PRI = {'TOTAL': 0, 'UNSPECIFIED': 1, 'MARKETABLE': 2}
DEN_PRI = {'PER_PLANT': 0, 'PER_AREA': 1, 'PER_PLOT': 2}
ORGAN_PRI = {'WHOLE_PLANT': 0, 'SHOOT': 1}
TIER_PRI = {'STRICT': 0, 'ASSUMED': 1, 'BROAD': 2, 'UNIT_UNRESOLVED': 3}


def dedup(df, split, endpoint):
    year = df['v5_measurement_year'] if 'v5_measurement_year' in df.columns else ''
    key = df.study_id.astype(str) + '|' + df.experiment_key.astype(str) + '|' + df.arm_key_t.astype(str) + '|' + \
        df.arm_key_c.astype(str) + '|' + df.timepoint_key.astype(str) + '|' + pd.Series(year, index=df.index).astype(str)
    df['v6_pair_key'] = key
    def col(c, default):
        return df[c] if c in df.columns else pd.Series(default, index=df.index)
    # fresh before dry fruit mass, full before early harvest, TOTAL > UNSPECIFIED > MARKETABLE,
    # whole plant > shoot (TFM contract), STRICT > ASSUMED > BROAD > UNIT_UNRESOLVED, per plant > per area
    pri = (col('is_dry_yield', 0).fillna(0).astype(float) * 1e5
           + col('is_early_yield', 0).fillna(0).astype(float) * 1e4
           + col('h2_yield_scope', 'UNSPECIFIED').map(SCOPE_PRI).fillna(3) * 1e3
           + col('organ_scope', None).map(ORGAN_PRI).fillna(2) * 1e2
           + col('yield_tier', None).map(TIER_PRI).fillna(4) * 10
           + df.denominator.map(DEN_PRI).fillna(3))
    df['v6_dup_priority'] = pri
    df['v6_primary_of_pair'] = 1
    base = df[df.in_default == 1]
    n = 0
    for k, g in base.groupby('v6_pair_key'):
        if len(g) < 2:
            continue
        keep = g.sort_values(['v6_dup_priority', 'contrast_id']).index[0]
        drop = [i for i in g.index if i != keep]
        setv(df, drop, 'v6_primary_of_pair', 0, split, endpoint, 'B3_ONE_CONTRAST_PER_ARM_PAIR',
             f'same arm pair, harvest and year; kept {g.loc[keep, "contrast_id"]} (fresh > dry, full > early, '
             'TOTAL > UNSPECIFIED > MARKETABLE, whole plant > shoot, STRICT > ASSUMED > BROAD, per plant > per area)')
        n += len(drop)
    return n


# ---------------------------------------------------------------------------------------------- B1 V3.1 fixes
NON_BIO = [  # (study, arm_key_t, arm_key_c, reason) restored from SynerPlant_Yield_V2/outputs/v31/*/v31_changes.csv
    ('D_1c70767428261b78', 'E1.SB.VEH', 'E1.S.C1', 'R2_NOT_A_BIOSTIMULANT: culture medium without bacteria'),
    ('653', 'E1.SB.NPK', 'E1.S', 'R2_NOT_A_BIOSTIMULANT: NPK fertiliser alone'),
    ('706', 'E1.S.VEH', 'E1.S', 'R2_NOT_A_BIOSTIMULANT: acetic-acid solvent of chitosan'),
]
REBASE = [  # (study, treated arm, raw control, correct control arm, reason)
    ('653', 'E1.SB.AMF+NPK', 'E1.S', 'E1.SB.NPK', 'V31-RB02: AMF+NPK compared with NPK alone'),
    ('706', 'E1.S.CH003', 'E1.S', 'E1.S.VEH', 'V31-RB01: chitosan in solvent compared with the solvent'),
    ('706', 'E1.S.CH005', 'E1.S', 'E1.S.VEH', 'V31-RB01: chitosan in solvent compared with the solvent'),
]


def restore_v31(df, split, endpoint):
    n_ex, new_rows = 0, []
    for sid, at, ac, why in NON_BIO:
        idx = df.index[(df.study_id.astype(str) == sid) & (df.arm_key_t == at)]
        if len(idx):
            setv(df, idx, 'v6_excluded_reason', why, split, endpoint, 'B1_RESTORE_V31_FIX', 'V3.1 register v31_changes.csv')
            n_ex += len(idx)
    for sid, at, ac, cc, why in REBASE:
        t = df[(df.study_id.astype(str) == sid) & (df.arm_key_t == at) & (df.arm_key_c == ac)]
        c = df[(df.study_id.astype(str) == sid) & (df.arm_key_t == cc) & (df.arm_key_c == ac)]
        if t.empty or c.empty:
            continue
        for (_, tr), (_, cr) in zip(t.iterrows(), c.iloc[[0] * len(t)].iterrows()):
            nr = tr.copy()
            nr['contrast_id'] = tr.contrast_id + '_V6RB'
            nr['arm_key_c'] = cc
            for f in ['mean', 'sd', 'n']:
                nr[f + '_c'] = cr[f + '_t']
            for f in ['cv_used', 'n_imp', 'n_imputed', 'cv_source']:
                if f + '_t' in cr and f + '_c' in nr:
                    nr[f + '_c'] = cr[f + '_t']
            if tr.mean_t > 0 and cr.mean_t > 0:
                nr['effect'] = math.log(tr.mean_t / cr.mean_t)
                if 'effect_bc_imp' in nr:
                    nr['effect_bc_imp'] = nr['effect']
            if 'var_lnrr_imp' in nr and all(k in nr for k in ['cv_used_t', 'cv_used_c', 'n_imp_t', 'n_imp_c']):
                try:
                    nr['var_lnrr_imp'] = nr.cv_used_t ** 2 / nr.n_imp_t + nr.cv_used_c ** 2 / nr.n_imp_c
                except Exception:
                    pass
            nr['var_effect'] = (tr.sd_t ** 2 / (tr.n_t * tr.mean_t ** 2) + cr.sd_t ** 2 / (cr.n_t * cr.mean_t ** 2)
                                if pd.notna(tr.sd_t) and pd.notna(cr.sd_t) and tr.n_t and cr.n_t else np.nan)
            nr['v6_excluded_reason'] = None
            nr['v6_flags'] = 'V6_REBASED_CONTROL'
            new_rows.append(nr)
            REG.append({'split': split, 'endpoint': endpoint, 'contrast_id': nr.contrast_id, 'study_id': sid,
                        'experiment_key': tr.experiment_key, 'arm_key_t': at, 'arm_key_c': cc, 'field': 'NEW_CONTRAST',
                        'old_value': f'{at} vs {ac}', 'new_value': f'{at} vs {cc}, lnRR={nr.effect:.4f}',
                        'rule': 'B1_RESTORE_V31_REBASE', 'evidence': why})
        # the raw-control version of a re-based contrast leaves the default set
        setv(df, t.index, 'v6_excluded_reason', 'REPLACED_BY_V6_REBASED_CONTRAST', split, endpoint, 'B1_RESTORE_V31_REBASE', why)
    if new_rows:
        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
    return df, n_ex, len(new_rows)


def detect_non_biostimulant(df):
    pat = r'VEH|VEHICLE|SOLVENT|MOCK|NPK|MEDIUM|WATER_SPRAY|BLANK|PLACEBO|UREA_ONLY|FERTILI[SZ]ER_ONLY'
    m = df.bio_code.astype(str).str.upper().str.contains(pat, regex=True) & (df.contrast_type == 'SB_vs_S')
    return df.loc[m, ['study_id', 'experiment_key', 'arm_key_t', 'arm_key_c', 'bio_code', 'v6_excluded_reason']]


# ---------------------------------------------------------------------------------------------- A study audit
AUDIT = [
    # study, endpoint scope ('all'|'yield'), row filter: (field, regex), field, value, evidence
    ('D_787a2af6e69899c4', 'all', None, 'h2_stress_duration_days', 84.0, 'Tahiri 2022 p.746: "maintained ... for the additional 12 weeks" (DB unit = weeks; V5 lost it)'),
    ('D_787a2af6e69899c4', 'all', ('arm_key_t', r'PGPR'), 'h3_n_applications', 2.0, 'p.747: PGPR inoculation plus booster "after 15 days"'),
    ('D_787a2af6e69899c4', 'all', ('arm_key_t', r'\.(SB|B)\.PGPR$'), 'h_dose_class', 'CFU', 'p.747: ~10^9 CFU/mL, 50 mL'),
    ('D_787a2af6e69899c4', 'all', ('arm_key_t', r'\.(SB|B)\.PGPR$'), 'h_log10_dose', 9.0, 'p.747: ~10^9 CFU/mL'),
    ('D_787a2af6e69899c4', 'all', ('arm_key_t', r'\.(SB|B)\.AMF$'), 'h_dose_class', 'PER_PLANT_OR_POT', 'p.747: 10 g sand inoculum with spores per plant (not CFU)'),
    ('D_9cb48f9f1f80975a', 'all', ('experiment_key', r'^E2$'), 'h3_n_applications', 26.0, 'Perez-Inocencio 2023 p.3: inoculated "at the beginning ... and once a week until the end" over ~180 d (approx.; E1 value 1 had been copied)'),
    ('D_2e3875208f031bf2', 'all', ('arm_key_t', r'S1I[23]$'), 'h_stress_class', 'COMBINED', 'Dou 2023 Tables 6-7 p.8: S1 (soil salt) x I2/I3 (deficit irrigation) = salt + drought'),
    ('D_2e3875208f031bf2', 'all', ('arm_key_t', r'S1I[23]$'), 'h3_stress_combined', 1, 'idem'),
    ('D_2e3875208f031bf2', 'all', ('arm_key_t', r'S1I[23]$'), 'h3_n_stresses', 2, 'idem'),
    ('D_2e3875208f031bf2', 'all', ('arm_key_t', r'S1I'), 'h3_stress_salinity', 1, 'idem: S1 = saline soil'),
    ('D_2e3875208f031bf2', 'all', ('arm_key_t', r'S1I1$'), 'h_stress_class', 'SALINITY', 'S1I1 = saline soil, full irrigation'),
    ('D_2e3875208f031bf2', 'all', ('arm_key_t', r'S1I1$'), 'h3_stress_drought', 0, 'idem'),
    ('D_2e3875208f031bf2', 'all', ('arm_key_t', r'S1I'), 'h2_salinity_nacl_mm', np.nan, 'salinity is soil salt content (g/g), not NaCl mM; V5 value 0 meant "no salinity"'),
    ('D_2e3875208f031bf2', 'all', ('arm_key_t', r'S1I'), 'h2_salinity_measure_type', 'SOIL_SALT_CONTENT', 'idem'),
    ('D_2e3875208f031bf2', 'all', ('arm_key_t', r'S1I'), 'h2_salinity_reported', 1, 'idem'),
    ('D_5bfa54dd469be771', 'all', ('arm_key_t', r'\.SB\.SI60\.'), 'h3_n_applications', 1.0, 'Silicon 2023 p.3: Si applied once before transplant; ASE weekly x6 only'),
    ('D_5bfa54dd469be771', 'all', ('arm_key_t', r'\.SB\.SI60\.'), 'h2_application_phase', 'NURSERY_SEEDLING', 'idem'),
    ('D_5bfa54dd469be771', 'yield', None, 'h2_yield_scope', 'TOTAL', 'Table 3 p.7: fruit yield per plant at harvest (total)'),
    ('D_5bfa54dd469be771', 'all', None, 'v6_temperature_day_c', 31.0, 'p.3: polyhouse 28-34 C (midpoint)'),
    ('D_86b092ac9ca2d729', 'yield', None, 'h2_yield_scope', 'TOTAL', 'Ahmed 2022 p.98: "Fruit yield ... recorded at crop maturity"'),
    ('D_86b092ac9ca2d729', 'all', None, 'v6_temperature_day_c', 34.0, 'p.97: polyhouse 30-38 C (midpoint)'),
    ('D_61bafda8e5809db9', 'all', None, 'h2_stress_duration_days', 106.0, 'AASJ 2023 p.4: ambient heat over the season, transplant 14 June to harvest 28 Sep/2 Oct'),
    ('D_61bafda8e5809db9', 'all', None, 'h2_plant_density_m2', 3.3, 'p.4: hills 30 cm apart on 1 m wide plots'),
    ('D_61bafda8e5809db9', 'all', None, 'h3_fert_n_kg_ha', 286.0, 'p.4: per-feddan rates converted to ha (/0.42)'),
    ('D_19afb23b32e7648a', 'all', None, 'h2_stress_duration_days', 90.0, 'Phyton 2022 p.4: 200 mM NaCl irrigation from transplant, grown 90 days'),
    ('D_19afb23b32e7648a', 'all', None, 'h2_stress_onset_phase', 'TRANSPLANT', 'idem'),
    ('D_6b5d82abb9f7e388', 'all', None, 'v6_temperature_day_c', 22.0, 'Alam 2023 p.4: mean temperature 22 C'),
    ('D_d2cc590a442913d8', 'all', None, 'h3_n_applications', 1.0, 'Sayed 2022: single seed/seedling priming before grafting'),
    ('D_068b862524c2c34a', 'all', ('experiment_key', r'^E1$'), 'h2_drought_etc_pct', 60.0, 'Top 2023 p.5617 / db_arms: 0.6 vs 1.0 L per plant per day (2020)'),
    ('D_068b862524c2c34a', 'all', ('experiment_key', r'^E2$'), 'h2_drought_etc_pct', 33.3, 'p.5617 / db_arms: 0.4 vs 1.2 L per plant per day (2021)'),
    ('D_068b862524c2c34a', 'all', None, 'h2_drought_fc_pct', np.nan, 'reduction is of irrigation volume, not % field capacity (V5 value 25 not in source)'),
    ('D_068b862524c2c34a', 'all', None, 'h2_drought_supply_type', 'ETC_OR_IRRIGATION_PCT', 'idem'),
]
AUDIT_FLAGS = [
    ('D_19afb23b32e7648a', None, 'NO_UNSTRESSED_REFERENCE_CONTROL_COLLAPSED', 'Table 2 p.6: stressed control 42 g/plant vs 1166.6 g/plant; no unstressed arm'),
    ('D_24fe4181e5a0c693', None, 'TARGET_TEXT_FIGURE_CONFLICT', 'p.10 text 0.86->3.18 kg/plant vs Fig. 7 p.11 0.56 kg/plant'),
    ('D_24fe4181e5a0c693', None, 'TARGET_IMPLAUSIBLE_FOR_SYSTEM', '3-4 kg/plant from 750 mL pots with 15-32 g fruits (Table 4 p.11)'),
    ('D_d2cc590a442913d8', None, 'TARGET_TEXT_FIGURE_CONFLICT', 'text +10.5%/+5.7% (p.1, p.4) vs ~10x in Fig. 1C'),
    ('D_d2cc590a442913d8', None, 'STRESS_AMBIENT_NO_UNSTRESSED_REFERENCE', 'winter field season, monthly minima 12-22 C (Fig. 10 p.17)'),
    ('D_61bafda8e5809db9', None, 'STRESS_AMBIENT_NO_UNSTRESSED_REFERENCE', 'summer heat, no temperature data, no cool comparator (p.2)'),
    ('D_61bafda8e5809db9', None, 'YIELD_SCOPE_MIXED_WITHIN_STUDY', 'H1 total (Fig. 1C p.11) vs H2 marketable (Table 8 p.10)'),
    ('D_61bafda8e5809db9', None, 'PRODUCT_SUPPLIES_NUTRIENTS', 'K-silicate supplies K, fulvic product supplies N (p.14)'),
    ('D_6b5d82abb9f7e388', None, 'TARGET_QUANTIZED_WHOLE_UNITS', 'Fig. 3k p.6: bars read in whole kg/plant'),
    ('D_068b862524c2c34a', None, 'STRESS_BARELY_REALISED_SOURCE', 'p.5620/5623: SMC only 1.4 pp lower; "Plants did hence not experience severe water deficit"'),
    ('D_df10fa5eec64cb8d', ('arm_key_t', r'SAL1000'), 'STRESS_NOT_REALISED_SOURCE', 'Table 6 p.105: 1000 ppm yield ~8% above the non-saline control in both seasons'),
    ('D_adda3ddd52623208', ('arm_key_t', r'N70'), 'NUTRIENT_LIMITATION_NOT_REALISED', 'Table 1 p.4: 70% nutrient control 51.19 g > 100% control 46.72 g'),
    ('D_adda3ddd52623208', None, 'YIELD_POSSIBLY_REREPORTED', 'p.2: yield also reported in Di Stasio et al. 2018 (ref. 27)'),
    ('D_f3c00040a8fabdde', None, 'PRODUCT_SUPPLIES_NUTRIENTS', 'Table 1 p.2: compost 20.3 g N/kg x 40 t/ha (~800 kg N/ha); gypsum supplies Ca/S'),
    ('D_1c70767428261b78', ('experiment_key', r'^E1$'), 'YIELD_EARLY_PARTIAL_HARVEST', 'p.67: E1 yield read at 60 DAT'),
    ('D_9cb48f9f1f80975a', None, 'SMALL_N_STRAIN_RANK_REVERSALS', 'p.3 / Table 3 p.8: n = 5 plants per treatment'),
]


def apply_audit(df, split, endpoint):
    if split != 'train':
        return 0
    n = 0
    for sid, scope, flt, field, val, ev in AUDIT:
        if scope == 'yield' and endpoint != 'yield':
            continue
        m = df.study_id.astype(str) == sid
        if flt:
            m &= df[flt[0]].astype(str).str.contains(flt[1], regex=True)
        if field in STRESS_FIELDS:
            m &= df.contrast_type == 'SB_vs_S'
        idx = df.index[m]
        if len(idx):
            setv(df, idx, field, val, split, endpoint, 'A_SOURCE_CHECKED_STUDY_AUDIT', ev)
            if field == 'h3_n_applications' and 'h3_log_n_applications' in df.columns:
                setv(df, idx, 'h3_log_n_applications', math.log1p(val), split, endpoint, 'A_SOURCE_CHECKED_STUDY_AUDIT', ev)
                if 'h3_n_applications_source' in df.columns:
                    setv(df, idx, 'h3_n_applications_source', 'V6_SOURCE_AUDIT', split, endpoint, 'A_SOURCE_CHECKED_STUDY_AUDIT', ev)
            if field == 'h2_stress_duration_days' and 'h2_stress_duration_reported' in df.columns:
                setv(df, idx, 'h2_stress_duration_reported', 1, split, endpoint, 'A_SOURCE_CHECKED_STUDY_AUDIT', ev)
            n += len(idx)
    for sid, flt, flag, ev in AUDIT_FLAGS:
        # flags about the fruit-yield values were checked on the yield tables only; stress/design flags apply to all
        if endpoint != 'yield' and flag.startswith(('TARGET_', 'YIELD_', 'NO_UNSTRESSED_REFERENCE_CONTROL_COLLAPSED')):
            continue
        m = df.study_id.astype(str) == sid
        if flt:
            m &= df[flt[0]].astype(str).str.contains(flt[1], regex=True)
        add_flag(df, df.index[m], flag, split, endpoint, 'A_SOURCE_CHECKED_STUDY_AUDIT', ev)
    return n


RELIABILITY_FLAGS = {'STRESS_NOT_REALISED', 'STRESS_NOT_REALISED_SOURCE', 'STRESS_BARELY_REALISED_SOURCE',
                     'CONTROL_COLLAPSED_LT_25PCT', 'NO_UNSTRESSED_REFERENCE_CONTROL_COLLAPSED',
                     'TARGET_QUANTIZED_WHOLE_UNITS', 'TARGET_TEXT_FIGURE_CONFLICT', 'TARGET_IMPLAUSIBLE_FOR_SYSTEM',
                     'NUTRIENT_LIMITATION_NOT_REALISED'}


# ---------------------------------------------------------------------------------------------- driver
def run(split, endpoint, mt):
    f = V5D / f'{split}_{endpoint}.parquet'
    df = pd.read_parquet(f).reset_index(drop=True)
    n0 = len(df)
    df['v6_flags'] = ''
    df['v6_excluded_reason'] = None
    df, n_ex, n_rb = restore_v31(df, split, endpoint)
    n_audit = apply_audit(df, split, endpoint)
    fills = fill_moderators(df, split, endpoint, mt)
    n_fert = fill_fert_n(df, split, endpoint)
    n_rs = fill_rootstock(df, split, endpoint)
    fill_age(df)
    severity_and_flags(df, split, endpoint)
    n_dup = dedup(df, split, endpoint)
    df['in_default_v6'] = ((df.in_default == 1) & df.v6_excluded_reason.isna() & (df.v6_primary_of_pair == 1)).astype(int)
    flags = df.v6_flags.fillna('').str.split(';')
    df['v6_reliability_flag'] = flags.map(lambda x: int(bool(set(x) & RELIABILITY_FLAGS)))
    df['in_quality_core_v6'] = ((df.in_default_v6 == 1) & (df.v6_reliability_flag == 0)).astype(int)
    # numeric / object hygiene for parquet
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].where(df[c].notna(), None)
    stem = f'{split}_{endpoint}_V6'
    df.to_parquet(DATA / f'{stem}.parquet', index=False)
    df.to_csv(DATA / f'{stem}.csv', index=False)
    nb = detect_non_biostimulant(df)
    nb.to_csv(RES / f'non_biostimulant_candidates_{stem}.csv', index=False)
    sbs = df[(df.contrast_type == 'SB_vs_S')]
    return {'rows_v5': n0, 'rows_v6': len(df), 'studies': int(df.study_id.nunique()),
            'in_default_v5': int((df.in_default == 1).sum()), 'in_default_v6': int(df.in_default_v6.sum()),
            'in_quality_core_v6': int(df.in_quality_core_v6.sum()),
            'quality_core_studies': int(df.loc[df.in_quality_core_v6 == 1, 'study_id'].nunique()),
            'excluded_non_biostimulant': n_ex, 'rebased_new': n_rb, 'secondary_duplicates': n_dup,
            'audit_cells': n_audit, 'moderator_fills': fills, 'fert_n_filled': n_fert, 'rootstock_rows': n_rs,
            'stress_realisation_SB_vs_S': sbs.v6_stress_realisation.value_counts().to_dict(),
            'non_biostimulant_candidates_left': int(nb.v6_excluded_reason.isna().sum())}


def coverage_table(rows):
    out = []
    for split in ['train', 'test']:
        for ep in ['yield', 'dry_biomass']:
            v5 = pd.read_parquet(V5D / f'{split}_{ep}.parquet')
            v6 = pd.read_parquet(DATA / f'{split}_{ep}_V6.parquet')
            # coverage among stressed contrasts (SB_vs_S), share of studies with the value
            v5 = v5[(v5.in_default == 1) & (v5.contrast_type == 'SB_vs_S')]
            v6 = v6[(v6.in_default_v6 == 1) & (v6.contrast_type == 'SB_vs_S')]
            for c in ['h2_stress_duration_days', 'h2_days_application_before_stress', 'h2_plant_density_m2', 'h3_fert_n_kg_ha',
                      'h3_n_applications', 'v6_temperature_day_c', 'v6_relative_humidity_pct', 'v6_pot_volume_l',
                      'v6_photoperiod_h', 'v6_abs_latitude_printed', 'v6_rootstock', 'v6_age_days']:
                def cov(d):
                    if c not in d.columns:
                        return 0.0
                    return round(float(d[c].notna().groupby(d.study_id).any().mean()), 3)
                out.append({'split': split, 'endpoint': ep, 'feature': c, 'study_coverage_v5': cov(v5), 'study_coverage_v6': cov(v6)})
    pd.DataFrame(out).to_csv(RES / 'feature_coverage_V5_vs_V6.csv', index=False)
    return out


def main():
    summary = {'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'), 'runs': {}}
    for split in ['train', 'test']:
        mt = moderator_table(split)
        summary[f'moderator_parse_{split}'] = mt.parse_status.str.split('|').str[0].value_counts().to_dict()
        for ep in ['yield', 'dry_biomass']:
            summary['runs'][f'{split}_{ep}'] = run(split, ep, mt)
    reg = pd.DataFrame(REG)
    reg.to_csv(DATA / 'corrections_register_V6.csv', index=False)
    pd.DataFrame([{'study_id': a[0], 'endpoint_scope': a[1], 'row_filter': '' if a[2] is None else f'{a[2][0]} ~ {a[2][1]}',
                   'field': a[3], 'new_value': a[4], 'evidence': a[5]} for a in AUDIT] +
                 [{'study_id': a[0], 'endpoint_scope': 'all', 'row_filter': '' if a[1] is None else f'{a[1][0]} ~ {a[1][1]}',
                   'field': 'v6_flags', 'new_value': a[2], 'evidence': a[3]} for a in AUDIT_FLAGS]
                 ).to_csv(DATA / 'study_audit_corrections_V6.csv', index=False)
    summary['register_rows'] = len(reg)
    summary['register_by_rule'] = reg.rule.value_counts().to_dict() if len(reg) else {}
    summary['coverage'] = coverage_table(summary)
    (RES / 'summary_V6.json').write_text(json.dumps(summary, indent=1, ensure_ascii=False, default=str), encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'coverage'}, indent=1, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
