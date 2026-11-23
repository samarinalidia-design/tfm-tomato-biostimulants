"""V7 step 1 (TRAIN only, exploratory): recover excluded yield evidence and add compact, comparable features.

Input : 06_database_corrections_v6/data/train_{yield,dry_biomass}_V6.parquet (V5 tables + V6 corrections)
        05_analysis_train_expansion_v5/data/raw/contrast_candidates.parquet (frozen TRAIN_DEV contrasts)
Output: 07_train_improvement_v7/data/train_{yield,dry_biomass}_V7.parquet, results/v7_build_report.json

1. Recovered yield rows (marked v7_source; they are NOT in in_default_v6):
   MAIN_EFFECT  B_MAIN_EFFECT contrasts (factor-level means pooled over the stress levels; author decision 7 keeps them
                out of factorial marts - here they are used as training evidence only, flagged)
   COMPONENT    ln(yield) = ln(fruit number per plant) + ln(mean fruit mass) for the same arm pair, for studies with no
                fruit-yield contrast (variance = sum, independence assumed). Same rule as SynerPlant_Yield_V2 y01.
2. New features (pre-experimental, no target information):
   v7_exp_loss    expected relative yield loss of the stressed arm from its printed stress level:
                  salinity  Maas-Hoffman tomato (threshold 2.5 dS/m, slope 9.9 %/dS/m; FAO-29); EC from ECw (x1.5 for
                            soil, x1 soilless) or from NaCl (0.1 dS/m per mM)
                  drought   FAO-33 Ky = 1.05 x (1 - supply fraction) (supply = % field capacity or % ETc/irrigation)
                  combined  1 - (1 - Ls)(1 - Ld);  no stress 0;  other stresses missing (+ indicator)
   v7_sal_ec_dsm, v7_drought_supply_frac   family-specific intensities with STRUCTURAL zero / one for other families
   v7_log_pot_l, v7_log_dose_z_in_class    log pot volume; log10 dose standardised within its dose class (class
                  statistics are computed inside each CV fold by v7_02, here only the raw log is stored)
   v7_fert_regime  NONE / NUTRIENT_SOLUTION / NUMERIC_N / TEXT_ONLY / NOT_REPORTED
"""
import sys, json, math, pathlib, importlib.util
import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parents[2]
V5S = REPO / '05_analysis_train_expansion_v5' / 'v5' / 'scripts'
V6 = REPO / '06_database_corrections_v6'
OUT = REPO / '07_train_improvement_v7'
(OUT / 'data').mkdir(parents=True, exist_ok=True); (OUT / 'results').mkdir(parents=True, exist_ok=True)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


sys.path.insert(0, str(V5S)); sys.path.insert(0, str(V6 / 'scripts'))
B5 = load('v5_01_build', V5S / 'v5_01_build.py')
C6 = load('v6_corrections', V6 / 'scripts' / 'v6_corrections.py')
B5.TRAIN_FREEZE = REPO / '03_data_freeze' / 'train_dev_DATA_FREEZE_20261113T112939135807Z'   # repository copy of the freeze


def _load_v2_module(freeze):
    """V5's loader reads the freeze from the author's original folder; inside the repository the copy in 03_data_freeze
    is used instead (same SHA-256 per 03_data_freeze/MANIFEST.json). V5 code itself is not modified."""
    f = REPO / '05_analysis_train_expansion_v5' / 'scripts' / '07_features_v2.py'
    src = f.read_text(encoding='utf-8').split('\nAUDIT = []')[0]
    src = src.replace("F = ROOT.parent / 'TFM_A399_Agent_System_v2_2_2026-10-19/TFM_AGENT_SYSTEM_v2_2/exports/DATA_FREEZE_20261113T112939135807Z'",
                      f"F = pathlib.Path({str(freeze)!r})")
    ns = {'__file__': str(f), '__name__': 'v2'}
    exec(compile(src, '07_features_v2', 'exec'), ns)
    ns['ARMS'] = pd.read_parquet(freeze / 'db_arms.parquet'); ns['MOD'] = pd.read_parquet(freeze / 'db_moderators.parquet')
    return ns


