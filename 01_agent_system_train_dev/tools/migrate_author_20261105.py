"""One-off migration for author decisions of 2026-11-05. Dry run unless --apply."""
import json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
for stream in (sys.stdout,sys.stderr):
    if hasattr(stream,"reconfigure"):stream.reconfigure(encoding="utf-8",errors="replace")
from tfmlib.config import Config
from tfmlib.db import connect,now,rows,tx,changelog
from tfmlib.reconcile import agree_override,promote,refresh_slots
from tfmlib.tasks import create_task,set_state

RUN="AUTHOR-20261105"
EXCLUDED_STUDY="D_585e152fad56086b"
DRY=re.compile(r"\bdry\b|\bdw\b|\bdm\b|dry[- ]?(weight|wt|mass|matter)",re.I)
apply_="--apply" in sys.argv
cfg=Config();con=connect(cfg.db_path)
con.execute("CREATE TABLE IF NOT EXISTS wf_dry_basis(study_id TEXT,tv_record_key TEXT,basis TEXT,method TEXT,source_file_id TEXT,receipt_id TEXT,evidence TEXT,run_id TEXT,created_at TEXT,PRIMARY KEY(study_id,tv_record_key))")

if "--split-marketable-fruit-number" in sys.argv:
    # Total and marketable panels of Fig. 6 shared one record key, so one overwrote the other.
    study,slots="D_b205610597d43dda",("D_b205610597d43dda#07","D_b205610597d43dda#08")
    from tfmlib.reconcile import reconcile
    with tx(con):
        marketable=rows(con,"SELECT value_id,record_key FROM wf_values WHERE slot_id=?",(slots[1],))
        keys=sorted({r["record_key"] for r in marketable})
        for r in marketable:
            con.execute("UPDATE wf_values SET record_key=?,context_key='MARKETABLE' WHERE value_id=?",(r["record_key"]+"MARKETABLE",r["value_id"]))
        for k in keys:
            con.execute("DELETE FROM wf_reconciliation WHERE study_id=? AND record_key=? AND family='FIGURE'",(study,k))
            con.execute("DELETE FROM an_target_values WHERE study_id=? AND record_key=?",(study,k))
        stats=[reconcile(con,cfg,study,"FIGURE",s,RUN) for s in slots]
        refresh_slots(con,study)
        changelog(con,RUN,"migration","split-marketable-fruit-number","APPLIED" if apply_ else "DRY_RUN",{"keys":len(keys),"stats":stats})
        print("split",len(keys),"keys",stats)
        print("values",rows(con,"SELECT context_key,COUNT(*) n FROM an_target_values WHERE study_id=? AND endpoint='FRUIT_NUMBER' GROUP BY 1",(study,)))
        if not apply_:raise SystemExit("Dry run complete: rolled back. Repeat with --apply.")
    raise SystemExit(0)

if "--close-superseded" in sys.argv:
    # Conflicts whose readings belong to replaced runs: a newer FA/FB pass of the slot supersedes them.
    live="EXISTS(SELECT 1 FROM wf_slot_pass sp WHERE sp.slot_id=v.slot_id AND sp.pass=v.pass AND sp.run_id=v.run_id)"
    with tx(con):
        stale=[r for r in rows(con,"SELECT r.* FROM wf_reconciliation r WHERE r.status IN ('OPEN','ESCALATED') AND r.family='FIGURE' AND NOT EXISTS(SELECT 1 FROM wf_values v WHERE v.value_id IN (r.value_id_a,r.value_id_b) AND "+live+")")]
        for r in stale:
            print("close",r["rec_id"],r["study_id"],r["record_key"],r["fields_conflict"],"values",con.execute("SELECT COUNT(*) FROM an_target_values WHERE study_id=? AND record_key=?",(r["study_id"],r["record_key"])).fetchone()[0])
            con.execute("DELETE FROM an_target_values WHERE study_id=? AND record_key=?",(r["study_id"],r["record_key"]))
            con.execute("UPDATE wf_reconciliation SET status='RESOLVED',resolved_value_id=NULL,resolved_by='SUPERSEDED',updated_at=? WHERE rec_id=?",(now(),r["rec_id"]))
        for r in rows(con,"SELECT DISTINCT study_id FROM wf_tasks t WHERE task_type='ADJUDICATE' AND status='READY' AND study_id NOT IN (SELECT study_id FROM wf_reconciliation WHERE status IN ('OPEN','ESCALATED'))"):
            print("cancel adjudication for",r["study_id"])
            con.execute("UPDATE wf_tasks SET status='CANCELLED',updated_at=? WHERE study_id=? AND task_type='ADJUDICATE' AND status='READY'",(now(),r["study_id"]))
        changelog(con,RUN,"migration","close-superseded","APPLIED" if apply_ else "DRY_RUN",{"closed":len(stale)})
        if not apply_:raise SystemExit("Dry run complete: rolled back. Repeat with --apply.")
    raise SystemExit(0)

