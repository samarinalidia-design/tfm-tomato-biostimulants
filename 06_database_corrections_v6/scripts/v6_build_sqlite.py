"""Build the V6 corrected databases as new release assets.

Reads the original release zips (never modified), copies each TFM_DATABASE_CLASS_A_FINAL.sqlite, adds the v6_* tables
written by v6_corrections.py, records a v6_manifest table and writes new zips next to the originals:
  TFM_DATABASE_TRAIN_DEV_V6_CORRECTED_20261122.zip
  TFM_DATABASE_EXTERNAL_TEST_V6_CORRECTED_20261122.zip
The original tables are untouched; every corrected value lives in v6_* tables, with its register row.
Usage: python v6_build_sqlite.py [path to TFM_GITHUB_RELEASE_ASSETS]
"""
import hashlib, json, pathlib, sqlite3, sys, tempfile, zipfile, datetime, shutil
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parents[2]
OUT = REPO / '06_database_corrections_v6'
ASSETS = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else REPO.parent / 'TFM_GITHUB_RELEASE_ASSETS'
SRC = {'train': ('TFM_DATABASE_TRAIN_DEV_DATA_FREEZE_20261113.zip', 'a7f473fdf248174c5c53e4173ea0a7bcd09905331dda9ad13c934e31c2dfd4de',
                 'TFM_DATABASE_TRAIN_DEV_V6_CORRECTED_20261122.zip'),
       'test': ('TFM_DATABASE_EXTERNAL_TEST_DATA_FREEZE_20261118.zip', '106ef154d01a1164acd51a8d19dfb52cc15e7c60b4a41a40b1ff9f8dfd89593b',
                'TFM_DATABASE_EXTERNAL_TEST_V6_CORRECTED_20261122.zip')}


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def main():
    reg = pd.read_csv(OUT / 'data' / 'corrections_register_V6.csv', low_memory=False)
    audit = pd.read_csv(OUT / 'data' / 'study_audit_corrections_V6.csv')
    summary = json.loads((OUT / 'results' / 'summary_V6.json').read_text(encoding='utf-8'))
    result = {}
    for split, (zname, want, outname) in SRC.items():
        with tempfile.TemporaryDirectory() as td:
            td = pathlib.Path(td)
            with zipfile.ZipFile(ASSETS / zname) as z:
                z.extract('TFM_DATABASE_CLASS_A_FINAL.sqlite', td)
            src = td / 'TFM_DATABASE_CLASS_A_FINAL.sqlite'
            got = sha(src)
            assert got == want, f'{zname}: sha256 {got} != {want}'
            dst = td / 'TFM_DATABASE_CLASS_A_V6_CORRECTED.sqlite'
            shutil.copyfile(src, dst)
            con = sqlite3.connect(dst)
            con.execute('PRAGMA journal_mode=DELETE')
            tables = {}
            for ep in ['yield', 'dry_biomass']:
                df = pd.read_parquet(OUT / 'data' / f'{split}_{ep}_V6.parquet')
                for c in df.columns:                       # SQLite cannot store lists/dicts
                    if df[c].dtype == object:
                        df[c] = df[c].map(lambda v: json.dumps(v, default=str) if isinstance(v, (list, dict)) else v)
                t = f'v6_{split}_{ep}'
                df.to_sql(t, con, index=False, if_exists='replace')
                tables[t] = len(df)
            r = reg[reg.split == split]
            r.to_sql('v6_corrections_register', con, index=False, if_exists='replace'); tables['v6_corrections_register'] = len(r)
            if split == 'train':
                audit.to_sql('v6_study_audit_corrections', con, index=False, if_exists='replace'); tables['v6_study_audit_corrections'] = len(audit)
            mp = pd.read_csv(OUT / 'results' / f'moderators_parsed_{split}_V6.csv', low_memory=False)
            mp.to_sql('v6_moderators_parsed', con, index=False, if_exists='replace'); tables['v6_moderators_parsed'] = len(mp)
            man = {'built_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
                   'base_asset': zname, 'base_sqlite_sha256': want, 'script': 'TFM_GITHUB_REPO/06_database_corrections_v6/scripts/v6_corrections.py',
                   'v6_tables': tables, 'runs': {k: v for k, v in summary['runs'].items() if k.startswith(split)},
                   'note': 'Original tables unchanged. Use v6_<split>_<endpoint> with in_default_v6 / in_quality_core_v6.'}
            pd.DataFrame([{'key': k, 'value': json.dumps(v, ensure_ascii=False, default=str)} for k, v in man.items()]).to_sql(
                'v6_manifest', con, index=False, if_exists='replace')
            con.commit()
            assert con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            con.close()
            dsha = sha(dst)
            zout = ASSETS / outname
            assert not zout.exists() or zout.name != zname
            with zipfile.ZipFile(zout, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
                z.write(dst, dst.name)
            result[split] = {'asset': outname, 'sqlite_sha256': dsha, 'zip_bytes': zout.stat().st_size, 'tables': tables}
            print(split, result[split])
    (OUT / 'results' / 'V6_RELEASE_ASSETS.json').write_text(json.dumps(result, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
