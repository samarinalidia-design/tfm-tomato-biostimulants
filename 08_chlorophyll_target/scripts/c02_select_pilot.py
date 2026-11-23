"""Chlorophyll pilot: select 50 TRAIN studies (stratified, seeded) and check that their original full texts are available
locally with the SHA-256 recorded in the frozen database.

Strata (proportional to the 152 TRAIN studies with chlorophyll-content assets, EXCLUDED_SCOPE removed):
  design coded in the frozen DB (45 studies) vs not coded (5 studies, to test the design-coding path)
  within coded: source type of the chlorophyll assets (table only / figure only / both) and stress family
Usage: python c02_select_pilot.py <TRAIN sqlite> <local fulltext dir> <local supplements dir>
Output: data/pilot50_studies.csv, results/pilot_selection.json
"""
import sys, json, hashlib, pathlib, sqlite3
import numpy as np
import pandas as pd

OUT = pathlib.Path(__file__).resolve().parents[1]
SEED = 20261122
N_CODED, N_UNCODED = 45, 5


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def main():
    db, ft, sp = sys.argv[1], pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3])
    S = pd.read_csv(OUT / 'data' / 'chlorophyll_studies.csv')
    A = pd.read_csv(OUT / 'data' / 'chlorophyll_assets.csv')
    S = S[(S.role == 'TRAIN') & S.content_not_spad & (S.workflow_status != 'EXCLUDED_SCOPE')].copy()
    A = A[A.role == 'TRAIN']
    loc = (A.locator.fillna('').str.lower())
    A['is_fig'] = loc.str.contains(r'\bfig'); A['is_tab'] = loc.str.contains(r'\btable|\btab\.')
    src = A.groupby('study_id').agg(fig=('is_fig', 'any'), tab=('is_tab', 'any'))
    S['source_type'] = S.study_id.map(lambda s: 'both' if src.loc[s, 'fig'] and src.loc[s, 'tab'] else
                                      ('figure' if src.loc[s, 'fig'] else ('table' if src.loc[s, 'tab'] else 'text/other')))
    c = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    arms = pd.read_sql('select study_id, stress_code from arms', c)
    fam = arms.assign(f=arms.stress_code.fillna('NONE').str.upper().str.extract(r'^(SAL|NACL|DROUGHT|DEF|WATER|HEAT|COLD|CHILL|BIO|PATH)')[0]
                      .replace({'NACL': 'SAL', 'DEF': 'DROUGHT', 'WATER': 'DROUGHT', 'CHILL': 'COLD', 'PATH': 'BIO'}))
    fam = fam.dropna(subset=['f']).groupby('study_id').f.agg(lambda x: x.value_counts().index[0])
    S['stress_family'] = S.study_id.map(fam).fillna('OTHER/UNCODED')
    files = pd.read_sql("select study_id, role, file_name, sha256 from files", c)
    rng = np.random.default_rng(SEED)
    coded = S[S.design_coded == True].copy(); unc = S[S.design_coded != True].copy()
    coded['stratum'] = coded.source_type + '|' + coded.stress_family
    # proportional allocation with largest remainders
    share = coded.stratum.value_counts() / len(coded) * N_CODED
    alloc = np.floor(share).astype(int)
    for k in (share - alloc).sort_values(ascending=False).index[:N_CODED - alloc.sum()]:
        alloc[k] += 1
    pick = []
    for k, n in alloc.items():
        g = coded[coded.stratum == k]
        pick += list(rng.choice(g.study_id.values, size=min(n, len(g)), replace=False))
    pick += list(rng.choice(unc.study_id.values, size=min(N_UNCODED, len(unc)), replace=False))
    P = S[S.study_id.isin(pick)].copy()
    # local originals with SHA check
    rows = []
    for sid in P.study_id:
        for r in files[files.study_id == sid].itertuples():
            root = ft if r.role == 'FULLTEXT' else sp
            path = root / r.file_name
            ok = path.exists() and sha(path) == r.sha256
            rows.append(dict(study_id=sid, role=r.role, file_name=r.file_name, local_path=str(path), exists=path.exists(), sha_ok=ok))
    F = pd.DataFrame(rows)
    st = F.groupby('study_id').agg(n_files=('file_name', 'size'), fulltext_ok=('sha_ok', lambda x: bool(x[F.loc[x.index, 'role'] == 'FULLTEXT'].all())),
                                   all_files_ok=('sha_ok', 'all')).reset_index()
    P = P.merge(st, on='study_id', how='left')
    P.to_csv(OUT / 'data' / 'pilot50_studies.csv', index=False)
    F.to_csv(OUT / 'data' / 'pilot50_files.csv', index=False)
    rep = {'seed': SEED, 'selected': len(P), 'design_coded': int((P.design_coded == True).sum()),
           'source_type': P.source_type.value_counts().to_dict(), 'stress_family': P.stress_family.value_counts().to_dict(),
           'with_spad_too': int(P.spad.sum()), 'fulltext_sha_ok': int(P.fulltext_ok.sum()), 'all_files_ok': int(P.all_files_ok.sum()),
           'missing_or_mismatch_files': F[~F.sha_ok][['study_id', 'file_name', 'exists']].to_dict('records')}
    (OUT / 'results' / 'pilot_selection.json').write_text(json.dumps(rep, indent=1, default=str), encoding='utf-8')
    print(json.dumps(rep, indent=1, default=str))


if __name__ == '__main__':
    main()