if "--advance-stale" in sys.argv:
    # The study state moves only when a task of that study is submitted, so finished studies stayed parked.
    from tfmlib.submit import Ctx,maybe_verify
    with tx(con):
        before={r["state"]:r["n"] for r in rows(con,"SELECT state,COUNT(*) n FROM wf_study_status GROUP BY 1")}
        tasks_before=con.execute("SELECT COUNT(*) FROM wf_tasks").fetchone()[0]
        for r in rows(con,"SELECT study_id FROM wf_study_status WHERE state IN ('ADJUDICATION','EXTRACTING')"):
            ctx=Ctx(con,cfg,{"task_id":"advance-stale","study_id":r["study_id"],"task_type":"REVIEW","scope_ref":""},{},RUN)
            maybe_verify(ctx)
        print("states before",before)
        print("states after",{r["state"]:r["n"] for r in rows(con,"SELECT state,COUNT(*) n FROM wf_study_status GROUP BY 1")})
        print("new tasks",con.execute("SELECT COUNT(*) FROM wf_tasks").fetchone()[0]-tasks_before)
        print("ready",{r["task_type"]:r["n"] for r in rows(con,"SELECT task_type,COUNT(*) n FROM wf_tasks WHERE status='READY' GROUP BY 1")})
        changelog(con,RUN,"migration","advance-stale","APPLIED" if apply_ else "DRY_RUN",{})
        if not apply_:raise SystemExit("Dry run complete: rolled back. Repeat with --apply.")
    raise SystemExit(0)

if "--seed-dry-basis" in sys.argv:
    # Dry values promoted by the 2026-11-11 re-reads and table recovery have no basis check yet.
    with tx(con):
        need=set();seeded=0
        for tv in rows(con,"SELECT t.* FROM an_target_values t WHERE t.endpoint='DRY_BIOMASS' AND NOT EXISTS (SELECT 1 FROM wf_dry_basis b WHERE b.study_id=t.study_id AND b.tv_record_key=t.record_key)"):
            text=" ".join(str(tv.get(k) or "") for k in ("verbatim","source_cell","locator","unit_raw","outcome_context_json"))
            if DRY.search(text):
                con.execute("INSERT OR IGNORE INTO wf_dry_basis VALUES(?,?,?,?,?,?,?,?,?)",(tv["study_id"],tv["record_key"],"DRY_CONFIRMED","LABEL_KEYWORD",tv["source_file_id"],tv["receipt_id"],text[:300],"AUTHOR-20261112",now()))
                seeded+=1
            else:need.add(tv["study_id"])
        for study in sorted(need):
            if not con.execute("SELECT 1 FROM wf_tasks WHERE study_id=? AND task_type='DRY_BASIS' AND status IN ('READY','LEASED')",(study,)).fetchone():
                print("dry basis task",study,create_task(con,cfg,study,"DRY_BASIS","rest-20261112"))
        print("dry basis seeded by label",seeded)
        changelog(con,"AUTHOR-20261112","migration","seed-dry-basis","APPLIED" if apply_ else "DRY_RUN",{"seeded":seeded,"studies":sorted(need)})
        if not apply_:raise SystemExit("Dry run complete: rolled back. Repeat with --apply.")
    raise SystemExit(0)

if "--seed-remaining" in sys.argv:
    # Dry values promoted after the first seeding have no basis check; this pair was never compared as candidates.
    with tx(con):
        need=set();seeded=0
        for tv in rows(con,"SELECT t.* FROM an_target_values t WHERE t.endpoint='DRY_BIOMASS' AND NOT EXISTS (SELECT 1 FROM wf_dry_basis b WHERE b.study_id=t.study_id AND b.tv_record_key=t.record_key)"):
            text=" ".join(str(tv.get(k) or "") for k in ("verbatim","source_cell","locator","unit_raw","outcome_context_json"))
            if DRY.search(text):
                con.execute("INSERT OR IGNORE INTO wf_dry_basis VALUES(?,?,?,?,?,?,?,?,?)",(tv["study_id"],tv["record_key"],"DRY_CONFIRMED","LABEL_KEYWORD",tv["source_file_id"],tv["receipt_id"],text[:300],RUN,now()))
                seeded+=1
            else:need.add(tv["study_id"])
        for study in sorted(need):print("dry basis task",study,create_task(con,cfg,study,"DRY_BASIS","rest-20261106"))
        print("dry basis seeded",seeded)
        pair=sorted(["D_adda3ddd52623208","D_0dea1827dd555ada"])
        print("dedup task",create_task(con,cfg,pair[0],"DEDUP","cluster::"+json.dumps(pair),priority=1))
        changelog(con,RUN,"migration","seed-remaining","APPLIED" if apply_ else "DRY_RUN",{"seeded":seeded,"studies":sorted(need)})
        if not apply_:raise SystemExit("Dry run complete: rolled back. Repeat with --apply.")
    raise SystemExit(0)

def reopen(sid,study):
    con.execute("DELETE FROM wf_slot_pass WHERE slot_id=?",(sid,))
    con.execute("UPDATE wf_target_slots SET status='OPEN',not_extractable_reason=NULL,updated_at=? WHERE slot_id=?",(now(),sid))
    for tt in ("FIGURE_A","FIGURE_B"):
        hit=con.execute("UPDATE wf_tasks SET status='READY',attempts=0,lease_owner=NULL,lease_expires=NULL,last_error=NULL,updated_at=? WHERE study_id=? AND task_type=? AND scope_ref=?",(now(),study,tt,sid)).rowcount
        if not hit:create_task(con,cfg,study,tt,sid)
    set_state(con,study,"EXTRACTING",RUN)

