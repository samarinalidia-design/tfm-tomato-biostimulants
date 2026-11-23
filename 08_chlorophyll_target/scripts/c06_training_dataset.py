"""Chlorophyll training dataset (TRAIN_DEV, publication year <= 2023), built with the lessons of the yield/biomass work.

Input : data/<TAG>_contrasts.csv (c05), the V6 corrected yield and dry-biomass marts (moderators of the same arms),
        the V6 non-biostimulant register, the packets (study year, role check).
Output: data/chl_train_dataset_V8.csv / .parquet (one row per contrast, all endpoints and contrast types, with flags)
        results/chl_dataset_summary_V8.json

Rules (each one answers an error we found earlier):
 1. Split integrity. Only TRAIN_DEV studies of the frozen split; a study or DOI of the EXTERNAL_TEST database aborts the build
    (printed issue year > 2023 is only flagged: online-first <= 2023, assigned to TRAIN_DEV by the freeze).
 2. One row per (study, experiment, endpoint, contrast type, treated arm, control arm): the passes may report the same
    data in several units, bases or tables. Priority: printed total > a+b computed; FRESH_MASS > DRY_MASS > LEAF_AREA
    > UNSPECIFIED > EXTRACT_VOLUME; reported variance > assumed SE > imputed; TABLE > FIGURE; SPAD > other indices.
    (V5 kept fresh/dry and shoot/whole-plant duplicates; V6 B3.)
 3. Stress moderators are attached to SB_vs_S and S_vs_C rows only (V6 B2: stress fields leaked onto B_vs_C rows).
 4. Moderators come from the same arm in the V6 marts (arm > experiment > study), never from another arm; treatment
    descriptors are arm-level only. Coverage is reported, nothing is imputed here (the featurizer imputes inside CV).
 5. Non-biostimulant treatments of the V6 register are excluded from the default set (R2_NOT_A_BIOSTIMULANT).
 6. Variance provenance is kept (REPORTED / USER_ASSUMED_SE / IMPUTED_CVBAR). The default analysis weight is NOT the
    inverse variance: for biomass the precision-weight mismatch made ML worse than the mean, so `w_train` = 1 per
    contrast divided by the number of contrasts of the study (each study weighs the same); `w_ivw` is given separately.
 7. Grouped CV: `cv_group` = study_id (all contrasts of a study, including shared controls, stay in one fold).
 8. Reliability flags, not silent deletions: time point outside the stress period, computed total, figure source,
    extreme effect (|lnRR| > ln 3), pigment values internally inconsistent in the source (b > a or total < a), stress not realised in the matched yield/biomass contrast, product supplies
    nutrients, unknown n. `in_default_chl` keeps flagged rows; `in_quality_core_chl` drops them.
Usage: python c06_training_dataset.py
"""
import json, os, pathlib, re
import numpy as np
import pandas as pd

OUT = pathlib.Path(__file__).resolve().parents[1]
REPO = OUT.parent
V6 = REPO / '06_database_corrections_v6'
WORK = pathlib.Path(os.environ.get('CHL_WORK', r"C:/Users/lenovo/Desktop/master's/TFM_CHLOROPHYLL_PILOT/work"))
TAG = os.environ.get('CHL_TAG', 'all')
SPLIT = os.environ.get('CHL_SPLIT', 'TRAIN')          # TRAIN or TEST
SP = 'train' if SPLIT == 'TRAIN' else 'test'

BASIS_PRI = {'FRESH_MASS': 0, 'DRY_MASS': 1, 'LEAF_AREA': 2, 'UNSPECIFIED': 3, 'EXTRACT_VOLUME': 4, 'INDEX': 5}
VAR_PRI = {'REPORTED': 0, 'USER_ASSUMED_SE': 1, 'IMPUTED_CVBAR': 2}
TREAT_RE = re.compile(r'dujardin|taxon|active|route|dose|n_applications|live_micro|nonliving|n_components|genus|product|'
                      r'composition|microorganism|strain|biostimulant_class|application_stage|application_phase|class_key|'
                      r'frequency|n_actives|n_taxa|n_routes')
STRESS_RE = re.compile(r'stress|drought|salinity|nacl|field_capacity|irrigation|ec_irrigation|pathogen|inoculum|soil_ec|'
                       r'phase_app_minus|days_application_before')
