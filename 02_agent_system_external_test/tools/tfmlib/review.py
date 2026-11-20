"""Human-in-the-loop: export open questions to CSV, import decisions, apply them."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

from . import numbers as N
from .db import add_issue, changelog, now, rows, tx
from .reconcile import promote, refresh_slots
from .tasks import set_state

COLS = ["review_id", "priority", "study_id", "kind", "ref", "question", "options", "evidence", "decision",
        "decision_note", "decided_by"]


def export(con, out_csv: Path) -> int:
    items = rows(con, "SELECT * FROM wf_review WHERE status='OPEN' ORDER BY priority, study_id, review_id")
    Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        for it in items:
            w.writerow({**it, "decision": "", "decision_note": "", "decided_by": ""})
    return len(items)


def _parse_value(dec: str) -> Dict[str, Any]:
    # VALUE:mean;dispersion_type;dispersion_value;n
    body = dec.split(":", 1)[1]
    parts = [p.strip() for p in body.split(";")]
    parts += [""] * (4 - len(parts))
    return {"mean": N.parse_number(parts[0]), "dispersion_type": parts[1] or "NONE",
            "dispersion_value": N.parse_number(parts[2]) if parts[2] else None,
            "n": N.parse_number(parts[3]) if parts[3] else None}


def apply(con, cfg, in_csv: Path, reviewer: str = "author") -> Dict[str, int]:
    from .submit import Ctx, _schedule_design_extraction, after_scope_ok, maybe_verify  # late import (cycle)
    counts: Dict[str, int] = {}
    touched = set()
    gap_studies = set()
    if Path(in_csv).suffix.lower() == ".json":
        decisions = json.loads(Path(in_csv).read_text(encoding="utf-8-sig"))
    else:
        with open(in_csv, newline="", encoding="utf-8-sig") as fh:
            decisions = [r for r in csv.DictReader(fh) if (r.get("decision") or "").strip()]
    with tx(con):
        for r in decisions:
            item = (rows(con, "SELECT * FROM wf_review WHERE review_id=? AND status='OPEN'", (int(r["review_id"]),)) or [None])[0]
            if not item:
                continue
            dec = r["decision"].strip()
            kind, ref, study = item["kind"], item["ref"], item["study_id"]
            run_id = f"HUMAN-{reviewer}"
            fake_task = {"task_id": f"review-{item['review_id']}", "study_id": study, "task_type": "REVIEW", "scope_ref": ""}
            if kind == "SCOPE":
                if dec == "KEEP_A":
                    con.execute("UPDATE wf_scope SET status='REJECTED' WHERE study_id=?", (study,))
                    ctx = Ctx(con, cfg, fake_task, {}, run_id)
                    after_scope_ok(ctx)
                elif dec.startswith("CONFIRM_"):
                    con.execute("UPDATE wf_scope SET status='CONFIRMED' WHERE study_id=?", (study,))
                    set_state(con, study, "EXCLUDED_SCOPE", run_id, scope_status="EXCLUDED", locked=1,
                              notes=f"moved to class {dec.split('_', 1)[1]} by {reviewer}")
                    con.execute("UPDATE wf_tasks SET status='CANCELLED', updated_at=? WHERE study_id=? AND status IN "
                                "('READY','LEASED')", (now(), study))
            elif kind == "CONFLICT":
                rec_id = int(ref.split("-", 1)[1])
                rec = (rows(con, "SELECT * FROM wf_reconciliation WHERE rec_id=?", (rec_id,)) or [None])[0]
                if rec is None:
                    pass  # a later re-reading replaced this record, so only the question is closed
                elif dec in ("A", "B"):
                    vid = rec["value_id_a"] if dec == "A" else rec["value_id_b"]
                    base = rows(con, "SELECT * FROM wf_values WHERE value_id=?", (vid,))[0]
                    promote(con, cfg, study, rec["record_key"], base, "HUMAN_VERIFIED", [vid], None, run_id)
                    con.execute("UPDATE wf_reconciliation SET status='RESOLVED', resolved_value_id=?, resolved_by='HUMAN', "
                                "updated_at=? WHERE rec_id=?", (vid, now(), rec_id))
                elif dec == "NOT_EXTRACTABLE":
                    con.execute("UPDATE wf_reconciliation SET status='RESOLVED', resolved_value_id=NULL, resolved_by='HUMAN', "
                                "updated_at=? WHERE rec_id=?", (now(), rec_id))
                elif dec.upper().startswith("VALUE:"):
                    vid = rec["value_id_a"] or rec["value_id_b"]
                    base = rows(con, "SELECT * FROM wf_values WHERE value_id=?", (vid,))[0]
                    override = _parse_value(dec)
                    override["notes"] = f"human value ({reviewer}): {r.get('decision_note') or ''}"
                    promote(con, cfg, study, rec["record_key"], base, "HUMAN_VERIFIED", [vid], override, run_id)
                    con.execute("UPDATE wf_reconciliation SET status='RESOLVED', resolved_value_id=?, resolved_by='HUMAN', "
                                "updated_at=? WHERE rec_id=?", (vid, now(), rec_id))
                else:
                    continue
                refresh_slots(con, study)
            elif kind == "DUPLICATE":
                rel_id = int(ref.split("-", 1)[1])
                con.execute("UPDATE wf_relations SET status=? WHERE rel_id=?",
                            ("CONFIRMED" if dec == "CONFIRM" else "REJECTED", rel_id))
            elif kind == "PATCH":
                pid = int(ref.split("-", 1)[1])
                if dec == "ACCEPT":
                    from .maintenance import apply_patch
                    apply_patch(con,cfg,pid,run_id)
                else:
                    con.execute("UPDATE wf_core_patches SET status='REJECTED' WHERE patch_id=?",(pid,))
            elif kind == "DESIGN_GAP":
                if dec != "ACK_SOURCE_LIMIT":
                    raise ValueError(f"review {item['review_id']}: leave a real design gap undecided; only ACK_SOURCE_LIMIT is accepted")
                gap_studies.add(study)
            elif kind == "TRIAGE_UNCLEAR":
                if dec not in ("PRESENT", "ABSENT"):
                    continue
                field = ref.split(":", 1)[1]
                status_col = {"fruit_yield": "yield_status", "dry_biomass": "biomass_status"}[field]
                target = "P2" if con.execute("SELECT 1 FROM wf_triage WHERE study_id=? AND pass='P2'", (study,)).fetchone() else "P1"
                con.execute(f"UPDATE wf_triage SET {field}=? WHERE study_id=? AND pass=?", (dec, study, target))
                con.execute(f"UPDATE wf_study_status SET {status_col}=?,updated_at=? WHERE study_id=?", (dec, now(), study))
            elif kind == "TASK_FAILED":
                con.execute("UPDATE wf_tasks SET status=?, attempts=0, last_error=NULL, updated_at=? WHERE task_id=?",
                            ("READY" if dec == "REQUEUE" else "CANCELLED", now(), ref))
            elif kind == "AUDIT" and dec.upper().startswith("VALUE:"):
                tv_id = int(ref.split("-")[1])
                tv = rows(con, "SELECT * FROM an_target_values WHERE tv_id=?", (tv_id,))[0]
                promote(con, cfg, study, tv["record_key"], tv, "HUMAN_VERIFIED", json.loads(tv["basis_value_ids"] or "[]"),
                        _parse_value(dec), run_id)
            con.execute("UPDATE wf_review SET status='DECIDED', decision=?, decision_note=?, decided_by=?, decided_at=? "
                        "WHERE review_id=?", (dec, r.get("decision_note"), r.get("decided_by") or reviewer, now(),
                                              item["review_id"]))
            changelog(con, run_id, "review", item["review_id"], f"{kind}:{dec}", r.get("decision_note"))
            counts[kind] = counts.get(kind, 0) + 1
            if study:
                touched.add(study)
        for s in gap_studies:
            if con.execute("SELECT 1 FROM wf_review WHERE study_id=? AND kind='DESIGN_GAP' AND status='OPEN' LIMIT 1", (s,)).fetchone():
                continue
            for t in rows(con, "SELECT task_id FROM wf_tasks WHERE study_id=? AND task_type='DESIGN' AND status='READY' AND scope_ref LIKE 'rev-%'", (s,)):
                con.execute("UPDATE wf_tasks SET status='CANCELLED', updated_at=?, "
                            "last_error='design reports classified as source limits; no revision needed' WHERE task_id=?", (now(), t["task_id"]))
                changelog(con, f"HUMAN-{reviewer}", "task", t["task_id"], "CANCELLED_NONSTRUCTURAL_DESIGN_REVISION")
            _schedule_design_extraction(Ctx(con, cfg, {"task_id": "review", "study_id": s, "task_type": "REVIEW", "scope_ref": ""}, {}, f"HUMAN-{reviewer}"), False)
        for s in touched:
            ctx = Ctx(con, cfg, {"task_id": "review", "study_id": s, "task_type": "REVIEW", "scope_ref": ""}, {}, f"HUMAN-{reviewer}")
            maybe_verify(ctx)
    return counts
