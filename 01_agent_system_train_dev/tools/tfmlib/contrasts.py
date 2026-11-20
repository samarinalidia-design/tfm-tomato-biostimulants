"""Deterministic contrasts from source-verified arm summaries. No epsilon, no invented SD."""
from __future__ import annotations
import hashlib,json,math,re
from collections import defaultdict
from .db import rows,now,tx,changelog
from .reconcile import KEY_ATTRS
from .stats import lnrr,lnrr_bias_corrected
LINKING=('DUPLICATE_DATA','PREPRINT_OF','COMPANION_SHARED_EXPERIMENT','SHARED_CONTROLS')
VER_RANK={'DOUBLE_AGREE':1,'ADJUDICATED':2,'HUMAN_VERIFIED':0}
BLOCK_RE=re.compile(r"\b(rcbd|crbd|block(s|ed)?\b|block design)",re.I)
REAL_CLUSTER_RE=re.compile(r"split[- ]?plot|strip[- ]?plot|repeated|nested|paired|same plant|block\w*\s+(was\s+|is\s+)?not|not\s+block",re.I)

MAIN_EFFECT_BG='MAIN_EFFECT_POOLED'
POOLED_BIO_RE=re.compile(r'^(POOLED|MARGINAL)',re.I)

def _independent(design):
    """Author decision 2026-11-05: randomized blocks count as independent unless a real shared cluster exists."""
    allocation=design.get('allocation')
    if allocation=='INDEPENDENT_PARALLEL':return True,False
    text=design.get('description') or ''
    if allocation in ('CLUSTERED','UNKNOWN') and BLOCK_RE.search(text) and not REAL_CLUSTER_RE.search(text):return True,True
    return False,False

def dependency_clusters(con):
    parent={}
    def find(x):
        parent.setdefault(x,x)
        while parent[x]!=x: parent[x]=parent[parent[x]];x=parent[x]
        return x
    for r in rows(con,"SELECT * FROM wf_relations WHERE status='CONFIRMED'"):
        if r['relation'] not in LINKING:continue
        a,b=find(r['study_a']),find(r['study_b'])
        if a!=b:parent[max(a,b)]=min(a,b)
    return {x:'DC-'+find(x) for x in list(parent)}

def excluded_duplicates(con,cfg):
    # Only an explicit full-data PREPRINT_OF/DUPLICATE_DATA relation can exclude a version.
    # Partial/companion/shared-control links only create dependency clusters.
    out={}
    for r in rows(con,"SELECT * FROM wf_relations WHERE status='CONFIRMED' AND relation IN ('PREPRINT_OF','DUPLICATE_DATA')"):
        out[r['study_a']]=r['relation']+' of '+r['study_b']
    return out

def _sig(t):
    return ';'.join([t['endpoint']]+[f'{a}={t.get(a) or ""}' for a in KEY_ATTRS.get(t['endpoint'],())]+[f'context={t.get("context_key") or ""}',f'tp={t["timepoint_key"]}',f'unit={t.get("unit_norm") or t.get("unit_raw") or ""}'])
def _cid(*p):return hashlib.sha256('|'.join(str(x) for x in p).encode()).hexdigest()[:24]

