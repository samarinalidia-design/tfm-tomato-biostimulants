"""Chlorophyll full run (TRAIN): all remaining TRAIN studies with a chlorophyll-content or chlorophyll-index asset
(EXCLUDED_SCOPE and the 50 pilot studies removed), with the SHA-256 check of the local originals.
Usage: python c02b_select_full.py <sqlite> <local fulltext dir> <local supplements dir> [TRAIN|TEST]
(TEST: all TEST studies with a chlorophyll asset, outputs data/test_*.csv)
Output: data/full_studies.csv, data/full_files.csv, data/full_groups.csv (groups of 5, figures and tables mixed)
"""
import sys, json, hashlib, pathlib, sqlite3
import pandas as pd

OUT = pathlib.Path(__file__).resolve().parents[1]


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def main():
    db, ft, sp = sys.argv[1], pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3])
    S = pd.read_csv(OUT / 'data' / 'chlorophyll_studies.csv', dtype={'study_id': str})
    A = pd.read_csv(OUT / 'data' / 'chlorophyll_assets.csv', dtype={'study_id': str})
    pilot = set(pd.read_csv(OUT / 'data' / 'pilot50_studies.csv', dtype={'study_id': str}).study_id)
    ROLE = sys.argv[4] if len(sys.argv) > 4 else 'TRAIN'
    PREF = 'full' if ROLE == 'TRAIN' else 'test'
    S = S[(S.role == ROLE) & (S.workflow_status != 'EXCLUDED_SCOPE') & (~S.study_id.isin(pilot) if ROLE == 'TRAIN' else True)].copy()
    loc = A[A.role == ROLE].assign(f=lambda x: x.locator.fillna('').str.lower().str.contains(r'\bfig'))
    S['has_figure'] = S.study_id.map(loc.groupby('study_id').f.any()).fillna(False)
    c = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    files = pd.read_sql("select study_id, role, file_name, sha256 from files", c)
    rows = []
    for sid in S.study_id:
        for r in files[files.study_id == sid].itertuples():
            path = (ft if r.role == 'FULLTEXT' else sp) / r.file_name
            if not path.exists() and r.role != 'FULLTEXT' and (sp / str(sid) / r.file_name).exists():
                path = sp / str(sid) / r.file_name          # TEST corpus keeps supplements in per-study folders
            rows.append(dict(study_id=sid, role=r.role, file_name=r.file_name, local_path=str(path), exists=path.exists(),
                             sha_ok=path.exists() and sha(path) == r.sha256))
    F = pd.DataFrame(rows)
    ok = F.groupby('study_id').apply(lambda g: bool(g[g.role == 'FULLTEXT'].sha_ok.all()) and len(g[g.role == 'FULLTEXT']) > 0)
    S['fulltext_ok'] = S.study_id.map(ok).fillna(False)
    S.to_csv(OUT / 'data' / f'{PREF}_studies.csv', index=False); F.to_csv(OUT / 'data' / f'{PREF}_files.csv', index=False)
    use = S[S.fulltext_ok].sort_values(['has_figure', 'study_id'])
    ids = list(use.study_id); ng = (len(ids) + 4) // 5
    G = pd.DataFrame([(f'F{i + 1:02d}', s) for i in range(ng) for s in ids[i::ng]], columns=['group', 'study_id'])
    G.to_csv(OUT / 'data' / f'{PREF}_groups.csv', index=False)
    print(json.dumps({'studies': len(S), 'fulltext_ok': int(S.fulltext_ok.sum()), 'content': int(S.content_not_spad.sum()),
                      'spad_only': int((~S.content_not_spad).sum()), 'design_coded': int(S.design_coded.sum()), 'groups': ng,
                      'file_problems': F[~F.sha_ok][['study_id', 'file_name', 'exists']].to_dict('records')}, indent=1))


if __name__ == '__main__':
    main()
