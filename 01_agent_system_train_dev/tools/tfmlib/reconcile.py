"""Field-level comparison of independent passes and promotion to the verified layer.

Rules (TFM 3.8): discrepancies are never averaged; they go to adjudication.
Agreeing figure readings (two calibrated digitisations within tolerance) may be
averaged (config reconcile.figure_agree_value) — that is repeated measurement,
not conflict resolution.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from . import numbers as N
from . import units as U
from .db import changelog, now, rows
from .figures import agree as fig_agree
from .stats import sd_from

ATTRS = ("yield_scope", "mass_basis", "denominator", "harvest_window", "organ_scope")
# Only these attributes define *which* quantity a value is (they enter the record key);
# keep in sync with `endpoints.*.required_attrs` in config/pipeline.yaml.
KEY_ATTRS = {
    "FRUIT_YIELD": ("yield_scope", "mass_basis", "denominator", "harvest_window"),
    "DRY_BIOMASS": ("organ_scope",),
    "FRUIT_NUMBER": ("denominator",),
    "MEAN_FRUIT_MASS": (),
    "WATER_PRODUCTIVITY": ("denominator",),
}


# Kept on the record for the endpoint but outside its record key.
NON_KEY_KEPT = {"DRY_BIOMASS": ("mass_basis",)}


def strip_irrelevant(v: Dict[str, Any]) -> List[str]:
    """Null attributes that do not apply to the endpoint (so both passes build the same key)."""
    keep = tuple(KEY_ATTRS.get(v["endpoint"], ATTRS)) + NON_KEY_KEPT.get(v["endpoint"], ())
    dropped = [a for a in ATTRS if a not in keep and v.get(a) not in (None, "")]
    for a in ATTRS:
        if a not in keep:
            v[a] = None
    return dropped


def record_key(v: Dict[str, Any]) -> str:
    keep = KEY_ATTRS.get(v["endpoint"], ATTRS)
    parts = [str(v["arm_key"]), str(v["endpoint"])]
    parts += [str(v.get(a) or "") if a in keep else "" for a in ATTRS]
    parts.append(str(v["timepoint_key"]))
    parts.append(str(v.get("context_key") or ""))
    return "|".join(parts)


def _latest(con, study_id: str, passes: Tuple[str, ...], figure: bool, slot_id: Optional[str] = None) -> Dict[str, Dict]:
    sql = ("SELECT * FROM wf_values WHERE study_id=? AND pass IN (%s) AND source_kind %s 'FIGURE'"
           % (",".join("?" for _ in passes), "=" if figure else "<>"))
    params: List[Any] = [study_id, *passes]
    if slot_id:
        sql += " AND slot_id=?"
        params.append(slot_id)
    sql += " AND EXISTS (SELECT 1 FROM wf_slot_pass sp WHERE sp.slot_id=wf_values.slot_id AND sp.pass=wf_values.pass AND sp.run_id=wf_values.run_id) ORDER BY value_id"
    out: Dict[str, Dict] = {}
    for r in rows(con, sql, params):
        out[r["record_key"]] = r          # later value_id overwrites earlier = latest run wins
    return out


def _unit_key(v: Dict[str, Any]) -> str:
    # Readers describe an unprinted unit in free text; that wording is not a unit difference.
    if re.search(r"no (printed )?unit|unit not printed|unitless|dimensionless", v.get("unit_raw") or "", re.I):
        return "UNITLESS"
    # 'g' with a confirmed PER_PLANT denominator and 'g/plant' are the same printed quantity.
    return (v.get("unit_norm") or U.normalize(v.get("unit_raw") or "", v.get("endpoint"), v.get("denominator"))[0]
            or re.sub(r"[\(\[].*$", "", N.clean(v.get("unit_raw") or "")).lower().replace(" ", ""))


def compare(a: Dict[str, Any], b: Dict[str, Any], cfg, figure: bool) -> List[str]:
    bad: List[str] = []
    if a.get("source_file_id") != b.get("source_file_id"): bad.append("source_file_id")
    if figure:
        for field in ("dispersion_type_reported","dispersion_basis","error_bar_status"):
            if a.get(field) != b.get(field): bad.append(field)
        abs_frac = float(cfg.get("reconcile.figure_abs_frac_of_axis", 0.02))
        rel = float(cfg.get("reconcile.figure_rel_tol", 0.03))
        rng = max(a.get("axis_range") or 0, b.get("axis_range") or 0) or None
        if not fig_agree(a["mean"], b["mean"], None, 0.0, rel):
            bad.append("mean")
        da, db = a.get("dispersion_value"), b.get("dispersion_value")
        if (da is None) != (db is None):
            bad.append("dispersion_value")
        elif da is not None:
            # Two readings of a small bar agree within their declared digitization bound.
            bar_rel = max([rel] + [float(x) for x in (a.get("error_bar_relative_uncertainty"), b.get("error_bar_relative_uncertainty")) if x is not None])
            if not fig_agree(da, db, None, 0.0, bar_rel):
                bad.append("dispersion_value")
    else:
        if not N.close(float(a["mean"]), float(b["mean"]), rel=float(cfg.get("reconcile.table_rel_tol", 1e-9))):
            bad.append("mean")
        da, db = a.get("dispersion_value"), b.get("dispersion_value")
        if (da is None) != (db is None) or (da is not None and not N.close(float(da), float(db))):
            bad.append("dispersion_value")
    ta, tb = a.get("dispersion_type") or "NONE", b.get("dispersion_type") or "NONE"
    if {ta, tb} <= {"NONE", "UNCLEAR"}:
        pass
    elif ta != tb:
        bad.append("dispersion_type")
    if a.get("ci_json") != b.get("ci_json"): bad.append("ci_definition")
    if _context_checked(a) != _context_checked(b):bad.append("outcome_context")
    na, nb = a.get("n"), b.get("n")
    if (na is None) != (nb is None) or (na is not None and abs(float(na) - float(nb)) > 1e-9):
        bad.append("n")
    if _unit_key(a) != _unit_key(b):
        bad.append("unit")
    return bad


def _context_checked(v: Dict[str, Any]) -> Dict[str, Any]:
    """Assay text and the estimand/scale ids are each reader's own wording: no dictionary fixes them."""
    ctx = json.loads(v.get("outcome_context_json") or "null") or {}
    return {k: ctx.get(k) for k in ("scale_type", "scale_min", "scale_max", "effect_metric", "favorable_direction")}


