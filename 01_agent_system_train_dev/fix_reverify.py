"""Author decision 2026-11-13: run the normal readiness check after an unchanged DESIGN."""
from pathlib import Path
root = Path.cwd()
sub = root / "tools" / "tfmlib" / "submit.py"
s = sub.read_text(encoding="utf-8")
old = ('    if structural or extraction_needed:\n'
       '        set_state(con, study, "EXTRACTING", ctx.run_id)\n'
       '    return len(arms)')
new = ('    if structural or extraction_needed:\n'
       '        set_state(con, study, "EXTRACTING", ctx.run_id)\n'
       '    else:\n'
       '        # Author decision 2026-11-13: unchanged, source-confirmed design -> normal readiness check\n'
       '        maybe_verify(ctx)\n'
       '    return len(arms)')
assert s.count(old) == 1, "submit.py anchor not found"
sub.write_text(s.replace(old, new), encoding="utf-8")

cli = root / "tools" / "tfm.py"
c = cli.read_text(encoding="utf-8")
func = '''def cmd_reverify(cfg,a):
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
'''
a1 = "def cmd_checkpoint(cfg,a):"
a2 = '    s = sub.add_parser("checkpoint");s.set_defaults(f=cmd_checkpoint)'
assert c.count(a1) == 1 and c.count(a2) == 1 and "cmd_reverify" not in c, "tfm.py anchors"
c = c.replace(a1, func + a1).replace(a2, a2 + '\n    s = sub.add_parser("reverify");s.set_defaults(f=cmd_reverify)')
cli.write_text(c, encoding="utf-8")
print("OK")