B5.load_v2_module = _load_v2_module


# ------------------------------------------------------------------------------------------------ 1. recovery
def recover_yield(y6):
    raw = pd.read_parquet(REPO / '05_analysis_train_expansion_v5' / 'data' / 'raw' / 'contrast_candidates.parquet')
    tr = B5.apply_corrections(raw, 'TRAIN', B5.tv_means(B5.TRAIN_FREEZE))
    y, y_inter, y_svc, *_ = B5.select_tables(tr, 'TRAIN')
    P = B5.learn_cvbar(y)                                              # same CV-bar as V5 (TRAIN yield)
    have = set(y6.study_id)
    # 1a. B main effects of studies without any SB_vs_S / B_vs_C yield contrast
    me = y_inter[(y_inter.contrast_type == 'B_MAIN_EFFECT') & ~y_inter.study_id.isin(have)].copy()
    me['v7_source'] = 'MAIN_EFFECT'
    # 1b. component proxy
    pool = B5.base_pool(tr, 'FRUIT_NUMBER', 'TRAIN', 'fruit_number')
    pool = pd.concat([pool, B5.base_pool(tr, 'MEAN_FRUIT_MASS', 'TRAIN', 'fruit_mass')], ignore_index=True)
    k = pool[pool.contrast_type.isin(['SB_vs_S', 'B_vs_C']) & ~pool.study_id.isin(have) & (pool.mean_t > 0) & (pool.mean_c > 0)].copy()
    un = k.unit_norm.fillna('').astype(str).str.lower()
    k = k[~((k.endpoint == 'FRUIT_NUMBER') & un.str.contains('m2|ha|plot'))]          # per-plant counts only
    k['pair'] = k.study_id + '|' + k.experiment_key.astype(str) + '|' + k.arm_key_t + '|' + k.arm_key_c + '|' + k.contrast_type
    k['_tp'] = pd.to_numeric(k.timepoint_days, errors='coerce').fillna(-1)
    k = k.sort_values(['pair', 'endpoint', '_tp'], ascending=[True, True, False]).drop_duplicates(['pair', 'endpoint'])
    n_ = k[k.endpoint == 'FRUIT_NUMBER'].set_index('pair'); m_ = k[k.endpoint == 'MEAN_FRUIT_MASS'].set_index('pair')
    common = n_.index.intersection(m_.index)
    rows = []
    for p in common:
        a, b = n_.loc[p].copy(), m_.loc[p]
        a['contrast_id'] = 'V7PROXY:' + str(a.contrast_id)
        a['endpoint'] = 'FRUIT_YIELD'
        for s in ('t', 'c'):
            a[f'mean_{s}'] = a[f'mean_{s}'] * b[f'mean_{s}']
            a[f'sd_{s}'] = np.nan; a[f'n_{s}'] = np.nanmin([a[f'n_{s}'], b[f'n_{s}']]) if pd.notna(a[f'n_{s}']) or pd.notna(b[f'n_{s}']) else np.nan
        a['effect'] = float(n_.loc[p].effect) + float(b.effect)
        a['yield_scope'], a['mass_basis'], a['harvest_window'], a['denominator'] = 'TOTAL', 'FRESH', a.harvest_window, 'PER_PLANT'
        a['unit_norm'] = 'kg/plant'
        a['v7_proxy_var_parts'] = json.dumps([n_.loc[p].contrast_id, b.contrast_id])
        a['v7_source'] = 'COMPONENT_PROXY'
        rows.append(a)
    px = pd.DataFrame(rows).reset_index(drop=True) if rows else pd.DataFrame()
    rec = pd.concat([me, px], ignore_index=True)
    if rec.empty:
        return rec, {}
    rec['yield_tier'] = np.where(rec.v7_source == 'COMPONENT_PROXY', 'COMPONENT_PROXY', 'MAIN_EFFECT')
    rec['is_dry_yield'] = 0; rec['is_early_yield'] = 0
    rec = B5.impute_variance(rec, P)
    # proxy variance: number + mass parts imputed with the yield CV-bar is approximated by 2x the imputed yield variance
    pr = rec.v7_source == 'COMPONENT_PROXY'
    rec.loc[pr, 'var_lnrr_imp'] = rec.loc[pr, 'var_lnrr_imp'] * 2
    svc = y_svc[y_svc.study_id.isin(set(rec.study_id))]
    rec['mod_lnrr_stress_SvsC'] = B5.attach_svc(rec, svc) if len(svc) else np.nan
    rec = B5.features(rec, B5.TRAIN_FREEZE, 'yield')
    rec['in_default'] = 0
    rec['contrast_type_v7'] = rec.contrast_type
    rec.loc[rec.contrast_type == 'B_MAIN_EFFECT', 'contrast_type'] = 'SB_vs_S'       # stress-averaged effect, see flag
    rec['is_B_vs_C'] = (rec.contrast_type == 'B_vs_C').astype(int)
    rep = {'main_effect_contrasts': int((rec.v7_source == 'MAIN_EFFECT').sum()),
           'main_effect_studies': sorted(rec[rec.v7_source == 'MAIN_EFFECT'].study_id.unique().tolist()),
           'proxy_contrasts': int(pr.sum()), 'proxy_studies': sorted(rec[pr].study_id.unique().tolist())}
    return rec, rep