# ----------------------------------------------------------------- promote
def promote(con, cfg, study_id: str, rk: str, base: Dict[str, Any], verification: str,
            basis_ids: List[int], override: Optional[Dict[str, Any]] = None, run_id: Optional[str] = None) -> Optional[int]:
    v = dict(base)
    if override:
        v.update(override)
    existing = rows(con, "SELECT * FROM an_target_values WHERE study_id=? AND record_key=?", (study_id, rk,))
    if existing:
        ex = existing[0]
        if ex["verification"] == "HUMAN_VERIFIED" and verification != "HUMAN_VERIFIED":
            return ex["tv_id"]
        priority=cfg.get("source_priority") or ["SUPP_DATASET","SUPP_TABLE","TABLE","TEXT","FIGURE"]
        rank=lambda item: priority.index(item.get("source_kind")) if item.get("source_kind") in priority else len(priority)
        old_primary=rank(ex)<rank(v) and verification!="HUMAN_VERIFIED"
        primary,secondary=(dict(ex),v) if old_primary else (v,dict(ex))
        if primary.get("dispersion_value") is None and secondary.get("dispersion_value") is not None:
            pu,pf,_=U.normalize(primary.get("unit_raw") or "",primary["endpoint"])
            su,sf,_=U.normalize(secondary.get("unit_raw") or "",secondary["endpoint"])
            # Identical printed units are compatible even when the parser cannot normalize them.
            raw_same=N.clean(primary.get("unit_raw") or "").lower()==N.clean(secondary.get("unit_raw") or "").lower() and bool(primary.get("unit_raw"))
            if not (pu and pu==su and pf is not None and sf is not None) and raw_same:
                pu,su,pf,sf="RAW","RAW",1.0,1.0
            tol=float(cfg.get("reconcile.figure_rel_tol",.05)) if "FIGURE" in (primary.get("source_kind"),secondary.get("source_kind")) else float(cfg.get("reconcile.table_rel_tol",1e-9))
            compatible=pu and pu==su and pf is not None and sf is not None and abs(primary["mean"]*pf-secondary["mean"]*sf)<=tol*abs(primary["mean"]*pf)+1e-12
            np,ns=primary.get("n"),secondary.get("n")
            compatible=compatible and (np is None or ns is None or N.close(float(np),float(ns)))
            if compatible:
                provenance=json.loads(secondary.get("dispersion_provenance_json") or "null") or {
                    "source_kind":secondary.get("source_kind"),"source_file_id":secondary.get("source_file_id"),
                    "receipt_id":secondary.get("receipt_id"),"source_cell":secondary.get("source_cell"),
                    "locator":secondary.get("locator"),"value":secondary.get("dispersion_value"),
                    "unit_raw":secondary.get("unit_raw"),"verification":verification if old_primary else ex["verification"],
                    "basis_value_ids":basis_ids if old_primary else json.loads(ex.get("basis_value_ids") or "[]")}
                primary.update({k:secondary.get(k) for k in ("dispersion_type","dispersion_type_reported","dispersion_basis","error_bar_status","error_bar_bounds_json","error_bar_relative_uncertainty","ci_json")})
                primary["dispersion_value"]=secondary["dispersion_value"]*sf/pf
                if np is None:
                    primary.update(n=ns,n_unit=secondary.get("n_unit"),n_source=secondary.get("n_source"))
                    if ns is not None:provenance.update(n_from_secondary=True,n=ns,n_unit=secondary.get('n_unit'),n_source=secondary.get('n_source'))
                primary["dispersion_provenance_json"]=json.dumps(provenance,sort_keys=True)
                basis_ids=sorted(set(basis_ids+json.loads(ex.get("basis_value_ids") or "[]")))
                con.execute("UPDATE wf_reconciliation SET status='RESOLVED',resolved_by='SOURCE_COMPLEMENT_RECHECK',updated_at=? WHERE study_id=? AND record_key=? AND family='SOURCE_COMPLEMENT' AND status='OPEN'",(now(),study_id,rk))
                changelog(con,run_id,"an_target_values",rk,"SOURCE_SUPPORTED_UNCERTAINTY_COMPLEMENT",provenance)
            else:
                # An adjudicated lower-priority reading must not reopen the conflict it settled.
                if old_primary and verification=="ADJUDICATED":
                    changelog(con,run_id,"an_target_values",rk,"ADJUDICATED_LOWER_PRIORITY_NOT_PROMOTED",{"basis":basis_ids})
                    return ex["tv_id"]
                # Keep the exact higher-priority mean. The incompatible lower-priority
                # reading remains in wf_values and is handled as a source conflict.
                from .tasks import create_task
                old_ids=json.loads(ex.get("basis_value_ids") or "[]")
                if old_ids and basis_ids:
                    con.execute("INSERT INTO wf_reconciliation(study_id,record_key,family,value_id_a,value_id_b,outcome,fields_conflict,status,created_at,updated_at) VALUES(?,?,?,?,?,'CONFLICT',?,'OPEN',?,?) ON CONFLICT(study_id,record_key,family) DO UPDATE SET value_id_b=excluded.value_id_b,status='OPEN',updated_at=excluded.updated_at",(study_id,rk,'SOURCE_COMPLEMENT',old_ids[0],basis_ids[0],json.dumps(['source_mean_unit_or_n']),now(),now()))
                    create_task(con,cfg,study_id,'ADJUDICATE','source-complement-'+str(old_ids[0])+'-'+str(basis_ids[0]))
                if old_primary:return ex["tv_id"]
        elif old_primary:
            return ex["tv_id"]
        v=primary
        if old_primary:verification=ex["verification"]
    arm = (rows(con, "SELECT * FROM wf_design_arms WHERE study_id=? AND arm_key=?", (study_id, v["arm_key"])) or [{}])[0]
    exp = (rows(con, "SELECT * FROM wf_design_experiments WHERE study_id=? AND experiment_key=?",
                (study_id, arm.get("experiment_key"))) or [{}])[0]
    tp = (rows(con, "SELECT * FROM wf_design_timepoints WHERE study_id=? AND timepoint_key=?",
               (study_id, v["timepoint_key"])) or [{}])[0]
    sd = sd_from(v.get("dispersion_type"), v.get("dispersion_value"), v.get("n"), v.get("ci") or json.loads(v.get("ci_json") or "null"))
    unit_norm, fac, _ = U.normalize(v.get("unit_raw") or "", v["endpoint"], v.get("denominator"))
    mean_norm = v["mean"] * fac if fac is not None and v.get("mean") is not None else None
    sd_norm = sd * fac if fac is not None and sd is not None else None
    dispersion_provenance=v.get("dispersion_provenance_json")
    if not dispersion_provenance and v.get("dispersion_value") is not None:
        dispersion_provenance=json.dumps({"source_kind":v.get("source_kind"),"source_file_id":v.get("source_file_id"),"receipt_id":v.get("receipt_id"),"source_cell":v.get("source_cell"),"locator":v.get("locator"),"value":v.get("dispersion_value"),"unit_raw":v.get("unit_raw"),"verification":verification,"basis_value_ids":basis_ids},sort_keys=True)
    vals = dict(
        study_id=study_id, record_key=rk, arm_key=v["arm_key"], experiment_key=arm.get("experiment_key"),
        dispersion_provenance_json=dispersion_provenance,n_source=v.get("n_source"),
        experiment_id=exp.get("experiment_id"), arm_id=arm.get("arm_id"), role=arm.get("role"),
        stress_code=arm.get("stress_code"), bio_code=arm.get("bio_code"), genotype=arm.get("genotype"),
        season=arm.get("season"), site=arm.get("site"), endpoint=v["endpoint"],
        yield_scope=v.get("yield_scope"), mass_basis=v.get("mass_basis"), denominator=v.get("denominator"),
        harvest_window=v.get("harvest_window"), organ_scope=v.get("organ_scope"),
        timepoint_key=v["timepoint_key"], timepoint_days=tp.get("days"), is_terminal=tp.get("is_terminal"),
        mean=v["mean"], dispersion_type=v.get("dispersion_type"), dispersion_value=v.get("dispersion_value"),
        dispersion_type_reported=v.get("dispersion_type_reported",v.get("dispersion_type")),
        dispersion_basis=v.get("dispersion_basis") or ("NOT_REPORTED" if v.get("dispersion_type") in ("NONE","UNCLEAR",None) else "SOURCE_REPORTED"),
        error_bar_status=v.get("error_bar_status"), error_bar_bounds_json=v.get("error_bar_bounds_json"),
        error_bar_relative_uncertainty=v.get("error_bar_relative_uncertainty"),
        sd=sd, n=v.get("n"), n_unit=v.get("n_unit"), unit_raw=v.get("unit_raw"), unit_norm=unit_norm,
        mean_norm=mean_norm, sd_norm=sd_norm, source_kind=v.get("source_kind"),
        source_file_id=v.get("source_file_id"), page=v.get("page"), locator=v.get("locator"),
        verbatim=v.get("verbatim"), figure_item_id=v.get("figure_item_id"), verification=verification,
        outcome_context_json=v.get("outcome_context_json") or json.dumps(v.get("outcome_context"),sort_keys=True),context_key=v.get("context_key"),ci_json=v.get("ci_json") or json.dumps(v.get("ci")),receipt_id=v.get("receipt_id"),source_cell=v.get("source_cell"),basis_value_ids=json.dumps(basis_ids), updated_at=now())
    if existing:
        sets = ", ".join(f"{k}=?" for k in vals)
        con.execute(f"UPDATE an_target_values SET {sets} WHERE study_id=? AND record_key=?", [*vals.values(), study_id, rk])
        tv_id = existing[0]["tv_id"]
    else:
        vals["created_at"] = now()
        cols = ", ".join(vals)
        con.execute(f"INSERT INTO an_target_values({cols}) VALUES ({', '.join('?' for _ in vals)})", list(vals.values()))
        tv_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    changelog(con, run_id, "an_target_values", rk, f"PROMOTE:{verification}", {"basis": basis_ids})
    return tv_id


