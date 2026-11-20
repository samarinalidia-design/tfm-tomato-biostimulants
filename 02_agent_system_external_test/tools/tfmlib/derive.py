"""Reproducible summaries of a bounded relevant original supplementary range."""
import hashlib,json,statistics
from pathlib import Path
from .sourceqa import view,get_source
from .db import now,tx

def replicate_summary(con,cfg,request_path):
    d=json.loads(Path(request_path).read_text(encoding='utf-8-sig'))
    required={'source_file_id','sheet','range','group_column','group','biological_id_column','value_column','technical_repeats','unit','n_unit','endpoint','relevance'}
    if not required<=set(d):raise ValueError('missing replicate-summary fields: '+str(sorted(required-set(d))))
    if d['endpoint'] not in ('FRUIT_YIELD','DRY_BIOMASS','FRUIT_NUMBER','MEAN_FRUIT_MASS','WATER_PRODUCTIVITY'):
        raise ValueError('only project-relevant target/productivity raw data may be summarized; no omics matrices')
    if not d['relevance'].strip():raise ValueError('state the TFM objective served by this summary')
    original=view(con,cfg,d['source_file_id'],sheet=d['sheet'],cell_range=d['range'])
    r,p=get_source(con,cfg,d['source_file_id'])
    source_view=Path(original['assets'][-1])
    data=json.loads(source_view.read_text(encoding='utf-8'))['values']
    if not data:raise ValueError('empty range')
    header=[str(x) for x in data[0]]
    for k in ('group_column','biological_id_column','value_column'):
        if header.count(d[k])!=1:raise ValueError('unambiguous named header required: '+d[k])
    g,b,v=[header.index(d[k]) for k in ('group_column','biological_id_column','value_column')]
    units={}
    for row in data[1:]:
        if str(row[g])!=str(d['group']):continue
        if row[b] in (None,'') or row[v] in (None,''):raise ValueError('selected raw data has missing biological ID/value; provide an explicit valid range/disposition')
        try:x=float(row[v])
        except (TypeError,ValueError):raise ValueError('selected value is not numeric')
        import math
        if not math.isfinite(x):raise ValueError('non-finite raw value')
        units.setdefault(str(row[b]),[]).append(x)
    if not units:raise ValueError('group not found')
    if any(len(v)>1 for v in units.values()) and not d['technical_repeats']:
        raise ValueError('repeated biological IDs require documented technical-repeat aggregation')
    values=[statistics.mean(v) for v in units.values()]
    summary={'mean':statistics.mean(values),'sd':statistics.stdev(values) if len(values)>1 else None,'n':len(values),'unit':d['unit'],'n_unit':d['n_unit'],'method':'technical mean within independent biological ID, sample SD ddof=1 across IDs','n_biological':len(values),'n_readings':sum(map(len,units.values()))}
    rid='DER-'+hashlib.sha256(json.dumps({'source':r['sha256'],'recipe':d},sort_keys=True).encode()).hexdigest()[:24]
    payload={**original,'receipt_id':rid,'parent_receipt':original['receipt_id'],'recipe':d,'summary':summary,'verbatim_summary':json.dumps(summary,ensure_ascii=False)}
    dest=cfg.work_dir/'source_views'/rid;dest.mkdir(parents=True,exist_ok=True)
    (dest/'derived_summary.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    with tx(con):con.execute('INSERT OR REPLACE INTO wf_source_receipts VALUES(?,?,?,?,?,?,?,?,?)',(rid,r['study_id'],d['source_file_id'],r['sha256'],None,d['sheet'],d['range'],json.dumps(payload,ensure_ascii=False),now()))
    return payload
