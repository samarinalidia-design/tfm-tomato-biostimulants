"""Validation of agent submissions and the follow-up task graph.

A submission is either ACCEPTED (written in one transaction, task DONE,
follow-up tasks created) or REJECTED with precise, actionable messages (the
task stays LEASED so the same agent can fix and resubmit).
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from jsonschema import Draft202012Validator

from . import numbers as N
from . import units as U
from .context import SCHEMA_FOR, source_texts
from .db import (ColumnResolver, add_issue, add_review, changelog, new_run_id, now, q, rows, sha256_file,
                 sha256_text, tx)
from .figures import CalibrationError, calibration_status, fit_axis, image_sha256, image_size, point_values
from .reconcile import ATTRS, promote, reconcile, record_key, refresh_slots, strip_irrelevant
from .stats import sd_from
from .tasks import create_task, mark_done, set_state

LNRR_ENDPOINTS = {"FRUIT_YIELD", "DRY_BIOMASS", "FRUIT_NUMBER", "MEAN_FRUIT_MASS", "WATER_PRODUCTIVITY"}


class Reject(Exception):
    def __init__(self, errors: List[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


_SCHEMAS: Dict[str, Draft202012Validator] = {}


def validator(cfg, name: str) -> Draft202012Validator:
    if name not in _SCHEMAS:
        sch = json.loads((cfg.root / "schema" / "json" / f"{name}.schema.json").read_text(encoding="utf-8"))
        _SCHEMAS[name] = Draft202012Validator(sch)
    return _SCHEMAS[name]


def agent_meta(cfg, agent: str) -> Tuple[Optional[str], Optional[str]]:
    f = cfg.agent_file(agent)
    if not f.exists():
        return None, None
    txt = f.read_text(encoding="utf-8")
    m = re.search(r"^model:\s*(\S+)", txt, re.M)
    return (m.group(1) if m else None), sha256_text(txt, 12)


class Ctx:
    """Per-submission context: collects warnings and writes WARN issues."""

    def __init__(self, con, cfg, task, data, run_id):
        self.con, self.cfg, self.task, self.d, self.run_id = con, cfg, task, data, run_id
        self.study = task["study_id"]
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.followups: List[str] = []

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, rule: str, msg: str, entity: str = "submission", eid: Any = None) -> None:
        self.warnings.append(f"{rule}: {msg}")
        add_issue(self.con, rule, "WARN", self.study, entity, eid or self.task["task_id"], msg, self.run_id)

    def check(self) -> None:
        if self.errors:
            raise Reject(self.errors)

    def follow(self, task_type: str, scope_ref: str = "") -> None:
        tid = create_task(self.con, self.cfg, self.study, task_type, scope_ref)
        self.followups.append(f"{task_type}:{tid}")


# ------------------------------------------------------------------ entry
def submit(con, cfg, task_id: str, path: Path) -> Dict[str, Any]:
    task = (rows(con, "SELECT * FROM wf_tasks WHERE task_id=?", (task_id,)) or [None])[0]
    if task and cfg.get("scope.enforce_frozen_ids", True):
        from .sourceqa import frozen_ids
        if task["study_id"] not in frozen_ids(cfg):
            return {"status":"REJECTED","errors":["study_id outside the frozen scope manifest"]}
    if not task:
        return {"status": "ERROR", "errors": [f"unknown task {task_id}"]}
    if task["status"] == "DONE":
        try: digest=sha256_text(Path(path).read_text(encoding="utf-8-sig"))
        except OSError: digest=None
        prev=rows(con,"SELECT * FROM wf_runs WHERE task_id=? AND status='ACCEPTED' ORDER BY rowid DESC LIMIT 1",(task_id,))
        if prev and prev[0]["output_sha256"]==digest:
            return {"status":"ACCEPTED","run_id":prev[0]["run_id"],"idempotent_replay":True,"warnings":[],"followups":[]}
    if task["status"] not in ("LEASED", "READY"):
        return {"status": "ERROR", "errors": [f"task {task_id} is {task['status']} — claim a new task instead"]}
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8-sig")
        data = json.loads(raw)
    except Exception as exc:
        return {"status": "REJECTED", "errors": [f"cannot read JSON {path}: {exc}"]}
    vname = SCHEMA_FOR[task["task_type"]]
    errs = []
    for e in sorted(validator(cfg, vname).iter_errors(data), key=lambda e: list(e.absolute_path)):
        loc = "/".join(str(p) for p in e.absolute_path) or "(root)"
        errs.append(f"schema {vname} at {loc}: {e.message[:300]}")
    if isinstance(data, dict):
        if data.get("task_id") != task_id:
            errs.append(f"task_id must be {task_id}")
        if str(data.get("study_id")) != str(task["study_id"]):
            errs.append(f"study_id must be {task['study_id']}")
        if data.get("agent") not in (task["agent"],):
            errs.append(f"agent must be {task['agent']}")
    run_id = new_run_id("R")
    alias, psha = agent_meta(cfg, task["agent"])
    model_id = data.get("model_id") if isinstance(data, dict) else None

    def record(status: str, msg: str, n_items: int = 0) -> None:
        con.execute("INSERT INTO wf_runs(run_id, task_id, agent, model_alias, model_id, prompt_sha, schema_version, "
                    "code_version, started_at, finished_at, status, output_sha256, n_items, message) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (run_id, task_id, task["agent"], alias, model_id, psha, cfg.get("schema_version"),
                     __import__("tfmlib").__version__, task.get("updated_at"), now(), status,
                     sha256_text(raw), n_items, msg[:4000]))

    if errs:
        con.execute("BEGIN IMMEDIATE")
        record("REJECTED", json.dumps(errs, ensure_ascii=False))
        con.execute("COMMIT")
        return {"status": "REJECTED", "run_id": run_id, "errors": errs}
    handler = HANDLERS[task["task_type"]]
    ctx = None
    try:
        with tx(con):
            ctx = Ctx(con, cfg, task, data, run_id)
            n_items = handler(ctx) or 0
            record("ACCEPTED", json.dumps({"warnings": ctx.warnings, "followups": ctx.followups},
                                          ensure_ascii=False), n_items)
            mark_done(con, task_id)
            changelog(con, run_id, "task", task_id, "DONE", {"n_items": n_items})
    except Reject as rj:
        con.execute("BEGIN IMMEDIATE")
        record("REJECTED", json.dumps(rj.errors, ensure_ascii=False))
        con.execute("COMMIT")
        return {"status": "REJECTED", "run_id": run_id, "errors": rj.errors,
                "warnings": ctx.warnings if ctx else []}
    return {"status": "ACCEPTED", "run_id": run_id, "warnings": ctx.warnings, "followups": ctx.followups}


# ----------------------------------------------------------------- helpers
def _study_has_supplements(con, cfg, study_id: str) -> bool:
    cr = ColumnResolver(con, cfg.column_map)
    sid, role = cr.get("files", "study_id"), cr.get("files", "role")
    if not sid or not role:
        return False
    return con.execute(f"SELECT COUNT(*) FROM files WHERE CAST({q(sid)} AS TEXT)=? AND UPPER({q(role)}) LIKE 'SUPP%'",
                       (study_id,)).fetchone()[0] > 0


def _needs_second_triage(con, cfg, study_id: str) -> bool:
    st = con.execute("SELECT priority FROM wf_study_status WHERE study_id=?", (study_id,)).fetchone()
    if st and st[0] == 0 and cfg.get("queue.second_triage_always_if_title_signal", True):
        return True
    frac = float(cfg.get("queue.second_triage_fraction_no_target", 1.0))
    h = int(hashlib.sha256(f"{cfg.get('queue.random_seed', 1)}:{study_id}".encode()).hexdigest()[:8], 16)
    return (h / 0xFFFFFFFF) < frac


def _route(con, cfg, slot: Dict[str, Any]) -> str:
    if slot["endpoint"] in (cfg.get("targets.secondary_productivity") or []) and \
            not cfg.get("targets.extract_secondary_productivity", True):
        return "SKIP_NOT_IN_SCOPE"
    if slot["source_kind"] != "FIGURE":
        return "EXTRACT"
    if slot.get("duplicate_of_locator"):
        used = con.execute("SELECT COUNT(*) FROM wf_target_slots WHERE route='TWIN_VALIDATION'").fetchone()[0]
        return "TWIN_VALIDATION" if used < int(cfg.get("queue.figure_twin_validation_max", 15)) \
            else "SKIP_DUPLICATE_OF_TABLE"
    return "FIGURE"


def _insert_slots(ctx: Ctx, slots: List[Dict[str, Any]]) -> int:
    con = ctx.con
    k0 = con.execute("SELECT COUNT(*) FROM wf_target_slots WHERE study_id=?", (ctx.study,)).fetchone()[0]
    n = 0
    for i, s in enumerate(slots, start=1):
        if con.execute("SELECT 1 FROM wf_target_slots WHERE study_id=? AND endpoint=? AND source_file_id=? AND locator_label=?",(ctx.study,s["endpoint"],s.get("source_file_id"),s["locator_label"])).fetchone():continue
        sid = f"{ctx.study}#{k0 + i:02d}"
        route = _route(con, ctx.cfg, s)
        con.execute("INSERT INTO wf_target_slots(slot_id, study_id, endpoint, source_kind, source_file_id, locator_label, "
                    "page, figure_item_id, expected_n_values, has_dispersion, description, route, status, "
                    "created_run_id, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'OPEN', ?, ?)",
                    (sid, ctx.study, s["endpoint"], s["source_kind"], s.get("source_file_id"), s["locator_label"],
                     s.get("page"), s.get("figure_item_id"), s["expected_n_values"], s["has_dispersion"],
                     s["description"] + (f" [duplicate of {s['duplicate_of_locator']}]" if s.get("duplicate_of_locator") else ""),
                     route, ctx.run_id, now()))
        n += 1
    return n


def after_scope_ok(ctx: Ctx) -> None:
    con = ctx.con
    work = con.execute("SELECT COUNT(*) FROM wf_target_slots WHERE study_id=? AND route IN "
                       "('EXTRACT','FIGURE','TWIN_VALIDATION')", (ctx.study,)).fetchone()[0]
    p1=(rows(con,"SELECT * FROM wf_triage WHERE study_id=? AND pass='P1'",(ctx.study,)) or [{}])[0]
    primary_recheck=p1.get("fruit_yield") in ("ABSENT", "UNCLEAR") and ctx.cfg.get("queue.primary_absence_requires_second_review", True)
    # Biomass-era extraction must never stand in for a primary-yield search.
    # Recheck a negative/unclear PRIMARY target even when biomass is available.
    if work and primary_recheck and not con.execute("SELECT 1 FROM wf_triage WHERE study_id=? AND pass='P2'",(ctx.study,)).fetchone():
        ctx.follow("TRIAGE_2ND")
    if work:
        ctx.follow("DESIGN")
        set_state(con, ctx.study, "TRIAGED", ctx.run_id, scope_status="OK")
    elif (primary_recheck or _needs_second_triage(con, ctx.cfg, ctx.study)) and not con.execute(
            "SELECT 1 FROM wf_triage WHERE study_id=? AND pass='P2'", (ctx.study,)).fetchone():
        ctx.follow("TRIAGE_2ND")
        set_state(con, ctx.study, "NO_TARGET_PENDING", ctx.run_id, scope_status="OK")
    else:
        set_state(con, ctx.study, "NO_TARGET_CONFIRMED", ctx.run_id, scope_status="OK")


def _design_sets(con, study: str) -> Tuple[Set[str], Set[str]]:
    arms = {r["arm_key"] for r in rows(con, "SELECT arm_key FROM wf_design_arms WHERE study_id=?", (study,))}
    tps = {r["timepoint_key"] for r in rows(con, "SELECT timepoint_key FROM wf_design_timepoints WHERE study_id=?", (study,))}
    return arms, tps


def _endpoint_attrs(ctx: Ctx, v: Dict[str, Any], label: str) -> None:
    spec = ctx.cfg.endpoint_spec(v["endpoint"])
    for a in spec.get("required_attrs", []):
        if v.get(a) in (None, ""):
            ctx.err(f"{label}: {v['endpoint']} requires '{a}' (use UNSPECIFIED only if the paper truly does not say)")
        elif v.get(a) == "UNSPECIFIED":
            ctx.warn("V010", f"{label}: {a}=UNSPECIFIED", "value", label)
    dropped = strip_irrelevant(v)
    if dropped:
        ctx.warn("V010", f"{label}: {dropped} do not apply to {v['endpoint']} — ignored", "value", label)


def _unit_check(ctx: Ctx, v: Dict[str, Any], label: str) -> Tuple[Optional[str], Optional[float]]:
    unit_norm, fac, den = U.normalize(v.get("unit_raw") or "", v["endpoint"])
    if unit_norm is None:
        ctx.warn("V008", f"{label}: unit '{v.get('unit_raw')}' not recognised for {v['endpoint']} — kept raw", "value", label)
    elif v["endpoint"] == "FRUIT_YIELD" and den and v.get("denominator") not in (den, "UNSPECIFIED", None, "OTHER"):
        ctx.err(f"{label}: unit '{v.get('unit_raw')}' implies {den} but denominator={v.get('denominator')}")
    return unit_norm, fac


def _numeric_checks(ctx: Ctx, v: Dict[str, Any], label: str) -> None:
    dt, dv, n = v.get("dispersion_type"), v.get("dispersion_value"), v.get("n")
    if dt in ("SD", "SE", "CI95") and dv is None:
        ctx.err(f"{label}: dispersion_type={dt} needs dispersion_value (for CI95 give the HALF-width)")
    if dt in ("NONE", "UNCLEAR") and dv is not None:
        ctx.err(f"{label}: dispersion_value given but dispersion_type={dt}")
    if dv is not None and dv < 0:
        ctx.err(f"{label}: dispersion_value < 0")
    if n is not None and n <= 0:
        ctx.err(f"{label}: n must be > 0")
    if n is not None and n > float(ctx.cfg.get("validation.n_max_plausible", 500)):
        ctx.warn("V005", f"{label}: n={n} is implausibly large (technical replicates counted?)", "value", label)
    if n is None:
        ctx.warn("V005", f"{label}: n missing — value will not be usable in weighted analyses", "value", label)
    if v.get("mean") is not None and v["mean"] <= 0 and v["endpoint"] in LNRR_ENDPOINTS:
        ctx.warn("V003", f"{label}: mean <= 0 — lnRR not computable", "value", label)
    if v["endpoint"].startswith("BIOTIC_"):
        m=v.get("outcome_context")
        if not m or not v.get("context_key"):ctx.err(f"{label}: biotic outcome needs explicit scale/assay/pathogen/context and prespecified estimand")
        else:
            binary=v["endpoint"] in ("BIOTIC_INCIDENCE","BIOTIC_MORTALITY","BIOTIC_SURVIVAL")
            if binary:
                if m.get("effect_metric") not in ("LOG_RR_BINARY","LOG_OR"):ctx.err("binary endpoint requires a separate log-RR/log-OR estimand")
                if m.get("events") is None or m.get("total") is None:ctx.warn("B006","binary events/denominator not reported; preserve raw value with no binomial effect/variance")
                elif m["events"]>m["total"]:ctx.err("binary events exceed reported denominator")
            if m.get("scale_type")=="ORDINAL" and m.get("effect_metric")!="DESCRIPTIVE_ORDINAL":ctx.err("ordinal/root-gall scores stay descriptive; no forced lnRR or continuous MD")
            if m.get("effect_metric")=="MD" and m.get("scale_type")!="CONTINUOUS":ctx.err("MD requires a compatible continuous scale")
            if m.get("effect_metric")=="lnRR" and v.get("mean",0)<=0:ctx.warn("V003","nonpositive biotic mean; no pseudocount")
    sd = sd_from(dt, dv, n)
    if sd is not None and v.get("mean") and v["mean"] > 0 and sd / v["mean"] > float(ctx.cfg.get("validation.cv_warn", 1.5)):
        ctx.warn("V009", f"{label}: CV={sd / v['mean']:.2f} — check SD vs SE vs variance", "value", label)


def _insert_value(ctx: Ctx, v: Dict[str, Any], pass_: str, unit_norm, fac, source_check: str,
                  extra: Optional[Dict[str, Any]] = None) -> int:
    rk = record_key(v)
    disp = v.get("dispersion_value")
    vals = dict(run_id=ctx.run_id, task_id=ctx.task["task_id"], pass_=pass_, study_id=ctx.study, slot_id=v.get("slot_id"),
                record_key=rk, arm_key=v["arm_key"], endpoint=v["endpoint"],
                yield_scope=v.get("yield_scope"), mass_basis=v.get("mass_basis"), denominator=v.get("denominator"),
                harvest_window=v.get("harvest_window"), organ_scope=v.get("organ_scope"),
                timepoint_key=v["timepoint_key"], mean=v["mean"], dispersion_type=v.get("dispersion_type"),
                dispersion_value=disp,
                dispersion_type_reported=v.get("dispersion_type_reported",v.get("dispersion_type")),
                dispersion_basis=v.get("dispersion_basis") or ("NOT_REPORTED" if v.get("dispersion_type") in ("NONE","UNCLEAR",None) else "SOURCE_REPORTED"),
                error_bar_status=v.get("error_bar_status"), error_bar_bounds_json=v.get("error_bar_bounds_json"),
                error_bar_relative_uncertainty=v.get("error_bar_relative_uncertainty"),
                n=v.get("n"), n_unit=v.get("n_unit"), n_source=v.get("n_source"),
                unit_raw=v.get("unit_raw"), unit_norm=unit_norm,
                mean_norm=v["mean"] * fac if fac is not None else None,
                disp_norm=disp * fac if (fac is not None and disp is not None) else None,
                sig_letters=v.get("sig_letters"), source_kind=v.get("source_kind"),
                source_file_id=v.get("source_file_id"), page=v.get("page"), locator=v.get("locator"),
                verbatim=v.get("verbatim"), figure_item_id=v.get("figure_item_id"), calib_id=None, axis_range=None,
                source_check=source_check, outcome_context_json=json.dumps(v.get("outcome_context"),sort_keys=True),context_key=v.get("context_key"),ci_json=json.dumps(v.get("ci")), receipt_id=v.get("receipt_id"), source_cell=v.get("source_cell"), confidence=v.get("confidence"), notes=v.get("notes"), created_at=now())
    if extra:
        vals.update(extra)
    cols = [("pass" if k == "pass_" else k) for k in vals]
    ctx.con.execute(f"INSERT INTO wf_values({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                    list(vals.values()))
    return ctx.con.execute("SELECT last_insert_rowid()").fetchone()[0]


def _slot_pass(ctx: Ctx, slot_status: List[Dict[str, Any]], pass_: str) -> None:
    for s in slot_status:
        ctx.con.execute("INSERT INTO wf_slot_pass(slot_id, pass, status, reason, n_values, run_id, created_at) "
                        "VALUES (?,?,?,?,?,?,?) ON CONFLICT(slot_id, pass) DO UPDATE SET status=excluded.status, "
                        "reason=excluded.reason, n_values=excluded.n_values, run_id=excluded.run_id, "
                        "created_at=excluded.created_at",
                        (s["slot_id"], pass_, s["status"], s.get("reason"), s["n_values"], ctx.run_id, now()))


def ensure_adjudication(ctx: Ctx) -> None:
    con = ctx.con
    open_n = con.execute("SELECT COUNT(*) FROM wf_reconciliation WHERE study_id=? AND status='OPEN'",
                         (ctx.study,)).fetchone()[0]
    if not open_n:
        return
    pending = con.execute("SELECT COUNT(*) FROM wf_tasks WHERE study_id=? AND task_type='ADJUDICATE' AND "
                          "status IN ('READY','LEASED')", (ctx.study,)).fetchone()[0]
    if not pending:
        k = con.execute("SELECT COUNT(*) FROM wf_tasks WHERE study_id=? AND task_type='ADJUDICATE'",
                        (ctx.study,)).fetchone()[0]
        ctx.follow("ADJUDICATE", f"adj-{k + 1}")
    set_state(con, ctx.study, "ADJUDICATION", ctx.run_id)


def _reopen_or_follow(ctx, tt):
    # Author decision 2026-11-13: a finished verifier from an earlier pass must run again on new data.
    r = ctx.con.execute("SELECT task_id,status FROM wf_tasks WHERE study_id=? AND task_type=? AND scope_ref=''", (ctx.study, tt)).fetchone()
    if r and r[1] in ("DONE", "FAILED", "CANCELLED"):
        ctx.con.execute("UPDATE wf_tasks SET status='READY',attempts=0,updated_at=? WHERE task_id=?", (now(), r[0]))
        ctx.followups.append(f"{tt}:{r[0]}")
    else:
        ctx.follow(tt)


def maybe_verify(ctx: Ctx) -> None:
    con, study = ctx.con, ctx.study
    st = con.execute("SELECT state FROM wf_study_status WHERE study_id=?", (study,)).fetchone()
    if not st or st[0] in ("CLOSED", "EXCLUDED_SCOPE", "NO_TARGET_CONFIRMED", "SCOPE_REVIEW"):
        return
    refresh_slots(con, study)
    # the submitting task is still LEASED until the transaction commits -> exclude it
    busy = con.execute("SELECT COUNT(*) FROM wf_tasks WHERE study_id=? AND status IN ('READY','LEASED') AND "
                       "task_type IN ('DESIGN','EXTRACT_A','EXTRACT_B','FIGURE_A','FIGURE_B','ADJUDICATE','MODERATORS_VERIFY','MODERATORS_ADJ') AND task_id<>?",
                       (study, ctx.task.get("task_id", ""))).fetchone()[0]
    if busy:
        return
    unresolved = con.execute("SELECT COUNT(*) FROM wf_reconciliation WHERE study_id=? AND status IN ('OPEN','ESCALATED')",
                             (study,)).fetchone()[0]
    if unresolved:
        set_state(con, study, "ADJUDICATION", ctx.run_id)
        return
    open_slots = con.execute("SELECT COUNT(*) FROM wf_target_slots WHERE study_id=? AND route IN "
                             "('EXTRACT','FIGURE','TWIN_VALIDATION') AND status NOT IN ('VERIFIED','VERIFIED_PARTIAL','NOT_EXTRACTABLE')",
                             (study,)).fetchone()[0]
    if open_slots:
        return
    n_ver = con.execute("SELECT COUNT(*) FROM an_target_values WHERE study_id=?", (study,)).fetchone()[0]
    if n_ver:
        todo = []
        for tt in ("MODERATORS", "ROB"):
            r = con.execute("SELECT task_id, status FROM wf_tasks WHERE study_id=? AND task_type=?", (study, tt)).fetchone()
            if not r:
                ctx.follow(tt)
                todo.append(tt)
            elif r[1] != "DONE" and r[0] != ctx.task.get("task_id"):
                todo.append(tt)
        if todo:
            set_state(con, study, "EXTRACTING", ctx.run_id)
            return
    set_state(con, study, "VERIFIED", ctx.run_id,
              notes=None if n_ver else "targets located but none extractable (see slot reasons)")


def _counterpart_done(con, study: str, task_type: str, scope_ref: str) -> bool:
    r = con.execute("SELECT status FROM wf_tasks WHERE study_id=? AND task_type=? AND scope_ref=?",
                    (study, task_type, scope_ref)).fetchone()
    return bool(r and r[0] == "DONE")


# ---------------------------------------------------------------- handlers
def h_triage(ctx: Ctx) -> int:
    d, con = ctx.d, ctx.con
    expected = "P1" if ctx.task["task_type"] == "TRIAGE" else "P2"
    if d["pass"] != expected:
        ctx.err(f"pass must be {expected} for {ctx.task['task_type']}")
    t, slots, ne = d["targets"], d["slots"], d["negative_evidence"]
    from .sourceqa import check_receipt
    cr = ColumnResolver(con, ctx.cfg.column_map)
    sc,fc = cr.get("files","study_id"),cr.get("files","active_file_id")
    originals = {str(r["f"]) for r in rows(con,f"SELECT {q(fc)} f FROM files WHERE CAST({q(sc)} AS TEXT)=?",(ctx.study,))}
    supplied = {r["source_file_id"] for r in d["source_checks"]}
    if supplied != originals: ctx.err(f"source_checks must cover exact file inventory; missing={originals-supplied}; extra={supplied-originals}")
    for review in d["source_checks"]:
        if review["disposition"] in ("CHECKED","IRRELEVANT") and not review["receipt_ids"]:
            ctx.err("source_checks: original receipt required even when a supplement is irrelevant")
        for rid in review["receipt_ids"]:
            try: check_receipt(con,ctx.cfg,ctx.study,review["source_file_id"],rid)
            except ValueError as exc: ctx.err(str(exc))
        con.execute("INSERT OR REPLACE INTO wf_source_audit VALUES(?,?,?,?,?,?,?,?)",(ctx.study,review["source_file_id"],review["disposition"],json.dumps(review["receipt_ids"]),review["docling_findings"],review["relevance"],ctx.run_id,now()))
    for a in d["asset_inventory"]:
        if a["source_file_id"] not in originals: ctx.err("asset inventory source outside study")
        if a["relevance"]=="IRRELEVANT" and a["disposition"]!="NOT_ELIGIBLE": ctx.err("irrelevant assets must be NOT_ELIGIBLE")
        con.execute("INSERT OR REPLACE INTO wf_asset_inventory VALUES(?,?,?,?,?,?,?,?)",(ctx.study,a["asset_key"],a["source_file_id"],a["locator"],a["relevance"],a["disposition"],a["reason"],ctx.run_id))
    if any(r["disposition"] in ("MISSING","UNREADABLE") for r in d["source_checks"]):
        ctx.err("source inaccessible: cannot claim absence or completion; recover original or escalate as one source-access blocker")
    for ep, key in (("FRUIT_YIELD", "fruit_yield"), ("DRY_BIOMASS", "dry_biomass")):
        has = any(s["endpoint"] == ep for s in slots)
        if t[key] == "PRESENT" and not has:
            ctx.err(f"targets.{key}=PRESENT but no slot with endpoint {ep} — add one slot per table/figure/text location")
        if t[key] == "ABSENT" and has:
            ctx.err(f"slot with endpoint {ep} but targets.{key}=ABSENT")
    if any(t[k] != "PRESENT" for k in ("fruit_yield", "dry_biomass")):
        if len(ne["sections_read"]) < 2:
            ctx.err("negative_evidence.sections_read: list the sections you actually read (>= 2) before declaring a target ABSENT/UNCLEAR")
        if len(ne["search_terms"]) < 5:
            ctx.err("negative_evidence.search_terms: >= 5 terms (e.g. yield, fruit weight, harvest, dry weight, biomass, DW)")
        if _study_has_supplements(con, ctx.cfg, ctx.study) and not ne["supplements_checked"]:
            ctx.err("this study has supplements in `files` — list the ones checked in negative_evidence.supplements_checked")
    for k in ("fruit_yield", "dry_biomass"):
        if t[k] == "UNCLEAR":
            if k == "fruit_yield" and expected == "P1" and ctx.cfg.get("queue.primary_absence_requires_second_review", True):
                ctx.warn("T001", "fruit_yield=UNCLEAR — independent original-source search precedes human review")
                continue
            ctx.warn("T001", f"{k}=UNCLEAR — sent to human review")
            add_review(con, ctx.study, "TRIAGE_UNCLEAR", f"{ctx.study}:{k}",
                       f"Triage could not decide whether {k} is reported. Check the paper.", ["PRESENT", "ABSENT"],
                       json.dumps(ne, ensure_ascii=False))
    for i, s in enumerate(slots):
        if s["source_kind"] == "FIGURE" and not s.get("figure_item_id"):
            ctx.warn("T002", f"slots[{i}] FIGURE without figure_item_id — digitizer must locate {s['locator_label']}")
    ctx.check()
    con.execute("INSERT OR REPLACE INTO wf_triage(study_id, pass, run_id, fruit_yield, dry_biomass, yield_components, "
                "scope_flag, scope_reason, n_experiments, design_summary, negative_evidence, payload, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (ctx.study, d["pass"], ctx.run_id, t["fruit_yield"], t["dry_biomass"], t["yield_components"],
                 d["scope"]["flag"], d["scope"].get("reason"), d["design"]["n_experiments"], d["design"]["summary"],
                 json.dumps(ne, ensure_ascii=False), json.dumps(d, ensure_ascii=False), now()))
    if d["pass"] == "P1":
        _insert_slots(ctx, slots)
        con.execute("UPDATE wf_study_status SET yield_status=?, biomass_status=?, updated_at=? WHERE study_id=?",
                    (t["fruit_yield"], t["dry_biomass"], now(), ctx.study))
        if (not d["scope"]["class_A_ok"]) or d["scope"]["flag"] != "NONE":
            ctx.follow("SCOPE")
            set_state(con, ctx.study, "SCOPE_REVIEW", ctx.run_id, scope_status="FLAGGED")
        else:
            after_scope_ok(ctx)
    else:
        p1 = (rows(con, "SELECT * FROM wf_triage WHERE study_id=? AND pass='P1'", (ctx.study,)) or [None])[0]
        # A complete negative second search can resolve an earlier UNCLEAR
        # primary even when it contributes no new quantitative slots.
        con.execute("UPDATE wf_study_status SET yield_status=?, updated_at=? WHERE study_id=?",
                    (t["fruit_yield"], now(), ctx.study))
        found_new = bool(slots)
        if p1 and (p1["fruit_yield"] != t["fruit_yield"] or p1["dry_biomass"] != t["dry_biomass"]):
            changelog(con,ctx.run_id,"triage",ctx.study,"P2_RECOVERED_OR_DISAGREED",slots)
            ctx.warn("T003", "second triage disagrees with first (counts toward triage miss-rate)")
        if found_new:
            inserted=_insert_slots(ctx, slots)
            con.execute("UPDATE wf_study_status SET yield_status=?, biomass_status=?, updated_at=? WHERE study_id=?",
                        (t["fruit_yield"], t["dry_biomass"], now(), ctx.study))
            if inserted:
                previous=con.execute("SELECT COUNT(*) FROM wf_tasks WHERE study_id=? AND task_type='DESIGN'",(ctx.study,)).fetchone()[0]
                ctx.follow("DESIGN", "triage-P2" if previous else "")
                set_state(con, ctx.study, "TRIAGED", ctx.run_id)
        else:
            existing=con.execute("SELECT COUNT(*) FROM wf_target_slots WHERE study_id=? AND route IN ('EXTRACT','FIGURE','TWIN_VALIDATION')",(ctx.study,)).fetchone()[0]
            if not existing:set_state(con, ctx.study, "NO_TARGET_CONFIRMED", ctx.run_id)
    return len(slots)


def h_scope(ctx: Ctx) -> int:
    d, con = ctx.d, ctx.con
    con.execute("INSERT OR REPLACE INTO wf_scope(study_id, run_id, proposed_class, reason, evidence, status, created_at) "
                "VALUES (?,?,?,?,?,?,?)", (ctx.study, ctx.run_id, d["proposed_class"], d["reason"],
                                           json.dumps(d["evidence"], ensure_ascii=False),
                                           "CONFIRMED" if d["proposed_class"] == "A" else "PROPOSED", now()))
    if d["proposed_class"] == "A":
        if ctx.cfg.get("scope.screen_all", False) and not con.execute(
                "SELECT 1 FROM wf_triage WHERE study_id=? AND pass='P1'", (ctx.study,)).fetchone():
            # EXTERNAL_TEST screening-first flow: eligibility confirmed -> fresh source inventory.
            set_state(con, ctx.study, "NEW", ctx.run_id, scope_status="OK")
            ctx.follow("TRIAGE")
        else:
            after_scope_ok(ctx)
    elif d["confidence"] == "HIGH" and d["evidence"]:
        con.execute("UPDATE wf_scope SET status='CONFIRMED' WHERE study_id=? AND run_id=?",(ctx.study,ctx.run_id))
        set_state(con,ctx.study,"EXCLUDED_SCOPE",ctx.run_id,scope_status="EXCLUDED",locked=1,notes=d["reason"])
        con.execute("UPDATE wf_tasks SET status='CANCELLED' WHERE study_id=? AND status='READY'",(ctx.study,))
    else:
        add_review(con, ctx.study, "SCOPE", ctx.study,
                   f"Scope auditor proposes class {d['proposed_class']} ({d['confidence']}): {d['reason']}",
                   [f"CONFIRM_{d['proposed_class']}", "KEEP_A"], json.dumps(d["evidence"], ensure_ascii=False), 1)
    return 1


def _design_signature(exps, arms, tps):
    """Compare inference-relevant fields, not JSON whitespace or list order."""
    def identifier(value):
        return "" if value is None else str(value)

    def components(value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                raise Reject(["stored design component_codes is invalid JSON; inspect before revising design"])
        if value is None:
            value = []
        if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
            raise Reject(["design component_codes must be a list of strings"])
        return tuple(sorted(value))

    e = frozenset((x["experiment_key"], identifier(x.get("experiment_id")), x.get("system") or "",
                   x.get("allocation") or "UNKNOWN", int(x.get("factorial_verified") or 0)) for x in exps)
    a = frozenset((x["arm_key"], x["experiment_key"], identifier(x.get("arm_id")), x["stress_code"],
                   x["bio_code"], int(x.get("n_bio_components") or 0), x.get("genotype") or "",
                   x.get("season") or "", x.get("site") or "", x.get("role") or "",
                   components(x.get("component_codes")), x.get("background_key") or "") for x in arms)
    t = frozenset((x["timepoint_key"], x.get("experiment_key") or "",
                   None if x.get("days") in (None, "") else float(x["days"]), x.get("kind") or "",
                   int(x.get("is_terminal") or 0)) for x in tps)
    return e, a, t


def _ensure_extraction_task(ctx, task_type, scope_ref, reopen_done=False):
    old = ctx.con.execute("SELECT task_id, status FROM wf_tasks WHERE study_id=? AND task_type=? AND scope_ref=?",
                          (ctx.study, task_type, scope_ref)).fetchone()
    if old and old["status"] == "FAILED":
        return False  # Retain genuine failures for the existing review/requeue workflow.
    if old and old["status"] == "DONE":
        if not reopen_done:
            return False
        ctx.con.execute("UPDATE wf_tasks SET status='READY', attempts=0, lease_owner=NULL, lease_expires=NULL, "
                        "last_error=NULL, updated_at=? WHERE task_id=?", (now(), old["task_id"]))
        changelog(ctx.con, ctx.run_id, "task", old["task_id"], "REOPEN_MISSING_SLOT_PASS")
    ctx.follow(task_type, scope_ref)
    return True


def _schedule_design_extraction(ctx, structural):
    """Preserve completed passes while ensuring new target slots are not stranded."""
    con, study = ctx.con, ctx.study
    needed = False
    missing = {}
    for pass_ in ("A", "B"):
        missing[pass_] = con.execute(
            "SELECT 1 FROM wf_target_slots s WHERE s.study_id=? AND s.route='EXTRACT' "
            "AND NOT EXISTS (SELECT 1 FROM wf_slot_pass p WHERE p.slot_id=s.slot_id AND p.pass=? "
            "AND p.status IN ('EXTRACTED','NOT_EXTRACTABLE')) LIMIT 1", (study, pass_)).fetchone() is not None
    if any(missing.values()):
        scope = ctx.task["scope_ref"]
        if not structural:
            # Reuse an existing pair instead of creating one batch per identical DESIGN.
            old = con.execute("SELECT scope_ref FROM wf_tasks WHERE study_id=? "
                              "AND task_type IN ('EXTRACT_A','EXTRACT_B') ORDER BY "
                              "CASE status WHEN 'LEASED' THEN 0 WHEN 'READY' THEN 1 WHEN 'DONE' THEN 2 "
                              "WHEN 'FAILED' THEN 3 ELSE 4 END, updated_at DESC, task_id DESC LIMIT 1", (study,)).fetchone()
            if old:
                scope = old["scope_ref"]
        for pass_, task_type in (("A", "EXTRACT_A"), ("B", "EXTRACT_B")):
            # Both tasks must share a scope so the existing counterpart/reconcile
            # protocol still works when one pass was already complete.
            needed = _ensure_extraction_task(ctx, task_type, scope, reopen_done=missing[pass_]) or needed
    for s in rows(con, "SELECT slot_id FROM wf_target_slots WHERE study_id=? "
                       "AND route IN ('FIGURE','TWIN_VALIDATION') AND status IN ('OPEN','EXTRACTED')", (study,)):
        for pass_, task_type in (("FA", "FIGURE_A"), ("FB", "FIGURE_B")):
            complete = con.execute("SELECT 1 FROM wf_slot_pass WHERE slot_id=? AND pass=? "
                                   "AND status IN ('EXTRACTED','NOT_EXTRACTABLE')", (s["slot_id"], pass_)).fetchone()
            if not complete:
                needed = _ensure_extraction_task(ctx, task_type, s["slot_id"], reopen_done=True) or needed
    return needed


def _queue_design_revision(ctx):
    # A running DESIGN already has a context snapshot. Reuse only READY work so
    # a later gap cannot disappear into a snapshot the agent has already read.
    queued = ctx.con.execute("SELECT scope_ref FROM wf_tasks WHERE study_id=? AND task_type='DESIGN' "
                             "AND status='READY' ORDER BY created_at, task_id LIMIT 1", (ctx.study,)).fetchone()
    if queued:
        return queued["scope_ref"]
    n = ctx.con.execute("SELECT COUNT(*) FROM wf_tasks WHERE study_id=? AND task_type='DESIGN'", (ctx.study,)).fetchone()[0]
    rev = f"rev-{n + 1}"
    ctx.follow("DESIGN", rev)
    return rev


def _record_design_gaps(ctx, reader):
    """Only a real design omission reopens DESIGN; source limits stay recorded as flags."""
    gaps = ctx.d["design_gaps"]
    structural = [g for g in gaps if g.get("kind") == "STRUCTURAL"]
    limits = [g for g in gaps if g.get("kind") != "STRUCTURAL"]
    if limits:
        ctx.warn("V014", f"source limits reported: {limits}")
    if structural:
        rev = _queue_design_revision(ctx)
        add_review(ctx.con, ctx.study, "DESIGN_GAP", f"{ctx.study}:{rev}:{ctx.task['task_id']}",
                   f"{reader} reported design gaps; design revision queued",
                   ["ACK"], json.dumps(structural, ensure_ascii=False), 3)



def h_design(ctx: Ctx) -> int:
    d, con, study = ctx.d, ctx.con, ctx.study
    cr = ColumnResolver(con, ctx.cfg.column_map)
    exps, arms, tps = d["experiments"], d["arms"], d["timepoints"]
    ek = [e["experiment_key"] for e in exps]
    if len(ek) != len(set(ek)):
        ctx.err("experiments: duplicate experiment_key")
    ak = [a["arm_key"] for a in arms]
    if len(ak) != len(set(ak)):
        ctx.err("arms: duplicate arm_key")
    tk = [t["timepoint_key"] for t in tps]
    if len(tk) != len(set(tk)):
        ctx.err("timepoints: duplicate timepoint_key")
    combos: Dict[tuple, str] = {}
    core_exp_ids: Set[str] = set()
    core_arm_ids: Set[str] = set()
    e_id, e_sid = cr.get("experiments", "experiment_id"), cr.get("experiments", "study_id")
    if e_id and e_sid:
        core_exp_ids = {str(r["x"]) for r in rows(con, f"SELECT {q(e_id)} AS x FROM experiments WHERE CAST({q(e_sid)} AS TEXT)=?", (study,))}
        a_id, a_exp = cr.get("arms", "arm_id"), cr.get("arms", "experiment_id")
        if a_id and a_exp and core_exp_ids:
            ph = ",".join("?" for _ in core_exp_ids)
            core_arm_ids = {str(r["x"]) for r in rows(con, f"SELECT {q(a_id)} AS x FROM arms WHERE CAST({q(a_exp)} AS TEXT) IN ({ph})",
                                                      list(core_exp_ids))}
    for e in exps:
        if e.get("experiment_id") and str(e["experiment_id"]) not in core_exp_ids:
            ctx.err(f"experiment {e['experiment_key']}: experiment_id {e['experiment_id']} not found among this study's "
                    f"core experiments {sorted(core_exp_ids)[:20]} — set null if it does not exist")
    roles_by_exp: Dict[str, Set[str]] = {}
    for a in arms:
        a["stress_code"] = "NONE" if a["stress_code"].strip().upper() == "NONE" else a["stress_code"].strip()
        a["bio_code"] = "NONE" if a["bio_code"].strip().upper() == "NONE" else a["bio_code"].strip()
        if a["experiment_key"] not in ek:
            ctx.err(f"arm {a['arm_key']}: unknown experiment_key {a['experiment_key']}")
        if a.get("arm_id") and str(a["arm_id"]) not in core_arm_ids:
            ctx.err(f"arm {a['arm_key']}: arm_id {a['arm_id']} not found in core arms of this study — set null")
        if (a["bio_code"] == "NONE") != (a["n_bio_components"] == 0):
            ctx.err(f"arm {a['arm_key']}: bio_code {a['bio_code']} inconsistent with n_bio_components={a['n_bio_components']}")
        combo = (a["experiment_key"], a["stress_code"], a["bio_code"], a.get("genotype") or "", a.get("season") or "",
                 a.get("site") or "")
        if combo in combos:
            ctx.err(f"arms {combos[combo]} and {a['arm_key']} have identical design cell {combo} — make codes distinct "
                    "(dose, timing, cultivar, season or site)")
        combos[combo] = a["arm_key"]
        role = ("C" if a["bio_code"] == "NONE" else "B") if a["stress_code"] == "NONE" else \
               ("S" if a["bio_code"] == "NONE" else "SB")
        a["role"] = role
        roles_by_exp.setdefault(a["experiment_key"], set()).add(role)
    for t in tps:
        if t.get("experiment_key") and t["experiment_key"] not in ek:
            ctx.err(f"timepoint {t['timepoint_key']}: unknown experiment_key")
    used = rows(con, "SELECT DISTINCT arm_key, timepoint_key FROM wf_values WHERE study_id=?", (study,))
    for u in used:
        if u["arm_key"] not in ak:
            ctx.err(f"arm_key {u['arm_key']} already has extracted values — keep it in the revised design")
        if u["timepoint_key"] not in tk:
            ctx.err(f"timepoint_key {u['timepoint_key']} already has extracted values — keep it in the revised design")
    for e, roles in roles_by_exp.items():
        if not {"S", "SB"} <= roles:
            ctx.warn("D001", f"experiment {e}: no S/SB pair (roles {sorted(roles)}) — no primary contrast possible")
    if not any(t["is_terminal"] for t in tps):
        ctx.warn("D002", "no timepoint marked is_terminal — terminal dry biomass cannot be identified")
    ctx.check()
    stored = _design_signature(rows(con, "SELECT * FROM wf_design_experiments WHERE study_id=?", (study,)),
                               rows(con, "SELECT * FROM wf_design_arms WHERE study_id=?", (study,)),
                               rows(con, "SELECT * FROM wf_design_timepoints WHERE study_id=?", (study,)))
    revised = _design_signature(exps, arms, tps)
    structural = stored != revised
    # Adding arms/timepoints/experiments leaves every stored cell unchanged: keep its checked values.
    additive = structural and any(stored) and all(old <= new for old, new in zip(stored, revised))
    if additive:
        changelog(con, ctx.run_id, "study", study, "DESIGN_ADDITIVE_REVISION", {"reason": "stored design cells unchanged"})
        structural = False
    if structural and any(stored):
        changelog(con,ctx.run_id,"study",study,"INVALIDATE_DESIGN_DEPENDENTS",{"reason":"new design revision; old extraction history retained"})
        con.execute("DELETE FROM an_target_values WHERE study_id=?",(study,))
        con.execute("DELETE FROM an_contrasts WHERE study_id=?",(study,))
        con.execute("DELETE FROM wf_reconciliation WHERE study_id=?",(study,))
        con.execute("DELETE FROM wf_slot_pass WHERE slot_id IN (SELECT slot_id FROM wf_target_slots WHERE study_id=?)",(study,))
        con.execute("UPDATE wf_target_slots SET status='OPEN' WHERE study_id=? AND route IN ('EXTRACT','FIGURE','TWIN_VALIDATION')",(study,))
        con.execute("UPDATE wf_tasks SET status='READY',attempts=0 WHERE study_id=? AND status='DONE' AND task_type IN ('FIGURE_A','FIGURE_B','MODERATORS','ROB')",(study,))
    for tbl in ("wf_design_experiments", "wf_design_arms", "wf_design_timepoints"):
        con.execute(f"DELETE FROM {tbl} WHERE study_id=?", (study,))
    for e in exps:
        con.execute("INSERT INTO wf_design_experiments VALUES (?,?,?,?,?,?,?,?)",
                    (study, e["experiment_key"], e.get("experiment_id"), e["description"], e.get("system"), ctx.run_id,e["allocation"],int(e["factorial_verified"])))
    for a in arms:
        con.execute("INSERT INTO wf_design_arms(study_id, arm_key, experiment_key, arm_id, label_in_source, stress_code, "
                    "stress_desc, bio_code, bio_desc, n_bio_components, genotype, season, site, role, run_id) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (study, a["arm_key"], a["experiment_key"], a.get("arm_id"), a["label_in_source"], a["stress_code"],
                     a.get("stress_desc"), a["bio_code"], a.get("bio_desc"), a["n_bio_components"], a.get("genotype"),
                     a.get("season"), a.get("site"), a["role"], ctx.run_id))
    for a in arms:
        con.execute("UPDATE wf_design_arms SET component_codes=?,background_key=? WHERE study_id=? AND arm_key=?",(json.dumps(a["component_codes"]),a["background_key"],study,a["arm_key"]))
    for t in tps:
        con.execute("INSERT INTO wf_design_timepoints VALUES (?,?,?,?,?,?,?,?)",
                    (study, t["timepoint_key"], t.get("experiment_key"), t["label"], t.get("days"), t["kind"],
                     int(t["is_terminal"]), ctx.run_id))
    for p in d["core_patches"]:
        con.execute("INSERT INTO wf_core_patches(study_id, table_name, row_id, field, current_value, proposed_value, reason, "
                    "locator, status, run_id, created_at) VALUES (?,?,?,?,?,?,?,?, 'PROPOSED', ?, ?)",
                    (study, p["table"], p["row_id"], p["field"], json.dumps(p.get("current")),
                     json.dumps(p.get("proposed")), p["reason"], p["locator"], ctx.run_id, now()))
        pid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        ctx.follow("PATCH_REVIEW", f"patch-{pid}")
    if not structural and not additive:
        changelog(con, ctx.run_id, "study", study, "DESIGN_CONFIRMED_UNCHANGED", {"revision": ctx.task["scope_ref"]})
    # A report closes only on an explicit answer; one left unanswered stays open.
    dispositions = {int(x["review_id"]): x for x in d.get("gap_dispositions", [])}
    for r in rows(con, "SELECT review_id FROM wf_review WHERE study_id=? AND kind='DESIGN_GAP' AND status='OPEN'", (study,)):
        x = dispositions.get(r["review_id"])
        if x:
            con.execute("UPDATE wf_review SET status='DECIDED',decision=?,decision_note=?,decided_by=?,decided_at=? WHERE review_id=?",
                        (x["disposition"], x["note"], ctx.run_id, now(), r["review_id"]))

    extraction_needed = _schedule_design_extraction(ctx, structural)
    if structural or extraction_needed:
        set_state(con, study, "EXTRACTING", ctx.run_id)
    else:
        # Author decision 2026-11-13: unchanged, source-confirmed design -> normal readiness check
        maybe_verify(ctx)
    return len(arms)


def _validate_value_item(ctx: Ctx, v: Dict[str, Any], label: str, arms: Set[str], tps: Set[str],
                         slots: Dict[str, Dict], texts: List[str], pass_: str) -> Tuple[Optional[str], Optional[float], str]:
    if v["arm_key"] not in arms:
        ctx.err(f"{label}: arm_key '{v['arm_key']}' not in design {sorted(arms)[:30]} — report it in design_gaps instead")
    if v["timepoint_key"] not in tps:
        ctx.err(f"{label}: timepoint_key '{v['timepoint_key']}' not in design {sorted(tps)} — report it in design_gaps")
    if not v.get("slot_id"):
        ctx.err(f"{label}: slot_id is required (one of {sorted(slots)})")
    elif v["slot_id"] not in slots:
        ctx.err(f"{label}: slot_id '{v['slot_id']}' is not an extraction slot of this study ({sorted(slots)})")
    elif slots[v["slot_id"]]["endpoint"] != v["endpoint"]:
        ctx.warn("V011", f"{label}: endpoint {v['endpoint']} differs from slot endpoint {slots[v['slot_id']]['endpoint']}",
                 "value", label)
    _endpoint_attrs(ctx, v, label)
    _numeric_checks(ctx, v, label)
    if not N.mean_in_verbatim(v["mean"], v["verbatim"]):
        ctx.err(f"{label}: mean {v['mean']} is not printed in verbatim {v['verbatim']!r} — copy the cell/sentence exactly "
                "(decimal commas are fine) and report the number as printed")
    cell = N.parse_cell(v["verbatim"])
    if v.get("dispersion_type") != "CI95" and v.get("dispersion_value") is not None and (cell["pm"] or cell["paren"]) and cell["disp"] is not None:
        if not N.close(float(cell["disp"]), float(v["dispersion_value"])):
            ctx.err(f"{label}: dispersion_value {v['dispersion_value']} differs from the printed {cell['disp']} in verbatim")
    from .sourceqa import check_receipt
    fid = v.get("source_file_id")
    fsid = __import__("tfmlib.db", fromlist=["ColumnResolver"]).ColumnResolver(ctx.con, ctx.cfg.column_map)
    sc, fc = fsid.get("files", "study_id"), fsid.get("files", "active_file_id")
    if not sc or not fc or not ctx.con.execute(f"SELECT 1 FROM files WHERE CAST({q(sc)} AS TEXT)=? AND CAST({q(fc)} AS TEXT)=?", (ctx.study,fid)).fetchone():
        ctx.err(f"{label}: source_file_id is not a registered source of this study")
    original = False
    if v.get("receipt_id"):
        try:
            check_receipt(ctx.con,ctx.cfg,ctx.study,fid,v["receipt_id"],v.get("page"))
            original = True
            receipt = rows(ctx.con,"SELECT payload FROM wf_source_receipts WHERE receipt_id=?",(v["receipt_id"],))[0]
            derived = json.loads(receipt["payload"]).get("summary")
            if derived:
                for field,key in (("mean","mean"),("n","n"),("dispersion_value","sd")):
                    a,b=v.get(field),derived.get(key)
                    if (a is None)!=(b is None) or (a is not None and not N.close(float(a),float(b))):ctx.err(f"{label}: derived {field} must equal deterministic original-range summary")
                if v.get("dispersion_type")!=("SD" if derived.get("sd") is not None else "NONE"):ctx.err("raw-derived summary SD type mismatch")
        except ValueError as exc: ctx.err(f"{label}: {exc}")
    if pass_ in ("B","ADJ") and not original:
        ctx.err(f"{label}: original PDF/supplement receipt is mandatory for independent verification")
    if original and not (v.get("source_cell") or "").strip():
        ctx.err(f"{label}: source_cell must identify exact row/column/group/timepoint")
    if texts:
        found = N.value_in_texts(v["mean"], texts)
        check = "PASS" if found else "FAIL"
        if not found:
            msg = f"{label}: mean {v['mean']} not found anywhere in the parsed source text/tables"
            ctx.warn("V007", msg + "; Docling may be wrong. Original evidence has priority.", "value", label)
            if not original:
                ctx.err(f"{label}: Docling discrepancy requires an original receipt before submission")
    else:
        check = "UNAVAILABLE"
    if original: check = "ORIGINAL_RECEIPT"
    unit_norm, fac = _unit_check(ctx, v, label)
    return unit_norm, fac, check


def _inventory_corrections(ctx,pass_,slots):
    from .sourceqa import check_receipt
    corrections={}
    for c in ctx.d.get("inventory_corrections",[]):
        sid=c["slot_id"];slot=slots.get(sid)
        if not slot:ctx.err("inventory correction refers to an unknown slot");continue
        if c["source_file_id"]!=slot["source_file_id"]:ctx.err("inventory correction must use slot's original source");continue
        try:check_receipt(ctx.con,ctx.cfg,ctx.study,c["source_file_id"],c["receipt_id"])
        except ValueError as exc:ctx.err(str(exc));continue
        corrections[sid]=c["expected_n_values"]
        ctx.con.execute("INSERT OR REPLACE INTO wf_inventory_corrections VALUES(?,?,?,?,?,?,?)",(sid,pass_,slot["expected_n_values"],c["expected_n_values"],c["receipt_id"],c["reason"],ctx.run_id))
        other=rows(ctx.con,"SELECT * FROM wf_inventory_corrections WHERE slot_id=? AND pass<>?",(sid,pass_))
        if pass_=="ADJ" or any(x["new_count"]==c["expected_n_values"] for x in other):
            ctx.con.execute("UPDATE wf_target_slots SET expected_n_values=? WHERE slot_id=?",(c["expected_n_values"],sid))
            changelog(ctx.con,ctx.run_id,"slot",sid,"SOURCE_VERIFIED_INVENTORY_CORRECTION",{"old":slot["expected_n_values"],"new":c["expected_n_values"],"receipt":c["receipt_id"],"reason":c["reason"]})
    return corrections

def h_values(ctx: Ctx) -> int:
    d, con, study = ctx.d, ctx.con, ctx.study
    pass_ = "A" if ctx.task["task_type"] == "EXTRACT_A" else "B"
    if d["pass"] != pass_:
        ctx.err(f"pass must be {pass_}")
    arms, tps = _design_sets(con, study)
    slots = {s["slot_id"]: s for s in rows(con, "SELECT * FROM wf_target_slots WHERE study_id=? AND route='EXTRACT'", (study,))}
    corrections=_inventory_corrections(ctx,pass_,slots)
    texts = source_texts(ctx.cfg, study)
    if not texts:
        ctx.warn("V007", "parsed source text not available — number-in-source check skipped (configure paths.yaml)")
    seen: Dict[str, str] = {}
    prepared = []
    for i, v in enumerate(d["values"]):
        label = f"values[{i}] ({v['arm_key']}, {v['endpoint']}, {v['timepoint_key']})"
        unit_norm, fac, check = _validate_value_item(ctx, v, label, arms, tps, slots, texts, pass_)
        rk = record_key(v)
        if rk in seen:
            ctx.err(f"{label}: duplicates {seen[rk]} (same arm/endpoint/attributes/timepoint). Keep ONE value — the "
                    "highest-priority source (supplement dataset > supplement table > main table > text)")
        seen[rk] = label
        prepared.append((v, unit_norm, fac, check))
    listed = {s["slot_id"]: s for s in d["slot_status"]}
    for sid in slots:
        if sid not in listed:
            ctx.err(f"slot_status: slot {sid} ({slots[sid]['locator_label']}) not reported — every extraction slot needs "
                    "EXTRACTED or NOT_EXTRACTABLE")
    for sid, s in listed.items():
        if sid not in slots:
            ctx.err(f"slot_status: unknown slot {sid}")
            continue
        cnt = sum(1 for v in d["values"] if v.get("slot_id") == sid)
        if s["n_values"] != cnt:
            ctx.err(f"slot_status {sid}: n_values={s['n_values']} but {cnt} values carry this slot_id")
        if s["status"] == "NOT_EXTRACTABLE" and not s.get("reason"):
            ctx.err(f"slot_status {sid}: NOT_EXTRACTABLE needs a reason")
        if s["status"] == "EXTRACTED" and cnt == 0:
            ctx.err(f"slot_status {sid}: EXTRACTED with 0 values")
        exp_n = slots[sid].get("expected_n_values") or 0
        if s["status"] == "EXTRACTED" and cnt != exp_n and corrections.get(sid)!=cnt:
            ctx.err(f"slot {sid}: {cnt} values < expected {exp_n}; fill missing cells or submit an evidenced inventory correction")
    ctx.check()
    for v, unit_norm, fac, check in prepared:
        _insert_value(ctx, v, pass_, unit_norm, fac, check)
    _slot_pass(ctx, d["slot_status"], pass_)
    con.execute("UPDATE wf_target_slots SET status='EXTRACTED', updated_at=? WHERE study_id=? AND route='EXTRACT' "
                "AND status='OPEN' AND slot_id IN (%s)" % ",".join("?" for _ in listed), [now(), study, *listed])
    if d.get("design_gaps"):
        _record_design_gaps(ctx, "Extractor")
    other = "EXTRACT_B" if pass_ == "A" else "EXTRACT_A"
    if _counterpart_done(con, study, other, ctx.task["scope_ref"]):
        st = reconcile(con, ctx.cfg, study, "TEXT_TABLE", run_id=ctx.run_id)
        ctx.followups.append(f"RECONCILED:{st}")
        refresh_slots(con, study)
        ensure_adjudication(ctx)
        maybe_verify(ctx)
    return len(prepared)


def _resolve_image(cfg, p: str) -> Path:
    path = Path(p).expanduser()
    if path.is_absolute():
        return path
    for base in (cfg.root, cfg.p("figures_root"), cfg.p("docling_root")):
        if base and (Path(base) / path).exists():
            return Path(base) / path
    return cfg.root / path


def h_figure(ctx: Ctx) -> int:
    d, con, study, cfg = ctx.d, ctx.con, ctx.study, ctx.cfg
    pass_ = "FA" if ctx.task["task_type"] == "FIGURE_A" else "FB"
    if d["pass"] != pass_:
        ctx.err(f"pass must be {pass_}")
    slot_id = ctx.task["scope_ref"]
    slot = (rows(con, "SELECT * FROM wf_target_slots WHERE slot_id=?", (slot_id,)) or [None])[0]
    if not slot:
        ctx.err(f"unknown slot {slot_id}")
        ctx.check()
    arms, tps = _design_sets(con, study)
    fcfg = cfg.get("figures") or {}
    seen: Dict[str, str] = {}
    prepared = []
    for i, p in enumerate(d["panels"]):
        lab = f"panels[{i}] ({p['figure_label']} {p['panel']})"
        if p.get("slot_id") not in (None, slot_id):
            ctx.err(f"{lab}: slot_id must be {slot_id}")
        p["slot_id"] = slot_id
        from .sourceqa import check_receipt
        try: check_receipt(con,cfg,study,p["source_file_id"],p["receipt_id"],p.get("page"))
        except ValueError as exc: ctx.err(f"{lab}: {exc}")
        _endpoint_attrs(ctx, p, lab)
        try:
            cal = fit_axis(p["axis"]["ticks"], p["axis"]["scale"])
        except CalibrationError as exc:
            ctx.err(f"{lab}: axis calibration impossible: {exc}")
            continue
        # Author decision 2026-11-06: a slot listed here may use an axis with two labelled points; the warning stays on the record.
        min_ticks = 2 if slot_id in (fcfg.get("two_tick_axis_slots") or []) else int(fcfg.get("min_ticks", 3))
        status = calibration_status(cal, min_ticks, int(fcfg.get("recommended_ticks", 3)),
                                    float(fcfg.get("max_resid_frac", 0.015)))
        if status == "FAIL":
            ctx.err(f"{lab}: calibration FAIL (max tick residual {cal['max_resid_frac']:.3%} of axis range, "
                    f"{cal['n_ticks']} ticks) — re-read tick positions (use figure-grid / figure-probe)")
        elif status == "WARN_TWO_TICKS":
            ctx.warn("F001", f"{lab}: only 2 ticks — residual cannot be checked; prefer >= 3")
        if p["value_axis"] == "y" and cal["b"] > 0:
            ctx.warn("F002", f"{lab}: value increases downwards (b>0) — inverted axis or misread ticks?")
        img = _resolve_image(cfg, p["image_path"])
        if p["coord_space"]=="image_px":
            receipt_dir=(cfg.work_dir/"source_views"/p["receipt_id"]).resolve()
            if not img.resolve().is_relative_to(receipt_dir):ctx.err(f"{lab}: image must be rendered/cropped from the original receipt directory, not an unverified Docling image")
        elif p["coord_space"]=="pdf_pt":
            from .sourceqa import get_source
            _,original_pdf=get_source(con,cfg,p["source_file_id"])
            if img.resolve()!=original_pdf.resolve():ctx.err(f"{lab}: PDF point coordinates require the exact original PDF")
        size = image_size(img) if p["coord_space"] == "image_px" else None
        if not img.exists():
            ctx.err(f"{lab}: original-linked image {p['image_path']} missing; cannot verify digitization")
        pts = []
        for j, pt in enumerate(p["points"]):
            pl = f"{lab}.points[{j}] ({pt['arm_key']}, {pt['timepoint_key']})"
            if pt["arm_key"] not in arms:
                ctx.err(f"{pl}: arm_key not in design")
            if pt["timepoint_key"] not in tps:
                ctx.err(f"{pl}: timepoint_key not in design")
            if size:
                w, h = size
                for key in ("px_mean", "px_err_hi", "px_err_lo"):
                    val = pt.get(key)
                    lim = h if p["value_axis"] == "y" else w
                    if val is not None and not (0 <= val <= lim):
                        ctx.err(f"{pl}: {key}={val} outside image (0..{lim})")
            mean, err, info = point_values(pt["px_mean"], pt.get("px_err_hi"), pt.get("px_err_lo"), cal)
            from .errorbars import resolve_error_bar
            try:
                uncertainty = resolve_error_bar(p,pt,cal,mean,err,info,fcfg)
            except ValueError as exc:
                ctx.err(f"{pl}: {exc}")
                continue
            if pt.get("true_zero"):
                mean = 0.0
            dtype = uncertainty["dispersion_type"]
            v = {"slot_id": slot_id, "arm_key": pt["arm_key"], "endpoint": p["endpoint"],
                 **{a: p.get(a) for a in ATTRS}, "timepoint_key": pt["timepoint_key"], "mean": mean,
                 **uncertainty,
                 "n": p.get("n"), "n_unit": p.get("n_unit"), "n_source": p.get("n_source"), "unit_raw": p["unit_raw"],
                 "source_kind": "FIGURE", "source_file_id": p["source_file_id"], "page": p.get("page"),
                 "locator": f"{p['figure_label']} panel {p['panel']} ({p['figure_item_id']})",
                 "verbatim": p["verbatim_caption"][:600], "figure_item_id": p["figure_item_id"],
                 "outcome_context":p.get("outcome_context"),"context_key":p.get("context_key"),"ci":p.get("ci"),"receipt_id":p["receipt_id"],"source_cell":p["source_cell"],"confidence": p["confidence"], "notes": "; ".join(str(x) for x in (pt.get("notes"),pt.get("error_bar_note"),uncertainty["dispersion_basis"]) if x)}
            if v["dispersion_type"] in ("NONE", "UNCLEAR"):
                v["dispersion_value"] = None
            _numeric_checks(ctx, v, pl)
            rk = record_key(v)
            if rk in seen:
                ctx.err(f"{pl}: duplicates {seen[rk]}")
            seen[rk] = pl
            pts.append((pt, v, mean, err))
        unit_norm, fac = _unit_check(ctx, p, lab)
        prepared.append((p, cal, status, img, pts, unit_norm, fac))
    listed = {s["slot_id"]: s for s in d["slot_status"]}
    if slot_id not in listed:
        ctx.err(f"slot_status must report slot {slot_id}")
    elif listed[slot_id]["status"] == "NOT_EXTRACTABLE" and not listed[slot_id].get("reason"):
        ctx.err("NOT_EXTRACTABLE needs a reason")
    elif listed[slot_id]["status"] == "EXTRACTED":
        cnt = sum(len(x[4]) for x in prepared)
        if listed[slot_id]["n_values"] != cnt:
            ctx.err(f"slot_status n_values={listed[slot_id]['n_values']} but {cnt} points were digitised")
        expected = int(slot.get("expected_n_values") or 0)
        if cnt < expected:
            reason = (listed[slot_id].get("reason") or "").strip()
            if cnt == 0 or not reason.startswith("PARTIAL:"):
                ctx.err(f"slot {slot_id}: {cnt} points < expected {expected}; if the rest fail the 5% limit after re-render, set reason 'PARTIAL: <arm/timepoint list and cause>'")
    ctx.check()
    n = 0
    for p, cal, status, img, pts, unit_norm, fac in prepared:
        calib_id = f"{ctx.run_id}|{p['figure_item_id']}|{p['panel']}"
        con.execute("INSERT INTO wf_fig_calibrations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (calib_id, ctx.run_id, pass_, study, p["figure_item_id"], p["panel"], str(img),
                     image_sha256(img) if img.exists() else None, p["coord_space"], p["value_axis"], cal["scale"],
                     json.dumps(p["axis"]["ticks"]), cal["a"], cal["b"], cal["r2"], cal["max_resid_frac"],
                     cal["axis_range"], status))
        for pt, v, mean, err in pts:
            vid = _insert_value(ctx, v, pass_, unit_norm, fac, "FIGURE",
                                extra={"calib_id": calib_id, "axis_range": cal["axis_range"]})
            con.execute("INSERT INTO wf_fig_points(calib_id, run_id, pass, study_id, arm_key, timepoint_key, px_mean, "
                        "px_err_hi, px_err_lo, value_mean, value_err, err_type, value_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (calib_id, ctx.run_id, pass_, study, pt["arm_key"], pt["timepoint_key"], pt["px_mean"],
                         pt.get("px_err_hi"), pt.get("px_err_lo"), mean, err, v["dispersion_type"], vid))
            n += 1
    _slot_pass(ctx, d["slot_status"], pass_)
    con.execute("UPDATE wf_target_slots SET status='EXTRACTED', updated_at=? WHERE slot_id=? AND status='OPEN'",
                (now(), slot_id))
    if d.get("design_gaps"):
        _record_design_gaps(ctx, "Figure reader")
    other = "FIGURE_B" if pass_ == "FA" else "FIGURE_A"
    if _counterpart_done(con, study, other, slot_id):
        st = reconcile(con, cfg, study, "FIGURE", slot_id=slot_id, run_id=ctx.run_id)
        ctx.followups.append(f"RECONCILED:{st}")
        refresh_slots(con, study)
        ensure_adjudication(ctx)
        maybe_verify(ctx)
    return n


def h_adjudication(ctx: Ctx) -> int:
    d, con, study = ctx.d, ctx.con, ctx.study
    open_recs = {r["rec_id"]: r for r in rows(con, "SELECT * FROM wf_reconciliation WHERE study_id=? AND status='OPEN'",
                                              (study,))}
    arms, tps = _design_sets(con, study)
    slots = {s["slot_id"]: s for s in rows(con, "SELECT * FROM wf_target_slots WHERE study_id=?", (study,))}
    _inventory_corrections(ctx,"ADJ",slots)
    texts = source_texts(ctx.cfg, study)
    decided: Set[int] = set()
    prepared = []
    for i, dec in enumerate(d["decisions"]):
        lab = f"decisions[{i}] (rec {dec['rec_id']})"
        rec = open_recs.get(dec["rec_id"])
        if not rec:
            ctx.err(f"{lab}: not an OPEN conflict of this study")
            continue
        decided.add(rec["rec_id"])
        kind = dec["decision"]
        from .sourceqa import check_receipt
        try: check_receipt(con,ctx.cfg,study,dec["source_file_id"],dec["receipt_id"])
        except ValueError as exc: ctx.err(f"{lab}: {exc}")
        if kind in ("ACCEPT_A", "ACCEPT_B"):
            vid = rec["value_id_a"] if kind == "ACCEPT_A" else rec["value_id_b"]
            if not vid:
                ctx.err(f"{lab}: {kind} but that pass has no value for this record")
        if kind == "RECHECK_FIGURE":
            from .db import get_meta
            figure_slots=set()
            for vid in (rec["value_id_a"],rec["value_id_b"]):
                if vid:
                    for item in rows(con,"SELECT slot_id FROM wf_values WHERE value_id=? AND source_kind='FIGURE'",(vid,)):
                        if item['slot_id']:figure_slots.add(item['slot_id'])
            if not figure_slots:ctx.err(f"{lab}: no graphical source slot to recheck")
            for sid in figure_slots:
                count=int(get_meta(con,'figure_recheck_count:'+sid) or 0)
                if count>=int(ctx.cfg.get('queue.figure_recheck_rounds',2)):
                    ctx.err(f"{lab}: bounded original-source figure rechecks exhausted; resolve from a defensible source or document unavailability")
            prepared.append((rec,dec,sorted(figure_slots)))
            continue
        if kind == "CORRECTED":
            if rec["family"] == "FIGURE":
                ctx.err(f"{lab}: figure conflicts cannot be CORRECTED by typing a value — ACCEPT_A/ACCEPT_B, "
                        "RECHECK_FIGURE or a source-supported ACCEPT/NOT_EXTRACTABLE decision is required")
            elif not dec.get("value"):
                ctx.err(f"{lab}: CORRECTED needs `value`")
            else:
                v = dec["value"]
                if record_key(v) != rec["record_key"]:
                    ctx.err(f"{lab}: corrected value has record key {record_key(v)} but the conflict is about "
                            f"{rec['record_key']} — resolve mapping conflicts with ACCEPT_*/NOT_EXTRACTABLE per record")
                unit_norm, fac, check = _validate_value_item(ctx, v, lab, arms, tps, slots, texts, "ADJ")
                prepared.append((rec, dec, (unit_norm, fac, check)))
                continue
        prepared.append((rec, dec, None))
    missing = sorted(set(open_recs) - decided)
    if missing:
        ctx.err(f"every OPEN conflict needs a decision; missing rec_id {missing}")
    ctx.check()
    requeued_slots=set()
    for rec, dec, extra in prepared:
        kind = dec["decision"]
        from .sourceqa import check_receipt
        try: check_receipt(con,ctx.cfg,study,dec["source_file_id"],dec["receipt_id"])
        except ValueError as exc: ctx.err(f"{lab}: {exc}")
        if kind in ("ACCEPT_A", "ACCEPT_B"):
            vid = rec["value_id_a"] if kind == "ACCEPT_A" else rec["value_id_b"]
            base = rows(con, "SELECT * FROM wf_values WHERE value_id=?", (vid,))[0]
            if base["source_file_id"] != dec["source_file_id"]: raise Reject(["adjudication receipt original must match accepted source"])
            promote(con, ctx.cfg, study, rec["record_key"], base, "ADJUDICATED", [vid], {"receipt_id":dec["receipt_id"],"source_cell":dec["source_cell"]}, ctx.run_id)
            con.execute("UPDATE wf_reconciliation SET status='RESOLVED', resolved_value_id=?, resolved_by='ADJUDICATOR', "
                        "updated_at=? WHERE rec_id=?", (vid, now(), rec["rec_id"]))
        elif kind == "RECHECK_FIGURE":
            from .db import get_meta,set_meta
            for sid in extra:
                if sid in requeued_slots:continue
                requeued_slots.add(sid)
                set_meta(con,'figure_recheck_count:'+sid,int(get_meta(con,'figure_recheck_count:'+sid) or 0)+1)
                keys={x['record_key'] for x in rows(con,"SELECT record_key FROM wf_values WHERE slot_id=? AND source_kind='FIGURE'",(sid,))}
                for target in rows(con,'SELECT * FROM an_target_values WHERE study_id=?',(study,)):
                    if target['record_key'] not in keys:continue
                    if target['source_kind']=='FIGURE':
                        con.execute('DELETE FROM an_target_values WHERE tv_id=?',(target['tv_id'],))
                    elif (json.loads(target.get('dispersion_provenance_json') or 'null') or {}).get('source_kind')=='FIGURE':
                        if json.loads(target['dispersion_provenance_json']).get('n_from_secondary'):
                            con.execute('UPDATE an_target_values SET n=NULL,n_unit=NULL,n_source=NULL WHERE tv_id=?',(target['tv_id'],))
                        con.execute("UPDATE an_target_values SET dispersion_type='UNCLEAR',dispersion_value=NULL,sd=NULL,sd_norm=NULL,dispersion_type_reported=NULL,dispersion_basis='PENDING_RECHECK',dispersion_provenance_json=NULL,error_bar_status=NULL,error_bar_bounds_json=NULL,error_bar_relative_uncertainty=NULL WHERE tv_id=?",(target['tv_id'],))
                con.execute('DELETE FROM an_contrasts WHERE study_id=?',(study,))
                con.execute('DELETE FROM wf_slot_pass WHERE slot_id=?',(sid,))
                con.execute("UPDATE wf_target_slots SET status='OPEN',updated_at=? WHERE slot_id=?",(now(),sid))
                for tt in ('FIGURE_A','FIGURE_B'):
                    ctx.follow(tt,sid)
                    con.execute("UPDATE wf_tasks SET status='READY',attempts=0,lease_owner=NULL,lease_expires=NULL,last_error=NULL,updated_at=? WHERE study_id=? AND task_type=? AND scope_ref=?",(now(),study,tt,sid))
            con.execute("UPDATE wf_reconciliation SET status='OPEN',resolved_value_id=NULL,resolved_by='RECHECK_FIGURE',updated_at=? WHERE rec_id=?",(now(),rec['rec_id']))
        elif kind == "CORRECTED":
            unit_norm, fac, check = extra
            vid = _insert_value(ctx, dec["value"], "ADJ", unit_norm, fac, check)
            base = rows(con, "SELECT * FROM wf_values WHERE value_id=?", (vid,))[0]
            if base["source_file_id"] != dec["source_file_id"]: raise Reject(["adjudication receipt original must match accepted source"])
            promote(con, ctx.cfg, study, rec["record_key"], base, "ADJUDICATED", [vid], {"receipt_id":dec["receipt_id"],"source_cell":dec["source_cell"]}, ctx.run_id)
            con.execute("UPDATE wf_reconciliation SET status='RESOLVED', resolved_value_id=?, resolved_by='ADJUDICATOR', "
                        "updated_at=? WHERE rec_id=?", (vid, now(), rec["rec_id"]))
        elif kind == "NOT_EXTRACTABLE":
            con.execute("UPDATE wf_reconciliation SET status='RESOLVED', resolved_value_id=NULL, resolved_by='ADJUDICATOR', "
                        "updated_at=? WHERE rec_id=?", (now(), rec["rec_id"]))
        else:  # ESCALATE_HUMAN
            con.execute("UPDATE wf_reconciliation SET status='ESCALATED', updated_at=? WHERE rec_id=?", (now(), rec["rec_id"]))
            add_review(con, study, "CONFLICT", f"rec-{rec['rec_id']}",
                       f"{rec['record_key']}: passes disagree on {rec['fields_conflict']}. {dec['rationale']}",
                       ["A", "B", "NOT_EXTRACTABLE", "VALUE:mean;dispersion_type;dispersion_value;n"],
                       dec["evidence_locator"], 1)
        changelog(con, ctx.run_id, "reconciliation", rec["rec_id"], f"ADJ:{kind}", dec["rationale"])
    refresh_slots(con, study)
    maybe_verify(ctx)
    return len(prepared)


def h_moderators(ctx: Ctx) -> int:
    d,con,study=ctx.d,ctx.con,ctx.study
    from .sourceqa import check_receipt
    arms,_=_design_sets(con,study)
    exps={r["experiment_key"] for r in rows(con,"SELECT experiment_key FROM wf_design_experiments WHERE study_id=?",(study,))}
    for m in d["moderators"]:
        if m.get("arm_key") and m["arm_key"] not in arms:ctx.err("moderator arm not in design")
        if m.get("experiment_key") and m["experiment_key"] not in exps:ctx.err("moderator experiment not in design")
        try:check_receipt(con,ctx.cfg,study,m["source_file_id"],m["receipt_id"])
        except ValueError as exc:ctx.err(str(exc))
    ctx.check()
    stage={"MODERATORS":"A","MODERATORS_VERIFY":"B","MODERATORS_ADJ":"ADJ"}[ctx.task["task_type"]]
    con.execute("INSERT OR REPLACE INTO wf_moderator_passes VALUES(?,?,?,?)",(study,stage,json.dumps(d,sort_keys=True),ctx.run_id))
    verification="UNVERIFIED"
    if stage=="A":_reopen_or_follow(ctx,"MODERATORS_VERIFY")
    elif stage=="B":
        first=rows(con,"SELECT payload FROM wf_moderator_passes WHERE study_id=? AND pass='A'",(study,))
        def canonical(payload):
            return sorted([(m.get("experiment_key") or "",m.get("arm_key") or "",m["feature"],str(m["value"]),m.get("unit") or "",m["availability"]) for m in payload["moderators"]])
        if first and canonical(json.loads(first[0]["payload"]))==canonical(d):verification="SOURCE_VERIFIED_AB"
        else:_reopen_or_follow(ctx,"MODERATORS_ADJ")
    else:verification="SOURCE_ADJUDICATED"
    if stage=="A" or verification!="UNVERIFIED":
        con.execute("DELETE FROM wf_moderators WHERE study_id=?",(study,))
        for m in d["moderators"]:
            con.execute("INSERT INTO wf_moderators(study_id,experiment_key,arm_key,verification,availability,receipt_id,source_file_id,feature,value,unit,locator,verbatim,run_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(study,m.get("experiment_key"),m.get("arm_key"),verification,m["availability"],m["receipt_id"],m["source_file_id"],m["feature"],str(m["value"]),m.get("unit"),m["locator"],m["verbatim"],ctx.run_id,now()))
    maybe_verify(ctx)
    return len(d["moderators"])


ROB_DOMAINS = ["randomization_allocation", "experimental_unit", "pseudoreplication", "baseline_comparability",
               "intervention_fidelity", "measurement_objectivity", "missing_data", "selective_reporting",
               "co_interventions", "unit_of_analysis"]


def h_rob(ctx: Ctx) -> int:
    d, con, study = ctx.d, ctx.con, ctx.study
    doms = {a["domain"] for a in d["assessments"]}
    miss = [x for x in ROB_DOMAINS if x not in doms]
    if miss:
        ctx.err(f"missing RoB domains: {miss} (use 'unclear' when not reported)")
    ctx.check()
    con.execute("DELETE FROM wf_rob WHERE study_id=?", (study,))
    for a in d["assessments"]:
        con.execute("INSERT OR REPLACE INTO wf_rob VALUES (?,?,?,?,?,?,?,?)",
                    (study, a.get("experiment_key") or "", a["domain"], a["judgement"], a["support"], a["locator"],
                     ctx.run_id, now()))
    maybe_verify(ctx)
    return len(d["assessments"])


def h_relations(ctx: Ctx) -> int:
    d, con = ctx.d, ctx.con
    for r in d["relations"]:
        # PREPRINT_OF is directional (study_a is the preprint of study_b); others are symmetric
        a, b = ((str(r["study_a"]), str(r["study_b"])) if r["relation"] == "PREPRINT_OF"
                else tuple(sorted([str(r["study_a"]), str(r["study_b"])])))
        from .sourceqa import check_receipt, frozen_ids
        if a not in frozen_ids(ctx.cfg) or b not in frozen_ids(ctx.cfg): raise Reject(["relation outside frozen scope"])
        try: check_receipt(con,ctx.cfg,ctx.study,r["source_file_id"],r["receipt_id"])
        except ValueError as exc: raise Reject([str(exc)])
        status = "CONFIRMED" if r["confidence"]=="HIGH" or r["relation"] in ("UNRELATED", "SAME_LAB_INDEPENDENT") else "PROPOSED"
        con.execute("INSERT INTO wf_relations(study_a, study_b, relation, evidence, confidence, status, run_id, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(study_a, study_b, relation) DO UPDATE SET "
                    "evidence=excluded.evidence, confidence=excluded.confidence, status=excluded.status,run_id=excluded.run_id",
                    (a, b, r["relation"], r["evidence"], r["confidence"], status, ctx.run_id, now()))
        if status == "PROPOSED":
            rid = con.execute("SELECT rel_id FROM wf_relations WHERE study_a=? AND study_b=? AND relation=?",
                              (a, b, r["relation"])).fetchone()[0]
            add_review(con, a, "DUPLICATE", f"rel-{rid}", f"{a} vs {b}: {r['relation']} ({r['confidence']}). {r['evidence']}",
                       ["CONFIRM", "REJECT"], "", 1)
    return len(d["relations"])


def h_audit(ctx: Ctx) -> int:
    d, con = ctx.d, ctx.con
    for it in d["items"]:
        if not con.execute("SELECT 1 FROM an_target_values WHERE tv_id=?", (it["tv_id"],)).fetchone():
            ctx.err(f"unknown tv_id {it['tv_id']}")
    ctx.check()
    for it in d["items"]:
        con.execute("INSERT INTO wf_audit(tv_id, run_id, verdict, field_errors, corrected, notes, created_at) "
                    "VALUES (?,?,?,?,?,?,?)", (it["tv_id"], ctx.run_id, it["verdict"], json.dumps(it["field_errors"]),
                                               json.dumps(it.get("corrected")), it.get("notes"), now()))
        if it["verdict"] != "CORRECT":
            add_review(con, ctx.study, "AUDIT", f"tv-{it['tv_id']}-{ctx.run_id}",
                       f"Auditor marked tv_id {it['tv_id']} {it['verdict']} ({it['field_errors']}). {it.get('notes') or ''}",
                       ["OK", "VALUE:mean;dispersion_type;dispersion_value;n"], json.dumps(it.get("corrected")), 1)
    return len(d["items"])


def h_temporal(ctx):
    from .sourceqa import check_receipt
    d=ctx.d
    try: check_receipt(ctx.con,ctx.cfg,ctx.study,d["source_file_id"],d["receipt_id"])
    except ValueError as exc: raise Reject([str(exc)])
    date=d["first_online_date"]
    from .mode import is_test, date_in_window, window, ELIGIBLE_TEST, INELIGIBLE_TEST
    if is_test(ctx.cfg):
        if d["eligibility"] in ("ELIGIBLE_PRE2024","INELIGIBLE_POST2023"):
            raise Reject(["EXTERNAL_TEST project: use ELIGIBLE_TEST_WINDOW, INELIGIBLE_PRE2024, INELIGIBLE_AFTER_WINDOW or UNRESOLVED_QUARANTINE"])
        if d["eligibility"]==ELIGIBLE_TEST and not date_in_window(ctx.cfg,date):
            raise Reject([f"ELIGIBLE_TEST_WINDOW requires a documented first-online date of this exact version within {window(ctx.cfg)}"])
        if d["eligibility"]=="INELIGIBLE_PRE2024" and (not date or date>=window(ctx.cfg)[0]):
            raise Reject(["INELIGIBLE_PRE2024 requires the documented earlier first-online date"])
    elif d["eligibility"]=="ELIGIBLE_PRE2024" and (not date or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",date) or date>"2023-12-31"):
        raise Reject(["pre-2024 eligibility requires documented date for this exact publication version"])
    ctx.con.execute("INSERT OR REPLACE INTO wf_temporal_review VALUES(?,?,?,?,?,?,?,?)",(ctx.study,d["eligibility"],d["source_file_id"],d["receipt_id"],date,d["evidence"],ctx.run_id,now()))
    if is_test(ctx.cfg) and d["eligibility"] in INELIGIBLE_TEST:
        # A publication first online before 2024 can never be TEST (TFM 3.1); it is excluded, not re-labelled.
        set_state(ctx.con,ctx.study,"EXCLUDED_SCOPE",ctx.run_id,scope_status="EXCLUDED",locked=1,
                  notes=f"temporal: {d['eligibility']} ({date})")
        ctx.con.execute("UPDATE wf_tasks SET status='CANCELLED' WHERE study_id=? AND status='READY'",(ctx.study,))
    return 1

def h_dry_basis(ctx):
    from .sourceqa import check_receipt
    con, study = ctx.con, ctx.study
    want = {r["record_key"] for r in rows(con, "SELECT record_key FROM an_target_values WHERE study_id=? AND endpoint='DRY_BIOMASS' AND record_key NOT IN (SELECT tv_record_key FROM wf_dry_basis WHERE study_id=?)", (study, study))}
    seen = set()
    for it in ctx.d["items"]:
        try:
            check_receipt(con, ctx.cfg, study, it["source_file_id"], it["receipt_id"])
        except ValueError as exc:
            ctx.err(str(exc))
        for rk in it["record_keys"]:
            if rk not in want:
                ctx.err(f"unknown or already checked record {rk}")
            seen.add(rk)
    if want - seen:
        ctx.err(f"records not checked: {sorted(want - seen)[:20]}")
    ctx.check()
    for it in ctx.d["items"]:
        for rk in it["record_keys"]:
            con.execute("INSERT OR REPLACE INTO wf_dry_basis VALUES(?,?,?,?,?,?,?,?,?)",
                        (study, rk, it["basis"], "ORIGINAL_SOURCE_CHECK", it["source_file_id"], it["receipt_id"], it["evidence"], ctx.run_id, now()))
    return len(seen)


from .maintenance import h_patches, h_qa

HANDLERS = {
    "PATCH_REVIEW":h_patches,"QA_REVIEW":h_qa,"TEMPORAL":h_temporal,"DRY_BASIS":h_dry_basis,
    "TRIAGE": h_triage, "TRIAGE_2ND": h_triage, "SCOPE": h_scope, "DESIGN": h_design,
    "EXTRACT_A": h_values, "EXTRACT_B": h_values, "FIGURE_A": h_figure, "FIGURE_B": h_figure,
    "ADJUDICATE": h_adjudication, "MODERATORS": h_moderators,"MODERATORS_VERIFY":h_moderators,"MODERATORS_ADJ":h_moderators, "ROB": h_rob, "DEDUP": h_relations, "AUDIT": h_audit,
}
