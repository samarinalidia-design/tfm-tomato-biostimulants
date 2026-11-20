"""Contrast-level marts and atomic release. Final export refuses all failed gates."""
from __future__ import annotations
import datetime,hashlib,json,os,platform,sqlite3,tempfile,shutil
from pathlib import Path
import pandas as pd
from .db import rows,q,get_meta,sha256_file,now
from . import __version__

def role_of(c):
    if c in ('effect','var_effect'):return 'TARGET'
    if c=='f_product_name':return 'PROVENANCE_ONLY'
    if c.startswith(('f_randomization','f_statistical_test','f_experimental_design','f_replicate_unit','f_n_replicates')):return 'QUALITY_FEATURE'
    if c.startswith('f_'):return 'FEATURE'
    if c.endswith('_id') or c in ('study_id','experiment_key','arm_key_t','arm_key_c','tv_ids'):return 'ID_GROUP'
    if c.startswith(('locator','receipt','source_','verbatim')):return 'PROVENANCE_ONLY'
    if c in ('weighted_eligible','analysis_eligible','exclusion_reason','flags','min_verification','uncertainty_assumed','weighted_reported_uncertainty_only_eligible','uncertainty_status','uncertainty_assumption_policy'):return 'QUALITY_FEATURE'
    return 'CONTEXT_ONLY'

def _temporal(st):
    if st.get('dataset_role')!='TRAIN_DEV':return False
    tag=str(st.get('temporal_eligibility') or '')
    if not tag.startswith('ELIGIBLE_'):return False
    try:y=int(float(st.get('year')))
    except (ValueError,TypeError):y=None
    if y is not None and y<=2023:return True
    # Boundary dates require an actual source-verified temporal decision in v2.
    return False

def _numeric_feature(feature,value,unit):
    import math
    try:v=float(value)
    except (TypeError,ValueError):return None
    if not math.isfinite(v):return None
    if 'days' in feature:
        u=(unit or '').strip().lower()
        if u in ('h','hr','hrs','hour','hours'):v/=24.0
        elif u not in ('','d','day','days','dap','dat','das'):return None
    if feature=='plant_density_m2':
        import re
        if re.search(r'\bha\b|hectare',(unit or '').lower()):v/=10000.0
    return v