if "--supplements-unavailable" in sys.argv:
    # Author decision 2026-11-06: these assets exist only in supplements absent from the corpus; none holds fruit yield.
    with tx(con):
        sel="FROM wf_asset_inventory a WHERE a.disposition='SLOT' AND a.study_id IN ('408','445','D_9c95d843082965e8','D_fec4bf7d8af2cec4') AND NOT EXISTS (SELECT 1 FROM wf_target_slots s WHERE s.study_id=a.study_id AND s.source_file_id=a.source_file_id AND TRIM(LOWER(s.locator_label))=TRIM(LOWER(a.locator)))"
        hit=rows(con,"SELECT a.study_id,a.locator "+sel)
        for r in hit:print(r["study_id"],"|",r["locator"][:80])
        con.execute("UPDATE wf_asset_inventory SET disposition='SOURCE_UNAVAILABLE' WHERE rowid IN (SELECT a.rowid "+sel+")")
        changelog(con,"AUTHOR-20261106","migration","supplements-unavailable","APPLIED" if apply_ else "DRY_RUN",{"assets":len(hit)})
        print("assets",len(hit))
        if not apply_:raise SystemExit("Dry run complete: rolled back. Repeat with --apply.")
    raise SystemExit(0)

if "--d952-sd" in sys.argv:
    # Adjudications T-006507 and T-006511: Methods 4.8 is the paper's only statement on bars and names SD,
    # so Fig. 6d and 5b take the same type as Fig. 6b/6c. Only the type label changes; the digitized width stays.
    with tx(con):
        n=0
        # Adjudication T-006530 found the same Methods 4.8 statement covers the Fig. 4b root dry weight.
        ep="DRY_BIOMASS" if "--dry" in sys.argv else "FRUIT_YIELD"
        for t in rows(con,"SELECT * FROM an_target_values WHERE study_id='D_952eb99fc48d3753' AND endpoint=? AND dispersion_basis='USER_ASSUMED_SE'",(ep,)):
            sd=t["dispersion_value"];fac=(t["mean_norm"]/t["mean"]) if t.get("mean_norm") is not None and t["mean"] else None
            con.execute("UPDATE an_target_values SET dispersion_type='SD',dispersion_basis='SOURCE_REPORTED',sd=?,sd_norm=?,updated_at=? WHERE tv_id=?",(sd,sd*fac if fac is not None else None,now(),t["tv_id"]))
            print("SD",t["tv_id"],t["arm_key"],round(sd,4));n+=1
        changelog(con,"AUTHOR-20261106","migration","d952-sd","APPLIED" if apply_ else "DRY_RUN",{"rows":n,"basis":"T-006507,T-006511 Methods 4.8 receipt SRC-26d7f53812d5f2bf99b96e42"})
        if not apply_:raise SystemExit("Dry run complete: rolled back. Repeat with --apply.")
    raise SystemExit(0)

if "--a4c2-table-means" in sys.argv:
    # Adjudication T-006533 and both readings of slot #02: exact dry-weight means are printed in the data
    # tables embedded under Fig. 1A and 1B (p4) and were never captured. Author rule: a table outranks a figure.
    study="D_a4c2f7c987f40633";fid="1Vc0ckaID1v8Zh79QIQ-Nzz-2rNWNsb_X"
    new=[("Figure 1A embedded data table, row 'Dry weight (gr)' (shoot)","Shoot dry weight printed in the data table under the Fig. 1A chart, 35 days after sowing, 3 arms: Control, Ba QST713, Bs MBI600. Printed mean outranks the graphical reading of slot #01; SE comes only from the #01 bars. Bare 'gr', basis per plant or per replicate not stated. n: Methods 4.4 p12 five replicates of 10 plants; per-bar n not stated."),
         ("Figure 1B embedded data table, row 'Dry weight (gr)' (root)","Root-only dry weight printed in the data table under the Fig. 1B chart, 35 days after sowing, 3 arms: Control, Ba QST713, Bs MBI600. Both figure readings of slot #02 found no readable SE cap, so variance is unavailable unless the original prints it. Keep root separate from shoot. Bare 'gr', basis not stated.")]
    with tx(con):
        k0=con.execute("SELECT COUNT(*) FROM wf_target_slots WHERE study_id=?",(study,)).fetchone()[0]
        for i,(loc,desc) in enumerate(new,start=1):
            if con.execute("SELECT 1 FROM wf_target_slots WHERE study_id=? AND locator_label=?",(study,loc)).fetchone():continue
            sid=f"{study}#{k0+i:02d}"
            con.execute("INSERT INTO wf_target_slots(slot_id,study_id,endpoint,source_kind,source_file_id,locator_label,page,figure_item_id,expected_n_values,has_dispersion,description,route,status,created_run_id,updated_at) VALUES (?,?,'DRY_BIOMASS','TABLE',?,?,4,NULL,3,'NO',?,'EXTRACT','OPEN',?,?)",(sid,study,fid,loc,desc,"AUTHOR-20261106",now()))
            print("slot",sid,loc)
        for tt in ("EXTRACT_A","EXTRACT_B"):
            if not con.execute("SELECT 1 FROM wf_tasks WHERE study_id=? AND task_type=? AND status IN ('READY','LEASED')",(study,tt)).fetchone():
                print("task",create_task(con,cfg,study,tt,"table-recovery"))
        set_state(con,study,"EXTRACTING","AUTHOR-20261106")
        changelog(con,"AUTHOR-20261106","migration","a4c2-table-means","APPLIED" if apply_ else "DRY_RUN",{"study":study,"basis":"T-006533; slot #02 FA/FB reasons; receipt SRC-5965334dc5a91b77579c7c6c"})
        if not apply_:raise SystemExit("Dry run complete: rolled back. Repeat with --apply.")
    raise SystemExit(0)

