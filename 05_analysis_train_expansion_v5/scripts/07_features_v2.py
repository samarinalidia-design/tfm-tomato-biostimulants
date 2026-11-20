"""Feature representation v2 (user review 2026-11-19, points 3-5). Adds h2_* columns; v1 columns untouched.

3. Representation fixes
   - cell-free filtrates / supernatants / microbial extracts are NOT live microorganisms
     -> DJ_MICROBIAL_DERIVED_NONLIVING, h2_live_microorganism = 0;
   - a single preparation is never a "mixture": the number of components comes from db_arms.n_bio_components,
     MIXTURE only if >= 2 components spanning >= 2 du Jardin categories;
   - stress-specific numerics distinguish NOT_APPLICABLE from NOT_REPORTED and keep the measurement type:
       drought water supply: % FC (incl. SFC/WHC/WC) and % ETc/irrigation dose are separate columns;
       salinity: NaCl concentration (mM) and measured ECw (dS/m) are separate columns, + measure type;
       non-drought rows get 100 % supply, non-saline rows 0 (= physically "no stress"), and a
       *_reported flag is computed only inside the relevant stress context.
4. Extra design factors from existing verified text (no re-extraction):
   development phase at application and at stress onset; stress duration (unit-converted);
   substrate type; soil EC unit-normalised; planting density from printed density, plants/ha, or
   spacing geometry (provenance kept in h2_density_source; pots = NOT_APPLICABLE).
5. Outcome definitions: yield_scope / harvest_window UNSPECIFIED refined only when the printed
   locator text states it (flag h2_definition_refined_from_locator).
"""
import re, json, pathlib
import numpy as np
import pandas as pd
from harmonize import DJ_RULES, DJ_OTHER, DJ_MICROBIAL, _txt

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROC, RES = ROOT / 'data/processed', ROOT / 'results'
F = ROOT.parent / 'TFM_A399_Agent_System_v2_2_2026-10-19/TFM_AGENT_SYSTEM_v2_2/exports/DATA_FREEZE_20261113T112939135807Z'
ARMS = pd.read_parquet(F / 'db_arms.parquet')
MOD = pd.read_parquet(F / 'db_moderators.parquet')

NONLIVING = r'cell-free|cell free|filtrate|supernatant|heat-killed|heat killed|autoclaved|dead cells|bacterial water extract|microbial-derived|culture broth extract|secondary metabolite'


def num(s):
    return pd.to_numeric(s, errors='coerce')


# ------------------------------------------------------------------ 3a/3b biostimulant identity
def dujardin_v2(x):
    cls = _txt(x, ['f_biostimulant_class'])
    t1 = _txt(x, ['f_biostimulant_class', 'bio_code'])
    t = _txt(x, ['f_biostimulant_class', 'bio_code', 'f_microorganism', 'f_composition', 'f_strain'])
    j = x[['study_id', 'arm_key_t']].merge(ARMS[['study_id', 'arm_key', 'n_bio_components', 'component_codes']],
                                           left_on=['study_id', 'arm_key_t'], right_on=['study_id', 'arm_key'], how='left')
    ncomp = j.n_bio_components.values
    nonliving = cls.str.contains(NONLIVING, regex=True) | (t1.str.contains(r'\bcf\b|cfcl|\bwe\b', regex=True) & cls.str.contains('microbial-derived|filtrate|extract'))
    prim, nh = [], []
    for i, (a, b, full, nl, nc) in enumerate(zip(cls, t1, t, nonliving, ncomp)):
        src = b if any(re.search(p, b) for _, p in DJ_RULES) else full
        hits = [(m.start(), c) for c, p in DJ_RULES for m in [re.search(p, src)] if m]
        cats = sorted(set(c for _, c in hits))
        nh.append(len(cats))
        if nl:
            prim.append('DJ_MICROBIAL_DERIVED_NONLIVING'); continue
        if not cats:
            if re.search(DJ_OTHER, full):
                prim.append('DJ_OTHER_NON_DUJARDIN')
            elif re.search(DJ_MICROBIAL, full):
                prim.append('DJ_MICROBIAL_UNSPECIFIED')
            else:
                prim.append('DJ_UNCLASSIFIED')
            continue
        if (nc != nc or nc <= 1) or len(cats) == 1:
            # single preparation: category named first in the curated label
            prim.append(min(hits)[1])
        else:
            prim.append('DJ_MIXTURE')
    out = pd.DataFrame(index=x.index)
    out['h2_dujardin'] = prim
    out['h2_n_components'] = ncomp
    live = out.h2_dujardin.isin(['DJ_BENEFICIAL_FUNGI', 'DJ_BENEFICIAL_BACTERIA', 'DJ_MICROBIAL_UNSPECIFIED']) | \
        ((out.h2_dujardin == 'DJ_MIXTURE') & t.str.contains(r'mycorrh|amf|glomus|trichoderma|pgpr|pgpb|bacillus|pseudomonas|azotobacter|azospirillum|rhizobi|inocul', regex=True))
    out['h2_live_microorganism'] = (live & ~nonliving.values).astype(int)
    out['h2_nonliving_microbial_product'] = nonliving.astype(int).values
    return out


