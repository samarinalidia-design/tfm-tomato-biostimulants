"""Fail-closed release and a reproducible, contrast-level human audit."""
from __future__ import annotations
import csv,hashlib,json,math,random
from collections import defaultdict
from pathlib import Path
from .db import rows,get_meta,set_meta,sha256_file,now,tx
from .sourceqa import frozen_ids

def snapshot_hash(con):
    # Exclude volatile build timestamps and human decisions. Any scientific/source change
    # invalidates the old audit; repeating the same deterministic contrast build does not.
    tables=['an_target_values','an_contrasts','wf_design_experiments','wf_design_arms','wf_design_timepoints','wf_moderators','wf_rob','wf_relations','wf_sources','wf_source_audit','wf_core_patches']
    payload={'execution_contract_hash':get_meta(con,'execution_contract_hash')}
    for table in tables:
        clean=[]
        for r in rows(con,f'SELECT * FROM {table}'):
            clean.append({k:v for k,v in r.items() if k not in ('created_at','updated_at','run_id')})
        payload[table]=sorted(clean,key=lambda x:json.dumps(x,sort_keys=True,ensure_ascii=False,default=str))
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()

def audit_item_hash(con,cid):
    found=rows(con,"SELECT * FROM an_contrasts WHERE contrast_id=?",(cid,))
    if not found:return None
    c=found[0]
    payload={"contrast":{k:v for k,v in c.items() if k!="created_at"},"values":[],"moderators":rows(con,"SELECT feature,value,unit,locator,verbatim,availability,verification,receipt_id,source_file_id FROM wf_moderators WHERE study_id=? ORDER BY feature",(c["study_id"],))}
    for vid in json.loads(c["tv_ids"]):
        v=rows(con,"SELECT * FROM an_target_values WHERE tv_id=?",(vid,))[0]
        payload["values"].append({k:x for k,x in v.items() if k not in ("updated_at","created_at","basis_value_ids")})
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def audit_selection(con,cfg):
    from .export import build_frames
    ev=build_frames(con,cfg)['evidence_long'].to_dict('records')
    N=len(ev);k=min(N,max(20,math.ceil(.15*N))) if N else 0
    strata=defaultdict(list)
    for x in ev:strata[f'{x["endpoint"]}|{x["contrast_type"]}|{x["any_figure_source"]}'].append(x)
    rnd=random.Random(cfg.get('queue.random_seed',20261018))
    groups={s:sorted(v,key=lambda r:r['contrast_id']) for s,v in sorted(strata.items())}
    # Largest remainder allocation, at least one per occupied stratum when k permits.
    allocation={s:(1 if k>=len(groups) else 0) for s in groups};remaining=k-sum(allocation.values())
    while remaining>0:
        candidates=[s for s in groups if allocation[s]<len(groups[s])]
        if not candidates:break
        s=max(candidates,key=lambda s:(k*len(groups[s])/max(N,1)-allocation[s],s))
        allocation[s]+=1;remaining-=1
    picked=[]
    for s,v in groups.items():picked.extend(rnd.sample(v,allocation[s]))
    return N,sorted(picked,key=lambda x:x['contrast_id'])