OUTCOME_ONLY = {'h2_yield_scope', 'h2_harvest_window', 'h2_definition_refined_from_locator', 'v6_pair_key', 'v6_dup_priority',
                'v6_primary_of_pair', 'v6_flags', 'v6_excluded_reason', 'v6_reliability_flag', 'v6_stress_loss_pct',
                'h3_text_all', 'mod_lnrr_stress_SvsC'}


def moderator_columns(df):
    cols = [c for c in df.columns if re.match(r'^(h_|h2_|h3_|v6_)', c) and c not in OUTCOME_ONLY and not c.endswith('_v6src')]
    treat = [c for c in cols if TREAT_RE.search(c)]
    stress = [c for c in cols if c not in treat and STRESS_RE.search(c)]
    ctx = [c for c in cols if c not in treat and c not in stress]
    return ctx, treat, stress


def first_non_null(g):
    return g.first()   # first non-null value per column


# source-quality concerns recorded by both passes and the adjudicator (values kept as printed, flagged here)
SOURCE_QUALITY = {
    'D_32b9fbeca86cb72f': 'chlorophyll values implausibly high (10-36 mg/g FW); Fig 2A nearly identical to Fig 1 (dry weight)',
    'T102': 'chlorophyll measured in cotyledons, not true leaves; printed unit implausible',
    'D_04fa19ad49a5a820': 'inoculated and non-inoculated plants grown in separate glasshouses (treatment confounded with glasshouse)',
    'D_624b082fb2c061f5': 'humic acid always co-applied with copper oxychloride; contrasts against the weedy check are confounded by the fungicide',
}


def sig_digits(x):
    try:
        t = f'{float(x):.6g}'.split('e')[0].replace('-', '').replace('.', '').lstrip('0').rstrip('0')
        return len(t)
    except (TypeError, ValueError):
        return 9