if "--dec036-t23" in sys.argv:
    # Adjudication T-006537: on the re-read the T23 leaf mean fails the 5% mean bound (5.1% on the embedded
    # raster), so the slot is VERIFIED_PARTIAL 24 of 25; the older row from the replaced readings goes.
    with tx(con):
        n=con.execute("DELETE FROM an_target_values WHERE study_id='D_dec036bff64f4a0e' AND record_key='E1.S50B100|DRY_BIOMASS|||||LEAF|FIG18_UNSPEC|'").rowcount
        print("dropped",n)
        changelog(con,"AUTHOR-20261106","migration","dec036-t23","APPLIED" if apply_ else "DRY_RUN",{"rows":n,"basis":"T-006537"})
        if not apply_:raise SystemExit("Dry run complete: rolled back. Repeat with --apply.")
    raise SystemExit(0)

UNIT_ASSUMED=[  # author decision 2026-11-12, PER_PLANT_CONTEXT_ASSUMED; unit-resolution reads of 2026-11-11
    ("D_e166ff7eadc506bb","FRUIT_YIELD","g","g/plant",1.0),
    ("D_65e9c78cc3179036","FRUIT_YIELD","g","g/plant",1.0),
    ("D_4b4f2119a7ee5348","FRUIT_YIELD","g","g/plant",1.0),
    ("D_71f54641804128b2","FRUIT_YIELD","Kg","kg/plant",1.0),
    ("373","FRUIT_YIELD","g","g/plant",1.0),
    ("D_59e850b9d6e676cf","DRY_BIOMASS","g dw Sh-1","g/plant",1.0),
    ("D_59e850b9d6e676cf","DRY_BIOMASS","g dw Rt-1","g/plant",1.0),
    ("D_0bb850652a630ca5","DRY_BIOMASS","cms","g/plant",1.0)]
UNIT_SOURCE=[  # unit stated in the original; read on 2026-11-11 and confirmed by an independent reviewer
    ("72","FRUIT_YIELD","Kg","kg/plot",1.0),
    ("D_02789d91069fe949","DRY_BIOMASS","g. (dm)/ plant","g/plant",1.0),
    ("D_d6200055f581ac4e","DRY_BIOMASS","g s-1","g/plant",1.0),
    ("D_46900f502be913e0","DRY_BIOMASS","g-1","g/plant",1.0),
    ("18","DRY_BIOMASS","mg/seedling","mg/plant",1.0),
    ("23","DRY_BIOMASS","Biomass (g-1plant) [axis label as printed; g per plant]","g/plant",1.0),
    ("110","DRY_BIOMASS","mg kg-1 DW","g",1.0),
    ("D_1955eb8ae71bee69","DRY_BIOMASS","x 100 mg dry wt","mg",100.0)]

if "--unit-resolve" in sys.argv:
    from tfmlib.units import normalize
    groups=UNIT_ASSUMED if "--assumed" in sys.argv else [x for x in UNIT_SOURCE if x[0] in sys.argv[sys.argv.index("--unit-resolve")+1].split(",")]
    with tx(con):
        for study,ep,raw,resolved,scale in groups:
            unit,fac,den=normalize(resolved,ep,None)
            if unit is None:raise SystemExit(f"parser does not know {resolved}")
            fac*=scale;n=0
            for table,key,spread,spread_norm in (('wf_values','value_id','dispersion_value','disp_norm'),('an_target_values','tv_id','sd','sd_norm')):
                for r in rows(con,f"SELECT * FROM {table} WHERE study_id=? AND endpoint=? AND unit_raw=? AND unit_norm IS NULL AND mean IS NOT NULL",(study,ep,raw)):
                    con.execute(f"UPDATE {table} SET unit_norm=?,mean_norm=?,{spread_norm}=? WHERE {key}=?",(unit,r['mean']*fac,r[spread]*fac if r[spread] is not None else None,r[key]))
                    if den and r.get('denominator') in (None,'UNSPECIFIED','OTHER'):con.execute(f"UPDATE {table} SET denominator=? WHERE {key}=?",(den,r[key]))
                    n+=1
            print(study,ep,repr(raw),"->",unit,"x",fac,den,"rows",n)
            changelog(con,"AUTHOR-20261112","migration","unit-resolve","APPLIED" if apply_ else "DRY_RUN",{"study":study,"endpoint":ep,"unit_raw":raw,"resolved":resolved,"scale":scale,"basis":"assumed per plant (author 2026-11-12)" if "--assumed" in sys.argv else "stated in original; independent review"})
        if not apply_:raise SystemExit("Dry run complete: rolled back. Repeat with --apply.")
    raise SystemExit(0)