# --------------------------------------------------------------- reconcile
def agree_override(a: Dict[str, Any], b: Dict[str, Any], cfg, figure: bool) -> Dict[str, Any]:
    """Fields promoted for an agreeing pair: figure readings are averaged, proof comes from the source."""
    override: Dict[str, Any] = {}
    if figure and cfg.get("reconcile.figure_agree_value", "mean") == "mean":
        da, db = a.get("dispersion_value"), b.get("dispersion_value")
        ua, ub = a.get("error_bar_relative_uncertainty"), b.get("error_bar_relative_uncertainty")
        override = {"mean": (a["mean"] + b["mean"]) / 2.0,
                    "dispersion_value": (da + db) / 2.0 if da is not None and db is not None else None,
                    "error_bar_relative_uncertainty": max(x for x in (ua, ub) if x is not None) if (ua is not None or ub is not None) else None,
                    "verbatim": a.get("verbatim"),
                    "notes": f"mean of 2 calibrated readings (FA={a['mean']:.6g}, FB={b['mean']:.6g})"}
    proof = b if b.get("receipt_id") else a
    if not proof.get("receipt_id"):
        raise ValueError("verification requires a check in the original source, not two Docling readings")
    override.update(receipt_id=proof.get("receipt_id"), source_cell=proof.get("source_cell"))
    return override