def build_frames(con,cfg):
    raw_units={r['tv_id']:r['unit_raw'] for r in rows(con,'SELECT tv_id,unit_raw FROM an_target_values')}
    def a_unit(r):return raw_units.get(json.loads(r['tv_ids'])[0])
    dry={(r['study_id'],r['tv_record_key']):r['basis'] for r in rows(con,'SELECT * FROM wf_dry_basis')}
    studies={str(s['study_id']):s for s in rows(con,'SELECT * FROM studies')}
    temporal={r['study_id']:r for r in rows(con,'SELECT * FROM wf_temporal_review')}
    tv={r['tv_id']:r for r in rows(con,'SELECT * FROM an_target_values')}
    mods={}
    for m in rows(con,'SELECT * FROM wf_moderators ORDER BY mod_id'):
        d=mods.setdefault((m['study_id'],m['experiment_key'] or '',m['arm_key'] or ''),{})
        prefix='f_' if m['availability']=='PLAN_PRE_EXPERIMENT' else 'context_'
        if m['feature'] in ('stress_intensity','stress_intensity_unit'):prefix='context_'
        numeric={'soil_ph','soil_ec','organic_matter','pot_volume_l','plant_density_m2','latitude','temperature_day_c','temperature_night_c','relative_humidity','vpd_kpa','photoperiod_h','ppfd','stress_duration_days','nacl_mm','ec_irrigation_ds_m','field_capacity_pct','dose','n_applications','days_application_before_stress','n_replicates'}
        value=m['value']
        if m['feature'] in numeric and prefix=='f_':
            d['context_'+m['feature']+'_raw']=value
            value=_numeric_feature(m['feature'],value,m['unit'])
        # Rows of one group never overwrite each other: disagreement empties the feature, all values stay visible.
        key=prefix+m['feature'];all_key='context_'+m['feature']+'_all'
        d[all_key]=json.dumps(sorted(set(json.loads(d.get(all_key,'[]')))|{str(m['value'])}),ensure_ascii=False)
        d[key]=None if key in d and d[key]!=value else value
        if m['unit']:d[key+'_unit']=m['unit']
    allrows=[]
    for c in rows(con,'SELECT * FROM an_contrasts ORDER BY contrast_id'):
        ids=json.loads(c['tv_ids']);a,b=tv[ids[0]],tv[ids[1]];st=studies.get(c['study_id'],{})
        flags=json.loads(c.get('flags') or '[]');reason=[]
        assumed=any(tv[i].get('dispersion_basis')=='USER_ASSUMED_SE' for i in ids)
        if assumed and 'USER_ASSUMED_SE' not in flags:flags.append('USER_ASSUMED_SE')
        c['flags']=json.dumps(flags)
        timeok=_temporal(st) or temporal.get(c['study_id'],{}).get('eligibility')=='ELIGIBLE_PRE2024'
        if not timeok:reason.append('TEMPORAL_OR_DATASET_ROLE_INELIGIBLE')
        if any(x.startswith('DUPLICATE_EXCLUDED:') for x in flags):reason.append('DUPLICATE_VERSION')
        if c['effect'] is None:reason.append('NONCOMPUTABLE_FOR_PRESPECIFIED_METRIC')
        r={**c,'yield_scope':a.get('yield_scope'),'mass_basis':a.get('mass_basis'),'denominator':a.get('denominator'),'harvest_window':a.get('harvest_window'),'organ_scope':a.get('organ_scope'),'timepoint_key':a['timepoint_key'],'timepoint_days':a.get('timepoint_days'),'is_terminal_t':a.get('is_terminal'),'is_terminal_c':b.get('is_terminal'),'genotype':a.get('genotype'),'season':a.get('season'),'site':a.get('site'),'unit_norm':a.get('unit_norm'),'year':st.get('year'),'doi':st.get('doi'),'title':st.get('title'),'dataset_role':st.get('dataset_role'),
           'source_file_id_t':a['source_file_id'],'source_file_id_c':b['source_file_id'],'locator_t':a['locator'],'locator_c':b['locator'],'receipt_id_t':a.get('receipt_id'),'receipt_id_c':b.get('receipt_id'),'source_cell_t':a.get('source_cell'),'source_cell_c':b.get('source_cell'),
           'analysis_eligible':int(not reason),'exclusion_reason':';'.join(reason),'weighted_eligible':int(not reason and c['var_available'] and c.get('var_effect',0)>0 and c.get('n_t') and c['n_t']>=2 and c.get('n_c') and c['n_c']>=2),'uncertainty_status':'AVAILABLE' if c['var_available'] else 'NOT_REPORTED_OR_NOT_DEFENSIBLE'}
        r['dry_basis_confirmed']=int(all(dry.get((tv[i]['study_id'],tv[i]['record_key']))=='DRY_CONFIRMED' for i in ids))
        variance=c.get('var_effect')
        r.update(uncertainty_assumed=int(assumed),uncertainty_assumption_policy='USER_DIRECTIVE_2026-10-19' if assumed else None,
                 weighted_reported_uncertainty_only_eligible=int(r['weighted_eligible'] and not assumed),
                 error_bar_digitization_over_5pct=int('ERROR_BAR_DIGITIZATION_OVER_5PCT' in flags),
                 per_plant_context_assumed=int('PER_PLANT_CONTEXT_ASSUMED' in flags))
        if assumed and c['var_available']:r['uncertainty_status']='AVAILABLE_USER_ASSUMED_SE'
        se=__import__('math').sqrt(variance) if variance is not None and variance>=0 else None
        r.update(se_effect=se,ci95_lower=c['effect']-1.96*se if c['effect'] is not None and se is not None else None,ci95_upper=c['effect']+1.96*se if c['effect'] is not None and se is not None else None,ci95_method='ASYMPTOTIC_NORMAL_APPROXIMATE' if se is not None else None)
        for key in [(c['study_id'],'',''),(c['study_id'],c['experiment_key'] or '',''),(c['study_id'],'',c['arm_key_t']),(c['study_id'],c['experiment_key'] or '',c['arm_key_t'])]:r.update(mods.get(key,{}))
        for arm,n in [(a,'t'),(b,'c')]:
            for key in ('mean','sd','n','n_unit','n_source','dispersion_type','dispersion_type_reported','dispersion_value','dispersion_basis','dispersion_provenance_json','error_bar_status','error_bar_bounds_json','error_bar_relative_uncertainty','unit_raw','mean_norm','sd_norm','outcome_context_json','context_key'):r[key+'_raw_'+n]=arm.get(key)
        allrows.append(r)
    candidates=pd.DataFrame(allrows)
    ev=[r for r in allrows if r['analysis_eligible']]
    frames={'biotic_measurements_verified':pd.DataFrame([r for r in tv.values() if r['endpoint'].startswith('BIOTIC_')],columns=list(next(iter(tv.values())).keys()) if tv else ['tv_id','study_id','endpoint','mean','outcome_context_json']), 'contrast_candidates':candidates,'evidence_long':pd.DataFrame(ev),'arm_values_verified':pd.DataFrame(list(tv.values()))}
    marts={k:[] for k in ['A_direct_yield','A_direct_dry_biomass','A_strict_SxB','A_strict_AxB','A_descriptive','A_productivity_components','A_biotic_secondary','A_meta_yield_weighted','A_meta_dry_biomass_weighted','A_meta_SxB_weighted','A_meta_AxB_weighted','A_direct_yield_assumed','A_meta_yield_assumed_weighted','A_direct_yield_broad','A_meta_yield_broad_weighted','A_main_effect_yield','A_direct_yield_unit_unresolved','A_meta_yield_unit_unresolved_weighted','A_box_centre_assumed']}
    # Organ preference is resolved within the same contrast context, before variance filtering.
    bm={}
    for r in ev:
        if r['endpoint']=='DRY_BIOMASS' and r['contrast_type']=='SB_vs_S' and r['is_terminal_t'] and r['is_terminal_c'] and r['organ_scope'] in ('WHOLE_PLANT','SHOOT'):
            key=tuple(r[k] for k in ('study_id','experiment_key','arm_key_t','arm_key_c','timepoint_key','genotype','season','site'))
            old=bm.get(key)
            if old is None or r['organ_scope']=='WHOLE_PLANT':bm[key]=r
    bmids={r['contrast_id'] for r in bm.values()}
    for r in ev:
        strict=False
        # Author decision 2026-11-06: a boxplot centre is usually a median, so it never joins contrasts built on means.
        if 'BOX_CENTRE_ASSUMED_MEAN' in (r.get('flags') or ''):
            marts['A_box_centre_assumed'].append({**r,'primary_estimand':0})
            marts['A_descriptive'].append(r)
            continue
        if r['contrast_type']=='B_MAIN_EFFECT':marts['A_main_effect_yield'].append({**r,'primary_estimand':0})
        if r['endpoint'].startswith('BIOTIC_'):marts['A_biotic_secondary'].append(r)
        if r['contrast_type']=='SB_vs_S' and r['endpoint']=='FRUIT_YIELD':
            strict=r['yield_scope']=='TOTAL' and r['mass_basis']=='FRESH' and r['harvest_window']=='CUMULATIVE' and r['denominator'] not in ('UNSPECIFIED','OTHER',None) and bool(r['unit_norm'])
            if strict:
                marts['A_direct_yield'].append({**r,'primary_estimand':1})
                if r['weighted_eligible']:marts['A_meta_yield_weighted'].append(r)
            elif r['yield_scope'] in ('TOTAL','UNSPECIFIED') and r['mass_basis'] in ('FRESH','UNSPECIFIED') and r['harvest_window'] in ('CUMULATIVE','UNSPECIFIED') and r['denominator'] not in ('UNSPECIFIED','OTHER',None) and bool(r['unit_norm']):
                # Second tier: unspecified attributes are explicit assumptions, never the primary estimand.
                row={**r,'primary_estimand':0,'yield_assumptions':';'.join(f'{f}=UNSPECIFIED' for f in ('yield_scope','mass_basis','harvest_window') if r[f]=='UNSPECIFIED')}
                marts['A_direct_yield_assumed'].append(row)
                if r['weighted_eligible']:marts['A_meta_yield_assumed_weighted'].append(row)
            elif r['yield_scope'] in ('TOTAL','MARKETABLE','UNSPECIFIED') and r['mass_basis'] in ('FRESH','UNSPECIFIED') and r['harvest_window'] in ('CUMULATIVE','SINGLE_HARVEST','PARTIAL','UNSPECIFIED') and r['denominator'] not in ('UNSPECIFIED','OTHER',None) and bool(r['unit_norm']):
                # Third tier (author directive: retain every study with yield): the differing definition stays explicit.
                row={**r,'primary_estimand':0,'yield_assumptions':';'.join(f'{f}={r[f]}' for f in ('yield_scope','mass_basis','harvest_window') if r[f] not in ('TOTAL','FRESH','CUMULATIVE'))}
                marts['A_direct_yield_broad'].append(row)
                if r['weighted_eligible']:marts['A_meta_yield_broad_weighted'].append(row)
            elif r['yield_scope'] in ('TOTAL','MARKETABLE','UNSPECIFIED') and r['mass_basis'] in ('FRESH','UNSPECIFIED') and r['harvest_window'] in ('CUMULATIVE','SINGLE_HARVEST','PARTIAL','UNSPECIFIED'):
                # Fourth tier (author directive: keep yield for ML): lnRR needs one shared raw unit, not a known denominator. Bare g is never read as per plant.
                row={**r,'primary_estimand':0,'yield_assumptions':';'.join([f"denominator={r['denominator']}",f"unit_raw={a_unit(r)}"]+[f'{f}={r[f]}' for f in ('yield_scope','mass_basis','harvest_window') if r[f] not in ('TOTAL','FRESH','CUMULATIVE')])}
                marts['A_direct_yield_unit_unresolved'].append(row)
                if r['weighted_eligible']:marts['A_meta_yield_unit_unresolved_weighted'].append(row)
        elif r['contrast_type']=='SB_vs_S' and r['endpoint']=='DRY_BIOMASS':
            strict=r['contrast_id'] in bmids and bool(r['unit_norm']) and bool(r['dry_basis_confirmed'])
            if strict:
                marts['A_direct_dry_biomass'].append({**r,'primary_estimand':1})
                if r['weighted_eligible']:marts['A_meta_dry_biomass_weighted'].append(r)
        elif r['contrast_type'] in ('SxB','AxB'):
            # Keep endpoint semantics separate. No ambiguous yield / root biomass in strict interaction marts.
            semantic=(r['endpoint']=='FRUIT_YIELD' and r['yield_scope']=='TOTAL' and r['mass_basis']=='FRESH' and r['harvest_window']=='CUMULATIVE') or (r['endpoint']=='DRY_BIOMASS' and r['organ_scope'] in ('WHOLE_PLANT','SHOOT') and r['is_terminal_t'] and r['is_terminal_c'] and r['dry_basis_confirmed'])
            strict=semantic and bool(r['unit_norm'])
            if strict:
                marts['A_strict_SxB' if r['contrast_type']=='SxB' else 'A_strict_AxB'].append(r)
                if r['weighted_eligible']:marts['A_meta_SxB_weighted' if r['contrast_type']=='SxB' else 'A_meta_AxB_weighted'].append(r)
        elif r['contrast_type']=='SB_vs_S' and not r['endpoint'].startswith('BIOTIC_'):marts['A_productivity_components'].append(r)
        if not strict or not r['weighted_eligible']:marts['A_descriptive'].append(r)
    allcols=list(candidates.columns) or ['contrast_id','study_id','endpoint','contrast_type','effect','var_effect','analysis_eligible','weighted_eligible']
    for name,data in marts.items():
        extra=['primary_estimand'] if name in ('A_direct_yield','A_direct_dry_biomass','A_main_effect_yield','A_box_centre_assumed') else (['primary_estimand','yield_assumptions'] if 'yield_assumed' in name or 'yield_broad' in name or 'yield_unit_unresolved' in name else [])
        frames[name]=pd.DataFrame(data,columns=allcols+extra)
    for name in ('evidence_long','contrast_candidates'):
        if frames[name].empty:frames[name]=pd.DataFrame(columns=allcols)
    for name in ('A_strict_SxB','A_strict_AxB'):
        f=frames[name]
        f['n_independent_clusters_endpoint']=f.groupby('endpoint')['dependency_cluster_id'].transform('nunique') if len(f) else pd.Series(dtype='int64')
        f['inference_scope']=f['n_independent_clusters_endpoint'].map(lambda n:'EXPLORATORY_FEWER_THAN_5_CLUSTERS' if n<5 else 'DESIGN_ELIGIBLE_INFERENCE_NOT_YET_FITTED')
    return frames

