import json, hashlib, pathlib
raw = pathlib.Path(__file__).resolve().parents[1]/'data'/'raw'
m = json.load(open(raw/'MANIFEST.json'))
ref = {f['file']: f for f in m['files']}
rows = []
for fn in ['contrast_candidates.parquet','feature_policy.csv','data_dictionary.csv']:
    h = hashlib.sha256((raw/fn).read_bytes()).hexdigest()
    ok = h == ref[fn]['sha256']
    rows.append(f"{fn}\t{ref[fn]['sha256']}\t{h}\t{'MATCH' if ok else 'MISMATCH'}")
    assert ok, fn
open(raw/'SHA256_VERIFICATION.tsv','w').write("file\tmanifest_sha256\tcopy_sha256\tstatus\n"+"\n".join(rows)+"\n")
print("\n".join(rows)); print('build', m['build'], m['status'])