def _pair_context(con, study_id: str, family: str, A: Dict[str, Dict], B: Dict[str, Dict], cfg, figure: bool) -> None:
    """Free-text context_key must not split readings that match in every checked field."""
    def cell(v):
        # Biotic records are identified by slot and context; an optional organ label does not split them.
        attrs = () if v["endpoint"].startswith("BIOTIC_") else KEY_ATTRS.get(v["endpoint"], ATTRS)
        return (v.get("slot_id"), v["arm_key"], v["endpoint"], v["timepoint_key"],
                *(v.get(x) or "" for x in attrs))
    only_a: Dict[tuple, List[str]] = {}
    only_b: Dict[tuple, List[str]] = {}
    for k, v in A.items():
        if k not in B:
            only_a.setdefault(cell(v), []).append(k)
    for k, v in B.items():
        if k not in A:
            only_b.setdefault(cell(v), []).append(k)
    for c in set(only_a) & set(only_b):
        if len(only_a[c]) != 1 or len(only_b[c]) != 1:
            continue
        ka, kb = only_a[c][0], only_b[c][0]
        if [f for f in compare(A[ka], B[kb], cfg, figure) if f != "outcome_context"]:
            continue
        B[ka] = {**B.pop(kb), "outcome_context_json": A[ka].get("outcome_context_json")}
        con.execute("UPDATE wf_reconciliation SET status='RESOLVED',resolved_by='PAIRED_CONTEXT',updated_at=? "
                    "WHERE study_id=? AND record_key=? AND family=? AND status='OPEN'", (now(), study_id, kb, family))


