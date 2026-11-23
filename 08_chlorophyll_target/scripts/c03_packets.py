"""Chlorophyll pilot: one packet per study for the extraction agents.
Packet = bibliographic identity, registered original files (local path + SHA-256), every chlorophyll asset locator from the
agents' asset inventory, and the frozen, source-verified design (experiments and arms) of the A399 database.
Usage: python c03_packets.py <TRAIN sqlite> [list prefix: pilot50 (default) | full]
"""
import sys, json, os, pathlib, sqlite3
import pandas as pd

OUT = pathlib.Path(__file__).resolve().parents[1]
WORK = pathlib.Path(os.environ.get('CHL_WORK', r"C:/Users/lenovo/Desktop/master's/TFM_CHLOROPHYLL_PILOT/work"))


def main():
    c = sqlite3.connect(f'file:{sys.argv[1]}?mode=ro', uri=True)
    pref = sys.argv[2] if len(sys.argv) > 2 else 'pilot50'
    P = pd.read_csv(OUT / 'data' / f'{pref}_studies.csv', dtype={'study_id': str})
    if 'fulltext_ok' in P:
        P = P[P.fulltext_ok == True]
    F = pd.read_csv(OUT / 'data' / f'{pref}_files.csv', dtype={'study_id': str})
    A = pd.read_csv(OUT / 'data' / 'chlorophyll_assets.csv')
    files = pd.read_sql('select study_id, role, file_name, sha256 from files', c)
    st = pd.read_sql('select study_id, doi, title, year, journal from studies', c)
    ex = pd.read_sql('select study_id, experiment_key, description, system, allocation, factorial_verified from experiments', c)
    arms = pd.read_sql('select study_id, experiment_key, arm_key, label_in_source, stress_code, stress_desc, bio_code, bio_desc, '
                       'genotype, season, site, role from arms', c)
    (WORK / 'packets').mkdir(parents=True, exist_ok=True)
    for sid in P.study_id:
        f = F[F.study_id == sid].merge(files[['file_name', 'sha256']], on='file_name')
        meta = st[st.study_id == sid].iloc[0].to_dict()
        pk = {'study_id': sid, 'doi': meta.get('doi'), 'title': meta.get('title'), 'year': meta.get('year'),
              'files': [{'role': r.role, 'file_name': r.file_name, 'local_path': r.local_path, 'sha256': r.sha256} for r in f.itertuples()],
              'chlorophyll_assets_from_inventory': A[(A.study_id.astype(str) == sid) & (A.role == os.environ.get('CHL_ROLE', 'TRAIN'))][['locator', 'reason']].to_dict('records'),
              'design_from_A399': {
                  'coded': bool(P.loc[P.study_id == sid, 'design_coded'].iloc[0]),
                  'experiments': ex[ex.study_id == sid].drop(columns='study_id').to_dict('records'),
                  'arms': arms[arms.study_id == sid].drop(columns='study_id').to_dict('records')},
              'note': ('Arms were coded and source-verified in the A399 project (fruit yield / dry biomass). Map every chlorophyll value to one '
                       'of these arm_keys. If the chlorophyll measurements use arms or experiments that are not in this list, or if the '
                       'design was not coded, add them under design_check.new_arms with the same coding conventions.')}
        (WORK / 'packets' / f'{sid}.json').write_text(json.dumps(pk, indent=1, ensure_ascii=False, default=str), encoding='utf-8')
    print('packets', len(P), '->', WORK / 'packets')


if __name__ == '__main__':
    main()
