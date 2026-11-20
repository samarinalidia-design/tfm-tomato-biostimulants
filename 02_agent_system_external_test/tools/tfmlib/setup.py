"""One-time local Drive routing and reproducible preflight. No Drive writes."""
import csv,hashlib,importlib,json,os,re,sys
from pathlib import Path
import yaml
from .db import rows,now,tx,changelog

def configure(cfg,corpus,workbook=None):
    root=Path(corpus).expanduser().resolve()
    if not root.is_dir():raise ValueError('corpus root not found; download/sync original Drive folder first')
    if cfg.root.resolve()==root or cfg.root.resolve().is_relative_to(root):raise ValueError('agent project must be outside synchronized corpus root')
    if (cfg.root/'.claude/settings.local.json').exists():raise ValueError('settings.local.json already exists; retain it and configure exact paths manually')
    def unique(paths,label,required=True):
        paths=sorted(set(paths))
        if len(paths)>1:raise ValueError(f'{label}: ambiguous paths {paths}; use config/paths.yaml with exact path')
        if not paths and required:raise ValueError(f'{label}: not found under {root}')
        return paths[0] if paths else None
    wb=Path(workbook).expanduser().resolve() if workbook else unique(root.rglob('TFM_DATABASE_CLASS_A_WORKING.xlsx'),'workbook')
    dirs=[p for p in root.rglob('*') if p.is_dir()]
    ft=unique([p for p in dirs+[root] if re.match(r'^01[_ ]fulltexts?$',p.name,re.I)],'01 fulltext')
    su=unique([p for p in dirs+[root] if re.match(r'^02[_ ]supplements?$',p.name,re.I)],'02 supplements')
    dl=unique([p for p in dirs+[root] if p.name=='docling_local_sourceqa_v4_3_rerun_380'],'Docling run',False)
    fig=unique([p for p in dirs+[root] if p.name=='figure_extraction_v1_2_queue_aligned'],'figure extraction',False)
    from .sourceqa import frozen_ids
    scope=frozen_ids(cfg);maps=[];ambiguous=[]
    if dl:
        candidates={p.parent for p in dl.rglob('STUDY_HANDOFF*.json')}|{p for p in dl.iterdir() if p.is_dir()}
        for sid in sorted(scope):
            forms={sid,sid.zfill(4) if sid.isdigit() else sid}
            hits=[p for p in candidates if any(re.search(r'(?<![A-Za-z0-9])'+re.escape(x)+r'(?![A-Za-z0-9])',p.name) for x in forms)]
            if len(hits)==1:maps.append({'study_id':sid,'folder':str(hits[0])})
            elif len(hits)>1:ambiguous.append(sid)
    mp=cfg.root/'config/docling_map.csv'
    with mp.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['study_id','folder']);w.writeheader();w.writerows(maps)
    paths={'corpus_root':str(root),'workbook':str(wb),'fulltext_root':str(ft),'supplements_root':str(su),'docling_root':str(dl) if dl else '', 'figures_root':str(fig) if fig else '', 'legacy_figure_json_root':str(fig) if fig else '', 'docling_map_csv':str(mp),'docling_study_globs':['{study_id}','**/{study_id}'],'context':{'max_chars':120000,'keep_sections_regex':'(material|method|experimental|design|treatment|statistic|result|yield|harvest|biomass|table|figure|supplement)','drop_sections_regex':'(introduction|discussion|reference|bibliograph)'}}
    (cfg.root/'config/paths.yaml').write_text(yaml.safe_dump(paths,allow_unicode=True,sort_keys=False),encoding='utf-8')
    # Corpus is read-only, work and DB stay outside the synchronized input tree.
    if cfg.root==root or cfg.root.is_relative_to(root):raise ValueError('agent project must be outside synchronized corpus root')
    local=cfg.root/'.claude/settings.local.json'
    if local.exists():raise ValueError('settings.local.json already exists; retain it and configure exact paths manually')
    corpus_rule='//'+str(root).lstrip('/').replace('\\','/')+'/**'
    local.write_text(json.dumps({'permissions':{'additionalDirectories':[str(root)],'deny':[f'Edit({corpus_rule})']}},ensure_ascii=False,indent=2),encoding='utf-8')
    return {'configured':True,'workbook':str(wb),'docling_mapped':len(maps),'docling_ambiguous':ambiguous,'note':'Missing/ambiguous Docling is a warning; original source verification is still mandatory.'}