def reconcile(con, cfg, study_id: str, family: str, slot_id: Optional[str] = None,
              run_id: Optional[str] = None) -> Dict[str, int]:
    """family TEXT_TABLE compares passes A/B; FIGURE compares FA/FB (optionally one slot)."""
    figure = family == "FIGURE"
    pa, pb = ("FA", "FB") if figure else ("A", "B")
    A = _latest(con, study_id, (pa,), figure, slot_id)
    B = _latest(con, study_id, (pb,), figure, slot_id)
    _pair_context(con, study_id, family, A, B, cfg, figure)
    stats = {"AGREE": 0, "CONFLICT": 0, "ONLY_A": 0, "ONLY_B": 0, "kept_resolved": 0}
    for rk in sorted(set(A) | set(B)):
        a, b = A.get(rk), B.get(rk)
        va, vb = (a or {}).get("value_id"), (b or {}).get("value_id")
        prev = rows(con, "SELECT * FROM wf_reconciliation WHERE study_id=? AND record_key=? AND family=?",
                    (study_id, rk, family))
        if prev and prev[0]["status"] == "RESOLVED" and prev[0]["resolved_by"] in ("ADJUDICATOR", "HUMAN") \
                and prev[0]["value_id_a"] == va and prev[0]["value_id_b"] == vb:
            stats["kept_resolved"] += 1
            continue
        if a and b:
            bad = compare(a, b, cfg, figure)
            outcome = "AGREE" if not bad else "CONFLICT"
        else:
            bad, outcome = ["missing_in_" + ("B" if a else "A")], ("ONLY_A" if a else "ONLY_B")
        stats[outcome] += 1
        status = "RESOLVED" if outcome == "AGREE" else "OPEN"
        resolved = None
        if outcome == "AGREE":
            promote(con, cfg, study_id, rk, a, "DOUBLE_AGREE", [va, vb], agree_override(a, b, cfg, figure), run_id)
            resolved = va
        if prev:
            con.execute("UPDATE wf_reconciliation SET value_id_a=?, value_id_b=?, outcome=?, fields_conflict=?, "
                        "status=?, resolved_value_id=?, resolved_by=?, updated_at=? WHERE rec_id=?",
                        (va, vb, outcome, json.dumps(bad), status, resolved, "AUTO" if resolved else None, now(),
                         prev[0]["rec_id"]))
        else:
            con.execute("INSERT INTO wf_reconciliation(study_id, record_key, family, value_id_a, value_id_b, outcome, "
                        "fields_conflict, status, resolved_value_id, resolved_by, created_at, updated_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (study_id, rk, family, va, vb, outcome, json.dumps(bad), status, resolved,
                         "AUTO" if resolved else None, now(), now()))
    changelog(con, run_id, "reconcile", f"{study_id}:{family}:{slot_id or ''}", "RECONCILE", stats)
    return stats