# ------------------------------------------------------------------ 3c stress-context numerics
def stress_v2(x):
    out = pd.DataFrame(index=x.index)
    cls = x.h_stress_class
    sc = x.stress_code.astype(str)
    dr, sal, none = cls == 'DROUGHT', cls == 'SALINITY', cls == 'NONE'
    # --- drought supply, typed
    u = (x.f_field_capacity_pct_unit.astype(str) + ' ' + x.f_irrigation_regime_unit.astype(str)).str.lower()
    fc_val = num(x.f_field_capacity_pct)
    code_fc = num(sc.str.extract(r'(?i)(\d+(?:\.\d+)?)\s*(?:pct)?_?(?:fc|sfc|whc)\b', expand=False))
    code_etc = num(sc.str.extract(r'(?i)(\d+(?:\.\d+)?)\s*(?:pct)?_?etc', expand=False))
    code_di = num(sc.str.extract(r'(?i)di_?(\d+)\s*pct', expand=False))
    is_etc_unit = u.str.contains(r'etc|evapotransp|crop water requirement')
    fc = code_fc.copy(); etc = code_etc.copy().fillna(code_di)
    fc = fc.fillna(fc_val.where(~is_etc_unit)); etc = etc.fillna(fc_val.where(is_etc_unit))
    t = pd.Series('UNKNOWN_TYPE', index=x.index)
    t[fc.notna()] = 'FIELD_CAPACITY_PCT'; t[etc.notna() & fc.isna()] = 'ETC_OR_IRRIGATION_PCT'
    t[~dr] = 'NOT_APPLICABLE'
    out['h2_drought_supply_type'] = t
    out['h2_drought_fc_pct'] = np.where(dr, fc, 100.0)          # not drought -> full supply
    out['h2_drought_etc_pct'] = np.where(dr, etc, 100.0)
    out.loc[dr & out.h2_drought_fc_pct.isna() & etc.notna(), 'h2_drought_fc_pct'] = np.nan
    out['h2_drought_supply_reported'] = np.where(dr, (fc.notna() | etc.notna()).astype(float), np.nan)
    # --- salinity, typed
    nacl = num(x.f_nacl_mm)
    nacl = nacl.fillna(num(sc.str.extract(r'(?i)nacl[_ ]?(\d+(?:\.\d+)?)\s*mm', expand=False)))
    pct = num(sc.str.extract(r'(?i)nacl[_ ]?(\d+(?:\.\d+)?)\s*pct', expand=False))
    gl = num(sc.str.extract(r'(?i)nacl[_ ]?(\d+(?:\.\d+)?)\s*g_?l', expand=False))
    nacl = nacl.fillna(pct * 171.1).fillna(gl * 17.11)
    ecu = x.f_ec_irrigation_ds_m_unit.astype(str).str.lower()
    ecw = num(x.f_ec_irrigation_ds_m)
    ecw = np.where(ecu.str.contains(r'us|µs|μs'), ecw / 1000.0, ecw)
    ecw = pd.Series(ecw, index=x.index).fillna(num(sc.str.extract(r'(?i)ec[_ ]?(\d+(?:\.\d+)?)', expand=False)))
    st = pd.Series('UNKNOWN_TYPE', index=x.index)
    st[ecw.notna()] = 'EC_WATER_MEASURED'; st[nacl.notna()] = 'NACL_CONCENTRATION'
    st[nacl.notna() & ecw.notna()] = 'NACL_AND_EC'
    st[~sal] = 'NOT_APPLICABLE'
    out['h2_salinity_measure_type'] = st
    out['h2_salinity_nacl_mm'] = np.where(sal, nacl, 0.0)
    out['h2_salinity_ecw_dsm'] = np.where(sal, ecw, 0.0)
    out['h2_salinity_reported'] = np.where(sal, (nacl.notna() | ecw.notna()).astype(float), np.nan)
    # --- duration (all stresses), unit converted
    d = num(x.f_stress_duration_days); du = x.f_stress_duration_days_unit.astype(str).str.lower()
    mult = np.select([du.str.contains('week'), du.str.contains('month'), du.str.match(r'^h\b|hour')], [7.0, 30.4, 1 / 24], 1.0)
    dd = d * mult
    out['h2_stress_duration_days'] = np.where(none, 0.0, dd)
    out['h2_stress_duration_reported'] = np.where(none, np.nan, dd.notna().astype(float))
    # application relative to stress, unit converted
    a = num(x.f_days_application_before_stress); au = x.f_days_application_before_stress_unit.astype(str).str.lower()
    a = a * np.where(au.str.match(r'^h\b|hour'), 1 / 24, 1.0)
    out['h2_days_application_before_stress'] = np.where(none, np.nan, a)
    return out


