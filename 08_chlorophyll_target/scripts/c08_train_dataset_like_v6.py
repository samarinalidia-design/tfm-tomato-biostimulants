"""Chlorophyll TRAIN dataset in the SAME structure and with the SAME feature code as the yield / dry-biomass TRAIN tables.

1. Contrasts: chl_train_dataset_V8 (c06): SB_vs_S and B_vs_C (the contrast types of the yield / biomass tables), S_vs_C
   kept only as the stress-damage moderator (as V5 attach_svc). Endpoints: CHL_CONTENT (main target) and CHL_INDEX (separate).
2. Moderators: A399 `moderators` (freeze db_moderators) + the moderators extracted for the chlorophyll-only studies
   (work/moderators/<study>.json; every row's verbatim must be found in the PDF text, otherwise the row is dropped).
   f_* / context_* columns are built with the exact rule of the A399 export (tfmlib/export.py build_frames): levels study ->
   experiment -> arm, later level overrides, disagreeing values inside one group empty the feature, numeric features parsed,
   availability PLAN_PRE_EXPERIMENT -> f_, otherwise context_. The rule is first validated by rebuilding the f_* columns of
   the V6 yield table (agreement reported).
3. Features: the V5 feature code itself (v5_01_build.features: harmonize, stress_v5, hybrid_v5, 07_features_v2, 11_features_v3),
   with db_arms / db_moderators extended by the new arms and moderators. Endpoint branch 'biomass' (no yield-specific parts).
4. Outcome-definition columns (counterpart of organ_scope / is_terminal for biomass): chl_basis, chl_measure_kind,
   is_computed_total, is_terminal, timepoint_days.
5. Variance: var_lnRR of c05 (SD / SE x sqrt(n) / UNLABELLED as SE / CV-bar imputation) -> var_lnrr_imp. dependency_cluster_id
   from the freeze contrast_candidates (study -> cluster), else the study itself. w_n = 1 / contrasts of the study (equal study
   weight, used through the engine's 'n' weight scheme for all three targets).
Outputs: data/train_chlorophyll_V8.parquet (CHL_CONTENT), data/train_chl_index_V8.parquet, results/c08_build_report.json
"""
import json, os, pathlib, re, sys, importlib.util
import numpy as np
import pandas as pd

OUT = pathlib.Path(__file__).resolve().parents[1]
REPO = OUT.parent
WORK = pathlib.Path(os.environ.get('CHL_WORK', r"C:/Users/lenovo/Desktop/master's/TFM_CHLOROPHYLL_PILOT/work"))
SPLIT = os.environ.get('CHL_SPLIT', 'TRAIN')
SP = 'train' if SPLIT == 'TRAIN' else 'test'
FREEZE = REPO / '03_data_freeze' / ('train_dev_DATA_FREEZE_20261113T112939135807Z' if SPLIT == 'TRAIN' else 'external_test_DATA_FREEZE_20261118T105532769144Z')
V5S = REPO / '05_analysis_train_expansion_v5' / 'v5' / 'scripts'
NUMERIC = {'soil_ph', 'soil_ec', 'organic_matter', 'pot_volume_l', 'plant_density_m2', 'latitude', 'temperature_day_c', 'temperature_night_c',
           'relative_humidity', 'vpd_kpa', 'photoperiod_h', 'ppfd', 'stress_duration_days', 'nacl_mm', 'ec_irrigation_ds_m',
           'field_capacity_pct', 'dose', 'n_applications', 'days_application_before_stress', 'n_replicates'}


def numeric_feature(feature, value, unit):            # = tfmlib/export.py _numeric_feature
    import math
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    if 'days' in feature:
        u = (unit or '').strip().lower()
        if u in ('h', 'hr', 'hrs', 'hour', 'hours'):
            v /= 24.0
        elif u not in ('', 'd', 'day', 'days', 'dap', 'dat', 'das'):
            return None
    if feature == 'plant_density_m2' and re.search(r'\bha\b|hectare', (unit or '').lower()):
        v /= 10000.0
    return v