def main():
    C = pd.read_csv(OUT / 'data' / f'{TAG}_contrasts.csv', dtype={'study_id': str})
    years, roles = {}, {}
    for f in (WORK / 'packets').glob('*.json'):
        pk = json.loads(f.read_text(encoding='utf-8'))
        years[pk['study_id']] = pk.get('year')
    C['year'] = C.study_id.map(years)
    # split integrity follows the frozen split (TRAIN_DEV vs EXTERNAL_TEST), not the printed issue year: a few TRAIN_DEV
    # articles were online in <= 2023 and printed later (e.g. study 83, DOI 10.1007/s13399-023-05103-x, issue 2025)
    import sqlite3
    tdb = os.environ.get('TFM_TEST_DB', str(pathlib.Path(__file__).resolve().parents[2] / '03_data_freeze' / 'external_test_DATA_FREEZE_20261118T105532769144Z' / 'TFM_DATABASE_CLASS_A_FINAL.sqlite'))   # unzip the release database here or set TFM_TEST_DB
    dois = {}
    for f in (WORK / 'packets').glob('*.json'):
        pk = json.loads(f.read_text(encoding='utf-8'))
        dois[pk['study_id']] = str(pk.get('doi') or '').lower()
    if pathlib.Path(tdb).exists():
        tc = sqlite3.connect(f'file:{tdb}?mode=ro', uri=True)
        T = pd.read_sql('select study_id, doi from studies', tc)
        test_ids, test_dois = set(T.study_id.astype(str)), set(T.doi.dropna().str.lower())
        if SPLIT == 'TRAIN':
            leak = sorted({s for s in C.study_id.unique() if s in test_ids or (dois.get(s) and dois[s] in test_dois)})
            assert not leak, f'EXTERNAL_TEST studies in TRAIN dataset: {leak}'
        else:                                            # TEST: every study must belong to the EXTERNAL_TEST database, none to TRAIN
            out = sorted(set(C.study_id) - test_ids)
            assert not out, f'non-TEST studies in TEST dataset: {out}'
            trdb = os.environ.get('TFM_TRAIN_DB', str(pathlib.Path(__file__).resolve().parents[2] / '03_data_freeze' / 'train_dev_DATA_FREEZE_20261113T112939135807Z' / 'TFM_DATABASE_CLASS_A_FINAL.sqlite'))
            TR = pd.read_sql('select doi from studies', sqlite3.connect(f'file:{trdb}?mode=ro', uri=True))
            ov = sorted({s for s in C.study_id.unique() if dois.get(s) and dois[s] in set(TR.doi.dropna().str.lower())})
            assert not ov, f'TEST studies whose DOI is in TRAIN_DEV: {ov}'
    else:
        raise SystemExit(f'TEST database not found for the split check: {tdb}')
    C['print_year_after_2023'] = (pd.to_numeric(C.year, errors='coerce') > 2023).astype(int)

    # ---- rule 2: one row per arm pair
    C['p_computed'] = C.computed.fillna('').str.contains('A_PLUS_B').astype(int)
    C['p_basis'] = C.basis.map(BASIS_PRI).fillna(9)
    C['p_var'] = C.variance_status.fillna('IMPUTED_CVBAR|IMPUTED_CVBAR').str.split('|').map(lambda x: max(VAR_PRI.get(v, 2) for v in x))
    C['p_src'] = ((C.source_t == 'FIGURE') | (C.source_c == 'FIGURE')).astype(int)
    C['p_meas'] = np.where(C.measure.isin(['CHL_TOTAL', 'SPAD']), 0, 1)
    key = ['study_id', 'experiment_key', 'endpoint', 'contrast_type', 'arm_key_t', 'arm_key_c']
    C = C.sort_values(key + ['p_meas', 'p_computed', 'p_basis', 'p_var', 'p_src'])
    C['dup_rank'] = C.groupby(key).cumcount()
    n_dup = int((C.dup_rank > 0).sum())
    C['is_primary'] = (C.dup_rank == 0).astype(int)

    # ---- rule 4: moderators from the same arms in the V6 marts
    M = pd.concat([pd.read_parquet(V6 / 'data' / f'{SP}_{e}_V6.parquet').assign(src_endpoint=e) for e in ['yield', 'dry_biomass']],
                  ignore_index=True)
    M['study_id'] = M.study_id.astype(str)
    ctx, treat, stress = moderator_columns(M)
    arm_t = first_non_null(M.groupby(['study_id', 'experiment_key', 'arm_key_t'])[ctx + treat + stress]).reset_index()
    exp_l = first_non_null(M.groupby(['study_id', 'experiment_key'])[ctx]).reset_index()
    stu_l = first_non_null(M.groupby(['study_id'])[ctx]).reset_index()
    D = C.merge(arm_t, on=['study_id', 'experiment_key', 'arm_key_t'], how='left', indicator='m_arm')
    D['moderator_level'] = np.where(D.m_arm == 'both', 'ARM', '')
    D = D.drop(columns='m_arm')
    for lev, T, on in [('EXPERIMENT', exp_l, ['study_id', 'experiment_key']), ('STUDY', stu_l, ['study_id'])]:
        miss = D.moderator_level == ''
        if miss.any():
            fill = D.loc[miss, on].merge(T, on=on, how='left')
            got = fill[ctx].notna().any(axis=1).values
            for c in ctx:
                D.loc[miss, c] = fill[c].values
            D.loc[miss[miss].index[got], 'moderator_level'] = lev
    D['moderator_level'] = D.moderator_level.replace('', 'NONE')
    # rule 3: no stress descriptors outside stressed contrasts
    D.loc[D.contrast_type == 'B_vs_C', stress] = np.nan
    # treatment descriptors only describe the biostimulant arm; S_vs_C has none
    D.loc[D.contrast_type == 'S_vs_C', treat] = np.nan
    # stress damage in chlorophyll itself (same experiment and stress code), a study-level moderator for SB_vs_S
    svc = C[(C.contrast_type == 'S_vs_C') & (C.is_primary == 1)].groupby(['study_id', 'experiment_key', 'endpoint', 'stress_code']).lnRR.mean()
    D['chl_lnrr_stress_SvsC'] = [svc.get((r.study_id, r.experiment_key, r.endpoint, r.stress_code), np.nan) if r.contrast_type == 'SB_vs_S' else np.nan
                                 for r in D.itertuples()]

    # ---- rule 5: non-biostimulants
    NB = pd.concat([pd.read_csv(V6 / 'results' / f'non_biostimulant_candidates_{SP}_{e}_V6.csv', dtype={'study_id': str})
                    for e in ['yield', 'dry_biomass']])
    nb = set(zip(NB.study_id, NB.experiment_key, NB.arm_key_t))
    D['excluded_reason'] = ['R2_NOT_A_BIOSTIMULANT' if (r.study_id, r.experiment_key, r.arm_key_t) in nb else '' for r in D.itertuples()]

    # ---- rule 8: flags
    # internal pigment inconsistency of the source (full run: Chl b printed above Chl a, printed total below Chl a,
    # usually a mislabelled unit or column); flagged per study and experiment, values are kept as printed
    VR = pd.read_csv(OUT / 'data' / f'{TAG}_values_with_roles.csv', dtype={'study_id': str}, low_memory=False)
    VR = VR[VR.computed.fillna('') == '']
    VR['tp'] = VR.tp.astype(str)
    pv = VR.pivot_table(index=['study_id', 'experiment_key', 'arm_key', 'tp'], columns='measure', values='mean', aggfunc='first')
    bad = pd.Series(False, index=pv.index)
    if {'CHL_A', 'CHL_B'} <= set(pv.columns):
        bad |= (pv.CHL_B > pv.CHL_A).fillna(False)
    if {'CHL_A', 'CHL_TOTAL'} <= set(pv.columns):
        bad |= (pv.CHL_TOTAL < pv.CHL_A).fillna(False)
    if {'CHL_A', 'CHL_B', 'CHL_TOTAL'} <= set(pv.columns):      # printed total far from a + b (full run: D_d73a0c43c80df3fc)
        ab = pv.CHL_A + pv.CHL_B
        bad |= ((pv.CHL_TOTAL > 1.25 * ab) | (pv.CHL_TOTAL < 0.8 * ab)).fillna(False)
    # systematic only (>= half of the arm x time points of the experiment): sporadic b > a can be physiological under stress
    share = bad.astype(float).groupby(level=[0, 1]).mean()
    incons = {i for i, v in share.items() if v >= 0.5}
    V6F = M.groupby(['study_id', 'experiment_key', 'arm_key_t']).v6_flags.apply(lambda s: ';'.join(sorted({x for v in s.dropna() for x in str(v).split(';') if x})))
    def flags(r):
        f = []
        if 'A_PLUS_B' in str(r.computed):
            f.append('TOTAL_COMPUTED_A_PLUS_B')
        if 'FIGURE' in (r.source_t, r.source_c):
            f.append('FIGURE_SOURCE')
        if abs(r.lnRR) > np.log(3):
            f.append('EXTREME_EFFECT')
        if 'IMPUTED' in str(r.variance_status):
            f.append('VARIANCE_IMPUTED')
        if 'USER_ASSUMED_SE' in str(r.variance_status):
            f.append('UNLABELLED_BARS_AS_SE')
        if pd.isna(r.n_t) or pd.isna(r.n_c):
            f.append('N_NOT_STATED')
        if (r.study_id, r.experiment_key) in incons and r.endpoint == 'CHL_CONTENT':
            f.append('SOURCE_PIGMENT_INCONSISTENT')
        if min(sig_digits(r.mean_t), sig_digits(r.mean_c)) < 2:     # e.g. totals printed as 0.01 (D_6b5d82abb9f7e388)
            f.append('MEAN_ROUNDED_LT_2_SIG_DIGITS')
        u = str(r.unit_raw).lower().replace(' ', '')
        if r.endpoint == 'CHL_CONTENT' and 'mg' in u and not any(x in u for x in ('µg', 'ug', 'mm', 'dm2', 'm2', 'cm')) and                 max(float(r.mean_t), float(r.mean_c)) > 10:
            f.append('UNIT_MAGNITUDE_IMPLAUSIBLE')      # > 10 mg/g: unit probably mislabelled; ratio (lnRR) unaffected
        if r.study_id in SOURCE_QUALITY:
            f.append('SOURCE_QUALITY_CONCERN')
        if r.print_year_after_2023:
            f.append('PRINT_YEAR_AFTER_2023_IN_FROZEN_TRAIN')
        if r.tp_outside_stress:
            f.append('TIMEPOINT_OUTSIDE_STRESS')
        v6 = V6F.get((r.study_id, r.experiment_key, r.arm_key_t), '')
        for x in ('STRESS_NOT_REALISED', 'PRODUCT_SUPPLIES_NUTRIENTS', 'SMALL_N_STRAIN_RANK_REVERSALS'):
            if x in v6 and (x != 'STRESS_NOT_REALISED' or r.contrast_type != 'B_vs_C'):
                f.append('V6_' + x)
        return ';'.join(f)
    if 'tp_outside_stress' not in D:
        D['tp_outside_stress'] = False
    D['chl_flags'] = D.apply(flags, axis=1)
    hard = ('EXTREME_EFFECT', 'SOURCE_QUALITY_CONCERN', 'MEAN_ROUNDED_LT_2_SIG_DIGITS', 'TIMEPOINT_OUTSIDE_STRESS', 'SOURCE_PIGMENT_INCONSISTENT', 'V6_STRESS_NOT_REALISED', 'V6_PRODUCT_SUPPLIES_NUTRIENTS', 'N_NOT_STATED')
    D['chl_reliability_flag'] = D.chl_flags.map(lambda s: int(any(h in s for h in hard)))

    # ---- rules 6, 7
    D['se_lnRR'] = np.sqrt(D.var_lnRR)
    D['w_ivw'] = 1 / D.var_lnRR
    D['cv_group'] = D.study_id
    D['dataset_role'] = 'TRAIN_DEV' if SPLIT == 'TRAIN' else 'EXTERNAL_TEST'
    D['in_default_chl'] = ((D.is_primary == 1) & (D.excluded_reason == '')).astype(int)
    D['in_quality_core_chl'] = ((D.in_default_chl == 1) & (D.chl_reliability_flag == 0)).astype(int)
    k = D[D.in_default_chl == 1].groupby(['study_id', 'endpoint', 'contrast_type']).lnRR.transform('size')
    D['w_train'] = np.nan
    D.loc[D.in_default_chl == 1, 'w_train'] = 1 / k
    D['pct_effect'] = 100 * (np.exp(D.lnRR) - 1)
    D = D.drop(columns=['p_computed', 'p_basis', 'p_var', 'p_src', 'p_meas'])
    D.to_csv(OUT / 'data' / f'chl_{SP}_dataset_V8.csv', index=False)
    for c in D.columns:
        if D[c].dtype == object:
            D[c] = D[c].astype(str).where(D[c].notna(), None)
    D.to_parquet(OUT / 'data' / f'chl_{SP}_dataset_V8.parquet', index=False)

    def block(df):
        return dict(rows=len(df), studies=int(df.study_id.nunique()))
    d = D[D.in_default_chl == 1]
    cov = {c: round(float(d[d.contrast_type == 'SB_vs_S'][c].notna().mean()), 3) for c in ctx + treat + stress}
    summ = {
        'input_contrasts': len(C), 'duplicates_removed_from_default': n_dup,
        'excluded_non_biostimulant': int((D.excluded_reason != '').sum()),
        'by_endpoint_contrast': {f'{ep}|{ct}': {'default': block(g[g.in_default_chl == 1]), 'quality_core': block(g[g.in_quality_core_chl == 1])}
                                 for (ep, ct), g in D.groupby(['endpoint', 'contrast_type'])},
        'moderator_level_SB_vs_S_content': d[(d.contrast_type == 'SB_vs_S') & (d.endpoint == 'CHL_CONTENT')].moderator_level.value_counts().to_dict(),
        'flags_default': d.chl_flags.str.split(';').explode().replace('', np.nan).dropna().value_counts().to_dict(),
        'moderators_with_coverage_ge_50pct_SB_vs_S': sorted([c for c, v in cov.items() if v >= 0.5]),
        'n_moderator_columns': len(cov)}
    (OUT / 'results' / f'chl_dataset_summary_V8{"" if SPLIT == "TRAIN" else "_test"}.json').write_text(json.dumps(summ, indent=1, default=str), encoding='utf-8')
    print(json.dumps({k: v for k, v in summ.items() if k != 'moderators_with_coverage_ge_50pct_SB_vs_S'}, indent=1, default=str))


if __name__ == '__main__':
    main()