# ------------------------------------------------------------------ 4. phases, substrate, density
PHASES = [('SEED', r'seed|sowing|priming|germinat'), ('NURSERY_SEEDLING', r'nursery|seedling|transplant(?:ing)? (?:stage|time)?|before transplant|plug|tray|\d+[- ]?leaf|true leaf'),
          ('TRANSPLANT', r'transplant|planting'), ('VEGETATIVE', r'vegetative|after transplant|dat\b|days after transplant'),
          ('FLOWERING', r'flower|anthesis|bloom'), ('FRUITING', r'fruit set|fruiting|fruit development|ripen|harvest')]


def phase(text, none_mask=None):
    t = text.astype(str).str.lower()
    out = pd.Series('UNSPECIFIED', index=text.index)
    n = pd.Series(0, index=text.index)
    for name, p in PHASES:
        m = t.str.contains(p, regex=True)
        out[m & (out == 'UNSPECIFIED')] = name
        n += m.astype(int)
    out[(n >= 3)] = 'MULTIPLE_STAGES'
    out[t.isin(['nan', 'none', ''])] = 'UNSPECIFIED'
    if none_mask is not None:
        out[none_mask] = 'NOT_APPLICABLE'
    return out


def substrate(x):
    t = _txt(x, ['f_substrate', 'f_system'])
    s = np.select([t.str.contains(r'rockwool|perlite|vermiculite|coco|hydropon|nutrient solution|soilless|inert'),
                   t.str.contains(r'peat|potting|compost mix|commercial substrate|growing medium|mix'),
                   t.str.contains(r'steril|autoclav|pasteur'),
                   t.str.contains(r'sand'),
                   t.str.contains(r'soil|field|loam|clay')],
                  ['SOILLESS_INERT', 'PEAT_POTTING_MIX', 'STERILISED_SOIL', 'SAND_OR_SANDY', 'FIELD_OR_NATURAL_SOIL'], 'UNSPECIFIED')
    ec = num(x.f_soil_ec); eu = x.f_soil_ec_unit.astype(str).str.lower()
    ec = np.where(eu.str.contains(r'us|µs|μs'), ec / 1000.0, ec)
    return pd.Series(s, index=x.index), pd.Series(ec, index=x.index)