if "--drop-replaced-readings" in sys.argv:
    # A re-read can change a record key, which leaves the old row beside the new one and doubles the arm.
    # Drop an old row only when a newer row holds the same arm and timepoint of that slot; otherwise keep its mean.
    with tx(con):
        dropped=kept=0
        for s in rows(con,"SELECT slot_id,MAX(created_at) read_at FROM wf_slot_pass WHERE pass IN ('FA','FB') AND created_at >= '2026-11-06' GROUP BY slot_id HAVING COUNT(*)=2"):
            read_from=rows(con,"SELECT MIN(created_at) t FROM wf_slot_pass WHERE slot_id=? AND pass IN ('FA','FB')",(s["slot_id"],))[0]["t"]
            found=rows(con,"SELECT DISTINCT t.* FROM an_target_values t JOIN json_each(t.basis_value_ids) j JOIN wf_values v ON v.value_id=j.value WHERE v.slot_id=?",(s["slot_id"],))
            # Within one slot an arm and timepoint identify one bar; re-reads changed only scope, basis or context labels.
            fresh={(t["arm_key"],t["timepoint_key"]) for t in found if t["updated_at"]>=read_from}
            for t in found:
                if t["updated_at"]>=read_from:continue
                if (t["arm_key"],t["timepoint_key"]) in fresh:
                    con.execute("DELETE FROM an_target_values WHERE tv_id=?",(t["tv_id"],));dropped+=1
                else:
                    kept+=1;print("kept, no new row",s["slot_id"],t["arm_key"],t["timepoint_key"],t.get("context_key"),round(t["mean"],3),t["error_bar_status"])
        print("dropped",dropped,"kept",kept)
        changelog(con,"AUTHOR-20261106","migration","drop-replaced-readings","APPLIED" if apply_ else "DRY_RUN",{"dropped":dropped,"kept":kept})
        if not apply_:raise SystemExit("Dry run complete: rolled back. Repeat with --apply.")
    raise SystemExit(0)

if "--reopen-slot" in sys.argv:
    # A slot read under the replaced error-bar rule is read again, and its pending adjudication is dropped.
    sid=sys.argv[sys.argv.index("--reopen-slot")+1]
    with tx(con):
        study=rows(con,"SELECT study_id FROM wf_target_slots WHERE slot_id=?",(sid,))[0]["study_id"]
        reopen(sid,study)
        print("cancelled adjudication",con.execute("UPDATE wf_tasks SET status='CANCELLED',updated_at=? WHERE study_id=? AND task_type='ADJUDICATE' AND status='READY'",(now(),study)).rowcount)
        print("reopened",sid,rows(con,"SELECT task_id,task_type,status FROM wf_tasks WHERE study_id=? AND scope_ref=?",(study,sid)))
        changelog(con,"AUTHOR-20261106","migration","reopen-slot","APPLIED" if apply_ else "DRY_RUN",{"slot":sid})
        if not apply_:raise SystemExit("Dry run complete: rolled back. Repeat with --apply.")
    raise SystemExit(0)

if "--reopen-yield-bars" in sys.argv or "--reopen-dry-bars" in sys.argv:
    # Author decision 2026-11-06: bars declined for the 5% limit are read again at any size.
    endpoint="DRY_BIOMASS" if "--reopen-dry-bars" in sys.argv else "FRUIT_YIELD"
    with tx(con):
        slots=rows(con,"SELECT DISTINCT t.study_id,v.slot_id FROM an_target_values t JOIN wf_values v ON v.study_id=t.study_id AND v.record_key=t.record_key AND v.source_kind='FIGURE' WHERE t.endpoint=? AND t.source_kind='FIGURE' AND t.error_bar_status='NOT_READABLE' ORDER BY 1,2",(endpoint,))
        for r in slots:reopen(r["slot_id"],r["study_id"])
        print("reopened",len(slots),"slots in",len({r["study_id"] for r in slots}),"studies")
        print("ready",rows(con,"SELECT task_type,COUNT(*) n FROM wf_tasks WHERE status='READY' GROUP BY 1"))
        changelog(con,"AUTHOR-20261106","migration","reopen-yield-bars","APPLIED" if apply_ else "DRY_RUN",{"slots":[r["slot_id"] for r in slots]})
        if not apply_:raise SystemExit("Dry run complete: rolled back. Repeat with --apply.")
    raise SystemExit(0)