def preflight(con,cfg):
    problems=[];versions={}
    for mod in ('pandas','openpyxl','jsonschema','yaml','numpy','PIL','fitz','pyarrow','docx','scipy','matplotlib','xlrd'):
        try:
            m=importlib.import_module(mod);versions[mod]=getattr(m,'__version__','available')
        except ImportError:problems.append('missing dependency: '+mod)
    from .sourceqa import libreoffice_binary
    if not libreoffice_binary():problems.append('LibreOffice not installed: required to read the original legacy DOC supplement')
    for key in ('workbook','fulltext_root','supplements_root'):
        p=cfg.p(key)
        if not p or not p.exists():problems.append('missing/offline path: '+key)
    expected=set(cfg.get('audited_baseline_sha256') or [])
    from .db import sha256_file
    if cfg.p('workbook') and cfg.p('workbook').is_file() and sha256_file(cfg.p('workbook')) not in expected:
        problems.append('baseline workbook hash differs from the bootstrap record; rerun tools/bootstrap_test_corpus.py, never edit it by hand')
    from .sourceqa import frozen_ids,index_sources
    ids=frozen_ids(cfg)
    scopehash=hashlib.sha256(('\n'.join(sorted(ids))+'\n').encode()).hexdigest()
    if scopehash!=str(cfg.get('scope.scope_sha256','')):problems.append('scope IDs changed (scope.scope_sha256 in config/pipeline.yaml)')
    from .mode import is_test,model_freeze,train_dev_identity
    freeze=None
    if is_test(cfg):
        fpath,freeze=model_freeze(cfg)
        if cfg.get('test_protocol.require_model_freeze',True) and not freeze:
            problems.append(f'MODEL_FREEZE.json not found at {fpath}: TFM 3.1 requires the model to be frozen before TEST extraction (run notebook 03 in the ML package first)')
        if train_dev_identity(cfg) is None:problems.append('manifests/train_dev_identity.csv missing: TRAIN_DEV overlap cannot be checked')
    indexed=None
    if not any('path:' in x for x in problems):
        indexed=index_sources(con,cfg)
        if indexed['problems']:problems.append(f'{len(indexed["problems"])} original files missing/ambiguous/changed')
    if not problems and freeze is not None:
        from .db import set_meta,get_meta,sha256_file as _sha
        fpath=model_freeze(cfg)[0];digest=_sha(fpath)
        if get_meta(con,'model_freeze_sha256') not in (None,digest):problems.append('MODEL_FREEZE.json changed after it was recorded for this TEST database')
        else:
            set_meta(con,'model_freeze_sha256',digest);set_meta(con,'model_freeze_path',str(fpath))
            if get_meta(con,'model_freeze_recorded_at') is None:set_meta(con,'model_freeze_recorded_at',now())
    return {'status':'FAIL' if problems else 'PASS','problems':problems,'dependencies':versions,'source_index':indexed,'scope_count':len(ids),'scope_sha256':scopehash,'python':sys.version}

def normalize_metadata(con,cfg):
    n=0
    with tx(con):
        for s in rows(con,'SELECT * FROM studies'):
            try:y=int(float(s.get('year')))
            except (TypeError,ValueError):y=None
            date=str(s.get('first_publication_date') or '')[:10]
            changes={}
            from .mode import role as _role
            if not s.get('dataset_role'):changes['dataset_role']=_role(cfg)
            if s.get('temporal_eligibility')=='PROVISIONAL_YEAR_UNKNOWN' and y and y<=2023 and (not date or date<='2023-12-31'):
                changes['temporal_eligibility']='ELIGIBLE_KNOWN_PRE2024'
            for field,new in changes.items():
                con.execute(f'UPDATE studies SET {field}=? WHERE CAST(study_id AS TEXT)=?',(new,str(s['study_id'])))
                changelog(con,'BASELINE_NORMALIZATION','studies',s['study_id'],'DETERMINISTIC_METADATA',{'field':field,'old':s.get(field),'new':new,'basis':'known baseline year and TFM TRAIN_DEV cutoff; no exact date invented'})
                n+=1
    from .tasks import create_task
    with tx(con):
        for s in rows(con,'SELECT * FROM studies'):
            try: y=int(float(s.get('year')))
            except (TypeError,ValueError):y=None
            if cfg.get('scope.temporal_review_all',False) or y is None or y>2023:
                create_task(con,cfg,str(s['study_id']),'TEMPORAL',priority=1)
    return {'metadata_fields_normalized':n}