def parse_density(text):
    """plants per m2 from printed density / spacing geometry; returns (value, source) or (nan, '')."""
    if not isinstance(text, str) or not text.strip():
        return np.nan, ''
    s = text.lower().replace(',', '').replace('×', 'x')
    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:plants?|seedlings?)\s*(?:per|/)\s*(?:a\s*)?(\d+(?:\.\d+)?)\s*(?:m)?\s*x\s*(\d+(?:\.\d+)?)\s*m\b', s)
    if m:
        return float(m.group(1)) / (float(m.group(2)) * float(m.group(3))), 'PLANTS_PER_PLOT_AREA'
    m = re.search(r'(\d+(?:\.\d+)?)\s*plants?\s*(?:ha-1|/ha|per ha)', s) or re.search(r'(\d{4,})\s*(?:plants)?\s*(?:ha|hectare)', s)
    if m:
        return float(m.group(1)) / 10000.0, 'PLANTS_PER_HA'
    m = re.search(r'(\d+(?:\.\d+)?)\s*(cm|m)?\s*x\s*(\d+(?:\.\d+)?)\s*(cm|m)\b', s)
    if m and 'twin' not in s:
        a, ua, b, ub = float(m.group(1)), m.group(2) or m.group(4), float(m.group(3)), m.group(4)
        fa = 0.01 if ua == 'cm' else 1.0; fb = 0.01 if ub == 'cm' else 1.0
        if a * fa * b * fb > 0:
            return 1.0 / (a * fa * b * fb), 'SPACING_GEOMETRY'
    m = re.search(r'(\d+(?:\.\d+)?)\s*m within row on (\d+(?:\.\d+)?)\s*m', s)
    if m:
        return 1.0 / (float(m.group(1)) * float(m.group(2))), 'SPACING_GEOMETRY'
    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:plants?)?\s*(?:m-2|/m2|per m2|per square met)', s)
    if m:
        return float(m.group(1)), 'PRINTED_PER_M2'
    return np.nan, ''


def density(x):
    dm = MOD[MOD.feature == 'plant_density_m2'].copy()
    dm['txt'] = dm.value.astype(str) + ' ' + dm.unit.astype(str) + ' ' + dm.verbatim.astype(str)
    parsed = dm.txt.map(parse_density)
    dm['val'] = parsed.map(lambda p: p[0]); dm['src'] = parsed.map(lambda p: p[1])
    dm = dm.dropna(subset=['val'])
    by_study = dm.groupby('study_id').agg(val=('val', 'median'), src=('src', 'first'), nvals=('val', 'nunique'))
    val = pd.Series(np.nan, index=x.index); src = pd.Series('', index=x.index, dtype=object)
    direct = num(x.f_plant_density_m2); du = x.f_plant_density_m2_unit.astype(str).str.lower()
    ha = du.str.contains('ha')
    plot = du.str.contains('plot')
    direct = np.where(ha, direct / 10000.0, np.where(plot, np.nan, direct))
    direct = pd.Series(direct, index=x.index)
    val[direct.notna()] = direct; src[direct.notna()] = 'F_PLANT_DENSITY_M2'
    m = val.isna() & x.study_id.isin(by_study.index)
    val[m] = x.study_id[m].map(by_study.val); src[m] = x.study_id[m].map(by_study.src)
    potted = x.h_potted == 1
    cat = np.where(val.notna(), 'REPORTED_OR_DERIVED', np.where(potted, 'NOT_APPLICABLE_POTS', 'NOT_REPORTED'))
    val = val.where((val > 0.2) & (val < 40))
    return val, src.where(val.notna(), ''), pd.Series(cat, index=x.index)