def effective_tables(con,cfg):
    tv=rows(con,'SELECT * FROM an_target_values');armmap={}
    experiments=[];arms=[];measurements=[];provenance=[]
    for e in rows(con,'SELECT * FROM wf_design_experiments'):
        experiments.append({**e,'experiment_id':e['experiment_id'] or e['study_id']+'::'+e['experiment_key']})
    em={(e['study_id'],e['experiment_key']):e['experiment_id'] for e in experiments}
    for a in rows(con,'SELECT * FROM wf_design_arms'):
        aid=a['arm_id'] or a['study_id']+'::'+a['arm_key'];armmap[(a['study_id'],a['arm_key'])]=aid
        arms.append({**a,'arm_id':aid,'experiment_id':em[(a['study_id'],a['experiment_key'])]})
    for t in tv:
        mid='V2M-'+hashlib.sha256((t['study_id']+'|'+t['record_key']).encode()).hexdigest()[:24]
        pid='V2P-'+mid[4:]
        measurements.append({**t,'measurement_id':mid,'experiment_id':em[(t['study_id'],t['experiment_key'])],'arm_id':armmap[(t['study_id'],t['arm_key'])],'outcome_standard_name':t['endpoint'],'unit':t['unit_norm'],'provenance_id':pid,'verification_status':t['verification']})
        provenance.append({'provenance_id':pid,'study_id':t['study_id'],'source_file_id':t['source_file_id'],'page':t['page'],'locator':t['locator'],'source_cell':t['source_cell'],'source_quote':t['verbatim'],'receipt_id':t['receipt_id']})
    studies=pd.DataFrame(rows(con,'SELECT s.*,w.state AS final_disposition FROM studies s JOIN wf_study_status w ON CAST(s.study_id AS TEXT)=w.study_id'))
    result = {'studies':studies,'files':pd.DataFrame(rows(con,'SELECT s.*,a.disposition,a.relevance FROM wf_sources s LEFT JOIN wf_source_audit a USING(study_id,source_file_id)')),'experiments':pd.DataFrame(experiments),'arms':pd.DataFrame(arms),'measurements':pd.DataFrame(measurements),'provenance_qa':pd.DataFrame(provenance),'moderators':pd.DataFrame(rows(con,'SELECT * FROM wf_moderators')),'risk_of_bias':pd.DataFrame(rows(con,'SELECT * FROM wf_rob')),'study_relations':pd.DataFrame(rows(con,"SELECT * FROM wf_relations WHERE status IN ('CONFIRMED','REFERENCE_ONLY')")),'source_audit':pd.DataFrame(rows(con,'SELECT * FROM wf_source_audit')),'asset_inventory':pd.DataFrame(rows(con,'SELECT * FROM wf_asset_inventory')), 'covariance':pd.DataFrame(rows(con,'SELECT * FROM an_covariance'))}
    fallback={'experiments':['study_id','experiment_key','experiment_id'],'arms':['study_id','arm_key','arm_id','experiment_id'],'measurements':['measurement_id','study_id','experiment_id','arm_id','endpoint','mean','sd','n','provenance_id'],'provenance_qa':['provenance_id','study_id','source_file_id','locator','receipt_id']}
    source_tables={'moderators':'wf_moderators','risk_of_bias':'wf_rob','study_relations':'wf_relations','source_audit':'wf_source_audit','asset_inventory':'wf_asset_inventory','covariance':'an_covariance'}
    for name,df in result.items():
        if not len(df.columns):
            if name in source_tables:
                result[name]=pd.DataFrame(columns=[x[1] for x in con.execute('PRAGMA table_info('+q(source_tables[name])+')')])
            else:result[name]=pd.DataFrame(columns=fallback.get(name,['study_id']))
    return result

