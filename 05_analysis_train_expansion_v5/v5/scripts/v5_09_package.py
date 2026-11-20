"""V5 step 9: package the version - Excel workbooks (TRAIN/TEST + dictionary + corrections), data dictionary CSV,
SHA-256 manifest of every file in v5/ (data, code, results, figures, freeze)."""
import hashlib, json, datetime, pathlib
import pandas as pd

V5 = pathlib.Path(__file__).resolve().parents[1]; ROOT = V5.parent
D = V5 / 'data'; R = V5 / 'results'; F = V5 / 'figures'
V5_COLS = {
    'v5_stress_declared': 'Author-declared stress kept for transparency when V5 reclassified the stress (e.g. 112 SALINITY_AUTHOR_DECLARED_SOIL_EC_1.2_mS_cm).',
    'v5_correction': 'V5 correction codes applied to the contrast (STRESS_DISPUTED, NO_STRESS_RECODED).',
    'v5_measurement_year': 'Measurement (harvest) year taken from the timepoint key where it carries the year (717, D_068b..., D_0e4b...).',
    'v5_fractions_summed': 'Number of fruit-size fractions summed into this total-yield contrast (SD not summed; variance imputed).',
    'h_stress_class': 'V5 harmonised stress class: NONE, SALINITY, DROUGHT, HEAT, COLD, NUTRIENT, HEAVY_METAL, CHEMICAL_TOXICITY, BIOTIC, '
                      'ALKALINITY_CALCAREOUS, LIGHT_UV_OZONE, FLOOD_HYPOXIA, OTHER_MANAGEMENT, COMBINED (>= 2 families). Fixed V4 rule bugs '
                      "('ht_' matched 'drought_'; 'nutrient solution' read as nutrient stress; 'wilting' read as disease).",
    'h_stress_families': "All stress families detected in the stress code, joined with '+'.",
    'h_hybrid': 'HYBRID only with explicit hybrid/F1 evidence; OP_CULTIVAR_LINE only with explicit open-pollinated/landrace/heirloom/inbred evidence; else UNSPECIFIED.',
    'h3_hybrid': '1 = hybrid, 0 = explicit OP/landrace, NaN = unknown (V4 coded unknown as 0).',
    'h3_experiment_year': 'Experiment year: measurement year from the timepoint key if present, else parsed from the season text.',
    'h3_experiment_year_source': 'TIMEPOINT_KEY | SEASON_TEXT | MISSING.',
    'h3_latitude_source': 'PRINTED (coordinates in the paper) | COUNTRY_CENTROID (centre of the country, approximate) | MISSING.',
    'h3_cultivar_key': 'Normalised cultivar name; UNSPECIFIED when not reported (never guessed).',
    'dataset_role_v5': 'TRAIN (TRAIN_DEV freeze 2026-11-13) or TEST (EXTERNAL_TEST freeze 2026-11-18).',
    'var_lnrr_imp': 'Sampling variance of lnRR. Author SD/SE where reported; otherwise study-printed CV%/LSD; otherwise the mean CV (CV-bar, Nakagawa et al. 2023) '
                    'estimated on TRAIN only. Imputed variances are NOT reported by the authors.',
    'variance_status': 'AUTHOR_SD_SE | STUDY_PRINTED_CV_OR_LSD_OR_N_IMPUTED | IMPUTED_MEAN_CV_NOT_AUTHOR_REPORTED.',
}


def dictionary():
    old = pd.read_csv(ROOT / 'data/processed/new_columns_dictionary.csv')
    base = pd.read_csv(ROOT / 'data/raw/data_dictionary.csv')
    base = base.drop_duplicates('column')
    base = pd.DataFrame({'column': base.column, 'description': 'freeze column; table=' + base.table.astype(str) + ', role=' + base.role.astype(str) +
                         ', dtype=' + base.dtype.astype(str), 'source': 'freeze data_dictionary.csv'})
    old = old.assign(source='TFM_TRAIN_EXPANSION rounds 1-7')
    new = pd.DataFrame([{'column': k, 'description': v, 'source': 'V5'} for k, v in V5_COLS.items()])
    d = pd.concat([new, old, base]).drop_duplicates('column', keep='first')
    cols = set(pd.read_parquet(D / 'train_yield.parquet').columns) | set(pd.read_parquet(D / 'train_dry_biomass.parquet').columns)
    d['in_v5_tables'] = d.column.isin(cols)
    d.to_csv(D / 'data_dictionary_V5.csv', index=False, encoding='utf-8-sig')
    return d


def workbooks(d):
    reg = pd.read_csv(D / 'corrections_register.csv')
    flow = pd.read_csv(R / 'build_flow_v5.csv')
    readme = pd.DataFrame({'item': ['version', 'TRAIN source', 'TEST source', 'selection', 'variance', 'TEST label', 'S_vs_C', 'unknowns'],
                           'value': ['V5, 2026-11-20', 'DATA_FREEZE_20261113T112939135807Z (TRAIN_DEV, read only)',
                                     'DATA_FREEZE_20261118T105532769144Z (EXTERNAL_TEST, read only)',
                                     'identical definitions and selection rules for TRAIN and TEST (see build_flow)',
                                     'var_lnrr_imp: author SD where reported, otherwise imputed (CV-bar from TRAIN) - imputed values are not author-reported',
                                     'POST_HOC_TEST_REUSE: TEST was used in earlier versions',
                                     'mod_lnrr_stress_SvsC is an outcome of the experiment: meta-regression moderator only, never an ML feature',
                                     'cultivar UNSPECIFIED, hybrid UNSPECIFIED/NaN, latitude COUNTRY_CENTROID flagged; nothing invented']})
    for ep, name in [('yield', 'YIELD'), ('dry_biomass', 'DRY_BIOMASS')]:
        out = V5 / f'SynerPlant_{name}_TRAIN_TEST_V5.xlsx'
        with pd.ExcelWriter(out, engine='openpyxl') as w:
            readme.to_excel(w, 'README', index=False)
            for role in ('train', 'test'):
                x = pd.read_parquet(D / f'{role}_{ep}.parquet').drop(columns=['h3_text_all'], errors='ignore')
                x.to_excel(w, role.upper(), index=False)
                i = D / f'{role}_{ep}_interactions.parquet'
                if i.exists():
                    pd.read_parquet(i).to_excel(w, f'{role.upper()}_interactions', index=False)
            reg.to_excel(w, 'corrections_register', index=False)
            flow[flow.table == ('yield' if ep == 'yield' else 'biomass')].to_excel(w, 'build_flow', index=False)
            d.to_excel(w, 'dictionary', index=False)
        print('written', out.name)


def manifest():
    rows = []
    for p in sorted(V5.rglob('*')):
        if p.is_file() and not p.name.startswith('_') and p.suffix not in ('.pyc',) and 'MANIFEST' not in p.name:
            rows.append(dict(path=str(p.relative_to(V5)).replace('\\', '/'), bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    pd.DataFrame(rows).to_csv(V5 / 'MANIFEST_V5_sha256.csv', index=False)
    print(len(rows), 'files in manifest')


if __name__ == '__main__':
    d = dictionary(); workbooks(d); manifest()
