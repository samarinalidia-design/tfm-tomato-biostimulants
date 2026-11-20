"""Audit: where does yield exist across the 399 frozen studies, and why do studies drop out of train_yield?
Reads the freeze read-only (study / measurement / asset tables are not copied; only counted)."""
import json, pathlib
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
F = ROOT.parent / 'TFM_A399_Agent_System_v2_2_2026-10-19/TFM_AGENT_SYSTEM_v2_2/exports/DATA_FREEZE_20261113T112939135807Z'
st = pd.read_parquet(F / 'db_studies.parquet')
m = pd.read_parquet(F / 'db_measurements.parquet')
a = pd.read_parquet(F / 'db_asset_inventory.parquet')
c = pd.read_parquet(ROOT / 'data/raw/contrast_candidates.parquet')
ty = pd.read_parquet(ROOT / 'data/processed/train_yield.parquet')
tb = pd.read_parquet(ROOT / 'data/processed/train_dry_biomass.parquet')

ep = m.groupby('study_id').endpoint.apply(set)
rows = []
for s in st.study_id:
    e = ep.get(s, set())
    cy = c[(c.study_id == s) & (c.endpoint == 'FRUIT_YIELD')]
    yslot = a[(a.study_id == s) & (a.disposition == 'SLOT') & a.reason.fillna('').str.contains(r'PRIMARY FRUIT_YIELD|fruit yield fresh mass|Total fruit fresh mass per plant|fruit fresh mass produced per plant', case=False)]
    if 'FRUIT_YIELD' not in e:
        if len(yslot):
            why = 'YIELD_SLOT_IN_ASSET_INVENTORY_BUT_NO_VERIFIED_MEASUREMENT'
        elif e & {'FRUIT_NUMBER', 'MEAN_FRUIT_MASS', 'WATER_PRODUCTIVITY'}:
            why = 'ONLY_YIELD_COMPONENTS_MEASURED (fruit number / mean fruit mass)'
        elif e:
            why = 'NO_YIELD_MEASURED (other endpoints only)'
        else:
            why = 'NO_VERIFIED_MEASUREMENTS_AT_ALL'
    elif s in set(ty.study_id):
        why = 'IN_train_yield'
    elif len(cy) == 0:
        why = 'YIELD_MEASURED_BUT_NO_CONTRAST_BUILT'
    elif set(cy.contrast_type) <= {'S_vs_C', 'SxB', 'AxB', 'B_MAIN_EFFECT'}:
        why = 'ONLY_S_vs_C_OR_INTERACTION_OR_MAIN_EFFECT_CONTRASTS'
    elif (cy.yield_scope == 'NON_MARKETABLE').all():
        why = 'ONLY_NON_MARKETABLE'
    else:
        why = 'OTHER (lnRR not computable)'
    rows.append(dict(study_id=s, year=st.set_index('study_id').year.get(s), has_yield_measurement=int('FRUIT_YIELD' in e),
                     yield_contrasts_any_type=len(cy), in_train_yield=int(s in set(ty.study_id)),
                     in_train_dry_biomass=int(s in set(tb.study_id)), endpoints=';'.join(sorted(e)), status=why))
R = pd.DataFrame(rows)
R.to_csv(ROOT / 'results/yield_coverage_audit_399_studies.csv', index=False)
S = R.status.value_counts().rename_axis('status').reset_index(name='studies')
S.to_csv(ROOT / 'results/yield_coverage_audit_summary.csv', index=False)
print(S.to_string())
print('studies with any verified measurement:', (R.endpoints != '').sum(), '| with yield measurement:', R.has_yield_measurement.sum(),
      '| in train_yield:', R.in_train_yield.sum(), '| in yield OR biomass table:', ((R.in_train_yield + R.in_train_dry_biomass) > 0).sum())