def human_audit_export(con,cfg,path):
    N,picked=audit_selection(con,cfg);sha=snapshot_hash(con)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    cols=['contrast_id','snapshot_hash','study_id','endpoint','contrast_type','tv_ids','mean_t','sd_t','n_t','mean_c','sd_c','n_c','effect','var_effect','uncertainty_assumed','uncertainty_status','source_file_id_t','source_file_id_c','locator_t','locator_c','receipt_id_t','receipt_id_c','verdict','reviewer','notes']
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore');w.writeheader()
        for r in picked:
            old=(rows(con,"SELECT * FROM wf_contrast_audit WHERE contrast_id=? AND verdict='CORRECT' AND item_hash=?",(r['contrast_id'],audit_item_hash(con,r['contrast_id']))) or [{}])[0]
            w.writerow({**r,'snapshot_hash':sha,'verdict':old.get('verdict',''),'reviewer':old.get('reviewer',''),'notes':old.get('notes','')})
    # Keep an explicit arm list including ALL four arms of factorial contrasts.
    tv={r['tv_id']:r for r in rows(con,'SELECT * FROM an_target_values')}
    arms=[]
    for r in picked:
        for vid in json.loads(r['tv_ids']):arms.append({'contrast_id':r['contrast_id'],**tv[vid]})
    (path.parent/'audit_arm_evidence.json').write_text(json.dumps(arms,ensure_ascii=False,indent=2),encoding='utf-8')
    from openpyxl import Workbook
    from openpyxl.styles import Font,PatternFill,Alignment,Protection
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.utils import get_column_letter
    wb=Workbook();ws=wb.active;ws.title='Human audit';ws.append(cols)
    with path.open(encoding='utf-8-sig',newline='') as f:
        data=list(csv.DictReader(f))
    for r in data:ws.append([r.get(c,'') for c in cols])
    ws.freeze_panes='D2';ws.auto_filter.ref=ws.dimensions
    for i,c in enumerate(cols,1):
        ws.column_dimensions[get_column_letter(i)].width=22 if c not in ('locator_t','locator_c','notes') else 48
        for cell in ws[get_column_letter(i)]:
            cell.alignment=Alignment(vertical='top',wrap_text=True)
            if c in ('contrast_id','snapshot_hash','study_id','receipt_id_t','receipt_id_c'):cell.number_format='@'
            if cell.row==1:cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='26384B')
            elif c in ('verdict','reviewer','notes'):cell.protection=Protection(locked=False);cell.fill=PatternFill('solid',fgColor='FFF2CC')
    vcol=get_column_letter(cols.index('verdict')+1)
    dv=DataValidation(type='list',formula1='"CORRECT,INCORRECT,UNSURE"',allow_blank=True);ws.add_data_validation(dv)
    if len(data):dv.add(f'{vcol}2:{vcol}{len(data)+1}')
    ws.protection.sheet=True
    armws=wb.create_sheet('Arm evidence')
    acols=['contrast_id','tv_id','study_id','arm_key','endpoint','mean','sd','n','n_unit','dispersion_type','dispersion_type_reported','dispersion_basis','dispersion_value','error_bar_status','error_bar_relative_uncertainty','dispersion_provenance_json','unit_raw','mean_norm','sd_norm','source_file_id','page','locator','source_cell','receipt_id','original_view','uncertainty_original_view']
    armws.append(acols)
    for arm in arms:
        rid=arm.get('receipt_id');receipts=rows(con,'SELECT payload FROM wf_source_receipts WHERE receipt_id=?',(rid,));assets=json.loads(receipts[0]['payload']).get('assets',[]) if receipts else []
        png=next((p for p in assets if p.endswith('.png')),assets[-1] if assets else '')
        uncertainty=json.loads(arm.get('dispersion_provenance_json') or 'null') or {}
        urows=rows(con,'SELECT payload FROM wf_source_receipts WHERE receipt_id=?',(uncertainty.get('receipt_id'),))
        uassets=json.loads(urows[0]['payload']).get('assets',[]) if urows else []
        upng=next((p for p in uassets if p.endswith('.png')),uassets[-1] if uassets else '')
        entry={**arm,'original_view':png,'uncertainty_original_view':upng};armws.append([entry.get(c) for c in acols])
        for column,target in [('original_view',png),('uncertainty_original_view',upng)]:
            if target:armws.cell(armws.max_row,acols.index(column)+1).hyperlink=target
    armws.freeze_panes='D2';armws.auto_filter.ref=armws.dimensions
    for i,c in enumerate(acols,1):
        armws.column_dimensions[get_column_letter(i)].width=45 if c in ('locator','source_cell','original_view') else 20
        for cell in armws[get_column_letter(i)]:
            cell.alignment=Alignment(vertical='top',wrap_text=True)
            if cell.row==1:cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='26384B')
    wb.save(path.with_suffix('.xlsx'))
    set_meta(con,'human_audit_expected',{'snapshot_hash':sha,'N':N,'k':len(picked),'ids':[r['contrast_id'] for r in picked]})
    return {'N_retained_contrasts':N,'k':len(picked),'csv':str(path),'xlsx':str(path.with_suffix('.xlsx')),'snapshot_hash':sha,'note':'Author or appointed human expert checks all arms/critical fields; agents cannot enter human verdicts.'}

