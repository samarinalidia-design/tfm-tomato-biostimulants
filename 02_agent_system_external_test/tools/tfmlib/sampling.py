"""Gold standard (30-40 studies, manual, blind) and the TFM 3.10 audit sample."""
from __future__ import annotations

import csv
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import numbers as N
from . import units as U
from .db import now, rows, set_meta, tx
from .reconcile import KEY_ATTRS, record_key
from .tasks import create_task

GOLD_COLS = ["study_id", "arm_label_in_paper", "arm_key", "endpoint", "yield_scope", "mass_basis", "denominator",
             "harvest_window", "organ_scope", "timepoint_label", "timepoint_key", "mean", "dispersion_type",
             "dispersion_value", "n", "unit_raw", "source_kind", "locator", "entered_by"]


def _strata(con) -> Dict[str, str]:
    out = {}
    for s in rows(con, "SELECT study_id, GROUP_CONCAT(DISTINCT endpoint) eps, GROUP_CONCAT(DISTINCT source_kind) srcs "
                       "FROM wf_target_slots WHERE route IN ('EXTRACT','FIGURE') GROUP BY study_id"):
        ep = "YIELD" if "FRUIT_YIELD" in (s["eps"] or "") else "BIOMASS"
        src = "FIGURE" if (s["srcs"] or "") == "FIGURE" else ("MIXED" if "FIGURE" in (s["srcs"] or "") else "TABLE_TEXT")
        out[s["study_id"]] = f"{ep}|{src}"
    return out


