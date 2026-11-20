"""Work queue with leases (safe for several agents running in parallel)."""
from __future__ import annotations

import datetime as _dt
import random
from typing import Any, Dict, List, Optional, Sequence

from .db import add_review, changelog, now, rows, tx


def reviewable_patches(con, study_id: str) -> List[Dict[str, Any]]:
    """Proposals still needing an agent decision, excluding open human reviews."""
    return rows(con, "SELECT p.* FROM wf_core_patches p WHERE p.study_id=? AND p.status='PROPOSED' "
                     "AND NOT EXISTS (SELECT 1 FROM wf_review r WHERE r.kind='PATCH' "
                     "AND r.ref='patch-' || p.patch_id AND r.status='OPEN') ORDER BY p.patch_id",
                (study_id,))


def _cancel_empty_patch_reviews(con) -> None:
    for r in rows(con, "SELECT DISTINCT study_id FROM wf_tasks "
                       "WHERE task_type='PATCH_REVIEW' AND status='READY'"):
        if reviewable_patches(con, r["study_id"]):
            continue
        for task in rows(con, "SELECT task_id FROM wf_tasks WHERE study_id=? "
                              "AND task_type='PATCH_REVIEW' AND status='READY'", (r["study_id"],)):
            con.execute("UPDATE wf_tasks SET status='CANCELLED', updated_at=?, "
                        "last_error='no reviewable proposal: decided or awaiting human review' WHERE task_id=?",
                        (now(), task["task_id"]))
            changelog(con, None, "task", task["task_id"], "CANCELLED_EMPTY_PATCH_REVIEW")


def _cancel_empty_adjudications(con) -> None:
    for task in rows(con, "SELECT t.task_id FROM wf_tasks t WHERE t.task_type='ADJUDICATE' AND t.status='READY' "
                          "AND NOT EXISTS (SELECT 1 FROM wf_reconciliation r WHERE r.study_id=t.study_id AND r.status='OPEN')"):
        con.execute("UPDATE wf_tasks SET status='CANCELLED', updated_at=?, "
                    "last_error='no open reconciliation conflict' WHERE task_id=?", (now(), task["task_id"]))
        changelog(con, None, "task", task["task_id"], "CANCELLED_EMPTY_ADJUDICATION")


def _claim_conflicts(con, study_id: str, task_type: str) -> bool:
    # DESIGN may invalidate dependent work. Never overlap it with another worker
    # of this study; likewise do not review the same study's patches twice at once.
    return con.execute("SELECT 1 FROM wf_tasks WHERE study_id=? AND status='LEASED' "
                       "AND (?='DESIGN' OR task_type='DESIGN' "
                       "OR (?='PATCH_REVIEW' AND task_type='PATCH_REVIEW')) LIMIT 1",
                       (study_id, task_type, task_type)).fetchone() is not None


def _next_id(con) -> str:
    r = con.execute("SELECT MAX(CAST(SUBSTR(task_id, 3) AS INTEGER)) FROM wf_tasks").fetchone()[0]
    return f"T-{(r or 0) + 1:06d}"


def create_task(con, cfg, study_id: str, task_type: str, scope_ref: str = "",
                priority: Optional[int] = None) -> Optional[str]:
    """Idempotent: returns the task_id (new or existing). Call inside a transaction."""
    if cfg.get("scope.enforce_frozen_ids", True):
        from .sourceqa import frozen_ids
        if str(study_id) not in frozen_ids(cfg):
            raise ValueError("study_id outside frozen 399 scope")
    ex = con.execute("SELECT task_id, status FROM wf_tasks WHERE study_id=? AND task_type=? AND scope_ref=?",
                     (study_id, task_type, scope_ref)).fetchone()
    if ex:
        if ex["status"] in ("CANCELLED",):
            con.execute("UPDATE wf_tasks SET status='READY', updated_at=? WHERE task_id=?", (now(), ex["task_id"]))
        return ex["task_id"]
    if priority is None:
        pr = con.execute("SELECT priority FROM wf_study_status WHERE study_id=?", (study_id,)).fetchone()
        priority = pr[0] if pr else 3
    tid = _next_id(con)
    con.execute("INSERT INTO wf_tasks(task_id, study_id, task_type, agent, scope_ref, status, priority, "
                "created_at, updated_at) VALUES (?,?,?,?,?, 'READY', ?, ?, ?)",
                (tid, study_id, task_type, cfg.agent_for(task_type), scope_ref, priority, now(), now()))
    return tid


def seed_triage(con, cfg, limit: Optional[int] = None, studies: Optional[Sequence[str]] = None) -> int:
    sql = "SELECT study_id FROM wf_study_status WHERE state='NEW'"
    params: List[Any] = []
    if studies:
        sql += " AND study_id IN (%s)" % ",".join("?" for _ in studies)
        params += list(studies)
    sql += " ORDER BY priority, study_id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    n = 0
    with tx(con):
        for r in rows(con, sql, params):
            before = con.execute("SELECT COUNT(*) FROM wf_tasks").fetchone()[0]
            create_task(con, cfg, r["study_id"], "TRIAGE")
            n += con.execute("SELECT COUNT(*) FROM wf_tasks").fetchone()[0] - before
    return n