def _write_df(df,path):
    # Preserve JSON-compatible heterogeneous metadata in Parquet and Excel without coercing analytical numerics.
    clean=df.copy()
    for c in clean.select_dtypes(include='object').columns:
        clean[c]=clean[c].map(lambda v:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else (str(v) if v is not None and not isinstance(v,str) else v))
    clean.to_csv(path.with_suffix('.csv'),index=False)
    clean.to_parquet(path.with_suffix('.parquet'),index=False)

def export_all(con,cfg,out_dir=None,draft=False):
    from .release import checks,snapshot_hash
    from .validate import run
    from .contrasts import build
    # Always rebuild from the current verified layer and revalidate; no stale PASS metadata.
    build(con,cfg);run(con,cfg,'PRE_EXPORT')
    gates=checks(con,cfg)
    failed=[g for g in gates if g['status']!='PASS']
    if failed and not draft:
        return {'status':'BLOCKED','ready_to_use':False,'failed_gates':failed,'note':'No final files were written; use --draft for a clearly labelled diagnostic preview.'}
    frames=build_frames(con,cfg);eff=effective_tables(con,cfg)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    final=Path(out_dir) if out_dir else cfg.root/'exports'/f'{"DRAFT" if draft else "DATA_FREEZE"}_{stamp}'
    if final.exists():raise ValueError('output folder already exists; use a new immutable build path')
    final.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.tfm_build_',dir=final.parent))
    try:
        for name,df in frames.items():_write_df(df,stage/name)
        for name,df in eff.items():_write_df(df,stage/('db_'+name))
        rawnames=[r['name'] for r in rows(con,"SELECT name FROM sqlite_master WHERE type='table'") if not r['name'].startswith(('wf_','an_','sqlite_'))]
        xlsx=stage/'TFM_DATABASE_CLASS_A_FINAL.xlsx'
        with pd.ExcelWriter(xlsx,engine='openpyxl') as w:
            pd.DataFrame([{'item':'status','value':'DRAFT_NOT_READY' if draft else 'DATA_FREEZE_READY_TO_USE'},{'item':'raw_ sheets','value':'Preserved imported source layer with accepted patches; not independently verified analytical data.'},{'item':'analysis','value':'Use evidence_long and purpose-specific A_ marts; no ML preprocessing was fitted.'}]).to_excel(w,sheet_name='_README',index=False)
            for name,df in {**eff,**frames}.items():df.to_excel(w,sheet_name=name[:31],index=False)
            for name in rawnames:pd.DataFrame(rows(con,f'SELECT * FROM {q(name)}')).to_excel(w,sheet_name=('raw_'+name)[:31],index=False)
        dbpath=stage/'TFM_DATABASE_CLASS_A_FINAL.sqlite'
        dest=sqlite3.connect(dbpath);con.backup(dest)
        for name in rawnames:dest.execute(f'ALTER TABLE {q(name)} RENAME TO {q("raw_"+name)}')
        for name,df in {**eff,**frames}.items():
            if len(df.columns):df.to_sql(name,dest,index=False,if_exists='replace')
        dest.commit()
        if dest.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('exported SQLite integrity check failed')
        dest.close()
        dictionary=[{'table':name,'column':c,'role':role_of(c),'dtype':str(df[c].dtype),'missing':int(df[c].isna().sum())} for name,df in {**eff,**frames}.items() for c in df.columns]
        pd.DataFrame(dictionary).to_csv(stage/'data_dictionary.csv',index=False)
        pd.DataFrame([{'column':d['column'],'role':d['role'],'use_in_primary_model':d['role']=='FEATURE'} for d in dictionary if d['table']=='evidence_long']).drop_duplicates().to_csv(stage/'feature_policy.csv',index=False)
        pd.DataFrame(rows(con,'SELECT * FROM wf_validation')).to_csv(stage/'qa_issues.csv',index=False)
        (stage/'acceptance_report.json').write_text(json.dumps({'ready_to_use':not draft,'gates':gates,'rows':{k:len(v) for k,v in frames.items()}},ensure_ascii=False,indent=2),encoding='utf-8')
        from .diagnostics import write as write_diagnostics
        write_diagnostics(con,frames,stage)
        pd.DataFrame([{'mart':name,'rows':len(df),'studies':df['study_id'].nunique() if 'study_id' in df else 0,'dependency_clusters':df['dependency_cluster_id'].nunique() if 'dependency_cluster_id' in df else 0} for name,df in frames.items()]).to_csv(stage/'readiness_by_mart.csv',index=False)
        (stage/'DATA_FREEZE.md').write_text('DATA_FREEZE_READY_TO_USE\n' if not draft else 'DRAFT_NOT_READY\n',encoding='utf-8')
        files=[p for p in stage.rglob('*') if p.is_file()]
        import importlib.metadata
        deps={n:importlib.metadata.version(n) for n in ('pandas','openpyxl','jsonschema','PyYAML','numpy','Pillow','PyMuPDF','pyarrow','scipy','matplotlib','xlrd')}
        manifest={'build':stamp,'status':'DRAFT_NOT_READY' if draft else 'DATA_FREEZE_READY_TO_USE','ready_to_use':not draft,'snapshot_hash':snapshot_hash(con),'code_version':__version__,'contract_version':cfg.get('contract_version'),'python':platform.python_version(),'dependencies':deps,'execution_contract_hash':get_meta(con,'execution_contract_hash'),'workbook_sha256':get_meta(con,'workbook_sha256'),'scope_sha256':sha256_file(cfg.root/'manifests/scope_A_399.csv'),'files':[{'file':p.relative_to(stage).as_posix(),'sha256':sha256_file(p),'bytes':p.stat().st_size} for p in sorted(files)],'gates':gates}
        (stage/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(stage,final)
        return {'status':'DRAFT' if draft else 'READY_TO_USE','ready_to_use':not draft,'out_dir':str(final),'gates':gates,'rows':{k:len(v) for k,v in frames.items()}}
    except BaseException:
        shutil.rmtree(stage,ignore_errors=True);raise

def export_xlsx(con,cfg,out_path):
    raise ValueError('v2 creates the complete Excel atomically with export --out; standalone --xlsx is disabled')
