"""Global validation rules (core integrity + verified layer + contrasts).

Re-running is idempotent: issues that no longer occur are marked RESOLVED.
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from .db import ColumnResolver, now, q, rows, table_exists, tx
from .stats import mad_z

Issue = Tuple[str, str, Optional[str], str, str, str]   # rule, severity, study, entity, entity_id, message


def _pk_dupes(con, cr, table, field) -> List[Issue]:
    c = cr.get(table, field)
    if not c:
        return []
    out = []
    for r in rows(con, f"SELECT {q(c)} AS k, COUNT(*) n FROM {q(table)} WHERE {q(c)} IS NOT NULL "
                       f"GROUP BY {q(c)} HAVING COUNT(*) > 1"):
        out.append(("G001", "BLOCKING", None, table, str(r["k"]), f"{table}.{c} duplicated {r['n']} times"))
    return out


def _fk(con, cr, child, cfield, parent, pfield, sev="BLOCKING") -> List[Issue]:
    cc, pc = cr.get(child, cfield), cr.get(parent, pfield)
    if not cc or not pc:
        return []
    sql = (f"SELECT DISTINCT CAST(c.{q(cc)} AS TEXT) AS k FROM {q(child)} c WHERE c.{q(cc)} IS NOT NULL AND "
           f"CAST(c.{q(cc)} AS TEXT) NOT IN (SELECT CAST({q(pc)} AS TEXT) FROM {q(parent)} WHERE {q(pc)} IS NOT NULL)")
    return [("G002", sev, None, child, str(r["k"]), f"{child}.{cc}={r['k']} has no parent in {parent}.{pc}")
            for r in rows(con, sql)][:500]


def core_rules(con, cfg) -> List[Issue]:
    cr = ColumnResolver(con, cfg.column_map)
    out: List[Issue] = []
    for t, f in (("studies", "study_id"), ("experiments", "experiment_id"), ("arms", "arm_id"),
                 ("measurements", "measurement_id")):
        out += _pk_dupes(con, cr, t, f)
    out += _fk(con, cr, "experiments", "study_id", "studies", "study_id")
    out += _fk(con, cr, "arms", "experiment_id", "experiments", "experiment_id")
    out += _fk(con, cr, "measurements", "arm_id", "arms", "arm_id")
    out += _fk(con, cr, "measurements", "experiment_id", "experiments", "experiment_id")
    out += _fk(con, cr, "stress_factors", "arm_id", "arms", "arm_id")
    out += _fk(con, cr, "arm_components", "arm_id", "arms", "arm_id")
    sid, yr = cr.get("studies", "study_id"), cr.get("studies", "year")
    te, fpd = cr.get("studies", "temporal_eligibility"), cr.get("studies", "first_publication_date")
    dr, cls = cr.get("studies", "dataset_role"), cr.get("studies", "class_final")
    if sid and yr and te:
        for r in rows(con, f"SELECT {q(sid)} s, {q(yr)} y, {q(te)} t FROM studies"):
            y = r["y"]
            try:
                y = int(float(y)) if y not in (None, "") else None
            except (TypeError, ValueError):
                y = None
            if y and r["t"] == "PROVISIONAL_YEAR_UNKNOWN":
                exp = "ELIGIBLE_KNOWN_PRE2024" if y <= 2023 else "EXCLUDE_POST2023_KNOWN"
                out.append(("G003", "WARN", str(r["s"]), "studies", str(r["s"]),
                            f"year={y} is known but temporal_eligibility=PROVISIONAL_YEAR_UNKNOWN (expected {exp})"))
    if sid and dr:
        for r in rows(con, f"SELECT {q(sid)} s FROM studies WHERE {q(dr)} IS NULL OR TRIM({q(dr)})=''"):
            out.append(("G004", "WARN", str(r["s"]), "studies", str(r["s"]), "dataset_role empty (expected TRAIN_DEV)"))
    if sid and cls:
        for r in rows(con, f"SELECT {q(sid)} s, {q(cls)} c FROM studies WHERE COALESCE({q(cls)},'') <> 'A'"):
            out.append(("G005", "WARN", str(r["s"]), "studies", str(r["s"]), f"class_final={r['c']} in the class-A working set"))
    ms, se_, sd_, n_ = (cr.get("measurements", f) for f in ("measurement_id", "se", "sd", "n"))
    if ms and se_ and sd_ and n_:
        for r in rows(con, f"SELECT {q(ms)} id, {q(sd_)} sd, {q(se_)} se, {q(n_)} n FROM measurements "
                           f"WHERE {q(sd_)} IS NOT NULL AND {q(se_)} IS NOT NULL AND {q(n_)} IS NOT NULL"):
            try:
                sd, se, n = float(r["sd"]), float(r["se"]), float(r["n"])
            except (TypeError, ValueError):
                continue
            if sd > 0 and n > 0 and abs(sd - se * n ** 0.5) / sd > 0.10:
                out.append(("G006", "WARN", None, "measurements", str(r["id"]),
                            f"SD={sd} vs SE*sqrt(n)={se * n ** 0.5:.4g} differ >10 % (SE/SD swapped or n wrong?)"))
    return out


def verified_rules(con, cfg) -> List[Issue]:
    out: List[Issue] = []
    cvw = float(cfg.get("validation.cv_warn", 1.5))
    for tv in rows(con, "SELECT * FROM an_target_values"):
        k = tv["record_key"]
        if not tv["source_file_id"] or not tv["locator"]:
            out.append(("P001", "BLOCKING", tv["study_id"], "an_target_values", k, "verified value without source_file_id/locator"))
        if tv["mean"] is not None and tv["mean"] <= 0:
            out.append(("P002", "WARN", tv["study_id"], "an_target_values", k, "mean <= 0 (no lnRR)"))
        if tv["sd"] is not None and tv["mean"] and tv["mean"] > 0 and tv["sd"] / tv["mean"] > cvw:
            out.append(("P003", "WARN", tv["study_id"], "an_target_values", k, f"CV={tv['sd'] / tv['mean']:.2f}"))
        if tv["n"] is None:
            out.append(("P004", "WARN", tv["study_id"], "an_target_values", k, "n missing"))
        if tv["arm_id"] is None:
            out.append(("P005", "INFO", tv["study_id"], "an_target_values", k, "arm not linked to a core arm_id"))
    # identical value vectors in two studies -> possible duplicate publication
    vec: Dict[str, List[float]] = defaultdict(list)
    for r in rows(con, "SELECT study_id, mean FROM an_target_values WHERE mean IS NOT NULL ORDER BY study_id, mean"):
        vec[r["study_id"]].append(round(float(r["mean"]), 6))
    seen: Dict[Tuple, str] = {}
    for s, v in vec.items():
        if len(v) < 3:
            continue
        key = tuple(v)
        if key in seen:
            out.append(("P006", "WARN", s, "study", s, f"identical verified values as study {seen[key]} — run DEDUP"))
        else:
            seen[key] = s
    return out


def contrast_rules(con, cfg) -> List[Issue]:
    out: List[Issue] = []
    thr = float(cfg.get("validation.mad_z_flag", 4.5))
    for ep in [r["endpoint"] for r in rows(con, "SELECT DISTINCT endpoint FROM an_contrasts")]:
        cs = rows(con, "SELECT contrast_id, study_id, effect FROM an_contrasts WHERE endpoint=? AND contrast_type='SB_vs_S' "
                       "AND effect IS NOT NULL", (ep,))
        zs = mad_z([c["effect"] for c in cs])
        for c, z in zip(cs, zs):
            if abs(z) > thr:
                out.append(("C001", "WARN", c["study_id"], "an_contrasts", c["contrast_id"],
                            f"{ep} lnRR={c['effect']:.3f} is a robust outlier (|z_MAD|={abs(z):.1f} > {thr}) — review, never delete"))
    for c in rows(con, "SELECT contrast_id, study_id FROM an_contrasts WHERE contrast_type='SB_vs_S' AND effect IS NULL"):
        out.append(("C002", "WARN", c["study_id"], "an_contrasts", c["contrast_id"], "lnRR not computable (non-positive mean)"))
    return out


def run(con, cfg, run_id: Optional[str] = None, scopes: Tuple[str, ...] = ("core", "verified", "contrasts")) -> Dict[str, int]:
    found: List[Issue] = []
    rules_run: Set[str] = set()
    if "core" in scopes and table_exists(con, "studies"):
        found += core_rules(con, cfg)
        rules_run |= {"G001", "G002", "G003", "G004", "G005", "G006"}
    if "verified" in scopes:
        found += verified_rules(con, cfg)
        rules_run |= {"P001", "P002", "P003", "P004", "P005", "P006"}
    if "contrasts" in scopes:
        found += contrast_rules(con, cfg)
        rules_run |= {"C001", "C002"}
    keys = {(r, s or "", e, i, m) for r, _, s, e, i, m in found}
    with tx(con):
        for r in rows(con, "SELECT issue_id, rule_id, study_id, entity, entity_id, message FROM wf_validation "
                           "WHERE status='OPEN' AND rule_id IN (%s)" % ",".join("?" for _ in rules_run), list(rules_run)):
            if (r["rule_id"], r["study_id"] or "", r["entity"], r["entity_id"], r["message"]) not in keys:
                con.execute("UPDATE wf_validation SET status='RESOLVED', resolved_at=?, resolution='no longer detected' "
                            "WHERE issue_id=?", (now(), r["issue_id"]))
        for rule, sev, study, ent, eid, msg in found:
            ex = con.execute("SELECT 1 FROM wf_validation WHERE rule_id=? AND COALESCE(study_id,'')=? AND entity=? AND "
                             "entity_id=? AND message=? AND status='OPEN'", (rule, study or "", ent, eid, msg)).fetchone()
            # A reviewed flag stays closed while its contrast and effect are unchanged; z_MAD moves with the pool.
            waived = con.execute("SELECT 1 FROM wf_validation WHERE rule_id=? AND COALESCE(study_id,'')=? AND entity=? AND "
                                 "entity_id=? AND message LIKE ? AND status='WAIVED'",
                                 (rule, study or "", ent, eid, msg.split(" (|z_MAD|")[0] + "%")).fetchone()
            if not ex and not waived:
                con.execute("INSERT INTO wf_validation(rule_id, severity, study_id, entity, entity_id, message, status, "
                            "run_id, created_at) VALUES (?,?,?,?,?,?, 'OPEN', ?, ?)",
                            (rule, sev, study, ent, eid, msg, run_id, now()))
    counts: Dict[str, int] = defaultdict(int)
    for rule, sev, *_ in found:
        counts[f"{rule}:{sev}"] += 1
    return dict(sorted(counts.items()))