def mod_groups(M):
    """= tfmlib/export.py build_frames, moderator part."""
    mods = {}
    for m in M.sort_values('mod_order').to_dict('records'):
        d = mods.setdefault((str(m['study_id']), m['experiment_key'] or '', m['arm_key'] or ''), {})
        prefix = 'f_' if m['availability'] == 'PLAN_PRE_EXPERIMENT' else 'context_'
        if m['feature'] in ('stress_intensity', 'stress_intensity_unit'):
            prefix = 'context_'
        value = m['value']
        if m['feature'] in NUMERIC and prefix == 'f_':
            d['context_' + m['feature'] + '_raw'] = value
            value = numeric_feature(m['feature'], value, m['unit'])
        key = prefix + m['feature']; all_key = 'context_' + m['feature'] + '_all'
        d[all_key] = json.dumps(sorted(set(json.loads(d.get(all_key, '[]'))) | {str(m['value'])}), ensure_ascii=False)
        d[key] = None if key in d and d[key] != value else value
        if m['unit']:
            d[key + '_unit'] = m['unit']
    return mods


def attach(rows, mods):
    out = []
    for r in rows.to_dict('records'):
        x = {}
        s, e, a = str(r['study_id']), r.get('experiment_key') or '', r['arm_key_t']
        for key in [(s, '', ''), (s, e, ''), (s, '', a), (s, e, a)]:
            x.update(mods.get(key, {}))
        out.append(x)
    return pd.DataFrame(out, index=rows.index)


def norm_txt(t):
    return re.sub(r'[^a-z0-9]+', '', str(t).lower())


def load_new_moderators(availability_by_feature):
    """Agent-extracted moderators; a row is kept only if its verbatim occurs in the text of the cited PDF page (or anywhere
    in the registered files of the study)."""
    import fitz
    rows, report = [], []
    for f in sorted((WORK / 'moderators').glob('*.json')):
        d = json.loads(f.read_text(encoding='utf-8-sig'))
        sid = str(d['study_id'])
        pk = json.loads((WORK / 'packets' / f'{sid}.json').read_text(encoding='utf-8'))
        pages = {}
        for fl in pk['files']:
            if not fl['file_name'].lower().endswith('.pdf') or not pathlib.Path(fl['local_path']).exists():
                continue
            doc = fitz.open(fl['local_path'])
            for i, p in enumerate(doc):
                pages[(fl['file_name'], i + 1)] = norm_txt(p.get_text())
        alltxt = ''.join(pages.values())
        ok = bad = 0
        vf = WORK / 'moderators_verify' / f'{sid}.json'          # rows confirmed on the page image by an independent verifier
        confirmed = set(json.loads(vf.read_text(encoding='utf-8')).get('confirmed_row_indices', [])) if vf.exists() else set()
        for i, r in enumerate(d.get('rows', [])):
            v = norm_txt(r.get('verbatim', ''))
            found = len(v) >= 8 and (v in alltxt or v[:60] in alltxt)
            image_only = False
            if not found:                   # cited page has (almost) no text layer: verbatim read from the rendered image
                pg = r.get('page')
                image_only = any(k[1] == pg and len(t) < 200 for k, t in pages.items()) or i in confirmed
                if not image_only:
                    bad += 1; continue
            ok += 1
            rows.append(dict(study_id=sid, experiment_key=r.get('experiment_key') or None, arm_key=r.get('arm_key') or None,
                             feature=r['feature'], value=None if r.get('value') is None else str(r['value']), unit=r.get('unit') or None,
                             availability=availability_by_feature.get(r['feature'], 'PLAN_PRE_EXPERIMENT'),
                             mod_order=10_000_000 + i, source='CHL_V8_AGENT_IMAGE_PAGE' if image_only else 'CHL_V8_AGENT'))
        report.append(dict(study_id=sid, rows_kept=ok, rows_dropped_verbatim_not_found=bad))
    return pd.DataFrame(rows), pd.DataFrame(report)