def human_audit_import(con,cfg,path,reviewer):
    expected=json.loads(get_meta(con,'human_audit_expected') or '{}');sha=snapshot_hash(con)
    if expected.get('snapshot_hash')!=sha:raise ValueError('data changed; regenerate human audit after corrections')
    if not reviewer.strip() or reviewer.lower() in ('agent','claude','ai','assistant'):raise ValueError('named human reviewer required')
    path=Path(path)
    if path.suffix.lower()=='.xlsx':
        from openpyxl import load_workbook
        wb=load_workbook(path,read_only=True,data_only=True);it=wb['Human audit'].iter_rows(values_only=True);header=next(it);data=[dict(zip(header,row)) for row in it if any(x is not None for x in row)];wb.close()
    else:
        with path.open(encoding='utf-8-sig',newline='') as f:data=list(csv.DictReader(f))
    allowed=set(expected['ids']);seen=set();prepared=[]
    for r in data:
        cid=r['contrast_id']
        if cid not in allowed or cid in seen:raise ValueError('unexpected or duplicate audit contrast')
        seen.add(cid)
        if r.get('snapshot_hash')!=sha:raise ValueError('stale human audit row')
        v=str(r.get('verdict') or '').strip().upper()
        if v not in ('CORRECT','INCORRECT','UNSURE'):raise ValueError('every selected contrast needs CORRECT/INCORRECT/UNSURE')
        prepared.append((cid,sha,v,reviewer,r.get('notes'),now(),audit_item_hash(con,cid)))
    if seen!=allowed:raise ValueError('audit is incomplete')
    with tx(con):
        for r in prepared:
            con.execute('INSERT OR REPLACE INTO wf_contrast_audit VALUES(?,?,?,?,?,?,?)',r)
            if r[2]!='CORRECT':
                c=rows(con,'SELECT * FROM an_contrasts WHERE contrast_id=?',(r[0],))[0]
                from .tasks import create_task,set_state
                set_state(con,c['study_id'],'STRUCTURED','HUMAN_AUDIT_RECHECK',locked=0,notes='Human audit requested source recheck: '+str(r[4]))
                create_task(con,cfg,c['study_id'],'DESIGN','human-fix-'+sha[:12])
    return {'imported':len(prepared),'correct':sum(r[2]=='CORRECT' for r in prepared)}