# ------------------------------------------------------------------ 5. definitions
def refine_definitions(x):
    loc = (x.locator_t.astype(str) + ' | ' + x.source_cell_t.astype(str)).str.lower()
    sc, hw = x.yield_scope.copy(), x.harvest_window.copy()
    flag = pd.Series(0, index=x.index)
    rules_scope = [('MARKETABLE', r'marketable|market-able|commercial yield|saleable'), ('TOTAL', r'total (?:fruit )?yield|total fruit')]
    rules_hw = [('CUMULATIVE', r'cumulative|total (?:fruit )?yield|seasonal|whole season|all harvests|sum of harvests|total fruit'),
                ('SINGLE_HARVEST', r'first harvest|1st harvest|single harvest|one harvest'),
                ('PARTIAL', r'\bharvest \d|picking \d|\d(?:st|nd|rd|th) (?:harvest|picking)')]
    for name, p in rules_scope:
        m = (sc == 'UNSPECIFIED') & loc.str.contains(p, regex=True)
        sc[m] = name; flag[m] = 1
    for name, p in rules_hw:
        m = (hw == 'UNSPECIFIED') & loc.str.contains(p, regex=True)
        hw[m] = name; flag[m] = 1
    return sc, hw, flag


def build(name):
    x = pd.read_parquet(PROC / f'{name}.parquet')
    out = dujardin_v2(x).join(stress_v2(x))
    none = x.h_stress_class == 'NONE'
    out['h2_application_phase'] = phase(x.f_application_stage)
    out['h2_stress_onset_phase'] = phase(x.f_stress_onset_stage, none_mask=none)
    out['h2_substrate_type'], out['h2_soil_ec_dsm'] = substrate(x)
    out['h2_plant_density_m2'], out['h2_density_source'], out['h2_density_status'] = density(x)
    if 'yield_scope' in x and name == 'train_yield':
        out['h2_yield_scope'], out['h2_harvest_window'], out['h2_definition_refined_from_locator'] = refine_definitions(x)
    for c in out.columns:
        x[c] = out[c].values
    x.to_parquet(PROC / f'{name}_v2.parquet', index=False)
    x.to_csv(PROC / f'{name}_v2.csv', index=False, encoding='utf-8')
    return x


AUDIT = []
for name in ('train_yield', 'train_dry_biomass'):
    x = build(name)
    d = x[x.in_default == 1]
    ch = d[d.h_dujardin != d.h2_dujardin]
    AUDIT.append(dict(table=name, item='du Jardin class changed v1->v2', rows=len(ch), studies=ch.study_id.nunique()))
    for k, g in ch.groupby(['h_dujardin', 'h2_dujardin']):
        AUDIT.append(dict(table=name, item=f'  {k[0]} -> {k[1]}', rows=len(g), studies=g.study_id.nunique()))
    nl = d[d.h2_nonliving_microbial_product == 1]
    AUDIT.append(dict(table=name, item='non-living microbial products (cell-free filtrates etc.)', rows=len(nl), studies=nl.study_id.nunique()))
    for c in ['h2_drought_supply_type', 'h2_salinity_measure_type', 'h2_application_phase', 'h2_stress_onset_phase', 'h2_substrate_type', 'h2_density_status', 'h2_density_source']:
        for k, g in d.groupby(c):
            AUDIT.append(dict(table=name, item=f'{c} = {k}', rows=len(g), studies=g.study_id.nunique()))
    for c in ['h2_drought_supply_reported', 'h2_salinity_reported', 'h2_stress_duration_reported']:
        g = d[d[c].notna()]
        AUDIT.append(dict(table=name, item=f'{c}: reported within applicable context', rows=int(g[c].sum()), studies=g[g[c] == 1].study_id.nunique(),
                          note=f'of {len(g)} applicable rows / {g.study_id.nunique()} studies'))
    if name == 'train_yield':
        for c0, c1 in [('yield_scope', 'h2_yield_scope'), ('harvest_window', 'h2_harvest_window')]:
            u0 = d[d[c0] == 'UNSPECIFIED']; u1 = d[d[c1] == 'UNSPECIFIED']
            AUDIT.append(dict(table=name, item=f'{c0} UNSPECIFIED before -> after locator refinement', rows=f'{len(u0)} -> {len(u1)}',
                              studies=f'{u0.study_id.nunique()} -> {u1.study_id.nunique()}'))