def refresh_slots(con, study_id: str) -> None:
    """Derive slot status from both passes' declarations and the reconciliation state.

    VERIFIED        both passes reported, >=1 value promoted, nothing open/escalated
    NOT_EXTRACTABLE both passes declared it (with reasons) or nothing survived adjudication
    EXTRACTED       values submitted, waiting for the other pass / adjudication / human
    """
    for s in rows(con, "SELECT * FROM wf_target_slots WHERE study_id=?", (study_id,)):
        if s["route"] not in ("EXTRACT", "FIGURE", "TWIN_VALIDATION"):
            continue
        sid = s["slot_id"]
        passes = ("FA", "FB") if s["route"] in ("FIGURE", "TWIN_VALIDATION") else ("A", "B")
        sp = {r["pass"]: r for r in rows(con, "SELECT * FROM wf_slot_pass WHERE slot_id=?", (sid,))}
        new, reason = s["status"], s["not_extractable_reason"]
        if not all(p in sp for p in passes):
            if any(r["status"] == "EXTRACTED" for r in sp.values()) and s["status"] == "OPEN":
                new = "EXTRACTED"
        else:
            vids = [r["value_id"] for r in rows(con, "SELECT value_id FROM wf_values WHERE slot_id=?", (sid,))]
            unresolved = verified = 0
            if vids:
                ph = ",".join("?" for _ in vids)
                unresolved = con.execute(
                    f"SELECT COUNT(*) FROM wf_reconciliation WHERE status IN ('OPEN','ESCALATED') AND "
                    f"(value_id_a IN ({ph}) OR value_id_b IN ({ph}))", vids + vids).fetchone()[0]
                verified = con.execute(
                    f"SELECT COUNT(*) FROM wf_reconciliation WHERE status='RESOLVED' AND resolved_value_id IS NOT NULL "
                    f"AND (value_id_a IN ({ph}) OR value_id_b IN ({ph}) OR resolved_value_id IN ({ph}))",
                    vids + vids + vids).fetchone()[0]
            if not vids and all(sp[p]["status"] == "NOT_EXTRACTABLE" for p in passes):
                new = "NOT_EXTRACTABLE"
                reason = " | ".join(f"{p}: {sp[p]['reason']}" for p in passes)
            elif unresolved:
                new = "EXTRACTED"
            elif verified >= int(s.get("expected_n_values") or 0) and verified > 0:
                new = "VERIFIED"
            elif verified:
                # Author decision 2026-11-05: keep what was verified and record what is missing.
                new = "VERIFIED_PARTIAL"
                reason = f"verified {verified} of {s.get('expected_n_values')} expected values; " + " | ".join(f"{p}: {sp[p].get('reason') or 'n/a'}" for p in passes)
            elif vids:
                new, reason = "NOT_EXTRACTABLE", "no value survived reconciliation/adjudication"
        if new != s["status"] or reason != s["not_extractable_reason"]:
            con.execute("UPDATE wf_target_slots SET status=?, not_extractable_reason=?, updated_at=? WHERE slot_id=?",
                        (new, reason, now(), sid))
