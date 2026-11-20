"""Author decision 2026-11-13: re-run moderator verification after a re-extraction; queue missing dry-basis checks."""
from pathlib import Path
root = Path.cwd()
sub = root / "tools" / "tfmlib" / "submit.py"
s = sub.read_text(encoding="utf-8")
helper = '''def _reopen_or_follow(ctx, tt):
    # Author decision 2026-11-13: a finished verifier from an earlier pass must run again on new data.
    r = ctx.con.execute("SELECT task_id,status FROM wf_tasks WHERE study_id=? AND task_type=? AND scope_ref=''", (ctx.study, tt)).fetchone()
    if r and r[1] in ("DONE", "FAILED", "CANCELLED"):
        ctx.con.execute("UPDATE wf_tasks SET status='READY',attempts=0,updated_at=? WHERE task_id=?", (now(), r[0]))
        ctx.followups.append(f"{tt}:{r[0]}")
    else:
        ctx.follow(tt)


def maybe_verify(ctx: Ctx) -> None:'''
for old, new in [('def maybe_verify(ctx: Ctx) -> None:', helper),
                 ('if stage=="A":ctx.follow("MODERATORS_VERIFY")', 'if stage=="A":_reopen_or_follow(ctx,"MODERATORS_VERIFY")'),
                 ('else:ctx.follow("MODERATORS_ADJ")', 'else:_reopen_or_follow(ctx,"MODERATORS_ADJ")')]:
    assert s.count(old) == 1, old
    s = s.replace(old, new)
sub.write_text(s, encoding="utf-8")

cli = root / "tools" / "tfm.py"
c = cli.read_text(encoding="utf-8")
func = '''def cmd_requeue_stale(cfg,a):
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
'''
a1 = "def cmd_checkpoint(cfg,a):"
a2 = '    s = sub.add_parser("checkpoint");s.set_defaults(f=cmd_checkpoint)'
assert c.count(a1) == 1 and c.count(a2) == 1 and "cmd_requeue_stale" not in c, "tfm.py anchors"
c = c.replace(a1, func + a1).replace(a2, a2 + '\n    s = sub.add_parser("requeue-stale");s.set_defaults(f=cmd_requeue_stale)')
cli.write_text(c, encoding="utf-8")
print("OK")