A = pd.DataFrame(AUDIT)
A.to_csv(RES / 'features_v2_audit.csv', index=False)
print(A.to_string())

NEW = {
    'h2_dujardin': 'du Jardin class v2: cell-free filtrates -> DJ_MICROBIAL_DERIVED_NONLIVING; single-component preparations take the first-named category; MIXTURE only for >=2 components (db_arms.n_bio_components) spanning >=2 categories.',
    'h2_n_components': 'Number of biostimulant components of the treated arm (db_arms.n_bio_components).',
    'h2_live_microorganism': '1 if the product contains living microorganisms (0 for cell-free filtrates/extracts).',
    'h2_nonliving_microbial_product': '1 for cell-free filtrates, supernatants, microbial water extracts.',
    'h2_drought_supply_type': 'FIELD_CAPACITY_PCT | ETC_OR_IRRIGATION_PCT | UNKNOWN_TYPE (drought, not reported) | NOT_APPLICABLE (not drought).',
    'h2_drought_fc_pct / h2_drought_etc_pct': 'Water supply of the drought treatment by measurement type; 100 when not drought (no deficit); NaN = drought, not reported.',
    'h2_drought_supply_reported': 'Within drought rows only: 1 reported, 0 not reported; NaN = not applicable.',
    'h2_salinity_measure_type': 'NACL_CONCENTRATION | EC_WATER_MEASURED | NACL_AND_EC | UNKNOWN_TYPE | NOT_APPLICABLE.',
    'h2_salinity_nacl_mm / h2_salinity_ecw_dsm': 'NaCl concentration (mM; % w/v*171.1; g/L*17.11) and measured irrigation-water EC (dS/m) kept separate; 0 when not saline.',
    'h2_salinity_reported': 'Within salinity rows only: 1 reported, 0 not; NaN = not applicable.',
    'h2_stress_duration_days': 'Stress duration in days (weeks*7, months*30.4, h/24); 0 when no stress; NaN = not reported.',
    'h2_stress_duration_reported': 'Within stressed rows: 1/0; NaN for no-stress rows.',
    'h2_days_application_before_stress': 'Days between first application and stress onset (unit converted); NaN without stress.',
    'h2_application_phase / h2_stress_onset_phase': 'Development phase: SEED, NURSERY_SEEDLING, TRANSPLANT, VEGETATIVE, FLOWERING, FRUITING, MULTIPLE_STAGES, UNSPECIFIED (onset: NOT_APPLICABLE without stress).',
    'h2_substrate_type': 'SOILLESS_INERT, PEAT_POTTING_MIX, STERILISED_SOIL, SAND_OR_SANDY, FIELD_OR_NATURAL_SOIL, UNSPECIFIED.',
    'h2_soil_ec_dsm': 'Soil EC normalised to dS/m (uS/cm / 1000).',
    'h2_plant_density_m2': 'Plants per m2: printed value, plants/ha / 10000, plants per plot area, or 1/(row x plant spacing). Range-checked 0.2-40.',
    'h2_density_source': 'Provenance of the density value (F_PLANT_DENSITY_M2, PLANTS_PER_HA, PLANTS_PER_PLOT_AREA, SPACING_GEOMETRY, PRINTED_PER_M2).',
    'h2_density_status': 'REPORTED_OR_DERIVED | NOT_APPLICABLE_POTS | NOT_REPORTED.',
    'h2_yield_scope / h2_harvest_window': 'Yield definition with UNSPECIFIED refined only when the printed locator/source cell states it.',
    'h2_definition_refined_from_locator': '1 if a definition field was refined from the locator text.',
}
dd = pd.read_csv(PROC / 'new_columns_dictionary.csv')
dd = pd.concat([dd[~dd.column.isin(NEW)], pd.DataFrame([{'column': k, 'description': v} for k, v in NEW.items()])])
dd.to_csv(PROC / 'new_columns_dictionary.csv', index=False, encoding='utf-8')