def checks(con,cfg,include_audit=True):
    from .export import build_frames
    from .validate import core_rules,verified_rules,contrast_rules
    scope=frozen_ids(cfg); actual={r['study_id'] for r in rows(con,'SELECT study_id FROM wf_study_status')}
    result=[]
    def add(gate,ok,value):result.append({'gate':gate,'status':'PASS' if ok else 'FAIL','value':value})
    from .config import execution_contract_hash
    add("execution_contract_unchanged",get_meta(con,"execution_contract_hash")==execution_contract_hash(cfg),"code/schema/prompts/scientific configuration fingerprint")
    add('frozen_399_scope',actual==scope and len(actual)==cfg.get('scope.expected_count',399),f'{len(actual)} studies; exact frozen ID equality')
    if len(scope)>=10:add("real_source_pilot",get_meta(con,"pilot_status")=="PASS",get_meta(con,"pilot_status") or "PENDING")
    # Recompute live integrity; never trust a stale wf_validation table.
    live=core_rules(con,cfg)+verified_rules(con,cfg)+contrast_rules(con,cfg)
    blocking=[x for x in live if x[1]=='BLOCKING']
    blocking+=rows(con,"SELECT * FROM wf_validation WHERE status='OPEN' AND severity='BLOCKING'")
    add('relational_and_blocking_qa',not blocking,f'{len(blocking)} blockers')
    unfinished=rows(con,"SELECT study_id,state FROM wf_study_status WHERE state NOT IN ('CLOSED','NO_TARGET_CONFIRMED','EXCLUDED_SCOPE')")
    add('all_399_scientifically_closed',not unfinished,f'{len(unfinished)} unfinished')
    primary_recall_gaps=[]
    if cfg.get('queue.primary_absence_requires_second_review', True):
        for study in rows(con,"SELECT study_id,yield_status FROM wf_study_status WHERE state<>'EXCLUDED_SCOPE'"):
            passes={r['pass']:r for r in rows(con,"SELECT * FROM wf_triage WHERE study_id=?",(study['study_id'],))}
            first=passes.get('P1')
            if not first:
                primary_recall_gaps.append(study['study_id']+': no new original-source inventory')
            elif first['fruit_yield']!='PRESENT':
                second=passes.get('P2')
                completed=con.execute("SELECT 1 FROM wf_tasks WHERE study_id=? AND task_type='TRIAGE_2ND' AND status='DONE'",(study['study_id'],)).fetchone()
                if not second or not completed or second['fruit_yield']=='UNCLEAR':
                    primary_recall_gaps.append(study['study_id']+': primary absence not independently resolved')
                elif study['yield_status']!=second['fruit_yield']:
                    primary_recall_gaps.append(study['study_id']+': primary status differs from independent search')
    add('primary_target_absence_independently_reviewed',not primary_recall_gaps,f'{len(primary_recall_gaps)} gaps: {primary_recall_gaps[:20]}')
    busy=rows(con,"SELECT task_id,status FROM wf_tasks WHERE status NOT IN ('DONE','CANCELLED')")
    add('task_queue_closed',not busy,f'{len(busy)} ready/leased/failed tasks')
    known=rows(con,'SELECT * FROM wf_sources');ok=[r for r in known if r['status']=='OK' and r['path'] and Path(r['path']).is_file()]
    # Rehash all originals for final release to catch silent Drive updates.
    unchanged=[r for r in ok if sha256_file(Path(r['path']))==r['sha256']]
    n_expected=len(__import__('tfmlib.sourceqa',fromlist=['expected']).expected(cfg))
    add('original_sources_available',len(unchanged)==n_expected==len(known),f'{len(unchanged)}/{n_expected} originals with unchanged bytes')
    qa={r['source_file_id']:r for r in rows(con,'SELECT * FROM wf_source_audit')}
    done=[r for r in known if r['source_file_id'] in qa and qa[r['source_file_id']]['disposition'] in ('CHECKED','IRRELEVANT')]
    add('docling_and_original_source_review',len(done)==n_expected,f'{len(done)}/{n_expected} source dispositions')
    targets=rows(con,'SELECT * FROM an_target_values');bad=[]
    from .sourceqa import check_receipt
    for r in targets:
        try:
            check_receipt(con,cfg,r['study_id'],r['source_file_id'],r.get('receipt_id'),r.get('page'))
            if not r.get('source_cell'):raise ValueError('missing cell')
        except ValueError:bad.append(r['tv_id'])
    add('critical_values_checked_in_original',not bad,f'{len(bad)} targets without current exact-source receipt/cell')
    incomplete_bars=[];bad_dispersion_sources=[]
    for r in targets:
        if r.get('source_kind')=='FIGURE' and not r.get('error_bar_status'):
            incomplete_bars.append(r['tv_id'])
        if (r.get('error_bar_status') or '').startswith('DIGITIZED'):
            bound=r.get('error_bar_relative_uncertainty')
            if bound is None or not r.get('error_bar_bounds_json'):incomplete_bars.append(r['tv_id'])
        provenance=json.loads(r.get('dispersion_provenance_json') or 'null')
        if r.get('dispersion_value') is not None:
            if not provenance:bad_dispersion_sources.append(r['tv_id']);continue
            try:
                check_receipt(con,cfg,r['study_id'],provenance['source_file_id'],provenance.get('receipt_id'))
                if not provenance.get('source_cell'):raise ValueError('missing uncertainty cell')
            except (ValueError,KeyError):bad_dispersion_sources.append(r['tv_id'])
    add('figure_error_bars_accounted_for',not incomplete_bars,f'{len(incomplete_bars)} missing error-bar dispositions/bounds')
    add('uncertainty_original_provenance',not bad_dispersion_sources,f'{len(bad_dispersion_sources)} uncertainty values without original evidence')
    slots=rows(con,"SELECT * FROM wf_target_slots WHERE route IN ('EXTRACT','FIGURE','TWIN_VALIDATION') AND status NOT IN ('VERIFIED','VERIFIED_PARTIAL','NOT_EXTRACTABLE')")
    add('expected_slots_complete',not slots,f'{len(slots)} incomplete slots')
    unchecked=rows(con,"SELECT t.tv_id FROM an_target_values t WHERE t.endpoint='DRY_BIOMASS' AND NOT EXISTS (SELECT 1 FROM wf_dry_basis b WHERE b.study_id=t.study_id AND b.tv_record_key=t.record_key)")
    add('dry_basis_checked',not unchecked,f'{len(unchecked)} dry-biomass values without a basis check')
    missing_assets=rows(con,"SELECT a.* FROM wf_asset_inventory a WHERE a.disposition='SLOT' AND NOT EXISTS (SELECT 1 FROM wf_target_slots s WHERE s.study_id=a.study_id AND s.source_file_id=a.source_file_id AND TRIM(LOWER(s.locator_label))=TRIM(LOWER(a.locator)))")
    add('relevant_assets_represented',not missing_assets,f'{len(missing_assets)} relevant assets without target slot')
    open_review=rows(con,"SELECT * FROM wf_review WHERE status='OPEN'")
    proposed=rows(con,"SELECT * FROM wf_core_patches WHERE status='PROPOSED'")
    rels=rows(con,"SELECT * FROM wf_relations WHERE status='PROPOSED'")
    add('questions_patches_relations_resolved',not(open_review or proposed or rels),f'{len(open_review)} questions; {len(proposed)} patches; {len(rels)} relations')
    st={r['study_id'] for r in targets}
    rob={(r['study_id'],r['domain']) for r in rows(con,'SELECT study_id,domain FROM wf_rob')}
    from .submit import ROB_DOMAINS
    miss=[s for s in st if any((s,d) not in rob for d in ROB_DOMAINS)]
    add('risk_of_bias_10_domains',not miss,f'{len(miss)} target studies incomplete')
    bad_mods=rows(con,"SELECT * FROM wf_moderators WHERE verification NOT IN ('SOURCE_VERIFIED_AB','SOURCE_ADJUDICATED')")
    for m in rows(con,'SELECT * FROM wf_moderators'):
        try:check_receipt(con,cfg,m['study_id'],m['source_file_id'],m['receipt_id'])
        except ValueError:bad_mods.append(m)
    add('used_moderators_independently_verified',not bad_mods,f'{len(bad_mods)} unverified/stale moderator facts')
    outliers=rows(con,"SELECT * FROM wf_validation WHERE status='OPEN' AND rule_id='C001'")
    add('outliers_reviewed_without_deletion',not outliers,f'{len(outliers)} unresolved outliers')
    test=con.execute("SELECT COUNT(*) FROM studies WHERE UPPER(COALESCE(dataset_role,'')) LIKE '%TEST%'").fetchone()[0]
    add('no_inspected_confirmatory_test',test==0,f'{test} TEST labels')
    frames=build_frames(con,cfg)
    badfeat=[c for df in frames.values() for c in df.columns if c.startswith('f_') and any(x in c.lower() for x in ('transcript','metabolom','proteom','gene_expression','mda','proline','chlorophyll','outcome'))]
    add('relevant_features_and_no_leakage',not badfeat,str(sorted(set(badfeat))))
    if include_audit:
        N,picked=audit_selection(con,cfg);sha=snapshot_hash(con)
        correct={r['contrast_id'] for r in rows(con,"SELECT * FROM wf_contrast_audit WHERE verdict='CORRECT'") if r.get('item_hash')==audit_item_hash(con,r['contrast_id'])}
        ids={r['contrast_id'] for r in picked}
        add('human_contrast_audit',ids<=correct,f'{len(ids&correct)}/{len(ids)} required of N={N}')
    return result