def v6_layer(rec, mt):
    """Same V6 rules for the recovered rows (moderator parsing, N, rootstock, flags)."""
    rec = rec.copy()
    rec['v6_flags'] = ''; rec['v6_excluded_reason'] = None
    C6.fill_moderators(rec, 'train', 'yield', mt); C6.fill_fert_n(rec, 'train', 'yield'); C6.fill_rootstock(rec, 'train', 'yield')
    C6.fill_age(rec); C6.severity_and_flags(rec, 'train', 'yield')
    rec['v6_primary_of_pair'] = 1; rec['in_default_v6'] = 0
    flags = rec.v6_flags.fillna('').str.split(';')
    rec['v6_reliability_flag'] = flags.map(lambda x: int(bool(set(x) & C6.RELIABILITY_FLAGS)))
    rec['in_quality_core_v6'] = 0
    return rec


# ------------------------------------------------------------------------------------------------ 2. features
KY_TOMATO, MH_THRESHOLD, MH_SLOPE = 1.05, 2.5, 0.099


def num(s):
    return pd.to_numeric(s, errors='coerce')


def add_features(d):
    d = d.copy()
    cls = d.h_stress_class.astype(str)
    sal = cls.isin(['SALINITY', 'COMBINED']) | (d.get('h3_stress_salinity', 0) == 1)
    dro = cls.isin(['DROUGHT', 'COMBINED']) | (d.get('h3_stress_drought', 0) == 1)
    soilless = d.get('h2_substrate_type', pd.Series('', index=d.index)).astype(str).str.contains('SOILLESS|HYDRO|NUTRIENT', case=False)
    ecw = num(d.get('h2_salinity_ecw_dsm')); nacl = num(d.get('h2_salinity_nacl_mm'))
    ec = np.where(ecw > 0, ecw * np.where(soilless, 1.0, 1.5), np.where(nacl > 0, 0.1 * nacl, np.nan))
    ec = pd.Series(ec, index=d.index)
    d['v7_sal_ec_dsm'] = np.where(sal, ec, 0.0)                                    # structural zero outside salinity
    l_sal = ((ec - MH_THRESHOLD).clip(lower=0) * MH_SLOPE).clip(upper=1)
    fc, etc = num(d.get('h2_drought_fc_pct')), num(d.get('h2_drought_etc_pct'))
    supply = np.where(dro & (etc < 100), etc / 100, np.where(dro & (fc < 100), fc / 100, np.nan))
    supply = pd.Series(supply, index=d.index)
    d['v7_drought_supply_frac'] = np.where(dro, supply, 1.0)                        # structural one outside drought
    l_dro = (KY_TOMATO * (1 - supply)).clip(lower=0, upper=1)
    none = (cls == 'NONE') | (d.contrast_type == 'B_vs_C')
    loss = np.where(none, 0.0,
           np.where(sal & dro, 1 - (1 - l_sal.fillna(0)) * (1 - l_dro.fillna(0)),
           np.where(sal, l_sal, np.where(dro, l_dro, np.nan))))
    loss = pd.Series(loss, index=d.index)
    loss[(sal & l_sal.isna()) & ~(dro & l_dro.notna())] = np.nan
    d['v7_exp_loss'] = loss
    d['v7_exp_loss_known'] = loss.notna().astype(int)
    d['v7_log_pot_l'] = np.log(num(d.get('v6_pot_volume_l')))
    d['v7_log_dose'] = num(d.get('h_log10_dose'))
    t = d.get('context_fertilization_all', pd.Series('', index=d.index)).fillna('').astype(str).str.lower()
    regime = np.select([d.get('h3_fert_none', 0) == 1, d.get('h3_fert_nutrient_solution', 0) == 1, num(d.get('h3_fert_n_kg_ha')).notna(),
                        t.str.len() > 3], ['NONE', 'NUTRIENT_SOLUTION', 'NUMERIC_N', 'TEXT_ONLY'], 'NOT_REPORTED')
    d['v7_fert_regime'] = regime
    d['v7_log_fert_n'] = np.log1p(num(d.get('h3_fert_n_kg_ha')))
    d['v7_temp_day'] = num(d.get('v6_temperature_day_c'))
    d['v7_lat'] = num(d.get('v6_abs_latitude_printed')).fillna(num(d.get('h3_abs_latitude')))
    d['v7_log_stress_days'] = np.log1p(num(d.get('h2_stress_duration_days')).where(~none))
    d['v7_is_main_effect'] = (d.get('v7_source', '') == 'MAIN_EFFECT').astype(int) if 'v7_source' in d else 0
    d['v7_is_proxy'] = (d.get('v7_source', '') == 'COMPONENT_PROXY').astype(int) if 'v7_source' in d else 0
    return d