def gold_sample(con, cfg, n: int, out_dir: Path, seed: Optional[int] = None) -> Dict[str, Any]:
    strata = _strata(con)
    if not strata:
        raise RuntimeError("no studies with target slots yet — run TRIAGE first")
    rnd = random.Random(seed if seed is not None else cfg.get("queue.random_seed", 1))
    by: Dict[str, List[str]] = defaultdict(list)
    for s, k in sorted(strata.items()):
        by[k].append(s)
    total = sum(len(v) for v in by.values())
    alloc = {k: max(1, round(n * len(v) / total)) for k, v in by.items()}
    while sum(alloc.values()) > n and max(alloc.values()) > 1:
        alloc[max(alloc, key=alloc.get)] -= 1
    picked = []
    for k, v in by.items():
        picked += [(s, k) for s in rnd.sample(v, min(alloc[k], len(v)))]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "gold_studies.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["study_id", "stratum", "slots"])
        for s, k in sorted(picked):
            sl = rows(con, "SELECT locator_label, endpoint FROM wf_target_slots WHERE study_id=?", (s,))
            w.writerow([s, k, "; ".join(f"{x['endpoint']}@{x['locator_label']}" for x in sl)])
    with open(out_dir / "gold_entry_template.csv", "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerow(GOLD_COLS)
    with open(out_dir / "gold_design_keys.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["study_id", "kind", "key", "label_in_source", "description"])
        for s, _ in sorted(picked):
            for a in rows(con, "SELECT arm_key, label_in_source, stress_desc, bio_desc FROM wf_design_arms WHERE study_id=?", (s,)):
                w.writerow([s, "arm", a["arm_key"], a["label_in_source"], f"{a['stress_desc']} / {a['bio_desc']}"])
            for t in rows(con, "SELECT timepoint_key, label FROM wf_design_timepoints WHERE study_id=?", (s,)):
                w.writerow([s, "timepoint", t["timepoint_key"], t["label"], ""])
    set_meta(con, "gold_sample", [s for s, _ in picked])
    return {"n": len(picked), "strata": {k: alloc[k] for k in alloc}, "out_dir": str(out_dir)}


def _f(x):
    if x in (None, ""):
        return None
    v = N.parse_number(str(x))
    return v


def gold_import(con, path: Path, entered_by: str = "author") -> int:
    n = 0
    with open(path, newline="", encoding="utf-8-sig") as fh, tx(con):
        for r in csv.DictReader(fh):
            if not r.get("study_id") or r.get("mean") in (None, ""):
                continue
            con.execute("INSERT INTO wf_gold(study_id, arm_key, endpoint, timepoint_key, yield_scope, mass_basis, denominator, "
                        "harvest_window, organ_scope, mean, dispersion_type, dispersion_value, n, unit_raw, source_kind, "
                        "locator, entered_by, entered_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (r["study_id"].strip(), (r.get("arm_key") or "").strip() or None, r.get("endpoint"),
                         (r.get("timepoint_key") or "").strip() or None, r.get("yield_scope") or None,
                         r.get("mass_basis") or None, r.get("denominator") or None, r.get("harvest_window") or None,
                         r.get("organ_scope") or None, _f(r.get("mean")), r.get("dispersion_type") or None,
                         _f(r.get("dispersion_value")), _f(r.get("n")), r.get("unit_raw"), r.get("source_kind"),
                         r.get("locator"), r.get("entered_by") or entered_by, now()))
            n += 1
    return n


def gold_score(con, cfg) -> Dict[str, Any]:
    gold = rows(con, "SELECT * FROM wf_gold")
    res = {"gold_values": len(gold), "matched": 0, "mean_exact": 0, "mean_exact_den": 0, "disp_exact": 0, "disp_den": 0,
           "n_exact": 0, "n_den": 0, "unit_exact": 0, "figure_rel_errors": [], "unmatched": []}
    for g in gold:
        if not g["arm_key"] or not g["timepoint_key"] or not g["endpoint"]:
            res["unmatched"].append({"gold_id": g["gold_id"], "why": "arm_key/timepoint_key/endpoint not filled"})
            continue
        rk = record_key(dict(g))
        tv = rows(con, "SELECT * FROM an_target_values WHERE study_id=? AND record_key=?", (g["study_id"], rk))
        if not tv:
            res["unmatched"].append({"gold_id": g["gold_id"], "record_key": rk, "why": "not in verified layer"})
            continue
        tv = tv[0]
        res["matched"] += 1
        if tv["source_kind"] == "FIGURE" or (g["source_kind"] or "").upper() == "FIGURE":
            if g["mean"]:
                res["figure_rel_errors"].append(abs(tv["mean"] - g["mean"]) / abs(g["mean"]))
        else:
            res["mean_exact_den"] += 1
            res["mean_exact"] += int(N.close(tv["mean"], g["mean"] or float("nan")))
        if g["dispersion_type"]:
            res["disp_den"] += 1
            same_type = (tv["dispersion_type"] or "") == g["dispersion_type"]
            same_val = (g["dispersion_value"] is None and tv["dispersion_value"] is None) or (
                g["dispersion_value"] is not None and tv["dispersion_value"] is not None and
                abs(tv["dispersion_value"] - g["dispersion_value"]) <= 0.01 * max(abs(g["dispersion_value"]), 1e-9))
            res["disp_exact"] += int(same_type and same_val)
        if g["n"] is not None:
            res["n_den"] += 1
            res["n_exact"] += int(tv["n"] is not None and abs(tv["n"] - g["n"]) < 1e-9)
        res["unit_exact"] += int((U.normalize(g["unit_raw"] or "", g["endpoint"])[0] or (g["unit_raw"] or "").lower())
                                 == (tv["unit_norm"] or (tv["unit_raw"] or "").lower()))
    acc = cfg.get("acceptance") or {}
    fe = sorted(res.pop("figure_rel_errors"))
    summary = {
        "gold_values": res["gold_values"],
        "recall_values": round(res["matched"] / res["gold_values"], 4) if res["gold_values"] else None,
        "table_mean_exact": round(res["mean_exact"] / res["mean_exact_den"], 4) if res["mean_exact_den"] else None,
        "dispersion_exact": round(res["disp_exact"] / res["disp_den"], 4) if res["disp_den"] else None,
        "n_exact": round(res["n_exact"] / res["n_den"], 4) if res["n_den"] else None,
        "figure_median_rel_err": round(fe[len(fe) // 2], 4) if fe else None,
        "figure_p95_rel_err": round(fe[min(len(fe) - 1, int(0.95 * len(fe)))], 4) if fe else None,
        "unmatched": res["unmatched"][:200],
    }
    verdict = {}
    for k, thr, higher in (("recall_values", acc.get("recall_values", 0.95), True),
                           ("table_mean_exact", acc.get("table_mean_exact", 0.98), True),
                           ("dispersion_exact", acc.get("dispersion_exact", 0.95), True),
                           ("n_exact", acc.get("n_exact", 0.95), True),
                           ("figure_median_rel_err", acc.get("figure_median_rel_err", 0.03), False),
                           ("figure_p95_rel_err", acc.get("figure_p95_rel_err", 0.08), False)):
        v = summary[k]
        verdict[k] = None if v is None else ("PASS" if (v >= thr if higher else v <= thr) else "FAIL")
    summary["verdict"] = verdict
    with tx(con):
        set_meta(con, "last_gold_score", summary)
    return summary


def audit_sample(con, cfg, out_csv: Path, create_agent_tasks: bool = False, seed: Optional[int] = None) -> Dict[str, Any]:
    tvs = rows(con, "SELECT * FROM an_target_values ORDER BY tv_id")
    N_ = len(tvs)
    if not N_:
        raise RuntimeError("no verified values yet")
    k = min(N_, max(20, math.ceil(0.15 * N_)))
    rnd = random.Random(seed if seed is not None else cfg.get("queue.random_seed", 1))
    by: Dict[str, List[Dict]] = defaultdict(list)
    for t in tvs:
        by[f"{t['endpoint']}|{'FIGURE' if t['source_kind'] == 'FIGURE' else 'TABLE_TEXT'}"].append(t)
    picked: List[Dict] = []
    for key, items in sorted(by.items()):
        m = max(1, round(k * len(items) / N_))
        picked += rnd.sample(items, min(m, len(items)))
    picked = picked[:k] if len(picked) > k else picked
    cols = ["tv_id", "study_id", "arm_key", "endpoint", "timepoint_key", "mean", "dispersion_type", "dispersion_value", "n",
            "unit_raw", "source_kind", "source_file_id", "page", "locator", "verbatim", "verification",
            "verdict(CORRECT/INCORRECT/UNSURE)", "field_errors", "corrected_value", "notes"]
    Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for t in sorted(picked, key=lambda x: (x["study_id"], x["tv_id"])):
            w.writerow([t.get(c) if c in t else "" for c in cols])
    if create_agent_tasks:
        with tx(con):
            by_study: Dict[str, List[int]] = defaultdict(list)
            for t in picked:
                by_study[t["study_id"]].append(t["tv_id"])
            for s, ids in by_study.items():
                create_task(con, cfg, s, "AUDIT", "audit:" + ",".join(str(i) for i in sorted(ids)))
    return {"N_verified": N_, "k": len(picked), "formula": "min(N, max(20, ceil(0.15*N)))", "csv": str(out_csv)}


def audit_import(con, path: Path, reviewer: str = "author") -> int:
    n = 0
    with open(path, newline="", encoding="utf-8-sig") as fh, tx(con):
        for r in csv.DictReader(fh):
            v = (r.get("verdict(CORRECT/INCORRECT/UNSURE)") or r.get("verdict") or "").strip().upper()
            if v not in ("CORRECT", "INCORRECT", "UNSURE"):
                continue
            con.execute("INSERT INTO wf_audit(tv_id, run_id, verdict, field_errors, corrected, notes, created_at) "
                        "VALUES (?,?,?,?,?,?,?)", (int(r["tv_id"]), f"HUMAN-{reviewer}", v,
                                                   json.dumps([x.strip() for x in (r.get("field_errors") or "").split(",") if x.strip()]),
                                                   json.dumps(r.get("corrected_value") or None), r.get("notes"), now()))
            n += 1
    return n