def main():
    MOD = pd.read_parquet(FREEZE / 'db_moderators.parquet')
    MOD['study_id'] = MOD.study_id.astype(str)
    MOD['mod_order'] = pd.to_numeric(MOD.mod_id, errors='coerce')
    avail = MOD.groupby('feature').availability.agg(lambda s: s.value_counts().index[0]).to_dict()
    NEW, newrep = load_new_moderators(avail)
    allM = pd.concat([MOD[['study_id', 'experiment_key', 'arm_key', 'feature', 'value', 'unit', 'availability', 'mod_order']], NEW],
                     ignore_index=True)
    # A399 moderators (source-adjudicated) win: a new row is used only for a (study, feature) absent from A399
    if len(NEW):
        have = set(zip(MOD.study_id, MOD.feature))
        NEW = NEW[[(s, f) not in have for s, f in zip(NEW.study_id, NEW.feature)]].reset_index(drop=True)
        allM = pd.concat([MOD[['study_id', 'experiment_key', 'arm_key', 'feature', 'value', 'unit', 'availability', 'mod_order']], NEW],
                         ignore_index=True)
    mods = mod_groups(allM.where(allM.notna(), None))

    # ---- validation of the rule on the V6 yield table
    Y6 = pd.read_parquet(REPO / '06_database_corrections_v6' / 'data' / 'train_yield_V6.parquet')
    Y6['study_id'] = Y6.study_id.astype(str)
    mods_db = mod_groups(MOD.where(MOD.notna(), None))
    R = attach(Y6, mods_db)
    val = {}
    for c in ['f_cultivar', 'f_dose', 'f_route', 'f_stress_type', 'f_biostimulant_class', 'f_composition', 'f_microorganism',
              'f_n_applications', 'f_system', 'f_country', 'f_latitude', 'f_application_stage', 'f_dose_unit']:
        a = Y6[c].astype(str).replace({'nan': 'None'}).str.replace(r'\.0$', '', regex=True)
        b = R.get(c, pd.Series(None, index=R.index)).astype(str).replace({'nan': 'None'}).str.replace(r'\.0$', '', regex=True)
        val[c] = round(float((a == b).mean()), 4)

    # ---- chlorophyll contrasts
    D = pd.read_parquet(OUT / 'data' / f'chl_{SP}_dataset_V8.parquet')
    keep = D.contrast_type.isin(['SB_vs_S', 'B_vs_C']) & D.endpoint.isin(['CHL_CONTENT', 'CHL_INDEX'])
    X = D[keep].copy().reset_index(drop=True)
    X = X[[c for c in X.columns if not re.match(r'^(h_|h2_|h3_|v6_)', c)]]          # moderators are rebuilt below
    F = attach(X, mods)
    for c in F.columns:
        X[c] = F[c].values
    # columns the V5 feature code expects
    X['contrast_id'] = 'CHL_' + pd.util.hash_pandas_object(X[['study_id', 'experiment_key', 'endpoint', 'measure', 'arm_key_t', 'arm_key_c', 'timepoint']].astype(str), index=False).astype(str)
    X['effect'] = X.lnRR; X['var_effect'] = X.var_lnRR; X['var_lnrr_imp'] = X.var_lnRR
    X['is_terminal_t'] = 1; X['is_terminal_c'] = 1
    X['timepoint_days'] = pd.to_numeric(X.timepoint, errors='coerce')
    X['timepoint_key'] = X.timepoint.astype(str)
    X['flags'] = '[]'
    cc = pd.read_parquet(FREEZE / 'contrast_candidates.parquet', columns=['study_id', 'dependency_cluster_id'])
    cl = cc.assign(study_id=cc.study_id.astype(str)).drop_duplicates('study_id').set_index('study_id').dependency_cluster_id
    X['dependency_cluster_id'] = X.study_id.map(cl).fillna('CHLCL_' + X.study_id)
    Y5 = pd.read_parquet(REPO / '05_analysis_train_expansion_v5' / 'v5' / 'data' / 'train_dry_biomass.parquet')
    for c in Y5.columns:                               # every column of the biomass table exists (NaN where not applicable)
        if c not in X.columns:
            X[c] = np.nan
    for c in [c for c in X.columns if c.startswith(('f_', 'context_'))]:
        X[c] = X[c].astype(object).where(X[c].notna(), None)

    # ---- V5 feature code, with db_arms / db_moderators extended
    sys.path.insert(0, str(V5S)); sys.path.insert(0, str(REPO / '05_analysis_train_expansion_v5' / 'scripts'))
    spec = importlib.util.spec_from_file_location('v5_01_build', V5S / 'v5_01_build.py')
    B5 = importlib.util.module_from_spec(spec); spec.loader.exec_module(B5)
    ARMS = pd.read_parquet(FREEZE / 'db_arms.parquet')
    new_arms = pd.read_sql_query if False else None
    na = X[['study_id', 'arm_key_t']].drop_duplicates().rename(columns={'arm_key_t': 'arm_key'})
    na = na[~na.set_index(['study_id', 'arm_key']).index.isin(ARMS.assign(study_id=ARMS.study_id.astype(str)).set_index(['study_id', 'arm_key']).index)]
    ARMS_X = pd.concat([ARMS, na], ignore_index=True)
    MOD_X = pd.concat([MOD, NEW.drop(columns=['source'], errors='ignore')], ignore_index=True) if len(NEW) else MOD

    def _load_v2_module(freeze):
        f = REPO / '05_analysis_train_expansion_v5' / 'scripts' / '07_features_v2.py'
        src = f.read_text(encoding='utf-8').split('\nAUDIT = []')[0]
        src = src.replace("F = ROOT.parent / 'TFM_A399_Agent_System_v2_2_2026-10-19/TFM_AGENT_SYSTEM_v2_2/exports/DATA_FREEZE_20261113T112939135807Z'",
                          f"F = pathlib.Path({str(FREEZE)!r})")
        ns = {'__file__': str(f), '__name__': 'v2'}
        exec(compile(src, '07_features_v2', 'exec'), ns)
        ns['ARMS'] = ARMS_X; ns['MOD'] = MOD_X
        return ns
    B5.load_v2_module = _load_v2_module
    X['study_id'] = X.study_id.astype(str)
    X = B5.features(X, FREEZE, 'biomass')

    # ---- outcome-definition columns and weights
    X['chl_basis'] = X.basis.fillna('UNSPECIFIED')
    X['chl_measure_kind'] = np.where(X.measure == 'CHL_TOTAL', np.where(X.computed.fillna('').str.contains('A_PLUS_B'), 'A_PLUS_B', 'PRINTED_TOTAL'), X.measure)
    X['is_computed_total'] = X.computed.fillna('').str.contains('A_PLUS_B').astype(int)
    X['in_default'] = X.in_default_chl
    X['in_quality_core'] = X.in_quality_core_chl
    X['w_n'] = 1.0 / X.groupby(['study_id', 'endpoint']).lnRR.transform('size')
    X['dataset_role'] = 'TRAIN_DEV' if SPLIT == 'TRAIN' else 'EXTERNAL_TEST'
    rep = {'rule_validation_on_V6_yield_agreement': val, 'new_moderator_rows': int(len(NEW)),
           'new_moderator_report': newrep.to_dict('records') if len(newrep) else []}
    for ep, name in [('CHL_CONTENT', f'{SP}_chlorophyll_V8'), ('CHL_INDEX', f'{SP}_chl_index_V8')]:
        Z = X[X.endpoint == ep].reset_index(drop=True)
        for c in Z.columns:
            if Z[c].dtype == object:
                Z[c] = Z[c].map(lambda v: v if v is None or isinstance(v, str) else (json.dumps(v) if isinstance(v, (list, dict)) else str(v)))
        Z.to_parquet(OUT / 'data' / f'{name}.parquet', index=False)
        d = Z[Z.in_default == 1]
        rep[name] = dict(rows=len(Z), default_rows=len(d), default_studies=int(d.study_id.nunique()),
                         by_type=d.contrast_type.value_counts().to_dict(),
                         coverage_default={c: round(float(d[c].notna().mean()), 3) for c in
                                           ['h2_dujardin', 'h_stress_class', 'h_route', 'h_system', 'h_log10_dose', 'f_cultivar', 'f_country',
                                            'h_stress_intensity', 'f_latitude', 'h3_taxon_bacillus']})
        if 'h_stress_class' in d:
            rep[name]['stress_class_SBvsS'] = d[d.contrast_type == 'SB_vs_S'].h_stress_class.value_counts().to_dict()
            rep[name]['dujardin'] = d.h2_dujardin.value_counts().to_dict()
    (OUT / 'results' / f'c08_build_report{"" if SPLIT == "TRAIN" else "_test"}.json').write_text(json.dumps(rep, indent=1, default=str, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(rep, indent=1, default=str, ensure_ascii=False)[:6000])


if __name__ == '__main__':
    main()