def main():
    y6 = pd.read_parquet(V6 / 'data' / 'train_yield_V6.parquet')
    b6 = pd.read_parquet(V6 / 'data' / 'train_dry_biomass_V6.parquet')
    mt = C6.moderator_table('train')
    rec, rep = recover_yield(y6)
    if len(rec):
        rec = v6_layer(rec, mt)
        y6['v7_source'] = 'V6'
        y7 = pd.concat([y6, rec.reindex(columns=list(dict.fromkeys(list(y6.columns) + list(rec.columns))))], ignore_index=True)
    else:
        y7 = y6.assign(v7_source='V6')
    b6['v7_source'] = 'V6'
    y7, b7 = add_features(y7), add_features(b6)
    for c in y7.columns:
        if y7[c].dtype == object:
            y7[c] = y7[c].map(lambda v: json.dumps(v, default=str) if isinstance(v, (list, dict)) else v)
    y7.to_parquet(OUT / 'data' / 'train_yield_V7.parquet', index=False)
    b7.to_parquet(OUT / 'data' / 'train_dry_biomass_V7.parquet', index=False)
    s = y7[y7.contrast_type == 'SB_vs_S']
    rep.update({'yield_rows': len(y7), 'yield_studies': int(y7.study_id.nunique()),
                'yield_studies_default_v6': int(y7[y7.in_default_v6 == 1].study_id.nunique()),
                'yield_studies_with_recovered': int(y7[(y7.in_default_v6 == 1) | y7.v7_source.isin(['MAIN_EFFECT', 'COMPONENT_PROXY'])].study_id.nunique()),
                'exp_loss_coverage_SB_vs_S_studies': float(s.v7_exp_loss.notna().groupby(s.study_id).any().mean()),
                'exp_loss_by_class': s.groupby('h_stress_class').v7_exp_loss.apply(lambda x: round(float(x.notna().mean()), 2)).to_dict()})
    (OUT / 'results' / 'v7_build_report.json').write_text(json.dumps(rep, indent=1, default=str), encoding='utf-8')
    print(json.dumps(rep, indent=1, default=str))


if __name__ == '__main__':
    main()
