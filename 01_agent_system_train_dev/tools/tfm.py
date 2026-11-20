#!/usr/bin/env python3
"""TFM agent system CLI — the ONLY way agents read work and write results.

Run `python3 tools/tfm.py -h` for commands. Output is JSON (machine-readable)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

from tfmlib import __version__  # noqa: E402
from tfmlib.config import Config  # noqa: E402
from tfmlib.db import ColumnResolver, connect, get_meta, init_schema, now, rows, tx  # noqa: E402


def out(obj, pretty=True):
    print(json.dumps(obj, ensure_ascii=False, indent=1 if pretty else None, default=str))


def _con(cfg, readonly=False):
    if not cfg.db_path.exists() and not readonly:
        con = connect(cfg.db_path)
        init_schema(con)
        return con
    con = connect(cfg.db_path, readonly=readonly)
    if not readonly:
        init_schema(con)   # idempotent: creates new wf_ tables after upgrades
    return con


def cmd_init(cfg, a):
    con = _con(cfg)
    out({"db": str(cfg.db_path), "code_version": __version__, "created_at": get_meta(con, "created_at")})


def cmd_import_xlsx(cfg, a):
    from tfmlib.importer import import_workbook, seed_studies
    path = Path(a.path).expanduser() if a.path else cfg.p("workbook")
    if not path or not path.exists():
        sys.exit(f"workbook not found: {path} (set `workbook` in config/paths.yaml)")
    con = _con(cfg)
    counts = import_workbook(con, path)
    seeded = seed_studies(con, cfg)
    cr = ColumnResolver(con, cfg.column_map)
    checks = _check_columns(con, cfg)
    out({"imported": counts, "studies": seeded, "column_check": checks})


def _check_columns(con, cfg):
    cr = ColumnResolver(con, cfg.column_map)
    resolved = {}
    for table, fields in (cfg.column_map or {}).items():
        for f in fields:
            resolved[f"{table}.{f}"] = cr.get(table, f)
    return {"resolved": resolved, "missing": cr.misses, "fuzzy": cr.fuzzy}


def cmd_check_columns(cfg, a):
    out(_check_columns(_con(cfg), cfg))


def cmd_import_registry(cfg, a):
    from tfmlib.importer import import_registry, seed_studies
    path = Path(a.path).expanduser() if a.path else cfg.p("yield_registry")
    con = _con(cfg)
    n = import_registry(con, path)
    out({"registry_rows": n, "reprioritised": seed_studies(con, cfg)})


def cmd_import_legacy(cfg, a):
    from tfmlib.importer import import_legacy_figures
    root = Path(a.dir).expanduser() if a.dir else cfg.p("legacy_figure_json_root")
    out(import_legacy_figures(_con(cfg), root))


def cmd_seed(cfg, a):
    from tfmlib.tasks import seed_triage
    con = _con(cfg)
    out({"triage_tasks_created": seed_triage(con, cfg, a.limit, a.studies)})


def cmd_claim(cfg, a):
    from tfmlib.context import build_packet
    from tfmlib.tasks import claim
    con = _con(cfg)
    owner = a.owner or f"{os.environ.get('USER', 'agent')}@{now()}"
    tasks = claim(con, cfg, owner, a.agent, a.types.split(",") if a.types else None, a.limit, a.study)
    res = []
    for t in tasks:
        p = build_packet(con, cfg, t)
        res.append({"task_id": t["task_id"], "task_type": t["task_type"], "agent": t["agent"], "study_id": t["study_id"],
                    "scope_ref": t["scope_ref"], "packet": str(p.relative_to(cfg.root)),
                    "output_path": f"work/outbox/{t['task_id']}.json",
                    "submit": f"python3 tools/tfm.py submit {t['task_id']} work/outbox/{t['task_id']}.json"})
    out({"claimed": len(res), "tasks": res})


def cmd_packet(cfg, a):
    from tfmlib.context import build_packet
    con = _con(cfg)
    t = rows(con, "SELECT * FROM wf_tasks WHERE task_id=?", (a.task_id,))
    if not t:
        sys.exit("unknown task")
    out({"packet": str(build_packet(con, cfg, t[0]).relative_to(cfg.root))})


def cmd_submit(cfg, a):
    from tfmlib.submit import submit
    res = submit(_con(cfg), cfg, a.task_id, Path(a.file))
    out(res)
    if res.get("status") != "ACCEPTED":
        sys.exit(2)


def cmd_release(cfg, a):
    from tfmlib.tasks import release
    out({"task_id": a.task_id, "status": release(_con(cfg), cfg, a.task_id, a.error)})


def cmd_reconcile(cfg, a):
    from tfmlib.reconcile import reconcile, refresh_slots
    from tfmlib.submit import Ctx, ensure_adjudication, maybe_verify
    con = _con(cfg)
    with tx(con):
        st = reconcile(con, cfg, a.study, a.family, a.slot)
        refresh_slots(con, a.study)
        ctx = Ctx(con, cfg, {"task_id": "manual", "study_id": a.study, "task_type": "RECONCILE", "scope_ref": ""}, {}, "MANUAL")
        ensure_adjudication(ctx)
        maybe_verify(ctx)
    out({"reconciled": st, "followups": ctx.followups})


def cmd_figure_fit(cfg, a):
    from tfmlib.figures import CalibrationError, calibration_status, fit_axis, point_values
    data = json.loads(Path(a.file).read_text(encoding="utf-8-sig"))
    fcfg = cfg.get("figures") or {}
    res = []
    for p in data.get("panels", []):
        try:
            cal = fit_axis(p["axis"]["ticks"], p["axis"]["scale"])
        except CalibrationError as exc:
            res.append({"panel": p.get("panel"), "error": str(exc)})
            continue
        st = calibration_status(cal, int(fcfg.get("min_ticks", 2)), int(fcfg.get("recommended_ticks", 3)),
                                float(fcfg.get("max_resid_frac", 0.015)))
        pts = []
        for pt in p["points"]:
            m, e, info = point_values(pt["px_mean"], pt.get("px_err_hi"), pt.get("px_err_lo"), cal)
            pts.append({"arm_key": pt["arm_key"], "timepoint_key": pt["timepoint_key"], "mean": round(m, 6),
                        "err": None if e is None else round(e, 6), **info})
        res.append({"figure": p.get("figure_label"), "panel": p.get("panel"), "calibration": {k: round(v, 6) if isinstance(v, float) else v for k, v in cal.items()},
                    "status": st, "points": pts})
    out(res)


def cmd_figure_grid(cfg, a):
    from tfmlib.figures import grid_overlay
    bbox = tuple(int(float(x)) for x in a.bbox.split(",")) if a.bbox else None
    if not Path(a.image).resolve().is_relative_to((cfg.work_dir/"source_views").resolve()): raise ValueError("figure-grid input must be an original-source receipt image")
    out(grid_overlay(Path(a.image), Path(a.out), a.step, a.zoom, bbox))


def cmd_figure_snap(cfg, a):
    from tfmlib.figures import snap_vertical
    if not Path(a.image).resolve().is_relative_to((cfg.work_dir/"source_views").resolve()): raise ValueError("figure-snap input must be an original-source receipt image")
    out(snap_vertical(Path(a.image), json.loads(a.points), int(a.search or cfg.get("figures.snap_search_px", 6)),
                      offset=a.offset))


def cmd_figure_probe(cfg, a):
    from tfmlib.figures import vector_probe
    bbox = [float(x) for x in a.bbox.split(",")] if a.bbox else None
    res = vector_probe(Path(a.pdf), a.page, bbox)
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1), encoding="utf-8")
        out({"written": a.out, "texts": len(res["texts"]), "rects": len(res["rects"]), "lines": len(res["lines"])})
    else:
        out(res)


def cmd_validate(cfg, a):
    from tfmlib.validate import run
    out(run(_con(cfg), cfg, "VALIDATE-" + now(), tuple(a.scope.split(","))))


def cmd_contrasts(cfg, a):
    from tfmlib.contrasts import build
    out(build(_con(cfg), cfg, a.study))


def cmd_close(cfg, a):
    from tfmlib.tasks import set_state
    con = _con(cfg)
    st = rows(con, "SELECT * FROM wf_study_status WHERE study_id=?", (a.study,))
    if not st:
        sys.exit("unknown study")
    st = st[0]
    problems = []
    if a.force:
        problems.append("--force cannot bypass release/verification rules in v2")
    if st["state"] not in ("VERIFIED",):
        problems.append(f"state is {st['state']} (needs VERIFIED)")
    blk = con.execute("SELECT COUNT(*) FROM wf_validation WHERE (study_id=? OR study_id IS NULL) AND status='OPEN' AND severity='BLOCKING'",
                      (a.study,)).fetchone()[0]
    if blk:
        problems.append(f"{blk} open BLOCKING issues")
    busy = con.execute("SELECT COUNT(*) FROM wf_tasks WHERE study_id=? AND status IN ('READY','LEASED')", (a.study,)).fetchone()[0]
    if busy:
        problems.append(f"{busy} tasks still open")
    if problems:
        out({"closed": False, "problems": problems})
        sys.exit(2)
    with tx(con):
        set_state(con, a.study, "CLOSED", "CLOSE", locked=1, closed_at=now())
    out({"closed": True, "study_id": a.study})


def cmd_close_all(cfg, a):
    con = _con(cfg)
    ids = [r["study_id"] for r in rows(con, "SELECT study_id FROM wf_study_status WHERE state='VERIFIED'")]
    closed, skipped = [], []
    for s in ids:
        a.study, a.force = s, False
        try:
            cmd_close(cfg, a)
            closed.append(s)
        except SystemExit:
            skipped.append(s)
    out({"closed": len(closed), "skipped": skipped})


def cmd_review_export(cfg, a):
    from tfmlib.review import export
    out({"open_items": export(_con(cfg), Path(a.out)), "csv": a.out})


def cmd_review_import(cfg, a):
    from tfmlib.review import apply
    out(apply(_con(cfg), cfg, Path(a.file), a.reviewer))


def cmd_gold_sample(cfg, a):
    from tfmlib.sampling import gold_sample
    out(gold_sample(_con(cfg), cfg, a.n, Path(a.out)))


def cmd_gold_import(cfg, a):
    from tfmlib.sampling import gold_import
    out({"gold_rows": gold_import(_con(cfg), Path(a.file))})


def cmd_gold_score(cfg, a):
    from tfmlib.sampling import gold_score
    out(gold_score(_con(cfg), cfg))


def cmd_audit_sample(cfg, a):
    from tfmlib.sampling import audit_sample
    out(audit_sample(_con(cfg), cfg, Path(a.out), a.agent))


def cmd_audit_import(cfg, a):
    from tfmlib.sampling import audit_import
    out({"audit_rows": audit_import(_con(cfg), Path(a.file), a.reviewer)})


def cmd_dedup_seed(cfg, a):
    from tfmlib.dedup import seed_dedup_tasks
    out(seed_dedup_tasks(_con(cfg), cfg))


def cmd_status(cfg, a):
    con = _con(cfg)
    res = {
        "db": str(cfg.db_path), "workbook_sha256": get_meta(con, "workbook_sha256"),
        "studies_by_state": rows(con, "SELECT * FROM v_progress ORDER BY state"),
        "tasks": rows(con, "SELECT task_type, status, COUNT(*) n FROM wf_tasks GROUP BY task_type, status ORDER BY task_type"),
        "slots": rows(con, "SELECT * FROM v_slot_progress"),
        "verified_values": rows(con, "SELECT endpoint, verification, source_kind, COUNT(*) n FROM an_target_values "
                                     "GROUP BY endpoint, verification, source_kind"),
        "contrasts": rows(con, "SELECT endpoint, contrast_type, COUNT(*) n, SUM(var_available) with_var, "
                               "COUNT(DISTINCT study_id) studies, COUNT(DISTINCT dependency_cluster_id) clusters "
                               "FROM an_contrasts GROUP BY endpoint, contrast_type"),
        "open_review": rows(con, "SELECT kind, COUNT(*) n FROM wf_review WHERE status='OPEN' GROUP BY kind"),
        "open_issues": rows(con, "SELECT severity, rule_id, COUNT(*) n FROM wf_validation WHERE status='OPEN' "
                                 "GROUP BY severity, rule_id ORDER BY severity, rule_id"),
        "runs": rows(con, "SELECT agent, status, COUNT(*) n FROM wf_runs GROUP BY agent, status"),
    }
    out(res)


def cmd_gates(cfg, a):
    from tfmlib.gates import accuracy
    from tfmlib.release import checks
    con = _con(cfg)
    out({"gates": checks(con, cfg), "accuracy": accuracy(con, cfg)})


def cmd_export(cfg, a):
    from tfmlib.export import export_all, export_xlsx
    con = _con(cfg)
    res = export_all(con, cfg, Path(a.out) if a.out else None, draft=a.draft)
    if a.xlsx:
        res["xlsx"] = export_xlsx(con, cfg, Path(a.xlsx))
    out(res)


def cmd_sql(cfg, a):
    con = connect(cfg.db_path, readonly=True)
    sql = a.query.strip().rstrip(";")
    if not sql.lower().startswith(("select", "with", "pragma table_info")):
        sys.exit("read-only: only SELECT/WITH queries are allowed")
    res = rows(con, sql)
    out(res[: a.limit] if a.limit else res)


def cmd_study(cfg, a):
    from tfmlib.context import study_dump
    out(study_dump(_con(cfg), cfg, a.study))


def cmd_replicate_summary(cfg,a):
    from tfmlib.derive import replicate_summary
    out(replicate_summary(_con(cfg),cfg,Path(a.file)))
def cmd_verify_build(cfg,a):
    from tfmlib.db import sha256_file
    root=Path(a.dir);manifest=json.loads((root/"MANIFEST.json").read_text(encoding="utf-8"))
    bad=[f["file"] for f in manifest["files"] if not (root/f["file"]).is_file() or sha256_file(root/f["file"])!=f["sha256"]]
    out({"status":"FAIL" if bad else "PASS","files":len(manifest["files"]),"changed_or_missing":bad,"ready_to_use":manifest["ready_to_use"] and not bad})
    if bad:sys.exit(2)
def cmd_pilot_select(cfg,a):
    from tfmlib.db import set_meta
    con=_con(cfg);saved=get_meta(con,"pilot_ids")
    if saved:ids=json.loads(saved)
    else:
        k=min(int(cfg.get("autonomy.pilot_studies",10)),con.execute("SELECT COUNT(*) FROM wf_study_status").fetchone()[0]);ids=[]
        groups={r["priority"]:[] for r in rows(con,"SELECT DISTINCT priority FROM wf_study_status ORDER BY priority")}
        for r in rows(con,"SELECT study_id,priority FROM wf_study_status ORDER BY priority,study_id"):groups[r["priority"]].append(r["study_id"])
        while len(ids)<k and any(groups.values()):
            for priority in sorted(groups):
                if groups[priority] and len(ids)<k:ids.append(groups[priority].pop(0))
        set_meta(con,"pilot_ids",ids)
    out({"pilot_studies":ids,"status":get_meta(con,"pilot_status") or "PENDING","instruction":"Finish these studies with claim --study, up to four independent workers, then pilot-finish; no user batch approval required."})
def cmd_pilot_finish(cfg,a):
    from tfmlib.db import set_meta
    con=_con(cfg);ids=json.loads(get_meta(con,"pilot_ids") or "[]");problems=[]
    for study in ids:
        r=rows(con,"SELECT state FROM wf_study_status WHERE study_id=?",(study,))[0]
        if r["state"] not in ("VERIFIED","CLOSED","NO_TARGET_CONFIRMED","EXCLUDED_SCOPE"):problems.append({"study_id":study,"state":r["state"]})
        if con.execute("SELECT COUNT(*) FROM wf_validation WHERE study_id=? AND severity='BLOCKING' AND status='OPEN'",(study,)).fetchone()[0]:problems.append({"study_id":study,"reason":"open blocking QA"})
    status="PASS" if ids and not problems else "PENDING"
    set_meta(con,"pilot_status",status);out({"status":status,"pilot_n":len(ids),"problems":problems})

def cmd_source_index(cfg,a):
    from tfmlib.sourceqa import index_sources
    out(index_sources(_con(cfg),cfg))
def cmd_source_view(cfg,a):
    from tfmlib.sourceqa import view
    out(view(_con(cfg),cfg,a.source_file_id,a.page,a.sheet,a.cell_range,a.dpi,a.sheet_index))
def cmd_preflight(cfg,a):
    from tfmlib.setup import preflight
    r=preflight(_con(cfg),cfg);out(r)
    if r["status"]!="PASS":sys.exit(2)
def cmd_configure(cfg,a):
    from tfmlib.setup import configure
    out(configure(cfg,a.corpus,a.workbook))
def cmd_metadata(cfg,a):
    from tfmlib.setup import normalize_metadata
    out(normalize_metadata(_con(cfg),cfg))
def cmd_relations_import(cfg,a):
    from tfmlib.maintenance import import_relations
    out(import_relations(_con(cfg),cfg))
def cmd_qa_seed(cfg,a):
    from tfmlib.maintenance import seed_qa
    out(seed_qa(_con(cfg),cfg))
def cmd_human_export(cfg,a):
    from tfmlib.release import human_audit_export
    out(human_audit_export(_con(cfg),cfg,Path(a.out)))
def cmd_human_import(cfg,a):
    from tfmlib.release import human_audit_import
    out(human_audit_import(_con(cfg),cfg,Path(a.file),a.reviewer))
def cmd_contract_rebase(cfg,a):
    from tfmlib.config import execution_contract_hash
    from tfmlib.db import set_meta,changelog
    reason=a.reason.strip()
    if len(reason)<20:raise ValueError("state the reason for the contract change")
    con=_con(cfg);old=get_meta(con,"execution_contract_hash");new=execution_contract_hash(cfg)
    if old==new:
        out({"status":"UNCHANGED","hash":new});return
    leased=con.execute("SELECT COUNT(*) FROM wf_tasks WHERE status='LEASED'").fetchone()[0]
    if leased:raise ValueError(f"{leased} leased tasks: finish or release them first")
    with tx(con):
        set_meta(con,"execution_contract_hash",new)
        changelog(con,"HUMAN-CONTRACT-REBASE","contract","execution_contract_hash","REBASE",{"old":old,"new":new,"reason":reason,"reviewer":a.reviewer})
    out({"status":"REBASED","old":old,"new":new})
def cmd_units_renormalize(cfg,a):
    from tfmlib.maintenance import renormalize_units
    out(renormalize_units(_con(cfg),cfg,a.apply))
def cmd_reverify(cfg,a):
    """Apply the normal maybe_verify readiness check to STRUCTURED studies with no open tasks."""
    from tfmlib.submit import Ctx, maybe_verify
    con=_con(cfg);res=[]
    for r in rows(con,"SELECT study_id FROM wf_study_status WHERE state='STRUCTURED'"):
        sid=r["study_id"]
        if con.execute("SELECT COUNT(*) FROM wf_tasks WHERE study_id=? AND status IN ('READY','LEASED')",(sid,)).fetchone()[0]:
            res.append({"study_id":sid,"state":"STRUCTURED","note":"open tasks"});continue
        with tx(con):
            maybe_verify(Ctx(con,cfg,{"study_id":sid,"task_id":""},{},"REVERIFY-"+now()))
        res.append({"study_id":sid,"state":con.execute("SELECT state FROM wf_study_status WHERE study_id=?",(sid,)).fetchone()[0]})
    out({"n":len(res),"by_state":{st:sum(1 for x in res if x["state"]==st) for st in {x["state"] for x in res}},"studies":res})
def cmd_requeue_stale(cfg,a):
    """Reopen moderator verification for studies with UNVERIFIED moderators; queue DRY_BASIS for unchecked dry biomass."""
    from tfmlib.tasks import set_state, create_task
    con=_con(cfg);mods=[];dry=[]
    with tx(con):
        for r in rows(con,"SELECT DISTINCT study_id FROM wf_moderators WHERE verification NOT IN ('SOURCE_VERIFIED_AB','SOURCE_ADJUDICATED')"):
            sid=r["study_id"];set_state(con,sid,"STRUCTURED","REQUEUE-STALE",locked=0,notes="moderators re-extracted; independent verification re-run")
            t=con.execute("SELECT task_id FROM wf_tasks WHERE study_id=? AND task_type='MODERATORS_VERIFY' AND scope_ref=''",(sid,)).fetchone()
            if t:con.execute("UPDATE wf_tasks SET status='READY',attempts=0,updated_at=? WHERE task_id=?",(now(),t[0]));tid=t[0]
            else:tid=create_task(con,cfg,sid,"MODERATORS_VERIFY","")
            mods.append({"study_id":sid,"task":tid})
        for r in rows(con,"SELECT DISTINCT t.study_id FROM an_target_values t WHERE t.endpoint='DRY_BIOMASS' AND NOT EXISTS (SELECT 1 FROM wf_dry_basis b WHERE b.study_id=t.study_id AND b.tv_record_key=t.record_key)"):
            dry.append({"study_id":r["study_id"],"task":create_task(con,cfg,r["study_id"],"DRY_BASIS","rerun-20261113")})
    out({"moderators_verify":mods,"dry_basis":dry})
def cmd_checkpoint(cfg,a):
    con=_con(cfg)
    data={"at":now(),"states":rows(con,"SELECT * FROM v_progress"),"tasks":rows(con,"SELECT * FROM v_task_queue"),"next_action":"Continue /tfm-finalize from persisted queue; never restart/import over this database."}
    p=cfg.work_dir/"CHECKPOINT.json";p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    out(data)

def main(argv=None):
    ap = argparse.ArgumentParser(prog="tfm.py", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init"); s.set_defaults(f=cmd_init)
    s = sub.add_parser("import-xlsx"); s.add_argument("path", nargs="?"); s.set_defaults(f=cmd_import_xlsx)
    s = sub.add_parser("check-columns"); s.set_defaults(f=cmd_check_columns)
    s = sub.add_parser("import-registry"); s.add_argument("path", nargs="?"); s.set_defaults(f=cmd_import_registry)
    s = sub.add_parser("import-legacy-figures"); s.add_argument("dir", nargs="?"); s.set_defaults(f=cmd_import_legacy)
    s = sub.add_parser("seed"); s.add_argument("--limit", type=int); s.add_argument("--studies", nargs="*"); s.set_defaults(f=cmd_seed)
    s = sub.add_parser("claim"); s.add_argument("--agent", default="any"); s.add_argument("--types")
    s.add_argument("--limit", type=int, default=1); s.add_argument("--owner"); s.add_argument("--study"); s.set_defaults(f=cmd_claim)
    s = sub.add_parser("packet"); s.add_argument("task_id"); s.set_defaults(f=cmd_packet)
    s = sub.add_parser("submit"); s.add_argument("task_id"); s.add_argument("file"); s.set_defaults(f=cmd_submit)
    s = sub.add_parser("release"); s.add_argument("task_id"); s.add_argument("--error"); s.set_defaults(f=cmd_release)
    s = sub.add_parser("reconcile"); s.add_argument("study"); s.add_argument("--family", default="TEXT_TABLE",
                                                                             choices=["TEXT_TABLE", "FIGURE"])
    s.add_argument("--slot"); s.set_defaults(f=cmd_reconcile)
    s = sub.add_parser("figure-fit"); s.add_argument("file"); s.set_defaults(f=cmd_figure_fit)
    s = sub.add_parser("figure-grid"); s.add_argument("image"); s.add_argument("--out", required=True)
    s.add_argument("--step", type=int, default=50); s.add_argument("--zoom", type=float, default=2.0); s.add_argument("--bbox")
    s.set_defaults(f=cmd_figure_grid)
    s = sub.add_parser("figure-snap"); s.add_argument("image"); s.add_argument("--points", required=True)
    s.add_argument("--search", type=int)
    s.add_argument("--offset", type=int, default=0, help="sample +/- offset px from x (bar tops: 6-10; caps/markers: 0)")
    s.set_defaults(f=cmd_figure_snap)
    s = sub.add_parser("figure-probe"); s.add_argument("pdf"); s.add_argument("--page", type=int, required=True)
    s.add_argument("--bbox"); s.add_argument("--out"); s.set_defaults(f=cmd_figure_probe)
    s = sub.add_parser("validate"); s.add_argument("--scope", default="core,verified,contrasts"); s.set_defaults(f=cmd_validate)
    s = sub.add_parser("contrasts"); s.add_argument("--study"); s.set_defaults(f=cmd_contrasts)
    s = sub.add_parser("close"); s.add_argument("study"); s.add_argument("--force", action="store_true"); s.set_defaults(f=cmd_close)
    s = sub.add_parser("close-all"); s.set_defaults(f=cmd_close_all)
    s = sub.add_parser("review-export"); s.add_argument("out"); s.set_defaults(f=cmd_review_export)
    s = sub.add_parser("review-import"); s.add_argument("file"); s.add_argument("--reviewer", default="author")
    s.set_defaults(f=cmd_review_import)
    s = sub.add_parser("gold-sample"); s.add_argument("--n", type=int, default=35); s.add_argument("--out", default="work/gold")
    s.set_defaults(f=cmd_gold_sample)
    s = sub.add_parser("gold-import"); s.add_argument("file"); s.set_defaults(f=cmd_gold_import)
    s = sub.add_parser("gold-score"); s.set_defaults(f=cmd_gold_score)
    s = sub.add_parser("audit-sample"); s.add_argument("--out", default="work/audit/audit_sample.csv")
    s.add_argument("--agent", action="store_true", help="also queue AUDIT tasks for the qa-auditor agent")
    s.set_defaults(f=cmd_audit_sample)
    s = sub.add_parser("audit-import"); s.add_argument("file"); s.add_argument("--reviewer", default="author")
    s.set_defaults(f=cmd_audit_import)
    s = sub.add_parser("dedup-seed"); s.set_defaults(f=cmd_dedup_seed)
    s = sub.add_parser("status"); s.set_defaults(f=cmd_status)
    s = sub.add_parser("gates"); s.set_defaults(f=cmd_gates)
    s = sub.add_parser("export"); s.add_argument("--out"); s.add_argument("--xlsx"); s.add_argument("--draft",action="store_true"); s.set_defaults(f=cmd_export)
    s = sub.add_parser("sql"); s.add_argument("query"); s.add_argument("--limit", type=int, default=200); s.set_defaults(f=cmd_sql)
    s = sub.add_parser("study"); s.add_argument("study"); s.set_defaults(f=cmd_study)
    s = sub.add_parser("replicate-summary");s.add_argument("file");s.set_defaults(f=cmd_replicate_summary)
    s = sub.add_parser("verify-build");s.add_argument("dir");s.set_defaults(f=cmd_verify_build)
    s = sub.add_parser("pilot-select");s.set_defaults(f=cmd_pilot_select)
    s = sub.add_parser("pilot-finish");s.set_defaults(f=cmd_pilot_finish)
    s = sub.add_parser("source-index"); s.set_defaults(f=cmd_source_index)
    s = sub.add_parser("source-view"); s.add_argument("source_file_id"); s.add_argument("--page",type=int);s.add_argument("--sheet");s.add_argument("--sheet-index",type=int);s.add_argument("--range",dest="cell_range");s.add_argument("--dpi",type=int,default=180);s.set_defaults(f=cmd_source_view)
    s = sub.add_parser("configure");s.add_argument("--corpus",required=True);s.add_argument("--workbook");s.set_defaults(f=cmd_configure)
    s = sub.add_parser("preflight");s.set_defaults(f=cmd_preflight)
    s = sub.add_parser("metadata-normalize");s.set_defaults(f=cmd_metadata)
    s = sub.add_parser("relations-import");s.set_defaults(f=cmd_relations_import)
    s = sub.add_parser("qa-seed");s.set_defaults(f=cmd_qa_seed)
    s = sub.add_parser("human-audit-export");s.add_argument("--out",default="work/human_review/audit.csv");s.set_defaults(f=cmd_human_export)
    s = sub.add_parser("human-audit-import");s.add_argument("file");s.add_argument("--reviewer",required=True);s.set_defaults(f=cmd_human_import)
    s = sub.add_parser("checkpoint");s.set_defaults(f=cmd_checkpoint)
    s = sub.add_parser("requeue-stale");s.set_defaults(f=cmd_requeue_stale)
    s = sub.add_parser("reverify");s.set_defaults(f=cmd_reverify)
    s = sub.add_parser("contract-rebase");s.add_argument("--reason",required=True);s.add_argument("--reviewer",required=True);s.set_defaults(f=cmd_contract_rebase)
    s = sub.add_parser("units-renormalize");s.add_argument("--apply",action="store_true");s.set_defaults(f=cmd_units_renormalize)
    a = ap.parse_args(argv)
    cfg = Config()
    os.chdir(cfg.root)
    for field in ("out","xlsx"):
        v=getattr(a,field,None)
        if v:
            destination=Path(v).expanduser().resolve()
            if not (destination.is_relative_to(cfg.work_dir.resolve()) or destination.is_relative_to((cfg.root/"exports").resolve())):
                out({"status":"ERROR","error":"output must stay inside project work/ or exports/; original corpus is read-only"});sys.exit(2)
    try:
        a.f(cfg, a)
    except (ValueError,RuntimeError,FileNotFoundError) as exc:
        out({"status":"ERROR","error":str(exc)});sys.exit(2)


if __name__ == "__main__":
    main()
