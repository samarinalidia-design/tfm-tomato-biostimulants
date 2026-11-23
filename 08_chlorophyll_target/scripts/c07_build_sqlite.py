"""Chlorophyll TRAIN_DEV database: V6 corrected TRAIN_DEV sqlite + chl_* tables, written as a new release asset.

Base   : TFM_DATABASE_TRAIN_DEV_V6_CORRECTED_20261122.zip (never modified; its tables are copied unchanged)
Adds   : chl_study_status    one row per study: status of pass A, pass B, adjudication, final; notes
         chl_values_pass     every value of pass A and pass B as extracted (with receipts and fit files)
         chl_values_adjudicated  final value sets of adjudicated studies (with the decision log in chl_study_status)
         chl_values_final    reconciled values used downstream (agreed A/B, or adjudicated)
         chl_new_arms        arms added for chlorophyll (design not coded in A399 or arms not in it)
         chl_values_with_roles  final values + arm roles + computed a+b totals + SD basis
         chl_contrasts       all contrasts (SB_vs_S, B_vs_C, S_vs_C; CHL_CONTENT and CHL_INDEX)
         chl_train_dataset   the training dataset (c06) with flags, moderators, weights, cv_group
         chl_receipts        render receipts of every pass (page image sha256)
         chl_manifest        provenance, row counts, hashes
Output : TFM_DATABASE_TRAIN_DEV_V8_CHLOROPHYLL_20261122.zip in TFM_GITHUB_RELEASE_ASSETS
Usage  : python c07_build_sqlite.py [path to TFM_GITHUB_RELEASE_ASSETS]
"""
import datetime, hashlib, json, os, pathlib, shutil, sqlite3, sys, tempfile, zipfile
import pandas as pd

OUT = pathlib.Path(__file__).resolve().parents[1]
REPO = OUT.parent
ASSETS = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else REPO.parent / 'TFM_GITHUB_RELEASE_ASSETS'
WORK = pathlib.Path(os.environ.get('CHL_WORK', r"C:/Users/lenovo/Desktop/master's/TFM_CHLOROPHYLL_PILOT/work"))
TAG = os.environ.get('CHL_TAG', 'all')
BASE = 'TFM_DATABASE_TRAIN_DEV_V6_CORRECTED_20261122.zip'
OUTNAME = 'TFM_DATABASE_TRAIN_DEV_V8_CHLOROPHYLL_20261122.zip'


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def sqlable(df):
    df = df.copy()
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].map(lambda v: json.dumps(v, ensure_ascii=False, default=str) if isinstance(v, (list, dict)) else v)
    return df


def outbox(p):
    rows, st = [], {}
    for f in sorted((WORK / 'outbox' / p).glob('*.json')):
        d = json.loads(f.read_text(encoding='utf-8-sig'))
        st[d['study_id']] = d
        for i, v in enumerate(d.get('values', [])):
            rows.append({'study_id': d['study_id'], 'pass': p, 'value_index': i, **v})
    return pd.DataFrame(rows), st


def main():
    A, sA = outbox('A'); B, sB = outbox('B'); J, sJ = outbox('ADJ')
    studies = sorted(set(sA) | set(sB))
    S = []
    arms = []
    for sid in studies:
        fin = sJ.get(sid) or (sA.get(sid) if sA.get(sid, {}).get('status') == sB.get(sid, {}).get('status') else None)
        S.append(dict(study_id=sid, status_A=sA.get(sid, {}).get('status'), status_B=sB.get(sid, {}).get('status'),
                      status_ADJ=sJ.get(sid, {}).get('status'), status_final=(fin or {}).get('status'), adjudicated=sid in sJ,
                      notes_A=sA.get(sid, {}).get('notes'), notes_B=sB.get(sid, {}).get('notes'), adjudication_log=sJ.get(sid, {}).get('notes'),
                      design_issues=json.dumps((fin or {}).get('design_check', {}).get('issues'), ensure_ascii=False)))
        for a in ((fin or {}).get('design_check', {}).get('new_arms') or []):
            arms.append({'study_id': sid, 'source': 'ADJ' if sid in sJ else 'A_B_AGREED', **a})
    rec = []
    for p in ['A', 'B', 'ADJ']:
        f = WORK / f'receipts_{p}.jsonl'
        if f.exists():
            rec += [json.loads(l) for l in f.read_text(encoding='utf-8').splitlines() if l.strip()]
    tables = {
        'chl_study_status': pd.DataFrame(S),
        'chl_values_pass': pd.concat([A, B], ignore_index=True),
        'chl_values_adjudicated': J,
        'chl_values_final': pd.read_csv(OUT / 'data' / f'{TAG}_values_reconciled.csv', dtype={'study_id': str}, low_memory=False),
        'chl_new_arms': pd.DataFrame(arms),
        'chl_values_with_roles': pd.read_csv(OUT / 'data' / f'{TAG}_values_with_roles.csv', dtype={'study_id': str}, low_memory=False),
        'chl_contrasts': pd.read_csv(OUT / 'data' / f'{TAG}_contrasts.csv', dtype={'study_id': str}, low_memory=False),
        'chl_train_dataset': pd.read_parquet(OUT / 'data' / 'chl_train_dataset_V8.parquet'),
        'chl_receipts': pd.DataFrame(rec)}
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        with zipfile.ZipFile(ASSETS / BASE) as z:
            name = [n for n in z.namelist() if n.endswith('.sqlite')][0]
            z.extract(name, td)
        src = td / name; base_sha = sha(src)
        dst = td / 'TFM_DATABASE_CLASS_A_V8_CHLOROPHYLL.sqlite'
        shutil.copyfile(src, dst)
        con = sqlite3.connect(dst); con.execute('PRAGMA journal_mode=DELETE')
        before = {t: con.execute(f'select count(*) from "{t}"').fetchone()[0]
                  for (t,) in con.execute("select name from sqlite_master where type='table'")}
        counts = {}
        for t, df in tables.items():
            sqlable(df).to_sql(t, con, index=False, if_exists='replace'); counts[t] = len(df)
        man = {'built_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'), 'base_asset': BASE,
               'base_sqlite_sha256': base_sha, 'dataset_role': 'TRAIN_DEV (publication year <= 2023)',
               'scripts': 'TFM_GITHUB_REPO/08_chlorophyll_target/scripts c01-c07', 'protocol': 'docs/EXTRACTION_PROTOCOL.md',
               'chl_tables': counts, 'base_tables_unchanged': len(before),
               'note': 'Tables of the V6 base are copied unchanged. Use chl_train_dataset with in_default_chl / in_quality_core_chl; '
                       'cv_group for grouped CV; w_train (equal study weight) as the default training weight.'}
        pd.DataFrame([{'key': k, 'value': json.dumps(v, ensure_ascii=False, default=str)} for k, v in man.items()]).to_sql(
            'chl_manifest', con, index=False, if_exists='replace')
        con.commit()
        after = {t: con.execute(f'select count(*) from "{t}"').fetchone()[0] for t in before}
        assert before == after, 'base tables changed'
        assert con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        con.close()
        dsha = sha(dst)
        zout = ASSETS / OUTNAME
        with zipfile.ZipFile(zout, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            z.write(dst, dst.name)
    res = {'asset': OUTNAME, 'sqlite_sha256': dsha, 'zip_bytes': zout.stat().st_size, 'chl_tables': counts, 'base_tables_unchanged': len(before)}
    (OUT / 'results' / 'V8_RELEASE_ASSET.json').write_text(json.dumps(res, indent=1), encoding='utf-8')
    print(json.dumps(res, indent=1))


if __name__ == '__main__':
    main()