if "--rewaive-outliers" in sys.argv:
    # validate reopened flags that QA had already waived; the identical flag keeps its source-checked verdict.
    with tx(con):
        # z_MAD in the message moves with the pool, so a verdict matches on the contrast and its effect.
        opened=rows(con,"SELECT * FROM wf_validation WHERE status='OPEN' AND rule_id='C001'")
        for r in opened:
            hit=rows(con,"SELECT resolution FROM wf_validation WHERE status='WAIVED' AND rule_id='C001' AND entity=? AND entity_id=? AND message LIKE ? LIMIT 1",(r["entity"],r["entity_id"],r["message"].split(" (|z_MAD|")[0]+"%"))
            r["res"]=hit[0]["resolution"] if hit else None
            if r["res"]:con.execute("UPDATE wf_validation SET status='WAIVED',resolved_at=?,resolution=? WHERE issue_id=?",(now(),r["res"],r["issue_id"]))
            else:print("no earlier verdict",r["issue_id"],r["study_id"],r["message"])
        print("rewaived",sum(1 for r in opened if r["res"]),"of",len(opened))
        changelog(con,"AUTHOR-20261106","migration","rewaive-outliers","APPLIED" if apply_ else "DRY_RUN",{"rewaived":sum(1 for r in opened if r["res"]),"open":len(opened)})
        if not apply_:raise SystemExit("Dry run complete: rolled back. Repeat with --apply.")
    raise SystemExit(0)

if "--qa-escalations" in sys.argv:
    # D_8001: the PDF prints 2024, so the tag goes through an independent patch review.
    # D_2839: slots #02 and #03 hold one quantity. Decision 2 keeps Fig. 5; the prose stays in wf_values as raw source values.
    with tx(con):
        study="D_8001a5a9a7f243bb"
        cur=con.execute("SELECT temporal_eligibility FROM studies WHERE study_id=?",(study,)).fetchone()[0]
        con.execute("INSERT INTO wf_core_patches(study_id,table_name,row_id,field,current_value,proposed_value,reason,locator,status,run_id,created_at) VALUES(?,?,?,?,?,?,?,?,'PROPOSED',?,?)",
                    (study,"studies",study,"temporal_eligibility",json.dumps(cur),json.dumps("EXCLUDE_POST2023_KNOWN"),"Original page 1 prints Published: 6 June 2024 and Agronomy 2024, 14, 1227; year 2024 is after the 2023-12-31 cutoff","physical page 1, history block and citation","AUTHOR-20261106",now()))
        pid=con.execute("SELECT last_insert_rowid()").fetchone()[0]
        print("patch",pid,"task",create_task(con,cfg,study,"PATCH_REVIEW",f"patch-{pid}"))
        study,slot="D_2839c8267b75ab63","D_2839c8267b75ab63#03"
        ctx="FSOLANI_WILT|DISEASE_INCIDENCE_PCT_SEVERITY_WEIGHTED_0_4_SONG|PLANT|45DAT"
        for r in rows(con,"SELECT tv_id,arm_key,timepoint_key,source_kind,mean FROM an_target_values WHERE study_id=? AND context_key=?",(study,ctx)):print("drop",r)
        n=con.execute("DELETE FROM an_target_values WHERE study_id=? AND context_key=?",(study,ctx)).rowcount
        con.execute("UPDATE wf_target_slots SET status='NOT_EXTRACTABLE',not_extractable_reason=?,updated_at=? WHERE slot_id=?",("Same quantity as Fig. 5 (slot #02). Author decision 2 of 2026-11-05 keeps the figure value; prose values 95.2/57.1/42.3/34 stay in wf_values as raw source values",now(),slot))
        changelog(con,"AUTHOR-20261106","migration","qa-escalations","APPLIED" if apply_ else "DRY_RUN",{"patch":pid,"dropped_values":n})
        print("dropped",n,"values of",slot)
        print("slot",rows(con,"SELECT slot_id,status FROM wf_target_slots WHERE study_id=? AND endpoint='BIOTIC_SEVERITY'",(study,)))
        if not apply_:raise SystemExit("Dry run complete: rolled back. Repeat with --apply.")
    raise SystemExit(0)

if "--close-excluded-slots" in sys.argv:
    # Release gates count these rows regardless of study state; the scope decision is the reason.
    with tx(con):
        hit=con.execute("UPDATE wf_target_slots SET status='NOT_EXTRACTABLE',not_extractable_reason='Study excluded by scope decision',updated_at=? WHERE status NOT IN ('VERIFIED','VERIFIED_PARTIAL','NOT_EXTRACTABLE') AND study_id IN (SELECT study_id FROM wf_study_status WHERE state='EXCLUDED_SCOPE')",(now(),)).rowcount
        print("closed slots",hit)
        changelog(con,"AUTHOR-20261106","migration","close-excluded-slots","APPLIED" if apply_ else "DRY_RUN",{"slots":hit})
        if not apply_:raise SystemExit("Dry run complete: rolled back. Repeat with --apply.")
    raise SystemExit(0)

if "--preview-patches" in sys.argv:
    # Read only: try the patches a decision file accepts, report each failure, then roll everything back.
    from tfmlib.maintenance import apply_patch
    decisions=json.loads(Path(sys.argv[sys.argv.index("--preview-patches")+1]).read_text(encoding="utf-8-sig"))
    wanted={d["review_id"] for d in decisions if d["decision"]=="ACCEPT"}
    items=rows(con,"SELECT review_id,ref FROM wf_review WHERE status='OPEN' AND kind='PATCH'")
    con.execute("BEGIN")
    for it in items:
        if it["review_id"] not in wanted:continue
        pid=int(it["ref"].split("-",1)[1])
        try:
            apply_patch(con,cfg,pid,"PREVIEW");print("ok",it["review_id"],pid)
        except ValueError as exc:
            print("FAIL",it["review_id"],pid,exc)
    con.execute("ROLLBACK")
    raise SystemExit(0)

