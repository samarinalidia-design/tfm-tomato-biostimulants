"""Eight data-stage figure groups; exact underlying tables, no fitted ML."""
from pathlib import Path
import pandas as pd
from .db import rows

def write(con,frames,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    out=Path(out)/'figures';out.mkdir()
    ev=frames['evidence_long'];tv=frames['arm_values_verified']
    groups=[]
    def counts(sql,key,label):
        x=rows(con,sql);return pd.DataFrame([{'category':r[key],'count':r['n']} for r in x],columns=['category','count'])
    groups.append(('01_database_assembly','A399 database assembly',pd.DataFrame([{'category':'Frozen studies','count':con.execute('SELECT COUNT(*) FROM wf_study_status').fetchone()[0]},{'category':'Original source files','count':con.execute('SELECT COUNT(*) FROM wf_sources').fetchone()[0]},{'category':'Verified arm values','count':len(tv)},{'category':'Retained contrasts','count':len(ev)}])))
    groups.append(('02_evidence_landscape','Retained contrasts by endpoint',ev.groupby('endpoint',dropna=False).size().rename('count').reset_index().rename(columns={'endpoint':'category'}) if len(ev) else pd.DataFrame(columns=['category','count'])))
    stress='f_stress_type';bio='f_biostimulant_class'
    if len(ev):
        z=pd.DataFrame({'stress':ev[stress] if stress in ev else ['UNKNOWN']*len(ev),'biostimulant':ev[bio] if bio in ev else ['UNKNOWN']*len(ev)}).fillna('UNKNOWN');heat=z.groupby(['stress','biostimulant']).size().rename('count').reset_index()
        htable=pd.DataFrame({'category':heat['stress'].astype(str)+' × '+heat['biostimulant'].astype(str),'count':heat['count']})
    else:heat=pd.DataFrame(columns=['stress','biostimulant','count']);htable=pd.DataFrame(columns=['category','count'])
    groups.append(('03_stress_biostimulant','Stress and biostimulant coverage',htable))
    cols=[c for c in ev if c.startswith('f_')]+[c for c in ('mean_t','sd_t','n_t','mean_c','sd_c','n_c') if c in ev]
    groups.append(('04_completeness','Missing entries by relevant field',pd.DataFrame([{'category':c,'count':int(ev[c].isna().sum())} for c in cols],columns=['category','count'])))
    cc=frames['contrast_candidates'];attr=cc['exclusion_reason'].replace('','RETAINED').value_counts() if len(cc) else pd.Series(dtype='int64')
    groups.append(('05_attrition','Candidate contrast disposition',pd.DataFrame({'category':attr.index,'count':attr.values})))
    qa=[]
    if len(tv):
        qa.extend({'category':'source '+str(k),'count':int(v)} for k,v in tv['source_kind'].value_counts().items())
        qa.extend([{'category':'values with n','count':int(tv['n'].notna().sum())},{'category':'values with SD','count':int(tv['sd'].notna().sum())}])
    qa.extend({'category':'RoB '+r['judgement'],'count':r['n']} for r in rows(con,'SELECT judgement,COUNT(*) n FROM wf_rob GROUP BY judgement'))
    groups.append(('06_provenance_uncertainty_RoB','Source uncertainty and risk of bias coverage',pd.DataFrame(qa,columns=['category','count'])))
    by=ev.groupby(['endpoint','contrast_type']).size() if len(ev) else pd.Series(dtype='int64')
    groups.append(('07_outcomes_contrasts','Endpoint and contrast types',pd.DataFrame([{'category':' / '.join(k),'count':int(v)} for k,v in by.items()],columns=['category','count'])))
    supplement=[{'category':r['role'],'count':r['n']} for r in rows(con,'SELECT s.role,COUNT(DISTINCT v.tv_id) n FROM an_target_values v JOIN wf_sources s ON v.source_file_id=s.source_file_id GROUP BY s.role')]
    groups.append(('08_supplement_contribution','Verified arm values by original source role',pd.DataFrame(supplement,columns=['category','count'])))
    heat.to_csv(out/'03_heatmap_cells.csv',index=False)
    for name,title,df in groups:
        df.to_csv(out/(name+'.csv'),index=False)
        fig,ax=plt.subplots(figsize=(9,max(3.2,min(12,len(df)*.28+1.4))))
        if name.startswith('03') and len(heat):
            pivot=heat.pivot(index='stress',columns='biostimulant',values='count').fillna(0)
            im=ax.imshow(pivot.values,aspect='auto',cmap='Blues');ax.set_xticks(range(len(pivot.columns)),pivot.columns,rotation=35,ha='right');ax.set_yticks(range(len(pivot.index)),pivot.index);fig.colorbar(im,ax=ax,label='Retained contrasts')
        elif len(df):
            display=df.iloc[:40];ax.barh(display['category'].astype(str),display['count'],color='#365c74');ax.invert_yaxis();ax.set_xlabel('Count')
            if len(df)>40:ax.text(.98,.01,'First 40 fields; full table in CSV',transform=ax.transAxes,ha='right',fontsize=8)
        else:ax.text(.5,.5,'No eligible records',ha='center',va='center',transform=ax.transAxes);ax.set_xticks([]);ax.set_yticks([])
        ax.set_title(title+'\nFrozen category A scope only',fontsize=12);fig.tight_layout()
        for ext in ('png','svg','pdf'):fig.savefig(out/(name+'.'+ext),dpi=180)
        plt.close(fig)
