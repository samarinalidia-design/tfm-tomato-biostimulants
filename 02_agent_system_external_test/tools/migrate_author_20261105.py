#!/usr/bin/env python3
"""Apply the author decisions of 2026-11-15 (Lidiia Samarina) to the EXTERNAL_TEST queue.

The decisions were given by the author in the Claude Code session of 2026-11-15 and are recorded
with that provenance. Run without --apply for a dry run (prints the plan only).

1. Open review items: SCOPE (T039, T097 -> class C, excluded), TRIAGE_UNCLEAR (missing supplements are
   not included -> ABSENT for T021/T073/T104 dry biomass; T085 dry biomass PRESENT from main-text
   Fig. 3b; T061 fruit yield ABSENT: fruit-cluster weight is not fruit yield), TASK_FAILED T-000951 -> REQUEUE
   (schema now allows organ_scope UNSPECIFIED).
2. Slots whose only source is an unregistered supplement (T104#01/#02) -> NOT_EXTRACTABLE.
3. Temporal: printed final publication date used when no first-online date is printed (config
   assumptions.temporal_final_publication_date) -> ELIGIBLE_TEST_WINDOW with that provenance.
4. Boxplot slots in assumptions.box_centre_as_mean_slots that were closed only for the missing
   author decision are reopened for fresh independent FA/FB readings.
5. Execution contract rebased for the maintenance code/schema/config changes of 2026-11-15.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tfmlib.config import Config  # noqa: E402
from tfmlib.db import changelog, connect, get_meta, init_schema, now, rows, set_meta, tx  # noqa: E402
from tfmlib.tasks import set_state  # noqa: E402

REVIEWER = "Lidiia Samarina"
SOURCE = "author decision given in Claude Code session 2026-11-15"
RUN = "HUMAN-AUTHOR-20261115"

REVIEW_DECISIONS = {
    ("T021", "TRIAGE_UNCLEAR", "T021:dry_biomass"): ("ABSENT", "Dry weight only in unregistered Fig. S9; missing supplements are not included."),
    ("T039", "SCOPE", "T039"): ("CONFIRM_C", "Class C confirmed: no experimentally imposed stress."),
    ("T061", "TRIAGE_UNCLEAR", "T061:fruit_yield"): ("ABSENT", "Fruit-cluster weight and fruit set are not fruit-yield mass; no total yield per plant or area."),
    ("T073", "TRIAGE_UNCLEAR", "T073:dry_biomass"): ("ABSENT", "Dry weights only in unregistered supplementary figures; missing supplements are not included."),
    ("T085", "TRIAGE_UNCLEAR", "T085:dry_biomass"): ("PRESENT", "Main-text Fig. 3b reports dry weight (organ not printed -> organ_scope UNSPECIFIED)."),
    ("T085", "TASK_FAILED", "T-000951"): ("REQUEUE", "Schema now includes organ_scope UNSPECIFIED; resubmit the complete Fig. 3b reading."),
    ("T097", "SCOPE", "T097"): ("CONFIRM_C", "Class C confirmed: tomato bioinoculant without imposed stress."),
    ("T104", "TRIAGE_UNCLEAR", "T104:dry_biomass"): ("ABSENT", "Dry mass only in unregistered Figs S1/S2; missing supplements are not included."),
}
SUPPLEMENT_ONLY_SLOTS = ["T104#01", "T104#02"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    cfg = Config()
    con = connect(cfg.db_path)
    init_schema(con)
    plan = {"reviews": [], "closed_slots": [], "temporal": [], "reopened_slots": [], "studies_reopened": [], "contract": None}

    # 1. review decisions
    decisions = []
    for (study, kind, ref), (dec, note) in REVIEW_DECISIONS.items():
        it = rows(con, "SELECT review_id FROM wf_review WHERE study_id=? AND kind=? AND ref=? AND status='OPEN'", (study, kind, ref))
        for r in it:
            decisions.append({"review_id": r["review_id"], "decision": dec, "decision_note": f"{note} ({SOURCE})", "decided_by": REVIEWER})
            plan["reviews"].append({"review_id": r["review_id"], "study_id": study, "kind": kind, "decision": dec})

    # 2. supplement-only slots
    for sid in SUPPLEMENT_ONLY_SLOTS:
        s = rows(con, "SELECT slot_id,status FROM wf_target_slots WHERE slot_id=?", (sid,))
        if s and s[0]["status"] not in ("VERIFIED", "VERIFIED_PARTIAL", "NOT_EXTRACTABLE"):
            plan["closed_slots"].append(sid)

    # 3. temporal
    tfp = cfg.get("assumptions.temporal_final_publication_date") or {}
    for study, info in tfp.items():
        tr = rows(con, "SELECT * FROM wf_temporal_review WHERE study_id=?", (study,))
        if tr and tr[0]["eligibility"] == "UNRESOLVED_QUARANTINE":
            plan["temporal"].append({"study_id": study, **info})

    # 4. boxplot slots
    for sid in cfg.get("assumptions.box_centre_as_mean_slots") or []:
        s = rows(con, "SELECT * FROM wf_target_slots WHERE slot_id=?", (sid,))
        if not s:
            continue
        s = s[0]
        reason = s.get("not_extractable_reason") or ""
        if s["status"] == "NOT_EXTRACTABLE" and ("BOX" in reason.upper()) and "DUPLICATE_SLOT" not in reason.split("|")[0]:
            plan["reopened_slots"].append(sid)
    plan["studies_reopened"] = sorted({s.split("#")[0] for s in plan["reopened_slots"]})

    from tfmlib.config import execution_contract_hash
    old, new = get_meta(con, "execution_contract_hash"), execution_contract_hash(cfg)
    plan["contract"] = {"old": old, "new": new, "changed": old != new}

    if not a.apply:
        print(json.dumps({"dry_run": True, **plan}, ensure_ascii=False, indent=1))
        return

    out_dir = cfg.root / "work" / "human_review"
    out_dir.mkdir(parents=True, exist_ok=True)
    dec_path = out_dir / "author_decisions_20261115.json"
    dec_path.write_text(json.dumps(decisions, ensure_ascii=False, indent=1), encoding="utf-8")
    from tfmlib.review import apply as review_apply
    review_counts = review_apply(con, cfg, dec_path, REVIEWER)

    with tx(con):
        for sid in plan["closed_slots"]:
            reason = ("SOURCE_NOT_REGISTERED: the only source is a supplement cited by the article but not registered in "
                      "source_manifest_TEST.csv (Figs S1/S2); author decision 2026-11-15: missing supplements are not included")
            con.execute("UPDATE wf_target_slots SET status='NOT_EXTRACTABLE', not_extractable_reason=? WHERE slot_id=?", (reason, sid))
            con.execute("UPDATE wf_tasks SET status='CANCELLED', last_error='author decision 2026-11-15: unregistered supplement not included', "
                        "updated_at=? WHERE scope_ref=? AND status IN ('READY','LEASED','FAILED')", (now(), sid))
            changelog(con, RUN, "slot", sid, "NOT_EXTRACTABLE_SUPPLEMENT_NOT_INCLUDED", {"reviewer": REVIEWER, "source": SOURCE})

        for t in plan["temporal"]:
            tr = rows(con, "SELECT * FROM wf_temporal_review WHERE study_id=?", (t["study_id"],))[0]
            ev = (tr["evidence"] or "") + (f" || AUTHOR DECISION 2026-11-15 ({REVIEWER}): no first-online date is printed in the original; "
                                         f"the printed final publication is used instead: {t['issue']} (year {t['year']}). "
                                         f"Retained as TEST, not quarantined." + (f" Note: {t['note']}." if t.get("note") else ""))
            con.execute("UPDATE wf_temporal_review SET eligibility='ELIGIBLE_TEST_WINDOW', evidence=?, run_id=?, created_at=? WHERE study_id=?",
                        (ev, RUN, now(), t["study_id"]))
            changelog(con, RUN, "temporal", t["study_id"], "ELIGIBLE_BY_FINAL_PUBLICATION_DATE", t)

        for sid in plan["reopened_slots"]:
            con.execute("UPDATE wf_target_slots SET status='OPEN', not_extractable_reason=NULL WHERE slot_id=?", (sid,))
            con.execute("DELETE FROM wf_slot_pass WHERE slot_id=?", (sid,))
            con.execute("UPDATE wf_tasks SET status='READY', attempts=0, last_error=NULL, updated_at=? WHERE scope_ref=? "
                        "AND task_type IN ('FIGURE_A','FIGURE_B')", (now(), sid))
            changelog(con, RUN, "slot", sid, "REOPENED_BOX_CENTRE_AS_MEAN", {"reviewer": REVIEWER, "source": SOURCE})
        for study in plan["studies_reopened"]:
            set_state(con, study, "EXTRACTING", RUN, locked=0,
                      notes="author decision 2026-11-15: boxplot centre line used as mean; slots re-read")

    # T104: re-evaluate after its open slots were closed
    from tfmlib.submit import Ctx, maybe_verify
    with tx(con):
        st = con.execute("SELECT state FROM wf_study_status WHERE study_id='T104'").fetchone()
        if st and st[0] not in ("CLOSED", "EXCLUDED_SCOPE", "NO_TARGET_CONFIRMED"):
            maybe_verify(Ctx(con, cfg, {"task_id": "", "study_id": "T104", "task_type": "REVIEW", "scope_ref": ""}, {}, RUN))

    if plan["contract"]["changed"]:
        leased = con.execute("SELECT COUNT(*) FROM wf_tasks WHERE status='LEASED'").fetchone()[0]
        if leased:
            plan["contract"]["rebased"] = False
            plan["contract"]["error"] = f"{leased} leased tasks; release them and rerun"
        else:
            with tx(con):
                set_meta(con, "execution_contract_hash", new)
                changelog(con, "HUMAN-CONTRACT-REBASE", "contract", "execution_contract_hash", "REBASE",
                          {"old": old, "new": new, "reviewer": REVIEWER,
                           "reason": "maintenance 2026-11-15 instructed by the author: export scope-manifest path, organ_scope UNSPECIFIED, "
                                     "TIFF and text-table .xls source views, DRY_BASIS seeding in qa-seed, C001 pooling by comparable metric, "
                                     "author decisions in config (box centre, temporal final publication date, missing supplements, contradiction priority)"})
            plan["contract"]["rebased"] = True
    print(json.dumps({"applied": True, "review_counts": review_counts, **plan}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