if "--preview-units" in sys.argv:
    # Read only: what the human units-renormalize command would now change for fruit yield.
    from tfmlib.units import normalize
    seen=set()
    for r in rows(con,"SELECT study_id,unit_raw,denominator,mean FROM an_target_values WHERE endpoint='FRUIT_YIELD' AND unit_norm IS NULL AND unit_raw IS NOT NULL ORDER BY study_id"):
        k=(r["study_id"],r["unit_raw"],r["denominator"])
        if k in seen:continue
        seen.add(k);u,f,d=normalize(r["unit_raw"],"FRUIT_YIELD",r["denominator"])
        print(r["study_id"],"|",r["unit_raw"][:40],"|",r["denominator"],"->",u,f,d,"| example",r["mean"],"->",None if f is None else round(r["mean"]*f,4))
    raise SystemExit(0)

if "--reopen-two-tick" in sys.argv:
    # Author decision 2026-11-06: Fig. 3k is the only yield of its study, so it is read on its two labelled axis points.
    with tx(con):
        for sid in cfg.get("figures.two_tick_axis_slots") or []:
            study=rows(con,"SELECT study_id FROM wf_target_slots WHERE slot_id=?",(sid,))[0]["study_id"]
            reopen(sid,study);print("reopened",sid)
        print("ready",rows(con,"SELECT task_id,task_type,scope_ref FROM wf_tasks WHERE status='READY' AND task_type IN ('FIGURE_A','FIGURE_B')"))
        changelog(con,"AUTHOR-20261106","migration","reopen-two-tick","APPLIED" if apply_ else "DRY_RUN",{})
        if not apply_:raise SystemExit("Dry run complete: rolled back. Repeat with --apply.")
    raise SystemExit(0)

