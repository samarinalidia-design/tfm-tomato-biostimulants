"""Source-supported routine corrections and QA, without per-row author approval."""
import json
from .db import ColumnResolver, columns, rows, q, now, tx, changelog, table_exists
from .tasks import create_task, reviewable_patches

def apply_patch(con,cfg,pid,run_id):
    p=(rows(con,'SELECT * FROM wf_core_patches WHERE patch_id=?',(pid,)) or [None])[0]
    if not p: raise ValueError('unknown patch')
    table,field=p['table_name'],p['field']
    if table.startswith(('wf_','an_','sqlite_')) or not table_exists(con,table) or field not in columns(con,table):
        raise ValueError('patch must address an existing core table and field')
    if table=='studies' and field=='study_id': raise ValueError('frozen study_id cannot change')
    rid=p['row_id']; cr=ColumnResolver(con,cfg.column_map)
    if rid.startswith('row:'): key='_row'; rid=int(rid.split(':')[1])
    else:
        candidates=[k for k in columns(con,table) if k.endswith('_id')]
        preferred={'studies':'study_id','experiments':'experiment_id','arms':'arm_id','measurements':'measurement_id','provenance_qa':'provenance_id'}.get(table)
        if preferred: candidates=[preferred]
        hits=[k for k in candidates if con.execute(f'SELECT COUNT(*) FROM {q(table)} WHERE CAST({q(k)} AS TEXT)=?',(str(rid),)).fetchone()[0]==1]
        if len(hits)!=1: raise ValueError('row_id ambiguous: use row:<original Excel row>')
        key=hits[0]
    data=rows(con,f'SELECT * FROM {q(table)} WHERE CAST({q(key)} AS TEXT)=?',(str(rid),))
    if len(data)!=1: raise ValueError('patch must identify exactly one row')
    row=data[0]; sid=str(p['study_id'])
    belongs=str(row.get('study_id',''))==sid
    if table=='studies': belongs=str(row.get('study_id'))==sid
    if not belongs and row.get('experiment_id'):
        belongs=bool(con.execute('SELECT 1 FROM experiments WHERE CAST(experiment_id AS TEXT)=? AND CAST(study_id AS TEXT)=?',(str(row['experiment_id']),sid)).fetchone())
    if not belongs and row.get('arm_id'):
        belongs=bool(con.execute('SELECT 1 FROM arms a JOIN experiments e ON a.experiment_id=e.experiment_id WHERE CAST(a.arm_id AS TEXT)=? AND CAST(e.study_id AS TEXT)=?',(str(row['arm_id']),sid)).fetchone())
    if not belongs: raise ValueError('patch row is not proven to belong to this study')
    old=json.loads(p['current_value'] or 'null');new=json.loads(p['proposed_value'] or 'null')
    if row[field]!=old and str(row[field])!=str(old) and not (row[field] in (None,'') and old in (None,'')): raise ValueError('stale patch current value')
    con.execute(f'UPDATE {q(table)} SET {q(field)}=? WHERE CAST({q(key)} AS TEXT)=?',(new,str(rid)))
    con.execute("UPDATE wf_core_patches SET status='ACCEPTED' WHERE patch_id=?",(pid,))
    changelog(con,run_id,table,str(rid),'APPLY_PATCH',{'field':field,'old':old,'new':new,'patch_id':pid})

def h_patches(ctx):
    from .submit import Reject
    from .sourceqa import check_receipt
    expected={r['patch_id'] for r in reviewable_patches(ctx.con, ctx.study)}
    supplied={d['patch_id'] for d in ctx.d['decisions']}
    if supplied!=expected: raise Reject(['review every proposed patch for this study'])
    for d in ctx.d['decisions']:
        try: check_receipt(ctx.con,ctx.cfg,ctx.study,d['source_file_id'],d['receipt_id'])
        except ValueError as exc: raise Reject([str(exc)])
        if d['decision']=='ACCEPT':
            try: apply_patch(ctx.con,ctx.cfg,d['patch_id'],ctx.run_id)
            except ValueError as exc: raise Reject([str(exc)])
        elif d['decision']=='REJECT': ctx.con.execute("UPDATE wf_core_patches SET status='REJECTED' WHERE patch_id=?",(d['patch_id'],))
        else:
            from .db import add_review
            add_review(ctx.con,ctx.study,'PATCH',f"patch-{d['patch_id']}",d['reason'],['ACCEPT','REJECT'],d['receipt_id'])
    from .submit import maybe_verify
    maybe_verify(ctx)
    return len(supplied)