def expire_leases(con, cfg) -> int:
    max_att = int(cfg.get("queue.max_attempts", 3))
    t = now()
    expired = rows(con, "SELECT * FROM wf_tasks WHERE status='LEASED' AND lease_expires < ?", (t,))
    for task in expired:
        if task["attempts"] >= max_att:
            con.execute("UPDATE wf_tasks SET status='FAILED', lease_owner=NULL, updated_at=?, "
                        "last_error=COALESCE(last_error,'') || ' | lease expired' WHERE task_id=?", (t, task["task_id"]))
            add_review(con, task["study_id"], "TASK_FAILED", task["task_id"],
                       f"{task['task_type']} failed {task['attempts']} times — inspect and re-queue",
                       ["REQUEUE", "CANCEL"], task.get("last_error") or "")
        else:
            con.execute("UPDATE wf_tasks SET status='READY', lease_owner=NULL, lease_expires=NULL, updated_at=? "
                        "WHERE task_id=?", (t, task["task_id"]))
    return len(expired)


def claim(con, cfg, owner: str, agent: Optional[str] = None, task_types: Optional[Sequence[str]] = None,
          limit: int = 1, study_id: Optional[str] = None) -> List[Dict[str, Any]]:
    if limit < 0:
        raise ValueError("claim limit must be nonnegative")
    lease_min = int(cfg.get("queue.lease_minutes", 45))
    out: List[Dict[str, Any]] = []
    with tx(con):
        expire_leases(con, cfg)
        _cancel_empty_patch_reviews(con)
        _cancel_empty_adjudications(con)
        sql = "SELECT * FROM wf_tasks WHERE status='READY'"
        params: List[Any] = []
        if agent and agent != "any":
            sql += " AND agent=?"
            params.append(agent)
        if task_types:
            sql += " AND task_type IN (%s)" % ",".join("?" for _ in task_types)
            params += list(task_types)
        if study_id:
            sql += " AND study_id=?"
            params.append(study_id)
        # locked (closed/excluded) studies get no extraction work; audits and dedup still run on them
        sql += (" AND (task_type IN ('AUDIT','DEDUP','QA_REVIEW','PATCH_REVIEW','TEMPORAL','DRY_BASIS') OR "
                "study_id NOT IN (SELECT study_id FROM wf_study_status WHERE locked=1))")
        sql += " ORDER BY priority, created_at, task_id"
        exp = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(minutes=lease_min)).isoformat(timespec="seconds")
        for task in rows(con, sql, params):
            if len(out) >= int(limit):
                break
            if _claim_conflicts(con, task["study_id"], task["task_type"]):
                continue
            cur = con.execute("UPDATE wf_tasks SET status='LEASED', lease_owner=?, lease_expires=?, "
                              "attempts=attempts+1, updated_at=? WHERE task_id=? AND status='READY'",
                              (owner, exp, now(), task["task_id"]))
            if cur.rowcount:
                task.update(status="LEASED", lease_owner=owner, lease_expires=exp, attempts=task["attempts"] + 1)
                out.append(task)
    return out


def release(con, cfg, task_id: str, error: Optional[str] = None) -> str:
    max_att = int(cfg.get("queue.max_attempts", 3))
    with tx(con):
        t = con.execute("SELECT * FROM wf_tasks WHERE task_id=?", (task_id,)).fetchone()
        if not t:
            raise KeyError(task_id)
        status = "FAILED" if t["attempts"] >= max_att and error else "READY"
        con.execute("UPDATE wf_tasks SET status=?, lease_owner=NULL, lease_expires=NULL, last_error=?, "
                    "updated_at=? WHERE task_id=?", (status, error, now(), task_id))
        if status == "FAILED":
            add_review(con, t["study_id"], "TASK_FAILED", task_id,
                       f"{t['task_type']} failed {t['attempts']} times", ["REQUEUE", "CANCEL"], error or "")
        changelog(con, None, "task", task_id, f"RELEASE->{status}", error)
    return status


def mark_done(con, task_id: str) -> None:
    con.execute("UPDATE wf_tasks SET status='DONE', lease_owner=NULL, lease_expires=NULL, last_error=NULL, "
                "updated_at=? WHERE task_id=?", (now(), task_id))


def set_state(con, study_id: str, state: str, run_id: Optional[str] = None, **fields: Any) -> None:
    sets = ["state=?", "updated_at=?"]
    vals: List[Any] = [state, now()]
    for k, v in fields.items():
        sets.append(f"{k}=?")
        vals.append(v)
    vals.append(study_id)
    con.execute(f"UPDATE wf_study_status SET {', '.join(sets)} WHERE study_id=?", vals)
    changelog(con, run_id, "study", study_id, f"STATE->{state}", fields or None)


def sample_fraction(items: Sequence[str], frac: float, seed: int) -> List[str]:
    rnd = random.Random(seed)
    k = max(1, round(len(items) * frac)) if items and frac > 0 else 0
    return sorted(rnd.sample(list(items), min(k, len(items))))