with tx(con):
    # KNO3 is not a biostimulant: this study has no biostimulant arm left.
    study=EXCLUDED_STUDY
    print("exclude",study,con.execute("SELECT COUNT(*) FROM an_target_values WHERE study_id=?",(study,)).fetchone()[0],"values")
    for cid in [r["contrast_id"] for r in rows(con,"SELECT contrast_id FROM an_contrasts WHERE study_id=?",(study,))]:
        con.execute("DELETE FROM an_covariance WHERE contrast_a=? OR contrast_b=?",(cid,cid))
    con.execute("DELETE FROM an_contrasts WHERE study_id=?",(study,))
    con.execute("DELETE FROM an_target_values WHERE study_id=?",(study,))
    con.execute("UPDATE wf_tasks SET status='CANCELLED',updated_at=? WHERE study_id=? AND status IN ('READY','LEASED','FAILED')",(now(),study))
    # Release gates count these rows regardless of study state, so they are closed with the same reason.
    note="Author 2026-11-05: KNO3 is not a biostimulant"
    con.execute("UPDATE wf_target_slots SET status='NOT_EXTRACTABLE',not_extractable_reason=?,updated_at=? WHERE study_id=? AND status NOT IN ('VERIFIED','VERIFIED_PARTIAL','NOT_EXTRACTABLE')",(note,now(),study))
    con.execute("UPDATE wf_reconciliation SET status='RESOLVED',resolved_value_id=NULL,resolved_by='HUMAN',updated_at=? WHERE study_id=? AND status IN ('OPEN','ESCALATED')",(now(),study))
    con.execute("UPDATE wf_review SET status='DECIDED',decision='EXCLUDED_SCOPE',decision_note=?,decided_by=?,decided_at=? WHERE study_id=? AND status='OPEN'",(note,RUN,now(),study))
    con.execute("UPDATE wf_validation SET status='WAIVED',resolved_at=?,resolution=? WHERE study_id=? AND status='OPEN' AND severity<>'BLOCKING'",(now(),note,study))
    set_state(con,study,"EXCLUDED_SCOPE",RUN,scope_status="EXCLUDED",locked=1,notes=note)

    # Boxplot slots declined earlier, then slots declined as a whole on the 5% limit.
    box=["D_0e4b363eeb15d524#01","256#01","256#02","256#03","256#04","D_b205610597d43dda#07","D_b205610597d43dda#08"]
    limit=[r["slot_id"] for r in rows(con,"SELECT slot_id FROM wf_target_slots WHERE status='NOT_EXTRACTABLE' AND route IN ('FIGURE','TWIN_VALIDATION') AND instr(coalesce(not_extractable_reason,''),'5%') AND coalesce(not_extractable_reason,'') NOT LIKE '%DUPLICATE%' AND coalesce(not_extractable_reason,'') NOT LIKE '%Unsupported geometry%' AND study_id NOT IN (SELECT study_id FROM wf_study_status WHERE state='EXCLUDED_SCOPE')")]
    for sid in sorted(set(box+limit)):
        s=rows(con,"SELECT study_id,endpoint,expected_n_values,status FROM wf_target_slots WHERE slot_id=?",(sid,))[0]
        print("reopen",sid,s["endpoint"],s["expected_n_values"],"was",s["status"])
        reopen(sid,s["study_id"])

    # Average every agreeing figure pair. Figure now outranks text, not tables.
    changed=0
    for rec in rows(con,"SELECT * FROM wf_reconciliation WHERE family='FIGURE' AND outcome='AGREE' AND status='RESOLVED' AND resolved_by='AUTO'"):
        ex=rows(con,"SELECT verification,source_kind FROM an_target_values WHERE study_id=? AND record_key=?",(rec["study_id"],rec["record_key"]))
        if not ex or (ex[0]["source_kind"]=="FIGURE" and ex[0]["verification"]!="DOUBLE_AGREE"):continue
        a=rows(con,"SELECT * FROM wf_values WHERE value_id=?",(rec["value_id_a"],))[0]
        b=rows(con,"SELECT * FROM wf_values WHERE value_id=?",(rec["value_id_b"],))[0]
        promote(con,cfg,rec["study_id"],rec["record_key"],a,"DOUBLE_AGREE",[rec["value_id_a"],rec["value_id_b"]],agree_override(a,b,cfg,True),RUN)
        changed+=1
    print("re-promoted agreeing figure pairs",changed)

    # Restore table values replaced by adjudicated figure values.
    priority=cfg.get("source_priority");restored=0
    for tv in rows(con,"SELECT * FROM an_target_values WHERE source_kind='FIGURE' AND verification='ADJUDICATED'"):
        rec=rows(con,"SELECT * FROM wf_reconciliation WHERE study_id=? AND record_key=? AND family='TEXT_TABLE' AND status='RESOLVED' AND resolved_value_id IS NOT NULL",(tv["study_id"],tv["record_key"]))
        if not rec:continue
        base=rows(con,"SELECT * FROM wf_values WHERE value_id=?",(rec[0]["resolved_value_id"],))[0]
        if priority.index(base["source_kind"])>=priority.index("FIGURE"):continue
        ver="DOUBLE_AGREE" if rec[0]["outcome"]=="AGREE" else "ADJUDICATED"
        print("restore",tv["tv_id"],tv["study_id"],tv["mean"],"->",base["mean"])
        promote(con,cfg,tv["study_id"],tv["record_key"],base,ver,[base["value_id"]],{"receipt_id":base.get("receipt_id"),"source_cell":base.get("source_cell")},RUN)
        restored+=1
    print("restored table values",restored)

    # Dry basis: explicit source labels are seeded. Other studies get a source check task.
    need=set();seeded=0
    for tv in rows(con,"SELECT * FROM an_target_values WHERE endpoint='DRY_BIOMASS'"):
        text=" ".join(str(tv.get(k) or "") for k in ("verbatim","source_cell","locator","unit_raw","outcome_context_json"))
        if DRY.search(text):
            con.execute("INSERT OR IGNORE INTO wf_dry_basis VALUES(?,?,?,?,?,?,?,?,?)",(tv["study_id"],tv["record_key"],"DRY_CONFIRMED","LABEL_KEYWORD",tv["source_file_id"],tv["receipt_id"],text[:300],RUN,now()))
            seeded+=1
        else:need.add(tv["study_id"])
    for study in sorted(need):create_task(con,cfg,study,"DRY_BASIS","")
    print("dry basis seeded",seeded,"studies to check",len(need))

    # Open design reports closed only by a design pass, and no such pass is queued for them.
    gap=[r["study_id"] for r in rows(con,"SELECT DISTINCT study_id FROM wf_review WHERE kind='DESIGN_GAP' AND status='OPEN' ORDER BY study_id")]
    for study in gap:create_task(con,cfg,study,"DESIGN","gap-review-20261105")
    print("design gap reviews queued",len(gap))

    # A primary absence needs its independent original-only search before release.
    second=[r["study_id"] for r in rows(con,"SELECT t.study_id FROM wf_triage t JOIN wf_study_status s USING(study_id) WHERE t.pass='P1' AND t.fruit_yield<>'PRESENT' AND s.state<>'EXCLUDED_SCOPE' AND NOT EXISTS (SELECT 1 FROM wf_triage p WHERE p.study_id=t.study_id AND p.pass='P2') ORDER BY t.study_id")]
    for study in second:create_task(con,cfg,study,"TRIAGE_2ND","")
    print("independent second triage queued",second)

    studies=[r["study_id"] for r in rows(con,"SELECT DISTINCT study_id FROM wf_target_slots")]
    before={r["status"]:r["n"] for r in rows(con,"SELECT status,COUNT(*) n FROM wf_target_slots GROUP BY 1")}
    for study in studies:refresh_slots(con,study)
    print("slots before refresh",before)
    print("slots after refresh",{r["status"]:r["n"] for r in rows(con,"SELECT status,COUNT(*) n FROM wf_target_slots GROUP BY 1")})
    print("ready tasks",{r["task_type"]:r["n"] for r in rows(con,"SELECT task_type,COUNT(*) n FROM wf_tasks WHERE status='READY' GROUP BY 1")})
    changelog(con,RUN,"migration","author-20261105","APPLIED" if apply_ else "DRY_RUN",{})
    if not apply_:raise SystemExit("Dry run complete: rolled back. Repeat with --apply.")
print("applied")