def build(con,cfg,study_id=None):
    clusters=dependency_clusters(con);dups=excluded_duplicates(con,cfg)
    tvs=rows(con,'SELECT * FROM an_target_values'+(' WHERE study_id=?' if study_id else ''),(study_id,) if study_id else ())
    arms={(x['study_id'],x['arm_key']):x for x in rows(con,'SELECT * FROM wf_design_arms')}
    exps={(x['study_id'],x['experiment_key']):x for x in rows(con,'SELECT * FROM wf_design_experiments')}
    groups=defaultdict(list);marginal_yield=[];cell_yield_studies=set()
    box_slots=cfg.get('assumptions.box_centre_as_mean_slots') or []
    box_ids={r['value_id'] for s in box_slots for r in rows(con,'SELECT value_id FROM wf_values WHERE slot_id=?',(s,))}
    two_tick_ids={r['value_id'] for s in (cfg.get('figures.two_tick_axis_slots') or []) for r in rows(con,'SELECT value_id FROM wf_values WHERE slot_id=?',(s,))}
    per_plant_assumed={(str(x['study']),x['endpoint'],x['unit_raw']) for x in (cfg.get('assumptions.per_plant_context_assumed') or [])}
    for t in tvs:
        if not t.get('receipt_id'): continue
        t=dict(t)
        t['_pp']=(str(t['study_id']),t['endpoint'],t.get('unit_raw')) in per_plant_assumed
        t['_box']=bool(set(json.loads(t.get('basis_value_ids') or '[]'))&box_ids)
        t['_two_tick']=bool(set(json.loads(t.get('basis_value_ids') or '[]'))&two_tick_ids)
        if t.get('mean_norm') is not None:t['mean'],t['sd']=t['mean_norm'],t.get('sd_norm')
        a=arms.get((t['study_id'],t['arm_key']),{})
        key=(t['study_id'],t['experiment_key'],t.get('genotype') or '',t.get('season') or '',t.get('site') or '',a.get('background_key') or '',_sig(t))
        t['_components']=frozenset(json.loads(a.get('component_codes') or '[]'))
        groups[key].append(t)
        if t['endpoint']=='FRUIT_YIELD':
            if 'MARG' in str(a.get('background_key') or '').upper():marginal_yield.append(t)
            else:cell_yield_studies.add(t['study_id'])
    # Author decision 2026-11-05: a study printing only factor-level yield means keeps its biostimulant
    # main effect in a separate mart. A study with real factorial cells never uses this route.
    for t in marginal_yield:
        if t['study_id'] not in cell_yield_studies:
            groups[(t['study_id'],t['experiment_key'],t.get('genotype') or '',t.get('season') or '','',MAIN_EFFECT_BG,_sig(t))].append(t)
    output=[];coeffs={};armvars={};main_effect_blocked=set()
    for (study,exp,geno,season,site,bg,sig),items in groups.items():
        design=exps.get((study,exp),{});independent,block_assumed=_independent(design)
        roles=defaultdict(list)
        for it in items:roles[it['role']].append(it)
        def unique(which,field,val):
            h=[x for x in roles[which] if x.get(field)==val]
            return h[0] if len(h)==1 else None
        C=roles['C'][0] if len(roles['C'])==1 else None
        def make(ctype,terms,t,c):
            meta=json.loads(t.get('outcome_context_json') or 'null') or {}
            metric=meta.get('effect_metric','lnRR')
            biotic=t['endpoint'].startswith('BIOTIC_')
            if any(x['mean'] is None or x['mean']<=0 for x,w in terms):effect=None
            else:effect=sum(w*math.log(x['mean']) for x,w in terms)
            flags=[]
            if block_assumed:flags.append('BLOCK_ASSUMED_INDEPENDENT')
            if any(x.get('_box') for x,w in terms):flags.append('BOX_CENTRE_ASSUMED_MEAN')
            if any(x.get('_two_tick') for x,w in terms):flags.append('TWO_TICK_AXIS_CALIBRATION')
            if any(x.get('_pp') for x,w in terms):flags.append('PER_PLANT_CONTEXT_ASSUMED')
            if any((x.get('error_bar_relative_uncertainty') or 0)>float(cfg.get('figures.max_error_bar_rel_uncertainty',0.05))+1e-12 for x,w in terms):flags.append('ERROR_BAR_DIGITIZATION_OVER_5PCT')
            contexts=[json.loads(x.get('outcome_context_json') or 'null') or {} for x,w in terms]
            context_ok=all(all(m.get(k)==meta.get(k) for k in ('estimand_id','effect_metric','scale_id','scale_type','assay','pathogen','favorable_direction')) for m in contexts)
            if biotic and not context_ok:flags.append('INCOMPATIBLE_BIOTIC_CONTEXT')
            if metric=='MD':effect=sum(w*x['mean'] for x,w in terms) if context_ok else None
            if metric=='DESCRIPTIVE_ORDINAL':effect=None;flags.append('ORDINAL_DESCRIPTIVE_ONLY')
            if metric in ('LOG_RR_BINARY','LOG_OR'):
                if len(terms)!=2:effect=None;flags.append('BINARY_FACTORIAL_METRIC_NOT_PRESPECIFIED')
                else:
                    tm,cm=contexts[0],contexts[1];et,nt,ec,nc=tm.get('events'),tm.get('total'),cm.get('events'),cm.get('total')
                    if context_ok and all(x is not None and x>0 for x in (et,nt,ec,nc)) and (metric!='LOG_OR' or (et<nt and ec<nc)):
                        effect=math.log((et/nt)/(ec/nc)) if metric=='LOG_RR_BINARY' else math.log((et/(nt-et))/(ec/(nc-ec)))
                    else:effect=None;flags.append('BINARY_ZERO_OR_MISSING_CELL_NO_PSEUDOCOUNT')
            variances=[]
            for x,w in terms:
                av=x['sd']**2/(x['n']*(1 if metric=='MD' else x['mean']**2)) if x.get('sd') is not None and x.get('n') and x['n']>=2 and (metric=='MD' or x['mean']>0) else None
                armvars[x['tv_id']]=av
                if av is None:variances=None;break
                variances.append(w*w*av)
            var=sum(variances) if independent and variances else None
            if metric in ('LOG_RR_BINARY','LOG_OR'):
                var=None
                if effect is not None and independent and len(terms)==2 and all(m.get('binomial_independent') and x.get('n')==m.get('total') for (x,w),m in zip(terms,contexts)):
                    var=(1/et-1/nt+1/ec-1/nc) if metric=='LOG_RR_BINARY' else (1/et+1/(nt-et)+1/ec+1/(nc-ec))
            if not context_ok or metric=='DESCRIPTIVE_ORDINAL':var=None
            if effect is None:var=None
            if not independent:flags.append('DEPENDENT_OR_UNKNOWN_ALLOCATION_VARIANCE_UNAVAILABLE')
            if effect is None: flags.append('NONCOMPUTABLE_FOR_METRIC')
            if study in dups:flags.append('DUPLICATE_EXCLUDED:'+dups[study])
            if t['endpoint']=='FRUIT_YIELD' and ctype!='B_MAIN_EFFECT':main_effect_blocked.add(study)
            cid=_cid(study,exp,ctype,sig,geno,season,site,bg,*[(x['arm_key'],w) for x,w in terms])
            ids=[x['tv_id'] for x,w in terms];coeffs[cid]={x['tv_id']:w for x,w in terms}
            vmin=max(VER_RANK.get(x['verification'],3) for x,w in terms)
            output.append(dict(contrast_id=cid,study_id=study,experiment_key=exp,endpoint=t['endpoint'],contrast_type=ctype,signature=sig,
              arm_key_t=t['arm_key'],arm_key_c=c['arm_key'],tv_ids=json.dumps(ids),stress_code=t['stress_code'],bio_code=t['bio_code'],
              mean_t=t['mean'],sd_t=t.get('sd'),n_t=t.get('n'),mean_c=c['mean'],sd_c=c.get('sd'),n_c=c.get('n'),effect=effect,var_effect=var,
              effect_bc=lnrr_bias_corrected(t['mean'],t.get('sd'),t.get('n'),c['mean'],c.get('sd'),c.get('n')) if metric=='lnRR' and ctype in ('SB_vs_S','S_vs_C','B_vs_C') else None,
              effect_metric=metric,estimand_id=meta.get('estimand_id'),favorable_direction=meta.get('favorable_direction','POSITIVE'),pct_effect=100*math.expm1(effect) if metric in ('lnRR','LOG_RR_BINARY') and effect is not None and abs(effect)<700 else None,var_available=int(var is not None),
              shared_control_id=f'{study}|{exp}|{c["arm_key"]}|{sig}',dependency_cluster_id=clusters.get(study,'DC-'+study),
              min_verification={0:'HUMAN_VERIFIED',1:'DOUBLE_AGREE',2:'ADJUDICATED'}.get(vmin,'UNKNOWN'),any_figure_source=int(any(x['source_kind']=='FIGURE' or (json.loads(x.get('dispersion_provenance_json') or 'null') or {}).get('source_kind')=='FIGURE' for x,w in terms)),flags=json.dumps(flags),created_at=now()))
        if bg==MAIN_EFFECT_BG:
            # These groups are appended last, so every cell-based contrast of the study already exists.
            if study in main_effect_blocked:continue
            for stress in {x['stress_code'] for x in items}:
                same=[x for x in items if x['stress_code']==stress]
                ctrl=[x for x in same if (x.get('bio_code') or 'NONE')=='NONE']
                if len(ctrl)!=1:continue
                for treated in same:
                    bio=treated.get('bio_code') or 'NONE'
                    if bio=='NONE' or POOLED_BIO_RE.match(bio):continue
                    make('B_MAIN_EFFECT',[(treated,1),(ctrl[0],-1)],treated,ctrl[0])
                    # n and covariance of pooled means are undefined here: point effect only.
                    made=output[-1];made['var_effect']=None;made['var_available']=0
                    made['flags']=json.dumps(json.loads(made['flags'])+['MAIN_EFFECT_ONLY_POOLED_OVER_OTHER_FACTORS'])
            continue
        for sb in roles['SB']:
            s=unique('S','stress_code',sb['stress_code']);b=unique('B','bio_code',sb['bio_code'])
            if s:make('SB_vs_S',[(sb,1),(s,-1)],sb,s)
            if s and b and C and design.get('factorial_verified'):
                make('SxB',[(sb,1),(s,-1),(C,1),(b,-1)],sb,s)
        if C:
            for s in roles['S']:make('S_vs_C',[(s,1),(C,-1)],s,C)
            for b in roles['B']:make('B_vs_C',[(b,1),(C,-1)],b,C)
        if design.get('factorial_verified'):
            # Exact Control-A-B-AB cells, same stress/background, doses encoded in component identity.
            for ab in items:
                if len(ab['_components'])!=2:continue
                aa,bb=sorted(ab['_components'])
                compatible=[x for x in items if x['stress_code']==ab['stress_code']]
                def one(cs):
                    h=[x for x in compatible if x['_components']==frozenset(cs)]
                    return h[0] if len(h)==1 else None
                ctl,a,b=one([]),one([aa]),one([bb])
                if ctl and a and b:make('AxB',[(ab,1),(ctl,1),(a,-1),(b,-1)],ab,ctl)
    with tx(con):
        if study_id:
            old=[r['contrast_id'] for r in rows(con,'SELECT contrast_id FROM an_contrasts WHERE study_id=?',(study_id,))]
            for cid in old:con.execute('DELETE FROM an_covariance WHERE contrast_a=? OR contrast_b=?',(cid,cid))
            con.execute('DELETE FROM an_contrasts WHERE study_id=?',(study_id,))
        else:con.execute('DELETE FROM an_covariance');con.execute('DELETE FROM an_contrasts')
        for c in output:
            con.execute(f'INSERT INTO an_contrasts({",".join(c)}) VALUES({",".join("?" for x in c)})',list(c.values()))
        for i,a in enumerate(output):
            for b in output[i+1:]:
                if a['dependency_cluster_id']!=b['dependency_cluster_id']:continue
                shared=set(coeffs[a['contrast_id']])&set(coeffs[b['contrast_id']])
                cov=None;method='DEPENDENCY_CLUSTER_COVARIANCE_UNKNOWN'
                if shared and a['effect_metric']==b['effect_metric'] and a['effect_metric'] in ('lnRR','MD') and a['var_available'] and b['var_available'] and all(armvars.get(k) is not None for k in shared):
                    cov=sum(coeffs[a['contrast_id']][k]*coeffs[b['contrast_id']][k]*armvars[k] for k in shared);method='SHARED_INDEPENDENT_ARM_DELTA_METHOD'
                con.execute('INSERT OR REPLACE INTO an_covariance VALUES(?,?,?,?,?)',(a['contrast_id'],b['contrast_id'],cov,method,json.dumps(sorted(shared))))
        changelog(con,None,'an_contrasts',study_id or 'ALL','BUILD',{'n':len(output)})
    summary=defaultdict(int)
    for c in output:summary[c['endpoint']+':'+c['contrast_type']]+=1
    return dict(summary)