def h_qa(ctx):
    from .submit import Reject
    from .sourceqa import check_receipt
    from .db import add_review
    for d in ctx.d['decisions']:
        r=(rows(ctx.con,"SELECT * FROM wf_validation WHERE issue_id=? AND status='OPEN'",(d['issue_id'],)) or [None])[0]
        if not r or (r['study_id'] and r['study_id']!=ctx.study): raise Reject(['issue is not an open issue of this study'])
        try: check_receipt(ctx.con,ctx.cfg,ctx.study,d['source_file_id'],d['receipt_id'])
        except ValueError as exc: raise Reject([str(exc)])
        if d['decision']=='RETAIN_FLAG':
            if r['severity']=='BLOCKING': raise Reject(['blocking integrity/source errors cannot be waived by agents'])
            ctx.con.execute("UPDATE wf_validation SET status='WAIVED',resolved_at=?,resolution=? WHERE issue_id=?",(now(),d['evidence'],r['issue_id']))
        else: add_review(ctx.con,ctx.study,'QA',f"issue-{r['issue_id']}",r['message'],['RESOLVE'],d['evidence'])
        ctx.con.execute('INSERT OR REPLACE INTO wf_qa_reviews VALUES(?,?,?,?,?)',(r['issue_id'],d['decision'],d['evidence'],ctx.run_id,now()))
    return len(ctx.d['decisions'])

def seed_qa(con,cfg):
    n=0
    with tx(con):
        for r in rows(con,"SELECT * FROM wf_validation WHERE status='OPEN' AND study_id IS NOT NULL AND (severity='BLOCKING' OR rule_id IN ('C001','G003','G004'))"):
            create_task(con,cfg,r['study_id'],'QA_REVIEW',f"issue-{r['issue_id']}");n+=1
    return {'qa_tasks':n}

def renormalize_units(con,cfg,apply=False):
    """Fill derived normalized fields the corrected unit parser now recognizes; printed values never change."""
    from .units import normalize
    changes=[];skipped=[]
    for table,key,spread,spread_norm in (('wf_values','value_id','dispersion_value','disp_norm'),('an_target_values','tv_id','sd','sd_norm')):
        for r in rows(con,f"SELECT * FROM {table} WHERE unit_norm IS NULL AND unit_raw IS NOT NULL AND mean IS NOT NULL"):
            unit,fac,den=normalize(r['unit_raw'],r['endpoint'],r.get('denominator'))
            if unit is None:continue
            if r['endpoint']=='FRUIT_YIELD' and den and r.get('denominator') not in (den,'UNSPECIFIED',None,'OTHER'):
                skipped.append({'table':table,'id':r[key],'study_id':r['study_id'],'unit_raw':r['unit_raw'],'denominator':r.get('denominator')});continue
            changes.append((table,key,r[key],spread_norm,r['unit_raw'],unit,r['mean']*fac,r[spread]*fac if r[spread] is not None else None,den if r['endpoint']=='FRUIT_YIELD' and r.get('denominator') in ('UNSPECIFIED',None,'OTHER') else None))
    counts={}
    for c in changes:
        label=f"{c[0]}: {c[4]} -> {c[5]}";counts[label]=counts.get(label,0)+1
    if apply:
        with tx(con):
            for table,key,rid,spread_norm,raw,unit,mean_norm,sd_norm,implied_den in changes:
                con.execute(f"UPDATE {table} SET unit_norm=?,mean_norm=?,{spread_norm}=? WHERE {key}=?",(unit,mean_norm,sd_norm,rid))
                # The printed unit states the denominator; the record key keeps its original text.
                if implied_den:con.execute(f"UPDATE {table} SET denominator=? WHERE {key}=?",(implied_den,rid))
                changelog(con,'HUMAN-UNIT-RENORMALIZE',table,rid,'RENORMALIZE_UNIT',{'unit_raw':raw,'unit_norm':unit})
    return {'applied':bool(apply),'changes':len(changes),'by_unit':counts,'skipped_denominator_conflict':skipped}

def import_relations(con,cfg):
    cr=ColumnResolver(con,cfg.column_map)
    a,b,k=(cr.get('study_relations',f) for f in ('study_a','study_b','relation'))
    if not all((a,b,k)): return {'imported':0}
    mapping={'PREPRINT_SAME_TOMATO_EXPERIMENT':'COMPANION_SHARED_EXPERIMENT','PREPRINT_VERSION_OF_PUBLISHED_STUDY':'PREPRINT_OF'}
    from .sourceqa import frozen_ids
    scope=frozen_ids(cfg);n=0
    with tx(con):
        for r in rows(con,'SELECT * FROM study_relations'):
            sa,sb=str(r[a]),str(r[b]); rel=mapping.get(r[k],r[k])
            if sa not in scope and sb not in scope: continue
            status='PROPOSED' if sa in scope and sb in scope else 'REFERENCE_ONLY'
            if rel not in ('PREPRINT_OF','COMPANION_SHARED_EXPERIMENT','DUPLICATE_DATA','SHARED_CONTROLS','SAME_LAB_INDEPENDENT','UNRELATED'): continue
            cur=con.execute("INSERT OR IGNORE INTO wf_relations(study_a,study_b,relation,evidence,confidence,status,run_id,created_at) VALUES(?,?,?,?,?,?,'IMPORT',?)",(sa,sb,rel,json.dumps(r,ensure_ascii=False),'BASELINE_UNVERIFIED',status,now()));n+=cur.rowcount
            if status=='PROPOSED':create_task(con,cfg,sa,'DEDUP','cluster::'+json.dumps(sorted([sa,sb])),priority=1)
    return {'imported':n,'note':'baseline links require source verification; they are not silently ignored or automatically assumed correct'}
